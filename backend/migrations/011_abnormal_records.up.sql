CREATE TABLE IF NOT EXISTS abnormal_records (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    period_id INTEGER NOT NULL REFERENCES attendance_periods(id) ON DELETE CASCADE,
    employee_attendance_id INTEGER REFERENCES employee_attendance(id) ON DELETE SET NULL,
    employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
    employee_name VARCHAR(100) NOT NULL,
    exception_type VARCHAR(30) NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    dates JSONB NOT NULL DEFAULT '[]'::jsonb,
    supplement_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT abnormal_records_type_check CHECK (
        exception_type IN (
            'absenteeism',
            'missing_punch',
            'late_arrival',
            'early_departure',
            'unrecognized',
            'conflicting'
        )
    ),
    CONSTRAINT abnormal_records_supplement_check CHECK (
        supplement_status IN ('pending', 'yes', 'no', 'not_required')
    )
);

CREATE INDEX IF NOT EXISTS idx_abnormal_records_period ON abnormal_records(period_id);
CREATE INDEX IF NOT EXISTS idx_abnormal_records_company ON abnormal_records(company_id);
CREATE INDEX IF NOT EXISTS idx_abnormal_records_employee ON abnormal_records(period_id, employee_name);
CREATE INDEX IF NOT EXISTS idx_abnormal_records_type ON abnormal_records(period_id, exception_type);

CREATE TABLE IF NOT EXISTS abnormal_record_edit_logs (
    id SERIAL PRIMARY KEY,
    abnormal_record_id INTEGER NOT NULL REFERENCES abnormal_records(id) ON DELETE CASCADE,
    edited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    editor_name VARCHAR(100),
    field_name VARCHAR(50) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    edited_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_abnormal_record_edit_logs_record ON abnormal_record_edit_logs(abnormal_record_id);
