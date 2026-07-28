from __future__ import annotations

import re
import unicodedata
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Protocol

from sqlalchemy import text

from app.publish.package import PackageEntry, validate_package


REJECTED_VERSION_REUSE_ERROR = "error.skill.publish.rejectedVersionReuse"
RESERVED_SLUGS = {
    "admin",
    "api",
    "dashboard",
    "search",
    "auth",
    "me",
    "global",
    "system",
    "static",
    "assets",
    "health",
}
SECRET_RULES = (
    (re.compile(r"(AKIA[0-9A-Z]{16})"), 1, "cloud access key"),
    (re.compile(r"(ghp_[A-Za-z0-9]{20,})"), 1, "GitHub token"),
    (re.compile(r"(sk-[A-Za-z0-9]{20,})"), 1, "API key"),
    (
        re.compile(r"(?i)(api[_-]?key|access[_-]?key|secret|password|token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{12,})"),
        2,
        "secret or token",
    ),
)
PLACEHOLDER_VALUE = re.compile(r"(?i).*(your|example|sample|placeholder|changeme|replace|dummy|mock|test|fake|todo|xxx|redacted).*")
PRE_PUBLISH_TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".js",
    ".ts",
    ".py",
    ".sh",
    ".svg",
    ".html",
    ".css",
    ".csv",
    ".toml",
    ".xml",
    ".ini",
    ".cfg",
    ".env",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".lua",
    ".sql",
    ".r",
    ".bat",
    ".ps1",
    ".zsh",
    ".bash",
}


@dataclass(frozen=True)
class PublishNamespaceContext:
    namespace_id: int
    status: str
    publisher_is_member: bool
    is_super_admin: bool


@dataclass(frozen=True)
class PublishConflictContext:
    own_skill_status: str | None = None
    own_version_status: str | None = None
    other_owner_has_published: bool = False


@dataclass(frozen=True)
class PublishDryRunInput:
    namespace_slug: str
    entries: list[PackageEntry]
    publisher_id: str
    visibility: str
    platform_roles: set[str] = field(default_factory=set)
    now: datetime | None = None
    allowed_extensions: AbstractSet[str] | None = None


@dataclass(frozen=True)
class PublishDryRunResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
    resolved_slug: str | None
    resolved_version: str | None


class DryRunRepository(Protocol):
    async def read_namespace_context(
        self,
        namespace_slug: str,
        publisher_id: str,
        platform_roles: set[str],
    ) -> PublishNamespaceContext | None:
        ...

    async def read_publish_conflicts(
        self,
        namespace_id: int,
        skill_slug: str,
        publisher_id: str,
        resolved_version: str,
    ) -> PublishConflictContext:
        ...


