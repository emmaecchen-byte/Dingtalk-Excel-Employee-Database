import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models import Company, Employee
from app.services.dingtalk_api import DingTalkAPIError, dingtalk_corp_client

logger = logging.getLogger(__name__)


@dataclass
class EmployeeSyncSummary:
    added: int = 0
    updated: int = 0
    deactivated: int = 0
    total_from_dingtalk: int = 0
    message: str = ""


def _department_name(dept_map: Dict[int, str], dept_id_list: List[int]) -> str:
    if not dept_id_list:
        return ""
    for dept_id in dept_id_list:
        if dept_id in dept_map:
            return dept_map[dept_id]
    return dept_map.get(dept_id_list[0], f"Department {dept_id_list[0]}")


def _employee_changed(existing: Employee, *, name: str, department: str, position: Optional[str], employee_code: Optional[str]) -> bool:
    return (
        existing.name != name
        or existing.department != department
        or (existing.position or "") != (position or "")
        or (existing.employee_code or "") != (employee_code or "")
        or not existing.is_active
    )


def fetch_dingtalk_employees(root_dept_id: int) -> Tuple[Dict[str, Dict], Dict[int, str]]:
    dept_ids = dingtalk_corp_client.collect_all_department_ids(root_dept_id)
    dept_map: Dict[int, str] = {}
    for dept_id in dept_ids:
        dept_map[dept_id] = dingtalk_corp_client.get_department_name(dept_id)

    basic_users: Dict[str, Dict] = {}
    for dept_id in dept_ids:
        for user in dingtalk_corp_client.list_users_in_department(dept_id):
            userid = user.get("userid")
            if userid:
                basic_users[userid] = user

    logger.info("Found %s unique employees across DingTalk departments", len(basic_users))

    detailed_users: Dict[str, Dict] = {}
    for index, userid in enumerate(basic_users.keys(), start=1):
        detail = dingtalk_corp_client.get_user_detail(userid)
        detailed_users[userid] = detail
        if index % 25 == 0:
            logger.info("Fetched detailed profiles for %s/%s employees", index, len(basic_users))

    return detailed_users, dept_map


def sync_employees_for_company(db: Session, company: Company, root_dept_id: int) -> EmployeeSyncSummary:
    if not dingtalk_corp_client.is_configured():
        raise DingTalkAPIError(
            "DingTalk API is not configured. Set DINGTALK_CLIENT_ID and DINGTALK_CLIENT_SECRET.",
            status_code=503,
        )

    logger.info("Starting employee sync for company_id=%s", company.id)
    dingtalk_users, dept_map = fetch_dingtalk_employees(root_dept_id)
    summary = EmployeeSyncSummary(total_from_dingtalk=len(dingtalk_users))

    existing_employees: List[Employee] = (
        db.query(Employee).filter(Employee.company_id == company.id).all()
    )
    existing_by_dingtalk_id = {
        employee.dingtalk_user_id: employee
        for employee in existing_employees
        if employee.dingtalk_user_id
    }
    seen_ids: Set[str] = set()

    for userid, profile in dingtalk_users.items():
        seen_ids.add(userid)
        raw_dept_ids = profile.get("dept_id_list") or profile.get("deptIdList") or []
        if isinstance(raw_dept_ids, str):
            raw_dept_ids = [part for part in raw_dept_ids.split(",") if part]

        dept_ids: List[int] = []
        for item in raw_dept_ids:
            try:
                dept_ids.append(int(item))
            except (TypeError, ValueError):
                continue

        name = profile.get("name") or profile.get("nick") or userid
        department = _department_name(dept_map, dept_ids)
        position = profile.get("title") or profile.get("position")
        employee_code = profile.get("job_number") or profile.get("jobNumber")

        existing = existing_by_dingtalk_id.get(userid)
        if existing:
            if _employee_changed(
                existing,
                name=name,
                department=department,
                position=position,
                employee_code=employee_code,
            ):
                existing.name = name
                existing.department = department
                existing.position = position
                existing.employee_code = employee_code
                existing.is_active = True
                summary.updated += 1
                logger.info("Updated employee %s (%s)", name, userid)
        else:
            employee = Employee(
                company_id=company.id,
                dingtalk_user_id=userid,
                name=name,
                department=department,
                position=position,
                employee_code=employee_code,
                is_active=True,
            )
            db.add(employee)
            summary.added += 1
            logger.info("Added employee %s (%s)", name, userid)

    for employee in existing_employees:
        if employee.dingtalk_user_id and employee.dingtalk_user_id not in seen_ids and employee.is_active:
            employee.is_active = False
            summary.deactivated += 1
            logger.info("Deactivated employee %s (%s)", employee.name, employee.dingtalk_user_id)

    db.commit()
    summary.message = (
        f"Employee sync completed: {summary.added} added, "
        f"{summary.updated} updated, {summary.deactivated} deactivated"
    )
    logger.info(summary.message)
    return summary
