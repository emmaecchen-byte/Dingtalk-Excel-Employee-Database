"""
Attendance API routes (upload-and-convert, daily cell edits).
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models import User
from app.schemas import DailyAttendancePatchRequest, DailyAttendancePatchResponse
from app.services.attendance_period_table import AttendanceTableError, patch_daily_cell
from app.services.excel_converter import ExcelConverterError, convert_dingtalk_upload_to_workbook
from app.services.excel_download import stream_file_chunks
from app.services.export import PeriodExportError, generate_period_excel
from app.services.pdf_export import generate_period_pdf
from app.routers import attendance_exceptions as attendance_exceptions_router
from app.routers import attendance_periods as attendance_periods_router
from app.routers import audit_logs as audit_logs_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/attendance", tags=["attendance"])
router.include_router(attendance_exceptions_router.router)
router.include_router(attendance_periods_router.router)
router.include_router(audit_logs_router.router)

HR_ROLES = ["hr_admin", "hr_viewer"]


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


@router.post("/upload-and-convert")
async def upload_and_convert_attendance(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    year: Optional[int] = Form(None),
    month: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    """
    Upload a DingTalk monthly-summary .xlsx and download the full 4-sheet workbook.

    - Parses 月度汇总 (employee names + daily statuses)
    - Maps status text to symbols via company attendance rules
    - Detects anomalies for 情况说明 (旷工 / 迟到 / 缺卡)
    - Generates 签字 / 情况说明 / 月度汇总 / 加班结算加班工资
    """
    if year is not None and (year < 2000 or year > 2100):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Year must be between 2000 and 2100",
        )
    if month is not None and (month < 1 or month > 12):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Month must be between 1 and 12",
        )

    try:
        export_result = await convert_dingtalk_upload_to_workbook(
            db,
            current_user,
            file,
            year=year,
            month=month,
        )
    except ExcelConverterError as exc:
        logger.warning(
            "Upload-and-convert failed: user_id=%s company_id=%s reason=%s",
            current_user.id,
            current_user.company_id,
            exc.message,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as exc:
        logger.exception(
            "Upload-and-convert error: user_id=%s company_id=%s",
            current_user.id,
            current_user.company_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to convert uploaded attendance file",
        ) from exc

    background_tasks.add_task(export_result.cleanup)

    logger.info(
        "Upload-and-convert download started: user_id=%s period=%s-%02d employees=%s file=%s",
        current_user.id,
        export_result.year,
        export_result.month,
        export_result.employee_count,
        export_result.filename,
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
    """Download attendance grid + exception report for a period (.pdf, landscape)."""
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
