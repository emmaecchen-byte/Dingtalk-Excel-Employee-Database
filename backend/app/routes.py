from datetime import datetime
import io
import logging
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import require_roles
from app.config import settings
from app.database import get_db
from app.excel.attendance_export import AttendanceExcelError
from app.models import MonthlyAttendance, User
from app.pdf.attendance_pdf import AttendancePdfError, generate_attendance_pdf
from app.services.excel_download import prepare_excel_download
from app.services.excel_upload import ExcelUploadError, handle_excel_upload
from app.services.month_clone import CloneCopyOptions, MonthCloneError, clone_month
from app.services.snapshot_service import SnapshotServiceError
from app.services.sync_counts import count_pending_conflicts, count_pending_updates
from app.schemas import (
    AttendancePatchRequest,
    AttendancePatchResponse,
    AttendanceSummaryResponse,
    EmployeeSummary,
    ExcelFieldChange,
    ExcelUploadConflictPreview,
    ExcelUploadResponse,
    MonthCloneRequest,
    MonthCloneResponse,
    MonthlyAttendanceResponse,
    MonthlyStats,
)
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
        result = generate_attendance_pdf(
            db,
            company_id=current_user.company_id,
            year=year,
            month=month,
            generated_by=current_user.name,
        )
    except AttendancePdfError as exc:
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


@router.get("/excel/download/{year}/{month}")
def download_excel(
    year: int,
    month: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """
    Download a populated attendance workbook for the given month.

    - Requires ``hr_admin`` or ``hr_viewer`` role
    - Loads ``backend/templates/master_template.xlsx`` via openpyxl
    - Populates 签字 / 情况说明 / 月度汇总 sheets from ``monthly_attendance``
    - Creates a versioned ``excel_snapshots`` row before streaming the file
    """
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
        download_result = prepare_excel_download(db, current_user, year, month)
    except AttendanceExcelError as exc:
        logger.warning(
            "Excel download failed: user_id=%s company_id=%s period=%s-%02d reason=%s",
            current_user.id,
            current_user.company_id,
            year,
            month,
            exc.message,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
    except SnapshotServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as exc:
        logger.exception(
            "Excel download error: user_id=%s company_id=%s period=%s-%02d",
            current_user.id,
            current_user.company_id,
            year,
            month,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate Excel download",
        ) from exc

    background_tasks.add_task(download_result.cleanup)

    snapshot = download_result.snapshot
    snapshot_id = snapshot.id if snapshot else download_result.snapshot_id
    snapshot_version = snapshot.snapshot_version if snapshot else ""

    logger.info(
        "Excel download started: user_id=%s email=%s snapshot_id=%s version=v%s file=%s",
        current_user.id,
        current_user.email,
        snapshot_id,
        snapshot_version,
        download_result.filename,
    )

    return StreamingResponse(
        download_result.iter_content(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{download_result.filename}"',
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "X-Snapshot-Id": str(snapshot_id),
            "X-Snapshot-Version": str(snapshot_version),
        },
    )


@router.post("/excel/clone", response_model=MonthCloneResponse)
def clone_month_endpoint(
    payload: MonthCloneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    try:
        result = clone_month(
            db,
            company_id=current_user.company_id,
            user=current_user,
            source_year=payload.source_year,
            source_month=payload.source_month,
            target_year=payload.target_year,
            target_month=payload.target_month,
            copy_options=CloneCopyOptions.from_dict(payload.copy_options.model_dump()),
        )
    except MonthCloneError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except AttendanceExcelError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.message) from exc

    return MonthCloneResponse(**result)


@router.post("/excel/upload", response_model=ExcelUploadResponse)
async def upload_excel(
    year: int = Form(...),
    month: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """
    Upload an edited attendance workbook and detect changes vs the latest snapshot.

    - Accepts multipart/form-data: ``year``, ``month``, ``file``
    - Requires ``hr_admin`` or ``hr_viewer`` role
    - Parses Sheet 3 ``月度汇总`` for daily status and scalar fields
    - Diffs against the most recent ``excel_snapshots`` row for the period
    - Records each change in ``manual_changes`` with ``change_source='excel_upload'``
    """
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
        result = await handle_excel_upload(db, current_user, year, month, file)
    except ExcelUploadError as exc:
        logger.warning(
            "Excel upload failed: user_id=%s company_id=%s period=%s-%02d reason=%s",
            current_user.id,
            current_user.company_id,
            year,
            month,
            exc.message,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as exc:
        logger.exception(
            "Excel upload error: user_id=%s company_id=%s period=%s-%02d",
            current_user.id,
            current_user.company_id,
            year,
            month,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process Excel upload",
        ) from exc

    preview_changes = [
        ExcelFieldChange(
            employee_id=change.employee_id,
            employee_name=change.employee_name,
            field_name=change.field_name,
            old_value=change.old_value,
            new_value=change.new_value,
            conflict=change.conflict,
            conflict_id=change.conflict_id,
        )
        for change in result.changes[:10]
    ]
    all_changes = [
        ExcelFieldChange(
            employee_id=change.employee_id,
            employee_name=change.employee_name,
            field_name=change.field_name,
            old_value=change.old_value,
            new_value=change.new_value,
            conflict=change.conflict,
            conflict_id=change.conflict_id,
        )
        for change in result.changes
    ]

    return ExcelUploadResponse(
        success=True,
        year=result.year,
        month=result.month,
        snapshot_id=result.snapshot_id,
        total_changes=result.changes_detected,
        employees_affected=result.employees_modified,
        changes_list=preview_changes,
        changes_detected=result.changes_detected,
        employees_modified=result.employees_modified,
        conflicts_created=result.conflicts_created,
        auto_merged=result.auto_merged,
        has_conflicts=result.has_conflicts,
        conflicts_list=[
            ExcelUploadConflictPreview(**item) for item in result.conflicts_list
        ],
        pending_conflicts_count=result.pending_conflicts_count,
        changes=all_changes,
    )
