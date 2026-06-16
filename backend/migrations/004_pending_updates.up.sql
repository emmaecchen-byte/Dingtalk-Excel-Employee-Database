CREATE TABLE IF NOT EXISTS pending_updates (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
    dingtalk_user_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    field_name VARCHAR(100) NOT NULL,
    dingtalk_value TEXT,
    previous_value TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    conflict_id INTEGER REFERENCES conflicts(id) ON DELETE SET NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    processed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pending_updates_company_status
    ON pending_updates (company_id, status);

CREATE INDEX IF NOT EXISTS idx_pending_updates_employee_period
    ON pending_updates (company_id, employee_id, year, month);
