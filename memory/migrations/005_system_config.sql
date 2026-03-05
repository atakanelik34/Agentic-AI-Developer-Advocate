CREATE TABLE IF NOT EXISTS system_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT
);

INSERT INTO system_config (key, value, updated_by)
VALUES ('AUTO_MODE', 'DRY_RUN', 'migration')
ON CONFLICT (key) DO NOTHING;
