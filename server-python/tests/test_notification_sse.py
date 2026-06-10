from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.api.notifications import format_sse_comment, format_sse_event
from app.main import create_app


def test_sse_requires_authenticated_user() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/notifications/sse")

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"


def test_sse_stream_emits_connected_event_with_event_stream_content_type() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": "Alice",
        "email": "alice@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }

    async def finite_stream(user_id: str) -> AsyncIterator[str]:
        yield format_sse_event("connected", "ok")

    app.state.notification_sse_stream_factory = finite_stream
    client = TestClient(app)

    with client.stream("GET", "/api/web/notifications/sse", headers={"X-Mock-User-Id": "user-1"}) as response:
        body = next(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert body == "event: connected\ndata: ok\n\n"


def test_sse_formatter_matches_java_connected_notification_and_ping_shapes() -> None:
    assert format_sse_event("connected", "ok") == "event: connected\ndata: ok\n\n"
    assert format_sse_comment("ping") == ": ping\n\n"
    assert (
        format_sse_event("notification", '{"id":1,"title":"Ready"}')
        == 'event: notification\ndata: {"id":1,"title":"Ready"}\n\n'
    )
