from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_product_suite_sync_cronjob_is_optional_and_daily() -> None:
    cronjob = read(
        "deploy/k8s/addons/product-suite-admin-sync/cronjob.yaml"
    )
    addon = read(
        "deploy/k8s/addons/product-suite-admin-sync/kustomization.yaml"
    )
    base = read("deploy/k8s/base/kustomization.yaml")

    assert "kind: CronJob" in cronjob
    assert 'schedule: "0 2 * * *"' in cronjob
    assert "concurrencyPolicy: Forbid" in cronjob
    assert "successfulJobsHistoryLimit: 3" in cronjob
    assert "failedJobsHistoryLimit: 5" in cronjob
    assert "backoffLimit: 2" in cronjob
    assert "restartPolicy: Never" in cronjob
    assert "cronjob.yaml" in addon
    assert "product-suite-admin-sync" not in base


def test_product_suite_sync_cronjob_uses_python_command_and_shared_contract() -> None:
    cronjob = read(
        "deploy/k8s/addons/product-suite-admin-sync/cronjob.yaml"
    )

    assert "ghcr.io/iflytek/skillhub-server-python:edge" in cronjob
    assert "- uv" in cronjob
    assert "- run" in cronjob
    assert "- --no-sync" in cronjob
    assert "- python" in cronjob
    assert "- -m" in cronjob
    assert "- app.integrations.product_suite" in cronjob
    assert "SKILLHUB_DATABASE_URL" in cronjob
    assert "name: skillhub-secret" in cronjob
    assert "key: database-url" in cronjob
    assert "SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE" in cronjob
    assert "SKILLHUB_PRODUCT_SUITE_API_URL" in cronjob
    assert "SKILLHUB_PRODUCT_SUITE_API_TIMEOUT_SECONDS" in cronjob
    assert "SKILLHUB_PRODUCT_SUITE_IDENTITY_PROVIDER" in cronjob
    assert "name: skillhub-product-suite-sync-secret" in cronjob


def test_plain_cronjob_remains_an_explicit_example() -> None:
    example_path = (
        ROOT
        / "deploy/k8s/plain/backend/product-suite-admin-sync-cronjob.yaml.example"
    )
    enabled_path = (
        ROOT
        / "deploy/k8s/plain/backend/product-suite-admin-sync-cronjob.yaml"
    )
    example = example_path.read_text(encoding="utf-8")

    assert example_path.is_file()
    assert enabled_path.exists() is False
    assert "kind: CronJob" in example
    assert "app.integrations.product_suite" in example
    assert "- --no-sync" in example


def test_product_suite_sync_docs_explain_internal_image_and_opt_in() -> None:
    manual = read("server-python/PRODUCT_SUITE_ADMIN_SYNC.zh.md")
    addon_readme = read(
        "deploy/k8s/addons/product-suite-admin-sync/README.md"
    )
    k8s_readme = read("deploy/k8s/README.md")
    plain_readme = read("deploy/k8s/plain/README.md")

    assert "organization image" in addon_readme
    assert "kubectl apply -k deploy/k8s/addons/product-suite-admin-sync" in (
        addon_readme
    )
    assert "kubectl create job" in addon_readme
    assert "kubectl logs" in addon_readme
    assert "suspend" in addon_readme
    assert "backend deployment" in addon_readme.lower()
    assert "product-suite-admin-sync" in k8s_readme
    assert "product-suite-admin-sync-cronjob.yaml.example" in plain_readme
    assert "fetch_product_suite_owners" in manual
    assert "httpx" in manual


def test_pic_secret_example_does_not_define_a_shared_token_name() -> None:
    secret_example = read(
        "deploy/k8s/addons/product-suite-admin-sync/secret.yaml.example"
    )

    assert "kind: Secret" in secret_example
    assert "name: skillhub-product-suite-sync-secret" in secret_example
    assert "PIC_API_TOKEN" in secret_example
    assert "SKILLHUB_PRODUCT_SUITE_API_TOKEN" not in secret_example