class PublishDryRunRepository:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    async def read_namespace_context(
        self,
        namespace_slug: str,
        publisher_id: str,
        platform_roles: set[str],
    ) -> PublishNamespaceContext | None:
        is_super_admin = "SUPER_ADMIN" in platform_roles
        async with self.engine.connect() as connection:
            namespace_row = (
                await connection.execute(
                    text(
                        """
                        SELECT id, status
                        FROM namespace
                        WHERE slug = :namespace_slug
                        LIMIT 1
                        """
                    ),
                    {"namespace_slug": namespace_slug},
                )
            ).mappings().one_or_none()

            if namespace_row is None:
                return None

            publisher_is_member = False
            if not is_super_admin:
                member_role = (
                    await connection.execute(
                        text(
                            """
                            SELECT role
                            FROM namespace_member
                            WHERE namespace_id = :namespace_id
                              AND user_id = :publisher_id
                            LIMIT 1
                            """
                        ),
                        {"namespace_id": namespace_row["id"], "publisher_id": publisher_id},
                    )
                ).scalar_one_or_none()
                publisher_is_member = member_role is not None

        return PublishNamespaceContext(
            namespace_id=int(namespace_row["id"]),
            status=str(namespace_row["status"]),
            publisher_is_member=publisher_is_member,
            is_super_admin=is_super_admin,
        )

    async def read_publish_conflicts(
        self,
        namespace_id: int,
        skill_slug: str,
        publisher_id: str,
        resolved_version: str,
    ) -> PublishConflictContext:
        async with self.engine.connect() as connection:
            own_skill = (
                await connection.execute(
                    text(
                        """
                        SELECT id, status
                        FROM skill
                        WHERE namespace_id = :namespace_id
                          AND slug = :skill_slug
                          AND owner_id = :publisher_id
                        LIMIT 1
                        """
                    ),
                    {"namespace_id": namespace_id, "skill_slug": skill_slug, "publisher_id": publisher_id},
                )
            ).mappings().one_or_none()

            own_skill_status = None
            own_version_status = None
            if own_skill is not None:
                own_skill_status = str(own_skill["status"])
                own_version_status = (
                    await connection.execute(
                        text(
                            """
                            SELECT status
                            FROM skill_version
                            WHERE skill_id = :skill_id
                              AND version = :resolved_version
                            LIMIT 1
                            """
                        ),
                        {"skill_id": own_skill["id"], "resolved_version": resolved_version},
                    )
                ).scalar_one_or_none()
                if own_version_status is not None:
                    own_version_status = str(own_version_status)

            other_owner_has_published = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT EXISTS (
                                SELECT 1
                                FROM skill s
                                JOIN skill_version sv ON sv.skill_id = s.id
                                WHERE s.namespace_id = :namespace_id
                                  AND s.slug = :skill_slug
                                  AND s.owner_id <> :publisher_id
                                  AND sv.status = 'PUBLISHED'
                            )
                            """
                        ),
                        {"namespace_id": namespace_id, "skill_slug": skill_slug, "publisher_id": publisher_id},
                    )
                ).scalar_one_or_none()
            )

        return PublishConflictContext(
            own_skill_status=own_skill_status,
            own_version_status=own_version_status,
            other_owner_has_published=other_owner_has_published,
        )


async def validate_publish_dry_run(
    request: PublishDryRunInput,
    repository: DryRunRepository,
) -> PublishDryRunResult:
    errors: list[str] = []
    warnings: list[str] = []
    resolved_slug: str | None = None
    resolved_version: str | None = None

    namespace = await repository.read_namespace_context(
        request.namespace_slug,
        request.publisher_id,
        request.platform_roles,
    )
    if namespace is None:
        return PublishDryRunResult(
            valid=False,
            errors=[f"Namespace not found: {request.namespace_slug}"],
            warnings=[],
            resolved_slug=None,
            resolved_version=None,
        )

    if namespace.status == "FROZEN":
        errors.append(f"Namespace is frozen: {request.namespace_slug}")
    if namespace.status == "ARCHIVED":
        errors.append(f"Namespace is archived: {request.namespace_slug}")
    if not namespace.is_super_admin and not namespace.publisher_is_member:
        errors.append(f"Publisher is not a member of namespace: {request.namespace_slug}")

    package_validation = validate_package(request.entries, allowed_extensions=request.allowed_extensions)
    errors.extend(package_validation.errors)
    warnings.extend(package_validation.warnings)
    if not package_validation.valid:
        return PublishDryRunResult(False, errors, warnings, None, None)

    metadata = package_validation.metadata
    if metadata is None:
        errors.append("Missing required file: SKILL.md at root")
        return PublishDryRunResult(False, errors, warnings, None, None)

    resolved_version = metadata.version if metadata.version else auto_version(request.now)
    try:
        resolved_slug = slugify(metadata.name)
    except ValueError as exc:
        errors.append(f"Invalid skill name for slug generation: {exc}")
        return PublishDryRunResult(False, errors, warnings, resolved_slug, resolved_version)

    warnings.extend(scan_pre_publish_warnings(request.entries))

    if resolved_slug is not None and not errors:
        conflicts = await repository.read_publish_conflicts(
            namespace.namespace_id,
            resolved_slug,
            request.publisher_id,
            resolved_version,
        )
        if conflicts.own_skill_status == "ARCHIVED":
            errors.append(f"Cannot publish to archived skill: {resolved_slug}")
        if conflicts.own_version_status == "PUBLISHED":
            errors.append(f"Version already published: {resolved_version}")
        if conflicts.own_version_status == "REJECTED":
            errors.append(REJECTED_VERSION_REUSE_ERROR)
        if conflicts.other_owner_has_published:
            errors.append(f'Name conflict: slug "{resolved_slug}" is already published by another user')

    return PublishDryRunResult(
        valid=not errors and not warnings,
        errors=errors,
        warnings=warnings,
        resolved_slug=resolved_slug,
        resolved_version=resolved_version,
    )


def auto_version(now: datetime | None) -> str:
    instant = now or datetime.now(tz=UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(UTC).strftime("%Y%m%d%H%M%S")


def slugify(raw: str | None) -> str:
    if raw is None:
        raise ValueError("error.slug.blank")
    parts: list[str] = []
    previous_dash = False
    for char in raw.strip().lower():
        if is_java_slug_character(char):
            parts.append(char)
            previous_dash = False
        elif not previous_dash:
            parts.append("-")
            previous_dash = True
    slug = "".join(parts).strip("-")
    validate_slug(slug)
    return slug


def is_java_slug_character(char: str) -> bool:
    category = unicodedata.category(char)
    return category[0] in {"L", "N"} or category == "So"


def validate_slug(slug: str) -> None:
    if not slug:
        raise ValueError("error.slug.blank")
    if len(slug) < 2 or len(slug) > 64:
        raise ValueError("error.slug.length")
    if re.search(r"[A-Z]", slug):
        raise ValueError("error.slug.pattern")
    if (
        not is_java_slug_character(slug[0])
        or not is_java_slug_character(slug[-1])
        or any(char != "-" and not is_java_slug_character(char) for char in slug)
    ):
        raise ValueError("error.slug.pattern")
    if "--" in slug:
        raise ValueError("error.slug.doubleHyphen")
    if slug in RESERVED_SLUGS:
        raise ValueError(f"error.slug.reserved: {slug}")


def scan_pre_publish_warnings(entries: list[PackageEntry]) -> list[str]:
    warnings: list[str] = []
    for entry in entries:
        if PurePosixPath(entry.path).suffix.lower() not in PRE_PUBLISH_TEXT_EXTENSIONS:
            continue
        try:
            content = entry.content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        lines = content.splitlines()
        if content.endswith(("\n", "\r")):
            lines.append("")
        for index, line in enumerate(lines, start=1):
            for pattern, group_index, label in SECRET_RULES:
                match = pattern.search(line)
                if match is None:
                    continue
                matched_value = match.group(group_index)
                if is_placeholder_value(matched_value):
                    continue
                warnings.append(
                    f"{entry.path} line {index} contains a value that looks like a {label}. "
                    "Replace real credentials with placeholders before publishing."
                )
                break
    return warnings


def is_placeholder_value(value: str | None) -> bool:
    if value is None or value.strip() == "":
        return False
    return bool(PLACEHOLDER_VALUE.match(value)) or all(ch in {"x", "X", "*", "-"} for ch in value)
