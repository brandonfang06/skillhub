from pathlib import Path

import pytest

from skillhub_oss_importer.discovery import DiscoveryError, discover_skill_roots


def test_discovers_sorted_case_insensitive_roots_without_git(tmp_path: Path) -> None:
    (tmp_path / "zeta").mkdir()
    (tmp_path / "zeta" / "SKILL.md").write_text("z", encoding="utf-8")
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "SKILL.md").write_text("a", encoding="utf-8")
    (tmp_path / "lower").mkdir()
    (tmp_path / "lower" / "skill.md").write_text("no", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "SKILL.md").write_text("no", encoding="utf-8")

    assert [item.source_path for item in discover_skill_roots(tmp_path, tmp_path)] == ["alpha", "lower", "zeta"]


def test_fails_when_no_skills_exist(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="SKILL.md"):
        discover_skill_roots(tmp_path, tmp_path)


def test_rejects_ambiguous_manifests_before_packaging(tmp_path: Path, monkeypatch) -> None:
    # Windows cannot materialize both names; model the Linux directory listing.
    monkeypatch.setattr("skillhub_oss_importer.discovery.os.walk",
                        lambda *args, **kwargs: iter([(str(tmp_path), [], ["SKILL.md", "skill.md"])]))
    with pytest.raises(DiscoveryError, match="Ambiguous SKILL.md"):
        discover_skill_roots(tmp_path, tmp_path)


def test_does_not_follow_manifest_symlink(tmp_path: Path) -> None:
    target = tmp_path / "source.txt"
    target.write_text("untrusted", encoding="utf-8")
    try:
        (tmp_path / "skill.md").symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(DiscoveryError, match="No SKILL.md"):
        discover_skill_roots(tmp_path, tmp_path)
