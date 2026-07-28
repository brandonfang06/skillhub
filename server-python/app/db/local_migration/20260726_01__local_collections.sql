CREATE TABLE IF NOT EXISTS local_collection (
    id BIGSERIAL PRIMARY KEY,
    namespace_id BIGINT NOT NULL REFERENCES namespace(id),
    slug VARCHAR(128) NOT NULL,
    display_name VARCHAR(256) NOT NULL,
    summary VARCHAR(2000) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    hidden BOOLEAN NOT NULL DEFAULT FALSE,
    latest_published_version_id BIGINT,
    created_by VARCHAR(128) NOT NULL REFERENCES user_account(id),
    updated_by VARCHAR(128) NOT NULL REFERENCES user_account(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (namespace_id, slug)
);

CREATE TABLE IF NOT EXISTS local_collection_version (
    id BIGSERIAL PRIMARY KEY,
    collection_id BIGINT NOT NULL REFERENCES local_collection(id) ON DELETE CASCADE,
    version VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('DRAFT', 'PUBLISHED', 'YANKED')),
    draft_revision INTEGER NOT NULL DEFAULT 1 CHECK (draft_revision > 0),
    release_notes TEXT,
    created_by VARCHAR(128) NOT NULL REFERENCES user_account(id),
    published_by VARCHAR(128) REFERENCES user_account(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    UNIQUE (collection_id, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_local_collection_version_one_draft
    ON local_collection_version(collection_id)
    WHERE status = 'DRAFT';

CREATE TABLE IF NOT EXISTS local_collection_version_member (
    id BIGSERIAL PRIMARY KEY,
    collection_version_id BIGINT NOT NULL REFERENCES local_collection_version(id) ON DELETE CASCADE,
    skill_id BIGINT REFERENCES skill(id) ON DELETE SET NULL,
    skill_version_id BIGINT REFERENCES skill_version(id) ON DELETE SET NULL,
    skill_slug_snapshot VARCHAR(128) NOT NULL,
    skill_version_snapshot VARCHAR(64) NOT NULL,
    skill_owner_id_snapshot VARCHAR(128) NOT NULL,
    skill_visibility_snapshot VARCHAR(32) NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    note VARCHAR(500),
    UNIQUE (collection_version_id, skill_version_id),
    UNIQUE (collection_version_id, position)
);

CREATE OR REPLACE FUNCTION local_snapshot_collection_member_access_before_skill_delete()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE local_collection_version_member
    SET skill_owner_id_snapshot = OLD.owner_id,
        skill_visibility_snapshot = OLD.visibility
    WHERE skill_id = OLD.id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_local_collection_member_access_before_skill_delete
    BEFORE DELETE ON skill
    FOR EACH ROW
    EXECUTE FUNCTION local_snapshot_collection_member_access_before_skill_delete();

ALTER TABLE local_collection
    ADD CONSTRAINT fk_local_collection_latest_published_version
    FOREIGN KEY (latest_published_version_id) REFERENCES local_collection_version(id);

CREATE INDEX IF NOT EXISTS idx_local_collection_namespace_status
    ON local_collection(namespace_id, status, hidden);

CREATE INDEX IF NOT EXISTS idx_local_collection_version_collection_status
    ON local_collection_version(collection_id, status, published_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_local_collection_member_skill_version
    ON local_collection_version_member(skill_version_id, skill_id);

CREATE INDEX IF NOT EXISTS idx_local_collection_member_skill_id
    ON local_collection_version_member(skill_id)
    WHERE skill_id IS NOT NULL;
