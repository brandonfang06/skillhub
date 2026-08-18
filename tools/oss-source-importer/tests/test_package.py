from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from skillhub_oss_importer.discovery import discover_skill_roots
from skillhub_oss_importer.package import build_skill_package


def test_builds_deterministic_rooted_zip_and_excludes_nested_skill(tmp_path: Path) -> None:
    parent = tmp_path / "skills" / "parent"
    nested = parent / "nested"
    nested.mkdir(parents=True)
    (parent / "SKILL.md").write_bytes(b"parent\r\n")
    (parent / "reference.md").write_bytes(b"ref")
    (nested / "SKILL.md").write_bytes(b"nested")
    (nested / "example.txt").write_bytes(b"example")
    roots = discover_skill_roots(tmp_path, tmp_path)

    package = build_skill_package(roots[0], {root.path for root in roots})
    repeated = build_skill_package(roots[0], {root.path for root in roots})

    assert package.content == repeated.content
    assert package.has_explicit_version is False
    with ZipFile(BytesIO(package.content)) as archive:
        assert archive.namelist() == ["SKILL.md", "reference.md"]
        assert archive.read("SKILL.md") == b"parent\r\n"
        assert archive.getinfo("SKILL.md").date_time == (1980, 1, 1, 0, 0, 0)


def test_detects_explicit_frontmatter_version(tmp_path: Path) -> None:
    root = tmp_path / "versioned"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: versioned\ndescription: fixture\nversion: '1.2.3'\n---\n",
        encoding="utf-8",
    )
    skill_root = discover_skill_roots(tmp_path, tmp_path)[0]

    package = build_skill_package(skill_root, {skill_root.path})

    assert package.has_explicit_version is True
