-- Add compensatory leave (调休) hours column

BEGIN;

ALTER TABLE monthly_attendance
    ADD COLUMN IF NOT EXISTS total_compensatory_leave DECIMAL(5, 1) NOT NULL DEFAULT 0;

COMMIT;
