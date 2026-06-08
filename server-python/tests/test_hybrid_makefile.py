from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_makefile() -> str:
    return (ROOT / "Makefile").read_text(encoding="utf-8")


def read_hybrid_doc() -> str:
    return (ROOT / "docs" / "backend-python-migration" / "hybrid-local-e2e.md").read_text(encoding="utf-8")


def read_sdlc_readme() -> str:
    return (ROOT / "SDLC-README.md").read_text(encoding="utf-8")


def test_makefile_defines_python_dev_process() -> None:
    makefile = read_makefile()

    assert "DEV_PYTHON_PID := $(DEV_DIR)/python.pid" in makefile
    assert "DEV_PYTHON_LOG := $(DEV_DIR)/python.log" in makefile
    assert "DEV_PYTHON_URL := http://localhost:8081" in makefile
    assert "DEV_PYTHON_CMD := uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload" in makefile


def test_makefile_manages_hybrid_stack_and_python_status() -> None:
    makefile = read_makefile()

    assert "dev-all-hybrid:" in makefile
    assert "$(DEV_PROCESS) start --pid-file $(DEV_PYTHON_PID)" in makefile
    assert "$(DEV_PROCESS) stop --pid-file $(DEV_PYTHON_PID)" in makefile
    assert "curl -sf $(DEV_PYTHON_URL)/api/v1/health" in makefile
    assert "curl -sf $(DEV_WEB_URL)/api/v1/health" in makefile
    assert "SERVICE=python" in makefile


def test_makefile_defines_hybrid_e2e_targets() -> None:
    makefile = read_makefile()

    assert "test-e2e-smoke-hybrid:" in makefile
    assert "test-e2e-hybrid:" in makefile
    assert "pnpm run test:e2e:smoke" in makefile
    assert "pnpm run test:e2e" in makefile


