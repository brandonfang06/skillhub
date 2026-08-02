CREATE TABLE IF NOT EXISTS review_attempt_archive (
    id BIGSERIAL PRIMARY KEY,
    original_review_task_id BIGINT NOT NULL UNIQUE,
    original_skill_version_id BIGINT NOT NULL,
    skill_id BIGINT NOT NULL,
    namespace_id BIGINT NOT NULL,
    namespace_slug VARCHAR(64) NOT NULL,
    skill_slug VARCHAR(128) NOT NULL,
    version VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status = 'REJECTED'),
    submitted_by VARCHAR(128) NOT NULL,
    reviewed_by VARCHAR(128),
    review_comment TEXT,
    submitted_at TIMESTAMPTZ NOT NULL,
    reviewed_at TIMESTAMPTZ,
    parsed_metadata_json JSONB,
    manifest_json JSONB,
    files_json JSONB NOT NULL,
    scanner_summary_json JSONB,
    original_request_id VARCHAR(64),
    replacement_version_id BIGINT,
    replacement_review_task_id BIGINT,
    archive_reason VARCHAR(64) NOT NULL DEFAULT 'REJECTED_VERSION_RESUBMIT',
    archived_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_review_attempt_archive_skill_version
    ON review_attempt_archive(skill_id, version, reviewed_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_review_attempt_archive_namespace_status_reviewed
    ON review_attempt_archive(namespace_id, status, reviewed_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_review_attempt_archive_replacement_review
    ON review_attempt_archive(replacement_review_task_id)
    WHERE replacement_review_task_id IS NOT NULL;
