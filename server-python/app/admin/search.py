from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text


class AdminSearchError(Exception):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


RESERVED_FRONTMATTER_FIELDS = {"name", "description", "version", "x-astron-compliance"}
KEYWORD_FIELD_NAMES = {"keywords", "keyword", "tags", "tag"}
TOKEN_SPLITTER = re.compile(r"[^\w]+", re.UNICODE)
DIMENSIONS = 64
NGRAM_WEIGHT = 0.35


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _require_super_admin(platform_roles: list[str]) -> None:
    if "SUPER_ADMIN" not in set(platform_roles):
        raise AdminSearchError("admin.search.no_permission", status_code=403)


def _java_string_hash(value: str) -> int:
    result = 0
    for char in value:
        result = (31 * result + ord(char)) & 0xFFFFFFFF
    if result >= 0x80000000:
        result -= 0x100000000
    return result


def _semantic_vector(text_value: str) -> str:
    vector = [0.0] * DIMENSIONS
    if text_value.strip():
        for raw_token in TOKEN_SPLITTER.split(text_value.lower()):
            token = raw_token.strip()
            if not token:
                continue
            _add_token_weight(vector, token, 1.0 + min(len(token), 12) / 12.0)
            if len(token) >= 3:
                for index in range(0, len(token) - 2):
                    _add_token_weight(vector, token[index : index + 3], NGRAM_WEIGHT)
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude:
        vector = [value / magnitude for value in vector]
    return ",".join(f"{value:.6f}" for value in vector)


def _add_token_weight(vector: list[float], token: str, weight: float) -> None:
    vector[_java_string_hash(token) % DIMENSIONS] += weight


def _enrich_for_index(raw_text: str) -> str:
    normalized = " ".join(raw_text.strip().split())
    if not normalized:
        return ""
    parts = dict.fromkeys([normalized])
    for token in TOKEN_SPLITTER.split(normalized):
        normalized_token = token.strip()
        if normalized_token:
            parts.setdefault(normalized_token.lower() if normalized_token.isascii() else normalized_token, None)
    return " ".join(parts.keys())


def _flatten_to_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, bool | int | float):
        return [str(value)]
    if isinstance(value, dict):
        values: list[str] = []
        for key, item in value.items():
            if key is not None:
                values.append(str(key))
            values.extend(_flatten_to_strings(item))
        return values
    if isinstance(value, Iterable):
        values = []
        for item in value:
            values.extend(_flatten_to_strings(item))
        return values
    return [str(value)]


def _metadata_frontmatter(raw_metadata: Any) -> dict[str, Any]:
    if raw_metadata is None:
        return {}
    try:
        metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
    except (TypeError, ValueError):
        return {}
    frontmatter = metadata.get("frontmatter") if isinstance(metadata, dict) else None
    return dict(frontmatter) if isinstance(frontmatter, dict) else {}


def _metadata_compliance_snapshot(raw_metadata: Any) -> dict[str, Any]:
    if raw_metadata is None:
        return {}
    try:
        metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
    except (TypeError, ValueError):
        return {}
    snapshot = metadata.get("complianceSnapshot") if isinstance(metadata, dict) else None
    return dict(snapshot) if isinstance(snapshot, dict) else {}


def _append_compliance_search_values(
    snapshot: dict[str, Any],
    keywords: set[str],
    search_parts: list[str],
) -> None:
    items = snapshot.get("items")
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        for field_name in ("standard", "version", "controlId", "title"):
            value = item.get(field_name)
            if not isinstance(value, str | bool | int | float):
                continue
            normalized = str(value).strip()
            if normalized:
                keywords.add(normalized)
                search_parts.append(normalized)


