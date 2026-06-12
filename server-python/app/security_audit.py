from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.api.skills import to_java_instant
from app.auth.policy import is_namespace_manager, is_namespace_member


SCANNER_TYPE_API_TO_DB = {
    "skill-scanner": "SKILL_SCANNER",
    "custom": "CUSTOM",
}
SCANNER_TYPE_DB_TO_API = {value: key for key, value in SCANNER_TYPE_API_TO_DB.items()}


class SecurityAuditReadError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _normalize_scanner_type(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    normalized = value.strip()
    if normalized not in SCANNER_TYPE_API_TO_DB:
        raise SecurityAuditReadError(f"Unknown scanner type: {normalized}", status_code=400)
    return SCANNER_TYPE_API_TO_DB[normalized]


def _scanner_type_response(value: Any) -> str:
    text_value = str(value)
    return SCANNER_TYPE_DB_TO_API.get(text_value, text_value)


def _json_findings(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    parsed = value
    if isinstance(value, str):
        if value.strip() == "":
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(parsed, list):
        return []
    return [item if isinstance(item, dict) else {} for item in parsed]


async def _read_version(connection: Any, version_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, skill_id
                FROM skill_version
                WHERE id = :version_id
                LIMIT 1
                """
            ),
            {"version_id": version_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SecurityAuditReadError("error.skill.version.notFound", status_code=400)
    return dict(row)


async def _read_skill(connection: Any, skill_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id,
                       s.owner_id,
                       s.namespace_id,
                       s.visibility,
                       s.latest_version_id,
                       COALESCE(s.hidden, FALSE) AS hidden
                FROM skill s
                WHERE s.id = :skill_id
                LIMIT 1
                """
            ),
            {"skill_id": skill_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SecurityAuditReadError("error.skill.notFound", status_code=400)
    return dict(row)


async def _read_namespace_role(connection: Any, namespace_id: int, current_user_id: str | None) -> str | None:
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


def _is_admin_or_owner(role: str | None) -> bool:
    return is_namespace_manager(role)


def _can_view_audit(
    skill: dict[str, Any],
    *,
    current_user_id: str | None,
    namespace_role: str | None,
    platform_roles: list[str],
) -> bool:
    roles = {str(role) for role in platform_roles}
    if roles.intersection({"SUPER_ADMIN", "SKILL_ADMIN"}):
        return True
    if _is_admin_or_owner(namespace_role):
        return True
    if current_user_id is None:
        return False
    if bool(skill.get("hidden")):
        return str(skill["owner_id"]) == str(current_user_id) or _is_admin_or_owner(namespace_role)
    if skill.get("latest_version_id") is None:
        return str(skill["owner_id"]) == str(current_user_id)
    visibility = str(skill.get("visibility"))
    if visibility == "PUBLIC":
        return True
    if visibility == "NAMESPACE_ONLY":
        return is_namespace_member(namespace_role)
    if visibility == "PRIVATE":
        return str(skill["owner_id"]) == str(current_user_id) or _is_admin_or_owner(namespace_role)
    return False


def _audit_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "scanId": row.get("scan_id"),
        "scannerType": _scanner_type_response(row.get("scanner_type")),
        "verdict": row.get("verdict"),
        "isSafe": bool(row["is_safe"]),
        "maxSeverity": row.get("max_severity"),
        "findingsCount": int(row.get("findings_count") or 0),
        "findings": _json_findings(row.get("findings")),
        "scanDurationSeconds": float(row["scan_duration_seconds"]) if row.get("scan_duration_seconds") is not None else None,
        "scannedAt": to_java_instant(row.get("scanned_at")),
        "createdAt": to_java_instant(row.get("created_at")),
    }


async def _read_latest_security_audits(
    connection: Any,
    *,
    version_id: int,
    scanner_type: str | None,
) -> list[dict[str, Any]]:
    if scanner_type is not None:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, skill_version_id, scan_id, scanner_type, verdict, is_safe,
                           max_severity, findings_count, findings, scan_duration_seconds,
                           scanned_at, created_at
                    FROM security_audit
                    WHERE skill_version_id = :version_id
                      AND scanner_type = :scanner_type
                      AND deleted_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"version_id": version_id, "scanner_type": scanner_type},
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    rows = (
        await connection.execute(
            text(
                """
                SELECT DISTINCT ON (scanner_type)
                       id, skill_version_id, scan_id, scanner_type, verdict, is_safe,
                       max_severity, findings_count, findings, scan_duration_seconds,
                       scanned_at, created_at
                FROM security_audit
                WHERE skill_version_id = :version_id
                  AND deleted_at IS NULL
                ORDER BY scanner_type ASC, created_at DESC
                """
            ),
            {"version_id": version_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def list_security_audits(
    engine: Any,
    *,
    skill_id: int,
    version_id: int,
    scanner_type: str | None,
    current_user_id: str | None,
    platform_roles: list[str],
) -> list[dict[str, Any]]:
    normalized_scanner_type = _normalize_scanner_type(scanner_type)
    async with engine.connect() as connection:
        version = await _read_version(connection, version_id)
        if int(version["skill_id"]) != int(skill_id):
            raise SecurityAuditReadError("error.skill.version.notFound", status_code=400)

        skill = await _read_skill(connection, skill_id)
        namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), current_user_id)
        if not _can_view_audit(
            skill,
            current_user_id=current_user_id,
            namespace_role=namespace_role,
            platform_roles=platform_roles,
        ):
            raise SecurityAuditReadError("error.forbidden", status_code=403)

        rows = await _read_latest_security_audits(
            connection,
            version_id=version_id,
            scanner_type=normalized_scanner_type,
        )
    return [_audit_response(row) for row in rows]
