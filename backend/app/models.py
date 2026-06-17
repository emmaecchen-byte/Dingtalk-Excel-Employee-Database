from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base

JsonType = JSON().with_variant(JSONB, "postgresql")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dingtalk_corp_id: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    employees: Mapped[List["Employee"]] = relationship(back_populates="company")
    users: Mapped[List["User"]] = relationship(back_populates="company")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    dingtalk_user_id: Mapped[Optional[str]] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="hr_viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    preferences: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="users")
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(back_populates="user")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    dingtalk_user_id: Mapped[Optional[str]] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    position: Mapped[Optional[str]] = mapped_column(String(100))
    employee_code: Mapped[Optional[str]] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="employees")
    attendance_records: Mapped[List["MonthlyAttendance"]] = relationship(back_populates="employee")


class MonthlyAttendance(Base):
    __tablename__ = "monthly_attendance"
    __table_args__ = (
        UniqueConstraint("company_id", "year", "month", "employee_id", name="monthly_attendance_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    total_attendance_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_personal_leave: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, default=0)
    total_sick_leave: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, default=0)
    total_annual_leave: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, default=0)
    total_compensatory_leave: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, default=0)
    total_overtime_hours: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, default=0)
    absenteeism_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lateness_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_punch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    anomaly_summary: Mapped[Optional[str]] = mapped_column(Text)
    supplement_submitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    manual_overrides: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    last_sync_from_dingtalk: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_manual_edit: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    employee: Mapped["Employee"] = relationship(back_populates="attendance_records")


for _day in range(1, 32):
    setattr(
        MonthlyAttendance,
        f"day_{_day}",
        mapped_column(f"day_{_day}", String(50), nullable=True),
    )

for _day in range(1, 32):
    setattr(
        MonthlyAttendance,
        f"overtime_day_{_day}",
        mapped_column(f"overtime_day_{_day}", Numeric(5, 1), nullable=True),
    )


class ExcelSnapshot(Base):
    __tablename__ = "excel_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    downloaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    dingtalk_sync_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime)
    data_snapshot: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    previous_snapshot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("excel_snapshots.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ManualChange(Base):
    __tablename__ = "manual_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    snapshot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("excel_snapshots.id", ondelete="SET NULL"))
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    change_source: Mapped[str] = mapped_column(String(20), nullable=False)
    change_timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    changed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    merged_to_truth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    merged_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PendingUpdate(Base):
    __tablename__ = "pending_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    dingtalk_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dingtalk_value: Mapped[Optional[str]] = mapped_column(Text)
    previous_value: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    conflict_id: Mapped[Optional[int]] = mapped_column(ForeignKey("conflicts.id", ondelete="SET NULL"))
    payload: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="dingtalk")
    endpoint: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    dingtalk_user_id: Mapped[Optional[str]] = mapped_column(String(100))
    event_id: Mapped[Optional[str]] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    payload: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    headers: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    pending_update_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pending_updates.id", ondelete="SET NULL")
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    sync_type: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Conflict(Base):
    __tablename__ = "conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dingtalk_value: Mapped[Optional[str]] = mapped_column(Text)
    manual_value: Mapped[Optional[str]] = mapped_column(Text)
    resolved_value: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    resolution_method: Mapped[Optional[str]] = mapped_column(String(30))
    resolved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class VersionHistory(Base):
    __tablename__ = "version_history"
    __table_args__ = (
        UniqueConstraint("company_id", "year", "month", "version_number", name="version_history_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_by: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    changes_summary: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    snapshot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("excel_snapshots.id", ondelete="SET NULL"))
    version_note: Mapped[Optional[str]] = mapped_column(Text)
