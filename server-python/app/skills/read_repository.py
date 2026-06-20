import re
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth.context import bearer_token, has_bearer_authorization, resolve_current_user_or_401
from app.auth.policy import is_namespace_manager, is_namespace_member
from app.skills.read_compare import (
    BINARY_FILE_EXTENSIONS,
    COMPARE_MAX_FILE_BYTES,
    COMPARE_MAX_LINES,
    build_compare_file,
    build_compare_hunks,
    build_compare_response,
    is_binary_compare_path,
    split_compare_lines,
)
from app.skills.read_compat import (
    build_clawhub_resolve_response,
    build_clawhub_search_response,
    build_clawhub_skill_detail_response,
    build_clawhub_skills_list_response,
    build_cli_resolve_response,
    build_cli_search_response,
    clawhub_resolve_selectors,
    from_clawhub_canonical_slug,
    to_clawhub_canonical_slug,
)
from app.skills.read_access import (
    LIFECYCLE_LIST_PRIORITY,
    LIFECYCLE_MANAGER_STATUSES,
    assert_skill_row_access,
    can_access_skill_row,
    can_manage_lifecycle_for_row,
    lifecycle_list_priority,
    lifecycle_visible_statuses,
)
from app.skills.read_files import (
    DownloadResult,
    SkillResolveError,
    assert_download_access,
    assert_installable_download_access,
    assert_version_file_content_access,
    build_download_filename,
    build_download_response,
    bundle_storage_key,
    read_bundle_or_build_fallback_zip,
    read_file_content_from_row,
    read_local_storage_bytes,
    read_local_storage_text,
    sanitize_download_filename,
)
from app.skills.read_resolve import (
    build_resolve_response,
    compute_version_fingerprint,
    find_latest_version,
    has_text,
    matched_value,
    resolve_version_row,
)
from app.skills.read_responses import (
    build_skill_detail_response,
    build_skill_search_response,
    build_skill_summary_response,
    build_tag_response,
    build_version_detail_response,
    build_versions_page_response,
    normalize_page_request,
    paginate_rows,
    to_epoch_millis,
    to_java_instant,
    to_lifecycle_version,
)


VersionRow = dict[str, Any]
FileRow = dict[str, Any]


def normalized_current_user_id(mock_user_id: str | None) -> str | None:
    return mock_user_id.strip() if mock_user_id is not None and mock_user_id.strip() != "" else None


async def optional_current_user_id(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None = None,
) -> str | None:
    header_user_id = normalized_current_user_id(mock_user_id)
    if header_user_id is not None:
        return header_user_id

    if has_bearer_authorization(authorization):
        if bearer_token(authorization) is None:
            raise HTTPException(status_code=401, detail="error.auth.required")
        user = await resolve_current_user_or_401(request, None, authorization)
        return str(user["userId"])

    try:
        user = await resolve_current_user_or_401(request, None, None)
    except HTTPException as exc:
        if exc.status_code == 401:
            return None
        raise
    return str(user["userId"])


