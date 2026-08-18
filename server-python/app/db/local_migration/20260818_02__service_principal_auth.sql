CREATE TABLE IF NOT EXISTS service_principal (
    id VARCHAR(128) PRIMARY KEY,
    code VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('ACTIVE', 'DISABLED')),
    created_by_user_id VARCHAR(128) NOT NULL REFERENCES user_account(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (code = LOWER(code))
);

CREATE TABLE IF NOT EXISTS service_token (
    id BIGSERIAL PRIMARY KEY,
    service_principal_id VARCHAR(128) NOT NULL REFERENCES service_principal(id),
    name VARCHAR(100) NOT NULL,
    token_prefix VARCHAR(16) NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    scope_json JSONB NOT NULL,
    created_by_user_id VARCHAR(128) NOT NULL REFERENCES user_account(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uk_service_token_active_name
    ON service_token (service_principal_id, LOWER(name))
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_service_token_principal
    ON service_token(service_principal_id);

CREATE INDEX IF NOT EXISTS idx_service_token_expires_at
    ON service_token(expires_at);

ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS actor_service_principal_id VARCHAR(128) REFERENCES service_principal(id);

CREATE INDEX IF NOT EXISTS idx_audit_log_service_actor
    ON audit_log(actor_service_principal_id);

ALTER TABLE local_oss_namespace_source
    ADD COLUMN IF NOT EXISTS created_by_service_principal_id VARCHAR(128) REFERENCES service_principal(id);

ALTER TABLE local_oss_skill_source
    ADD COLUMN IF NOT EXISTS created_by_service_principal_id VARCHAR(128) REFERENCES service_principal(id);

ALTER TABLE local_oss_skill_version_source
    ADD COLUMN IF NOT EXISTS imported_by_service_principal_id VARCHAR(128) REFERENCES service_principal(id);
