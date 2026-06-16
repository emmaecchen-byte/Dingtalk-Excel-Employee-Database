#!/usr/bin/env python3
"""
Idempotent demo database seeder for local testing without DingTalk.

Seeds:
  - Demo Company + admin/viewer users
  - 15 employees with May 2026 attendance (mixed anomalies)
  - Excel snapshot + version_history

Usage:
    npm run seed                          # from repo root
    python scripts/seed_demo_data.py      # from backend/
    python scripts/seed_demo_data.py --force   # rebuild May 2026 rows

Logins:
    admin@demo.com  / Admin123!   (hr_admin)
    viewer@demo.com / Viewer123!  (hr_viewer)
"""

from __future__ import annotations

import argparse
import calendar
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow `python scripts/seed_demo_data.py` without installing the package.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.database import SessionLocal
from app.db_upgrade import ensure_auth_schema
from app.models import (
    Company,
    Employee,
    ExcelSnapshot,
    ManualChange,
    MonthlyAttendance,
    User,
    VersionHistory,
)
from app.services.snapshot_service import create_snapshot

logger = logging.getLogger(__name__)

DEMO_COMPANY_NAME = "Demo Company"
DEMO_CORP_ID = "demo_corp_001"
DEMO_YEAR = 2026
DEMO_MONTH = 5

DEMO_ADMIN_EMAIL = "admin@demo.com"
DEMO_VIEWER_EMAIL = "viewer@demo.com"
DEMO_ADMIN_PASSWORD = "Admin123!"
DEMO_VIEWER_PASSWORD = "Viewer123!"

