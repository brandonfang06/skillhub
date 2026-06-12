from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin.labels import (
    AdminLabelError,
    create_label_definition,
    delete_label_definition,
    list_label_definitions,
    update_label_definition,
    update_label_sort_order,
)
from app.main import create_app


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, row: dict[str, Any] | None = None) -> None:
        self.rows = rows if rows is not None else ([row] if row is not None else [])

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)

    def scalar_one(self) -> int:
        return int(self.rows[0]["count"])


class FakeTransaction:
    def __init__(self, connection: "FakeLabelConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeLabelConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeConnect(FakeTransaction):
    pass


class FakeEngine:
    def __init__(self, connection: "FakeLabelConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


class FakeLabelConnection:
    def __init__(self, labels: dict[str, dict[str, Any]] | None = None) -> None:
        self.labels = labels or {}
        self.translations: dict[int, list[dict[str, Any]]] = {
            int(row["id"]): list(row.get("translations", [])) for row in self.labels.values()
        }
        self.next_id = max((int(row["id"]) for row in self.labels.values()), default=0)
        self.audit_rows: list[dict[str, Any]] = []
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        self.statements.append(sql)
        self.params.append(bound)
        if "COUNT(*)" in sql and "FROM label_definition" in sql:
            return FakeResult(row={"count": len(self.labels)})
        if "FROM label_definition" in sql and "LOWER(slug)" in sql:
            row = self.labels.get(str(bound["slug"]).lower())
            return FakeResult(row=self._without_embedded_translations(row)) if row else FakeResult()
        if "FROM label_definition" in sql and "ORDER BY sort_order" in sql:
            rows = sorted((self._without_embedded_translations(row) for row in self.labels.values()), key=lambda row: (row["sort_order"], row["id"]))
            return FakeResult(rows=rows)
        if "INSERT INTO label_definition" in sql:
            self.next_id += 1
            row = label_row(
                id=self.next_id,
                slug=bound["slug"],
                type=bound["type"],
                visible_in_filter=bound["visible_in_filter"],
                sort_order=bound["sort_order"],
                created_by=bound["created_by"],
            )
            self.labels[str(bound["slug"])] = row
            return FakeResult(row=self._without_embedded_translations(row))
        if "UPDATE label_definition" in sql:
            row = self._label_by_id(int(bound["label_id"]))
            if "type" in bound:
                row["type"] = bound["type"]
            if "visible_in_filter" in bound:
                row["visible_in_filter"] = bound["visible_in_filter"]
            if "sort_order" in bound:
                row["sort_order"] = bound["sort_order"]
            row["updated_at"] = datetime(2026, 6, 10, 9, 30, tzinfo=UTC)
            return FakeResult(row=self._without_embedded_translations(row))
        if "DELETE FROM label_translation" in sql:
            self.translations[int(bound["label_id"])] = []
            return FakeResult()
        if "INSERT INTO label_translation" in sql:
            self.translations.setdefault(int(bound["label_id"]), []).append(
                {"label_id": int(bound["label_id"]), "locale": bound["locale"], "display_name": bound["display_name"]}
            )
            return FakeResult()
        if "FROM label_translation" in sql and "label_id = ANY" in sql:
            label_ids = [int(value) for value in bound["label_ids"]]
            rows: list[dict[str, Any]] = []
            for label_id in label_ids:
                rows.extend(self.translations.get(label_id, []))
            return FakeResult(rows=rows)
        if "FROM label_translation" in sql and "label_id = :label_id" in sql:
            return FakeResult(rows=list(self.translations.get(int(bound["label_id"]), [])))
        if "DELETE FROM label_definition" in sql:
            row = self._label_by_id(int(bound["label_id"]))
            self.labels.pop(str(row["slug"]), None)
            self.translations.pop(int(bound["label_id"]), None)
            return FakeResult()
        if "INSERT INTO audit_log" in sql:
            self.audit_rows.append(bound.copy())
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")

    def _label_by_id(self, label_id: int) -> dict[str, Any]:
        for row in self.labels.values():
            if int(row["id"]) == label_id:
                return row
        raise AssertionError(f"unknown label id {label_id}")

    def _without_embedded_translations(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {key: value for key, value in row.items() if key != "translations"}


def label_row(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 1,
        "slug": "featured",
        "type": "RECOMMENDED",
        "visible_in_filter": True,
        "sort_order": 10,
        "created_by": "admin",
        "created_at": datetime(2026, 6, 10, 8, 5, tzinfo=UTC),
        "updated_at": datetime(2026, 6, 10, 8, 6, tzinfo=UTC),
        "translations": [{"label_id": 1, "locale": "en", "display_name": "Featured"}],
    }
    data.update(overrides)
    return data


def auth_user(user_id: str = "admin", roles: list[str] | None = None) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": roles or ["SUPER_ADMIN"],
    }


def bearer_user(user_id: str = "token-admin", roles: list[str] | None = None) -> dict[str, object]:
    data = auth_user(user_id, roles or ["SUPER_ADMIN"])
    data["oauthProvider"] = "api_token"
    data["tokenScopes"] = ["skill:read", "skill:publish", "skill:delete", "token:manage"]
    return data


@pytest.mark.anyio
async def test_create_label_normalizes_translations_and_writes_audit() -> None:
    connection = FakeLabelConnection()

    response = await create_label_definition(
        FakeEngine(connection),
        slug=" Featured ",
        type="RECOMMENDED",
        visible_in_filter=True,
        sort_order=5,
        translations=[{"locale": " en_US ", "displayName": " Featured "}],
        actor_user_id="admin",
        platform_roles=["SUPER_ADMIN"],
        request_id="req-create",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )

    assert response["slug"] == "featured"
    assert response["translations"] == [{"locale": "en-us", "displayName": "Featured"}]
    assert connection.audit_rows[-1]["action"] == "LABEL_CREATE"
    assert connection.audit_rows[-1]["detail_json"] == '{"slug":"featured"}'

    with pytest.raises(AdminLabelError, match="label.definition.no_permission") as forbidden:
        await create_label_definition(
            FakeEngine(FakeLabelConnection()),
            slug="other",
            type="RECOMMENDED",
            visible_in_filter=True,
            sort_order=0,
            translations=[{"locale": "en", "displayName": "Other"}],
            actor_user_id="user",
            platform_roles=["USER"],
            request_id=None,
            client_ip=None,
            user_agent=None,
        )
    assert forbidden.value.status_code == 403


@pytest.mark.anyio
async def test_update_delete_and_sort_order_match_java_contract() -> None:
    connection = FakeLabelConnection(
        {
            "featured": label_row(id=1, slug="featured", sort_order=10),
            "security": label_row(id=2, slug="security", sort_order=20, translations=[{"label_id": 2, "locale": "en", "display_name": "Security"}]),
        }
    )

    updated = await update_label_definition(
        FakeEngine(connection),
        slug="FEATURED",
        type="PRIVILEGED",
        visible_in_filter=False,
        sort_order=3,
        translations=[{"locale": "zh_TW", "displayName": " 精選 "}],
        actor_user_id="admin",
        platform_roles=["SUPER_ADMIN"],
        request_id="req-update",
        client_ip=None,
        user_agent=None,
    )

    assert updated["type"] == "PRIVILEGED"
    assert updated["visibleInFilter"] is False
    assert updated["translations"] == [{"locale": "zh-tw", "displayName": "精選"}]
    assert connection.audit_rows[-1]["action"] == "LABEL_UPDATE"

    sorted_labels = await update_label_sort_order(
        FakeEngine(connection),
        items=[{"slug": "security", "sortOrder": 1}, {"slug": "featured", "sortOrder": 2}],
        actor_user_id="admin",
        platform_roles=["SUPER_ADMIN"],
        request_id="req-sort",
        client_ip=None,
        user_agent=None,
    )

    assert [label["slug"] for label in sorted_labels] == ["featured", "security"]
    assert [label["sortOrder"] for label in sorted_labels] == [2, 1]
    assert connection.audit_rows[-1]["action"] == "LABEL_SORT_ORDER_UPDATE"
    assert connection.audit_rows[-1]["detail_json"] == '{"count":2}'

    deleted = await delete_label_definition(
        FakeEngine(connection),
        slug="security",
        actor_user_id="admin",
        platform_roles=["SUPER_ADMIN"],
        request_id="req-delete",
        client_ip=None,
        user_agent=None,
    )

    assert deleted == {"message": "Label deleted"}
    assert "security" not in connection.labels
    assert connection.audit_rows[-1]["action"] == "LABEL_DELETE"


@pytest.mark.anyio
async def test_list_label_definitions_sorts_and_includes_translations() -> None:
    connection = FakeLabelConnection(
        {
            "zeta": label_row(id=1, slug="zeta", sort_order=20),
            "alpha": label_row(id=2, slug="alpha", sort_order=10, translations=[{"label_id": 2, "locale": "en", "display_name": "Alpha"}]),
        }
    )

    response = await list_label_definitions(FakeEngine(connection), platform_roles=["SUPER_ADMIN"])

    assert [label["slug"] for label in response] == ["alpha", "zeta"]
    assert response[0]["translations"] == [{"locale": "en", "displayName": "Alpha"}]


def test_admin_label_routes_use_java_envelopes_and_auth() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id, ["SUPER_ADMIN"] if user_id == "admin" else ["USER"])
    app.state.admin_label_reader = lambda user: [{"slug": "featured"}]
    app.state.admin_label_create_writer = lambda payload, user, request: {"slug": payload["slug"]}
    app.state.admin_label_update_writer = lambda slug, payload, user, request: {"slug": slug, "type": payload["type"]}
    app.state.admin_label_delete_writer = lambda slug, user, request: {"message": "Label deleted"}
    app.state.admin_label_sort_writer = lambda payload, user, request: [{"slug": item["slug"], "sortOrder": item["sortOrder"]} for item in payload["items"]]
    client = TestClient(app)

    assert client.get("/api/v1/admin/labels").status_code == 401
    assert client.get("/api/v1/admin/labels", headers={"X-Mock-User-Id": "user"}).status_code == 403

    listed = client.get("/api/v1/admin/labels", headers={"X-Mock-User-Id": "admin"})
    assert listed.status_code == 200
    assert listed.json()["msg"] == "获取成功"
    assert listed.json()["data"] == [{"slug": "featured"}]

    created = client.post(
        "/api/v1/admin/labels",
        json={"slug": "featured", "type": "RECOMMENDED", "visibleInFilter": True, "sortOrder": 1, "translations": [{"locale": "en", "displayName": "Featured"}]},
        headers={"X-Mock-User-Id": "admin"},
    )
    assert created.status_code == 200
    assert created.json()["msg"] == "创建成功"

    updated = client.put(
        "/api/v1/admin/labels/featured",
        json={"type": "PRIVILEGED", "visibleInFilter": False, "sortOrder": 2, "translations": [{"locale": "en", "displayName": "Featured"}]},
        headers={"X-Mock-User-Id": "admin"},
    )
    assert updated.status_code == 200
    assert updated.json()["msg"] == "更新成功"

    sorted_response = client.put(
        "/api/v1/admin/labels/sort-order",
        json={"items": [{"slug": "featured", "sortOrder": 9}]},
        headers={"X-Mock-User-Id": "admin"},
    )
    assert sorted_response.status_code == 200
    assert sorted_response.json()["data"] == [{"slug": "featured", "sortOrder": 9}]

    deleted = client.delete("/api/v1/admin/labels/featured", headers={"X-Mock-User-Id": "admin"})
    assert deleted.status_code == 200
    assert deleted.json()["msg"] == "删除成功"
    assert deleted.json()["data"]["message"] == "Label deleted"


def test_admin_label_routes_accept_super_admin_session() -> None:
    app = create_app()
    app.state.local_auth_login = lambda payload: auth_user("admin", ["SUPER_ADMIN"])
    app.state.admin_label_reader = lambda user: [{"slug": "featured"}]
    app.state.admin_label_create_writer = lambda payload, user, request: {"slug": payload["slug"]}
    client = TestClient(app)

    login = client.post("/api/v1/auth/local/login", json={"username": "admin", "password": "Admin@staging2026"})
    listed = client.get("/api/v1/admin/labels")
    created = client.post(
        "/api/v1/admin/labels",
        json={
            "slug": "featured",
            "type": "RECOMMENDED",
            "visibleInFilter": True,
            "sortOrder": 1,
            "translations": [{"locale": "en", "displayName": "Featured"}],
        },
    )

    assert login.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["data"] == [{"slug": "featured"}]
    assert created.status_code == 200
    assert created.json()["data"] == {"slug": "featured"}


def test_admin_label_routes_reject_api_token_principals_as_unsupported() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id, ["SUPER_ADMIN"])
    app.state.auth_bearer_reader = lambda raw_token: bearer_user() if raw_token == "sk_valid" else None
    app.state.admin_label_reader = lambda user: [{"slug": "featured"}]
    app.state.admin_label_create_writer = lambda payload, user, request: {"slug": payload["slug"]}
    client = TestClient(app)

    unsupported = client.get("/api/v1/admin/labels", headers={"Authorization": "Bearer sk_valid"})
    assert unsupported.status_code == 403
    assert unsupported.json()["detail"] == "API token cannot access endpoint: /api/v1/admin/labels"

    invalid = client.get("/api/v1/admin/labels", headers={"Authorization": "Bearer sk_missing"})
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "error.auth.required"

    mock_precedence = client.post(
        "/api/v1/admin/labels",
        json={"slug": "featured", "type": "SYSTEM", "visibleInFilter": True, "sortOrder": 1, "translations": []},
        headers={"X-Mock-User-Id": "admin", "Authorization": "Bearer sk_valid"},
    )
    assert mock_precedence.status_code == 200
