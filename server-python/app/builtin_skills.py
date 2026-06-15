from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import text

from app.object_storage import object_storage_for_settings
from app.publish.dry_run import slugify
from app.publish.orchestration import PublishWriteInput, execute_publish_write
from app.publish.package import PackageEntry, extract_package_with_warnings, parse_skill_metadata, validate_package

GLOBAL_NAMESPACE = "global"
SYSTEM_PUBLISHER_ID = "builtin-skill-publisher"
SYSTEM_PUBLISHER_NAME = "Built-in Skill Publisher"
ALLOWED_BUILTIN_SKILL_HOST = "bjcdn.openstorage.cn"
MAX_MANIFEST_ITEMS = 100
DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parent / "builtin_skills" / "manifest.json"
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")


@dataclass(frozen=True)
class BuiltinSkillConfig:
    enabled: bool = True
    manifest_path: Path = DEFAULT_MANIFEST_PATH


@dataclass(frozen=True)
class BuiltinSkillManifestItem:
    slug: str
    version: str
    url: str


@dataclass(frozen=True)
class BuiltinSkillSyncSummary:
    total: int = 0
    published: int = 0
    idempotent_skipped: int = 0
    conflict_skipped: int = 0
    failed: int = 0


Publisher = Callable[[BuiltinSkillManifestItem, list[PackageEntry]], Any]
Downloader = Callable[[str], bytes | None]


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def builtin_skill_config(environ: dict[str, str] | None = None) -> BuiltinSkillConfig:
    env = os.environ if environ is None else environ
    manifest_path = env.get("SKILLHUB_BUILTIN_SKILLS_MANIFEST_PATH")
    return BuiltinSkillConfig(
        enabled=_parse_bool(env.get("SKILLHUB_BUILTIN_SKILLS_ENABLED"), True),
        manifest_path=Path(manifest_path) if manifest_path else DEFAULT_MANIFEST_PATH,
    )


def load_builtin_skill_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> list[BuiltinSkillManifestItem]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    skills = payload.get("skills") if isinstance(payload, dict) else None
    if not isinstance(skills, list):
        return []

    items: list[BuiltinSkillManifestItem] = []
    seen: set[tuple[str, str]] = set()
    for raw in skills[:MAX_MANIFEST_ITEMS]:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug") or "").strip()
        version = str(raw.get("version") or "").strip()
        url = str(raw.get("url") or "").strip()
        if not slug or not version or not url:
            continue
        if SLUG_PATTERN.fullmatch(slug) is None:
            continue
        key = (slug, version)
        if key in seen:
            continue
        seen.add(key)
        items.append(BuiltinSkillManifestItem(slug=slug, version=version, url=url))
    return items


def is_allowed_builtin_skill_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme.lower() != "https":
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.port not in {None, 443}:
        return False
    host = (parsed.hostname or "").lower()
    if not host or host == "localhost" or ":" in host:
        return False
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host):
        return False
    return host == ALLOWED_BUILTIN_SKILL_HOST or host.endswith(f".{ALLOWED_BUILTIN_SKILL_HOST}")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _http_get_no_redirect(url: str, timeout_seconds: int, max_size: int) -> tuple[int, bytes]:
    request = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", response.getcode()))
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size:
                    return status, b""
                chunks.append(chunk)
            return status, b"".join(chunks)
    except urllib.error.HTTPError as exc:
        return int(exc.code), b""


def download_builtin_skill_package(
    url: str,
    *,
    max_package_size: int,
    timeout_seconds: int = 30,
    http_get: Callable[[str, int, int], tuple[int, bytes]] = _http_get_no_redirect,
) -> bytes | None:
    if not is_allowed_builtin_skill_url(url):
        return None
    try:
        status, body = http_get(url, timeout_seconds, max_package_size)
    except OSError:
        return None
    if status != 200 or not body or len(body) > max_package_size:
        return None
    return body


def extract_builtin_skill_package(zip_bytes: bytes) -> list[PackageEntry]:
    entries, warnings = extract_package_with_warnings(zip_bytes)
    if warnings:
        raise ValueError(f"Built-in skill package has warnings: {'; '.join(warnings)}")
    validation = validate_package(entries)
    if not validation.valid or validation.warnings:
        messages = validation.errors + validation.warnings
        raise ValueError(f"Built-in skill package is invalid: {'; '.join(messages)}")
    return entries


async def _read_global_namespace_id(connection: Any) -> int | None:
    row = (
        await connection.execute(
            text("SELECT id FROM namespace WHERE slug = :slug LIMIT 1"),
            {"slug": GLOBAL_NAMESPACE},
        )
    ).mappings().one_or_none()
    return int(row["id"]) if row is not None else None


