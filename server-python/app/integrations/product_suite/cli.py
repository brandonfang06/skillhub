from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import json
import sys
from typing import Any

from app.core.config import Settings, get_settings
from app.core.database import create_database_engine, dispose_database_engine
from app.integrations.product_suite.contracts import (
    ProductSuiteSourceError,
    ProductSuiteSyncConfig,
    ProductSuiteSyncIssue,
    ProductSuiteSyncSummary,
    validate_snapshot,
)
from app.integrations.product_suite.repository import (
    reconcile_product_suite_admins,
)
from app.integrations.product_suite.source import (
    ProductSuiteSource,
    load_product_suite_source,
    product_suite_sync_config,
)


SourceLoader = Callable[[str], ProductSuiteSource]
EngineFactory = Callable[[Settings], Any]


def _issue_payload(issue: ProductSuiteSyncIssue) -> dict[str, Any]:
    return {
        "externalSuiteId": issue.external_suite_id,
        "namespaceSlug": issue.namespace_slug,
        "ownerWindowsAccount": issue.owner_windows_account,
        "code": issue.code,
        "detail": issue.detail,
    }


def _summary_payload(summary: ProductSuiteSyncSummary) -> dict[str, Any]:
    return {
        "suitesFetched": summary.suites_fetched,
        "namespacesResolved": summary.namespaces_resolved,
        "administratorsAdded": summary.administrators_added,
        "membersPromoted": summary.members_promoted,
        "membershipsUnchanged": summary.memberships_unchanged,
        "waitingForLogin": summary.waiting_for_login,
        "blocked": summary.blocked,
        "identityConflicts": summary.identity_conflicts,
        "issues": [_issue_payload(issue) for issue in summary.issues],
        "dryRun": summary.dry_run,
    }


@dataclass(frozen=True)
class ProductSuiteCommandResult:
    exit_code: int
    status: str
    summary: ProductSuiteSyncSummary | None = None
    error_detail: str = ""

    @classmethod
    def from_summary(
        cls,
        summary: ProductSuiteSyncSummary,
    ) -> ProductSuiteCommandResult:
        needs_attention = bool(
            summary.blocked
            or summary.identity_conflicts
            or summary.issues
        )
        return cls(
            exit_code=1 if needs_attention else 0,
            status="attention" if needs_attention else "ok",
            summary=summary,
        )

    @classmethod
    def fatal(cls, detail: str) -> ProductSuiteCommandResult:
        return cls(
            exit_code=2,
            status="fatal",
            error_detail=detail,
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "exitCode": self.exit_code,
        }
        if self.summary is not None:
            payload["summary"] = _summary_payload(self.summary)
        else:
            payload["error"] = {
                "code": "PRODUCT_SUITE_SYNC_FAILED",
                "detail": self.error_detail,
            }
        return payload


async def run_product_suite_sync(
    *,
    config: ProductSuiteSyncConfig,
    source_loader: SourceLoader = load_product_suite_source,
    engine_factory: EngineFactory = create_database_engine,
) -> ProductSuiteCommandResult:
    engine: Any | None = None
    try:
        fetcher = source_loader(config.source_module)
        try:
            fetched_records = await asyncio.wait_for(
                fetcher(config.source),
                timeout=config.source.timeout_seconds,
            )
        except TimeoutError as exc:
            raise ProductSuiteSourceError(
                "product suite source timed out after "
                f"{config.source.timeout_seconds:g} seconds"
            ) from exc
        records = validate_snapshot(fetched_records)
        engine = engine_factory(get_settings())
        summary = await reconcile_product_suite_admins(
            engine,
            records=records,
            identity_provider=config.identity_provider,
            dry_run=config.dry_run,
        )
        result = ProductSuiteCommandResult.from_summary(summary)
    except Exception as exc:
        result = ProductSuiteCommandResult.fatal(str(exc))

    if engine is not None:
        try:
            await dispose_database_engine(engine)
        except Exception as exc:
            return ProductSuiteCommandResult.fatal(
                f"database engine disposal failed: {exc}"
            )
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        config = product_suite_sync_config(
            sys.argv[1:] if argv is None else argv
        )
        result = asyncio.run(run_product_suite_sync(config=config))
    except Exception as exc:
        result = ProductSuiteCommandResult.fatal(str(exc))

    print(
        json.dumps(
            result.to_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    if result.exit_code == 2:
        print(
            f"product suite admin sync failed: {result.error_detail}",
            file=sys.stderr,
        )
    return result.exit_code
