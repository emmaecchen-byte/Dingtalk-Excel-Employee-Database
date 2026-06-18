"""API routes for attendance rule configuration."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.crud.attendance_rule import attendance_rule
from app.database import get_db
from app.models import AttendanceRule, User
from app.schemas import (
    AttendanceRuleCreateRequest,
    AttendanceRuleListResponse,
    AttendanceRuleResponse,
    AttendanceRuleUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config-rules"])

HR_ADMIN_ROLES = ["hr_admin"]


def _serialize_rule(rule: AttendanceRule) -> AttendanceRuleResponse:
    return AttendanceRuleResponse(
        id=rule.id,
        company_id=rule.company_id,
        raw_keyword=rule.raw_keyword,
        normalized_status=rule.normalized_status,
        symbol=rule.symbol,
        counts_as_attendance=rule.counts_as_attendance,
        counts_as_meal_allowance=rule.counts_as_meal_allowance,
        leave_type=rule.leave_type,
        is_abnormal=rule.is_abnormal,
        priority=rule.priority,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("/rules", response_model=AttendanceRuleListResponse)
def list_attendance_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ADMIN_ROLES)),
):
    from app.services.attendance_rule_engine import ensure_default_rules

    ensure_default_rules(db, current_user.company_id)
    rules = attendance_rule.list_for_company(db, current_user.company_id)
    return AttendanceRuleListResponse(
        total=len(rules),
        rules=[_serialize_rule(rule) for rule in rules],
    )


@router.post("/rules", response_model=AttendanceRuleResponse, status_code=status.HTTP_201_CREATED)
def create_attendance_rule(
    body: AttendanceRuleCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ADMIN_ROLES)),
):
    existing = attendance_rule.get_by_keyword(db, current_user.company_id, body.raw_keyword.strip())
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rule with keyword '{body.raw_keyword}' already exists",
        )

    rule = AttendanceRule(
        company_id=current_user.company_id,
        raw_keyword=body.raw_keyword.strip(),
        normalized_status=body.normalized_status.strip(),
        symbol=body.symbol,
        counts_as_attendance=body.counts_as_attendance,
        counts_as_meal_allowance=body.counts_as_meal_allowance,
        leave_type=body.leave_type,
        is_abnormal=body.is_abnormal,
        priority=body.priority,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    logger.info("Attendance rule created: id=%s company_id=%s keyword=%s", rule.id, rule.company_id, rule.raw_keyword)
    return _serialize_rule(rule)


@router.put("/rules/{rule_id}", response_model=AttendanceRuleResponse)
def update_attendance_rule(
    rule_id: int,
    body: AttendanceRuleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ADMIN_ROLES)),
):
    rule = attendance_rule.get_for_company(db, rule_id, current_user.company_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    changes = body.model_dump(exclude_unset=True)
    if "raw_keyword" in changes:
        keyword = changes["raw_keyword"].strip()
        conflict = attendance_rule.get_by_keyword(db, current_user.company_id, keyword)
        if conflict and conflict.id != rule.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rule with keyword '{keyword}' already exists",
            )
        changes["raw_keyword"] = keyword
    if "normalized_status" in changes:
        changes["normalized_status"] = changes["normalized_status"].strip()

    for field_name, value in changes.items():
        setattr(rule, field_name, value)
    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)
    return _serialize_rule(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attendance_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(HR_ADMIN_ROLES)),
):
    rule = attendance_rule.get_for_company(db, rule_id, current_user.company_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    db.delete(rule)
    db.commit()
    logger.info("Attendance rule deleted: id=%s company_id=%s", rule_id, current_user.company_id)
    return None
