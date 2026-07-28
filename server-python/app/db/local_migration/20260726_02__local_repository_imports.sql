CREATE TABLE IF NOT EXISTS local_repository_import (
    id BIGSERIAL PRIMARY KEY,
    namespace_id BIGINT NOT NULL REFERENCES namespace(id),
    actor_id VARCHAR(128) NOT NULL REFERENCES user_account(id),
    provider VARCHAR(16) NOT NULL CHECK (provider = 'GITLAB'),
    connection_key VARCHAR(64) NOT NULL,
    project_id VARCHAR(128) NOT NULL,
    project_full_path VARCHAR(512) NOT NULL,
    requested_ref VARCHAR(256) NOT NULL,
    resolved_commit_sha CHAR(40) NOT NULL,
    source_web_url VARCHAR(2000) NOT NULL,
    upstream_url VARCHAR(2000),
    archive_sha256 CHAR(64) NOT NULL,
    archive_bytes BIGINT NOT NULL CHECK (archive_bytes >= 0),
    state VARCHAR(32) NOT NULL CHECK (state IN ('PREVIEW_READY', 'INGESTING', 'COMPLETED', 'PARTIAL', 'FAILED')),
    error_code VARCHAR(128),
    ingest_operation_id VARCHAR(64),
    previous_import_id BIGINT REFERENCES local_repository_import(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS local_repository_import_candidate (
    id BIGSERIAL PRIMARY KEY,
    import_id BIGINT NOT NULL REFERENCES local_repository_import(id) ON DELETE CASCADE,
    source_path VARCHAR(1000) NOT NULL,
    detected_name VARCHAR(256) NOT NULL,
    detected_description VARCHAR(2000) NOT NULL,
    source_version VARCHAR(64),
    target_slug VARCHAR(128),
    target_version VARCHAR(64),
    visibility VARCHAR(32),
    state VARCHAR(16) NOT NULL CHECK (state IN ('DISCOVERED', 'SELECTED', 'CREATED', 'FAILED')),
    skill_id BIGINT REFERENCES skill(id) ON DELETE SET NULL,
    skill_version_id BIGINT REFERENCES skill_version(id) ON DELETE SET NULL,
    warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_code VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (import_id, source_path)
);

CREATE INDEX IF NOT EXISTS idx_local_repository_import_namespace_state
    ON local_repository_import(namespace_id, state, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_local_repository_import_project_ref
    ON local_repository_import(connection_key, project_full_path, requested_ref, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_local_repository_import_candidate_state
    ON local_repository_import_candidate(import_id, state, id);

CREATE INDEX IF NOT EXISTS idx_local_repository_import_candidate_skill_id
    ON local_repository_import_candidate(skill_id)
    WHERE skill_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_local_repository_import_candidate_skill_version_id
    ON local_repository_import_candidate(skill_version_id)
    WHERE skill_version_id IS NOT NULL;