async def _ensure_system_publisher(connection: Any, namespace_id: int) -> bool:
    user = (
        await connection.execute(
            text("SELECT id, system_account FROM user_account WHERE id = :user_id LIMIT 1"),
            {"user_id": SYSTEM_PUBLISHER_ID},
        )
    ).mappings().one_or_none()
    if user is not None and not bool(user.get("system_account")):
        return False
    if user is None:
        await connection.execute(
            text(
                """
                INSERT INTO user_account (id, display_name, email, avatar_url, status, system_account)
                VALUES (:id, :display_name, NULL, NULL, 'ACTIVE', TRUE)
                """
            ),
            {"id": SYSTEM_PUBLISHER_ID, "display_name": SYSTEM_PUBLISHER_NAME},
        )

    member = (
        await connection.execute(
            text(
                """
                SELECT id
                FROM namespace_member
                WHERE namespace_id = :namespace_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {"namespace_id": namespace_id, "user_id": SYSTEM_PUBLISHER_ID},
        )
    ).mappings().one_or_none()
    if member is None:
        await connection.execute(
            text(
                """
                INSERT INTO namespace_member (namespace_id, user_id, role)
                VALUES (:namespace_id, :user_id, 'OWNER')
                """
            ),
            {"namespace_id": namespace_id, "user_id": SYSTEM_PUBLISHER_ID},
        )
    return True


async def _existing_builtin_state(connection: Any, namespace_id: int, item: BuiltinSkillManifestItem) -> str | None:
    skill_rows = (
        await connection.execute(
            text(
                """
                SELECT id, owner_id
                FROM skill
                WHERE namespace_id = :namespace_id
                  AND slug = :slug
                """
            ),
            {"namespace_id": namespace_id, "slug": item.slug},
        )
    ).mappings().all()
    if any(str(row["owner_id"]) != SYSTEM_PUBLISHER_ID for row in skill_rows):
        return "conflict"

    builtin_skill = next((row for row in skill_rows if str(row["owner_id"]) == SYSTEM_PUBLISHER_ID), None)
    if builtin_skill is None:
        return None

    version = (
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
            {"skill_id": int(builtin_skill["id"]), "version": item.version},
        )
    ).mappings().one_or_none()
    return "exists" if version is not None else None


async def _default_publisher(engine: Any, settings: Any, namespace_id: int, item: BuiltinSkillManifestItem, entries: list[PackageEntry]) -> None:
    skill_md = next(entry for entry in entries if entry.path == "SKILL.md")
    metadata = parse_skill_metadata(skill_md.content)
    await execute_publish_write(
        engine,
        PublishWriteInput(
            namespace_id=namespace_id,
            namespace_slug=GLOBAL_NAMESPACE,
            slug=item.slug,
            display_name=metadata.name,
            summary=metadata.description,
            publisher_id=SYSTEM_PUBLISHER_ID,
            visibility="PUBLIC",
            version=item.version,
            auto_publish=True,
            metadata=metadata,
            entries=entries,
            storage_base_path=settings.storage_base_path,
            storage=object_storage_for_settings(settings),
            scanner_enabled=False,
            scan_mode="upload",
        ),
    )


async def synchronize_builtin_skills(
    engine: Any,
    settings: Any,
    *,
    environ: dict[str, str] | None = None,
    downloader: Downloader | None = None,
    publisher: Publisher | None = None,
) -> BuiltinSkillSyncSummary:
    config = builtin_skill_config(environ)
    if not config.enabled:
        return BuiltinSkillSyncSummary()

    items = load_builtin_skill_manifest(config.manifest_path)
    if not items:
        return BuiltinSkillSyncSummary()

    async with engine.begin() as connection:
        namespace_id = await _read_global_namespace_id(connection)
        if namespace_id is None:
            return BuiltinSkillSyncSummary(total=len(items), failed=len(items))
        if not await _ensure_system_publisher(connection, namespace_id):
            return BuiltinSkillSyncSummary(total=len(items), failed=len(items))

    published = 0
    idempotent_skipped = 0
    conflict_skipped = 0
    failed = 0
    active_downloader = downloader or (
        lambda url: download_builtin_skill_package(
            url,
            max_package_size=getattr(settings, "publish_max_package_size", 100 * 1024 * 1024),
        )
    )

    for item in items:
        async with engine.begin() as connection:
            state = await _existing_builtin_state(connection, namespace_id, item)
        if state == "conflict":
            conflict_skipped += 1
            continue
        if state == "exists":
            idempotent_skipped += 1
            continue

        package_bytes = active_downloader(item.url)
        if package_bytes is None:
            failed += 1
            continue
        try:
            entries = extract_builtin_skill_package(package_bytes)
            skill_md = next(entry for entry in entries if entry.path == "SKILL.md")
            metadata = parse_skill_metadata(skill_md.content)
            if slugify(metadata.name) != item.slug or metadata.version != item.version:
                failed += 1
                continue
            if publisher is None:
                await _default_publisher(engine, settings, namespace_id, item, entries)
            else:
                result = publisher(item, entries)
                if hasattr(result, "__await__"):
                    await result
            published += 1
        except Exception:
            failed += 1

    return BuiltinSkillSyncSummary(
        total=len(items),
        published=published,
        idempotent_skipped=idempotent_skipped,
        conflict_skipped=conflict_skipped,
        failed=failed,
    )