async def read_namespace_role(
    connection: Any,
    namespace_id: int,
    current_user_id: str | None,
) -> str | None:
    if current_user_id is None:
        return None
    return (
        await connection.execute(
            text(
                """
                SELECT role
                FROM namespace_member
                WHERE namespace_id = :namespace_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {"namespace_id": namespace_id, "user_id": current_user_id},
        )
    ).scalar_one_or_none()


def normalize_search_sort(sort: str | None) -> str:
    if sort is None or sort.strip() == "":
        return "newest"
    return sort.strip()


def parse_non_negative_int(raw_value: str | None, default_value: int) -> int:
    if raw_value is None or raw_value.strip() == "":
        return default_value
    normalized = raw_value.strip()
    if not re.fullmatch(r"\d+", normalized):
        return default_value
    try:
        return int(normalized)
    except ValueError:
        return default_value


def parse_positive_int(raw_value: str | None, default_value: int) -> int:
    parsed = parse_non_negative_int(raw_value, default_value)
    return parsed if parsed > 0 else default_value


def normalize_label_slugs(label_slugs: list[str] | None) -> list[str]:
    if not label_slugs:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in label_slugs:
        slug = value.strip().lower()
        if slug == "" or slug in seen:
            continue
        normalized.append(slug)
        seen.add(slug)
    return normalized


def normalize_search_keyword(keyword: str | None) -> str | None:
    if keyword is None or keyword.strip() == "":
        return None
    return keyword.strip().lower()


def build_skill_search_ts_query(keyword: str | None) -> str | None:
    normalized = normalize_search_keyword(keyword)
    if normalized is None:
        return None
    terms = re.findall(r"[\w\u4e00-\u9fff]+", normalized)[:8]
    compatible_terms = [
        term
        for term in terms
        if any(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" or ch == "_" for ch in term)
    ]
    if not compatible_terms:
        return None
    ts_terms = [
        f"{term}:*" if all(ord(ch) < 128 for ch in term) and any(ch.isalpha() for ch in term) else term
        for term in compatible_terms
    ]
    return " & ".join(ts_terms)


async def increment_published_download_counters(connection: Any, skill_id: int, version_id: int) -> None:
    await connection.execute(
        text("UPDATE skill SET download_count = download_count + 1 WHERE id = :skill_id"),
        {"skill_id": skill_id},
    )
    await connection.execute(
        text(
            """
            INSERT INTO skill_version_stats (skill_version_id, skill_id, download_count, updated_at)
            VALUES (:version_id, :skill_id, 1, CURRENT_TIMESTAMP)
            ON CONFLICT (skill_version_id)
            DO UPDATE SET download_count = skill_version_stats.download_count + 1,
                          updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"version_id": version_id, "skill_id": skill_id},
    )


async def read_skill_resolve(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    version: str | None,
    tag: str | None,
    hash_value: str | None,
    current_user_id: str | None = None,
    installable_only: bool = False,
) -> dict[str, object]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.slug, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        version_filters = ["skill_id = :skill_id", "status = 'PUBLISHED'"]
        if installable_only:
            version_filters.extend(["download_ready = TRUE", "yanked_at IS NULL"])
        version_where_sql = " AND ".join(version_filters)
        version_rows = (
            await connection.execute(
                text(
                    f"""
                    SELECT id, version
                    FROM skill_version
                    WHERE {version_where_sql}
                    ORDER BY id ASC
                    """
                ),
                {"skill_id": skill_row["id"]},
            )
        ).mappings().all()

        versions = [dict(row) for row in version_rows]
        version_ids = [row["id"] for row in versions]
        if not version_ids:
            raise SkillResolveError("error.skill.version.latest.unavailable")

        tag_rows = (
            await connection.execute(
                text(
                    """
                    SELECT tag_name, version_id
                    FROM skill_tag
                    WHERE skill_id = :skill_id
                    ORDER BY tag_name ASC
                    """
                ),
                {"skill_id": skill_row["id"]},
            )
        ).mappings().all()

        file_rows = (
            await connection.execute(
                text(
                    """
                    SELECT version_id, file_path, sha256
                    FROM skill_file
                    WHERE version_id = ANY(CAST(:version_ids AS bigint[]))
                    ORDER BY version_id ASC, file_path ASC
                    """
                ),
                {"version_ids": version_ids},
            )
        ).mappings().all()

    files_by_version: dict[int, list[FileRow]] = {int(version_id): [] for version_id in version_ids}
    for row in file_rows:
        files_by_version[int(row["version_id"])].append(dict(row))

    fingerprints = {
        int(version_row["id"]): compute_version_fingerprint(files_by_version[int(version_row["id"])])
        for version_row in versions
    }
    selected, matched = resolve_version_row(
        versions=versions,
        latest_version_id=int(skill_row["latest_version_id"]) if skill_row["latest_version_id"] is not None else None,
        tags={str(row["tag_name"]): int(row["version_id"]) for row in tag_rows},
        fingerprints=fingerprints,
        version=version,
        tag=tag,
        hash_value=hash_value,
    )
    selected_id = int(selected["id"])
    return build_resolve_response(
        skill_id=int(skill_row["id"]),
        namespace=namespace,
        slug=str(skill_row["slug"]),
        version_row=selected,
        fingerprint=fingerprints[selected_id],
        matched=matched,
    )


async def read_clawhub_legacy_slug_coordinate(engine: AsyncEngine, slug: str) -> tuple[str, str]:
    if "--" in slug:
        return from_clawhub_canonical_slug(slug)

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT n.slug AS namespace, s.slug AS slug
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE s.slug = :slug
                      AND n.status = 'ACTIVE'
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"slug": slug},
            )
        ).mappings().one_or_none()

    if row is None:
        return from_clawhub_canonical_slug(slug)
    return str(row["namespace"]), str(row["slug"])


async def read_skill_versions(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    page: int,
    size: int,
    current_user_id: str | None = None,
) -> dict[str, object]:
    page, size = normalize_page_request(page, size)
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
        can_manage = can_manage_lifecycle_for_row(dict(skill_row), current_user_id, namespace_role)
        visible_statuses = lifecycle_visible_statuses(can_manage)
        status_literals = ", ".join(f"'{status}'" for status in visible_statuses)
        rows = (
            await connection.execute(
                text(
                    f"""
                    SELECT id, version, status, changelog, file_count, total_size, published_at, download_ready
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND status IN ({status_literals})
                    ORDER BY
                      CASE status
                        WHEN 'PUBLISHED' THEN 0
                        WHEN 'REJECTED' THEN 1
                        WHEN 'PENDING_REVIEW' THEN 2
                        WHEN 'UPLOADED' THEN 3
                        WHEN 'DRAFT' THEN 4
                        WHEN 'SCANNING' THEN 5
                        WHEN 'SCAN_FAILED' THEN 6
                        WHEN 'YANKED' THEN 7
                        ELSE 8
                      END,
                      published_at DESC NULLS LAST,
                      created_at DESC NULLS LAST,
                      id DESC
                    """
                ),
                {"skill_id": skill_row["id"]},
            )
        ).mappings().all()

    page_rows, total = paginate_rows([dict(row) for row in rows], page, size)
    return build_versions_page_response(page_rows, total, page, size)


