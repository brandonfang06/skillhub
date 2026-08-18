from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOP = ROOT / "deploy" / "k8s" / "oss-github-source-import.zh.md"


def test_sop_documents_complete_source_import_contract() -> None:
    content = SOP.read_text(encoding="utf-8")
    for name in (
        "SKILLHUB_IMPORTER_IMAGE",
        "SKILLHUB_BASE_URL",
        "SKILLHUB_API_TOKEN",
        "SKILLHUB_SOURCE_REPOSITORY_URL",
        "SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE",
        "SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME",
        "SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE",
        "SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME",
        "SKILLHUB_IMPORT_SOURCE_ROOT",
        "SKILLHUB_IMPORT_REPORT_PATH",
        "SKILLHUB_IMPORT_TIMEOUT_SECONDS",
        "SSL_CERT_FILE",
        "CI_PROJECT_DIR",
        "CI_COMMIT_SHA",
        "CI_COMMIT_TAG",
        "CI_COMMIT_BRANCH",
        "CI_COMMIT_REF_NAME",
        "CI_PIPELINE_ID",
        "CI_JOB_ID",
    ):
        assert name in content
    for endpoint in (
        "/api/cli/v1/source-imports/namespaces/{namespaceSlug}",
        "/api/cli/v1/source-imports/{namespaceSlug}/skills/validate",
        "/api/cli/v1/source-imports/{namespaceSlug}/skills",
    ):
        assert endpoint in content


def test_sop_explains_identity_review_subpath_and_failures() -> None:
    content = SOP.read_text(encoding="utf-8")
    for phrase in (
        "source:import",
        "SKILL_ADMIN",
        "SUPER_ADMIN",
        "keycloak",
        "tsso",
        "https://skillhub.example.com/skillhub",
        "PENDING_REVIEW",
        "SKIPPED_UNCHANGED",
        "SKIPPED_ALREADY_IMPORTED",
        "requestId",
        "部分提交",
        "憑證",
        "0 個 SKILL.md",
    ):
        assert phrase in content
