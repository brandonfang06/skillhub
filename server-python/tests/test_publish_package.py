from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from app.publish.package import (
    PackageEntry,
    PackageLimits,
    determine_content_type,
    extract_package,
    extract_package_with_warnings,
    normalize_entry_path,
    parse_skill_metadata,
    strip_single_root_directory,
    validate_package,
)


def make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for path, content in entries.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def skill_md(name: str = "demo", description: str = "Demo skill") -> bytes:
    return f"---\nname: {name}\ndescription: {description}\nversion: 1.0.0\n---\n# Demo\n".encode()


def test_package_entry_size_and_content_type_mapping() -> None:
    entry = PackageEntry(path="src/main.py", content=b"print('ok')", content_type="text/x-python")

    assert entry.size == 11
    assert determine_content_type("SKILL.md") == "text/markdown"
    assert determine_content_type("manifest.json") == "application/json"
    assert determine_content_type("skill.yaml") == "application/x-yaml"
    assert determine_content_type("image.png") == "image/png"
    assert determine_content_type("archive.unknown") == "application/octet-stream"


@pytest.mark.parametrize(
    ("raw_path", "normalized"),
    [
        ("SKILL.md", "SKILL.md"),
        (" nested/SKILL.md ", "nested/SKILL.md"),
        ("nested\\src\\main.py", "nested/src/main.py"),
    ],
)
def test_normalize_entry_path_accepts_java_compatible_paths(raw_path: str, normalized: str) -> None:
    assert normalize_entry_path(raw_path) == normalized


@pytest.mark.parametrize(
    "raw_path",
    ["", "   ", "/SKILL.md", "../SKILL.md", "nested/../SKILL.md", "C:/tmp/SKILL.md", "a//b.txt"],
)
def test_normalize_entry_path_rejects_unsafe_or_non_normalized_paths(raw_path: str) -> None:
    with pytest.raises(ValueError):
        normalize_entry_path(raw_path)


def test_extract_package_skips_directories_and_os_metadata() -> None:
    archive = make_zip(
        {
            "skill/SKILL.md": skill_md(),
            "skill/src/main.py": b"print('ok')",
            "__MACOSX/._SKILL.md": b"ignored",
            "skill/.DS_Store": b"ignored",
            "skill/._README.md": b"ignored",
        }
    )

    entries = extract_package(archive)

    assert [(entry.path, entry.content, entry.content_type) for entry in entries] == [
        ("SKILL.md", skill_md(), "text/markdown"),
        ("src/main.py", b"print('ok')", "text/x-python"),
    ]


def test_extract_package_enforces_limits() -> None:
    with pytest.raises(ValueError, match="Too many files"):
        extract_package(make_zip({"a.txt": b"a", "b.txt": b"b"}), PackageLimits(max_file_count=1))

    with pytest.raises(ValueError, match="File too large"):
        extract_package(make_zip({"big.txt": b"abc"}), PackageLimits(max_single_file_size=2))

    with pytest.raises(ValueError, match="Package too large"):
        extract_package(make_zip({"a.txt": b"ab", "b.txt": b"cd"}), PackageLimits(max_total_size=3))


def test_strip_single_root_directory_only_when_all_files_share_root() -> None:
    assert strip_single_root_directory(
        [
            PackageEntry("skill/SKILL.md", b"", "text/markdown"),
            PackageEntry("skill/src/main.py", b"", "text/x-python"),
        ]
    ) == [
        PackageEntry("SKILL.md", b"", "text/markdown"),
        PackageEntry("src/main.py", b"", "text/x-python"),
    ]

    mixed = [
        PackageEntry("skill/SKILL.md", b"", "text/markdown"),
        PackageEntry("README.md", b"", "text/markdown"),
    ]
    assert strip_single_root_directory(mixed) == mixed


def test_extract_package_promotes_single_nested_skill_directory_with_warning() -> None:
    archive = make_zip(
        {
            "docs/README.md": b"# ignored",
            "package/SKILL.md": skill_md(),
            "package/src/main.py": b"print('ok')",
        }
    )

    entries, warnings = extract_package_with_warnings(archive)

    assert [entry.path for entry in entries] == ["SKILL.md", "src/main.py"]
    assert warnings == ["Ignored file outside skill directory: docs/README.md"]


def test_extract_package_rejects_ambiguous_nested_skill_directories() -> None:
    archive = make_zip({"one/SKILL.md": skill_md("one"), "two/SKILL.md": skill_md("two")})

    with pytest.raises(ValueError, match="Ambiguous package"):
        extract_package_with_warnings(archive)


def test_validate_package_requires_root_skill_md() -> None:
    result = validate_package([PackageEntry("README.md", b"# demo", "text/markdown")])

    assert not result.valid
    assert "Package must contain SKILL.md at root" in result.errors


def test_validate_package_reports_duplicate_disallowed_and_signature_warnings() -> None:
    result = validate_package(
        [
            PackageEntry("SKILL.md", skill_md(), "text/markdown"),
            PackageEntry("docs/README.exe", b"binary", "application/octet-stream"),
            PackageEntry("docs/bad.txt", b"\xff", "text/plain"),
            PackageEntry("image.png", b"not-a-png", "image/png"),
            PackageEntry("SKILL.md", skill_md(), "text/markdown"),
        ]
    )

    assert not result.valid
    assert "Duplicate file path: SKILL.md" in result.errors
    assert "Disallowed file extension: docs/README.exe" in result.warnings
    assert "Content signature mismatch for docs/bad.txt" in result.warnings
    assert "Content signature mismatch for image.png" in result.warnings


def test_parse_skill_metadata_reads_yaml_frontmatter() -> None:
    metadata = parse_skill_metadata(skill_md(name="agent-helper", description="Helps agents"))

    assert metadata.name == "agent-helper"
    assert metadata.description == "Helps agents"
    assert metadata.version == "1.0.0"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"---\ndescription: Missing name\n---\n", 'missing required field "name"'),
        (b"---\nname: missing-description\n---\n", 'missing required field "description"'),
    ],
)
def test_validate_package_uses_java_compatible_metadata_error_wording(content: bytes, message: str) -> None:
    result = validate_package([PackageEntry("SKILL.md", content, "text/markdown")])

    assert not result.valid
    assert f"Invalid SKILL.md frontmatter: {message}" in result.errors
