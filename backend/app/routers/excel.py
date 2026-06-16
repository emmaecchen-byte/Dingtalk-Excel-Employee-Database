"""
Excel download and upload routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models import User
from app.schemas import ExcelFieldChange, ExcelUploadConflictPreview, ExcelUploadResponse
from app.services.excel_download import prepare_excel_download
from app.services.excel_generator import ExcelGeneratorError
from app.services.excel_upload import ExcelUploadError, handle_excel_upload
from app.services.snapshot_service import SnapshotServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/excel", tags=["excel"])

HR_ROLES = ["hr_admin", "hr_viewer"]


@router.get("/download/{year}/{month}")
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
    - Creates a versioned ``excel_snapshots`` row before streaming the file
    - Loads ``backend/templates/master_template.xlsx`` and populates sheets from DB
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
    except ExcelGeneratorError as exc:
        logger.warning(
            "Excel download failed: user_id=%s company_id=%s period=%s-%02d reason=%s",
            current_user.id,
            current_user.company_id,
            year,
            month,
            exc.message,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
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


@router.post("/upload", response_model=ExcelUploadResponse)
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
    - Parses Sheet 3 ``月度汇总`` for daily status (day_1 … day_31)
    - Compares against the most recent ``excel_snapshots`` row for the period
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
