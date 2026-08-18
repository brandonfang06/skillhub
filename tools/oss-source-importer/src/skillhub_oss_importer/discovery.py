from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class DiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class SkillRoot:
    path: Path
    source_path: str


def discover_skill_roots(project_dir: Path, source_root: Path) -> list[SkillRoot]:
    project = project_dir.resolve()
    source = source_root.resolve()
    if not source.is_relative_to(project):
        raise DiscoveryError("Source root must stay within the project checkout")
    roots: list[SkillRoot] = []
    for current, directories, files in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name
            for name in directories
            if name != ".git" and not (current_path / name).is_symlink()
        )
        if "SKILL.md" in files and not current_path.is_symlink():
            relative = current_path.relative_to(project).as_posix() or "."
            roots.append(SkillRoot(current_path, relative))
    roots.sort(key=lambda item: item.source_path)
    if not roots:
        raise DiscoveryError("No exact-case SKILL.md files were found")
    return roots
