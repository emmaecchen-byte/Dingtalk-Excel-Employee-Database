CREATE TABLE IF NOT EXISTS edit_logs (
    id VARCHAR(36) PRIMARY KEY,
    period_id INTEGER NOT NULL REFERENCES attendance_periods(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_name VARCHAR(100),
    entity_type VARCHAR(50) NOT NULL,
    entity_id INTEGER NOT NULL,
    field_name VARCHAR(80) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    action VARCHAR(20) NOT NULL DEFAULT 'update',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_edit_logs_period ON edit_logs(period_id);
CREATE INDEX IF NOT EXISTS idx_edit_logs_user ON edit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_edit_logs_created_at ON edit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_edit_logs_entity ON edit_logs(entity_type, entity_id);
