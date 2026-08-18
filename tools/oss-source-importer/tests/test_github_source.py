import subprocess
from pathlib import Path

import pytest

from skillhub_oss_importer.github_source import SourceError, canonicalize_repository, verify_checkout_revision


def test_canonicalizes_only_github_https_repository() -> None:
    source = canonicalize_repository("https://github.com/MattPocock/Skills.git")
    assert source.canonical_url == "https://github.com/mattpocock/skills"
    assert source.namespace_slug == "oss-mattpocock-skills"
    assert source.namespace_display_name == "OSS-mattpocock-skills"
    with pytest.raises(SourceError):
        canonicalize_repository("https://gitlab.com/mattpocock/skills")


def test_verifies_checkout_head_exactly(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    (tmp_path / "README.md").write_text("fixture", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "fixture"], check=True)
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    verify_checkout_revision(tmp_path, head)
    with pytest.raises(SourceError, match="does not match"):
        verify_checkout_revision(tmp_path, "0" * 40)
