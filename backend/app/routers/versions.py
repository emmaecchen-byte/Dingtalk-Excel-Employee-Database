import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models import User
from app.schemas import (
    VersionCompareRequest,
    VersionCompareResponse,
    VersionDetailResponse,
    VersionListResponse,
    VersionRestoreRequest,
    VersionRestoreResponse,
    VersionRollbackRequest,
    VersionRollbackResponse,
)
from app.services.version_service import (
    VersionServiceError,
    compare_versions,
    get_version_detail,
    list_versions,
    preview_rollback,
    restore_version,
    rollback_to_version,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/versions", tags=["versions"])

HR_ROLES = ["hr_admin", "hr_viewer"]


def _raise_version_error(exc: VersionServiceError) -> None:
    detail = {"message": exc.message, **exc.details}
    raise HTTPException(status_code=exc.status_code, detail=detail) from exc


@router.post("/compare", response_model=VersionCompareResponse)
def compare_version_snapshots(
    payload: VersionCompareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    try:
        result = compare_versions(
            db,
            current_user.company_id,
            version_id_1=payload.version_id_1,
            version_id_2=payload.version_id_2,
            snapshot_id_1=payload.snapshot_id_1,
            snapshot_id_2=payload.snapshot_id_2,
        )
    except VersionServiceError as exc:
        _raise_version_error(exc)

    return VersionCompareResponse(**result)


@router.post("/restore", response_model=VersionRestoreResponse)
def restore_version_body(
    payload: VersionRestoreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    try:
        result = restore_version(
            db,
            current_user.company_id,
            current_user,
            version_id=payload.version_id,
            snapshot_id=payload.snapshot_id,
        )
    except VersionServiceError as exc:
        _raise_version_error(exc)

    return VersionRestoreResponse(**result)


@router.get("/{version_id}/rollback-preview")
def get_rollback_preview(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    try:
        return preview_rollback(db, current_user.company_id, version_id)
    except VersionServiceError as exc:
        _raise_version_error(exc)


@router.post("/{version_id}/rollback", response_model=VersionRollbackResponse)
def rollback_version(
    version_id: int,
    payload: VersionRollbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    try:
        result = rollback_to_version(
            db,
            current_user.company_id,
            current_user,
            version_id,
            confirm_data_loss=payload.confirm_data_loss,
        )
    except VersionServiceError as exc:
        _raise_version_error(exc)

    return VersionRollbackResponse(**result)


@router.post("/{version_id}/restore", response_model=VersionRestoreResponse)
def restore_version_by_id(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    try:
        result = restore_version(
            db,
            current_user.company_id,
            current_user,
            version_id=version_id,
        )
    except VersionServiceError as exc:
        _raise_version_error(exc)

    return VersionRestoreResponse(**result)


@router.get("/{version_id}", response_model=VersionDetailResponse)
def get_version(
    version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    try:
        return VersionDetailResponse(**get_version_detail(db, current_user.company_id, version_id))
    except VersionServiceError as exc:
        _raise_version_error(exc)


@router.get("/{year}/{month}", response_model=VersionListResponse)
def get_version_history(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    if month < 1 or month > 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Month must be between 1 and 12")

    versions = list_versions(db, current_user.company_id, year, month)
    return VersionListResponse(year=year, month=month, total=len(versions), versions=versions)
