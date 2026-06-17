CREATE TABLE IF NOT EXISTS webhook_events (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    source VARCHAR(30) NOT NULL DEFAULT 'dingtalk',
    endpoint VARCHAR(50) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    dingtalk_user_id VARCHAR(100),
    event_id VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    payload JSONB NOT NULL DEFAULT '{}',
    headers JSONB NOT NULL DEFAULT '{}',
    error_message TEXT,
    pending_update_id INTEGER REFERENCES pending_updates(id) ON DELETE SET NULL,
    processed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_status ON webhook_events(status);
CREATE INDEX IF NOT EXISTS idx_webhook_events_created_at ON webhook_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_webhook_events_event_id ON webhook_events(event_id);
