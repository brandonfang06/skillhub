from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.publish.package import PackageEntry, SkillMetadata


SourceRefType = Literal["TAG", "BRANCH", "COMMIT"]
SourceImportPlanOutcome = Literal["IMPORT", "SKIPPED_UNCHANGED", "SKIPPED_ALREADY_IMPORTED"]
SourceImportOutcome = Literal["IMPORTED", "SKIPPED_UNCHANGED", "SKIPPED_ALREADY_IMPORTED"]


@dataclass(frozen=True)
class SourceRepository:
    owner: str
    repository: str
    canonical_url: str
    namespace_slug: str
    namespace_display_name: str


@dataclass(frozen=True)
class SourceRevision:
    commit_sha: str
    ref_type: SourceRefType
    ref: str | None


@dataclass(frozen=True)
class SourceIdentity:
    provider_code: str
    login_name: str


@dataclass(frozen=True)
class SourcePackage:
    source_path: str
    entries: list[PackageEntry]
    metadata: SkillMetadata
    content_fingerprint: str
    effective_version: str


@dataclass(frozen=True)
class SourceProvenance:
    repository_url: str
    repository_revision_sha: str
    source_ref_type: SourceRefType
    source_ref: str | None
    source_path: str
    content_fingerprint: str
    browse_url: str
