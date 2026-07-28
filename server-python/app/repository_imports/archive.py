from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import posixpath
from pathlib import PurePosixPath
from stat import S_IFLNK
from zipfile import BadZipFile, ZipFile


class RepositoryArchiveError(ValueError):
    def __init__(self, detail: str, *, status_code: int = 422) -> None:
        super().__init__(detail)
        self.status_code = status_code


@dataclass(frozen=True)
class RepositoryArchiveLimits:
    max_file_count: int = 500
    max_single_file_bytes: int = 5 * 1024 * 1024
    max_total_bytes: int = 50 * 1024 * 1024


@dataclass(frozen=True)
class RepositoryArchiveFile:
    path: str
    content: bytes


def _normalize_path(raw_path: str) -> str:
    candidate = raw_path.replace("\\", "/")
    if (
        not candidate
        or candidate.startswith("/")
        or ":" in candidate
        or candidate.endswith("/")
    ):
        raise RepositoryArchiveError("error.repositoryImport.archive.unsafePath")
    normalized = posixpath.normpath(candidate)
    if (
        normalized in {"", ".", ".."}
        or normalized.startswith("../")
        or normalized != candidate
    ):
        raise RepositoryArchiveError("error.repositoryImport.archive.unsafePath")
    return normalized


def _strip_common_root(paths: list[str]) -> list[str]:
    first_segments = {PurePosixPath(path).parts[0] for path in paths}
    if len(first_segments) != 1 or any(len(PurePosixPath(path).parts) < 2 for path in paths):
        return paths
    return ["/".join(PurePosixPath(path).parts[1:]) for path in paths]


def read_repository_archive(
    archive_bytes: bytes,
    limits: RepositoryArchiveLimits | None = None,
) -> list[RepositoryArchiveFile]:
    effective_limits = limits or RepositoryArchiveLimits()
    try:
        with ZipFile(BytesIO(archive_bytes)) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if len(infos) > effective_limits.max_file_count:
                raise RepositoryArchiveError(
                    "error.repositoryImport.archive.tooManyFiles",
                    status_code=413,
                )
            normalized_paths: list[str] = []
            seen: set[str] = set()
            total = 0
            for info in infos:
                mode = (info.external_attr >> 16) & 0o170000
                if mode == S_IFLNK:
                    raise RepositoryArchiveError(
                        "error.repositoryImport.archive.symlink"
                    )
                path = _normalize_path(info.filename)
                identity = path.casefold()
                if identity in seen:
                    raise RepositoryArchiveError(
                        "error.repositoryImport.archive.duplicatePath"
                    )
                seen.add(identity)
                if info.file_size > effective_limits.max_single_file_bytes:
                    raise RepositoryArchiveError(
                        "error.repositoryImport.archive.fileTooLarge",
                        status_code=413,
                    )
                total += info.file_size
                if total > effective_limits.max_total_bytes:
                    raise RepositoryArchiveError(
                        "error.repositoryImport.archive.expandedTooLarge",
                        status_code=413,
                    )
                normalized_paths.append(path)

            stripped_paths = _strip_common_root(normalized_paths)
            files: list[RepositoryArchiveFile] = []
            actual_total = 0
            for info, path in zip(infos, stripped_paths, strict=True):
                content = archive.read(info)
                actual_total += len(content)
                if len(content) > effective_limits.max_single_file_bytes:
                    raise RepositoryArchiveError(
                        "error.repositoryImport.archive.fileTooLarge",
                        status_code=413,
                    )
                if actual_total > effective_limits.max_total_bytes:
                    raise RepositoryArchiveError(
                        "error.repositoryImport.archive.expandedTooLarge",
                        status_code=413,
                    )
                files.append(RepositoryArchiveFile(path=path, content=content))
            return files
    except BadZipFile as exc:
        raise RepositoryArchiveError(
            "error.repositoryImport.archive.invalid"
        ) from exc
