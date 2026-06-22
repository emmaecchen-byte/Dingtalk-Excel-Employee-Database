"""
Configurable attendance status rule engine (spec sections 7.5, 11.5).

Rules are loaded per company from the database. When no rules exist, defaults are seeded.
Higher ``priority`` wins when multiple keywords match the same raw text.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Lock
from typing import Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.crud.attendance_rule import attendance_rule
from app.models import AttendanceRule

logger = logging.getLogger(__name__)

RULE_CACHE_TTL_SECONDS = 60

LEGACY_SYMBOLS = frozenset({"√", "◇", "✬", "▼", "※", "●", "AL", "○", "FL", "ML", "旷工", "迟到", "缺卡"})

_rule_cache: dict[int, tuple[float, List["ResolvedAttendanceRule"]]] = {}
_cache_lock = Lock()

DEFAULT_RULE_DEFINITIONS: List[dict] = [
    {
        "raw_keyword": "正常",
        "normalized_status": "正常",
        "symbol": "√",
        "counts_as_attendance": True,
        "counts_as_meal_allowance": True,
        "leave_type": "present",
        "is_abnormal": False,
        "priority": 100,
    },
    {
        "raw_keyword": "√",
        "normalized_status": "正常",
        "symbol": "√",
        "counts_as_attendance": True,
        "counts_as_meal_allowance": True,
        "leave_type": "present",
        "is_abnormal": False,
        "priority": 100,
    },
    {
        "raw_keyword": "出勤",
        "normalized_status": "正常",
        "symbol": "√",
        "counts_as_attendance": True,
        "counts_as_meal_allowance": True,
        "leave_type": "present",
        "is_abnormal": False,
        "priority": 95,
    },
    {
        "raw_keyword": "旷工",
        "normalized_status": "旷工",
        "symbol": "旷工",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": None,
        "is_abnormal": True,
        "priority": 90,
    },
    {
        "raw_keyword": "迟到",
        "normalized_status": "迟到",
        "symbol": "迟到",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": None,
        "is_abnormal": True,
        "priority": 85,
    },
    {
        "raw_keyword": "上班迟到",
        "normalized_status": "迟到",
        "symbol": "迟到",
        "counts_as_attendance": True,
        "counts_as_meal_allowance": False,
        "leave_type": None,
        "is_abnormal": True,
        "priority": 87,
    },
    {
        "raw_keyword": "严重迟到",
        "normalized_status": "迟到",
        "symbol": "迟到",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": None,
        "is_abnormal": True,
        "priority": 86,
    },
    {
        "raw_keyword": "缺卡",
        "normalized_status": "缺卡",
        "symbol": "缺卡",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": None,
        "is_abnormal": True,
        "priority": 84,
    },
    {
        "raw_keyword": "上班缺卡",
        "normalized_status": "缺卡",
        "symbol": "缺卡",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": None,
        "is_abnormal": True,
        "priority": 85,
    },
    {
        "raw_keyword": "早退",
        "normalized_status": "早退",
        "symbol": "早退",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": None,
        "is_abnormal": True,
        "priority": 82,
    },
    {
        "raw_keyword": "上班早退",
        "normalized_status": "早退",
        "symbol": "早退",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": None,
        "is_abnormal": True,
        "priority": 83,
    },
    {
        "raw_keyword": "未打卡",
        "normalized_status": "缺卡",
        "symbol": "缺卡",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": None,
        "is_abnormal": True,
        "priority": 83,
    },
    {
        "raw_keyword": "出差",
        "normalized_status": "出差",
        "symbol": "▼",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": True,
        "leave_type": "business_trip",
        "is_abnormal": False,
        "priority": 80,
    },
    {
        "raw_keyword": "事假",
        "normalized_status": "事假",
        "symbol": "◇",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": "personal_leave",
        "is_abnormal": False,
        "priority": 75,
    },
    {
        "raw_keyword": "调休",
        "normalized_status": "调休",
        "symbol": "✬",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": "compensatory_leave",
        "is_abnormal": False,
        "priority": 74,
    },
    {
        "raw_keyword": "病假",
        "normalized_status": "病假",
        "symbol": "※",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": "sick_leave",
        "is_abnormal": False,
        "priority": 73,
    },
    {
        "raw_keyword": "年假",
        "normalized_status": "年假",
        "symbol": "AL",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": "annual_leave",
        "is_abnormal": False,
        "priority": 72,
    },
    {
        "raw_keyword": "产假",
        "normalized_status": "产假",
        "symbol": "○",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": "maternity_leave",
        "is_abnormal": False,
        "priority": 71,
    },
    {
        "raw_keyword": "陪产假",
        "normalized_status": "产假",
        "symbol": "○",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": "maternity_leave",
        "is_abnormal": False,
        "priority": 70,
    },
    {
        "raw_keyword": "丧假",
        "normalized_status": "丧假",
        "symbol": "FL",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": "funeral_leave",
        "is_abnormal": False,
        "priority": 69,
    },
    {
        "raw_keyword": "婚假",
        "normalized_status": "婚假",
        "symbol": "ML",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": "marriage_leave",
        "is_abnormal": False,
        "priority": 68,
    },
    {
        "raw_keyword": "福利假",
        "normalized_status": "福利假",
        "symbol": "●",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": "welfare_leave",
        "is_abnormal": False,
        "priority": 67,
    },
    {
        "raw_keyword": "生日假",
        "normalized_status": "福利假",
        "symbol": "●",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": "welfare_leave",
        "is_abnormal": False,
        "priority": 66,
    },
    {
        "raw_keyword": "休息",
        "normalized_status": "休息",
        "symbol": "",
        "counts_as_attendance": False,
        "counts_as_meal_allowance": False,
        "leave_type": None,
        "is_abnormal": False,
        "priority": 10,
    },
]


@dataclass(frozen=True)
class ResolvedAttendanceRule:
    raw_keyword: str
    normalized_status: str
    symbol: str
    counts_as_attendance: bool
    counts_as_meal_allowance: bool
    leave_type: Optional[str]
    is_abnormal: bool
    priority: int

    @classmethod
    def from_model(cls, rule: AttendanceRule) -> "ResolvedAttendanceRule":
        return cls(
            raw_keyword=rule.raw_keyword,
            normalized_status=rule.normalized_status,
            symbol=rule.symbol,
            counts_as_attendance=rule.counts_as_attendance,
            counts_as_meal_allowance=rule.counts_as_meal_allowance,
            leave_type=rule.leave_type,
            is_abnormal=rule.is_abnormal,
            priority=rule.priority,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "ResolvedAttendanceRule":
        return cls(
            raw_keyword=data["raw_keyword"],
            normalized_status=data["normalized_status"],
            symbol=data.get("symbol", ""),
            counts_as_attendance=bool(data.get("counts_as_attendance", False)),
            counts_as_meal_allowance=bool(data.get("counts_as_meal_allowance", False)),
            leave_type=data.get("leave_type"),
            is_abnormal=bool(data.get("is_abnormal", False)),
            priority=int(data.get("priority", 0)),
        )


def default_rules() -> List[ResolvedAttendanceRule]:
    return [ResolvedAttendanceRule.from_dict(item) for item in DEFAULT_RULE_DEFINITIONS]


def invalidate_company_rules_cache(company_id: int) -> None:
    with _cache_lock:
        _rule_cache.pop(company_id, None)


def invalidate_all_rules_cache() -> None:
    with _cache_lock:
        _rule_cache.clear()


def ensure_default_rules(db: Session, company_id: int) -> List[AttendanceRule]:
    existing = attendance_rule.list_for_company(db, company_id)
    existing_keywords = {rule.raw_keyword for rule in existing}

    created: List[AttendanceRule] = []
    for item in DEFAULT_RULE_DEFINITIONS:
        if item["raw_keyword"] in existing_keywords:
            continue
        rule = AttendanceRule(company_id=company_id, **item)
        db.add(rule)
        created.append(rule)

    if created:
        db.commit()
        for rule in created:
            db.refresh(rule)
        invalidate_company_rules_cache(company_id)
        logger.info("Seeded %s default attendance rules for company_id=%s", len(created), company_id)

    if existing:
        return existing + created
    return created


def load_company_rules(db: Session, company_id: int) -> List[ResolvedAttendanceRule]:
    now = time.monotonic()
    with _cache_lock:
        cached = _rule_cache.get(company_id)
        if cached and now - cached[0] < RULE_CACHE_TTL_SECONDS:
            return list(cached[1])

    ensure_default_rules(db, company_id)
    rows = attendance_rule.list_for_company(db, company_id)
    resolved = [ResolvedAttendanceRule.from_model(rule) for rule in rows]

    with _cache_lock:
        _rule_cache[company_id] = (now, resolved)
    return resolved


def build_anomaly_keywords(rules: Sequence[ResolvedAttendanceRule]) -> dict[str, tuple[str, ...]]:
    """Build keyword tuples for anomaly detection from configured rules."""
    absenteeism: List[str] = []
    lateness: List[str] = []
    missing_punch: List[str] = []
    early_departure: List[str] = []

    for rule in rules:
        if not rule.is_abnormal:
            continue
        if rule.normalized_status == "旷工":
            absenteeism.append(rule.raw_keyword)
        elif rule.normalized_status == "迟到":
            lateness.append(rule.raw_keyword)
        elif rule.normalized_status == "缺卡":
            missing_punch.append(rule.raw_keyword)
        elif rule.normalized_status == "早退":
            early_departure.append(rule.raw_keyword)

    return {
        "absenteeism": tuple(absenteeism or ("旷工",)),
        "lateness": tuple(lateness or ("迟到", "上班迟到")),
        "missing_punch": tuple(missing_punch or ("缺卡", "上班缺卡", "未打卡")),
        "early_departure": tuple(early_departure or ("早退", "上班早退")),
    }


def match_rule(text: str, rules: Sequence[ResolvedAttendanceRule]) -> Optional[ResolvedAttendanceRule]:
    """Return the highest-priority rule matching *text* (exact match preferred)."""
    normalized = (text or "").strip()
    if not normalized:
        return None

    if normalized in LEGACY_SYMBOLS:
        for rule in sorted(rules, key=lambda item: item.priority, reverse=True):
            if rule.symbol == normalized or rule.raw_keyword == normalized:
                return rule
        return ResolvedAttendanceRule(
            raw_keyword=normalized,
            normalized_status=normalized,
            symbol=normalized,
            counts_as_attendance=normalized == "√",
            counts_as_meal_allowance=normalized == "√",
            leave_type="present" if normalized == "√" else None,
            is_abnormal=normalized in {"旷工", "迟到", "缺卡"},
            priority=0,
        )

    exact_matches = [rule for rule in rules if rule.raw_keyword == normalized]
    if exact_matches:
        return max(exact_matches, key=lambda item: item.priority)

    substring_matches = [rule for rule in rules if rule.raw_keyword and rule.raw_keyword in normalized]
    if substring_matches:
        return max(substring_matches, key=lambda item: item.priority)

    return None


def is_known_status(text: str, rules: Sequence[ResolvedAttendanceRule]) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return True
    return match_rule(normalized, rules) is not None


def map_status_to_symbol(raw: str, rules: Sequence[ResolvedAttendanceRule]) -> str:
    """Map raw DingTalk / cell text to display symbol using configured rules."""
    text = (raw or "").strip()
    if not text:
        return ""

    matched = match_rule(text, rules)
    if matched:
        symbol = matched.symbol
        if symbol == "正常":
            return "√"
        return symbol

    if text in LEGACY_SYMBOLS:
        return text
    return ""


def apply_rule_to_totals(totals: dict, rule: ResolvedAttendanceRule) -> None:
    if rule.counts_as_attendance and rule.leave_type == "present":
        totals["present"] += 1
        return
    if rule.leave_type and rule.leave_type in totals:
        totals[rule.leave_type] += 1
        return
    if rule.is_abnormal:
        if rule.normalized_status == "旷工":
            totals["absenteeism"] += 1
        elif rule.normalized_status == "迟到":
            totals["lateness"] += 1
        elif rule.normalized_status == "缺卡":
            totals["missing_punch"] += 1


def build_status_options(rules: Sequence[ResolvedAttendanceRule]) -> List[dict]:
    """Build dropdown options for the attendance grid from unique normalized statuses."""
    seen: set[str] = set()
    options: List[dict] = []
    ordered = sorted(rules, key=lambda item: item.priority, reverse=True)
    for rule in ordered:
        if rule.normalized_status in seen:
            continue
        seen.add(rule.normalized_status)
        symbol = map_status_to_symbol(rule.normalized_status, rules) or rule.symbol
        options.append({"value": rule.normalized_status, "symbol": symbol})
    return options


def known_keywords(rules: Sequence[ResolvedAttendanceRule]) -> Iterable[str]:
    for rule in rules:
        yield rule.raw_keyword
