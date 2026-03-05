CREATE TABLE IF NOT EXISTS growth_experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    week_start DATE NOT NULL,
    hypothesis TEXT NOT NULL,
    method VARCHAR(100) NOT NULL,
    target_metric VARCHAR(100) NOT NULL,
    baseline_value DOUBLE PRECISION,
    result_value DOUBLE PRECISION,
    success BOOLEAN,
    status VARCHAR(30) NOT NULL DEFAULT 'planned',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_growth_experiments_week_status
    ON growth_experiments (week_start, status);
