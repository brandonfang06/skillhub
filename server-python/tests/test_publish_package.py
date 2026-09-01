from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile, ZipInfo

import pytest

from app.publish.package import (
    PackageEntry,
    PackageLimits,
    content_signature_matches,
    determine_content_type,
    extract_package,
    extract_package_with_warnings,
    is_allowed_extension,
    is_directory_entry_path,
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


def compliance_skill_md(compliance_yaml: str) -> bytes:
    return (
        "---\n"
        "name: compliance-demo\n"
        "description: Compliance demo\n"
        "version: 1.0.0\n"
        "x-astron-compliance:\n"
        f"{compliance_yaml}\n"
        "---\n"
        "# Demo\n"
    ).encode()


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
        ("\u00a0references/evidence.md\u00a0", "\u00a0references/evidence.md\u00a0"),
        ("\u2003references/evidence.md\u2003", "\u2003references/evidence.md\u2003"),
    ],
)
def test_normalize_entry_path_accepts_java_compatible_paths(raw_path: str, normalized: str) -> None:
    assert normalize_entry_path(raw_path) == normalized


@pytest.mark.parametrize(
    ("raw_path", "normalized"),
    [
        ("skill.md", "SKILL.md"),
        ("Skill.MD", "SKILL.md"),
        ("nested/skill.md", "nested/SKILL.md"),
        ("nested/Skill.MD", "nested/SKILL.md"),
    ],
)
def test_normalize_entry_path_canonicalizes_case_insensitive_skill_md(raw_path: str, normalized: str) -> None:
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


def test_extract_package_skips_windows_style_directory_entries() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive_writer:
        directory = ZipInfo("placeholder")
        directory.filename = "skill\\"
        archive_writer.writestr(directory, b"")
        skill_file = ZipInfo("placeholder")
        skill_file.filename = "skill\\SKILL.md"
        archive_writer.writestr(skill_file, skill_md())

    entries = extract_package(buffer.getvalue())

    assert [(entry.path, entry.content) for entry in entries] == [
        ("SKILL.md", skill_md()),
    ]


@pytest.mark.parametrize("path", ["skill/", "skill\\"])
def test_directory_entry_detection_is_platform_independent(path: str) -> None:
    assert is_directory_entry_path(path)


def test_extract_package_canonicalizes_case_insensitive_skill_md() -> None:
    archive = make_zip({"skill.md": skill_md(), "src/main.py": b"print('ok')"})

    entries = extract_package(archive)
    result = validate_package(entries)

    assert [entry.path for entry in entries] == ["SKILL.md", "src/main.py"]
    assert result.valid
    assert result.metadata is not None
    assert result.metadata.name == "demo"


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
            "package/skill.md": skill_md(),
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


def test_validate_package_accepts_runtime_allowed_extension_override() -> None:
    result = validate_package(
        [
            PackageEntry("SKILL.md", skill_md(), "text/markdown"),
            PackageEntry("docs/diagram.dot", b"digraph G { a -> b }\n", "text/vnd.graphviz"),
        ],
        allowed_extensions={".md", ".dot"},
    )

    assert result.valid
    assert result.warnings == []


def test_runtime_allowed_extension_override_replaces_default_allowlist() -> None:
    result = validate_package(
        [
            PackageEntry("SKILL.md", skill_md(), "text/markdown"),
            PackageEntry("src/main.py", b"print('ok')", "text/x-python"),
        ],
        allowed_extensions={".md", ".dot"},
    )

    assert "Disallowed file extension: src/main.py" in result.warnings


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


