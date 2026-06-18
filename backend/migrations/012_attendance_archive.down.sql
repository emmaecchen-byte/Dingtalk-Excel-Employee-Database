DROP INDEX IF EXISTS idx_attendance_period_edit_logs_daily;
DROP INDEX IF EXISTS idx_attendance_period_edit_logs_period;
DROP TABLE IF EXISTS attendance_period_edit_logs;

DROP INDEX IF EXISTS idx_attendance_periods_company_period;

CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_periods_company_period
    ON attendance_periods(company_id, year, month)
    WHERE status IN ('draft', 'validated', 'published');

ALTER TABLE attendance_periods DROP CONSTRAINT IF EXISTS attendance_periods_status_check;

ALTER TABLE attendance_periods ADD CONSTRAINT attendance_periods_status_check CHECK (
    status IN ('draft', 'validated', 'published', 'failed')
);

ALTER TABLE attendance_periods DROP COLUMN IF EXISTS archived_at;
ALTER TABLE attendance_periods DROP COLUMN IF EXISTS archived_by;
ALTER TABLE attendance_periods DROP COLUMN IF EXISTS confirmed_at;
ALTER TABLE attendance_periods DROP COLUMN IF EXISTS confirmed_by;
ALTER TABLE attendance_periods DROP COLUMN IF EXISTS data_source;