def _build_search_payload(skill: dict[str, Any], label_keywords: list[str]) -> tuple[str, str]:
    search_parts: list[str] = []
    keywords: set[str] = set()
    for value in (skill.get("slug"), skill.get("summary")):
        if value is not None and str(value).strip():
            search_parts.append(str(value).strip())
    for field_name, value in _metadata_frontmatter(skill.get("parsed_metadata_json")).items():
        normalized_field = str(field_name).lower()
        if normalized_field in KEYWORD_FIELD_NAMES:
            for keyword in _flatten_to_strings(value):
                if keyword.strip():
                    keywords.add(keyword.strip())
        if normalized_field not in RESERVED_FRONTMATTER_FIELDS and normalized_field not in KEYWORD_FIELD_NAMES:
            search_parts.append(str(field_name))
            search_parts.extend(text_value.strip() for text_value in _flatten_to_strings(value) if text_value.strip())
    _append_compliance_search_values(
        _metadata_compliance_snapshot(skill.get("parsed_metadata_json")),
        keywords,
        search_parts,
    )
    for label in label_keywords:
        if label.strip():
            keywords.add(label.strip())
    return _enrich_for_index(" ".join(sorted(keywords))), _enrich_for_index(" ".join(search_parts))


async def _read_active_skills(connection: Any) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT s.id AS skill_id,
                       s.namespace_id,
                       n.slug AS namespace_slug,
                       s.owner_id,
                       s.slug,
                       s.display_name,
                       s.summary,
                       s.visibility,
                       s.status,
                       CAST(sv.parsed_metadata_json AS text) AS parsed_metadata_json
                FROM skill s
                LEFT JOIN namespace n ON n.id = s.namespace_id
                JOIN LATERAL (
                    SELECT sv.id,
                           sv.parsed_metadata_json
                    FROM skill_version sv
                    WHERE sv.skill_id = s.id
                      AND sv.status = 'PUBLISHED'
                      AND EXISTS (
                          SELECT 1
                          FROM skill_file sf
                          WHERE sf.version_id = sv.id
                      )
                    ORDER BY
                      CASE WHEN sv.id = s.latest_version_id THEN 0 ELSE 1 END,
                      sv.published_at DESC NULLS LAST,
                      sv.created_at DESC NULLS LAST,
                      sv.id DESC
                    LIMIT 1
                ) sv ON TRUE
                WHERE s.status = 'ACTIVE'
                ORDER BY s.id ASC
                """
            )
        )
    ).mappings().all()
    return [dict(row) for row in rows if str(row.get("status")) == "ACTIVE" and row.get("namespace_slug") is not None]


async def _read_label_keywords(connection: Any, skill_ids: list[int]) -> dict[int, list[str]]:
    if not skill_ids:
        return {}
    rows = (
        await connection.execute(
            text(
                """
                SELECT sl.skill_id,
                       lt.display_name
                FROM skill_label sl
                JOIN label_definition ld ON ld.id = sl.label_id
                JOIN label_translation lt ON lt.label_id = ld.id
                WHERE sl.skill_id = ANY(CAST(:skill_ids AS bigint[]))
                ORDER BY sl.skill_id ASC, lt.locale ASC
                """
            ),
            {"skill_ids": skill_ids},
        )
    ).mappings().all()
    grouped: dict[int, list[str]] = {}
    for row in rows:
        grouped.setdefault(int(row["skill_id"]), []).append(str(row["display_name"]))
    return grouped


async def _upsert_document(connection: Any, skill: dict[str, Any], keywords: str, search_text: str) -> None:
    title = skill.get("display_name") or skill.get("slug")
    summary = skill.get("summary")
    semantic_vector = _semantic_vector("\n".join(str(value or "") for value in (title, summary, keywords, search_text)))
    await connection.execute(
        text(
            """
            INSERT INTO skill_search_document (
                skill_id, namespace_id, namespace_slug, owner_id, title, summary,
                keywords, search_text, semantic_vector, visibility, status, updated_at
            )
            VALUES (
                :skill_id, :namespace_id, :namespace_slug, :owner_id, :title, :summary,
                :keywords, :search_text, :semantic_vector, :visibility, :status, :updated_at
            )
            ON CONFLICT (skill_id) DO UPDATE SET
                namespace_id = EXCLUDED.namespace_id,
                namespace_slug = EXCLUDED.namespace_slug,
                owner_id = EXCLUDED.owner_id,
                title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                keywords = EXCLUDED.keywords,
                search_text = EXCLUDED.search_text,
                semantic_vector = EXCLUDED.semantic_vector,
                visibility = EXCLUDED.visibility,
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "skill_id": int(skill["skill_id"]),
            "namespace_id": int(skill["namespace_id"]),
            "namespace_slug": str(skill["namespace_slug"])[:64],
            "owner_id": str(skill["owner_id"])[:128],
            "title": str(title)[:512] if title is not None else None,
            "summary": str(summary) if summary is not None else None,
            "keywords": keywords,
            "search_text": search_text,
            "semantic_vector": semantic_vector,
            "visibility": str(skill["visibility"])[:32],
            "status": str(skill["status"])[:32],
            "updated_at": _utc_now_naive(),
        },
    )


