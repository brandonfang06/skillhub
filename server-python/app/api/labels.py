from collections import defaultdict
from collections.abc import Awaitable
from inspect import isawaitable
import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth.context import read_current_mock_user
from app.core.response import ok

router = APIRouter()

LabelRow = dict[str, Any]
TranslationRow = dict[str, Any]
MAX_LABELS_PER_SKILL = 10


class SkillLabelMutationError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_locale(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().replace("_", "-").lower()


def locale_language(value: str | None) -> str:
    normalized = normalize_locale(value)
    return normalized.split("-", 1)[0] if normalized else ""


def resolve_display_name(slug: str, translations: list[TranslationRow], locale: str | None) -> str:
    values: dict[str, str] = {}
    for translation in translations:
        normalized = normalize_locale(str(translation["locale"]))
        display_name = str(translation["display_name"])
        if normalized not in values:
            values[normalized] = display_name

    for candidate in [normalize_locale(locale), locale_language(locale), "en"]:
        value = values.get(candidate)
        if value and value.strip():
            return value

    return slug


def build_label_response(
    labels: list[LabelRow],
    translations: list[TranslationRow],
    locale: str | None,
) -> list[dict[str, str]]:
    translations_by_label: dict[int, list[TranslationRow]] = defaultdict(list)
    for translation in translations:
        translations_by_label[int(translation["label_id"])].append(translation)

    visible_labels = [label for label in labels if bool(label["visible_in_filter"])]
    visible_labels.sort(key=lambda label: (int(label["sort_order"]), int(label["id"])))

    return [
        {
            "slug": str(label["slug"]),
            "type": str(label["type"]),
            "displayName": resolve_display_name(
                str(label["slug"]),
                translations_by_label[int(label["id"])],
                locale,
            ),
        }
        for label in visible_labels
    ]


def build_skill_label_response(
    labels: list[LabelRow],
    translations: list[TranslationRow],
    locale: str | None,
) -> list[dict[str, str]]:
    translations_by_label: dict[int, list[TranslationRow]] = defaultdict(list)
    for translation in translations:
        translations_by_label[int(translation["label_id"])].append(translation)

    labels.sort(key=lambda label: (str(label["type"]), str(label["slug"])))

    return [
        {
            "slug": str(label["slug"]),
            "type": str(label["type"]),
            "displayName": resolve_display_name(
                str(label["slug"]),
                translations_by_label[int(label["id"])],
                locale,
            ),
        }
        for label in labels
    ]


def _normalize_label_slug(value: str | None) -> str:
    if value is None or value.strip() == "":
        raise SkillLabelMutationError("error.slug.blank", status_code=400)
    return value.strip().lower()


def _roles(user: dict[str, Any]) -> list[str]:
    return [str(role) for role in user.get("platformRoles", [])]


def _user_id(user: dict[str, Any]) -> str:
    value = user.get("userId") or user.get("id")
    if value is None or str(value).strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    return str(value)


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    return request.client.host if request.client else None


def _request_meta(request: Request) -> dict[str, str | None]:
    return {
        "request_id": request.headers.get("X-Request-Id"),
        "client_ip": _client_ip(request),
        "user_agent": request.headers.get("User-Agent"),
    }


async def _read_current_user(request: Request, mock_user_id: str | None) -> dict[str, Any]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")
    user_id = mock_user_id.strip()
    reader = getattr(request.app.state, "auth_me_reader", None)
    user = await _resolve_reader_result(reader(user_id)) if reader is not None else await read_current_mock_user(request.app.state.db_engine, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return dict(user)


async def _read_skill_for_label_mutation(connection: Any, namespace: str, slug: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id,
                       s.namespace_id,
                       n.slug AS namespace_slug,
                       s.slug,
                       s.owner_id
                FROM skill s
                JOIN namespace n ON n.id = s.namespace_id
                WHERE n.slug = :namespace
                  AND s.slug = :slug
                ORDER BY s.id ASC
                LIMIT 1
                """
            ),
            {"namespace": namespace, "slug": slug},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SkillLabelMutationError("error.skill.notFound", status_code=400)
    return dict(row)


async def _read_label_definition_for_mutation(connection: Any, label_slug: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT id,
                       slug,
                       type,
                       created_at
                FROM label_definition
                WHERE LOWER(slug) = :label_slug
                LIMIT 1
                """
            ),
            {"label_slug": _normalize_label_slug(label_slug)},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SkillLabelMutationError("label.not_found", status_code=400)
    return dict(row)


async def _read_namespace_role(connection: Any, namespace_id: int, user_id: str) -> str | None:
    row = (
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
            {"namespace_id": namespace_id, "user_id": user_id},
        )
    ).mappings().one_or_none()
    return str(row["role"]) if row is not None else None


def _assert_can_manage_skill_label(
    *,
    skill: dict[str, Any],
    label: dict[str, Any],
    actor_user_id: str,
    platform_roles: list[str],
    namespace_role: str | None,
) -> None:
    roles = {str(role) for role in platform_roles}
    if "SUPER_ADMIN" in roles:
        return
    if str(label["type"]) == "PRIVILEGED":
        raise SkillLabelMutationError("label.skill.no_permission", status_code=403)
    if str(skill["owner_id"]) == actor_user_id or namespace_role in {"ADMIN", "OWNER"}:
        return
    raise SkillLabelMutationError("label.skill.no_permission", status_code=403)


async def _read_skill_label(
    connection: Any,
    *,
    skill_id: int,
    label_id: int,
) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, skill_id, label_id, created_by
                FROM skill_label
                WHERE skill_id = :skill_id
                  AND label_id = :label_id
                LIMIT 1
                """
            ),
            {"skill_id": skill_id, "label_id": label_id},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _skill_label_count(connection: Any, skill_id: int) -> int:
    return int(
        (
            await connection.execute(
                text("SELECT COUNT(*) FROM skill_label WHERE skill_id = :skill_id"),
                {"skill_id": skill_id},
            )
        ).scalar_one()
    )


async def _write_skill_label_audit(
    connection: Any,
    *,
    actor_user_id: str,
    action: str,
    skill_id: int,
    label_slug: str,
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
                :client_ip, :user_agent, :detail_json, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "actor_user_id": actor_user_id,
            "action": action,
            "target_type": "SKILL",
            "target_id": skill_id,
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "detail_json": json.dumps({"labelSlug": label_slug}, separators=(",", ":")),
        },
    )


async def _skill_label_response_for_definition(connection: Any, label: dict[str, Any]) -> dict[str, str]:
    translations = (
        await connection.execute(
            text(
                """
                SELECT label_id, locale, display_name
                FROM label_translation
                WHERE label_id = ANY(CAST(:label_ids AS bigint[]))
                ORDER BY label_id ASC, locale ASC
                """
            ),
            {"label_ids": [int(label["id"])]},
        )
    ).mappings().all()
    return build_skill_label_response([dict(label)], [dict(row) for row in translations], None)[0]


async def attach_skill_label(
    engine: Any,
    *,
    namespace: str,
    slug: str,
    label_slug: str,
    actor_user_id: str,
    platform_roles: list[str],
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> dict[str, str]:
    async with engine.begin() as connection:
        skill = await _read_skill_for_label_mutation(connection, namespace, slug)
        label = await _read_label_definition_for_mutation(connection, label_slug)
        namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), actor_user_id)
        _assert_can_manage_skill_label(
            skill=skill,
            label=label,
            actor_user_id=actor_user_id,
            platform_roles=platform_roles,
            namespace_role=namespace_role,
        )
        if await _skill_label_count(connection, int(skill["id"])) >= MAX_LABELS_PER_SKILL:
            raise SkillLabelMutationError("label.skill.too_many", status_code=400)
        existing = await _read_skill_label(connection, skill_id=int(skill["id"]), label_id=int(label["id"]))
        if existing is None:
            await connection.execute(
                text(
                    """
                    INSERT INTO skill_label (skill_id, label_id, created_by, created_at)
                    VALUES (:skill_id, :label_id, :created_by, CURRENT_TIMESTAMP)
                    """
                ),
                {"skill_id": int(skill["id"]), "label_id": int(label["id"]), "created_by": actor_user_id},
            )
        await _write_skill_label_audit(
            connection,
            actor_user_id=actor_user_id,
            action="SKILL_LABEL_ATTACH",
            skill_id=int(skill["id"]),
            label_slug=label_slug,
            request_id=request_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        return await _skill_label_response_for_definition(connection, label)


async def detach_skill_label(
    engine: Any,
    *,
    namespace: str,
    slug: str,
    label_slug: str,
    actor_user_id: str,
    platform_roles: list[str],
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
) -> dict[str, str]:
    async with engine.begin() as connection:
        skill = await _read_skill_for_label_mutation(connection, namespace, slug)
        label = await _read_label_definition_for_mutation(connection, label_slug)
        namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), actor_user_id)
        _assert_can_manage_skill_label(
            skill=skill,
            label=label,
            actor_user_id=actor_user_id,
            platform_roles=platform_roles,
            namespace_role=namespace_role,
        )
        existing = await _read_skill_label(connection, skill_id=int(skill["id"]), label_id=int(label["id"]))
        if existing is None:
            raise SkillLabelMutationError("label.skill.not_found", status_code=400)
        await connection.execute(
            text(
                """
                DELETE FROM skill_label
                WHERE skill_id = :skill_id
                  AND label_id = :label_id
                """
            ),
            {"skill_id": int(skill["id"]), "label_id": int(label["id"])},
        )
        await _write_skill_label_audit(
            connection,
            actor_user_id=actor_user_id,
            action="SKILL_LABEL_DETACH",
            skill_id=int(skill["id"]),
            label_slug=label_slug,
            request_id=request_id,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    return {"message": "Label detached"}


async def read_visible_labels(engine: AsyncEngine, locale: str | None) -> list[dict[str, str]]:
    async with engine.connect() as connection:
        label_rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, slug, type, visible_in_filter, sort_order
                    FROM label_definition
                    WHERE visible_in_filter = true
                    ORDER BY sort_order ASC, id ASC
                    """
                )
            )
        ).mappings().all()

        label_ids = [row["id"] for row in label_rows]
        if not label_ids:
            return []

        translation_rows = (
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

    return build_label_response(
        [dict(row) for row in label_rows],
        [dict(row) for row in translation_rows],
        locale,
    )


async def read_skill_labels(engine: AsyncEngine, namespace: str, slug: str, locale: str | None) -> list[dict[str, str]]:
    async with engine.connect() as connection:
        skill_id = (
            await connection.execute(
                text(
                    """
                    SELECT s.id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND s.slug = :slug
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                      AND s.visibility = 'PUBLIC'
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).scalar_one_or_none()

        if skill_id is None:
            return []

        label_rows = (
            await connection.execute(
                text(
                    """
                    SELECT ld.id, ld.slug, ld.type
                    FROM skill_label sl
                    JOIN label_definition ld ON ld.id = sl.label_id
                    WHERE sl.skill_id = :skill_id
                    ORDER BY ld.type ASC, ld.slug ASC
                    """
                ),
                {"skill_id": skill_id},
            )
        ).mappings().all()

        label_ids = [row["id"] for row in label_rows]
        if not label_ids:
            return []

        translation_rows = (
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

    return build_skill_label_response(
        [dict(row) for row in label_rows],
        [dict(row) for row in translation_rows],
        locale,
    )


def requested_locale(request: Request) -> str | None:
    accept_language = request.headers.get("Accept-Language")
    if not accept_language:
        return None
    return accept_language.split(",", 1)[0].strip() or None


async def _resolve_reader_result(result: list[dict[str, str]] | Awaitable[list[dict[str, str]]]) -> list[dict[str, str]]:
    if isawaitable(result):
        return await result
    return result


@router.get("/api/v1/labels")
@router.get("/api/web/labels")
async def list_visible_labels(request: Request) -> dict[str, object]:
    locale = requested_locale(request)
    reader = getattr(request.app.state, "label_reader", None)
    if reader is not None:
        data = await _resolve_reader_result(reader(locale))
    else:
        data = await read_visible_labels(request.app.state.db_engine, locale)
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/labels")
@router.get("/api/web/skills/{namespace}/{slug}/labels")
async def list_skill_labels(namespace: str, slug: str, request: Request) -> dict[str, object]:
    locale = requested_locale(request)
    reader = getattr(request.app.state, "skill_label_reader", None)
    if reader is not None:
        data = await _resolve_reader_result(reader(namespace, slug, locale))
    else:
        data = await read_skill_labels(request.app.state.db_engine, namespace, slug, locale)
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.put("/api/v1/skills/{namespace}/{slug}/labels/{label_slug}")
@router.put("/api/web/skills/{namespace}/{slug}/labels/{label_slug}")
async def attach_skill_label_route(
    namespace: str,
    slug: str,
    label_slug: str,
    request: Request,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    user = await _read_current_user(request, x_mock_user_id)
    meta = _request_meta(request)
    writer = getattr(request.app.state, "skill_label_attach_writer", None)
    try:
        data = await _resolve_reader_result(
            writer(namespace, slug, label_slug, user, meta)
            if writer is not None
            else attach_skill_label(
                request.app.state.db_engine,
                namespace=namespace,
                slug=slug,
                label_slug=label_slug,
                actor_user_id=_user_id(user),
                platform_roles=_roles(user),
                request_id=meta["request_id"],
                client_ip=meta["client_ip"],
                user_agent=meta["user_agent"],
            )
        )
    except SkillLabelMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.delete("/api/v1/skills/{namespace}/{slug}/labels/{label_slug}")
@router.delete("/api/web/skills/{namespace}/{slug}/labels/{label_slug}")
async def detach_skill_label_route(
    namespace: str,
    slug: str,
    label_slug: str,
    request: Request,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    user = await _read_current_user(request, x_mock_user_id)
    meta = _request_meta(request)
    writer = getattr(request.app.state, "skill_label_detach_writer", None)
    try:
        data = await _resolve_reader_result(
            writer(namespace, slug, label_slug, user, meta)
            if writer is not None
            else detach_skill_label(
                request.app.state.db_engine,
                namespace=namespace,
                slug=slug,
                label_slug=label_slug,
                actor_user_id=_user_id(user),
                platform_roles=_roles(user),
                request_id=meta["request_id"],
                client_ip=meta["client_ip"],
                user_agent=meta["user_agent"],
            )
        )
    except SkillLabelMutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u5220\u9664\u6210\u529f", data, request)
