from collections import defaultdict
from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.response import ok

router = APIRouter()

LabelRow = dict[str, Any]
TranslationRow = dict[str, Any]


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
