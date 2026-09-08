from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from skillhub_oss_importer.discovery import discover_skill_roots
from skillhub_oss_importer.package import build_skill_package


@pytest.mark.parametrize("manifest", ["SKILL.md", "skill.md", "Skill.MD"])
def test_builds_deterministic_rooted_zip_and_excludes_nested_skill(tmp_path: Path, manifest: str) -> None:
    parent = tmp_path / "skills" / "parent"
    nested = parent / "nested"
    nested.mkdir(parents=True)
    (parent / manifest).write_bytes(b"parent\r\n")
    (parent / "reference.md").write_bytes(b"ref")
    (nested / manifest).write_bytes(b"nested")
    (nested / "example.txt").write_bytes(b"example")
    roots = discover_skill_roots(tmp_path, tmp_path)

    package = build_skill_package(roots[0], {root.path for root in roots})
    repeated = build_skill_package(roots[0], {root.path for root in roots})

    assert package.content == repeated.content
    with ZipFile(BytesIO(package.content)) as archive:
        assert archive.namelist() == ["SKILL.md", "reference.md"]
        assert archive.read("SKILL.md") == b"parent\r\n"
        assert archive.getinfo("SKILL.md").date_time == (1980, 1, 1, 0, 0, 0)
    assert (parent / manifest).read_bytes() == b"parent\r\n"
    assert {path.name for path in parent.iterdir()} == {manifest, "reference.md", "nested"}


def test_manifest_case_alone_does_not_change_package_bytes(tmp_path: Path) -> None:
    packages = []
    for directory, manifest in [("upper", "SKILL.md"), ("lower", "skill.md")]:
        root = tmp_path / directory
        root.mkdir()
        (root / manifest).write_bytes(b"same\r\n")
        discovered = discover_skill_roots(root, root)
        packages.append(build_skill_package(discovered[0], {root}).content)
    assert packages[0] == packages[1]
