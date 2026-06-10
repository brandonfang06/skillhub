from __future__ import annotations

from datetime import datetime
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.labels import SkillLabelMutationError, attach_skill_label, detach_skill_label
from app.main import create_app


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: int | None = None) -> None:
        self.rows = rows or []
        self.scalar = scalar

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)

    def scalar_one(self) -> int:
        return self.scalar if self.scalar is not None else len(self.rows)

    def scalar_one_or_none(self) -> int | None:
        if self.scalar is not None:
            return self.scalar
        return None


class FakeTransaction:
    def __init__(self, connection: "FakeSkillLabelConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeSkillLabelConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeSkillLabelConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeSkillLabelConnection:
    def __init__(self) -> None:
        self.skills: dict[tuple[str, str], dict[str, Any]] = {
            ("global", "demo"): {
                "id": 100,
                "namespace_id": 10,
                "namespace_slug": "global",
                "slug": "demo",
                "owner_id": "owner",
            }
        }
        self.labels: dict[str, dict[str, Any]] = {
            "featured": {"id": 20, "slug": "featured", "type": "RECOMMENDED", "created_at": datetime(2026, 6, 10)},
            "privileged": {"id": 21, "slug": "privileged", "type": "PRIVILEGED", "created_at": datetime(2026, 6, 10)},
        }
        self.translations: dict[int, list[dict[str, Any]]] = {
            20: [{"label_id": 20, "locale": "en", "display_name": "Featured"}],
            21: [{"label_id": 21, "locale": "en", "display_name": "Privileged"}],
        }
        self.namespace_roles: dict[tuple[int, str], str] = {(10, "namespace-admin"): "ADMIN"}
        self.skill_labels: list[dict[str, Any]] = []
        self.audit_logs: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = " ".join(str(statement).split())
        bound = params or {}
        if "FROM skill s" in sql and "JOIN namespace n" in sql:
            row = self.skills.get((str(bound["namespace"]), str(bound["slug"])))
            return FakeResult(rows=[row.copy()] if row else [])
        if "FROM label_definition" in sql and "LOWER(slug)" in sql:
            row = self.labels.get(str(bound["label_slug"]).lower())
            return FakeResult(rows=[row.copy()] if row else [])
        if "FROM namespace_member" in sql:
            role = self.namespace_roles.get((int(bound["namespace_id"]), str(bound["user_id"])))
            return FakeResult(rows=[{"role": role}] if role else [])
        if "SELECT COUNT(*)" in sql and "FROM skill_label" in sql:
            count = sum(1 for row in self.skill_labels if int(row["skill_id"]) == int(bound["skill_id"]))
            return FakeResult(scalar=count)
        if sql.startswith("DELETE FROM skill_label"):
            self.skill_labels = [
                row
                for row in self.skill_labels
                if not (int(row["skill_id"]) == int(bound["skill_id"]) and int(row["label_id"]) == int(bound["label_id"]))
            ]
            return FakeResult()
        if "FROM skill_label" in sql and "skill_id = :skill_id" in sql and "label_id = :label_id" in sql:
            rows = [
                row.copy()
                for row in self.skill_labels
                if int(row["skill_id"]) == int(bound["skill_id"]) and int(row["label_id"]) == int(bound["label_id"])
            ]
            return FakeResult(rows=rows)
        if sql.startswith("INSERT INTO skill_label"):
            row = {
                "id": len(self.skill_labels) + 1,
                "skill_id": int(bound["skill_id"]),
                "label_id": int(bound["label_id"]),
                "created_by": bound["created_by"],
            }
            self.skill_labels.append(row)
            return FakeResult(rows=[row.copy()])
        if "FROM label_translation" in sql:
            label_ids = [int(value) for value in bound.get("label_ids", [])]
            rows: list[dict[str, Any]] = []
            for label_id in label_ids:
                rows.extend(row.copy() for row in self.translations.get(label_id, []))
            return FakeResult(rows=rows)
        if sql.startswith("INSERT INTO audit_log"):
            self.audit_logs.append(dict(bound))
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.anyio
async def test_attach_skill_label_inserts_label_and_writes_java_audit_detail() -> None:
    connection = FakeSkillLabelConnection()
    result = await attach_skill_label(
        FakeEngine(connection),
        namespace="global",
        slug="demo",
        label_slug=" Featured ",
        actor_user_id="owner",
        platform_roles=["USER"],
        request_id="req-label",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )

    assert result == {"slug": "featured", "type": "RECOMMENDED", "displayName": "Featured"}
    assert connection.skill_labels == [{"id": 1, "skill_id": 100, "label_id": 20, "created_by": "owner"}]
    assert connection.audit_logs[-1]["action"] == "SKILL_LABEL_ATTACH"
    assert connection.audit_logs[-1]["target_type"] == "SKILL"
    assert connection.audit_logs[-1]["target_id"] == 100
    assert json.loads(connection.audit_logs[-1]["detail_json"]) == {"labelSlug": " Featured "}


@pytest.mark.anyio
async def test_attach_skill_label_is_idempotent_and_enforces_permissions() -> None:
    connection = FakeSkillLabelConnection()
    connection.skill_labels.append({"id": 1, "skill_id": 100, "label_id": 20, "created_by": "owner"})

    result = await attach_skill_label(
        FakeEngine(connection),
        namespace="global",
        slug="demo",
        label_slug="featured",
        actor_user_id="namespace-admin",
        platform_roles=["USER"],
        request_id=None,
        client_ip=None,
        user_agent=None,
    )

    assert result["slug"] == "featured"
    assert len(connection.skill_labels) == 1

    with pytest.raises(SkillLabelMutationError, match="label.skill.no_permission"):
        await attach_skill_label(
            FakeEngine(connection),
            namespace="global",
            slug="demo",
            label_slug="privileged",
            actor_user_id="owner",
            platform_roles=["USER"],
            request_id=None,
            client_ip=None,
            user_agent=None,
        )


@pytest.mark.anyio
async def test_attach_skill_label_rejects_too_many_labels() -> None:
    connection = FakeSkillLabelConnection()
    connection.skill_labels = [{"id": index, "skill_id": 100, "label_id": 1000 + index, "created_by": "owner"} for index in range(10)]

    with pytest.raises(SkillLabelMutationError, match="label.skill.too_many"):
        await attach_skill_label(
            FakeEngine(connection),
            namespace="global",
            slug="demo",
            label_slug="featured",
            actor_user_id="owner",
            platform_roles=["USER"],
            request_id=None,
            client_ip=None,
            user_agent=None,
        )


@pytest.mark.anyio
async def test_detach_skill_label_deletes_existing_label_and_audits() -> None:
    connection = FakeSkillLabelConnection()
    connection.skill_labels.append({"id": 1, "skill_id": 100, "label_id": 20, "created_by": "owner"})

    result = await detach_skill_label(
        FakeEngine(connection),
        namespace="global",
        slug="demo",
        label_slug="featured",
        actor_user_id="owner",
        platform_roles=["USER"],
        request_id="req-detach",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )

    assert result == {"message": "Label detached"}
    assert connection.skill_labels == []
    assert connection.audit_logs[-1]["action"] == "SKILL_LABEL_DETACH"
    assert json.loads(connection.audit_logs[-1]["detail_json"]) == {"labelSlug": "featured"}

    with pytest.raises(SkillLabelMutationError, match="label.skill.not_found"):
        await detach_skill_label(
            FakeEngine(connection),
            namespace="global",
            slug="demo",
            label_slug="featured",
            actor_user_id="owner",
            platform_roles=["USER"],
            request_id=None,
            client_ip=None,
            user_agent=None,
        )


def test_skill_label_mutation_routes_use_java_envelopes_and_auth() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": {"super-admin": ["SUPER_ADMIN"]}.get(user_id, ["USER"]),
    }
    app.state.skill_label_attach_writer = lambda namespace, slug, label_slug, user, request_meta: {
        "slug": label_slug,
        "type": "RECOMMENDED",
        "displayName": "Featured",
    }
    app.state.skill_label_detach_writer = lambda namespace, slug, label_slug, user, request_meta: {
        "message": "Label detached",
    }
    client = TestClient(app)

    assert client.put("/api/v1/skills/global/demo/labels/featured").status_code == 401

    attached = client.put(
        "/api/v1/skills/global/demo/labels/featured",
        headers={"X-Mock-User-Id": "owner", "X-Request-Id": "req-route"},
    )
    assert attached.status_code == 200
    assert attached.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert attached.json()["requestId"] == "req-route"
    assert attached.json()["data"] == {"slug": "featured", "type": "RECOMMENDED", "displayName": "Featured"}

    detached = client.delete("/api/web/skills/global/demo/labels/featured", headers={"X-Mock-User-Id": "super-admin"})
    assert detached.status_code == 200
    assert detached.json()["msg"] == "\u5220\u9664\u6210\u529f"
    assert detached.json()["data"] == {"message": "Label detached"}
