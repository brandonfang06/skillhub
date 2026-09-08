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
    manifest_name: str = "SKILL.md"


def discover_skill_roots(project_dir: Path, source_root: Path) -> list[SkillRoot]:
    project = project_dir.resolve()
    source = source_root.resolve()
    try:
        source.relative_to(project)
    except ValueError as exc:
        raise DiscoveryError("Source root must stay within the project checkout") from exc
    roots: list[SkillRoot] = []
    for current, directories, files in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name
            for name in directories
            if name != ".git" and not (current_path / name).is_symlink()
        )
        manifests = sorted(name for name in files if name.isascii() and name.lower() == "skill.md")
        if len(manifests) > 1:
            raise DiscoveryError(f"Ambiguous SKILL.md filenames: {current_path.relative_to(project).as_posix()}")
        if manifests and not (current_path / manifests[0]).is_symlink():
            relative = current_path.relative_to(project).as_posix() or "."
            roots.append(SkillRoot(current_path, relative, manifests[0]))
    roots.sort(key=lambda item: item.source_path)
    if not roots:
        raise DiscoveryError("No SKILL.md files were found (case-insensitive)")
    return roots
