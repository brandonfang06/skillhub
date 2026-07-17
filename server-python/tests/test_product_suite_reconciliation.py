from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.integrations.product_suite.contracts import ProductSuiteOwnerRecord
from app.integrations.product_suite.repository import reconcile_product_suite_admins
from tests.support.builders import namespace_row
from tests.support.fake_db import FakeResult, normalized_sql


def owner_record(
    external_suite_id: str,
    namespace_slug: str,
    owner_windows_account: str,
) -> ProductSuiteOwnerRecord:
    return ProductSuiteOwnerRecord.create(
        external_suite_id=external_suite_id,
        namespace_slug=namespace_slug,
        owner_windows_account=owner_windows_account,
    )


def user_identity(
    user_id: str,
    *,
    login_name: str,
    status: str = "ACTIVE",
    merged_to_user_id: str | None = None,
    binding_id: int = 1,
) -> dict[str, Any]:
    return {
        "id": binding_id,
        "user_id": user_id,
        "login_name": login_name,
        "status": status,
        "merged_to_user_id": merged_to_user_id,
    }


class ProductSuiteTransaction:
    def __init__(self, connection: "ProductSuiteConnection") -> None:
        self.connection = connection
        self.memberships_before: dict[tuple[int, str], str] = {}

    async def __aenter__(self) -> "ProductSuiteConnection":
        self.memberships_before = deepcopy(self.connection.memberships)
        self.connection.transaction_started = True
        return self.connection

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        tb: object,
    ) -> None:
        if exc_type is not None:
            self.connection.memberships = self.memberships_before
            self.connection.rolled_back = True
        else:
            self.connection.committed = True


class ProductSuiteEngine:
    def __init__(self, connection: "ProductSuiteConnection") -> None:
        self.connection = connection
        self.begin_calls = 0

    def begin(self) -> ProductSuiteTransaction:
        self.begin_calls += 1
        return ProductSuiteTransaction(self.connection)


class ProductSuiteConnection:
    def __init__(
        self,
        *,
        namespaces: dict[str, dict[str, Any]] | None = None,
        identities: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
        memberships: dict[tuple[int, str], str] | None = None,
        fail_on_write_number: int | None = None,
        insert_race_role: str | None = None,
    ) -> None:
        self.namespaces = namespaces or {}
        self.identities = identities or {}
        self.memberships = memberships or {}
        self.fail_on_write_number = fail_on_write_number
        self.insert_race_role = insert_race_role
        self.write_count = 0
        self.statements: list[str] = []
        self.transaction_started = False
        self.committed = False
        self.rolled_back = False

    async def execute(
        self,
        statement: object,
        params: dict[str, Any] | None = None,
    ) -> FakeResult:
        sql = normalized_sql(statement)
        bound = params or {}
        self.statements.append(sql)

        if sql.startswith("SELECT id, slug, status, type FROM namespace"):
            namespace = self.namespaces.get(str(bound["slug"]))
            return FakeResult(row=namespace.copy()) if namespace else FakeResult()

        if sql.startswith("SELECT ib.id, ib.user_id, ib.login_name"):
            key = (
                str(bound["provider_code"]),
                str(bound["login_name"]).casefold(),
            )
            return FakeResult(rows=deepcopy(self.identities.get(key, [])))

        if sql.startswith("SELECT role FROM namespace_member"):
            role = self.memberships.get(
                (int(bound["namespace_id"]), str(bound["user_id"]))
            )
            return FakeResult(row={"role": role}) if role else FakeResult()

        if sql.startswith("INSERT INTO namespace_member"):
            self._before_write()
            key = (int(bound["namespace_id"]), str(bound["user_id"]))
            if self.insert_race_role is not None and key not in self.memberships:
                self.memberships[key] = self.insert_race_role
                return FakeResult(rowcount=0)
            if key in self.memberships:
                return FakeResult(rowcount=0)
            self.memberships[key] = "ADMIN"
            return FakeResult(rowcount=1)

        if sql.startswith("UPDATE namespace_member"):
            self._before_write()
            key = (int(bound["namespace_id"]), str(bound["user_id"]))
            if self.memberships.get(key) != "MEMBER":
                return FakeResult(rowcount=0)
            self.memberships[key] = "ADMIN"
            return FakeResult(rowcount=1)

        raise AssertionError(f"unexpected SQL: {sql}")

    def _before_write(self) -> None:
        self.write_count += 1
        if self.write_count == self.fail_on_write_number:
            raise RuntimeError("database write failed")


