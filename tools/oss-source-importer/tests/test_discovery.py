from pathlib import Path

import pytest

from skillhub_oss_importer.discovery import DiscoveryError, discover_skill_roots


def test_discovers_sorted_exact_case_roots_without_git_or_symlink(tmp_path: Path) -> None:
    (tmp_path / "zeta").mkdir()
    (tmp_path / "zeta" / "SKILL.md").write_text("z", encoding="utf-8")
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "SKILL.md").write_text("a", encoding="utf-8")
    (tmp_path / "lower").mkdir()
    (tmp_path / "lower" / "skill.md").write_text("no", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "SKILL.md").write_text("no", encoding="utf-8")

    assert [item.source_path for item in discover_skill_roots(tmp_path, tmp_path)] == ["alpha", "zeta"]


def test_fails_when_no_skills_exist(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="SKILL.md"):
        discover_skill_roots(tmp_path, tmp_path)
