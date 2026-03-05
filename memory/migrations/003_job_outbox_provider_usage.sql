CREATE TABLE IF NOT EXISTS job_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0,
    payload JSONB DEFAULT '{}',
    result JSONB DEFAULT '{}',
    error TEXT,
    provider TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_job_runs_status_created
    ON job_runs (status, created_at DESC);

CREATE TABLE IF NOT EXISTS outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    payload JSONB NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    platform VARCHAR(50),
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    last_error TEXT,
    next_attempt_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outbox_events_status_next
    ON outbox_events (status, next_attempt_at);

ALTER TABLE published_content
    ADD CONSTRAINT fk_published_content_outbox_event
    FOREIGN KEY (outbox_event_id) REFERENCES outbox_events (id)
    ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS provider_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    request_id TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER,
    success BOOLEAN NOT NULL,
    cost_estimate_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_provider_usage_created
    ON provider_usage (created_at DESC);