DEMO_EMPLOYEES: List[Dict[str, Any]] = [
    {
        "name": "陈鹏",
        "department": "朋创",
        "position": "工程师",
        "employee_code": "E001",
        "dingtalk_user_id": "dt_user_001",
        "total_attendance_days": 21,
        "absenteeism_count": 0,
        "lateness_count": 0,
        "missing_punch_count": 0,
        "supplement_submitted": False,
        "anomaly_summary": None,
        "notes": None,
    },
    {
        "name": "芮超杰",
        "department": "电机部",
        "position": "技术员",
        "employee_code": "E002",
        "dingtalk_user_id": "dt_user_002",
        "total_attendance_days": 18,
        "absenteeism_count": 1,
        "lateness_count": 0,
        "missing_punch_count": 0,
        "supplement_submitted": True,
        "anomaly_summary": "旷工1天",
        "notes": "已提交补卡申请",
    },
    {
        "name": "张成",
        "department": "项目推进部",
        "position": "项目经理",
        "employee_code": "E003",
        "dingtalk_user_id": "dt_user_003",
        "total_attendance_days": 20,
        "absenteeism_count": 2,
        "lateness_count": 1,
        "missing_punch_count": 0,
        "supplement_submitted": False,
        "anomaly_summary": "迟到、旷工2天",
        "notes": None,
    },
    {
        "name": "蔡传军",
        "department": "朋创",
        "position": "主管",
        "employee_code": "E004",
        "dingtalk_user_id": "dt_user_004",
        "total_attendance_days": 22,
        "absenteeism_count": 0,
        "lateness_count": 0,
        "missing_punch_count": 1,
        "supplement_submitted": False,
        "anomaly_summary": "缺卡1天",
        "notes": "年假",
    },
    {
        "name": "李明",
        "department": "电机部",
        "position": "工程师",
        "employee_code": "E005",
        "dingtalk_user_id": "dt_user_005",
        "total_attendance_days": 19,
        "absenteeism_count": 0,
        "lateness_count": 2,
        "missing_punch_count": 1,
        "supplement_submitted": True,
        "anomaly_summary": "迟到2次、缺卡1天",
        "notes": "出差返程迟到",
    },
    {
        "name": "王芳",
        "department": "人事部",
        "position": "HR专员",
        "employee_code": "E006",
        "dingtalk_user_id": "dt_user_006",
        "total_attendance_days": 22,
        "absenteeism_count": 0,
        "lateness_count": 0,
        "missing_punch_count": 0,
        "supplement_submitted": False,
        "anomaly_summary": None,
        "notes": None,
    },
    {
        "name": "赵强",
        "department": "朋创",
        "position": "质检员",
        "employee_code": "E007",
        "dingtalk_user_id": "dt_user_007",
        "total_attendance_days": 17,
        "absenteeism_count": 1,
        "lateness_count": 1,
        "missing_punch_count": 2,
        "supplement_submitted": True,
        "anomaly_summary": "旷工1天、迟到1次、缺卡2天",
        "notes": "待补单",
    },
    {
        "name": "刘洋",
        "department": "项目推进部",
        "position": "助理",
        "employee_code": "E008",
        "dingtalk_user_id": "dt_user_008",
        "total_attendance_days": 21,
        "absenteeism_count": 0,
        "lateness_count": 1,
        "missing_punch_count": 0,
        "supplement_submitted": False,
        "anomaly_summary": "迟到1次",
        "notes": None,
    },
    {
        "name": "孙丽",
        "department": "电机部",
        "position": "文员",
        "employee_code": "E009",
        "dingtalk_user_id": "dt_user_009",
        "total_attendance_days": 20,
        "absenteeism_count": 0,
        "lateness_count": 0,
        "missing_punch_count": 0,
        "supplement_submitted": True,
        "anomaly_summary": None,
        "notes": "哺乳假",
    },
    {
        "name": "周杰",
        "department": "朋创",
        "position": "操作工",
        "employee_code": "E010",
        "dingtalk_user_id": "dt_user_010",
        "total_attendance_days": 16,
        "absenteeism_count": 2,
        "lateness_count": 0,
        "missing_punch_count": 1,
        "supplement_submitted": False,
        "anomaly_summary": "旷工2天、缺卡1天",
        "notes": None,
    },
    {
        "name": "吴敏",
        "department": "人事部",
        "position": "薪酬专员",
        "employee_code": "E011",
        "dingtalk_user_id": "dt_user_011",
        "total_attendance_days": 21,
        "absenteeism_count": 0,
        "lateness_count": 3,
        "missing_punch_count": 0,
        "supplement_submitted": True,
        "anomaly_summary": "迟到3次",
        "notes": "早高峰堵车",
    },
    {
        "name": "郑浩",
        "department": "项目推进部",
        "position": "工程师",
        "employee_code": "E012",
        "dingtalk_user_id": "dt_user_012",
        "total_attendance_days": 19,
        "absenteeism_count": 1,
        "lateness_count": 2,
        "missing_punch_count": 1,
        "supplement_submitted": False,
        "anomaly_summary": "旷工1天、迟到2次、缺卡1天",
        "notes": "项目现场考勤",
    },
    {
        "name": "黄涛",
        "department": "质量部",
        "position": "检验员",
        "employee_code": "E013",
        "dingtalk_user_id": "dt_user_013",
        "total_attendance_days": 22,
        "absenteeism_count": 0,
        "lateness_count": 0,
        "missing_punch_count": 0,
        "supplement_submitted": False,
        "anomaly_summary": None,
        "notes": None,
    },
    {
        "name": "马婷",
        "department": "财务部",
        "position": "会计",
        "employee_code": "E014",
        "dingtalk_user_id": "dt_user_014",
        "total_attendance_days": 21,
        "absenteeism_count": 0,
        "lateness_count": 1,
        "missing_punch_count": 0,
        "supplement_submitted": True,
        "anomaly_summary": "迟到1次",
        "notes": "月末结账加班",
    },
    {
        "name": "徐磊",
        "department": "朋创",
        "position": "班组长",
        "employee_code": "E015",
        "dingtalk_user_id": "dt_user_015",
        "total_attendance_days": 3,
        "absenteeism_count": 19,
        "lateness_count": 0,
        "missing_punch_count": 0,
        "supplement_submitted": False,
        "anomaly_summary": "旷工19天",
        "notes": "长期缺勤待核实",
    },
]

DEMO_MANUAL_CHANGES = [
    {"employee_code": "E002", "field_name": "notes", "old_value": "", "new_value": "已提交补卡申请"},
    {"employee_code": "E005", "field_name": "lateness_count", "old_value": "1", "new_value": "2"},
    {"employee_code": "E007", "field_name": "missing_punch_count", "old_value": "1", "new_value": "2"},
    {"employee_code": "E011", "field_name": "notes", "old_value": "", "new_value": "早高峰堵车"},
]


