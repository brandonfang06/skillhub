from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import RateLimitCategoryOverride
from app.main import create_app


RATE_LIMITED_ROUTE_CASES = [
    ("GET", "/api/v1/whoami", False),
    ("POST", "/api/v1/auth/direct/login", False),
    ("POST", "/api/v1/auth/session/bootstrap", False),
    ("POST", "/api/v1/stars/demo", False),
    ("DELETE", "/api/v1/stars/demo", False),
    ("POST", "/api/v1/auth/local/register", False),
    ("POST", "/api/v1/auth/local/login", False),
    ("POST", "/api/v1/auth/local/change-password", False),
    ("POST", "/api/v1/auth/local/password-reset/request", False),
    ("POST", "/api/v1/auth/local/password-reset/confirm", False),
    ("POST", "/api/cli/v1/skills/team-a/publish/validate", True),
    ("POST", "/api/web/skills/team-a/publish", True),
    ("POST", "/api/v1/skills/team-a/publish", True),
    ("POST", "/api/cli/v1/skills/team-a/publish", True),
    ("POST", "/api/v1/publish", False),
    ("POST", "/api/v1/skills", False),
    ("GET", "/api/v1/download?slug=demo", False),
    ("GET", "/api/v1/download/demo", False),
    ("GET", "/api/web/skills", False),
    ("GET", "/api/v1/search", False),
    ("GET", "/api/cli/v1/skills/search", False),
    ("GET", "/api/cli/v1/namespaces/team-a/skills", True),
    ("GET", "/api/v1/resolve?slug=demo", False),
    ("GET", "/api/cli/v1/skills/team-a/demo/resolve", False),
    ("GET", "/api/v1/resolve/demo", False),
    ("GET", "/api/v1/skills", False),
    ("GET", "/api/v1/skills/demo", False),
    ("DELETE", "/api/v1/skills/demo", False),
    ("POST", "/api/v1/skills/demo/undelete", False),
    ("GET", "/api/web/skills/team-a/demo/download", False),
    ("GET", "/api/v1/skills/team-a/demo/download", False),
    ("GET", "/api/web/skills/team-a/demo/versions/1.0.0/download", False),
    ("GET", "/api/v1/skills/team-a/demo/versions/1.0.0/download", False),
    ("GET", "/api/cli/v1/skills/team-a/demo/download", False),
    ("GET", "/api/cli/v1/skills/team-a/demo/versions/1.0.0/download", False),
    ("GET", "/api/web/skills/team-a/demo/tags/latest/download", False),
    ("GET", "/api/v1/skills/team-a/demo/tags/latest/download", False),
]


class SequenceRateLimitChecker:
    def __init__(self, decisions: list[bool]) -> None:
        self.decisions = list(decisions)
        self.calls: list[dict[str, object]] = []

    async def try_acquire(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
        member: str,
    ) -> bool:
        self.calls.append(
            {
                "key": key,
                "limit": limit,
                "window_seconds": window_seconds,
                "member": member,
            }
        )
        return self.decisions.pop(0)


def _empty_search() -> dict[str, object]:
    return {"items": [], "total": 0, "page": 0, "size": 20}


def test_enabled_rate_limit_returns_safe_429_before_second_search() -> None:
    app = create_app()
    checker = SequenceRateLimitChecker([True, False])
    app.state.settings = SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_overrides={},
    )
    app.state.rate_limit_checker = checker
    reader_calls: list[object] = []
    app.state.cli_skill_search_reader = lambda **kwargs: reader_calls.append(kwargs) or _empty_search()
    client = TestClient(app)

    allowed = client.get(
        "/api/cli/v1/skills/search",
        headers={"X-Request-Id": "rate-search-allowed"},
    )
    denied = client.get(
        "/api/cli/v1/skills/search",
        headers={"X-Request-Id": "rate-search-denied"},
    )

    assert allowed.status_code == 200
    assert denied.status_code == 429
    assert denied.headers["Retry-After"] == "60"
    assert denied.headers["X-Request-Id"] == "rate-search-denied"
    assert denied.json() == {
        "code": 429,
        "msg": "error.rateLimit.exceeded",
        "data": None,
        "timestamp": denied.json()["timestamp"],
        "requestId": "rate-search-denied",
    }
    assert len(reader_calls) == 1
    assert [call["limit"] for call in checker.calls] == [20, 20]
    assert [call["window_seconds"] for call in checker.calls] == [60, 60]
    assert checker.calls[0]["key"] == checker.calls[1]["key"]
    assert str(checker.calls[0]["key"]).startswith("ratelimit:search:ip:")
    assert "testclient" not in str(checker.calls[0]["key"])


