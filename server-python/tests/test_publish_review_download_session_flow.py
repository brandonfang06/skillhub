from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.api.skills import DownloadResult
from app.main import create_app
from app.publish.dry_run import PublishDryRunResult
from app.publish.orchestration import PublishWriteResult
from app.publish.side_effects import PublishSideEffectResult
from app.publish.storage import StoredPackageResult
from app.review.approval import ReviewApproveInput


def skill_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "SKILL.md",
            b"---\nname: Flow Skill\ndescription: Tests the user flow\nversion: 1.0.0\n---\n# Flow\n",
        )
        archive.writestr("src/main.py", b"print('flow')\n")
    return buffer.getvalue()


def principal(user_id: str, roles: list[str] | None = None) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": roles or ["USER"],
    }


def test_session_user_can_publish_review_approve_and_download_namespace_skill() -> None:
    app = create_app()
    flow: dict[str, object] = {}

    app.state.local_auth_login = lambda payload: principal(
        str(payload["username"]),
        ["USER"],
    )
    app.state.settings = SimpleNamespace(
        storage_base_path="C:/tmp/skillhub-flow-test-storage",
        security_scanner_enabled=False,
        security_scanner_mode="upload",
        redis_url="redis://localhost:6379",
        scan_stream_key="skillhub:scan:requests",
    )
    app.state.publish_write_namespace_id = 10

    async def validate_publish(namespace, entries, publisher_id, visibility, platform_roles):
        flow["publish_validate"] = {
            "namespace": namespace,
            "publisher_id": publisher_id,
            "visibility": visibility,
            "paths": [entry.path for entry in entries],
        }
        return PublishDryRunResult(
            valid=True,
            errors=[],
            warnings=[],
            resolved_slug="flow-skill",
            resolved_version="1.0.0",
        )

    async def write_publish(write_input):
        flow["publish_write"] = {
            "publisher_id": write_input.publisher_id,
            "visibility": write_input.visibility,
            "auto_publish": write_input.auto_publish,
        }
        return PublishWriteResult(
            skill_id=17,
            version_id=52,
            version_status="PENDING_REVIEW",
            latest_version_updated=False,
            stored_package=StoredPackageResult(
                files=[],
                bundle_key="packages/17/52/bundle.zip",
                bundle_size=10,
                file_count=2,
                total_size=20,
                bundle_ready=True,
                download_ready=True,
            ),
            side_effects=PublishSideEffectResult(
                review_task_id=901,
                security_audit_id=None,
                scan_task=None,
                events=[],
            ),
            replacement_deleted_keys=[],
            replacement_compensation_recorded=False,
        )

    async def approve_review(review_input: ReviewApproveInput):
        flow["review_approve"] = {
            "review_task_id": review_input.review_task_id,
            "reviewer_id": review_input.reviewer_id,
        }
        return {
            "id": review_input.review_task_id,
            "skillVersionId": 52,
            "namespace": "team-a",
            "skillSlug": "flow-skill",
            "version": "1.0.0",
            "status": "APPROVED",
            "submittedBy": "local-user",
            "submittedByName": "local-user",
            "reviewedBy": review_input.reviewer_id,
            "reviewedByName": review_input.reviewer_id,
            "reviewComment": review_input.comment,
            "submittedAt": "2026-06-18T10:00:00Z",
            "reviewedAt": "2026-06-18T10:05:00Z",
        }

    def review_detail(review_task_id, user_id):
        flow["review_detail"] = {
            "review_task_id": review_task_id,
            "user_id": user_id,
        }
        return {
            "id": review_task_id,
            "skillVersionId": 52,
            "namespace": "team-a",
            "skillSlug": "flow-skill",
            "version": "1.0.0",
            "status": "PENDING",
            "submittedBy": "local-user",
            "submittedByName": "local-user",
            "reviewedBy": None,
            "reviewedByName": None,
            "reviewComment": None,
            "submittedAt": "2026-06-18T10:00:00Z",
            "reviewedAt": None,
        }

    async def review_skill_detail(engine, storage_base_path, *, review_task_id, user_id):
        flow["review_skill_detail"] = {
            "review_task_id": review_task_id,
            "user_id": user_id,
            "storage_base_path": storage_base_path,
        }
        return {
            "skill": {
                "id": 17,
                "slug": "flow-skill",
                "namespace": "team-a",
                "resolutionMode": "REVIEW_TASK",
            },
            "versions": [{"id": 52, "version": "1.0.0", "status": "PENDING_REVIEW"}],
            "files": [{"id": 201, "filePath": "SKILL.md", "fileSize": 84}],
            "documentationPath": "SKILL.md",
            "documentationContent": "# Flow\n",
            "downloadUrl": f"/api/v1/reviews/{review_task_id}/download",
            "activeVersion": "1.0.0",
        }

    async def review_file(engine, storage_base_path, *, review_task_id, file_path, user_id):
        flow["review_file"] = {
            "review_task_id": review_task_id,
            "file_path": file_path,
            "user_id": user_id,
            "storage_base_path": storage_base_path,
        }
        return b"# Flow\n"

    def download_latest(namespace, slug, current_user_id):
        flow["download"] = {
            "namespace": namespace,
            "slug": slug,
            "current_user_id": current_user_id,
        }
        return DownloadResult(
            content=b"published-bundle",
            content_type="application/zip",
            filename="Flow Skill-1.0.0.zip",
        )

    app.state.publish_validate_reader = validate_publish
    app.state.publish_write_reader = write_publish
    app.state.review_detail_reader = review_detail
    app.state.review_skill_detail_reader = review_skill_detail
    app.state.review_file_reader = review_file
    app.state.review_approve_writer = approve_review
    app.state.skill_download_latest_reader = download_latest

    user_client = TestClient(app)
    admin_client = TestClient(app)
    assert user_client.post(
        "/api/v1/auth/local/login",
        json={"username": "local-user", "password": "Abcd123!"},
    ).status_code == 200
    assert admin_client.post(
        "/api/v1/auth/local/login",
        json={"username": "team-admin", "password": "Abcd123!"},
    ).status_code == 200

    publish_response = user_client.post(
        "/api/web/skills/team-a/publish",
        data={"visibility": "NAMESPACE_ONLY"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )
    assert publish_response.status_code == 200
    assert flow["publish_validate"] == {
        "namespace": "team-a",
        "publisher_id": "local-user",
        "visibility": "NAMESPACE_ONLY",
        "paths": ["SKILL.md", "src/main.py"],
    }
    assert flow["publish_write"] == {
        "publisher_id": "local-user",
        "visibility": "NAMESPACE_ONLY",
        "auto_publish": False,
    }

    review_detail_response = admin_client.get("/api/web/reviews/901")
    assert review_detail_response.status_code == 200
    assert review_detail_response.json()["data"]["status"] == "PENDING"
    assert flow["review_detail"] == {
        "review_task_id": 901,
        "user_id": "team-admin",
    }

    review_skill_response = admin_client.get("/api/web/reviews/901/skill-detail")
    assert review_skill_response.status_code == 200
    assert review_skill_response.json()["data"]["documentationPath"] == "SKILL.md"
    assert flow["review_skill_detail"] == {
        "review_task_id": 901,
        "user_id": "team-admin",
        "storage_base_path": "C:/tmp/skillhub-flow-test-storage",
    }

    review_file_response = admin_client.get("/api/web/reviews/901/file", params={"path": "SKILL.md"})
    assert review_file_response.status_code == 200
    assert review_file_response.content == b"# Flow\n"
    assert flow["review_file"] == {
        "review_task_id": 901,
        "file_path": "SKILL.md",
        "user_id": "team-admin",
        "storage_base_path": "C:/tmp/skillhub-flow-test-storage",
    }

    approve_response = admin_client.post(
        "/api/web/reviews/901/approve",
        json={"comment": "ship it"},
    )
    assert approve_response.status_code == 200
    assert flow["review_approve"] == {
        "review_task_id": 901,
        "reviewer_id": "team-admin",
    }

    download_response = user_client.get("/api/web/skills/team-a/flow-skill/download")
    assert download_response.status_code == 200
    assert download_response.content == b"published-bundle"
    assert flow["download"] == {
        "namespace": "team-a",
        "slug": "flow-skill",
        "current_user_id": "local-user",
    }