def _is_weekend(year: int, month: int, day: int) -> bool:
    return date(year, month, day).weekday() >= 5


def _build_day_values(
    year: int,
    month: int,
    *,
    absenteeism_count: int,
    lateness_count: int,
    missing_punch_count: int,
) -> Dict[str, Optional[str]]:
    """Assign realistic day statuses for weekdays in the target month."""
    days_in_month = calendar.monthrange(year, month)[1]
    values: Dict[str, Optional[str]] = {f"day_{day}": None for day in range(1, 32)}

    weekdays = [day for day in range(1, days_in_month + 1) if not _is_weekend(year, month, day)]
    for day in range(1, days_in_month + 1):
        if _is_weekend(year, month, day):
            values[f"day_{day}"] = None
        else:
            values[f"day_{day}"] = "√"

    cursor = 0

    def take_day(status: str) -> None:
        nonlocal cursor
        while cursor < len(weekdays):
            day = weekdays[cursor]
            cursor += 1
            if values[f"day_{day}"] == "√":
                values[f"day_{day}"] = status
                return

    for _ in range(absenteeism_count):
        take_day("旷工")
    for _ in range(lateness_count):
        take_day("迟到")
    for _ in range(missing_punch_count):
        take_day("缺卡")

    return values


def _build_overtime_day_values(
    year: int,
    month: int,
    *,
    employee_index: int,
) -> Dict[str, Optional[float]]:
    """Assign sample daily overtime hours on a few weekdays."""
    days_in_month = calendar.monthrange(year, month)[1]
    values: Dict[str, Optional[float]] = {f"overtime_day_{day}": None for day in range(1, 32)}
    weekdays = [day for day in range(1, days_in_month + 1) if not _is_weekend(year, month, day)]
    if len(weekdays) < 2:
        return values

    start = employee_index % max(1, len(weekdays) - 2)
    selected_days = weekdays[start : start + 3]
    hour_options = [2.0, 3.0, 4.0, 2.5, 3.5, 1.5]
    for offset, day in enumerate(selected_days):
        values[f"overtime_day_{day}"] = hour_options[(employee_index + offset) % len(hour_options)]
    return values


def _get_or_create_company(db: Session) -> Company:
    company = (
        db.query(Company)
        .filter((Company.dingtalk_corp_id == DEMO_CORP_ID) | (Company.name == DEMO_COMPANY_NAME))
        .first()
    )
    if company:
        if company.name != DEMO_COMPANY_NAME:
            company.name = DEMO_COMPANY_NAME
        if not company.dingtalk_corp_id:
            company.dingtalk_corp_id = DEMO_CORP_ID
        return company

    company = Company(name=DEMO_COMPANY_NAME, dingtalk_corp_id=DEMO_CORP_ID)
    db.add(company)
    db.flush()
    logger.info("Created demo company: %s", DEMO_COMPANY_NAME)
    return company


