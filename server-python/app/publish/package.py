from __future__ import annotations

import posixpath
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile

import yaml

from app.publish.java_compat import java_trim


@dataclass(frozen=True)
class PackageEntry:
    path: str
    content: bytes
    content_type: str

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class PackageLimits:
    max_file_count: int = 500
    max_single_file_size: int = 10 * 1024 * 1024
    max_total_size: int = 100 * 1024 * 1024


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    version: str | None = None
    frontmatter: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
    metadata: SkillMetadata | None = None


CONTENT_TYPES_BY_EXTENSION = {
    ".py": "text/x-python",
    ".json": "application/json",
    ".yaml": "application/x-yaml",
    ".yml": "application/x-yaml",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".css": "text/css",
    ".csv": "text/csv",
    ".xml": "application/xml",
    ".xsd": "application/xml",
    ".xsl": "application/xml",
    ".dtd": "application/xml-dtd",
    ".ini": "text/plain",
    ".cfg": "text/plain",
    ".env": "text/plain",
    ".js": "text/javascript",
    ".cjs": "text/javascript",
    ".mjs": "text/javascript",
    ".ts": "text/typescript",
    ".rb": "text/plain",
    ".go": "text/plain",
    ".rs": "text/plain",
    ".java": "text/plain",
    ".kt": "text/plain",
    ".lua": "text/plain",
    ".sql": "text/plain",
    ".r": "text/plain",
    ".sh": "text/x-shellscript",
    ".bash": "text/x-shellscript",
    ".zsh": "text/x-shellscript",
    ".bat": "text/plain",
    ".ps1": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".pdf": "application/pdf",
    ".toml": "application/toml",
    ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel",
    ".ppt": "application/vnd.ms-powerpoint",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

ALLOWED_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".html",
    ".css",
    ".csv",
    ".pdf",
    ".js",
    ".cjs",
    ".mjs",
    ".ts",
    ".py",
    ".sh",
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
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".gif",
    ".webp",
    ".ico",
    ".toml",
    ".xml",
    ".xsd",
    ".xsl",
    ".dtd",
    ".ini",
    ".cfg",
    ".env",
    ".doc",
    ".xls",
    ".ppt",
    ".docx",
    ".xlsx",
    ".pptx",
}

TEXT_LIKE_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".js",
    ".cjs",
    ".mjs",
    ".ts",
    ".py",
    ".sh",
    ".html",
    ".css",
    ".csv",
    ".toml",
    ".xml",
    ".xsd",
    ".xsl",
    ".dtd",
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


def package_extension(path: str) -> str:
    posix_path = PurePosixPath(path)
    suffix = posix_path.suffix.lower()
    if suffix:
        return suffix
    name = posix_path.name.lower()
    if name.startswith(".") and name.count(".") == 1:
        return name
    return ""


def determine_content_type(path: str) -> str:
    return CONTENT_TYPES_BY_EXTENSION.get(package_extension(path), "application/octet-stream")


def normalize_allowed_extensions(allowed_extensions: AbstractSet[str] | None) -> set[str] | None:
    if allowed_extensions is None:
        return None
    normalized = set()
    for extension in allowed_extensions:
        value = extension.strip().lower()
        if not value:
            continue
        if not value.startswith("."):
            value = f".{value}"
        normalized.add(value)
    return normalized


def canonicalize_skill_md_path(normalized_path: str) -> str:
    prefix, separator, filename = normalized_path.rpartition("/")
    if filename.lower() != "skill.md":
        return normalized_path
    if not separator:
        return "SKILL.md"
    return f"{prefix}/SKILL.md"


