from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EmployeeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    department: str
    position: Optional[str] = None
    total_attendance_days: int
    absenteeism_count: int
    lateness_count: int
    missing_punch_count: int
    anomaly_summary: Optional[str] = None
    supplement_submitted: bool
    notes: Optional[str] = None
    status: str
    manual_override_fields: List[str] = Field(default_factory=list)


class AttendancePatchRequest(BaseModel):
    field_name: str
    new_value: str


class AttendancePatchResponse(BaseModel):
    success: bool
    conflict_detected: bool
    conflict_id: Optional[int] = None
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    manual_override_fields: List[str] = Field(default_factory=list)


class MonthlyStats(BaseModel):
    total_employees: int
    total_absenteeism_days: int
    total_lateness_days: int
    total_missing_punch_days: int
    pending_conflicts: int
    pending_updates: int


class AttendanceSummaryResponse(BaseModel):
    year: int
    month: int
    stats: MonthlyStats
    last_sync: Optional[datetime] = None


class MonthlyAttendanceResponse(BaseModel):
    year: int
    month: int
    stats: MonthlyStats
    employees: List[EmployeeSummary]
    last_sync: Optional[datetime]


class PendingUpdateListItem(BaseModel):
    employee_name: str
    field_name: str
    new_value: Optional[str] = None


class SyncStatusResponse(BaseModel):
    last_sync_timestamp: Optional[datetime] = None
    pending_updates_count: int = 0
    pending_conflicts_count: int = 0
    pending_updates_list: List[PendingUpdateListItem] = Field(default_factory=list)
    employees_synced_at: Optional[datetime] = None
    attendance_synced_at: Optional[datetime] = None
    leaves_synced_at: Optional[datetime] = None
    overtime_synced_at: Optional[datetime] = None
    pending_updates: int = 0
    pending_conflicts: int = 0
    demo_mode: bool = False


class SyncResultResponse(BaseModel):
    success: bool
    message: str
    records_updated: int
    synced_at: datetime


class EmployeeSyncResponse(BaseModel):
    success: bool
    message: str
    added: int
    updated: int
    deactivated: int
    total_from_dingtalk: int
    synced_at: datetime


class MonthSyncRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class EmployeeLeaveSummary(BaseModel):
    employee_id: int
    name: str
    personal_leave_hours: float
    sick_leave_hours: float
    annual_leave_hours: float
    compensatory_leave_hours: float


class EmployeeOvertimeSummary(BaseModel):
    employee_id: int
    name: str
    overtime_hours: float


class LeaveSyncResponse(BaseModel):
    success: bool
    message: str
    year: int
    month: int
    employees_updated: int
    employees: List[EmployeeLeaveSummary]
    synced_at: datetime


class OvertimeSyncResponse(BaseModel):
    success: bool
    message: str
    year: int
    month: int
    employees_updated: int
    employees: List[EmployeeOvertimeSummary]
    synced_at: datetime


class ExcelFieldChange(BaseModel):
    employee_id: int
    employee_name: str
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    conflict: bool = False
    conflict_id: Optional[int] = None


class ExcelUploadResponse(BaseModel):
    success: bool
    year: int
    month: int
    snapshot_id: int
    changes_detected: int
    conflicts_created: int
    employees_modified: int
    pending_conflicts_count: int = 0
    changes: List[ExcelFieldChange]


