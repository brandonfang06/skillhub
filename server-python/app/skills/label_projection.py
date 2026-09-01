from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class SkillIncludeError(ValueError):
    def __init__(self, option: str) -> None:
        super().__init__("error.request.include.unsupported")
        self.option = option


def includes_skill_labels(values: list[str] | None) -> bool:
    if not values:
        return False

    requested = False
    for value in values:
        for raw_option in value.split(","):
            option = raw_option.strip().lower()
            if not option:
                continue
            if option != "labels":
                raise SkillIncludeError(option)
            requested = True
    return requested


def requested_locale(accept_language: str | None) -> str | None:
    if not accept_language:
        return None
    return accept_language.split(",", 1)[0].strip() or None


def _normalize_locale(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().replace("_", "-").lower()


def _resolve_display_name(
    slug: str,
    translations: list[dict[str, str]],
    locale: str | None,
) -> str:
    values: dict[str, str] = {}
    for translation in translations:
        normalized = _normalize_locale(translation["locale"])
        values.setdefault(normalized, translation["display_name"])

    normalized_locale = _normalize_locale(locale)
    language = normalized_locale.split("-", 1)[0] if normalized_locale else ""
    for candidate in (normalized_locale, language, "en"):
        value = values.get(candidate)
        if value and value.strip():
            return value
    return slug


async def read_skill_label_projection(
    engine: AsyncEngine,
    *,
    skill_ids: list[int],
    locale: str | None,
) -> dict[int, list[dict[str, str]]]:
    distinct_skill_ids = list(dict.fromkeys(skill_ids))
    if not distinct_skill_ids:
        return {}

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT sl.skill_id,
                           ld.id AS label_id,
                           ld.slug,
                           ld.type,
                           lt.locale,
                           lt.display_name
                    FROM skill_label sl
                    JOIN label_definition ld ON ld.id = sl.label_id
                    LEFT JOIN label_translation lt ON lt.label_id = ld.id
                    WHERE sl.skill_id = ANY(CAST(:skill_ids AS bigint[]))
                    ORDER BY sl.skill_id, ld.type, ld.slug, lt.locale
                    """
                ),
                {"skill_ids": distinct_skill_ids},
            )
        ).mappings().all()

    labels: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        skill_id = int(row["skill_id"])
        label_id = int(row["label_id"])
        label = labels[skill_id].setdefault(
            label_id,
            {
                "slug": str(row["slug"]),
                "type": str(row["type"]),
                "translations": [],
            },
        )
        if row["locale"] is not None and row["display_name"] is not None:
            label["translations"].append(
                {
                    "locale": str(row["locale"]),
                    "display_name": str(row["display_name"]),
                }
            )

    return {
        skill_id: [
            {
                "slug": str(label["slug"]),
                "type": str(label["type"]),
                "displayName": _resolve_display_name(
                    str(label["slug"]),
                    label["translations"],
                    locale,
                ),
            }
            for label in skill_labels.values()
        ]
        for skill_id, skill_labels in labels.items()
    }


__all__ = [
    "SkillIncludeError",
    "includes_skill_labels",
    "read_skill_label_projection",
    "requested_locale",
]
