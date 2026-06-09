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

    assert "[ValidateSet(" in script
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
    assert "verify-publish-transaction-split-smoke" in script
    assert "verify-publish-orchestration-foundation-smoke" in script
    assert "verify-publish-scanner-handoff-smoke" in script
    assert "verify-publish-cli-replacement-lookup-smoke" in script
    assert "verify-publish-pending-auto-withdraw-smoke" in script
    assert "verify-publish-storage-failure-cleanup-smoke" in script
    assert "verify-cli-publish-write-ownership-smoke" in script
    assert "verify-portal-publish-write-ownership-smoke" in script
    assert "verify-root-legacy-publish-write-ownership-smoke" in script
    assert "verify-publish-scanner-result-processing-smoke" in script
    assert "verify-publish-scan-task-worker-boundary-smoke" in script
    assert "verify-publish-scan-consumer-runtime-smoke" in script
    assert "verify-publish-scanner-http-client-smoke" in script
    assert "verify-publish-scan-daemon-supervisor-smoke" in script
    assert "verify-review-approve-smoke" in script
    assert "verify-review-reject-withdraw-smoke" in script
    assert "verify-review-submit-smoke" in script
    assert "verify-review-list-smoke" in script
    assert "verify-review-detail-smoke" in script
    assert "verify-review-skill-detail-smoke" in script
    assert "verify-review-file-smoke" in script
    assert "verify-review-download-smoke" in script
    assert "verify-promotion-read-smoke" in script
    assert "verify-promotion-submit-reject-smoke" in script
    assert "verify-promotion-approve-smoke" in script
    assert "verify-skill-lifecycle-archive-smoke" in script
    assert "verify-skill-version-delete-smoke" in script
    assert "verify-skill-version-withdraw-review-smoke" in script
    assert "verify-skill-confirm-publish-smoke" in script
    assert "verify-skill-submit-review-smoke" in script
    assert "verify-skill-rerelease-smoke" in script
    assert "verify-admin-skill-hide-unhide-smoke" in script
    assert "verify-admin-version-yank-smoke" in script
    assert "submitReviewBoundaryStillPythonOwned" in script
    assert "confirmPublishBoundaryStillPythonOwned" in script
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
    assert "Invoke-PublishTransactionSplitTests" in script
    assert "Invoke-PublishOrchestrationFoundationTests" in script
    assert "Invoke-PublishScannerHandoffTests" in script
    assert "Invoke-PublishScannerHandoffContractComparison" in script
    assert "Invoke-PublishCliReplacementLookupTests" in script
    assert "Invoke-PublishCliReplacementLookupContractComparison" in script
    assert "Invoke-PublishPendingAutoWithdrawTests" in script
    assert "Invoke-PublishPendingAutoWithdrawContractComparison" in script
    assert "Invoke-PublishStorageFailureCleanupTests" in script
    assert "Invoke-PublishStorageFailureCleanupContractComparison" in script
    assert "Invoke-CliPublishWriteOwnershipTests" in script
    assert "Invoke-CliPublishWriteOwnershipContractComparison" in script
    assert "Invoke-PortalPublishWriteOwnershipTests" in script
    assert "Invoke-PortalPublishWriteOwnershipContractComparison" in script
    assert "Invoke-RootLegacyPublishWriteOwnershipTests" in script
    assert "Invoke-RootLegacyPublishWriteOwnershipContractComparison" in script
    assert "Invoke-LegacyPublishPostJson" in script
    assert "Invoke-ClawHubRootPublishPostJson" in script
    assert "Invoke-PublishScannerResultProcessingTests" in script
    assert "Invoke-PublishScannerResultProcessingContractComparison" in script
    assert "Invoke-PublishScanTaskWorkerBoundaryTests" in script
    assert "Invoke-PublishScanTaskWorkerBoundaryContractComparison" in script
    assert "Invoke-PublishScanConsumerRuntimeTests" in script
    assert "Invoke-PublishScanConsumerRuntimeContractComparison" in script
    assert "Invoke-PublishScannerHttpClientTests" in script
    assert "Invoke-PublishScannerHttpClientContractComparison" in script
    assert "Invoke-PublishScanDaemonSupervisorTests" in script
    assert "Invoke-PublishScanDaemonSupervisorContractComparison" in script
    assert "Invoke-ReviewApproveTests" in script
    assert "Invoke-ReviewApproveContractComparison" in script
    assert "Invoke-ReviewRejectWithdrawTests" in script
    assert "Invoke-ReviewRejectWithdrawContractComparison" in script
    assert "Invoke-ReviewSubmitTests" in script
    assert "Invoke-ReviewSubmitContractComparison" in script
    assert "Invoke-ReviewListTests" in script
    assert "Invoke-ReviewListContractComparison" in script
    assert "Invoke-ReviewDetailTests" in script
    assert "Invoke-ReviewDetailContractComparison" in script
    assert "Invoke-ReviewSkillDetailTests" in script
    assert "Invoke-ReviewSkillDetailContractComparison" in script
    assert "Invoke-ReviewFileTests" in script
    assert "Invoke-ReviewFileContractComparison" in script
    assert "Invoke-ReviewDownloadTests" in script
    assert "Invoke-ReviewDownloadContractComparison" in script
    assert "Invoke-PromotionReadTests" in script
    assert "Invoke-PromotionReadContractComparison" in script
    assert "Invoke-PromotionSubmitRejectTests" in script
    assert "Invoke-PromotionSubmitRejectContractComparison" in script
    assert "Invoke-PromotionApproveTests" in script
    assert "Invoke-PromotionApproveContractComparison" in script
    assert "Invoke-SkillLifecycleArchiveTests" in script
    assert "Invoke-SkillLifecycleArchiveContractComparison" in script
    assert "Invoke-SkillVersionDeleteTests" in script
    assert "Invoke-SkillVersionDeleteContractComparison" in script
    assert "Invoke-SkillVersionWithdrawReviewTests" in script
    assert "Invoke-SkillVersionWithdrawReviewContractComparison" in script
    assert "Invoke-SkillConfirmPublishTests" in script
    assert "Invoke-SkillConfirmPublishContractComparison" in script
    assert "Invoke-SkillSubmitReviewTests" in script
    assert "Invoke-SkillSubmitReviewContractComparison" in script
    assert "Invoke-SkillRereleaseTests" in script
    assert "Invoke-SkillRereleaseContractComparison" in script
    assert "Invoke-AdminSkillHideUnhideTests" in script
    assert "Invoke-AdminSkillHideUnhideContractComparison" in script
    assert "Invoke-AdminVersionYankTests" in script
    assert "Invoke-AdminVersionYankContractComparison" in script
    assert "apply_scan_result_fixture.py" in script
    assert "process_scan_task_fixture.py" in script
    assert "consume_scan_task_fixture.py" in script
    assert "--scanner-source" in script
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
    assert "publish-transaction-split-contract-result.json" in script
    assert "publish-orchestration-foundation-contract-result.json" in script
    assert "publish-http-validate-contract-result.json" in script
    assert "publish-cli-write-direct-contract-result.json" in script
    assert "publish-scanner-handoff-contract-result.json" in script
    assert "publish-cli-replacement-lookup-contract-result.json" in script
    assert "publish-pending-auto-withdraw-contract-result.json" in script
    assert "publish-storage-failure-cleanup-contract-result.json" in script
    assert "cli-publish-write-ownership-contract-result.json" in script
    assert "portal-publish-write-ownership-contract-result.json" in script
    assert "root-legacy-publish-write-ownership-contract-result.json" in script
    assert "publish-scanner-result-processing-contract-result.json" in script
    assert "publish-scan-task-worker-boundary-contract-result.json" in script
    assert "publish-scan-consumer-runtime-contract-result.json" in script
    assert "publish-scanner-http-client-contract-result.json" in script
    assert "publish-scan-daemon-supervisor-contract-result.json" in script
    assert "review-approve-contract-result.json" in script
    assert "review-reject-withdraw-contract-result.json" in script
    assert "review-submit-contract-result.json" in script
    assert "review-list-contract-result.json" in script
    assert "review-detail-contract-result.json" in script
    assert "review-skill-detail-contract-result.json" in script
    assert "review-file-contract-result.json" in script
    assert "review-download-contract-result.json" in script
    assert "promotion-read-contract-result.json" in script
    assert "promotion-submit-reject-contract-result.json" in script
    assert "promotion-approve-contract-result.json" in script
    assert "skill-lifecycle-archive-contract-result.json" in script
    assert "skill-version-delete-contract-result.json" in script
    assert "skill-version-withdraw-review-contract-result.json" in script
    assert "skill-confirm-publish-contract-result.json" in script
    assert "skill-submit-review-contract-result.json" in script
    assert "skill-rerelease-contract-result.json" in script
    assert "admin-skill-hide-unhide-contract-result.json" in script
    assert "admin-version-yank-contract-result.json" in script
    assert "tests/test_publish_package.py" in script
    assert "tests/test_publish_dry_run.py" in script
    assert "tests/test_publish_storage.py" in script
    assert "tests/test_publish_transaction.py" in script
    assert "tests/test_publish_orchestration.py" in script
    assert "tests/test_publish_http_validate.py" in script
    assert "tests/test_publish_scanner_handoff.py" in script
    assert "tests/test_publish_scanner_result.py" in script
    assert "tests/test_publish_scan_worker.py" in script
    assert "tests/test_publish_scan_consumer.py" in script
    assert "tests/test_publish_scanner_client.py" in script
    assert "tests/test_publish_scan_daemon.py" in script
    assert "tests/test_review_approve.py" in script
    assert "tests/test_review_reject_withdraw.py" in script
    assert "tests/test_review_submit.py" in script
    assert "tests/test_review_list.py" in script
    assert "tests/test_review_detail.py" in script
    assert "tests/test_review_skill_detail.py" in script
    assert "tests/test_review_file_content.py" in script
    assert "tests/test_review_download.py" in script
    assert "tests/test_promotion_read.py" in script
    assert "tests/test_promotion_write.py" in script
    assert "tests/test_skill_lifecycle_archive.py" in script
    assert "tests/test_skill_lifecycle_delete_version.py" in script
    assert "tests/test_skill_lifecycle_withdraw_review.py" in script
    assert "tests/test_skill_lifecycle_confirm_publish.py" in script
    assert "tests/test_skill_lifecycle_submit_review.py" in script
    assert "tests/test_skill_lifecycle_rerelease.py" in script
    assert "tests/test_admin_skill_governance.py" in script
    assert "SKILLHUB_SCAN_CONSUMER_ENABLED" in script
    assert "tests/test_publish_side_effects.py" in script
    assert "tests/test_publish_replacement.py" in script
    assert "tests/test_publish_auto_withdraw.py" in script
    assert "python-storage-blocker" in script
    assert "scannerResultBoundary" in script
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
