from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOP = ROOT / "deploy" / "k8s" / "oss-github-source-import.zh.md"


def test_sop_documents_complete_source_import_contract() -> None:
    content = SOP.read_text(encoding="utf-8")
    for name in (
        "SKILLHUB_PYTHON_IMAGE",
        "SKILLHUB_BASE_URL",
        "SKILLHUB_SERVICE_TOKEN",
        "SKILLHUB_SOURCE_REPOSITORY_URL",
        "SKILLHUB_SOURCE_REF_TYPE",
        "SKILLHUB_SOURCE_REF",
        "SKILLHUB_DEV_GITLAB_REPOSITORY_URL",
        "SKILLHUB_DEV_GITLAB_BRANCH",
        "SKILLHUB_SOURCE_SCAN_STATUS",
        "SKILLHUB_SOURCE_SCAN_ID",
        "SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE",
        "SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME",
        "SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE",
        "SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME",
        "SKILLHUB_IMPORT_SOURCE_ROOT",
        "SKILLHUB_IMPORT_REPORT_PATH",
        "SKILLHUB_IMPORT_TIMEOUT_SECONDS",
        "SSL_CERT_FILE",
        "CI_PROJECT_DIR",
        "CI_JOB_TOKEN",
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
        "SUPER_ADMIN",
        "st_",
        "/admin/service-principals",
        "3 個曆年",
        "永不到期",
        "輪替",
        "撤銷",
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
        "GitLab job log",
        "event=validation_completed",
        "event=import_completed",
        "JSON report",
    ):
        assert phrase in content
    assert "`SKILLHUB_API_TOKEN` 不會 fallback" in content
    assert "scan SHA" not in content
    assert "Dev SHA" not in content


def test_sop_explains_version_importer_attribution() -> None:
    content = SOP.read_text(encoding="utf-8")
    for phrase in (
        "Imported by",
        "選定版本",
        "service principal 只是 audit actor",
        "不會改變 skill owner",
    ):
        assert phrase in content


def test_sop_explains_gitlab_shell_python_and_api_responsibilities() -> None:
    content = SOP.read_text(encoding="utf-8")
    for phrase in (
        "pull-pipeline-for-user",
        "`pull_pipeline`",
        "`pull_code`",
        "`publish_skillhub`",
        "Dev GitLab",
        "dotenv",
        "唯一可信來源",
        "GitLab Runner shell",
        "中央 repo 內的 Python 檔案",
        "不是一般 SkillHub CLI",
        "不使用 `curl`",
        "Python 標準函式庫",
        "Python 3.8",
        "不執行 `pip install`",
        "git clone",
        "公開 reverse proxy／Ingress",
        "Python FastAPI backend",
        'entrypoint: [""]',
        "GitHub URL 只用於 upstream provenance",
        "Runner 不連 GitHub",
        "protected branch",
        "YYYYMMDDHHMMSS",
    ):
        assert phrase in content
    assert "SKILLHUB_IMPORTER_IMAGE" not in content
    assert "requirements-runtime.txt" not in content
    assert "Python `httpx`" not in content
    assert "CI_REPOSITORY_URL" not in content
    assert "CI_COMMIT_SHA" not in content
    assert "SKILLHUB_SOURCE_COMMIT_SHA" not in content
    assert "SKILLHUB_DEV_GITLAB_COMMIT_SHA" not in content
    assert "SKILLHUB_SOURCE_SCAN_COMMIT_SHA" not in content