def _get_or_create_user(
    db: Session,
    *,
    company_id: int,
    email: str,
    name: str,
    role: str,
    password: str,
) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.company_id = company_id
        user.name = name
        user.role = role
        user.is_active = True
        user.password_hash = hash_password(password)
        return user

    user = User(
        company_id=company_id,
        name=name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    logger.info("Created demo user: %s (%s)", email, role)
    return user


def _get_or_create_employee(db: Session, company_id: int, spec: Dict[str, Any]) -> Employee:
    employee = (
        db.query(Employee)
        .filter(
            Employee.company_id == company_id,
            Employee.employee_code == spec["employee_code"],
        )
        .first()
    )
    if employee:
        employee.name = spec["name"]
        employee.department = spec["department"]
        employee.position = spec["position"]
        employee.dingtalk_user_id = spec["dingtalk_user_id"]
        employee.is_active = True
        return employee

    employee = Employee(
        company_id=company_id,
        dingtalk_user_id=spec["dingtalk_user_id"],
        name=spec["name"],
        department=spec["department"],
        position=spec["position"],
        employee_code=spec["employee_code"],
        is_active=True,
    )
    db.add(employee)
    db.flush()
    return employee


def _upsert_attendance(
    db: Session,
    *,
    company_id: int,
    employee_id: int,
    spec: Dict[str, Any],
    sync_time: datetime,
    force: bool,
    employee_index: int = 0,
) -> MonthlyAttendance:
    record = (
        db.query(MonthlyAttendance)
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == DEMO_YEAR,
            MonthlyAttendance.month == DEMO_MONTH,
            MonthlyAttendance.employee_id == employee_id,
        )
        .first()
    )
    if record and not force:
        return record

    day_values = _build_day_values(
        DEMO_YEAR,
        DEMO_MONTH,
        absenteeism_count=int(spec["absenteeism_count"]),
        lateness_count=int(spec["lateness_count"]),
        missing_punch_count=int(spec["missing_punch_count"]),
    )
    overtime_values = _build_overtime_day_values(
        DEMO_YEAR,
        DEMO_MONTH,
        employee_index=employee_index,
    )

    if record is None:
        record = MonthlyAttendance(
            company_id=company_id,
            year=DEMO_YEAR,
            month=DEMO_MONTH,
            employee_id=employee_id,
        )
        db.add(record)

    record.total_attendance_days = int(spec["total_attendance_days"])
    record.absenteeism_count = int(spec["absenteeism_count"])
    record.lateness_count = int(spec["lateness_count"])
    record.missing_punch_count = int(spec["missing_punch_count"])
    record.anomaly_summary = spec.get("anomaly_summary")
    record.supplement_submitted = bool(spec.get("supplement_submitted", False))
    record.notes = spec.get("notes")
    record.total_personal_leave = 0
    record.total_sick_leave = 0
    record.total_annual_leave = 0
    record.total_compensatory_leave = 0
    record.total_overtime_hours = round(
        sum(value or 0 for value in overtime_values.values()),
        1,
    )
    record.manual_overrides = {}
    record.last_sync_from_dingtalk = sync_time - timedelta(days=2)
    record.updated_at = sync_time

    for field_name, value in day_values.items():
        setattr(record, field_name, value)
    for field_name, value in overtime_values.items():
        setattr(record, field_name, value)

    db.flush()
    return record


def _ensure_manual_changes(
    db: Session,
    *,
    company_id: int,
    admin_user_id: int,
    employees_by_code: Dict[str, Employee],
    snapshot_id: Optional[int],
    change_time: datetime,
) -> int:
    existing_count = (
        db.query(ManualChange)
        .filter(
            ManualChange.company_id == company_id,
            ManualChange.year == DEMO_YEAR,
            ManualChange.month == DEMO_MONTH,
            ManualChange.change_source == "web_ui",
        )
        .count()
    )
    if existing_count:
        return existing_count

    created = 0
    for item in DEMO_MANUAL_CHANGES:
        employee = employees_by_code.get(item["employee_code"])
        if not employee:
            continue
        db.add(
            ManualChange(
                company_id=company_id,
                year=DEMO_YEAR,
                month=DEMO_MONTH,
                employee_id=employee.id,
                snapshot_id=snapshot_id,
                field_name=item["field_name"],
                old_value=item["old_value"],
                new_value=item["new_value"],
                change_source="web_ui",
                change_timestamp=change_time,
                changed_by=admin_user_id,
                merged_to_truth=True,
                merged_at=change_time,
            )
        )
        created += 1

    db.flush()
    logger.info("Created %s demo manual_changes rows", created)
    return created


