import pytest

from app.repository_imports.archive import RepositoryArchiveFile
from app.repository_imports.discovery import (
    RepositoryDiscoveryError,
    discover_skill_candidates,
)


def file(path: str, content: str) -> RepositoryArchiveFile:
    return RepositoryArchiveFile(path=path, content=content.encode())


def test_discovery_returns_independent_skill_roots_with_safe_metadata() -> None:
    candidates = discover_skill_candidates(
        [
            file(
                "skills/alpha/SKILL.md",
                "---\nname: Alpha\ndescription: First\nversion: 1.2.0\n---\n",
            ),
            file("skills/alpha/main.py", "print('not executed')"),
            file(
                "skills/beta/SKILL.md",
                "---\nname: Beta\ndescription: Second\n---\n",
            ),
        ]
    )

    assert [(item.source_path, item.detected_name, item.source_version) for item in candidates] == [
        ("skills/alpha", "Alpha", "1.2.0"),
        ("skills/beta", "Beta", None),
    ]
    assert [entry.path for entry in candidates[0].entries] == ["SKILL.md", "main.py"]


def test_discovery_rejects_nested_skill_roots() -> None:
    with pytest.raises(RepositoryDiscoveryError, match="nestedSkillRoot"):
        discover_skill_candidates(
            [
                file("alpha/SKILL.md", "---\nname: Alpha\n---"),
                file("alpha/nested/SKILL.md", "---\nname: Nested\n---"),
            ]
        )


def test_discovery_does_not_execute_repository_scripts(monkeypatch) -> None:
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not execute")

    monkeypatch.setattr("subprocess.run", forbidden)
    discover_skill_candidates(
        [
            file(
                "alpha/SKILL.md",
                "---\nname: Alpha\ndescription: Safe\n---",
            ),
            file("alpha/install.sh", "exit 1"),
        ]
    )

    assert called is False
