"""CRUD helpers for abnormal attendance records."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.crud.base import CRUDBase
from app.models import AbnormalRecord, AbnormalRecordEditLog


class CRUDAbnormalRecord(CRUDBase[AbnormalRecord]):
    def list_for_period(
        self,
        db: Session,
        *,
        period_id: int,
        company_id: int,
        employee_name: Optional[str] = None,
        exception_type: Optional[str] = None,
        supplement_status: Optional[str] = None,
    ) -> List[AbnormalRecord]:
        query = (
            db.query(AbnormalRecord)
            .options(joinedload(AbnormalRecord.edit_logs))
            .filter(
                AbnormalRecord.period_id == period_id,
                AbnormalRecord.company_id == company_id,
            )
            .order_by(AbnormalRecord.employee_name, AbnormalRecord.exception_type)
        )
        if employee_name:
            query = query.filter(AbnormalRecord.employee_name.ilike(f"%{employee_name}%"))
        if exception_type:
            query = query.filter(AbnormalRecord.exception_type == exception_type)
        if supplement_status:
            query = query.filter(AbnormalRecord.supplement_status == supplement_status)
        return query.all()

    def get_for_company(self, db: Session, record_id: int, company_id: int) -> Optional[AbnormalRecord]:
        return (
            db.query(AbnormalRecord)
            .options(joinedload(AbnormalRecord.edit_logs))
            .filter(AbnormalRecord.id == record_id, AbnormalRecord.company_id == company_id)
            .first()
        )


class CRUDAbnormalRecordEditLog(CRUDBase[AbnormalRecordEditLog]):
    def log_change(
        self,
        db: Session,
        *,
        abnormal_record_id: int,
        edited_by: Optional[int],
        editor_name: Optional[str],
        field_name: str,
        old_value: Optional[str],
        new_value: Optional[str],
    ) -> AbnormalRecordEditLog:
        entry = AbnormalRecordEditLog(
            abnormal_record_id=abnormal_record_id,
            edited_by=edited_by,
            editor_name=editor_name,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
        )
        db.add(entry)
        db.flush()
        return entry


abnormal_record = CRUDAbnormalRecord(AbnormalRecord)
abnormal_record_edit_log = CRUDAbnormalRecordEditLog(AbnormalRecordEditLog)
