CREATE TABLE IF NOT EXISTS attendance_periods (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    source_filename VARCHAR(255),
    uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    validation_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT attendance_periods_status_check CHECK (
        status IN ('draft', 'validated', 'published', 'failed')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_periods_company_period
    ON attendance_periods(company_id, year, month)
    WHERE status IN ('draft', 'validated', 'published');

CREATE TABLE IF NOT EXISTS employee_attendance (
    id SERIAL PRIMARY KEY,
    period_id INTEGER NOT NULL REFERENCES attendance_periods(id) ON DELETE CASCADE,
    employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
    employee_name VARCHAR(100) NOT NULL,
    row_index INTEGER NOT NULL DEFAULT 0,
    requires_review BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_employee_attendance_period ON employee_attendance(period_id);
CREATE INDEX IF NOT EXISTS idx_employee_attendance_name ON employee_attendance(period_id, employee_name);

CREATE TABLE IF NOT EXISTS daily_attendance (
    id SERIAL PRIMARY KEY,
    employee_attendance_id INTEGER NOT NULL REFERENCES employee_attendance(id) ON DELETE CASCADE,
    day INTEGER NOT NULL CHECK (day BETWEEN 1 AND 31),
    raw_text TEXT,
    morning_status VARCHAR(100),
    afternoon_status VARCHAR(100),
    requires_review BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT daily_attendance_unique UNIQUE (employee_attendance_id, day)
);

CREATE INDEX IF NOT EXISTS idx_daily_attendance_employee ON daily_attendance(employee_attendance_id);
