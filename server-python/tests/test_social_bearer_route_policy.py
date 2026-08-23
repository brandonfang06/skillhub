from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api import social as social_api
from app.main import create_app
from app.social.rating import SkillRatingInput
from app.social.star import SkillStarInput

BEARER_ALLOWED = "bearer_allowed"
SESSION_ONLY = "session_only"

EXPECTED_SOCIAL_ROUTE_POLICY = {
    ("GET", "/api/v1/skills/{skill_id}/star"): SESSION_ONLY,
    ("PUT", "/api/v1/skills/{skill_id}/star"): BEARER_ALLOWED,
    ("DELETE", "/api/v1/skills/{skill_id}/star"): BEARER_ALLOWED,
    ("GET", "/api/v1/skills/{skill_id}/rating"): SESSION_ONLY,
    ("PUT", "/api/v1/skills/{skill_id}/rating"): BEARER_ALLOWED,
    ("GET", "/api/web/skills/{skill_id}/star"): SESSION_ONLY,
    ("PUT", "/api/web/skills/{skill_id}/star"): BEARER_ALLOWED,
    ("DELETE", "/api/web/skills/{skill_id}/star"): BEARER_ALLOWED,
    ("GET", "/api/web/skills/{skill_id}/rating"): SESSION_ONLY,
    ("PUT", "/api/web/skills/{skill_id}/rating"): BEARER_ALLOWED,
}

EXCLUDED_SOCIAL_MUTATIONS = (
    ("POST", "/api/v1/stars/agent-helper"),
    ("DELETE", "/api/v1/stars/agent-helper"),
    ("PUT", "/api/v1/skills/10/subscription"),
    ("DELETE", "/api/v1/skills/10/subscription"),
    ("PUT", "/api/web/skills/10/subscription"),
    ("DELETE", "/api/web/skills/10/subscription"),
)

SOCIAL_ROUTE_PATTERN = re.compile(r"^/api/(?:v1|web)/skills/\{[^/]+\}/(?:star|rating)$")


def _registered_social_routes() -> tuple[
    tuple[str, str, str, dict[str, int] | None], ...
]:
    app = create_app()
    routes: list[tuple[str, str, str, dict[str, int] | None]] = []
    for route in app.routes:
        if (
            not isinstance(route, APIRoute)
            or SOCIAL_ROUTE_PATTERN.fullmatch(route.path) is None
        ):
            continue
        concrete_path = re.sub(r"\{[^/]+\}", "10", route.path)
        for method in route.methods:
            payload = (
                {"score": 4}
                if method == "PUT" and route.path.endswith("/rating")
                else None
            )
            routes.append((method, route.path, concrete_path, payload))
    return tuple(sorted(routes))


def _user(user_id: str, provider: str) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": "Social User",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": provider,
        "platformRoles": ["USER"],
        "tokenScopes": ["skill:read"] if provider == "api_token" else [],
    }


def _social_client(
    principal_reader: Callable[[str], dict[str, object] | None],
) -> tuple[TestClient, list[str]]:
    app = create_app()
    resolved_user_ids: list[str] = []
    app.state.auth_bearer_reader = principal_reader

    async def star_writer(payload: SkillStarInput) -> None:
        resolved_user_ids.append(payload.user_id)

    async def unstar_writer(payload: SkillStarInput) -> None:
        resolved_user_ids.append(payload.user_id)

    async def star_reader(skill_id: int, user_id: str | None) -> bool:
        assert skill_id == 10
        assert user_id is not None
        resolved_user_ids.append(user_id)
        return True

    async def rating_writer(payload: SkillRatingInput) -> None:
        assert payload.score == 4
        resolved_user_ids.append(payload.user_id)

    async def rating_reader(skill_id: int, user_id: str | None) -> dict[str, object]:
        assert skill_id == 10
        assert user_id is not None
        resolved_user_ids.append(user_id)
        return {"score": 4, "rated": True}

    app.state.skill_star_writer = star_writer
    app.state.skill_unstar_writer = unstar_writer
    app.state.skill_star_reader = star_reader
    app.state.skill_rating_writer = rating_writer
    app.state.skill_rating_reader = rating_reader
    return TestClient(app), resolved_user_ids


def _request(
    client: TestClient,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    **kwargs: Any,
) -> Any:
    return client.request(method, path, json=payload, **kwargs)


def test_registered_social_routes_have_exact_bearer_and_session_classification() -> (
    None
):
    registered_keys = tuple(
        (method, path_template)
        for method, path_template, _, _ in _registered_social_routes()
    )

    assert registered_keys == tuple(sorted(EXPECTED_SOCIAL_ROUTE_POLICY))


def test_bearer_api_token_obeys_registered_star_and_rating_route_policy() -> None:
    client, resolved_user_ids = _social_client(
        lambda raw_token: (
            _user("token-user", "api_token") if raw_token == "sk_social" else None
        )
    )

    for method, path_template, concrete_path, payload in _registered_social_routes():
        classification = EXPECTED_SOCIAL_ROUTE_POLICY[(method, path_template)]
        response = _request(
            client,
            method,
            concrete_path,
            payload,
            headers={"Authorization": "Bearer sk_social"},
        )

        assert response.status_code == (
            200 if classification == BEARER_ALLOWED else 401
        )

    assert resolved_user_ids == ["token-user"] * 6


@pytest.mark.parametrize(("method", "path"), EXCLUDED_SOCIAL_MUTATIONS)
def test_bearer_api_token_does_not_open_excluded_social_mutations(
    method: str, path: str
) -> None:
    client, resolved_user_ids = _social_client(
        lambda raw_token: (
            _user("token-user", "api_token") if raw_token == "sk_social" else None
        )
    )

    response = client.request(
        method, path, headers={"Authorization": "Bearer sk_social"}
    )

    assert response.status_code == 401
    assert resolved_user_ids == []


def test_session_cookie_behavior_for_registered_star_and_rating_routes_is_unchanged() -> (
    None
):
    client, resolved_user_ids = _social_client(lambda raw_token: None)
    client.app.state.local_auth_login = lambda body: _user("session-user", "local")
    login = client.post(
        "/api/v1/auth/local/login",
        json={"username": "session-user", "password": "Abcd123!"},
    )

    assert login.status_code == 200

    for method, _, concrete_path, payload in _registered_social_routes():
        response = _request(client, method, concrete_path, payload)
        assert response.status_code == 200

    assert resolved_user_ids == ["session-user"] * 10


def test_required_social_auth_preserves_invalid_bearer_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject_invalid_bearer(*args: object) -> dict[str, object]:
        raise HTTPException(status_code=401, detail="error.auth.token.invalid")

    monkeypatch.setattr(
        social_api, "resolve_current_user_or_401", reject_invalid_bearer
    )
    client, resolved_user_ids = _social_client(lambda raw_token: None)

    response = client.put(
        "/api/v1/skills/10/star",
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.token.invalid"
    assert resolved_user_ids == []
