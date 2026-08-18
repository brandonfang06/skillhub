from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_gitlab_template_uses_pinned_external_image_and_single_command() -> None:
    template = (ROOT / "deploy" / "gitlab" / "oss-source-import.yml").read_text(encoding="utf-8")

    assert 'image: "$SKILLHUB_IMPORTER_IMAGE"' in template
    assert "skillhub-oss-import --json-report \"$SKILLHUB_IMPORT_REPORT_PATH\"" in template
    assert "when: always" in template
    assert '- "$SKILLHUB_IMPORT_REPORT_PATH"' in template
    assert "pip install" not in template
    assert "curl " not in template
    assert ":latest" not in template


def test_template_documents_required_pipeline_variables() -> None:
    template = (ROOT / "deploy" / "gitlab" / "oss-source-import.yml").read_text(encoding="utf-8")
    for name in (
        "SKILLHUB_IMPORTER_IMAGE",
        "SKILLHUB_BASE_URL",
        "SKILLHUB_API_TOKEN",
        "SKILLHUB_SOURCE_REPOSITORY_URL",
        "SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE",
        "SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME",
    ):
        assert name in template