def test_powershell_hybrid_script_supports_local_windows_workflow() -> None:
    script = (ROOT / "scripts" / "dev-hybrid.ps1").read_text(encoding="utf-8")

    assert "[ValidateSet('up', 'down', 'status', 'verify-labels-smoke', 'verify-files-smoke', 'verify-detail-smoke', 'verify-search-smoke', 'verify-clawhub-search-smoke', 'verify-clawhub-resolve-smoke', 'verify-clawhub-skill-smoke', 'verify-clawhub-list-smoke', 'verify-auth-me-smoke', 'verify-auth-detail-smoke', 'verify-owner-preview-detail-smoke', 'verify-owner-preview-version-smoke', 'verify-owner-preview-files-smoke', 'verify-owner-preview-tag-files-smoke', 'verify-file-content-smoke', 'verify-download-smoke', 'verify-owner-preview-resolve-smoke', 'verify-owner-preview-compare-smoke', 'verify-publish-foundation-smoke', 'verify-publish-dry-run-smoke', 'verify-publish-storage-foundation-smoke', 'verify-publish-db-foundation-smoke', 'verify-publish-side-effects-foundation-smoke', 'verify-publish-replacement-foundation-smoke', 'e2e-smoke', 'e2e')]" in script
    assert "Start-ManagedProcess" in script
    assert "server-python" in script
    assert "uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload" in script
    assert "node_modules\\.bin\\vite.CMD" in script
    assert "playwright.smoke.config.ts" in script
    assert "playwright.config.ts" in script
    assert '$WebUrl/api/v1/health' in script
    assert "Docker CLI not available" in script
    assert "Stop-ProcessTree" in script
    assert "Stop-ProcessOnPort" in script
    assert "taskkill" in script
    assert "confirmModulesPurge=false" in script
    assert "Join-CmdArguments" in script
    assert "cmd.exe" in script
    assert "-Dmaven.repo.local=$mavenRepo" in script
    assert "$env:JAVA_BIN" in script
    assert "Invoke-NativeCommand" in script
    assert "LASTEXITCODE" in script
    assert "--store-dir" in script
    assert "pnpm-store" in script
    assert "$processId -le 0" in script
    assert "verify-labels-smoke" in script
    assert "verify-files-smoke" in script
    assert "verify-detail-smoke" in script
    assert "verify-search-smoke" in script
    assert "verify-clawhub-search-smoke" in script
    assert "verify-clawhub-resolve-smoke" in script
    assert "verify-clawhub-skill-smoke" in script
    assert "verify-clawhub-list-smoke" in script
    assert "verify-auth-me-smoke" in script
    assert "verify-auth-detail-smoke" in script
    assert "verify-owner-preview-detail-smoke" in script
    assert "verify-owner-preview-version-smoke" in script
    assert "verify-owner-preview-files-smoke" in script
    assert "verify-owner-preview-tag-files-smoke" in script
    assert "verify-file-content-smoke" in script
    assert "verify-download-smoke" in script
    assert "verify-owner-preview-resolve-smoke" in script
    assert "verify-owner-preview-compare-smoke" in script
    assert "verify-publish-foundation-smoke" in script
    assert "verify-publish-dry-run-smoke" in script
    assert "verify-publish-storage-foundation-smoke" in script
    assert "verify-publish-db-foundation-smoke" in script
    assert "verify-publish-side-effects-foundation-smoke" in script
    assert "verify-publish-replacement-foundation-smoke" in script
    assert "Invoke-LabelsContractComparison" in script
    assert "Invoke-FilesContractComparison" in script
    assert "Invoke-DetailContractComparison" in script
    assert "Invoke-SearchContractComparison" in script
    assert "Invoke-ClawHubSearchContractComparison" in script
    assert "Invoke-ClawHubResolveContractComparison" in script
    assert "Invoke-ClawHubSkillContractComparison" in script
    assert "Invoke-ClawHubListContractComparison" in script
    assert "Invoke-AuthMeContractComparison" in script
    assert "Invoke-AuthenticatedDetailContractComparison" in script
    assert "Invoke-OwnerPreviewDetailContractComparison" in script
    assert "Invoke-OwnerPreviewVersionContractComparison" in script
    assert "Invoke-OwnerPreviewFilesContractComparison" in script
    assert "Invoke-OwnerPreviewTagFilesContractComparison" in script
    assert "Invoke-FileContentContractComparison" in script
    assert "Invoke-DownloadContractComparison" in script
    assert "Invoke-OwnerPreviewResolveContractComparison" in script
    assert "Invoke-OwnerPreviewCompareContractComparison" in script
    assert "Invoke-PublishFoundationContractComparison" in script
    assert "Invoke-PublishDryRunTests" in script
    assert "Invoke-PublishStorageFoundationTests" in script
    assert "Invoke-PublishDbFoundationTests" in script
    assert "Invoke-PublishSideEffectsFoundationTests" in script
    assert "Invoke-PublishReplacementFoundationTests" in script
    assert "labels-contract-result.json" in script
    assert "files-contract-result.json" in script
    assert "detail-contract-result.json" in script
    assert "search-contract-result.json" in script
    assert "clawhub-search-contract-result.json" in script
    assert "clawhub-resolve-contract-result.json" in script
    assert "clawhub-skill-contract-result.json" in script
    assert "clawhub-list-contract-result.json" in script
    assert "auth-me-contract-result.json" in script
    assert "auth-detail-contract-result.json" in script
    assert "owner-preview-detail-contract-result.json" in script
    assert "owner-preview-version-contract-result.json" in script
    assert "owner-preview-files-contract-result.json" in script
    assert "owner-preview-tag-files-contract-result.json" in script
    assert "file-content-contract-result.json" in script
    assert "download-contract-result.json" in script
    assert "owner-preview-resolve-contract-result.json" in script
    assert "owner-preview-compare-contract-result.json" in script
    assert "publish-foundation-contract-result.json" in script
    assert "publish-dry-run-contract-result.json" in script
    assert "publish-storage-foundation-contract-result.json" in script
    assert "publish-db-foundation-contract-result.json" in script
    assert "publish-side-effects-foundation-contract-result.json" in script
    assert "publish-replacement-foundation-contract-result.json" in script
    assert "tests/test_publish_package.py" in script
    assert "tests/test_publish_dry_run.py" in script
    assert "tests/test_publish_storage.py" in script
    assert "tests/test_publish_transaction.py" in script
    assert "tests/test_publish_side_effects.py" in script
    assert "tests/test_publish_replacement.py" in script
    assert "javaMatchesPython" in script
    assert "java-storage" in script
    assert "PLAYWRIGHT_BROWSERS_PATH" in script
    assert "ms-playwright" in script
    assert "playwright.CMD' -Arguments @('install', 'chromium')" in script


def test_hybrid_local_e2e_doc_covers_windows_macos_and_ubuntu() -> None:
    doc = read_hybrid_doc()

    assert "## Windows" in doc
    assert "## macOS" in doc
    assert "## Ubuntu" in doc
    assert "Docker Desktop" in doc
    assert "Colima" in doc
    assert "Git for Windows" in doc
    assert "brew install make" in doc
    assert "sudo apt-get install" in doc
    assert "Ubuntu does not use Docker for dependency services" in doc
    assert "organization-managed PostgreSQL" in doc
    assert "organization-managed Redis" in doc
    assert "organization-managed MinIO" in doc
    assert "server/skillhub-app/src/main/resources/application-local.yml" in doc
    assert "powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\\dev-hybrid.ps1 up" in doc
    assert "make dev-all-hybrid" in doc
    assert "make test-e2e-smoke-hybrid" in doc


def test_sdlc_readme_documents_team_environment_rules_in_chinese() -> None:
    readme = read_sdlc_readme()

    assert "SkillHub SDLC README" in readme
    assert "專案定位" in readme
    assert "Backend Python Migration" in readme
    assert "server/ 不可修改" in readme
    assert "Windows" in readme
    assert "macOS" in readme
    assert "Ubuntu" in readme
    assert "Docker" in readme
    assert "server/skillhub-app/src/main/resources/application-local.yml" in readme
    assert "PostgreSQL" in readme
    assert "Redis" in readme
    assert "MinIO" in readme
    assert "plan" in readme
    assert "result" in readme
