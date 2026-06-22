"""Exception list, detection, and edit APIs."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.crud.abnormal_record import abnormal_record
from app.database import get_db
from app.models import AbnormalRecord, User
from app.services.audit_log import (
    log_abnormal_record_change,
    log_abnormal_record_created,
    log_abnormal_record_deleted,
)
from app.schemas import (
    AbnormalRecordCreateRequest,
    AbnormalRecordEditLogResponse,
    AbnormalRecordListResponse,
    AbnormalRecordResponse,
    AbnormalRecordUpdateRequest,
    ExceptionDetectionResponse,
)
from app.services.exception_detection import ExceptionDetectionError, detect_exceptions_for_period
from app.services.period_workflow import PeriodWorkflowError, assert_period_editable, get_period_for_company_or_raise

logger = logging.getLogger(__name__)

router = APIRouter(tags=["attendance-exceptions"])

HR_ROLES = ["hr_admin", "hr_viewer"]


def _require_mutable_period(db: Session, period_id: int, company_id: int) -> None:
    period = get_period_for_company_or_raise(db, period_id, company_id)
    assert_period_editable(period)


def _serialize_record(record: AbnormalRecord) -> AbnormalRecordResponse:
    return AbnormalRecordResponse(
        id=record.id,
        period_id=record.period_id,
        employee_attendance_id=record.employee_attendance_id,
        employee_id=record.employee_id,
        employee_name=record.employee_name,
        exception_type=record.exception_type,
        summary=record.summary,
        dates=record.dates or [],
        supplement_status=record.supplement_status,
        notes=record.notes,
        created_at=record.created_at,
        updated_at=record.updated_at,
        edit_logs=[
            AbnormalRecordEditLogResponse(
                id=log.id,
                field_name=log.field_name,
                old_value=log.old_value,
                new_value=log.new_value,
                editor_name=log.editor_name,
                edited_at=log.edited_at,
            )
            for log in sorted(record.edit_logs or [], key=lambda item: item.edited_at, reverse=True)
        ],
    )


@router.post("/period/{period_id}/detect-exceptions", response_model=ExceptionDetectionResponse)
def run_exception_detection(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    try:
        _require_mutable_period(db, period_id, current_user.company_id)
        result = detect_exceptions_for_period(db, period_id, current_user.company_id)
        db.commit()
    except PeriodWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ExceptionDetectionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return ExceptionDetectionResponse(**result)


@router.get("/period/{period_id}/exceptions", response_model=AbnormalRecordListResponse)
def list_period_exceptions(
    period_id: int,
    employee_name: Optional[str] = Query(None),
    exception_type: Optional[str] = Query(None),
    supplement_status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    records = abnormal_record.list_for_period(
        db,
        period_id=period_id,
        company_id=current_user.company_id,
        employee_name=employee_name,
        exception_type=exception_type,
        supplement_status=supplement_status,
    )
    return AbnormalRecordListResponse(
        period_id=period_id,
        total=len(records),
        records=[_serialize_record(record) for record in records],
    )


@router.post("/period/{period_id}/exceptions", response_model=AbnormalRecordResponse, status_code=status.HTTP_201_CREATED)
def create_exception_record(
    period_id: int,
    body: AbnormalRecordCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    try:
        _require_mutable_period(db, period_id, current_user.company_id)
    except PeriodWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    record = AbnormalRecord(
        company_id=current_user.company_id,
        period_id=period_id,
        employee_attendance_id=body.employee_attendance_id,
        employee_id=body.employee_id,
        employee_name=body.employee_name,
        exception_type=body.exception_type,
        summary=body.summary,
        dates=body.dates,
        supplement_status=body.supplement_status,
        notes=body.notes,
    )
    db.add(record)
    db.flush()
    log_abnormal_record_created(
        db,
        period_id=period_id,
        company_id=current_user.company_id,
        abnormal_record_id=record.id,
        user=current_user,
        summary=record.summary or record.employee_name,
    )
    db.commit()
    db.refresh(record)
    return _serialize_record(record)


@router.patch("/exception/{record_id}", response_model=AbnormalRecordResponse)
def update_exception_record(
    record_id: int,
    body: AbnormalRecordUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    record = abnormal_record.get_for_company(db, record_id, current_user.company_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception record not found")

    try:
        _require_mutable_period(db, record.period_id, current_user.company_id)
    except PeriodWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    changes = body.model_dump(exclude_unset=True)
    for field_name, new_value in changes.items():
        old_value = getattr(record, field_name)
        old_text = str(old_value) if old_value is not None else None
        new_text = str(new_value) if new_value is not None else None
        if old_text == new_text:
            continue
        setattr(record, field_name, new_value)
        log_abnormal_record_change(
            db,
            period_id=record.period_id,
            company_id=current_user.company_id,
            abnormal_record_id=record.id,
            user=current_user,
            field_name=field_name,
            old_value=old_text,
            new_value=new_text,
        )

    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return _serialize_record(record)


@router.delete("/exception/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exception_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ROLES)),
):
    record = abnormal_record.get_for_company(db, record_id, current_user.company_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception record not found")
    try:
        _require_mutable_period(db, record.period_id, current_user.company_id)
    except PeriodWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    summary = record.summary or record.employee_name
    period_id = record.period_id
    company_id = current_user.company_id
    record_id = record.id
    log_abnormal_record_deleted(
        db,
        period_id=period_id,
        company_id=company_id,
        abnormal_record_id=record_id,
        user=current_user,
        summary=summary,
    )
    db.delete(record)
    db.commit()
    return None
