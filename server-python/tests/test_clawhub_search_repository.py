from app.api.skills import build_clawhub_search_response, to_clawhub_canonical_slug


def test_to_clawhub_canonical_slug_maps_global_and_namespace() -> None:
    assert to_clawhub_canonical_slug("global", "demo") == "demo"
    assert to_clawhub_canonical_slug("team-ai", "demo") == "team-ai--demo"


def test_build_clawhub_search_response_maps_plain_results() -> None:
    portal_response = {
        "items": [
            {
                "slug": "demo",
                "displayName": "Demo Skill",
                "summary": "Demo summary",
                "namespace": "team-ai",
                "downloadCount": 7,
                "starCount": 3,
                "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
                "updatedAt": "2026-06-08T01:02:03Z",
            }
        ],
        "total": 1,
        "page": 0,
        "size": 20,
    }

    assert build_clawhub_search_response(portal_response) == {
        "results": [
            {
                "slug": "team-ai--demo",
                "displayName": "Demo Skill",
                "summary": "Demo summary",
                "version": "1.2.0",
                "score": 0.37,
                "updatedAt": 1780880523000,
            }
        ]
    }


def test_build_clawhub_search_response_handles_null_version_and_updated_at() -> None:
    portal_response = {
        "items": [
            {
                "slug": "demo",
                "displayName": "Demo Skill",
                "summary": None,
                "namespace": "global",
                "downloadCount": None,
                "starCount": None,
                "publishedVersion": None,
                "updatedAt": None,
            }
        ],
        "total": 1,
        "page": 0,
        "size": 20,
    }

    assert build_clawhub_search_response(portal_response) == {
        "results": [
            {
                "slug": "demo",
                "displayName": "Demo Skill",
                "summary": None,
                "version": None,
                "score": 0.0,
                "updatedAt": None,
            }
        ]
    }
