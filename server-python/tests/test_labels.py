from fastapi.testclient import TestClient

from app.main import create_app


def test_public_labels_v1_route_returns_envelope() -> None:
    app = create_app()
    app.state.label_reader = lambda locale: [
        {"slug": "official", "type": "RECOMMENDED", "displayName": "Official"}
    ]

    client = TestClient(app)
    response = client.get("/api/v1/labels", headers={"X-Request-Id": "labels-test"})

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "labels-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert response.json()["requestId"] == "labels-test"
    assert response.json()["data"] == [
        {"slug": "official", "type": "RECOMMENDED", "displayName": "Official"}
    ]


def test_public_labels_web_alias_returns_same_contract() -> None:
    app = create_app()
    app.state.label_reader = lambda locale: [
        {"slug": "team", "type": "RECOMMENDED", "displayName": "Team"}
    ]

    client = TestClient(app)
    response = client.get("/api/web/labels")

    assert response.status_code == 200
    assert response.json()["data"] == [
        {"slug": "team", "type": "RECOMMENDED", "displayName": "Team"}
    ]


def test_public_labels_passes_requested_locale_to_reader() -> None:
    seen_locales: list[str | None] = []
    app = create_app()
    app.state.label_reader = lambda locale: seen_locales.append(locale) or []

    client = TestClient(app)
    response = client.get("/api/v1/labels", headers={"Accept-Language": "zh-TW,en;q=0.8"})

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert seen_locales == ["zh-TW"]


def test_skill_labels_v1_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_label_reader = lambda namespace, slug, locale: [
        {"slug": "official", "type": "PRIVILEGED", "displayName": "Official"}
    ]

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/labels",
        headers={"X-Request-Id": "skill-labels-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "skill-labels-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert response.json()["requestId"] == "skill-labels-test"
    assert response.json()["data"] == [
        {"slug": "official", "type": "PRIVILEGED", "displayName": "Official"}
    ]


def test_skill_labels_web_alias_returns_same_contract() -> None:
    app = create_app()
    app.state.skill_label_reader = lambda namespace, slug, locale: [
        {"slug": "team", "type": "RECOMMENDED", "displayName": "Team"}
    ]

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/labels")

    assert response.status_code == 200
    assert response.json()["data"] == [
        {"slug": "team", "type": "RECOMMENDED", "displayName": "Team"}
    ]