async def read_skill_version_detail(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    version: str,
    current_user_id: str | None = None,
) -> dict[str, object]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
        can_manage = can_manage_lifecycle_for_row(dict(skill_row), current_user_id, namespace_role)
        row = (
            await connection.execute(
                text(
                    """
                    SELECT sv.id,
                           sv.version,
                           sv.status,
                           sv.changelog,
                           sv.file_count,
                           sv.total_size,
                           sv.published_at,
                           sv.parsed_metadata_json::text AS parsed_metadata_json,
                           sv.manifest_json::text AS manifest_json
                    FROM skill_version sv
                    WHERE sv.skill_id = :skill_id
                      AND sv.version = :version
                    ORDER BY sv.id ASC
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "version": version},
            )
        ).mappings().one_or_none()

    if row is None:
        raise SkillResolveError("error.skill.version.notFound")
    if str(row["status"]) != "PUBLISHED" and not can_manage:
        raise SkillResolveError("error.skill.version.notPublished")
    return build_version_detail_response(dict(row))


async def read_skill_detail(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    current_user_id: str | None = None,
) -> dict[str, object]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id,
                           s.slug,
                           s.display_name,
                           s.owner_id,
                           NULLIF(BTRIM(ua.display_name), '') AS owner_display_name,
                           s.summary,
                           s.visibility,
                           s.status,
                           s.download_count,
                           s.star_count,
                           s.subscription_count,
                           s.rating_avg,
                           s.rating_count,
                           s.hidden,
                           s.namespace_id,
                           s.latest_version_id,
                           n.slug AS namespace,
                           n.type AS namespace_type,
                           n.status AS namespace_status
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    LEFT JOIN user_account ua ON ua.id = s.owner_id
                    WHERE n.slug = :namespace
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")
        if str(skill_row["namespace_status"]) == "ARCHIVED":
            raise SkillResolveError("error.namespace.archived", status_code=403)

        namespace_role = None
        if current_user_id is not None:
            namespace_role = (
                await connection.execute(
                    text(
                        """
                        SELECT role
                        FROM namespace_member
                        WHERE namespace_id = :namespace_id
                          AND user_id = :user_id
                        LIMIT 1
                        """
                    ),
                    {
                        "namespace_id": skill_row["namespace_id"],
                        "user_id": current_user_id,
                    },
                )
            ).scalar_one_or_none()
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
        if str(skill_row["visibility"]) != "PUBLIC" and not is_namespace_member(namespace_role):
            raise SkillResolveError("error.skill.access.denied", status_code=403)

        published_version = (
            await connection.execute(
                text(
                    """
                    SELECT id, version, status, created_at
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND status = 'PUBLISHED'
                    ORDER BY
                      CASE WHEN id = :latest_version_id THEN 0 ELSE 1 END,
                      published_at DESC NULLS LAST,
                      created_at DESC NULLS LAST,
                      id DESC
                    LIMIT 1
                    """
                ),
                {
                    "skill_id": skill_row["id"],
                    "latest_version_id": skill_row["latest_version_id"],
                },
            )
        ).mappings().one_or_none()

        can_manage_lifecycle = current_user_id is not None and (
            str(skill_row["owner_id"]) == str(current_user_id) or is_namespace_manager(namespace_role)
        )
        owner_preview_version = None
        owner_preview_review_comment = None
        if can_manage_lifecycle:
            if published_version is None:
                preview_where_sql = ""
                preview_params: dict[str, Any] = {"skill_id": skill_row["id"]}
            elif published_version["created_at"] is None:
                preview_where_sql = "AND sv.created_at IS NULL AND sv.id > :published_version_id"
                preview_params = {
                    "skill_id": skill_row["id"],
                    "published_version_id": published_version["id"],
                }
            else:
                preview_where_sql = """
                          AND (
                              sv.created_at IS NULL
                              OR (
                                  sv.created_at IS NOT NULL
                                  AND (
                                      sv.created_at > :published_created_at
                                      OR (sv.created_at = :published_created_at AND sv.id > :published_version_id)
                                  )
                              )
                          )
                """
                preview_params = {
                    "skill_id": skill_row["id"],
                    "published_version_id": published_version["id"],
                    "published_created_at": published_version["created_at"],
                }
            owner_preview_version = (
                await connection.execute(
                    text(
                        f"""
                        SELECT sv.id, sv.version, sv.status, sv.created_at
                        FROM skill_version sv
                        WHERE sv.skill_id = :skill_id
                          AND sv.status NOT IN ('PUBLISHED', 'YANKED')
                          {preview_where_sql}
                        ORDER BY sv.created_at DESC NULLS FIRST, sv.id DESC
                        LIMIT 1
                        """
                    ),
                    preview_params,
                )
            ).mappings().one_or_none()

            if owner_preview_version is not None and str(owner_preview_version["status"]) == "REJECTED":
                owner_preview_review_comment = (
                    await connection.execute(
                        text(
                            """
                            SELECT review_comment
                            FROM review_task
                            WHERE skill_version_id = :skill_version_id
                              AND status = 'REJECTED'
                            ORDER BY reviewed_at DESC NULLS LAST, id DESC
                            LIMIT 1
                            """
                        ),
                        {"skill_version_id": owner_preview_version["id"]},
                    )
                ).scalar_one_or_none()

        promotion_blocked = (
            await connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM promotion_request
                        WHERE source_skill_id = :skill_id
                          AND status IN ('PENDING', 'APPROVED')
                    )
                    """
                ),
                {"skill_id": skill_row["id"]},
            )
        ).scalar_one()

        labels = (
            await connection.execute(
                text(
                    """
                    SELECT ld.slug,
                           ld.type,
                           COALESCE(lt.display_name, ld.slug) AS display_name
                    FROM skill_label sl
                    JOIN label_definition ld ON ld.id = sl.label_id
                    LEFT JOIN label_translation lt
                      ON lt.label_id = ld.id
                     AND LOWER(REPLACE(lt.locale, '_', '-')) = 'en'
                    WHERE sl.skill_id = :skill_id
                    ORDER BY sl.id ASC
                    """
                ),
                {"skill_id": skill_row["id"]},
            )
        ).mappings().all()

    row = dict(skill_row)
    row["published_version_id"] = published_version["id"] if published_version is not None else None
    row["published_version"] = published_version["version"] if published_version is not None else None
    row["published_version_status"] = published_version["status"] if published_version is not None else None
    row["owner_preview_version_id"] = owner_preview_version["id"] if owner_preview_version is not None else None
    row["owner_preview_version"] = owner_preview_version["version"] if owner_preview_version is not None else None
    row["owner_preview_version_status"] = owner_preview_version["status"] if owner_preview_version is not None else None
    row["owner_preview_review_comment"] = owner_preview_review_comment
    row["current_user_id"] = current_user_id
    row["namespace_role"] = namespace_role
    row["promotion_blocked"] = promotion_blocked
    label_rows = [
        {
            "slug": str(label["slug"]),
            "type": str(label["type"]),
            "displayName": str(label["display_name"]),
        }
        for label in labels
    ]
    return build_skill_detail_response(row, label_rows)


