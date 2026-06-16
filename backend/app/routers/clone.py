"""
Clone monthly attendance from a source period to a new target month.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.excel.attendance_export import AttendanceExcelError
from app.models import User
from app.schemas import MonthCloneRequest, MonthCloneResponse
from app.services.month_clone import CloneCopyOptions, MonthCloneError, clone_month

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/excel", tags=["excel"])

ADMIN_ROLES = ["hr_admin"]


@router.post("/clone", response_model=MonthCloneResponse)
def clone_month_endpoint(
    payload: MonthCloneRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(ADMIN_ROLES)),
):
    """
    Clone a source month into a new target month.

    Creates ``monthly_attendance`` rows, a versioned ``excel_snapshots`` row,
    and a ``version_history`` entry for the target period.
    """
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.message,
        ) from exc

    logger.info(
        "Month clone API: user_id=%s %s-%02d -> %s-%02d employees=%s",
        current_user.id,
        payload.source_year,
        payload.source_month,
        payload.target_year,
        payload.target_month,
        result["employees_copied"],
    )
    return MonthCloneResponse(**result)
