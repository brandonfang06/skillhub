from __future__ import annotations

import json
from typing import Any

from app.skills.compliance_contract import ComplianceSnapshotResponse


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    return ""


def _evidence_response(raw_evidence: Any) -> list[dict[str, str | None]]:
    if not isinstance(raw_evidence, list):
        return []
    return [
        {
            "type": _text_or_none(item.get("type")),
            "path": _text_or_none(item.get("path")),
            "url": _text_or_none(item.get("url")),
            "sha256": _text_or_none(item.get("sha256")),
        }
        for item in raw_evidence
        if isinstance(item, dict)
    ]


def compliance_snapshot_from_value(
    raw_snapshot: Any,
) -> dict[str, Any] | None:
    try:
        snapshot = (
            json.loads(raw_snapshot) if isinstance(raw_snapshot, str) else raw_snapshot
        )
    except (TypeError, ValueError):
        return None
    if not isinstance(snapshot, dict):
        return None
    raw_items = snapshot.get("items")
    items: list[dict[str, Any]] = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "standard": _text_or_none(item.get("standard")),
                    "version": _text_or_none(item.get("version")),
                    "controlId": _text_or_none(item.get("controlId")),
                    "title": _text_or_none(item.get("title")),
                    "evidence": _evidence_response(item.get("evidence")),
                }
            )
    return ComplianceSnapshotResponse.model_validate(
        {
            "schemaVersion": _text_or_none(snapshot.get("schemaVersion")),
            "items": items,
            "digest": _text_or_none(snapshot.get("digest")),
        }
    ).model_dump(mode="json", by_alias=True)


def compliance_snapshot_from_parsed_metadata(
    parsed_metadata_json: Any,
) -> dict[str, Any] | None:
    if parsed_metadata_json is None:
        return None
    try:
        metadata = (
            json.loads(parsed_metadata_json)
            if isinstance(parsed_metadata_json, str)
            else parsed_metadata_json
        )
    except (TypeError, ValueError):
        return None
    if not isinstance(metadata, dict):
        return None
    return compliance_snapshot_from_value(metadata.get("complianceSnapshot"))


__all__ = [
    "compliance_snapshot_from_parsed_metadata",
    "compliance_snapshot_from_value",
]
