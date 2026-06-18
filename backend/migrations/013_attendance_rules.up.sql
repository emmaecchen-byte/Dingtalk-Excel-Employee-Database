CREATE TABLE IF NOT EXISTS attendance_rules (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    raw_keyword VARCHAR(100) NOT NULL,
    normalized_status VARCHAR(100) NOT NULL,
    symbol VARCHAR(20) NOT NULL DEFAULT '',
    counts_as_attendance BOOLEAN NOT NULL DEFAULT FALSE,
    counts_as_meal_allowance BOOLEAN NOT NULL DEFAULT FALSE,
    leave_type VARCHAR(50),
    is_abnormal BOOLEAN NOT NULL DEFAULT FALSE,
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT attendance_rules_company_keyword_unique UNIQUE (company_id, raw_keyword)
);

CREATE INDEX IF NOT EXISTS idx_attendance_rules_company ON attendance_rules(company_id);
CREATE INDEX IF NOT EXISTS idx_attendance_rules_priority ON attendance_rules(company_id, priority DESC);