async def read_clawhub_skill_detail(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
) -> dict[str, object]:
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id,
                           s.slug,
                           s.display_name,
                           s.summary,
                           s.visibility,
                           s.status,
                           s.hidden,
                           s.created_at,
                           s.updated_at,
                           s.latest_version_id,
                           n.slug AS namespace,
                           n.status AS namespace_status,
                           pv.id AS published_version_id,
                           pv.version AS published_version,
                           pv.status AS published_version_status,
                           pv.published_at,
                           pv.changelog
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    LEFT JOIN LATERAL (
                        SELECT sv.id, sv.version, sv.status, sv.published_at, sv.changelog
                        FROM skill_version sv
                        WHERE sv.skill_id = s.id
                          AND sv.status = 'PUBLISHED'
                        ORDER BY
                          CASE WHEN sv.id = s.latest_version_id THEN 0 ELSE 1 END,
                          sv.published_at DESC NULLS LAST,
                          sv.created_at DESC NULLS LAST,
                          sv.id DESC
                        LIMIT 1
                    ) pv ON TRUE
                    WHERE n.slug = :namespace
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

    if row is None:
        raise SkillResolveError("error.skill.notFound")
    if str(row["namespace_status"]) == "ARCHIVED":
        raise SkillResolveError("error.namespace.archived", status_code=403)
    if str(row["visibility"]) != "PUBLIC":
        raise SkillResolveError("error.skill.access.denied", status_code=403)

    published_version = None
    if row["published_version_id"] is not None:
        published_version = {
            "id": int(row["published_version_id"]),
            "version": str(row["published_version"]),
            "status": str(row["published_version_status"]),
        }

    return {
        "slug": str(row["slug"]),
        "displayName": row["display_name"],
        "summary": row["summary"],
        "namespace": str(row["namespace"]),
        "publishedVersion": published_version,
        "createdAt": to_java_instant(row["created_at"]),
        "publishedAt": to_java_instant(row["published_at"]),
        "updatedAt": to_java_instant(row["updated_at"]),
        "changelog": row["changelog"],
    }