def active_namespaces(*slugs: str) -> dict[str, dict[str, Any]]:
    return {
        slug: namespace_row(id=index, slug=slug)
        for index, slug in enumerate(slugs, start=10)
    }


def identities(
    *values: tuple[str, str],
    provider: str = "keycloak",
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    return {
        (provider, account.casefold()): [
            user_identity(
                user_id,
                login_name=account,
                binding_id=index,
            )
        ]
        for index, (account, user_id) in enumerate(values, start=1)
    }


@pytest.mark.anyio
async def test_reconcile_adds_and_promotes_product_suite_admins() -> None:
    connection = ProductSuiteConnection(
        namespaces=active_namespaces("product-a", "product-b"),
        identities=identities(("hcfange", "user-a"), ("alice", "user-b")),
        memberships={(11, "user-b"): "MEMBER"},
    )

    summary = await reconcile_product_suite_admins(
        ProductSuiteEngine(connection),
        records=[
            owner_record("suite-a", "product-a", "HCFange"),
            owner_record("suite-b", "product-b", "alice"),
        ],
        identity_provider="keycloak",
        dry_run=False,
    )

    assert connection.memberships[(10, "user-a")] == "ADMIN"
    assert connection.memberships[(11, "user-b")] == "ADMIN"
    assert summary.administrators_added == 1
    assert summary.members_promoted == 1
    assert summary.namespaces_resolved == 2
    assert connection.committed is True


@pytest.mark.anyio
async def test_reconcile_dry_run_reports_without_writing() -> None:
    connection = ProductSuiteConnection(
        namespaces=active_namespaces("product-a", "product-b"),
        identities=identities(("hcfange", "user-a"), ("alice", "user-b")),
        memberships={(11, "user-b"): "MEMBER"},
    )

    summary = await reconcile_product_suite_admins(
        ProductSuiteEngine(connection),
        records=[
            owner_record("suite-a", "product-a", "hcfange"),
            owner_record("suite-b", "product-b", "alice"),
        ],
        identity_provider="keycloak",
        dry_run=True,
    )

    assert summary.dry_run is True
    assert summary.administrators_added == 1
    assert summary.members_promoted == 1
    assert connection.memberships == {(11, "user-b"): "MEMBER"}
    assert connection.write_count == 0


@pytest.mark.anyio
async def test_reconcile_waits_for_owner_to_log_in_without_an_issue() -> None:
    connection = ProductSuiteConnection(
        namespaces=active_namespaces("product-a"),
    )

    summary = await reconcile_product_suite_admins(
        ProductSuiteEngine(connection),
        records=[owner_record("suite-a", "product-a", "future-user")],
        identity_provider="keycloak",
        dry_run=False,
    )

    assert summary.waiting_for_login == 1
    assert summary.issues == []
    assert connection.memberships == {}


@pytest.mark.anyio
async def test_reconcile_fails_closed_for_duplicate_active_identities() -> None:
    connection = ProductSuiteConnection(
        namespaces=active_namespaces("product-a"),
        identities={
            ("keycloak", "shared"): [
                user_identity(
                    "user-a",
                    login_name="shared",
                    binding_id=1,
                ),
                user_identity(
                    "user-b",
                    login_name="SHARED",
                    binding_id=2,
                ),
            ]
        },
    )

    summary = await reconcile_product_suite_admins(
        ProductSuiteEngine(connection),
        records=[owner_record("suite-a", "product-a", "Shared")],
        identity_provider="keycloak",
        dry_run=False,
    )

    assert summary.identity_conflicts == 1
    assert [issue.code for issue in summary.issues] == ["IDENTITY_CONFLICT"]
    assert connection.memberships == {}


@pytest.mark.parametrize(
    "identity",
    [
        user_identity(
            "user-a",
            login_name="hcfange",
            status="DISABLED",
        ),
        user_identity(
            "user-a",
            login_name="hcfange",
            status="MERGED",
            merged_to_user_id="user-primary",
        ),
    ],
)
@pytest.mark.anyio
async def test_reconcile_skips_disabled_or_merged_users(
    identity: dict[str, Any],
) -> None:
    connection = ProductSuiteConnection(
        namespaces=active_namespaces("product-a"),
        identities={("keycloak", "hcfange"): [identity]},
    )

    summary = await reconcile_product_suite_admins(
        ProductSuiteEngine(connection),
        records=[owner_record("suite-a", "product-a", "hcfange")],
        identity_provider="keycloak",
        dry_run=False,
    )

    assert summary.blocked == 1
    assert [issue.code for issue in summary.issues] == ["USER_BLOCKED"]
    assert connection.memberships == {}


@pytest.mark.parametrize(
    ("namespace", "issue_code"),
    [
        (None, "NAMESPACE_NOT_FOUND"),
        (namespace_row(slug="product-a", status="FROZEN"), "NAMESPACE_BLOCKED"),
        (namespace_row(slug="product-a", status="ARCHIVED"), "NAMESPACE_BLOCKED"),
        (
            namespace_row(slug="product-a", status="ACTIVE", type="GLOBAL"),
            "NAMESPACE_BLOCKED",
        ),
    ],
)
@pytest.mark.anyio
async def test_reconcile_skips_missing_or_readonly_namespaces(
    namespace: dict[str, Any] | None,
    issue_code: str,
) -> None:
    connection = ProductSuiteConnection(
        namespaces={"product-a": namespace} if namespace else {},
        identities=identities(("hcfange", "user-a")),
    )

    summary = await reconcile_product_suite_admins(
        ProductSuiteEngine(connection),
        records=[owner_record("suite-a", "product-a", "hcfange")],
        identity_provider="keycloak",
        dry_run=False,
    )

    assert summary.blocked == 1
    assert [issue.code for issue in summary.issues] == [issue_code]
    assert connection.memberships == {}


@pytest.mark.anyio
async def test_reconcile_preserves_admin_and_owner_and_is_idempotent() -> None:
    connection = ProductSuiteConnection(
        namespaces=active_namespaces("product-a", "product-b"),
        identities=identities(("hcfange", "user-a"), ("alice", "user-b")),
        memberships={
            (10, "user-a"): "ADMIN",
            (11, "user-b"): "OWNER",
        },
    )
    engine = ProductSuiteEngine(connection)
    records = [
        owner_record("suite-a", "product-a", "hcfange"),
        owner_record("suite-b", "product-b", "alice"),
    ]

    first = await reconcile_product_suite_admins(
        engine,
        records=records,
        identity_provider="keycloak",
        dry_run=False,
    )
    second = await reconcile_product_suite_admins(
        engine,
        records=records,
        identity_provider="keycloak",
        dry_run=False,
    )

    assert first.memberships_unchanged == 2
    assert second.memberships_unchanged == 2
    assert connection.memberships == {
        (10, "user-a"): "ADMIN",
        (11, "user-b"): "OWNER",
    }
    assert connection.write_count == 0


@pytest.mark.anyio
async def test_reconcile_rereads_membership_after_insert_race() -> None:
    connection = ProductSuiteConnection(
        namespaces=active_namespaces("product-a"),
        identities=identities(("hcfange", "user-a")),
        insert_race_role="ADMIN",
    )

    summary = await reconcile_product_suite_admins(
        ProductSuiteEngine(connection),
        records=[owner_record("suite-a", "product-a", "hcfange")],
        identity_provider="keycloak",
        dry_run=False,
    )

    assert connection.memberships == {(10, "user-a"): "ADMIN"}
    assert summary.memberships_unchanged == 1
    assert summary.administrators_added == 0


@pytest.mark.anyio
async def test_reconcile_rolls_back_all_memberships_on_database_failure() -> None:
    connection = ProductSuiteConnection(
        namespaces=active_namespaces("product-a", "product-b"),
        identities=identities(("hcfange", "user-a"), ("alice", "user-b")),
        fail_on_write_number=2,
    )

    with pytest.raises(RuntimeError, match="database write failed"):
        await reconcile_product_suite_admins(
            ProductSuiteEngine(connection),
            records=[
                owner_record("suite-a", "product-a", "hcfange"),
                owner_record("suite-b", "product-b", "alice"),
            ],
            identity_provider="keycloak",
            dry_run=False,
        )

    assert connection.memberships == {}
    assert connection.rolled_back is True
