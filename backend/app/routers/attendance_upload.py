"""Attendance upload API routes."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models import User
from app.schemas import (
    AttendancePeriodTableResponse,
    AttendanceUploadResponse,
    DailyAttendancePatchRequest,
    DailyAttendancePatchResponse,
    ValidationIssueResponse,
)
from app.services.attendance_period_table import AttendanceTableError, build_period_table, patch_daily_cell
from app.services.attendance_upload_service import AttendanceUploadError, handle_attendance_upload
from app.services.export import PeriodExportError, generate_period_excel, generate_period_pdf
from app.services.excel_download import stream_file_chunks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/attendance", tags=["attendance-upload"])

HR_ROLES = ["hr_admin", "hr_viewer"]


@router.post("/upload", response_model=AttendanceUploadResponse)
async def upload_attendance_excel(
    file: UploadFile = File(...),
    year: Optional[int] = Form(None),
    month: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """
    Upload a DingTalk-exported monthly summary .xlsx file.

    - Creates or updates an ``attendance_periods`` row in ``draft``/``validated`` status
    - Parses employee names and daily statuses from the 月度汇总 sheet
    - Returns validation issues with severity (Error, Warning, Info)
    - Persists ``employee_attendance`` and ``daily_attendance`` rows when no blocking errors
    """
    if year is not None and (year < 2000 or year > 2100):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Year must be between 2000 and 2100")
    if month is not None and (month < 1 or month > 12):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Month must be between 1 and 12")

    try:
        result = await handle_attendance_upload(
            db,
            current_user,
            file,
            fallback_year=year,
            fallback_month=month,
        )
    except AttendanceUploadError as exc:
        logger.warning(
            "Attendance upload rejected: user_id=%s reason=%s",
            current_user.id,
            exc.message,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return AttendanceUploadResponse(
        success=not result.has_blocking_errors,
        period_id=result.period_id,
        year=result.year,
        month=result.month,
        status=result.status,
        employee_count=result.employee_count,
        daily_record_count=result.daily_record_count,
        requires_review_count=result.requires_review_count,
        persisted=result.persisted,
        has_blocking_errors=result.has_blocking_errors,
        validation_issues=[
            ValidationIssueResponse(**issue) for issue in result.validation_issues
        ],
    )


@router.get("/period/{period_id}/table", response_model=AttendancePeriodTableResponse)
def get_attendance_period_table(
    period_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """Paginated attendance grid for a period (AM/PM rows, day columns, totals)."""
    try:
        payload = build_period_table(
            db,
            period_id=period_id,
            company_id=current_user.company_id,
            page=page,
            page_size=page_size,
        )
    except AttendanceTableError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return AttendancePeriodTableResponse(**payload)


@router.patch("/daily/{daily_id}", response_model=DailyAttendancePatchResponse)
def patch_daily_attendance_cell(
    daily_id: int,
    body: DailyAttendancePatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """Update a single morning/afternoon cell and return recalculated totals."""
    try:
        result = patch_daily_cell(
            db,
            daily_id=daily_id,
            company_id=current_user.company_id,
            shift=body.shift,
            status=body.status,
            user=current_user,
        )
    except AttendanceTableError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return DailyAttendancePatchResponse(**result)


@router.get("/period/{period_id}/export/excel")
def export_period_excel(
    period_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """Download attendance + exception workbook for a period (.xlsx with formulas)."""
    try:
        export_result = generate_period_excel(db, period_id, current_user.company_id)
    except PeriodExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as exc:
        logger.exception(
            "Period Excel export failed: user_id=%s period_id=%s",
            current_user.id,
            period_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate Excel export",
        ) from exc

    background_tasks.add_task(export_result.cleanup)

    logger.info(
        "Period Excel export started: user_id=%s period_id=%s employees=%s exceptions=%s",
        current_user.id,
        period_id,
        export_result.employee_count,
        export_result.exception_count,
    )

    return StreamingResponse(
        stream_file_chunks(export_result.path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{export_result.filename}"',
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
    )


@router.get("/period/{period_id}/export/pdf")
def export_period_pdf(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """Download attendance + exception report for a period (.pdf, landscape)."""
    try:
        export_result = generate_period_pdf(db, period_id, current_user.company_id)
    except PeriodExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as exc:
        logger.exception(
            "Period PDF export failed: user_id=%s period_id=%s",
            current_user.id,
            period_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate PDF export",
        ) from exc

    logger.info(
        "Period PDF export started: user_id=%s period_id=%s employees=%s exceptions=%s",
        current_user.id,
        period_id,
        export_result.employee_count,
        export_result.exception_count,
    )

    return StreamingResponse(
        BytesIO(export_result.content),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{export_result.filename}"',
            "Content-Type": "application/pdf",
        },
    )