async def read_skill_search(
    engine: AsyncEngine,
    keyword: str | None,
    namespace: str | None,
    labels: list[str],
    sort: str,
    page: int,
    size: int,
    installable_only: bool = False,
) -> dict[str, object]:
    normalized_keyword = normalize_search_keyword(keyword)
    ts_query = build_skill_search_ts_query(normalized_keyword)
    has_keyword = normalized_keyword is not None
    use_relevance_ordering = sort == "relevance" and has_keyword

    filters = [
        "d.visibility = 'PUBLIC'",
        "d.status = 'ACTIVE'",
        "s.status = 'ACTIVE'",
        "s.hidden = FALSE",
        "n.status <> 'ARCHIVED'",
    ]
    installable_join_sql = ""
    if installable_only:
        installable_join_sql = "JOIN skill_version isv ON isv.id = s.latest_version_id"
        filters.extend(
            [
                "isv.status = 'PUBLISHED'",
                "isv.download_ready = TRUE",
                "isv.yanked_at IS NULL",
            ]
        )
    params: dict[str, object] = {
        "limit": size,
        "offset": page * size,
    }

    if namespace is not None and namespace.strip() != "":
        filters.append("d.namespace_slug = :namespace")
        params["namespace"] = namespace.strip()

    if labels:
        filters.append(
            """
            d.skill_id IN (
                SELECT sl.skill_id
                FROM skill_label sl
                JOIN label_definition ld ON ld.id = sl.label_id
                WHERE LOWER(ld.slug) = ANY(CAST(:label_slugs AS text[]))
            )
            """
        )
        params["label_slugs"] = labels

    if has_keyword:
        keyword_filters = []
        if ts_query is not None:
            keyword_filters.append("d.search_vector @@ to_tsquery('simple', :ts_query)")
            params["ts_query"] = ts_query
        keyword_filters.append("LOWER(d.title) LIKE :title_like")
        filters.append("(" + " OR ".join(keyword_filters) + ")")
        params["title_like"] = f"%{normalized_keyword}%"

    if sort == "downloads":
        order_sql = "s.download_count DESC, s.updated_at DESC, d.skill_id DESC"
    elif sort == "rating":
        order_sql = "s.rating_avg DESC, s.updated_at DESC, d.skill_id DESC"
    elif use_relevance_ordering:
        params["title_exact"] = normalized_keyword
        params["title_prefix"] = f"{normalized_keyword}%"
        if ts_query is not None:
            rank_sql = "ts_rank_cd(d.search_vector, to_tsquery('simple', :ts_query)) DESC,"
        else:
            rank_sql = ""
        order_sql = (
            "CASE "
            "WHEN LOWER(d.title) = :title_exact THEN 4 "
            "WHEN LOWER(d.title) LIKE :title_prefix THEN 3 "
            "WHEN LOWER(d.title) LIKE :title_like THEN 2 "
            f"ELSE 1 END DESC, {rank_sql} d.updated_at DESC, d.skill_id DESC"
        )
    else:
        order_sql = "s.updated_at DESC, d.skill_id DESC"

    where_sql = " AND ".join(filters)

    async with engine.connect() as connection:
        total = (
            await connection.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM skill_search_document d
                    JOIN skill s ON s.id = d.skill_id
                    JOIN namespace n ON n.id = d.namespace_id
                    {installable_join_sql}
                    WHERE {where_sql}
                    """
                ),
                params,
            )
        ).scalar_one()

        rows = (
            await connection.execute(
                text(
                    f"""
                    SELECT s.id,
                           s.slug,
                           s.display_name,
                           s.summary,
                           s.visibility,
                           s.status,
                           s.download_count,
                           s.star_count,
                           s.rating_avg,
                           s.rating_count,
                           n.slug AS namespace,
                           s.updated_at,
                           pv.id AS published_version_id,
                           pv.version AS published_version,
                           pv.status AS published_version_status,
                           CASE WHEN pv.id IS NULL THEN 'NONE' ELSE 'PUBLISHED' END AS resolution_mode
                    FROM skill_search_document d
                    JOIN skill s ON s.id = d.skill_id
                    JOIN namespace n ON n.id = d.namespace_id
                    {installable_join_sql}
                    LEFT JOIN LATERAL (
                        SELECT sv.id, sv.version, sv.status
                        FROM skill_version sv
                        WHERE sv.skill_id = s.id
                          AND sv.status = 'PUBLISHED'
                        ORDER BY
                          CASE WHEN sv.id = s.latest_version_id THEN 0 ELSE 1 END,
                          sv.published_at DESC NULLS LAST,
                          sv.created_at DESC NULLS LAST,
                          sv.id DESC
                        LIMIT 1
                    ) pv ON TRUE
                    WHERE {where_sql}
                    ORDER BY {order_sql}
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).mappings().all()

    return build_skill_search_response([dict(row) for row in rows], int(total), page, size)


