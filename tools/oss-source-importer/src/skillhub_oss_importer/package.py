from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .discovery import DiscoveryError, SkillRoot


@dataclass(frozen=True)
class BuiltPackage:
    source_path: str
    filename: str
    content: bytes


def build_skill_package(root: SkillRoot, all_roots: set[Path]) -> BuiltPackage:
    resolved_roots = {path.resolve() for path in all_roots}
    files: list[tuple[str, Path]] = []
    for current, directories, names in os.walk(root.path, topdown=True, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name
            for name in directories
            if name != ".git"
            and not (current_path / name).is_symlink()
            and (current_path / name).resolve() not in resolved_roots - {root.path.resolve()}
        )
        for name in sorted(names):
            path = current_path / name
            if path.is_symlink():
                continue
            resolved = path.resolve()
            try:
                resolved.relative_to(root.path.resolve())
            except ValueError as exc:
                raise DiscoveryError(f"Package path escapes source root: {path}") from exc
            files.append((path.relative_to(root.path).as_posix(), path))
    if not any(name == "SKILL.md" for name, _path in files):
        raise DiscoveryError(f"Package root lacks SKILL.md: {root.source_path}")
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for archive_path, source_path in sorted(files):
            info = ZipInfo(archive_path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source_path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    return BuiltPackage(
        root.source_path,
        f"{root.path.name}.zip",
        output.getvalue(),
    )
