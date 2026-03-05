CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS published_content (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    content_type VARCHAR(50) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    platform_id TEXT,
    url TEXT,
    embedding vector(1536),
    tags TEXT[] DEFAULT '{}',
    published_at TIMESTAMPTZ DEFAULT NOW(),
    metrics JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS community_interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform VARCHAR(50) NOT NULL,
    external_id TEXT NOT NULL,
    content TEXT NOT NULL,
    our_reply TEXT,
    replied_at TIMESTAMPTZ,
    interaction_type VARCHAR(50),
    author_handle TEXT,
    UNIQUE(platform, external_id)
);

CREATE TABLE IF NOT EXISTS product_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(50),
    priority VARCHAR(20),
    evidence TEXT[] DEFAULT '{}',
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    submitted_to_team BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    importance INTEGER DEFAULT 5,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_accessed TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS weekly_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    week_start DATE NOT NULL UNIQUE,
    content_published INTEGER DEFAULT 0,
    community_interactions INTEGER DEFAULT 0,
    feedback_submitted INTEGER DEFAULT 0,
    total_reach INTEGER DEFAULT 0,
    top_content JSONB DEFAULT '[]',
    growth_experiments JSONB DEFAULT '[]',
    raw_report TEXT
);

CREATE TABLE IF NOT EXISTS rate_limit_state (
    platform VARCHAR(50) NOT NULL,
    bucket_key TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (platform, bucket_key)
);

CREATE INDEX IF NOT EXISTS idx_published_content_embedding
    ON published_content USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_agent_memory_embedding
    ON agent_memory USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_community_platform_replied
    ON community_interactions (platform, replied_at);
