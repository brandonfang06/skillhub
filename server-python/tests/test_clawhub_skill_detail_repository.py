from app.api.skills import build_clawhub_skill_detail_response


def portal_detail_response() -> dict[str, object]:
    return {
        "slug": "demo",
        "displayName": "Demo Skill",
        "summary": "Demo summary",
        "namespace": "team-ai",
        "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
        "createdAt": "2026-06-08T00:01:02Z",
        "publishedAt": "2026-06-08T01:02:03Z",
        "updatedAt": "2026-06-08T02:03:04Z",
        "changelog": None,
    }


def test_build_clawhub_skill_detail_response_maps_plain_shape() -> None:
    assert build_clawhub_skill_detail_response(portal_detail_response()) == {
        "skill": {
            "slug": "team-ai--demo",
            "displayName": "Demo Skill",
            "summary": "Demo summary",
            "tags": {},
            "stats": {},
            "createdAt": 1780876862000,
            "updatedAt": 1780884184000,
        },
        "latestVersion": {
            "version": "1.2.0",
            "createdAt": 1780880523000,
            "changelog": "",
            "license": None,
        },
        "owner": None,
        "moderation": {
            "isSuspicious": False,
            "isMalwareBlocked": False,
            "verdict": "clean",
            "reasonCodes": [],
            "updatedAt": None,
            "engineVersion": None,
            "summary": None,
        },
    }


def test_build_clawhub_skill_detail_response_handles_missing_version_and_timestamps() -> None:
    detail = portal_detail_response()
    detail["publishedVersion"] = None
    detail["publishedAt"] = None
    detail["updatedAt"] = None
    detail["summary"] = None

    response = build_clawhub_skill_detail_response(detail)

    assert response["skill"]["summary"] is None  # type: ignore[index]
    assert response["skill"]["updatedAt"] == 0  # type: ignore[index]
    assert response["latestVersion"] is None