async def read_skill_version_files(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    version: str,
    current_user_id: str | None = None,
) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
        can_manage = can_manage_lifecycle_for_row(dict(skill_row), current_user_id, namespace_role)
        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id, status
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND version = :version
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "version": version},
            )
        ).mappings().one_or_none()

        if version_row is None:
            raise SkillResolveError("error.skill.version.notFound")
        if str(version_row["status"]) != "PUBLISHED" and not can_manage:
            raise SkillResolveError("error.skill.version.notPublished")

        version_id = version_row["id"]

        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, file_path, file_size, content_type, sha256
                    FROM skill_file
                    WHERE version_id = :version_id
                    ORDER BY file_path ASC
                    """
                ),
                {"version_id": version_id},
            )
        ).mappings().all()

    return [
        {
            "id": int(row["id"]),
            "filePath": str(row["file_path"]),
            "fileSize": int(row["file_size"]),
            "contentType": row["content_type"],
            "sha256": str(row["sha256"]),
        }
        for row in rows
    ]


async def read_skill_version_compare(
    engine: AsyncEngine,
    storage_base_path: str,
    namespace: str,
    slug: str,
    from_version: str,
    to_version: str,
    current_user_id: str | None = None,
) -> dict[str, object]:
    if from_version == to_version:
        raise SkillResolveError("error.skill.version.compare.same")

    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
        can_manage = can_manage_lifecycle_for_row(dict(skill_row), current_user_id, namespace_role)
        version_rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, version, status
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND version = ANY(CAST(:versions AS varchar[]))
                    ORDER BY version ASC
                    """
                ),
                {"skill_id": skill_row["id"], "versions": [from_version, to_version]},
            )
        ).mappings().all()

        versions_by_name = {str(row["version"]): row for row in version_rows}
        missing_version = from_version if from_version not in versions_by_name else to_version
        if missing_version not in versions_by_name:
            raise SkillResolveError("error.skill.version.notFound")

        for selected_version in (from_version, to_version):
            version_row = versions_by_name[selected_version]
            if str(version_row["status"]) != "PUBLISHED" and not can_manage:
                raise SkillResolveError("error.skill.version.notPublished")

        from_id = int(versions_by_name[from_version]["id"])
        to_id = int(versions_by_name[to_version]["id"])
        file_rows = (
            await connection.execute(
                text(
                    """
                    SELECT version_id, file_path, file_size, content_type, sha256, storage_key
                    FROM skill_file
                    WHERE version_id = ANY(CAST(:version_ids AS bigint[]))
                    ORDER BY version_id ASC, file_path ASC
                    """
                ),
                {"version_ids": [from_id, to_id]},
            )
        ).mappings().all()

    rows_by_version: dict[int, dict[str, dict[str, object]]] = {from_id: {}, to_id: {}}
    for row in file_rows:
        rows_by_version[int(row["version_id"])][str(row["file_path"])] = {
            "file_path": str(row["file_path"]),
            "file_size": int(row["file_size"]),
            "content_type": row["content_type"],
            "sha256": str(row["sha256"]),
            "storage_key": str(row["storage_key"]),
        }

    changed_paths = {
        path
        for path in set(rows_by_version[from_id]) | set(rows_by_version[to_id])
        if rows_by_version[from_id].get(path, {}).get("sha256") != rows_by_version[to_id].get(path, {}).get("sha256")
    }
    files_by_version: dict[int, dict[str, dict[str, object]]] = {from_id: {}, to_id: {}}
    for version_id in (from_id, to_id):
        for path in changed_paths:
            row = rows_by_version[version_id].get(path)
            if row is None:
                continue
            files_by_version[version_id][path] = {
                "file_path": row["file_path"],
                "file_size": row["file_size"],
                "content_type": row["content_type"],
                "sha256": row["sha256"],
                "content": read_local_storage_text(storage_base_path, str(row["storage_key"])),
            }

    return build_compare_response(
        from_version,
        to_version,
        files_by_version[from_id],
        files_by_version[to_id],
    )


async def read_skill_tag_files(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    tag_name: str,
    current_user_id: str | None = None,
) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
        skill_id = skill_row["id"]

        if tag_name.lower() == "latest":
            version_id = skill_row["latest_version_id"]
        else:
            version_id = (
                await connection.execute(
                    text(
                        """
                        SELECT version_id
                        FROM skill_tag
                        WHERE skill_id = :skill_id
                          AND tag_name = :tag_name
                        LIMIT 1
                        """
                    ),
                    {"skill_id": skill_id, "tag_name": tag_name},
                )
            ).scalar_one_or_none()

            if version_id is None:
                raise SkillResolveError("error.skill.tag.notFound")

        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id
                    FROM skill_version
                    WHERE id = :version_id
                      AND status = 'PUBLISHED'
                    LIMIT 1
                    """
                ),
                {"version_id": version_id},
            )
        ).mappings().one_or_none()

        if version_row is None:
            raise SkillResolveError("error.skill.tag.version.notFound")

        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, file_path, file_size, content_type, sha256
                    FROM skill_file
                    WHERE version_id = :version_id
                    ORDER BY file_path ASC
                    """
                ),
                {"version_id": version_id},
            )
        ).mappings().all()

    return [
        {
            "id": int(row["id"]),
            "filePath": str(row["file_path"]),
            "fileSize": int(row["file_size"]),
            "contentType": row["content_type"],
            "sha256": str(row["sha256"]),
        }
        for row in rows
    ]


async def list_skill_tags(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    current_user_id: str | None = None,
) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND (
                          (CAST(:current_user_id AS varchar) IS NOT NULL AND s.owner_id = CAST(:current_user_id AS varchar))
                          OR (s.latest_version_id IS NOT NULL AND s.hidden = false)
                      )
                    ORDER BY
                      CASE
                        WHEN CAST(:current_user_id AS varchar) IS NOT NULL AND s.owner_id = CAST(:current_user_id AS varchar) THEN 0
                        ELSE 1
                      END,
                      CASE
                        WHEN s.latest_version_id IS NOT NULL AND s.hidden = false THEN 0
                        ELSE 1
                      END,
                      s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug, "current_user_id": current_user_id},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)

        tag_rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, tag_name, version_id, created_at
                    FROM skill_tag
                    WHERE skill_id = :skill_id
                    ORDER BY tag_name ASC
                    """
                ),
                {"skill_id": skill_row["id"]},
            )
        ).mappings().all()

    tags = [build_tag_response(dict(row)) for row in tag_rows]
    if skill_row.get("latest_version_id") is not None:
        tags.append(
            {
                "id": None,
                "tagName": "latest",
                "versionId": int(skill_row["latest_version_id"]),
                "createdAt": None,
            }
        )
    return tags


async def read_namespace_row_for_tag_write(connection: Any, namespace: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT n.id, n.status
                FROM namespace n
                WHERE n.slug = :namespace
                LIMIT 1
                """
            ),
            {"namespace": namespace},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SkillResolveError("error.namespace.slug.notFound")
    return dict(row)


