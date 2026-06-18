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
    assert "SPRING_DATA_REDIS_HOST" in deployment
    assert "SPRING_DATA_REDIS_PASSWORD" in deployment
    assert "SPRING_DATA_REDIS_DATABASE" in deployment
    assert "SPRING_DATA_REDIS_SENTINEL_MASTER" in deployment
    assert "SPRING_DATA_REDIS_SENTINEL_NODES" in deployment
    assert "SPRING_DATA_REDIS_SENTINEL_PASSWORD" in deployment
    assert "SPRING_DATA_REDIS_USERNAME" in deployment
    assert "SPRING_DATA_REDIS_SSL_ENABLED" in deployment
    assert "SKILLHUB_STORAGE_PROVIDER" in deployment
    assert "SKILLHUB_STORAGE_S3_ENDPOINT" in deployment
    assert "SKILLHUB_STORAGE_S3_PROXY_ENDPOINT" in deployment
    assert "SKILLHUB_STORAGE_S3_PUBLIC_ENDPOINT" in deployment
    assert "SKILLHUB_STORAGE_S3_BUCKET" in deployment
    assert "SKILLHUB_SECURITY_SCANNER_BASE_URL" in deployment
    assert "SKILLHUB_SESSION_COOKIE_SECURE" in deployment
    assert "SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID" in deployment
    assert "SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI" in deployment
    assert "OAUTH2_GITHUB" not in deployment
    assert "OAUTH2_GITLAB" not in deployment
    assert "path: /api/v1/health" in deployment
    assert "SKILLHUB_STORAGE_BASE_PATH" not in deployment
    assert "skillhub-storage-pvc" not in deployment
    assert "/actuator/health" not in deployment


def test_kubernetes_config_and_secret_examples_expose_python_env_inputs() -> None:
    configmap = read("deploy/k8s/base/configmap.yaml")
    secret_example = read("deploy/k8s/base/secret.yaml.example")

    assert "database-url:" in secret_example
    assert "postgresql+asyncpg://skillhub:change-me@postgres.example.internal:5432/skillhub" in secret_example
    assert "redis-host:" in configmap
    assert "redis-sentinel-master:" in configmap
    assert "redis-sentinel-nodes:" in configmap
    assert "redis-ssl-enabled:" in configmap
    assert "redis-password:" in secret_example
    assert "redis-username:" in secret_example
    assert "redis-sentinel-password:" in secret_example
    assert "redis-url:" in secret_example
    assert "redis-url:" not in configmap
    assert "storage-provider: s3" in configmap
    assert "storage-s3-endpoint:" in configmap
    assert "storage-s3-proxy-endpoint:" in configmap
    assert "storage-s3-public-endpoint:" in configmap
    assert "storage-s3-bucket:" in configmap
    assert "oauth2-keycloak-issuer-uri:" in configmap
    assert "oauth2-gitlab" not in configmap
    assert "security-scanner-base-url:" in configmap
    assert "session-cookie-secure:" in configmap
    assert "PersistentVolumeClaim" not in configmap
    assert "spring-datasource" not in secret_example
    assert "oauth2-keycloak-client-id:" in secret_example
    assert "oauth2-keycloak-client-secret:" in secret_example
    assert "oauth2-github" not in secret_example
    assert "oauth2-gitlab" not in secret_example


def test_kubernetes_manifests_do_not_deploy_external_infrastructure() -> None:
    manifest_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "deploy/k8s").rglob("*.yaml")
        if path.name != "secret.yaml.example"
    )

    assert "kind: StatefulSet" not in manifest_text
    assert "name: postgres" not in manifest_text
    assert "name: redis" not in manifest_text
    assert "kind: PersistentVolumeClaim" not in manifest_text


