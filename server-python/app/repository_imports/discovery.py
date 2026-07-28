from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from app.publish.package import PackageEntry, determine_content_type, validate_package
from app.repository_imports.archive import RepositoryArchiveFile


class RepositoryDiscoveryError(ValueError):
    def __init__(self, detail: str, *, status_code: int = 422) -> None:
        super().__init__(detail)
        self.status_code = status_code


@dataclass(frozen=True)
class RepositorySkillCandidate:
    source_path: str
    detected_name: str
    detected_description: str
    source_version: str | None
    entries: list[PackageEntry]
    warnings: list[str]


def discover_skill_candidates(
    files: list[RepositoryArchiveFile],
) -> list[RepositorySkillCandidate]:
    roots = sorted(
        {
            str(PurePosixPath(item.path).parent)
            for item in files
            if PurePosixPath(item.path).name.casefold() == "skill.md"
        }
    )
    normalized_roots = ["" if root == "." else root for root in roots]
    for root in normalized_roots:
        prefix = f"{root}/" if root else ""
        if any(
            other != root and other.startswith(prefix)
            for other in normalized_roots
        ):
            raise RepositoryDiscoveryError(
                "error.repositoryImport.discovery.nestedSkillRoot"
            )
    if not normalized_roots:
        raise RepositoryDiscoveryError(
            "error.repositoryImport.discovery.skillMd.notFound"
        )

    candidates: list[RepositorySkillCandidate] = []
    for root in normalized_roots:
        prefix = f"{root}/" if root else ""
        entries = [
            PackageEntry(
                path=item.path[len(prefix) :],
                content=item.content,
                content_type=determine_content_type(item.path),
            )
            for item in files
            if (not root or item.path.startswith(prefix))
        ]
        validation = validate_package(entries)
        if not validation.valid or validation.metadata is None:
            raise RepositoryDiscoveryError(
                "error.repositoryImport.discovery.package.invalid"
            )
        candidates.append(
            RepositorySkillCandidate(
                source_path=root or ".",
                detected_name=validation.metadata.name,
                detected_description=validation.metadata.description,
                source_version=validation.metadata.version,
                entries=entries,
                warnings=list(validation.warnings),
            )
        )
    return candidates