def _ensure_snapshot_and_version(
    db: Session,
    *,
    company_id: int,
    admin_user_id: int,
    sync_time: datetime,
) -> tuple[Optional[int], Optional[int]]:
    snapshot = (
        db.query(ExcelSnapshot)
        .filter(
            ExcelSnapshot.company_id == company_id,
            ExcelSnapshot.year == DEMO_YEAR,
            ExcelSnapshot.month == DEMO_MONTH,
        )
        .order_by(ExcelSnapshot.snapshot_version.desc())
        .first()
    )
    if snapshot:
        version = (
            db.query(VersionHistory)
            .filter(
                VersionHistory.company_id == company_id,
                VersionHistory.year == DEMO_YEAR,
                VersionHistory.month == DEMO_MONTH,
                VersionHistory.snapshot_id == snapshot.id,
            )
            .first()
        )
        return snapshot.id, version.id if version else None

    snapshot_id = create_snapshot(
        db,
        company_id,
        DEMO_YEAR,
        DEMO_MONTH,
        admin_user_id,
        dingtalk_sync_timestamp=sync_time - timedelta(days=2),
        file_name=f"demo_seed_{DEMO_YEAR}_{DEMO_MONTH:02d}.xlsx",
        record_version_history=False,
        commit=False,
    )

    employee_count = (
        db.query(MonthlyAttendance)
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == DEMO_YEAR,
            MonthlyAttendance.month == DEMO_MONTH,
        )
        .count()
    )

    version = VersionHistory(
        company_id=company_id,
        year=DEMO_YEAR,
        month=DEMO_MONTH,
        version_number=1,
        created_by="hr_upload",
        created_by_user_id=admin_user_id,
        snapshot_id=snapshot_id,
        changes_summary={
            "event": "excel_snapshot",
            "snapshot_version": 1,
            "employee_count": employee_count,
            "file_name": f"demo_seed_{DEMO_YEAR}_{DEMO_MONTH:02d}.xlsx",
            "seed": "demo",
        },
        version_note=f"Demo seed snapshot for {DEMO_YEAR}-{DEMO_MONTH:02d}",
    )
    db.add(version)
    db.flush()
    logger.info("Created demo snapshot id=%s and version_history id=%s", snapshot_id, version.id)
    return snapshot_id, version.id


def seed_demo_data(db: Session, *, force: bool = False) -> Dict[str, Any]:
    """
    Seed or update demo data. Safe to run multiple times.

    When *force* is True, May 2026 attendance rows are rebuilt from demo specs.
    """
    company = _get_or_create_company(db)
    admin = _get_or_create_user(
        db,
        company_id=company.id,
        email=DEMO_ADMIN_EMAIL,
        name="HR Admin",
        role="hr_admin",
        password=DEMO_ADMIN_PASSWORD,
    )
    _get_or_create_user(
        db,
        company_id=company.id,
        email=DEMO_VIEWER_EMAIL,
        name="HR Viewer",
        role="hr_viewer",
        password=DEMO_VIEWER_PASSWORD,
    )

    sync_time = datetime.utcnow()
    employees_by_code: Dict[str, Employee] = {}
    attendance_records: List[MonthlyAttendance] = []

    for index, spec in enumerate(DEMO_EMPLOYEES):
        employee = _get_or_create_employee(db, company.id, spec)
        employees_by_code[spec["employee_code"]] = employee
        attendance_records.append(
            _upsert_attendance(
                db,
                company_id=company.id,
                employee_id=employee.id,
                spec=spec,
                sync_time=sync_time,
                force=force,
                employee_index=index,
            )
        )

    snapshot_id, version_id = _ensure_snapshot_and_version(
        db,
        company_id=company.id,
        admin_user_id=admin.id,
        sync_time=sync_time,
    )
    manual_changes = _ensure_manual_changes(
        db,
        company_id=company.id,
        admin_user_id=admin.id,
        employees_by_code=employees_by_code,
        snapshot_id=snapshot_id,
        change_time=sync_time - timedelta(hours=6),
    )

    db.commit()

    summary = {
        "company": DEMO_COMPANY_NAME,
        "employees": len(attendance_records),
        "year": DEMO_YEAR,
        "month": DEMO_MONTH,
        "snapshot_id": snapshot_id,
        "version_id": version_id,
        "manual_changes": manual_changes,
        "admin_email": DEMO_ADMIN_EMAIL,
        "admin_password": DEMO_ADMIN_PASSWORD,
        "viewer_email": DEMO_VIEWER_EMAIL,
        "viewer_password": DEMO_VIEWER_PASSWORD,
    }
    logger.info("Demo seed complete: %s", summary)
    return summary


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Seed demo attendance data")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild May 2026 attendance rows even if they already exist",
    )
    args = parser.parse_args()

    ensure_auth_schema()
    db = SessionLocal()
    try:
        summary = seed_demo_data(db, force=args.force)
    except Exception:
        db.rollback()
        logger.exception("Demo seed failed")
        return 1
    finally:
        db.close()

    print("Demo data seeded successfully.")
    print(f"  Company:   {summary['company']}")
    print(f"  Period:    {summary['year']}-{summary['month']:02d}")
    print(f"  Employees: {summary['employees']}")
    print(f"  Admin:     {summary['admin_email']} / {summary['admin_password']}")
    print(f"  Viewer:    {summary['viewer_email']} / {summary['viewer_password']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
