from fastapi.testclient import TestClient

from app.api.skills import build_compare_response
from app.main import create_app


def compare_response() -> dict[str, object]:
    return {
        "from": "1.0.0",
        "to": "1.1.0",
        "summary": {
            "totalFiles": 1,
            "addedFiles": 0,
            "modifiedFiles": 1,
            "removedFiles": 0,
            "addedLines": 1,
            "removedLines": 1,
        },
        "files": [
            {
                "path": "SKILL.md",
                "changeType": "MODIFIED",
                "oldSize": 11,
                "newSize": 12,
                "binary": False,
                "truncated": False,
                "hunks": [
                    {
                        "oldStart": 1,
                        "oldLines": 1,
                        "newStart": 1,
                        "newLines": 1,
                        "lines": [
                            {
                                "type": "DELETE",
                                "content": "old",
                                "oldLineNumber": 1,
                                "newLineNumber": None,
                            },
                            {
                                "type": "ADD",
                                "content": "new",
                                "oldLineNumber": None,
                                "newLineNumber": 1,
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_skill_version_compare_v1_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_version_compare_reader = (
        lambda namespace, slug, from_version, to_version, current_user_id: compare_response()
    )

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/compare",
        params={"from": "1.0.0", "to": "1.1.0"},
        headers={"X-Request-Id": "compare-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "compare-test"
    assert response.json()["code"] == 0
    assert response.json()["requestId"] == "compare-test"
    assert response.json()["data"] == compare_response()


def test_skill_version_compare_web_alias_returns_same_contract() -> None:
    app = create_app()
    app.state.skill_version_compare_reader = (
        lambda namespace, slug, from_version, to_version, current_user_id: compare_response()
    )

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/versions/compare", params={"from": "1.0.0", "to": "1.1.0"})

    assert response.status_code == 200
    assert response.json()["data"] == compare_response()


def test_skill_version_compare_route_forwards_params_and_current_user() -> None:
    seen: list[tuple[str, str, str, str, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        from_version: str,
        to_version: str,
        current_user_id: str | None,
    ) -> dict[str, object]:
        seen.append((namespace, slug, from_version, to_version, current_user_id))
        return compare_response()

    app.state.skill_version_compare_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/compare",
        params={"from": "1.0.0", "to": "1.1.0"},
        headers={"X-Mock-User-Id": " owner-1 "},
    )

    assert response.status_code == 200
    assert seen == [("global", "demo", "1.0.0", "1.1.0", "owner-1")]


def test_skill_version_compare_route_forwards_blank_current_user_as_none() -> None:
    seen: list[str | None] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        from_version: str,
        to_version: str,
        current_user_id: str | None,
    ) -> dict[str, object]:
        seen.append(current_user_id)
        return compare_response()

    app.state.skill_version_compare_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/global/demo/versions/compare",
        params={"from": "1.0.0", "to": "1.1.0"},
        headers={"X-Mock-User-Id": "   "},
    )

    assert response.status_code == 200
    assert seen == [None]


def test_build_compare_response_reports_modified_added_removed_and_omits_identical_files() -> None:
    response = build_compare_response(
        "1.0.0",
        "1.1.0",
        from_files={
            "README.md": {
                "file_path": "README.md",
                "file_size": 12,
                "content_type": "text/markdown",
                "sha256": "old",
                "content": "same\n",
            },
            "SKILL.md": {
                "file_path": "SKILL.md",
                "file_size": 10,
                "content_type": "text/markdown",
                "sha256": "old",
                "content": "line one\nold\n",
            },
            "old.txt": {
                "file_path": "old.txt",
                "file_size": 7,
                "content_type": "text/plain",
                "sha256": "removed",
                "content": "remove\n",
            },
        },
        to_files={
            "README.md": {
                "file_path": "README.md",
                "file_size": 12,
                "content_type": "text/markdown",
                "sha256": "old",
                "content": "same\n",
            },
            "SKILL.md": {
                "file_path": "SKILL.md",
                "file_size": 10,
                "content_type": "text/markdown",
                "sha256": "new",
                "content": "line one\nnew\n",
            },
            "new.txt": {
                "file_path": "new.txt",
                "file_size": 4,
                "content_type": "text/plain",
                "sha256": "added",
                "content": "add\n",
            },
        },
    )

    assert response["from"] == "1.0.0"
    assert response["to"] == "1.1.0"
    assert response["summary"] == {
        "totalFiles": 3,
        "addedFiles": 1,
        "modifiedFiles": 1,
        "removedFiles": 1,
        "addedLines": 3,
        "removedLines": 3,
    }
    assert [file["path"] for file in response["files"]] == ["SKILL.md", "new.txt", "old.txt"]
    assert response["files"][0]["changeType"] == "MODIFIED"
    assert response["files"][0]["hunks"][0]["lines"] == [
        {"type": "DELETE", "content": "old", "oldLineNumber": 2, "newLineNumber": None},
        {"type": "ADD", "content": "new", "oldLineNumber": None, "newLineNumber": 2},
    ]
    assert response["files"][1]["changeType"] == "ADDED"
    assert response["files"][1]["hunks"][0]["lines"][-1] == {
        "type": "ADD",
        "content": "",
        "oldLineNumber": None,
        "newLineNumber": 2,
    }
    assert response["files"][2]["changeType"] == "REMOVED"
