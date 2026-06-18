ALTER TABLE attendance_periods
    ADD COLUMN IF NOT EXISTS data_source VARCHAR(20) NOT NULL DEFAULT 'upload';

ALTER TABLE attendance_periods
    ADD COLUMN IF NOT EXISTS confirmed_by INTEGER REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE attendance_periods
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP;

ALTER TABLE attendance_periods
    ADD COLUMN IF NOT EXISTS archived_by INTEGER REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE attendance_periods
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP;

ALTER TABLE attendance_periods DROP CONSTRAINT IF EXISTS attendance_periods_status_check;

ALTER TABLE attendance_periods ADD CONSTRAINT attendance_periods_status_check CHECK (
    status IN ('draft', 'validated', 'confirmed', 'archived', 'published', 'failed')
);

DROP INDEX IF EXISTS idx_attendance_periods_company_period;

CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_periods_company_period
    ON attendance_periods(company_id, year, month)
    WHERE status IN ('draft', 'validated', 'confirmed', 'failed');

CREATE TABLE IF NOT EXISTS attendance_period_edit_logs (
    id SERIAL PRIMARY KEY,
    period_id INTEGER NOT NULL REFERENCES attendance_periods(id) ON DELETE CASCADE,
    daily_attendance_id INTEGER REFERENCES daily_attendance(id) ON DELETE SET NULL,
    employee_name VARCHAR(100),
    edited_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    editor_name VARCHAR(100),
    field_name VARCHAR(80) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    edited_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_attendance_period_edit_logs_period
    ON attendance_period_edit_logs(period_id);

CREATE INDEX IF NOT EXISTS idx_attendance_period_edit_logs_daily
    ON attendance_period_edit_logs(daily_attendance_id);
