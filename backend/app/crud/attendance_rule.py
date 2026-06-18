"""CRUD helpers for configurable attendance rules."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.models import AttendanceRule


class CRUDAttendanceRule(CRUDBase[AttendanceRule]):
    def list_for_company(self, db: Session, company_id: int) -> List[AttendanceRule]:
        return (
            db.query(AttendanceRule)
            .filter(AttendanceRule.company_id == company_id)
            .order_by(AttendanceRule.priority.desc(), AttendanceRule.id.asc())
            .all()
        )

    def get_for_company(self, db: Session, rule_id: int, company_id: int) -> Optional[AttendanceRule]:
        return (
            db.query(AttendanceRule)
            .filter(AttendanceRule.id == rule_id, AttendanceRule.company_id == company_id)
            .first()
        )

    def get_by_keyword(self, db: Session, company_id: int, raw_keyword: str) -> Optional[AttendanceRule]:
        return (
            db.query(AttendanceRule)
            .filter(
                AttendanceRule.company_id == company_id,
                AttendanceRule.raw_keyword == raw_keyword,
            )
            .first()
        )


attendance_rule = CRUDAttendanceRule(AttendanceRule)
