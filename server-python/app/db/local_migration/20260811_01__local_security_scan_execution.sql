CREATE TABLE IF NOT EXISTS local_security_scan_execution (
    security_audit_id BIGINT PRIMARY KEY
        REFERENCES security_audit(id) ON DELETE CASCADE,
    scan_status VARCHAR(16) NOT NULL
        CHECK (scan_status IN ('PENDING', 'COMPLETE', 'PARTIAL', 'FAILED')),
    analyzers_requested JSONB NOT NULL DEFAULT '[]'::jsonb,
    analyzers_completed JSONB NOT NULL DEFAULT '[]'::jsonb,
    analyzer_failures JSONB NOT NULL DEFAULT '[]'::jsonb,
    failure_code VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
