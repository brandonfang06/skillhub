CREATE TABLE IF NOT EXISTS local_oss_namespace_source (
    id BIGSERIAL PRIMARY KEY,
    namespace_id BIGINT NOT NULL UNIQUE REFERENCES namespace(id) ON DELETE CASCADE,
    repository_url VARCHAR(500) NOT NULL UNIQUE,
    created_by VARCHAR(128) NOT NULL REFERENCES user_account(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS local_oss_skill_source (
    id BIGSERIAL PRIMARY KEY,
    namespace_source_id BIGINT NOT NULL REFERENCES local_oss_namespace_source(id) ON DELETE CASCADE,
    source_path VARCHAR(1000) NOT NULL,
    skill_id BIGINT NOT NULL UNIQUE REFERENCES skill(id) ON DELETE CASCADE,
    created_by VARCHAR(128) NOT NULL REFERENCES user_account(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (namespace_source_id, source_path)
);

CREATE TABLE IF NOT EXISTS local_oss_skill_version_source (
    id BIGSERIAL PRIMARY KEY,
    skill_source_id BIGINT NOT NULL REFERENCES local_oss_skill_source(id) ON DELETE CASCADE,
    skill_version_id BIGINT NOT NULL UNIQUE REFERENCES skill_version(id) ON DELETE CASCADE,
    repository_revision_sha CHAR(40) NOT NULL,
    source_ref_type VARCHAR(16) NOT NULL CHECK (source_ref_type IN ('TAG', 'BRANCH', 'COMMIT')),
    source_ref VARCHAR(500),
    content_fingerprint CHAR(64) NOT NULL,
    imported_by VARCHAR(128) NOT NULL REFERENCES user_account(id),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (skill_source_id, content_fingerprint),
    CHECK (
        (source_ref_type = 'COMMIT' AND source_ref IS NULL)
        OR (source_ref_type IN ('TAG', 'BRANCH') AND source_ref IS NOT NULL)
    )
);
