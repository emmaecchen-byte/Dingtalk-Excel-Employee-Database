from datetime import datetime
from typing import List, Optional
import uuid

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


class AttendancePeriod(Base):
    __tablename__ = "attendance_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    data_source: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")
    source_filename: Mapped[Optional[str]] = mapped_column(String(255))
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    archived_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    validation_summary: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    employee_rows: Mapped[List["EmployeeAttendance"]] = relationship(back_populates="period")
    edit_logs: Mapped[List["AttendancePeriodEditLog"]] = relationship(back_populates="period")
    audit_logs: Mapped[List["EditLog"]] = relationship(back_populates="period")


class EmployeeAttendance(Base):
    __tablename__ = "employee_attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("attendance_periods.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    employee_name: Mapped[str] = mapped_column(String(100), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    period: Mapped["AttendancePeriod"] = relationship(back_populates="employee_rows")
    employee: Mapped[Optional["Employee"]] = relationship()
    daily_records: Mapped[List["DailyAttendance"]] = relationship(back_populates="employee_attendance")


class DailyAttendance(Base):
    __tablename__ = "daily_attendance"
    __table_args__ = (
        UniqueConstraint("employee_attendance_id", "day", name="daily_attendance_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_attendance_id: Mapped[int] = mapped_column(
        ForeignKey("employee_attendance.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    morning_status: Mapped[Optional[str]] = mapped_column(String(100))
    afternoon_status: Mapped[Optional[str]] = mapped_column(String(100))
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    employee_attendance: Mapped["EmployeeAttendance"] = relationship(back_populates="daily_records")


class AbnormalRecord(Base):
    __tablename__ = "abnormal_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("attendance_periods.id", ondelete="CASCADE"), nullable=False)
    employee_attendance_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employee_attendance.id", ondelete="SET NULL")
    )
    employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    employee_name: Mapped[str] = mapped_column(String(100), nullable=False)
    exception_type: Mapped[str] = mapped_column(String(30), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dates: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    supplement_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    edit_logs: Mapped[List["AbnormalRecordEditLog"]] = relationship(back_populates="abnormal_record")


class AbnormalRecordEditLog(Base):
    __tablename__ = "abnormal_record_edit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    abnormal_record_id: Mapped[int] = mapped_column(
        ForeignKey("abnormal_records.id", ondelete="CASCADE"), nullable=False
    )
    edited_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    editor_name: Mapped[Optional[str]] = mapped_column(String(100))
    field_name: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    edited_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    abnormal_record: Mapped["AbnormalRecord"] = relationship(back_populates="edit_logs")


class AttendancePeriodEditLog(Base):
    __tablename__ = "attendance_period_edit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("attendance_periods.id", ondelete="CASCADE"), nullable=False
    )
    daily_attendance_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("daily_attendance.id", ondelete="SET NULL")
    )
    employee_name: Mapped[Optional[str]] = mapped_column(String(100))
    edited_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    editor_name: Mapped[Optional[str]] = mapped_column(String(100))
    field_name: Mapped[str] = mapped_column(String(80), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    edited_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    period: Mapped["AttendancePeriod"] = relationship(back_populates="edit_logs")


class EditLog(Base):
    """Unified audit log for attendance and exception edits."""

    __tablename__ = "edit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    period_id: Mapped[int] = mapped_column(
        ForeignKey("attendance_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str] = mapped_column(String(80), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(20), nullable=False, default="update")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    period: Mapped["AttendancePeriod"] = relationship(back_populates="audit_logs")


class AttendanceRule(Base):
    __tablename__ = "attendance_rules"
    __table_args__ = (UniqueConstraint("company_id", "raw_keyword", name="attendance_rules_company_keyword_unique"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    raw_keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_status: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    counts_as_attendance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    counts_as_meal_allowance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    leave_type: Mapped[Optional[str]] = mapped_column(String(50))
    is_abnormal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