def test_release_compose_uses_python_server_image_and_healthcheck() -> None:
    release_compose = read("compose.release.yml")
    release_env = read(".env.release.example")

    assert "ghcr.io/iflytek/skillhub-server-python" in release_compose
    assert "SKILLHUB_SERVER_IMAGE=ghcr.io/iflytek/skillhub-server-python" in release_env
    assert "SKILLHUB_DATABASE_URL:" in release_compose
    assert "SPRING_DATA_REDIS_PASSWORD:" in release_compose
    assert "--requirepass" in release_compose
    assert "SKILLHUB_SECURITY_SCANNER_BASE_URL:" in release_compose
    assert "SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID:" in release_compose
    assert "SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI:" in release_compose
    assert "OAUTH2_GITHUB" not in release_compose
    assert "OAUTH2_GITLAB" not in release_compose
    assert "SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID=" in release_env
    assert "SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI=" in release_env
    assert "OAUTH2_GITHUB" not in release_env
    assert "OAUTH2_GITLAB" not in release_env
    assert "SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY" not in release_env
    assert "SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY" not in release_compose
    assert "http://localhost:8080/api/v1/health" in release_compose
    assert "/actuator/health" not in release_compose


def test_kubernetes_readme_describes_three_python_cutover_deployments() -> None:
    readme = read("deploy/k8s/README.md")

    assert "skillhub-web" in readme
    assert "skillhub-server" in readme
    assert "skillhub-scanner" in readme
    assert "SKILLHUB_DATABASE_URL" in readme
    assert "SPRING_DATA_REDIS_PASSWORD" in readme
    assert "SPRING_DATA_REDIS_SENTINEL_MASTER" in readme
    assert "SKILLHUB_STORAGE_S3_ENDPOINT" in readme
    assert "SKILLHUB_STORAGE_S3_PROXY_ENDPOINT" in readme
    assert "SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID" in readme
    assert "SKILLHUB_SECURITY_SCANNER_BASE_URL" in readme
    assert "/api/v1/health" in readme
    assert "/actuator/health" not in readme


def test_kubernetes_env_manual_documents_external_dependencies() -> None:
    manual = read("deploy/k8s/environment-variables.zh.md")

    assert "PostgreSQL" in manual
    assert "Redis" in manual
    assert "MinIO / S3" in manual
    assert "Keycloak / OIDC" in manual
    assert "SKILLHUB_DATABASE_URL" in manual
    assert "SKILLHUB_REDIS_URL" in manual
    assert "SPRING_DATA_REDIS_PASSWORD" in manual
    assert "SPRING_DATA_REDIS_SENTINEL_MASTER" in manual
    assert "SPRING_DATA_REDIS_SENTINEL_NODES" in manual
    assert "SPRING_DATA_REDIS_SENTINEL_PASSWORD" in manual
    assert "redis://:password@redis.example.internal:6379/0" in manual
    assert "SKILLHUB_STORAGE_S3_ENDPOINT" in manual
    assert "SKILLHUB_STORAGE_S3_PROXY_ENDPOINT" in manual
    assert "SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI" in manual
    assert "SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY" not in manual
    assert "Presigned URL" not in manual


def test_python_backend_env_manual_lists_runtime_env_vars_without_presign() -> None:
    manual = read("server-python/ENVIRONMENT_VARIABLES.md")

    assert "SKILLHUB_DATABASE_URL" in manual
    assert "SPRING_DATA_REDIS_SENTINEL_MASTER" in manual
    assert "SKILLHUB_STORAGE_S3_ENDPOINT" in manual
    assert "SKILLHUB_STORAGE_S3_PROXY_ENDPOINT" in manual
    assert "SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID" in manual
    assert "SKILLHUB_SECURITY_SCANNER_BASE_URL" in manual
    assert "SKILL_SCANNER_LLM_API_KEY" not in manual
    assert "SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY" not in manual
    assert "presigned" not in manual.lower()