class ConflictItem(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    department: str
    field_name: str
    manual_value: Optional[str] = None
    dingtalk_value: Optional[str] = None
    manual_edit_at: Optional[str] = None
    dingtalk_sync_at: Optional[str] = None
    created_at: Optional[str] = None
    status: str


class ConflictListResponse(BaseModel):
    year: int
    month: int
    total: int
    pending_conflicts_count: int
    conflicts: List[ConflictItem]


class ConflictResolveRequest(BaseModel):
    resolution_method: Literal["manual", "dingtalk_priority", "manual_priority"]
    resolved_value: Optional[str] = None


class ConflictBatchResolveRequest(BaseModel):
    conflict_ids: List[int]
    resolution_method: Literal["manual", "dingtalk_priority", "manual_priority"]
    resolved_value: Optional[str] = None


class ConflictAutoResolveRequest(BaseModel):
    year: Optional[int] = Field(default=None, ge=2000, le=2100)
    month: Optional[int] = Field(default=None, ge=1, le=12)


class ConflictResolveResponse(BaseModel):
    success: bool
    resolved_count: int
    pending_conflicts_count: int
    conflict_ids: List[int]


class ConflictSingleResolveResponse(BaseModel):
    success: bool
    conflict_id: int
    status: str
    resolution_method: str
    resolved_value: Optional[str] = None
    pending_conflicts_count: int


class VersionListItem(BaseModel):
    id: int
    version_number: int
    created_at: Optional[str] = None
    created_by: str
    summary: str
    event_type: Optional[str] = None
    snapshot_id: Optional[int] = None
    can_restore: bool
    changes_summary: dict = Field(default_factory=dict)


class VersionListResponse(BaseModel):
    year: int
    month: int
    total: int
    versions: List[VersionListItem]


class VersionCompareRequest(BaseModel):
    version_id_1: Optional[int] = None
    version_id_2: Optional[int] = None
    snapshot_id_1: Optional[int] = None
    snapshot_id_2: Optional[int] = None


class VersionFieldDiff(BaseModel):
    employee_id: int
    employee_name: str
    field_name: str
    value_in_snapshot_1: str
    value_in_snapshot_2: str


class VersionEmployeeChange(BaseModel):
    employee_id: int
    employee_name: str


class VersionCompareResponse(BaseModel):
    snapshot_id_1: int
    snapshot_id_2: int
    version_id_1: Optional[int] = None
    version_id_2: Optional[int] = None
    year: int
    month: int
    has_differences: bool
    added_employees: List[VersionEmployeeChange]
    removed_employees: List[VersionEmployeeChange]
    changed_fields: List[VersionFieldDiff]
    diff_text_old: str
    diff_text_new: str


class VersionRestoreRequest(BaseModel):
    version_id: Optional[int] = None
    snapshot_id: Optional[int] = None


class VersionRestoreResponse(BaseModel):
    success: bool
    restored_version_id: int
    restored_from_version: int
    employees_restored: int
    snapshot_id: int


class VersionDetailResponse(BaseModel):
    id: int
    version_number: int
    year: int
    month: int
    created_at: Optional[str] = None
    created_by: str
    changes_summary: dict = Field(default_factory=dict)
    version_note: Optional[str] = None
    snapshot_id: Optional[int] = None
    snapshot_version: Optional[int] = None
    data_snapshot: Optional[dict] = None


class VersionRollbackRequest(BaseModel):
    confirm_data_loss: bool = False


class VersionRollbackChange(BaseModel):
    employee_id: int
    employee_name: str
    field_name: str
    old_value: str
    new_value: str


class VersionRollbackResponse(BaseModel):
    success: bool
    version_id: int
    snapshot_id: int
    rolled_back_to_version: int
    rolled_back_to_version_id: int
    fields_changed: int
    employees_affected: int
    manual_changes_created: int
    conflicts_created: int
    pending_conflicts_count: int
    changes: List[VersionRollbackChange]


class MonthCloneCopyOptions(BaseModel):
    copy_employees: bool = True
    keep_attendance_data: bool = False
    keep_formulas: bool = True
    keep_manual_notes: bool = True
    reset_anomalies: bool = True


class MonthCloneRequest(BaseModel):
    source_year: int = Field(ge=2000, le=2100)
    source_month: int = Field(ge=1, le=12)
    target_year: int = Field(ge=2000, le=2100)
    target_month: int = Field(ge=1, le=12)
    copy_options: MonthCloneCopyOptions = Field(default_factory=MonthCloneCopyOptions)


class MonthCloneResponse(BaseModel):
    success: bool
    target_month_id: int
    employees_copied: int
    snapshot_id: Optional[int] = None
    version_number: Optional[int] = None
    target_year: int
    target_month: int