def test_authenticated_rate_limit_uses_category_override_and_hashed_user_key() -> None:
    app = create_app()
    checker = SequenceRateLimitChecker([True])
    app.state.settings = SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_overrides={
            "search": RateLimitCategoryOverride(
                authenticated=7,
                anonymous=3,
                window_seconds=30,
            )
        },
    )
    app.state.rate_limit_checker = checker
    app.state.auth_bearer_reader = lambda token: {
        "userId": "rate-user",
        "oauthProvider": "api_token",
        "platformRoles": ["USER"],
        "tokenScopes": ["skill:read"],
    }
    app.state.cli_skill_search_reader = lambda **kwargs: _empty_search()
    client = TestClient(app)

    response = client.get(
        "/api/cli/v1/skills/search",
        headers={"Authorization": "Bearer sk_rate"},
    )

    assert response.status_code == 200
    assert checker.calls[0]["limit"] == 7
    assert checker.calls[0]["window_seconds"] == 30
    assert str(checker.calls[0]["key"]).startswith("ratelimit:search:user:")
    assert "rate-user" not in str(checker.calls[0]["key"])


def test_disabled_rate_limit_preserves_existing_unlimited_behavior() -> None:
    app = create_app()
    app.state.settings = SimpleNamespace(
        rate_limit_enabled=False,
        rate_limit_overrides={},
    )
    app.state.rate_limit_checker = SequenceRateLimitChecker([])
    app.state.cli_skill_search_reader = lambda **kwargs: _empty_search()
    client = TestClient(app)

    response = client.get("/api/cli/v1/skills/search")

    assert response.status_code == 200
    assert app.state.rate_limit_checker.calls == []


def test_disabled_rate_limit_does_not_load_unrelated_deployment_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SKILLHUB_RATELIMIT_ENABLED", raising=False)
    monkeypatch.delenv("SKILLHUB_WEB_BASE_PATH", raising=False)
    monkeypatch.setenv(
        "SKILLHUB_PUBLIC_BASE_URL",
        "https://skillhub.example/skillhub",
    )
    monkeypatch.setenv("SKILLHUB_SESSION_COOKIE_SECURE", "true")
    app = create_app()
    app.state.cli_skill_search_reader = lambda **kwargs: _empty_search()

    response = TestClient(app).get("/api/cli/v1/skills/search")

    assert response.status_code == 200


def test_enabled_rate_limit_fails_closed_when_redis_is_unavailable() -> None:
    app = create_app()

    class UnavailableChecker:
        async def try_acquire(self, **kwargs: object) -> bool:
            raise ConnectionError("redis unavailable")

    app.state.settings = SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_overrides={},
    )
    app.state.rate_limit_checker = UnavailableChecker()
    app.state.cli_skill_search_reader = lambda **kwargs: _empty_search()
    client = TestClient(app)

    response = client.get(
        "/api/cli/v1/skills/search",
        headers={"X-Request-Id": "rate-limit-unavailable"},
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    assert response.json()["msg"] == "error.rateLimit.unavailable"
    assert response.json()["requestId"] == "rate-limit-unavailable"


def test_local_login_uses_anonymous_auth_rate_limit() -> None:
    app = create_app()
    checker = SequenceRateLimitChecker([False])
    app.state.settings = SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_overrides={},
        local_registration_enabled=True,
    )
    app.state.rate_limit_checker = checker
    app.state.local_login_service = lambda **kwargs: pytest.fail(
        "denied login must not reach credential verification"
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/local/login",
        json={"username": "someone", "password": "wrong"},
    )

    assert response.status_code == 429
    assert checker.calls[0]["limit"] == 10
    assert checker.calls[0]["window_seconds"] == 60


