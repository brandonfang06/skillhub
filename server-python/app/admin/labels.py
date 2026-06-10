from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.api.skills import to_java_instant


class AdminLabelError(Exception):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


SLUG_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def _require_super_admin(platform_roles: list[str]) -> None:
    if "SUPER_ADMIN" not in set(platform_roles):
        raise AdminLabelError("label.definition.no_permission", status_code=403)


def _normalize_slug(slug: str | None) -> str:
    if slug is None or slug.strip() == "":
        raise AdminLabelError("error.slug.blank", status_code=400)
    normalized = slug.strip().lower()
    if len(normalized) > 64:
        raise AdminLabelError("error.slug.length", status_code=400)
    if not SLUG_PATTERN.match(normalized):
        raise AdminLabelError("error.slug.pattern", status_code=400)
    if "--" in normalized:
        raise AdminLabelError("error.slug.doubleHyphen", status_code=400)
    return normalized


def _normalize_translations(translations: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if not translations:
        raise AdminLabelError("label.translation.empty", status_code=400)
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in translations:
        locale = str(item.get("locale") or "").strip().replace("_", "-").lower()
        if not locale:
            raise AdminLabelError("label.translation.locale.blank", status_code=400)
        if locale in seen:
            raise AdminLabelError("label.translation.locale.duplicate", status_code=400)
        seen.add(locale)
        display_name = str(item.get("displayName") or item.get("display_name") or "").strip()
        if not display_name:
            raise AdminLabelError("label.translation.display_name.blank", status_code=400)
        normalized.append({"locale": locale, "displayName": display_name})
    return normalized


def _label_response(row: dict[str, Any], translations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "slug": str(row["slug"]),
        "type": str(row["type"]),
        "visibleInFilter": bool(row["visible_in_filter"]),
        "sortOrder": int(row["sort_order"]),
        "translations": [
            {"locale": str(item["locale"]), "displayName": str(item["display_name"])}
            for item in sorted(translations, key=lambda item: str(item["locale"]))
        ],
        "createdAt": to_java_instant(row["created_at"]),
    }


async def _read_label_by_slug(connection: Any, slug: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, slug, type, visible_in_filter, sort_order, created_by, created_at, updated_at
                FROM label_definition
                WHERE LOWER(slug) = :slug
                LIMIT 1
                """
            ),
            {"slug": _normalize_slug(slug)},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AdminLabelError("label.not_found", status_code=400)
    return dict(row)


async def _read_label_optional(connection: Any, slug: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, slug, type, visible_in_filter, sort_order, created_by, created_at, updated_at
                FROM label_definition
                WHERE LOWER(slug) = :slug
                LIMIT 1
                """
            ),
            {"slug": _normalize_slug(slug)},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _read_translations(connection: Any, label_id: int) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT label_id, locale, display_name
                FROM label_translation
                WHERE label_id = :label_id
                ORDER BY locale ASC
                """
            ),
            {"label_id": label_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _read_translations_for_labels(connection: Any, label_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not label_ids:
        return {}
    rows = (
        await connection.execute(
            text(
                """
                SELECT label_id, locale, display_name
                FROM label_translation
                WHERE label_id = ANY(CAST(:label_ids AS bigint[]))
                ORDER BY label_id ASC, locale ASC
                """
            ),
            {"label_ids": label_ids},
        )
    ).mappings().all()
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["label_id"]), []).append(dict(row))
    return grouped


async def _replace_translations(connection: Any, label_id: int, translations: list[dict[str, str]]) -> None:
    await connection.execute(text("DELETE FROM label_translation WHERE label_id = :label_id"), {"label_id": label_id})
    for item in translations:
        await connection.execute(
            text(
                """
                INSERT INTO label_translation (label_id, locale, display_name, created_at, updated_at)
                VALUES (:label_id, :locale, :display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {"label_id": label_id, "locale": item["locale"], "display_name": item["displayName"]},
        )


async def _write_audit(
    connection: Any,
    *,
    actor_user_id: str,
    action: str,
    target_id: int | None,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    detail: dict[str, Any],
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO audit_log (
                actor_user_id, action, target_type, target_id, request_id,
                client_ip, user_agent, detail_json, created_at
            )
            VALUES (
                :actor_user_id, :action, 'LABEL', :target_id, :request_id,
                :client_ip, :user_agent, :detail_json, :created_at
            )
            """
        ),
        {
            "actor_user_id": actor_user_id,
            "action": action,
            "target_id": target_id,
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "detail_json": json.dumps(detail, separators=(",", ":")),
            "created_at": datetime.now(UTC),
        },
    )


async def list_label_definitions(engine: Any, *, platform_roles: list[str]) -> list[dict[str, Any]]:
    _require_super_admin(platform_roles)
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, slug, type, visible_in_filter, sort_order, created_by, created_at, updated_at
                    FROM label_definition
                    ORDER BY sort_order ASC, id ASC
                    """
                )
            )
        ).mappings().all()
        labels = [dict(row) for row in rows]
        translations_by_label = await _read_translations_for_labels(connection, [int(row["id"]) for row in labels])
    return [_label_response(row, translations_by_label.get(int(row["id"]), [])) for row in labels]


