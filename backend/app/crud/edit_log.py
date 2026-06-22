"""CRUD helpers for unified edit audit logs."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models import EditLog, User


class CRUDEditLog(CRUDBase[EditLog]):
    def log_change(
        self,
        db: Session,
        *,
        period_id: int,
        company_id: int,
        user: Optional[User],
        entity_type: str,
        entity_id: int,
        field_name: str,
        old_value: Optional[str],
        new_value: Optional[str],
        action: str = "update",
    ) -> EditLog:
        entry = EditLog(
            period_id=period_id,
            company_id=company_id,
            user_id=user.id if user else None,
            user_name=user.name if user else None,
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            action=action,
        )
        db.add(entry)
        db.flush()
        return entry

    def list_for_period(
        self,
        db: Session,
        *,
        period_id: int,
        company_id: int,
        user_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[EditLog]:
        query = db.query(EditLog).filter(
            EditLog.period_id == period_id,
            EditLog.company_id == company_id,
        )
        if user_id is not None:
            query = query.filter(EditLog.user_id == user_id)
        if entity_type:
            query = query.filter(EditLog.entity_type == entity_type)
        if date_from is not None:
            query = query.filter(EditLog.created_at >= date_from)
        if date_to is not None:
            query = query.filter(EditLog.created_at <= date_to)
        return (
            query.order_by(EditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_for_period(
        self,
        db: Session,
        *,
        period_id: int,
        company_id: int,
        user_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> int:
        query = db.query(EditLog).filter(
            EditLog.period_id == period_id,
            EditLog.company_id == company_id,
        )
        if user_id is not None:
            query = query.filter(EditLog.user_id == user_id)
        if entity_type:
            query = query.filter(EditLog.entity_type == entity_type)
        if date_from is not None:
            query = query.filter(EditLog.created_at >= date_from)
        if date_to is not None:
            query = query.filter(EditLog.created_at <= date_to)
        return query.count()


edit_log = CRUDEditLog(EditLog)
