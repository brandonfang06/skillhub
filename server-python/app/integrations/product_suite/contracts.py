from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


class ProductSuiteSourceError(ValueError):
    pass


def _required_text(value: str, *, field_name: str, max_length: int | None = None) -> str:
    normalized = value.strip()
    if not normalized:
        raise ProductSuiteSourceError(f"{field_name} must not be empty")
    if max_length is not None and len(normalized) > max_length:
        raise ProductSuiteSourceError(
            f"{field_name} must not exceed {max_length} characters"
        )
    return normalized


@dataclass(frozen=True)
class ProductSuiteSourceConfig:
    api_url: str
    timeout_seconds: float


@dataclass(frozen=True)
class ProductSuiteOwnerRecord:
    external_suite_id: str
    namespace_slug: str
    owner_windows_account: str
    normalized_windows_account: str

    @classmethod
    def create(
        cls,
        *,
        external_suite_id: str,
        namespace_slug: str,
        owner_windows_account: str,
    ) -> ProductSuiteOwnerRecord:
        suite_id = _required_text(
            external_suite_id,
            field_name="external_suite_id",
        )
        slug = _required_text(
            namespace_slug,
            field_name="namespace_slug",
            max_length=64,
        )
        account = _required_text(
            owner_windows_account,
            field_name="owner_windows_account",
            max_length=128,
        )
        return cls(
            external_suite_id=suite_id,
            namespace_slug=slug,
            owner_windows_account=account,
            normalized_windows_account=account.casefold(),
        )


@dataclass(frozen=True)
class ProductSuiteSyncConfig:
    source_module: str
    source: ProductSuiteSourceConfig
    identity_provider: str
    dry_run: bool


@dataclass(frozen=True)
class ProductSuiteSyncIssue:
    external_suite_id: str
    namespace_slug: str
    owner_windows_account: str
    code: str
    detail: str


@dataclass
class ProductSuiteSyncSummary:
    suites_fetched: int = 0
    namespaces_resolved: int = 0
    administrators_added: int = 0
    members_promoted: int = 0
    memberships_unchanged: int = 0
    waiting_for_login: int = 0
    blocked: int = 0
    identity_conflicts: int = 0
    issues: list[ProductSuiteSyncIssue] = field(default_factory=list)
    dry_run: bool = False


def validate_snapshot(records: Sequence[Any]) -> tuple[ProductSuiteOwnerRecord, ...]:
    validated = tuple(records)
    if not validated:
        raise ProductSuiteSourceError("product suite snapshot must not be empty")

    suite_ids: set[str] = set()
    namespace_slugs: set[str] = set()
    for record in validated:
        if not isinstance(record, ProductSuiteOwnerRecord):
            raise ProductSuiteSourceError(
                "product suite snapshot values must be ProductSuiteOwnerRecord"
            )
        suite_id = record.external_suite_id.casefold()
        namespace_slug = record.namespace_slug.casefold()
        if suite_id in suite_ids:
            raise ProductSuiteSourceError(
                f"duplicate external_suite_id: {record.external_suite_id}"
            )
        if namespace_slug in namespace_slugs:
            raise ProductSuiteSourceError(
                f"duplicate namespace_slug: {record.namespace_slug}"
            )
        suite_ids.add(suite_id)
        namespace_slugs.add(namespace_slug)

    return validated