def normalize_entry_path(raw_path: str) -> str:
    sanitized = java_trim(raw_path.replace("\\", "/"))
    if not sanitized:
        raise ValueError("Path must not be blank")
    if sanitized.startswith("/"):
        raise ValueError(f"Absolute paths are not allowed: {raw_path}")
    if ":" in sanitized:
        raise ValueError(f"Drive-qualified paths are not allowed: {raw_path}")

    canonical = posixpath.normpath(sanitized)
    if canonical in {"", ".", ".."} or canonical.startswith("../"):
        raise ValueError(f"Parent directory paths are not allowed: {raw_path}")
    if sanitized != canonical:
        raise ValueError(f"Path must be normalized: {raw_path}")
    return canonicalize_skill_md_path(canonical)


def is_os_metadata_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip()
    basename = PurePosixPath(normalized).name
    return normalized.startswith("__MACOSX/") or basename == ".DS_Store" or basename.startswith("._")


def strip_single_root_directory(entries: list[PackageEntry]) -> list[PackageEntry]:
    if not entries:
        return entries

    roots = set()
    for entry in entries:
        if "/" not in entry.path:
            return entries
        roots.add(entry.path.split("/", 1)[0])

    if len(roots) != 1:
        return entries

    root = next(iter(roots))
    prefix = f"{root}/"
    return [
        PackageEntry(entry.path.removeprefix(prefix), entry.content, entry.content_type)
        for entry in entries
    ]


def extract_package(zip_bytes: bytes, limits: PackageLimits | None = None) -> list[PackageEntry]:
    active_limits = limits or PackageLimits()
    if len(zip_bytes) > active_limits.max_total_size:
        raise ValueError(f"Package too large: {len(zip_bytes)} bytes (max: {active_limits.max_total_size})")

    entries: list[PackageEntry] = []
    total_size = 0
    try:
        with ZipFile(BytesIO(zip_bytes)) as archive:
            for info in archive.infolist():
                if info.is_dir() or is_os_metadata_path(info.filename):
                    continue
                if len(entries) >= active_limits.max_file_count:
                    raise ValueError(f"Too many files: more than {active_limits.max_file_count}")

                path = normalize_entry_path(info.filename)
                content = archive.read(info)
                if len(content) > active_limits.max_single_file_size:
                    raise ValueError(
                        f"File too large: {path} ({len(content)} bytes, max: {active_limits.max_single_file_size})"
                    )
                total_size += len(content)
                if total_size > active_limits.max_total_size:
                    raise ValueError(f"Package too large: {total_size} bytes (max: {active_limits.max_total_size})")

                entries.append(PackageEntry(path, content, determine_content_type(path)))
    except BadZipFile as exc:
        raise ValueError("Invalid zip package") from exc

    return strip_single_root_directory(entries)


def extract_package_with_warnings(
    zip_bytes: bytes,
    limits: PackageLimits | None = None,
) -> tuple[list[PackageEntry], list[str]]:
    entries = extract_package(zip_bytes, limits)
    promoted_entries, warnings = promote_single_skill_md_directory(entries)
    return promoted_entries, warnings


def promote_single_skill_md_directory(entries: list[PackageEntry]) -> tuple[list[PackageEntry], list[str]]:
    if any(entry.path == "SKILL.md" for entry in entries):
        return entries, []

    skill_directories = sorted(
        {
            entry.path.rsplit("/", 1)[0]
            for entry in entries
            if entry.path.endswith("/SKILL.md") and "/" in entry.path
        }
    )
    if not skill_directories:
        return entries, []
    if len(skill_directories) > 1:
        raise ValueError(f"Ambiguous package: SKILL.md found in multiple directories: {', '.join(skill_directories)}")

    prefix = f"{skill_directories[0]}/"
    promoted: list[PackageEntry] = []
    warnings: list[str] = []
    for entry in entries:
        if entry.path.startswith(prefix):
            promoted.append(PackageEntry(entry.path.removeprefix(prefix), entry.content, entry.content_type))
        else:
            warnings.append(f"Ignored file outside skill directory: {entry.path}")

    return promoted, warnings


