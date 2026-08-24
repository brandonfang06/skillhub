from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_gitlab_template_runs_the_project_local_python_importer() -> None:
    template = (ROOT / "deploy" / "gitlab" / "oss-source-import.yml").read_text(encoding="utf-8")

    assert 'name: "$SKILLHUB_PYTHON_IMAGE"' in template
    assert 'entrypoint: [""]' in template
    assert '/bin/sh "$CI_PROJECT_DIR/deploy/gitlab/oss-source-import.sh"' in template
    assert "when: always" in template
    assert '- "$SKILLHUB_IMPORT_REPORT_PATH"' in template
    assert "pip install" not in template
    assert "curl " not in template
    assert ":latest" not in template
    assert "SKILLHUB_IMPORTER_IMAGE" not in template
    assert "skillhub-oss-import --json-report" not in template


def test_shell_wrapper_installs_locked_dependencies_and_calls_python_file() -> None:
    wrapper = (ROOT / "deploy" / "gitlab" / "oss-source-import.sh").read_text(encoding="utf-8")

    assert "python -m pip install" in wrapper
    assert "requirements-runtime.txt" in wrapper
    assert "SKILLHUB_IMPORT_RUNTIME_DIR" in wrapper
    assert 'python "$CI_PROJECT_DIR/tools/oss-source-importer/run_import.py"' in wrapper
    assert "curl " not in wrapper
    assert "skillhub-oss-import --json-report" not in wrapper


def test_template_documents_required_pipeline_variables() -> None:
    template = (ROOT / "deploy" / "gitlab" / "oss-source-import.yml").read_text(encoding="utf-8")
    for name in (
        "SKILLHUB_PYTHON_IMAGE",
        "SKILLHUB_BASE_URL",
        "SKILLHUB_SERVICE_TOKEN",
        "SKILLHUB_SOURCE_REPOSITORY_URL",
        "SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE",
        "SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME",
        "CI_REPOSITORY_URL",
        "CI_COMMIT_SHA",
    ):
        assert name in template