async def assert_namespace_tag_admin(connection: Any, namespace_id: int, user_id: str) -> None:
    role = await read_namespace_role(connection, namespace_id, user_id)
    if role is None:
        raise SkillResolveError("error.namespace.membership.required", status_code=403)
    if not is_namespace_manager(role):
        raise SkillResolveError("error.namespace.admin.required", status_code=403)


async def read_skill_row_for_tag_write(connection: Any, namespace_id: int, slug: str, current_user_id: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                FROM skill s
                WHERE s.namespace_id = :namespace_id
                  AND s.slug = :slug
                  AND (
                      s.owner_id = :current_user_id
                      OR (s.latest_version_id IS NOT NULL AND s.hidden = false)
                  )
                ORDER BY
                  CASE
                    WHEN s.owner_id = :current_user_id THEN 0
                    ELSE 1
                  END,
                  CASE
                    WHEN s.latest_version_id IS NOT NULL AND s.hidden = false THEN 0
                    ELSE 1
                  END,
                  s.id ASC
                LIMIT 1
                """
            ),
            {"namespace_id": namespace_id, "slug": slug, "current_user_id": current_user_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SkillResolveError("error.skill.notFound")
    return dict(row)


async def create_or_move_skill_tag(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    tag_name: str,
    target_version: str,
    user_id: str,
) -> dict[str, object]:
    if tag_name.lower() == "latest":
        raise SkillResolveError("error.skill.tag.latest.reserved")

    async with engine.begin() as connection:
        namespace_row = await read_namespace_row_for_tag_write(connection, namespace)
        await assert_namespace_tag_admin(connection, int(namespace_row["id"]), user_id)
        skill_row = await read_skill_row_for_tag_write(connection, int(namespace_row["id"]), slug, user_id)

        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id, status
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND version = :target_version
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "target_version": target_version},
            )
        ).mappings().one_or_none()
        if version_row is None:
            raise SkillResolveError("error.skill.version.notFound")
        if str(version_row["status"]) != "PUBLISHED":
            raise SkillResolveError("error.skill.tag.targetVersion.notPublished")

        existing_tag = (
            await connection.execute(
                text(
                    """
                    SELECT id, skill_id, tag_name, version_id
                    FROM skill_tag
                    WHERE skill_id = :skill_id
                      AND tag_name = :tag_name
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "tag_name": tag_name},
            )
        ).mappings().one_or_none()

        if existing_tag is None:
            saved_row = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill_tag (skill_id, tag_name, version_id, created_by)
                        VALUES (:skill_id, :tag_name, :version_id, :created_by)
                        RETURNING id, tag_name, version_id, created_at
                        """
                    ),
                    {
                        "skill_id": int(skill_row["id"]),
                        "tag_name": tag_name,
                        "version_id": int(version_row["id"]),
                        "created_by": user_id,
                    },
                )
            ).mappings().one()
        else:
            saved_row = (
                await connection.execute(
                    text(
                        """
                        UPDATE skill_tag
                        SET version_id = :version_id,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE skill_id = :skill_id
                          AND tag_name = :tag_name
                        RETURNING id, tag_name, version_id, created_at
                        """
                    ),
                    {
                        "skill_id": int(skill_row["id"]),
                        "tag_name": tag_name,
                        "version_id": int(version_row["id"]),
                    },
                )
            ).mappings().one()

    return build_tag_response(dict(saved_row))


async def delete_skill_tag(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    tag_name: str,
    user_id: str,
) -> dict[str, str]:
    if tag_name.lower() == "latest":
        raise SkillResolveError("error.skill.tag.latest.delete")

    async with engine.begin() as connection:
        namespace_row = await read_namespace_row_for_tag_write(connection, namespace)
        await assert_namespace_tag_admin(connection, int(namespace_row["id"]), user_id)
        skill_row = await read_skill_row_for_tag_write(connection, int(namespace_row["id"]), slug, user_id)
        tag_row = (
            await connection.execute(
                text(
                    """
                    SELECT id, skill_id, tag_name, version_id
                    FROM skill_tag
                    WHERE skill_id = :skill_id
                      AND tag_name = :tag_name
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "tag_name": tag_name},
            )
        ).mappings().one_or_none()
        if tag_row is None:
            raise SkillResolveError("error.skill.tag.notFound")

        await connection.execute(
            text(
                """
                DELETE FROM skill_tag
                WHERE skill_id = :skill_id
                  AND tag_name = :tag_name
                """
            ),
            {"skill_id": skill_row["id"], "tag_name": tag_name},
        )

    return {"message": "Tag deleted"}


async def read_skill_version_file_content(
    engine: AsyncEngine,
    storage_base_path: str,
    namespace: str,
    slug: str,
    version: str,
    file_path: str,
    current_user_id: str | None = None,
) -> bytes:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
        can_manage = can_manage_lifecycle_for_row(dict(skill_row), current_user_id, namespace_role)
        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id, status
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND version = :version
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "version": version},
            )
        ).mappings().one_or_none()

        if version_row is None:
            raise SkillResolveError("error.skill.version.notFound")
        assert_version_file_content_access(dict(version_row), can_manage)

        file_row = (
            await connection.execute(
                text(
                    """
                    SELECT file_path, storage_key
                    FROM skill_file
                    WHERE version_id = :version_id
                      AND file_path = :file_path
                    LIMIT 1
                    """
                ),
                {"version_id": version_row["id"], "file_path": file_path},
            )
        ).mappings().one_or_none()

    if file_row is None:
        raise SkillResolveError("error.skill.file.notFound")
    return read_file_content_from_row(storage_base_path, dict(file_row))