def parse_skill_metadata(content: bytes) -> SkillMetadata:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("SKILL.md must be valid UTF-8") from exc

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening --- marker")

    closing_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_index = index
            break
    if closing_index is None:
        raise ValueError("missing closing --- marker")

    frontmatter_text = "\n".join(lines[1:closing_index])
    try:
        parsed = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        raise ValueError("invalid YAML syntax") from exc

    if not isinstance(parsed, dict):
        raise ValueError("frontmatter must be a YAML object")

    for field_name in ("name", "description"):
        value = parsed.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'missing required field "{field_name}"')

    version = parsed.get("version")
    return SkillMetadata(
        name=parsed["name"].strip(),
        description=parsed["description"].strip(),
        version=str(version).strip() if version is not None else None,
        frontmatter=parsed,
    )


def validate_package(
    entries: list[PackageEntry],
    limits: PackageLimits | None = None,
    *,
    allowed_extensions: AbstractSet[str] | None = None,
) -> ValidationResult:
    active_limits = limits or PackageLimits()
    active_allowed_extensions = normalize_allowed_extensions(allowed_extensions)
    errors: list[str] = []
    warnings: list[str] = []
    seen_paths: set[str] = set()
    normalized_entries: list[PackageEntry] = []
    skill_md_entry: PackageEntry | None = None

    for entry in entries:
        try:
            normalized_path = normalize_entry_path(entry.path)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        if normalized_path in seen_paths:
            errors.append(f"Duplicate file path: {normalized_path}")
        seen_paths.add(normalized_path)

        normalized_entry = PackageEntry(normalized_path, entry.content, determine_content_type(normalized_path))
        normalized_entries.append(normalized_entry)
        if not is_allowed_extension(normalized_path, active_allowed_extensions):
            warnings.append(f"Disallowed file extension: {normalized_path}")
        if not content_signature_matches(normalized_path, entry.content):
            warnings.append(f"Content signature mismatch for {normalized_path}")
        if normalized_path == "SKILL.md" and skill_md_entry is None:
            skill_md_entry = normalized_entry

    if skill_md_entry is None:
        errors.append("Package must contain SKILL.md at root")
        return ValidationResult(valid=False, errors=errors, warnings=warnings)

    if len(normalized_entries) > active_limits.max_file_count:
        errors.append(f"Too many files: {len(normalized_entries)} (max: {active_limits.max_file_count})")

    total_size = 0
    for entry in normalized_entries:
        total_size += entry.size
        if entry.size > active_limits.max_single_file_size:
            errors.append(f"File too large: {entry.path} ({entry.size} bytes, max: {active_limits.max_single_file_size})")
    if total_size > active_limits.max_total_size:
        errors.append(f"Package too large: {total_size} bytes (max: {active_limits.max_total_size})")

    metadata: SkillMetadata | None = None
    try:
        metadata = parse_skill_metadata(skill_md_entry.content)
    except ValueError as exc:
        errors.append(f"Invalid SKILL.md frontmatter: {exc}")
    if metadata is not None:
        from app.publish.compliance import validate_compliance_metadata

        errors.extend(validate_compliance_metadata(metadata.frontmatter, normalized_entries))

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings, metadata=metadata)


def is_allowed_extension(path: str, allowed_extensions: AbstractSet[str] | None = None) -> bool:
    active_allowed_extensions = normalize_allowed_extensions(allowed_extensions) or ALLOWED_EXTENSIONS
    return package_extension(path) in active_allowed_extensions


def is_valid_utf8_text(content: bytes) -> bool:
    if b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def content_signature_matches(path: str, content: bytes) -> bool:
    extension = package_extension(path)
    if extension in TEXT_LIKE_EXTENSIONS:
        return is_valid_utf8_text(content)
    if extension == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if extension == ".gif":
        return content.startswith(b"GIF8")
    if extension == ".webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if extension == ".ico":
        return content.startswith(b"\x00\x00\x01\x00")
    if extension == ".pdf":
        return content.startswith(b"%PDF")
    if extension == ".svg":
        return is_valid_utf8_text(content) and "<svg" in content.decode("utf-8").lower()
    return True
