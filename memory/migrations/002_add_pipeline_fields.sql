ALTER TABLE published_content
    ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'draft',
    ADD COLUMN IF NOT EXISTS quality_score DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS quality_flags JSONB DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS similarity_score DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS dedupe_source_id UUID,
    ADD COLUMN IF NOT EXISTS embedding_generated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS outbox_event_id UUID;

CREATE INDEX IF NOT EXISTS idx_published_content_status
    ON published_content (status, published_at DESC);
