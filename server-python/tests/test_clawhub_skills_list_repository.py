from app.api.skills import build_clawhub_skills_list_response


def portal_search_response() -> dict[str, object]:
    return {
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
        "total": 30,
        "page": 1,
        "size": 25,
    }


def test_build_clawhub_skills_list_response_maps_plain_shape() -> None:
    assert build_clawhub_skills_list_response(portal_search_response()) == {
        "items": [
            {
                "slug": "team-ai--demo",
                "displayName": "Demo Skill",
                "summary": "Demo summary",
                "tags": {},
                "stats": {"downloads": 7, "stars": 3},
                "createdAt": 0,
                "updatedAt": 1780880523000,
                "latestVersion": {
                    "version": "1.2.0",
                    "createdAt": 1780880523000,
                    "changelog": "",
                    "license": None,
                },
            }
        ],
        "nextCursor": "2",
    }


def test_build_clawhub_skills_list_response_handles_empty_last_page() -> None:
    response = portal_search_response()
    response["items"] = []
    response["total"] = 25
    response["page"] = 1
    response["size"] = 25

    assert build_clawhub_skills_list_response(response) == {"items": [], "nextCursor": None}


def test_build_clawhub_skills_list_response_handles_missing_version_and_counts() -> None:
    response = portal_search_response()
    response["items"] = [
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
    ]
    response["total"] = 1
    response["page"] = 0
    response["size"] = 25

    assert build_clawhub_skills_list_response(response) == {
        "items": [
            {
                "slug": "demo",
                "displayName": "Demo Skill",
                "summary": None,
                "tags": {},
                "stats": {},
                "createdAt": 0,
                "updatedAt": 0,
                "latestVersion": None,
            }
        ],
        "nextCursor": None,
    }