async def upsert_skill_search_document(connection: Any, skill_id: int) -> None:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id AS skill_id,
                       s.namespace_id,
                       n.slug AS namespace_slug,
                       s.owner_id,
                       s.slug,
                       s.display_name,
                       s.summary,
                       s.visibility,
                       s.status,
                       CAST(sv.parsed_metadata_json AS text) AS parsed_metadata_json
                FROM skill s
                JOIN namespace n ON n.id = s.namespace_id
                JOIN LATERAL (
                    SELECT sv.id,
                           sv.parsed_metadata_json
                    FROM skill_version sv
                    WHERE sv.skill_id = s.id
                      AND sv.status = 'PUBLISHED'
                      AND EXISTS (
                          SELECT 1
                          FROM skill_file sf
                          WHERE sf.version_id = sv.id
                      )
                    ORDER BY
                      CASE WHEN sv.id = s.latest_version_id THEN 0 ELSE 1 END,
                      sv.published_at DESC NULLS LAST,
                      sv.created_at DESC NULLS LAST,
                      sv.id DESC
                    LIMIT 1
                ) sv ON TRUE
                WHERE s.id = :skill_id
                  AND s.status = 'ACTIVE'
                LIMIT 1
                """
            ),
            {"skill_id": skill_id},
        )
    ).mappings().one_or_none()
    if row is None:
        await connection.execute(text("DELETE FROM skill_search_document WHERE skill_id = :skill_id"), {"skill_id": skill_id})
        return

    labels = await _read_label_keywords(connection, [int(row["skill_id"])])
    keywords, search_text = _build_search_payload(dict(row), labels.get(int(row["skill_id"]), []))
    await _upsert_document(connection, dict(row), keywords, search_text)


async def _write_audit(
    connection: Any,
    *,
    actor_user_id: str,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO audit_log (
                actor_user_id, action, target_type, target_id, request_id,
                client_ip, user_agent, detail_json, created_at
            )
            VALUES (
                :actor_user_id, :action, :target_type, :target_id, :request_id,
                :client_ip, :user_agent, :detail_json, :created_at
            )
            """
        ),
        {
            "actor_user_id": actor_user_id,
            "action": "REBUILD_SEARCH_INDEX",
            "target_type": "SEARCH_INDEX",
            "target_id": None,
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "detail_json": '{"scope":"ALL"}',
            "created_at": _utc_now_naive(),
        },
    )


async def rebuild_search_index(
    engine: Any,
    *,
    actor_user_id: str,
    platform_roles: list[str],
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> dict[str, int]:
    _require_super_admin(platform_roles)
    async with engine.begin() as connection:
        skills = await _read_active_skills(connection)
        labels_by_skill = await _read_label_keywords(connection, [int(skill["skill_id"]) for skill in skills])
        rebuilt = 0
        for skill in skills:
            keywords, search_text = _build_search_payload(skill, labels_by_skill.get(int(skill["skill_id"]), []))
            await _upsert_document(connection, skill, keywords, search_text)
            rebuilt += 1
        await _write_audit(
            connection,
            actor_user_id=actor_user_id,
            request_id=request_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    return {"rebuilt": rebuilt}
