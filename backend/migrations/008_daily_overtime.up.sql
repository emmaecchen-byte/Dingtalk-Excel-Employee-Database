-- Daily overtime hours per employee (overtime_day_1 … overtime_day_31)

BEGIN;

ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_1 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_2 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_3 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_4 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_5 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_6 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_7 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_8 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_9 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_10 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_11 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_12 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_13 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_14 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_15 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_16 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_17 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_18 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_19 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_20 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_21 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_22 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_23 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_24 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_25 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_26 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_27 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_28 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_29 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_30 DECIMAL(5, 1);
ALTER TABLE monthly_attendance ADD COLUMN IF NOT EXISTS overtime_day_31 DECIMAL(5, 1);

COMMIT;
