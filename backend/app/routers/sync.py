import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.config import settings
from app.database import get_db
from app.models import Company, User
from app.schemas import (
    EmployeeSyncResponse,
    LeaveSyncResponse,
    MonthSyncRequest,
    OvertimeSyncResponse,
    SyncResultResponse,
    SyncStatusResponse,
)
from app.services.dingtalk_api import DingTalkAPIError, dingtalk_corp_client
from app.services.employee_sync import sync_employees_for_company
from app.services.leave_overtime_sync import sync_leaves_for_company, sync_overtime_for_company
from app.services.sync_counts import get_sync_status
from app.sync_state import sync_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])

ADMIN_ROLES = ["hr_admin"]
HR_ROLES = ["hr_admin", "hr_viewer"]
READ_ROLES = ["hr_admin", "hr_viewer", "manager"]


@router.get("/status", response_model=SyncStatusResponse)
def sync_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(READ_ROLES)),
):
    status_payload = get_sync_status(db, current_user.company_id)
    return SyncStatusResponse(
        **status_payload,
        demo_mode=settings.demo_mode,
    )


@router.post("/employees", response_model=EmployeeSyncResponse)
def sync_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ADMIN_ROLES)),
):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    logger.info("Employee sync requested by user_id=%s company_id=%s", current_user.id, company.id)

    try:
        summary = sync_employees_for_company(
            db,
            company,
            root_dept_id=settings.dingtalk_root_department_id,
        )
    except DingTalkAPIError as exc:
        logger.error("Employee sync failed: %s", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    now = datetime.utcnow()
    sync_state.employees_synced_at = now

    return EmployeeSyncResponse(
        success=True,
        message=summary.message,
        added=summary.added,
        updated=summary.updated,
        deactivated=summary.deactivated,
        total_from_dingtalk=summary.total_from_dingtalk,
        synced_at=now,
    )


@router.post("/leaves", response_model=LeaveSyncResponse)
def sync_leaves(
    payload: MonthSyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    logger.info(
        "Leave sync requested by user_id=%s for %s-%02d",
        current_user.id,
        payload.year,
        payload.month,
    )

    try:
        summary = sync_leaves_for_company(db, company, payload.year, payload.month)
    except DingTalkAPIError as exc:
        logger.error("Leave sync failed: %s", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    now = datetime.utcnow()
    sync_state.leaves_synced_at = now
    return LeaveSyncResponse(
        success=True,
        message=summary.message,
        year=payload.year,
        month=payload.month,
        employees_updated=summary.employees_updated,
        employees=[
            {
                "employee_id": item.employee_id,
                "name": item.name,
                "personal_leave_hours": item.personal_leave_hours,
                "sick_leave_hours": item.sick_leave_hours,
                "annual_leave_hours": item.annual_leave_hours,
                "compensatory_leave_hours": item.compensatory_leave_hours,
            }
            for item in summary.employees
        ],
        synced_at=now,
    )


@router.post("/overtime", response_model=OvertimeSyncResponse)
def sync_overtime(
    payload: MonthSyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    logger.info(
        "Overtime sync requested by user_id=%s for %s-%02d",
        current_user.id,
        payload.year,
        payload.month,
    )

    try:
        summary = sync_overtime_for_company(db, company, payload.year, payload.month)
    except DingTalkAPIError as exc:
        logger.error("Overtime sync failed: %s", exc.message)
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    now = datetime.utcnow()
    sync_state.overtime_synced_at = now
    return OvertimeSyncResponse(
        success=True,
        message=summary.message,
        year=payload.year,
        month=payload.month,
        employees_updated=summary.employees_updated,
        employees=[
            {
                "employee_id": item.employee_id,
                "name": item.name,
                "overtime_hours": item.overtime_hours,
            }
            for item in summary.employees
        ],
        synced_at=now,
    )


@router.post("/all", response_model=SyncResultResponse)
def sync_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    from app.models import MonthlyAttendance

    logger.info("Full sync requested by user_id=%s", current_user.id)
    employee_message = "Employee sync skipped"
    leave_message = "Leave sync skipped"
    overtime_message = "Overtime sync skipped"
    records_updated = 0

    company = db.query(Company).filter(Company.id == current_user.company_id).first()

    if current_user.role == "hr_admin" and dingtalk_corp_client.is_configured() and company:
        try:
            summary = sync_employees_for_company(
                db,
                company,
                root_dept_id=settings.dingtalk_root_department_id,
            )
            employee_message = summary.message
            sync_state.employees_synced_at = datetime.utcnow()
        except DingTalkAPIError as exc:
            employee_message = f"Employee sync failed: {exc.message}"

    if dingtalk_corp_client.is_configured() and company:
        now = datetime.utcnow()
        default_year = now.year
        default_month = now.month
        try:
            leave_summary = sync_leaves_for_company(db, company, default_year, default_month)
            leave_message = leave_summary.message
            sync_state.leaves_synced_at = now
        except DingTalkAPIError as exc:
            leave_message = f"Leave sync failed: {exc.message}"

        try:
            overtime_summary = sync_overtime_for_company(db, company, default_year, default_month)
            overtime_message = overtime_summary.message
            sync_state.overtime_synced_at = now
        except DingTalkAPIError as exc:
            overtime_message = f"Overtime sync failed: {exc.message}"

    now = datetime.utcnow()
    records = (
        db.query(MonthlyAttendance)
        .filter(MonthlyAttendance.company_id == current_user.company_id)
        .all()
    )
    for record in records:
        record.last_sync_from_dingtalk = now
        record.updated_at = now
        records_updated += 1
    db.commit()

    sync_state.attendance_synced_at = now

    return SyncResultResponse(
        success=True,
        message=(
            f"Sync completed. {employee_message}. {leave_message}. {overtime_message}. "
            f"Attendance records touched: {records_updated}."
        ),
        records_updated=records_updated,
        synced_at=now,
    )