def test_kubernetes_manifests_do_not_expose_s3_presign_configuration() -> None:
    manifest_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "deploy/k8s").rglob("*.yaml")
        if path.name != "secret.yaml.example"
    )

    assert "SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY" not in manifest_text
    assert "storage-s3-presign-expiry" not in manifest_text


def test_web_static_assets_include_keycloak_login_icon() -> None:
    icon = read("web/public/keycloak-logo.svg")

    assert "<title>Keycloak</title>" in icon
    assert "viewBox=\"0 0 24 24\"" in icon


def test_plain_kubernetes_manifests_cover_three_python_workloads() -> None:
    frontend_service = read("deploy/k8s/plain/frontend/service.yaml")
    frontend_deployment = read("deploy/k8s/plain/frontend/deployment.yaml")
    backend_config = read("deploy/k8s/plain/backend/config.yaml")
    backend_secret = read("deploy/k8s/plain/backend/secret.yaml.example")
    backend_service = read("deploy/k8s/plain/backend/service.yaml")
    backend_deployment = read("deploy/k8s/plain/backend/deployment.yaml")
    scanner_secret = read("deploy/k8s/plain/scanner/secret.yaml.example")
    scanner_service = read("deploy/k8s/plain/scanner/service.yaml")
    scanner_deployment = read("deploy/k8s/plain/scanner/deployment.yaml")
    readme = read("deploy/k8s/plain/README.md")
    frontend = "\n".join([frontend_service, frontend_deployment])
    backend = "\n".join([backend_config, backend_secret, backend_service, backend_deployment])
    scanner = "\n".join([scanner_secret, scanner_service, scanner_deployment])
    combined = "\n".join([frontend, backend, scanner])

    assert "kind: Kustomization" not in combined
    assert "name: skillhub-web" in frontend
    assert "ghcr.io/iflytek/skillhub-web:edge" in frontend
    assert "SKILLHUB_API_UPSTREAM" in frontend
    assert "name: skillhub-server" in backend
    assert "ghcr.io/iflytek/skillhub-server-python:edge" in backend
    assert "name: skillhub-config" in backend
    assert "name: skillhub-secret" in backend
    assert "SKILLHUB_DATABASE_URL" in backend
    assert "SPRING_DATA_REDIS_PASSWORD" in backend
    assert "SPRING_DATA_REDIS_SENTINEL_MASTER" in backend
    assert "SPRING_DATA_REDIS_SENTINEL_NODES" in backend
    assert "SPRING_DATA_REDIS_SENTINEL_PASSWORD" in backend
    assert "redis-sentinel-master:" in backend_config
    assert "redis-username:" in backend_secret
    assert "SKILLHUB_STORAGE_S3_PROXY_ENDPOINT" in backend
    assert "SKILLHUB_SCANNER_USE_LLM" in backend
    assert "scanner-ai-defense-api-key" in backend_secret
    assert "SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID" in backend
    assert "SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI" in backend
    assert "OAUTH2_GITHUB" not in backend
    assert "OAUTH2_GITLAB" not in backend
    assert "SKILL_SCANNER_LLM_API_KEY" not in backend
    assert "skill-scanner-llm-api-key" not in backend_secret
    assert "name: skillhub-scanner" in scanner
    assert "name: skillhub-scanner-secret" in scanner_secret
    assert "ghcr.io/iflytek/skillhub-scanner:edge" in scanner
    assert "SKILL_SCANNER_LLM_API_KEY" in scanner
    assert "cp deploy/k8s/plain/backend/secret.yaml.example deploy/k8s/plain/backend/secret.yaml" in readme
    assert "cp deploy/k8s/plain/scanner/secret.yaml.example deploy/k8s/plain/scanner/secret.yaml" in readme
    assert "kubectl -n skillhub apply -f deploy/k8s/plain/backend/" in readme
    assert "kubectl -n skillhub apply -f deploy/k8s/plain/scanner/" in readme
    assert "kubectl -n skillhub apply -f deploy/k8s/plain/frontend/" in readme