@pytest.mark.parametrize(
    ("compliance_yaml", "message"),
    [
        ("  standard: nist-csf", "x-astron-compliance must be an array"),
        ("  - not-an-object", "x-astron-compliance[0] must be an object"),
        (
            "  - standard: nist-csf\n    version: '2.0'\n    controlId: GV.OC-03\n    extra: no",
            "x-astron-compliance[0].extra is not allowed",
        ),
        (
            "  - standard: ''\n    version: '2.0'\n    controlId: GV.OC-03",
            "x-astron-compliance[0].standard is required",
        ),
        (
            "  - standard: nist-csf\n    controlId: GV.OC-03",
            "x-astron-compliance[0].version is required",
        ),
        (
            "  - standard: nist-csf\n    version: '2.0'",
            "x-astron-compliance[0].controlId is required",
        ),
        (
            f"  - standard: {'a' * 65}\n    version: '2.0'\n    controlId: GV.OC-03",
            "x-astron-compliance[0].standard must be at most 64 characters",
        ),
        (
            "  - standard: nist/csf\n    version: '2.0'\n    controlId: GV.OC-03",
            "x-astron-compliance[0].standard has an invalid format",
        ),
        (
            "  - standard: '\u00a0MITRE-ATTACK\u00a0'\n    version: v19.1\n    controlId: T1059",
            "x-astron-compliance[0].standard has an invalid format",
        ),
        (
            f"  - standard: nist-csf\n    version: '{'v' * 65}'\n    controlId: GV.OC-03",
            "x-astron-compliance[0].version must be at most 64 characters",
        ),
        (
            f"  - standard: nist-csf\n    version: '{'😀' * 33}'\n    controlId: GV.OC-03",
            "x-astron-compliance[0].version must be at most 64 characters",
        ),
        (
            f"  - standard: nist-csf\n    version: '2.0'\n    controlId: {'C' * 129}",
            "x-astron-compliance[0].controlId must be at most 128 characters",
        ),
        (
            "  - standard: nist-csf\n    version: '2.0'\n    controlId: bad/control",
            "x-astron-compliance[0].controlId has an invalid format",
        ),
        (
            f"  - standard: nist-csf\n    version: '2.0'\n    controlId: GV.OC-03\n    title: {'t' * 201}",
            "x-astron-compliance[0].title must be at most 200 characters",
        ),
        (
            "  - standard: nist-csf\n    version: '2.0'\n    controlId: GV.OC-03\n    title: ''",
            "x-astron-compliance[0].title must be a non-empty string",
        ),
        (
            '  - standard: nist-csf\n    version: \'2.0\'\n    controlId: GV.OC-03\n    title: "\\uD800"',
            "x-astron-compliance[0].title must contain valid Unicode",
        ),
        (
            "  - standard: MITRE-ATTACK\n    version: v19.1\n    controlId: T1059\n"
            "  - standard: mitre-attack\n    version: v19.1\n    controlId: T1059",
            "x-astron-compliance contains duplicate mapping mitre-attack/v19.1/T1059",
        ),
        (
            "  - standard: nist-csf\n    version: '2.0'\n    controlId: GV.OC-03\n    evidence: object",
            "x-astron-compliance[0].evidence must be an array",
        ),
        (
            "  - standard: nist-csf\n    version: '2.0'\n    controlId: GV.OC-03\n"
            "    evidence:\n      - type: unknown",
            "type must be one of packaged-file, external-url",
        ),
        (
            "  - standard: nist-csf\n    version: '2.0'\n    controlId: GV.OC-03\n"
            "    evidence:\n      - type: '\u00a0external-url\u00a0'\n        url: https://example.com",
            "type must be one of packaged-file, external-url",
        ),
        (
            "  - standard: nist-csf\n    version: '2.0'\n    controlId: GV.OC-03\n"
            "    evidence:\n      - not-an-object",
            "x-astron-compliance[0].evidence[0] must be an object",
        ),
        (
            "  - standard: nist-csf\n    version: '2.0'\n    controlId: GV.OC-03\n"
            "    evidence:\n      - type: external-url\n        url: https://example.com\n        extra: no",
            "x-astron-compliance[0].evidence[0].extra is not allowed",
        ),
        (
            "  - standard: nist-csf\n    version: '2.0'\n    controlId: GV.OC-03\n"
            "    evidence:\n      - type: packaged-file\n        path: ../outside.md",
            "Parent directory paths are not allowed",
        ),
        (
            "  - standard: nist-csf\n    version: '2.0'\n    controlId: GV.OC-03\n"
            "    evidence:\n      - type: packaged-file\n        path: references/missing.md",
            "path does not exist in package: references/missing.md",
        ),
        (
            "  - standard: nist-csf\n    version: '2.0'\n    controlId: GV.OC-03\n"
            f"    evidence:\n      - type: packaged-file\n        path: {'p' * 513}",
            "path must be at most 512 characters",
        ),
        (
            "  - standard: soc2\n    version: '2017'\n    controlId: CC6.1\n"
            "    evidence:\n      - type: external-url\n        url: file:///tmp/evidence.md",
            "url must be an http or https URL",
        ),
        (
            "  - standard: soc2\n    version: '2017'\n    controlId: CC6.1\n"
            "    evidence:\n      - type: external-url\n        url: https:///missing-host",
            "url must be an http or https URL",
        ),
        (
            "  - standard: soc2\n    version: '2017'\n    controlId: CC6.1\n"
            f"    evidence:\n      - type: external-url\n        url: https://example.com/{'u' * 2030}",
            "url must be at most 2048 characters",
        ),
        (
            "  - standard: soc2\n    version: '2017'\n    controlId: CC6.1\n"
            "    evidence:\n      - type: external-url\n        url: https://exa mple.com/%zz",
            "url must be an http or https URL",
        ),
        (
            "  - standard: soc2\n    version: '2017'\n    controlId: CC6.1\n"
            "    evidence:\n      - type: external-url\n        url: 'https://example.com/a\\b'",
            "url must be an http or https URL",
        ),
        (
            "  - standard: soc2\n    version: '2017'\n    controlId: CC6.1\n"
            "    evidence:\n      - type: external-url\n        url: 'https://example.com/a[b]'",
            "url must be an http or https URL",
        ),
        (
            "  - standard: soc2\n    version: '2017'\n    controlId: CC6.1\n"
            "    evidence:\n      - type: external-url\n        url: 'https://user@example.com@evil.example/path'",
            "url must be an http or https URL",
        ),
        (
            "  - standard: soc2\n    version: '2017'\n    controlId: CC6.1\n"
            "    evidence:\n      - type: external-url\n        url: 'https://example.123/path'",
            "url must be an http or https URL",
        ),
        (
            "  - standard: soc2\n    version: '2017'\n    controlId: CC6.1\n"
            "    evidence:\n      - type: external-url\n        url: 'https://example.com:2147483648/path'",
            "url must be an http or https URL",
        ),
        (
            "  - standard: soc2\n    version: '2017'\n    controlId: CC6.1\n"
            "    evidence:\n      - type: external-url\n        url: 'https://[fe80::1%eth-0]/path'",
            "url must be an http or https URL",
        ),
    ],
)
def test_validate_package_rejects_invalid_compliance_metadata(
    compliance_yaml: str,
    message: str,
) -> None:
    result = validate_package(
        [PackageEntry("SKILL.md", compliance_skill_md(compliance_yaml), "text/markdown")]
    )

    assert not result.valid
    assert any(message in error for error in result.errors)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com:/path",
        "https://example.com:65536/path",
        "https://example.com:2147483647/path",
        "https://example.com/a\u200db",
        "https://123/path",
        "https://1abc/path",
        "https://010.000.000.001/path",
        "https://[fe80::1%eth_0]/path",
        "https://[fe80::1%eth.0]/path",
        "https://[::ffff:010.000.000.001]/path",
        "https://[0:0:0:0:0:ffff:010.000.000.001]/path",
    ],
)
def test_validate_package_accepts_java_compatible_external_evidence_urls(url: str) -> None:
    result = validate_package(
        [
            PackageEntry(
                "SKILL.md",
                compliance_skill_md(
                    "  - standard: soc2\n"
                    "    version: '2017'\n"
                    "    controlId: CC6.1\n"
                    "    evidence:\n"
                    "      - type: external-url\n"
                    f"        url: '{url}'"
                ),
                "text/markdown",
            )
        ]
    )

    assert result.valid