def test_authenticated_download_uses_download_rate_limit_before_storage() -> None:
    app = create_app()
    checker = SequenceRateLimitChecker([False])
    app.state.settings = SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_overrides={},
    )
    app.state.rate_limit_checker = checker
    app.state.auth_bearer_reader = lambda token: {
        "userId": "download-user",
        "oauthProvider": "api_token",
        "platformRoles": ["USER"],
        "tokenScopes": ["skill:read"],
    }
    app.state.skill_download_latest_reader = lambda *args: pytest.fail(
        "denied download must not reach storage"
    )
    client = TestClient(app)

    response = client.get(
        "/api/cli/v1/skills/team-a/demo/download",
        headers={"Authorization": "Bearer sk_download"},
    )

    assert response.status_code == 429
    assert checker.calls[0]["limit"] == 120
    assert checker.calls[0]["window_seconds"] == 60
    assert ":resource:" in str(checker.calls[0]["key"])


def test_authenticated_namespace_manifest_uses_skills_rate_limit() -> None:
    app = create_app()
    checker = SequenceRateLimitChecker([False])
    app.state.settings = SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_overrides={},
    )
    app.state.rate_limit_checker = checker
    app.state.auth_bearer_reader = lambda token: {
        "userId": "manifest-user",
        "oauthProvider": "api_token",
        "platformRoles": ["USER"],
        "tokenScopes": ["skill:read"],
    }
    app.state.cli_namespace_manifest_reader = lambda **kwargs: pytest.fail(
        "anonymous manifest must not reach repository"
    )
    client = TestClient(app)

    response = client.get(
        "/api/cli/v1/namespaces/team-a/skills",
        headers={"Authorization": "Bearer sk_manifest"},
    )

    assert response.status_code == 429
    assert checker.calls[0]["limit"] == 60


def test_anonymous_zero_limit_preserves_protected_route_401_semantics() -> None:
    app = create_app()
    checker = SequenceRateLimitChecker([])
    app.state.settings = SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_overrides={},
    )
    app.state.rate_limit_checker = checker
    app.state.cli_namespace_manifest_reader = lambda **kwargs: pytest.fail(
        "anonymous manifest must not reach repository"
    )
    client = TestClient(app)

    response = client.get("/api/cli/v1/namespaces/team-a/skills")

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"
    assert checker.calls == []


@pytest.mark.parametrize("method,path,_anonymous_zero", RATE_LIMITED_ROUTE_CASES)
def test_every_rate_limited_alias_rejects_an_authenticated_request_at_limit(
    method: str,
    path: str,
    _anonymous_zero: bool,
) -> None:
    app = create_app()
    checker = SequenceRateLimitChecker([False])
    app.state.settings = SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_overrides={},
        local_registration_enabled=True,
    )
    app.state.rate_limit_checker = checker
    app.state.auth_bearer_reader = lambda token: {
        "userId": "all-alias-user",
        "oauthProvider": "api_token",
        "platformRoles": ["USER"],
        "tokenScopes": ["skill:read", "skill:publish"],
    }

    response = TestClient(app).request(
        method,
        path,
        headers={"Authorization": "Bearer sk_all_aliases"},
    )

    assert response.status_code == 429, (method, path, response.text)
    assert len(checker.calls) == 1


@pytest.mark.parametrize("method,path,anonymous_zero", RATE_LIMITED_ROUTE_CASES)
def test_every_rate_limited_alias_handles_anonymous_principal_at_limit(
    method: str,
    path: str,
    anonymous_zero: bool,
) -> None:
    app = create_app()
    checker = SequenceRateLimitChecker([] if anonymous_zero else [False])
    app.state.settings = SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_overrides={},
        local_registration_enabled=True,
    )
    app.state.rate_limit_checker = checker

    response = TestClient(app).request(method, path)

    assert response.status_code == (401 if anonymous_zero else 429), (
        method,
        path,
        response.text,
    )
    assert len(checker.calls) == (0 if anonymous_zero else 1)
