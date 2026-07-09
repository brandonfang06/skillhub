CREATE TABLE IF NOT EXISTS local_skill_download_event (
    id BIGSERIAL PRIMARY KEY,
    skill_id BIGINT NOT NULL REFERENCES skill(id) ON DELETE CASCADE,
    skill_version_id BIGINT NOT NULL REFERENCES skill_version(id) ON DELETE CASCADE,
    user_id VARCHAR(128) REFERENCES user_account(id),
    namespace_slug VARCHAR(64) NOT NULL,
    skill_slug VARCHAR(128) NOT NULL,
    version VARCHAR(64) NOT NULL,
    source VARCHAR(16) NOT NULL CHECK (source IN ('api', 'web', 'cli')),
    request_id VARCHAR(64),
    client_ip VARCHAR(64),
    user_agent VARCHAR(512),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_local_skill_download_event_skill_created_at
    ON local_skill_download_event(skill_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_local_skill_download_event_version_created_at
    ON local_skill_download_event(skill_version_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_local_skill_download_event_user_created_at
    ON local_skill_download_event(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_local_skill_download_event_created_at
    ON local_skill_download_event(created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_local_skill_download_event_namespace_slug_created_at
    ON local_skill_download_event(namespace_slug, skill_slug, created_at DESC);