async def read_skill_tag_file_content(
    engine: AsyncEngine,
    storage_base_path: str,
    namespace: str,
    slug: str,
    tag_name: str,
    file_path: str,
    current_user_id: str | None = None,
) -> bytes:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
        skill_id = skill_row["id"]
        if tag_name.lower() == "latest":
            version_id = skill_row["latest_version_id"]
        else:
            version_id = (
                await connection.execute(
                    text(
                        """
                        SELECT version_id
                        FROM skill_tag
                        WHERE skill_id = :skill_id
                          AND tag_name = :tag_name
                        LIMIT 1
                        """
                    ),
                    {"skill_id": skill_id, "tag_name": tag_name},
                )
            ).scalar_one_or_none()

            if version_id is None:
                raise SkillResolveError("error.skill.tag.notFound")

        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id
                    FROM skill_version
                    WHERE id = :version_id
                      AND status = 'PUBLISHED'
                    LIMIT 1
                    """
                ),
                {"version_id": version_id},
            )
        ).mappings().one_or_none()

        if version_row is None:
            raise SkillResolveError("error.skill.tag.version.notFound")

        file_row = (
            await connection.execute(
                text(
                    """
                    SELECT file_path, storage_key
                    FROM skill_file
                    WHERE version_id = :version_id
                      AND file_path = :file_path
                    LIMIT 1
                    """
                ),
                {"version_id": version_row["id"], "file_path": file_path},
            )
        ).mappings().one_or_none()

    if file_row is None:
        raise SkillResolveError("error.skill.file.notFound")
    return read_file_content_from_row(storage_base_path, dict(file_row))


async def read_skill_download_version(
    engine: AsyncEngine,
    storage_base_path: str,
    namespace: str,
    slug: str,
    version: str,
    current_user_id: str | None = None,
    installable_only: bool = False,
) -> DownloadResult:
    async with engine.begin() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.slug, s.display_name
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        can_manage = can_manage_lifecycle_for_row(dict(skill_row), current_user_id, namespace_role)
        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id, version, status, download_ready, yanked_at
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND version = :version
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "version": version},
            )
        ).mappings().one_or_none()

        if version_row is None:
            raise SkillResolveError("error.skill.version.notFound")
        if installable_only:
            assert_installable_download_access(dict(version_row))
        else:
            assert_download_access(dict(version_row), can_manage)

        file_rows = (
            await connection.execute(
                text(
                    """
                    SELECT file_path, storage_key
                    FROM skill_file
                    WHERE version_id = :version_id
                    ORDER BY file_path ASC
                    """
                ),
                {"version_id": version_row["id"]},
            )
        ).mappings().all()

        row = {
            "skill_id": int(skill_row["id"]),
            "version_id": int(version_row["id"]),
            "version": str(version_row["version"]),
            "status": str(version_row["status"]),
            "display_name": skill_row["display_name"],
            "slug": str(skill_row["slug"]),
            "content_type": "application/zip",
            "content_length": None,
        }
        result = read_bundle_or_build_fallback_zip(storage_base_path, row, [dict(file_row) for file_row in file_rows])

        if str(version_row["status"]) == "PUBLISHED":
            await increment_published_download_counters(connection, int(skill_row["id"]), int(version_row["id"]))

    return result


async def read_skill_download_latest(
    engine: AsyncEngine,
    storage_base_path: str,
    namespace: str,
    slug: str,
    current_user_id: str | None = None,
    installable_only: bool = False,
) -> DownloadResult:
    async with engine.connect() as connection:
        version = (
            await connection.execute(
                text(
                    """
                    SELECT sv.version
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    JOIN skill_version sv ON sv.id = s.latest_version_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).scalar_one_or_none()

    if version is None:
        raise SkillResolveError("error.skill.version.latest.unavailable")
    return await read_skill_download_version(
        engine,
        storage_base_path,
        namespace,
        slug,
        str(version),
        current_user_id,
        installable_only=installable_only,
    )


async def read_skill_download_tag(
    engine: AsyncEngine,
    storage_base_path: str,
    namespace: str,
    slug: str,
    tag_name: str,
    current_user_id: str | None = None,
    installable_only: bool = False,
) -> DownloadResult:
    async with engine.connect() as connection:
        version = (
            await connection.execute(
                text(
                    """
                    SELECT sv.version
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    JOIN skill_tag st ON st.skill_id = s.id
                    JOIN skill_version sv ON sv.id = st.version_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                      AND st.tag_name = :tag_name
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug, "tag_name": tag_name},
            )
        ).scalar_one_or_none()

    if version is None:
        raise SkillResolveError("error.skill.tag.notFound")
    return await read_skill_download_version(
        engine,
        storage_base_path,
        namespace,
        slug,
        str(version),
        current_user_id,
        installable_only=installable_only,
    )