async def create_label_definition(
    engine: Any,
    *,
    slug: str,
    type: str,
    visible_in_filter: bool,
    sort_order: int,
    translations: list[dict[str, Any]],
    actor_user_id: str,
    platform_roles: list[str],
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    _require_super_admin(platform_roles)
    normalized_slug = _normalize_slug(slug)
    normalized_translations = _normalize_translations(translations)
    async with engine.begin() as connection:
        count = (
            await connection.execute(text("SELECT COUNT(*) AS count FROM label_definition"))
        ).scalar_one()
        if int(count) >= 100:
            raise AdminLabelError("label.definition.too_many", status_code=400)
        if await _read_label_optional(connection, normalized_slug) is not None:
            raise AdminLabelError("label.slug.duplicate", status_code=400)
        row = (
            await connection.execute(
                text(
                    """
                    INSERT INTO label_definition (
                        slug, type, visible_in_filter, sort_order, created_by, created_at, updated_at
                    )
                    VALUES (
                        :slug, :type, :visible_in_filter, :sort_order, :created_by,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING id, slug, type, visible_in_filter, sort_order, created_by, created_at, updated_at
                    """
                ),
                {
                    "slug": normalized_slug,
                    "type": type,
                    "visible_in_filter": visible_in_filter,
                    "sort_order": sort_order,
                    "created_by": actor_user_id,
                },
            )
        ).mappings().one_or_none()
        label = dict(row) if row is not None else await _read_label_by_slug(connection, normalized_slug)
        await _replace_translations(connection, int(label["id"]), normalized_translations)
        await _write_audit(connection, actor_user_id=actor_user_id, action="LABEL_CREATE", target_id=int(label["id"]), request_id=request_id, client_ip=client_ip, user_agent=user_agent, detail={"slug": label["slug"]})
        translations_rows = await _read_translations(connection, int(label["id"]))
    return _label_response(label, translations_rows)


async def update_label_definition(
    engine: Any,
    *,
    slug: str,
    type: str,
    visible_in_filter: bool,
    sort_order: int,
    translations: list[dict[str, Any]],
    actor_user_id: str,
    platform_roles: list[str],
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    _require_super_admin(platform_roles)
    normalized_translations = _normalize_translations(translations)
    async with engine.begin() as connection:
        existing = await _read_label_by_slug(connection, slug)
        row = (
            await connection.execute(
                text(
                    """
                    UPDATE label_definition
                    SET type = :type,
                        visible_in_filter = :visible_in_filter,
                        sort_order = :sort_order,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :label_id
                    RETURNING id, slug, type, visible_in_filter, sort_order, created_by, created_at, updated_at
                    """
                ),
                {"label_id": int(existing["id"]), "type": type, "visible_in_filter": visible_in_filter, "sort_order": sort_order},
            )
        ).mappings().one_or_none()
        label = dict(row) if row is not None else await _read_label_by_slug(connection, str(existing["slug"]))
        await _replace_translations(connection, int(label["id"]), normalized_translations)
        await _write_audit(connection, actor_user_id=actor_user_id, action="LABEL_UPDATE", target_id=int(label["id"]), request_id=request_id, client_ip=client_ip, user_agent=user_agent, detail={"slug": label["slug"]})
        translations_rows = await _read_translations(connection, int(label["id"]))
    return _label_response(label, translations_rows)


async def delete_label_definition(
    engine: Any,
    *,
    slug: str,
    actor_user_id: str,
    platform_roles: list[str],
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> dict[str, str]:
    _require_super_admin(platform_roles)
    async with engine.begin() as connection:
        label = await _read_label_by_slug(connection, slug)
        await connection.execute(text("DELETE FROM label_definition WHERE id = :label_id"), {"label_id": int(label["id"])})
        await _write_audit(connection, actor_user_id=actor_user_id, action="LABEL_DELETE", target_id=int(label["id"]), request_id=request_id, client_ip=client_ip, user_agent=user_agent, detail={"slug": label["slug"]})
    return {"message": "Label deleted"}


async def update_label_sort_order(
    engine: Any,
    *,
    items: list[dict[str, Any]],
    actor_user_id: str,
    platform_roles: list[str],
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> list[dict[str, Any]]:
    _require_super_admin(platform_roles)
    if not items:
        raise AdminLabelError("label.sort_order.empty", status_code=400)
    async with engine.begin() as connection:
        labels: list[dict[str, Any]] = []
        for item in items:
            label = await _read_label_by_slug(connection, str(item["slug"]))
            row = (
                await connection.execute(
                    text(
                        """
                        UPDATE label_definition
                        SET sort_order = :sort_order,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :label_id
                        RETURNING id, slug, type, visible_in_filter, sort_order, created_by, created_at, updated_at
                        """
                    ),
                    {"label_id": int(label["id"]), "sort_order": int(item["sortOrder"])},
                )
            ).mappings().one_or_none()
            labels.append(dict(row) if row is not None else await _read_label_by_slug(connection, str(label["slug"])))
        await _write_audit(connection, actor_user_id=actor_user_id, action="LABEL_SORT_ORDER_UPDATE", target_id=None, request_id=request_id, client_ip=client_ip, user_agent=user_agent, detail={"count": len(items)})
        translations_by_label = await _read_translations_for_labels(connection, [int(row["id"]) for row in labels])
    labels.sort(key=lambda row: int(row["id"]))
    return [_label_response(row, translations_by_label.get(int(row["id"]), [])) for row in labels]
