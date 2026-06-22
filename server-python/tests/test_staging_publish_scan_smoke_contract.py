from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_staging_compose_exercises_s3_storage_and_scan_consumer() -> None:
    compose = read("docker-compose.staging.yml")

    assert "SKILLHUB_SCAN_CONSUMER_ENABLED: \"true\"" in compose
    assert "SKILLHUB_STORAGE_PROVIDER: s3" in compose
    assert "SKILLHUB_STORAGE_S3_ENDPOINT: http://minio:9000" in compose
    assert "SKILLHUB_STORAGE_S3_AUTO_CREATE_BUCKET: \"true\"" in compose
    assert "minio:" in compose


def test_publish_scan_download_smoke_script_is_registered_for_staging() -> None:
    script = read("scripts/publish-scan-download-smoke-test.sh")
    makefile = read("Makefile")

    assert "/api/web/skills/$SLUG/publish" in script
    assert "/api/v1/skills/$SKILL_ID/versions/$VERSION_ID/security-audit" in script
    assert "/api/web/reviews/$REVIEW_ID/approve" in script
    assert "/api/web/skills/$SLUG/$SKILL_SLUG/download" in script
    assert "publish-scan-smoke:" in makefile
    assert "scripts/publish-scan-download-smoke-test.sh $(STAGING_API_URL)" in makefile
