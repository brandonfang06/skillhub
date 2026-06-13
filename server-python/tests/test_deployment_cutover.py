from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_kubernetes_backend_deployment_uses_python_runtime_contract() -> None:
    deployment = read("deploy/k8s/base/backend-deployment.yaml")

    assert "ghcr.io/iflytek/skillhub-server-python:edge" in deployment
    assert "SKILLHUB_DATABASE_URL" in deployment
    assert "SKILLHUB_REDIS_URL" in deployment
    assert "SKILLHUB_STORAGE_BASE_PATH" in deployment
    assert "SKILLHUB_SECURITY_SCANNER_BASE_URL" in deployment
    assert "SKILLHUB_SESSION_COOKIE_SECURE" in deployment
    assert "path: /api/v1/health" in deployment
    assert "SPRING_" not in deployment
    assert "/actuator/health" not in deployment


def test_kubernetes_config_and_secret_examples_expose_python_env_inputs() -> None:
    configmap = read("deploy/k8s/base/configmap.yaml")
    secret_example = read("deploy/k8s/base/secret.yaml.example")

    assert "database-url:" in secret_example
    assert "postgresql+asyncpg://skillhub:change-me@postgres:5432/skillhub" in secret_example
    assert "redis-url:" in configmap
    assert "security-scanner-base-url:" in configmap
    assert "session-cookie-secure:" in configmap
    assert "spring-datasource" not in secret_example
    assert "SPRING_" not in configmap
    assert "SPRING_" not in secret_example


def test_release_compose_uses_python_server_image_and_healthcheck() -> None:
    release_compose = read("compose.release.yml")

    assert "ghcr.io/iflytek/skillhub-server-python" in release_compose
    assert "SKILLHUB_DATABASE_URL:" in release_compose
    assert "SKILLHUB_REDIS_URL:" in release_compose
    assert "SKILLHUB_SECURITY_SCANNER_BASE_URL:" in release_compose
    assert "http://localhost:8080/api/v1/health" in release_compose
    assert "SPRING_" not in release_compose
    assert "/actuator/health" not in release_compose


def test_kubernetes_readme_describes_three_python_cutover_deployments() -> None:
    readme = read("deploy/k8s/README.md")

    assert "frontend, backend-python, and scanner" in readme
    assert "SKILLHUB_DATABASE_URL" in readme
    assert "SKILLHUB_REDIS_URL" in readme
    assert "SKILLHUB_SECURITY_SCANNER_BASE_URL" in readme
    assert "/api/v1/health" in readme
    assert "SPRING_" not in readme
    assert "/actuator/health" not in readme
