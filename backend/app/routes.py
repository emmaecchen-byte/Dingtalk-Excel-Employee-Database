from datetime import datetime
import io
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import require_roles
from app.config import settings
from app.database import get_db
from app.models import MonthlyAttendance, User
from app.services.pdf_generator import AttendancePdfError, generate_attendance_pdf
from app.services.pdf_export import PeriodExportError, generate_period_pdf_for_month
from app.services.sync_counts import count_pending_conflicts, count_pending_updates
from app.schemas import (
    AttendancePatchRequest,
    AttendancePatchResponse,
    AttendanceSheetsResponse,
    AttendanceSummaryResponse,
    EmployeeSummary,
    MonthlyAttendanceResponse,
    MonthlyStats,
)
from app.services.attendance_sheets import build_attendance_sheets
from app.services.attendance_update import AttendanceUpdateError, patch_employee_attendance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["attendance"])

HR_ROLES = ["hr_admin", "hr_viewer"]
READ_ROLES = ["hr_admin", "hr_viewer", "manager"]


def _employee_status(record: MonthlyAttendance) -> str:
    if record.absenteeism_count or record.lateness_count or record.missing_punch_count:
        return "warning"
    return "ok"


@router.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "demo_mode": settings.demo_mode,
        "dingtalk_oauth_enabled": settings.dingtalk_enabled,
        "dingtalk_api_configured": bool(
            settings.dingtalk_client_id and settings.dingtalk_client_secret
        ),
    }


def _employee_summary(record: MonthlyAttendance) -> EmployeeSummary:
    return EmployeeSummary(
        id=record.employee.id,
        name=record.employee.name,
        department=record.employee.department,
        position=record.employee.position,
        total_attendance_days=record.total_attendance_days,
        absenteeism_count=record.absenteeism_count,
        lateness_count=record.lateness_count,
        missing_punch_count=record.missing_punch_count,
        anomaly_summary=record.anomaly_summary,
        supplement_submitted=record.supplement_submitted,
        notes=record.notes,
        status=_employee_status(record),
        manual_override_fields=sorted((record.manual_overrides or {}).keys()),
    )


@router.patch(
    "/attendance/{year}/{month}/{employee_id}",
    response_model=AttendancePatchResponse,
)
def patch_attendance_field(
    year: int,
    month: int,
    employee_id: int,
    payload: AttendancePatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    try:
        result = patch_employee_attendance(
            db,
            company_id=current_user.company_id,
            year=year,
            month=month,
            employee_id=employee_id,
            field_name=payload.field_name,
            new_value=payload.new_value,
            user=current_user,
        )
    except AttendanceUpdateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return AttendancePatchResponse(**result)


def _fetch_monthly_records(
    db: Session,
    company_id: int,
    year: int,
    month: int,
) -> List[MonthlyAttendance]:
    return (
        db.query(MonthlyAttendance)
        .options(joinedload(MonthlyAttendance.employee))
        .filter(
            MonthlyAttendance.company_id == company_id,
            MonthlyAttendance.year == year,
            MonthlyAttendance.month == month,
        )
        .all()
    )


def _build_monthly_stats(
    db: Session,
    company_id: int,
    employees: List[EmployeeSummary],
) -> MonthlyStats:
    return MonthlyStats(
        total_employees=len(employees),
        total_absenteeism_days=sum(employee.absenteeism_count for employee in employees),
        total_lateness_days=sum(employee.lateness_count for employee in employees),
        total_missing_punch_days=sum(employee.missing_punch_count for employee in employees),
        pending_conflicts=count_pending_conflicts(db, company_id),
        pending_updates=count_pending_updates(db, company_id),
    )


def _last_sync_from_records(records: List[MonthlyAttendance]):
    return max(
        (record.last_sync_from_dingtalk for record in records if record.last_sync_from_dingtalk),
        default=None,
    )


@router.get("/attendance/summary/{year}/{month}", response_model=AttendanceSummaryResponse)
def get_attendance_summary(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(READ_ROLES)),
):
    records = _fetch_monthly_records(db, current_user.company_id, year, month)
    if not records:
        raise HTTPException(status_code=404, detail=f"No attendance data for {year}-{month:02d}")

    employees = [_employee_summary(record) for record in records]
    return AttendanceSummaryResponse(
        year=year,
        month=month,
        stats=_build_monthly_stats(db, current_user.company_id, employees),
        last_sync=_last_sync_from_records(records),
    )


@router.get("/attendance/{year}/{month}/sheets", response_model=AttendanceSheetsResponse)
def get_attendance_sheets(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(READ_ROLES)),
):
    try:
        payload = build_attendance_sheets(db, current_user.company_id, year, month)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return AttendanceSheetsResponse(**payload)


@router.get("/attendance/{year}/{month}", response_model=MonthlyAttendanceResponse)
def get_monthly_attendance(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(READ_ROLES)),
):
    records = _fetch_monthly_records(db, current_user.company_id, year, month)
    if not records:
        raise HTTPException(status_code=404, detail=f"No attendance data for {year}-{month:02d}")

    employees = [_employee_summary(record) for record in records]
    return MonthlyAttendanceResponse(
        year=year,
        month=month,
        stats=_build_monthly_stats(db, current_user.company_id, employees),
        employees=employees,
        last_sync=_last_sync_from_records(records),
    )


@router.get("/attendance/export/pdf/{year}/{month}")
def export_attendance_pdf(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    if year < 2000 or year > 2100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Year must be between 2000 and 2100",
        )
    if month < 1 or month > 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Month must be between 1 and 12",
        )

    try:
        try:
            result = generate_period_pdf_for_month(
                db,
                company_id=current_user.company_id,
                year=year,
                month=month,
            )
        except PeriodExportError:
            result = generate_attendance_pdf(
                db,
                company_id=current_user.company_id,
                year=year,
                month=month,
                generated_by=current_user.name,
            )
    except (PeriodExportError, AttendancePdfError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
    except Exception as exc:
        logger.exception(
            "PDF export failed: user_id=%s company_id=%s period=%s-%02d",
            current_user.id,
            current_user.company_id,
            year,
            month,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate PDF report",
        ) from exc

    logger.info(
        "PDF export started: user_id=%s period=%s-%02d file=%s",
        current_user.id,
        year,
        month,
        result.filename,
    )

    return StreamingResponse(
        io.BytesIO(result.content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )
