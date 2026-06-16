-- DingTalk Attendance Management - Initial Schema
-- PostgreSQL 14+

BEGIN;

CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    dingtalk_corp_id VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    dingtalk_user_id VARCHAR(100),
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255),
    role VARCHAR(30) NOT NULL DEFAULT 'hr_viewer',
    preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT users_role_check CHECK (
        role IN ('hr_admin', 'hr_viewer', 'manager', 'employee')
    )
);

CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    dingtalk_user_id VARCHAR(100),
    name VARCHAR(100) NOT NULL,
    department VARCHAR(200) NOT NULL DEFAULT '',
    position VARCHAR(100),
    employee_code VARCHAR(50),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monthly_attendance (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    day_1 VARCHAR(50),
    day_2 VARCHAR(50),
    day_3 VARCHAR(50),
    day_4 VARCHAR(50),
    day_5 VARCHAR(50),
    day_6 VARCHAR(50),
    day_7 VARCHAR(50),
    day_8 VARCHAR(50),
    day_9 VARCHAR(50),
    day_10 VARCHAR(50),
    day_11 VARCHAR(50),
    day_12 VARCHAR(50),
    day_13 VARCHAR(50),
    day_14 VARCHAR(50),
    day_15 VARCHAR(50),
    day_16 VARCHAR(50),
    day_17 VARCHAR(50),
    day_18 VARCHAR(50),
    day_19 VARCHAR(50),
    day_20 VARCHAR(50),
    day_21 VARCHAR(50),
    day_22 VARCHAR(50),
    day_23 VARCHAR(50),
    day_24 VARCHAR(50),
    day_25 VARCHAR(50),
    day_26 VARCHAR(50),
    day_27 VARCHAR(50),
    day_28 VARCHAR(50),
    day_29 VARCHAR(50),
    day_30 VARCHAR(50),
    day_31 VARCHAR(50),
    total_attendance_days INTEGER NOT NULL DEFAULT 0,
    total_personal_leave DECIMAL(5, 1) NOT NULL DEFAULT 0,
    total_sick_leave DECIMAL(5, 1) NOT NULL DEFAULT 0,
    total_annual_leave DECIMAL(5, 1) NOT NULL DEFAULT 0,
    total_overtime_hours DECIMAL(5, 1) NOT NULL DEFAULT 0,
    absenteeism_count INTEGER NOT NULL DEFAULT 0,
    lateness_count INTEGER NOT NULL DEFAULT 0,
    missing_punch_count INTEGER NOT NULL DEFAULT 0,
    anomaly_summary TEXT,
    supplement_submitted BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    manual_overrides JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_sync_from_dingtalk TIMESTAMP,
    last_manual_edit TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT monthly_attendance_unique UNIQUE (company_id, year, month, employee_id)
);

CREATE TABLE IF NOT EXISTS excel_snapshots (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    snapshot_version INTEGER NOT NULL DEFAULT 1,
    downloaded_at TIMESTAMP,
    downloaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    file_name VARCHAR(255),
    file_size INTEGER,
    dingtalk_sync_timestamp TIMESTAMP,
    data_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    previous_snapshot_id INTEGER REFERENCES excel_snapshots(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT excel_snapshots_status_check CHECK (
        status IN ('active', 'superseded', 'merged')
    )
);

CREATE TABLE IF NOT EXISTS manual_changes (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    snapshot_id INTEGER REFERENCES excel_snapshots(id) ON DELETE SET NULL,
    field_name VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    change_source VARCHAR(20) NOT NULL,
    change_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    merged_to_truth BOOLEAN NOT NULL DEFAULT FALSE,
    merged_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT manual_changes_source_check CHECK (
        change_source IN ('excel_upload', 'web_ui', 'conflict', 'rollback')
    )
);

CREATE TABLE IF NOT EXISTS conflicts (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    field_name VARCHAR(100) NOT NULL,
    dingtalk_value TEXT,
    manual_value TEXT,
    resolved_value TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    resolution_method VARCHAR(30),
    resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT conflicts_status_check CHECK (
        status IN ('pending', 'resolved', 'ignored')
    ),
    CONSTRAINT conflicts_resolution_method_check CHECK (
        resolution_method IS NULL OR resolution_method IN (
            'manual', 'dingtalk_priority', 'manual_priority'
        )
    )
);

CREATE TABLE IF NOT EXISTS version_history (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    version_number INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(50) NOT NULL,
    created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    changes_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    snapshot_id INTEGER REFERENCES excel_snapshots(id) ON DELETE SET NULL,
    version_note TEXT,
    CONSTRAINT version_history_unique UNIQUE (company_id, year, month, version_number),
    CONSTRAINT version_history_created_by_check CHECK (
        created_by IN (
            'dingtalk_sync', 'hr_upload', 'manual_edit', 'conflict_resolution'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_users_company_id ON users(company_id);
CREATE INDEX IF NOT EXISTS idx_employees_company_id ON employees(company_id);
CREATE INDEX IF NOT EXISTS idx_employees_dingtalk_user_id ON employees(dingtalk_user_id);
CREATE INDEX IF NOT EXISTS idx_monthly_attendance_period ON monthly_attendance(company_id, year, month);
CREATE INDEX IF NOT EXISTS idx_monthly_attendance_employee ON monthly_attendance(employee_id);
CREATE INDEX IF NOT EXISTS idx_excel_snapshots_period ON excel_snapshots(company_id, year, month);
CREATE INDEX IF NOT EXISTS idx_manual_changes_period ON manual_changes(company_id, year, month);
CREATE INDEX IF NOT EXISTS idx_conflicts_period_status ON conflicts(company_id, year, month, status);
CREATE INDEX IF NOT EXISTS idx_version_history_period ON version_history(company_id, year, month);

COMMIT;