@pytest.mark.parametrize("padding", ["\u00a0", "\u2003"])
def test_validate_package_preserves_java_unicode_whitespace_evidence_paths(
    padding: str,
) -> None:
    evidence_path = f"{padding}references/evidence.md{padding}"
    entries = extract_package(
        make_zip(
            {
                "SKILL.md": compliance_skill_md(
                    "  - standard: soc2\n"
                    "    version: '2017'\n"
                    "    controlId: CC6.1\n"
                    "    evidence:\n"
                    "      - type: packaged-file\n"
                    f"        path: '{evidence_path}'"
                ),
                evidence_path: b"evidence",
            }
        )
    )
    result = validate_package(entries)

    assert evidence_path in [entry.path for entry in entries]
    assert result.valid


def test_validate_package_enforces_compliance_mapping_and_evidence_limits() -> None:
    mappings = "\n".join(
        f"  - standard: standard-{index}\n    version: '1'\n    controlId: C{index}"
        for index in range(51)
    )
    evidence = "\n".join(
        f"      - type: external-url\n        url: https://example.com/{index}"
        for index in range(11)
    )
    too_many_mappings = validate_package(
        [PackageEntry("SKILL.md", compliance_skill_md(mappings), "text/markdown")]
    )
    too_many_evidence = validate_package(
        [
            PackageEntry(
                "SKILL.md",
                compliance_skill_md(
                    "  - standard: nist-csf\n"
                    "    version: '2.0'\n"
                    "    controlId: GV.OC-03\n"
                    "    evidence:\n"
                    f"{evidence}"
                ),
                "text/markdown",
            )
        ]
    )

    assert any("must contain at most 50 items" in error for error in too_many_mappings.errors)
    assert any("must contain at most 10 items" in error for error in too_many_evidence.errors)


@pytest.mark.parametrize(
    "path",
    [
        "docs/readme.doc",
        "docs/readme.docx",
        "sheets/data.xls",
        "sheets/data.xlsx",
        "slides/deck.ppt",
        "slides/deck.pptx",
        "schema/model.xsd",
        "schema/transform.xsl",
        "schema/entities.dtd",
        "config/app.ini",
        "config/app.cfg",
        "config/.env",
        "src/tool.rb",
        "src/tool.go",
        "src/tool.rs",
        "src/Tool.java",
        "src/tool.kt",
        "src/tool.lua",
        "db/query.sql",
        "stats/model.r",
        "scripts/run.bat",
    ],
)
def test_allowed_extensions_match_java_skill_package_policy(path: str) -> None:
    assert is_allowed_extension(path)


@pytest.mark.parametrize("path", ["README.markdown", "src/App.tsx", "src/App.jsx", "style/app.scss"])
def test_python_only_extensions_are_not_allowed_when_java_rejects_them(path: str) -> None:
    assert not is_allowed_extension(path)


@pytest.mark.parametrize("path", ["schema/model.xsd", "schema/transform.xsl", "schema/entities.dtd"])
def test_xml_schema_extensions_are_text_signature_checked(path: str) -> None:
    assert content_signature_matches(path, b"<schema></schema>")
    assert not content_signature_matches(path, b"\xff")
