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


class EmployeeSheetRow(BaseModel):
    id: int
    name: str
    department: str
    position: Optional[str] = None
    employee_code: Optional[str] = None
    days: List[str] = Field(default_factory=list)
    morning: List[str] = Field(default_factory=list)
    afternoon: List[str] = Field(default_factory=list)
    overtime_days: List[float] = Field(default_factory=list)
    sign_counts: dict = Field(default_factory=dict)
    absent_days: int = 0
    work_days: int = 0
    total_attendance_days: int = 0
    absenteeism_count: int = 0
    lateness_count: int = 0
    missing_punch_count: int = 0
    anomaly_summary: Optional[str] = None
    supplement_submitted: bool = False
    notes: Optional[str] = None
    first_anomaly_date: Optional[str] = None


class AttendanceSheetsResponse(BaseModel):
    company_name: str
    year: int
    month: int
    generated_at: datetime
    last_sync: Optional[datetime] = None
    work_days: int
    stats: MonthlyStats
    employees: List[EmployeeSheetRow]


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


class ExcelUploadConflictPreview(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    field_name: str
    dingtalk_value: Optional[str] = None
    manual_value: Optional[str] = None
    status: str


class ExcelUploadResponse(BaseModel):
    success: bool
    year: int
    month: int
    snapshot_id: int
    total_changes: int
    employees_affected: int
    changes_list: List[ExcelFieldChange]
    changes_detected: int
    employees_modified: int
    conflicts_created: int
    auto_merged: int = 0
    has_conflicts: bool = False
    conflicts_list: List[ExcelUploadConflictPreview] = Field(default_factory=list)
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
    resolved: int = 0
    failed: int = 0
    remaining: int = 0
    resolved_count: int = 0
    pending_conflicts_count: int = 0
    conflict_ids: List[int] = Field(default_factory=list)
    skipped_count: int = 0
    resolution_method: Optional[str] = None


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
    snapshot_data: Optional[dict] = None
    data_snapshot: Optional[dict] = None


class VersionRollbackRequest(BaseModel):
    confirm_data_loss: bool = False
    confirm_dingtalk_overwrite: bool = False


class VersionRollbackDingtalkWarning(BaseModel):
    employee_id: int
    employee_name: str
    field_name: str
    current_value: str
    rollback_value: str
    last_sync_from_dingtalk: Optional[str] = None


class VersionRollbackChange(BaseModel):
    employee_id: int
    employee_name: str
    field_name: str
    old_value: str
    new_value: str


class VersionRollbackResponse(BaseModel):
    success: bool
    new_version: int
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


class WebhookEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: Optional[int] = None
    source: str
    endpoint: str
    event_type: str
    dingtalk_user_id: Optional[str] = None
    event_id: Optional[str] = None
    status: str
    payload: dict = Field(default_factory=dict)
    error_message: Optional[str] = None
    pending_update_id: Optional[int] = None
    processed_at: Optional[datetime] = None
    created_at: datetime


class WebhookEventListResponse(BaseModel):
    events: List[WebhookEventResponse] = Field(default_factory=list)
    total: int = 0


class WebhookConfigResponse(BaseModel):
    attendance_url: str
    employee_url: str
    legacy_attendance_url: str
    webhook_secret_configured: bool
    webhook_crypto_configured: bool
    timestamp_max_skew_seconds: int
    allowed_ips: List[str] = Field(default_factory=list)
    demo_mode: bool
    supported_event_types: List[str] = Field(default_factory=list)


class WebhookReplayResponse(BaseModel):
    success: bool
    webhook_event_id: int
    status: str
    message: str


class WebhookTestRequest(BaseModel):
    user_id: str
    event_type: str = "attendance_check"
    event_time: Optional[str] = None
    event_id: Optional[str] = None
    work_date: Optional[str] = None
    year: Optional[int] = Field(None, ge=2000, le=2100)
    month: Optional[int] = Field(None, ge=1, le=12)
    data: Optional[dict] = None


class WebhookTestResponse(BaseModel):
    success: bool
    webhook_event_id: int
    pending_update_id: int
    pending_status: str
    duplicate: bool = False
    message: str


class ValidationIssueResponse(BaseModel):
    severity: str
    code: str
    message: str
    employee_name: Optional[str] = None
    day: Optional[int] = None
    row_index: Optional[int] = None


class AttendanceUploadResponse(BaseModel):
    success: bool
    period_id: int
    year: int
    month: int
    status: str
    employee_count: int
    daily_record_count: int
    requires_review_count: int
    persisted: bool
    has_blocking_errors: bool
    validation_issues: List[ValidationIssueResponse] = Field(default_factory=list)


class AttendanceStatusOption(BaseModel):
    value: str
    symbol: str


class AttendanceDayCell(BaseModel):
    daily_id: Optional[int] = None
    day: Optional[int] = None
    raw_text: str = ""
    status: str = ""
    symbol: str = ""
    requires_review: bool = False


class AttendanceRowTotals(BaseModel):
    present: int = 0
    personal_leave: int = 0
    compensatory_leave: int = 0
    business_trip: int = 0
    sick_leave: int = 0
    welfare_leave: int = 0
    annual_leave: int = 0
    maternity_leave: int = 0
    funeral_leave: int = 0
    marriage_leave: int = 0
    absenteeism: int = 0
    lateness: int = 0
    missing_punch: int = 0
    work_days: int = 0
    absent_days: int = 0


class AttendanceShiftRow(BaseModel):
    shift: str
    shift_label: str
    days: List[AttendanceDayCell] = Field(default_factory=list)
    totals: AttendanceRowTotals


class AttendanceTableEmployee(BaseModel):
    employee_attendance_id: int
    employee_id: Optional[int] = None
    employee_name: str
    department: str = ""
    requires_review: bool = False
    rows: List[AttendanceShiftRow] = Field(default_factory=list)
    totals: AttendanceRowTotals


class AttendancePeriodTableResponse(BaseModel):
    period_id: int
    year: int
    month: int
    days_in_month: int
    status: str
    is_editable: bool = True
    is_read_only: bool = False
    total_employees: int
    page: int
    page_size: int
    status_options: List[AttendanceStatusOption] = Field(default_factory=list)
    employees: List[AttendanceTableEmployee] = Field(default_factory=list)


class DailyAttendancePatchRequest(BaseModel):
    shift: Literal["morning", "afternoon"]
    status: str


class DailyAttendancePatchResponse(BaseModel):
    daily_id: int
    day: int
    shift: str
    status: str
    symbol: str
    morning_status: str = ""
    afternoon_status: str = ""
    morning_symbol: str = ""
    afternoon_symbol: str = ""
    raw_text: str
    requires_review: bool
    employee_attendance_id: int
    employee_requires_review: bool
    row_totals: AttendanceRowTotals
    employee_totals: AttendanceRowTotals


class AbnormalRecordDateEntry(BaseModel):
    day: int
    date: str
    morning: str = ""
    afternoon: str = ""
    raw_text: str = ""
    detail: str = ""
    shift: Optional[str] = None
    daily_id: Optional[int] = None


class AbnormalRecordEditLogResponse(BaseModel):
    id: int
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    editor_name: Optional[str] = None
    edited_at: datetime


class AbnormalRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_id: int
    employee_attendance_id: Optional[int] = None
    employee_id: Optional[int] = None
    employee_name: str
    exception_type: str
    summary: str
    dates: List[AbnormalRecordDateEntry] = Field(default_factory=list)
    supplement_status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    edit_logs: List[AbnormalRecordEditLogResponse] = Field(default_factory=list)


class AbnormalRecordListResponse(BaseModel):
    period_id: int
    total: int
    records: List[AbnormalRecordResponse] = Field(default_factory=list)


class AbnormalRecordUpdateRequest(BaseModel):
    supplement_status: Optional[str] = None
    notes: Optional[str] = None


class AbnormalRecordCreateRequest(BaseModel):
    employee_name: str
    exception_type: str
    summary: str
    dates: List[AbnormalRecordDateEntry] = Field(default_factory=list)
    employee_attendance_id: Optional[int] = None
    employee_id: Optional[int] = None
    supplement_status: str = "pending"
    notes: Optional[str] = None


class ExceptionDetectionResponse(BaseModel):
    period_id: int
    year: int
    month: int
    records_created: int


class AttendanceRuleResponse(BaseModel):
    id: int
    company_id: int
    raw_keyword: str
    normalized_status: str
    symbol: str
    counts_as_attendance: bool
    counts_as_meal_allowance: bool
    leave_type: Optional[str] = None
    is_abnormal: bool
    priority: int
    created_at: datetime
    updated_at: datetime


class AttendanceRuleListResponse(BaseModel):
    total: int
    rules: List[AttendanceRuleResponse] = Field(default_factory=list)


class AttendanceRuleCreateRequest(BaseModel):
    raw_keyword: str
    normalized_status: str
    symbol: str = ""
    counts_as_attendance: bool = False
    counts_as_meal_allowance: bool = False
    leave_type: Optional[str] = None
    is_abnormal: bool = False
    priority: int = 0


class AttendanceRuleUpdateRequest(BaseModel):
    raw_keyword: Optional[str] = None
    normalized_status: Optional[str] = None
    symbol: Optional[str] = None
    counts_as_attendance: Optional[bool] = None
    counts_as_meal_allowance: Optional[bool] = None
    leave_type: Optional[str] = None
    is_abnormal: Optional[bool] = None
    priority: Optional[int] = None


class AttendancePeriodSummary(BaseModel):
    id: int
    year: int
    month: int
    data_source: str
    employee_count: int
    exception_count: int
    status: str
    display_status: str
    is_editable: bool
    is_read_only: bool
    created_at: datetime
    updated_at: datetime
    confirmed_at: Optional[datetime] = None
    confirmed_by_name: Optional[str] = None
    archived_at: Optional[datetime] = None
    archived_by_name: Optional[str] = None
    source_filename: Optional[str] = None


class AttendancePeriodListResponse(BaseModel):
    total: int
    periods: List[AttendancePeriodSummary] = Field(default_factory=list)


class AttendancePeriodActionResponse(BaseModel):
    success: bool = True
    period: AttendancePeriodSummary


class AttendancePeriodEditLogResponse(BaseModel):
    id: int
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    employee_name: Optional[str] = None
    editor_name: Optional[str] = None
    edited_at: datetime


class EditLogResponse(BaseModel):
    id: str
    period_id: int
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    entity_type: str
    entity_id: int
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    action: str
    created_at: datetime


class EditLogListResponse(BaseModel):
    period_id: int
    total: int
    logs: List[EditLogResponse] = Field(default_factory=list)
