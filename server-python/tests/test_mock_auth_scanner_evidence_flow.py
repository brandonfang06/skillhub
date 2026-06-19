from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.main import create_app
from app.publish.dry_run import PublishDryRunResult
from app.publish.orchestration import PublishWriteResult
from app.publish.side_effects import PublishSideEffectResult, ScanTaskPayload
from app.publish.storage import StoredPackageResult


def skill_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "SKILL.md",
            b"---\nname: Scanned Skill\ndescription: Tests scanner evidence\nversion: 1.0.0\n---\n# Scanned\n",
        )
    return buffer.getvalue()


def principal(user_id: str) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": ["USER"],
    }


def test_session_publish_with_scanner_then_reads_security_audit_evidence() -> None:
    app = create_app()
    flow: dict[str, object] = {}

    app.state.local_auth_login = lambda payload: principal(str(payload["username"]))
    app.state.settings = SimpleNamespace(
        storage_base_path="C:/tmp/skillhub-scanner-flow-test-storage",
        security_scanner_enabled=True,
        security_scanner_mode="upload",
        redis_url="redis://localhost:6379",
        scan_stream_key="skillhub:scan:requests",
    )
    app.state.publish_write_namespace_id = 20

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
            resolved_slug="scanned-skill",
            resolved_version="1.0.0",
        )

    async def write_publish(write_input):
        flow["publish_write"] = {
            "publisher_id": write_input.publisher_id,
            "scanner_enabled": write_input.scanner_enabled,
            "scan_mode": write_input.scan_mode,
            "storage_base_path": write_input.storage_base_path,
        }
        return PublishWriteResult(
            skill_id=17,
            version_id=52,
            version_status="PENDING_REVIEW",
            latest_version_updated=False,
            stored_package=StoredPackageResult(
                files=[],
                bundle_key="packages/17/52/bundle.zip",
                bundle_size=64,
                file_count=1,
                total_size=96,
                bundle_ready=True,
                download_ready=True,
            ),
            side_effects=PublishSideEffectResult(
                review_task_id=901,
                security_audit_id=777,
                scan_task=ScanTaskPayload(
                    task_id="scan-task-777",
                    version_id=52,
                    skill_path=None,
                    bundle_key="packages/17/52/bundle.zip",
                    publisher_id="publisher",
                    created_at_millis=1781930400000,
                    metadata={"scannerType": "skill-scanner"},
                ),
                events=[],
            ),
            replacement_deleted_keys=[],
            replacement_compensation_recorded=False,
        )

    def security_audit_reader(skill_id, version_id, scanner_type, user):
        flow["security_audit"] = {
            "skill_id": skill_id,
            "version_id": version_id,
            "scanner_type": scanner_type,
            "user_id": user["userId"],
        }
        return [
            {
                "id": 777,
                "scanId": "scan-task-777",
                "scannerType": scanner_type or "skill-scanner",
                "verdict": "SAFE",
                "isSafe": True,
                "maxSeverity": None,
                "findingsCount": 0,
                "findings": [],
                "scanDurationSeconds": 1.0,
                "scannedAt": "2026-06-20T10:05:00Z",
                "createdAt": "2026-06-20T10:00:00Z",
            }
        ]

    app.state.publish_validate_reader = validate_publish
    app.state.publish_write_reader = write_publish
    app.state.security_audit_reader = security_audit_reader

    client = TestClient(app)
    login = client.post("/api/v1/auth/local/login", json={"username": "publisher", "password": "Abcd123!"})
    assert login.status_code == 200

    publish = client.post(
        "/api/web/skills/team-a/publish",
        data={"visibility": "NAMESPACE_ONLY"},
        files={"file": ("skill.zip", skill_zip(), "application/zip")},
    )
    assert publish.status_code == 200
    assert flow["publish_validate"] == {
        "namespace": "team-a",
        "publisher_id": "publisher",
        "visibility": "NAMESPACE_ONLY",
        "paths": ["SKILL.md"],
    }
    assert flow["publish_write"] == {
        "publisher_id": "publisher",
        "scanner_enabled": True,
        "scan_mode": "upload",
        "storage_base_path": "C:/tmp/skillhub-scanner-flow-test-storage",
    }

    audit = client.get(
        "/api/v1/skills/17/versions/52/security-audit",
        params={"scannerType": "skill-scanner"},
    )
    assert audit.status_code == 200
    assert audit.json()["data"][0]["scanId"] == "scan-task-777"
    assert audit.json()["data"][0]["isSafe"] is True
    assert flow["security_audit"] == {
        "skill_id": 17,
        "version_id": 52,
        "scanner_type": "skill-scanner",
        "user_id": "publisher",
    }
