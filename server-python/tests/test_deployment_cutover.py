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
    assert "SKILLHUB_DOWNLOAD_REQUIRE_AUTH" not in deployment
    assert "SKILLHUB_LOCAL_REGISTRATION_ENABLED" in deployment
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
    assert "download-require-auth" not in configmap
    assert "local-registration-enabled: \"false\"" in configmap
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
    assert "SKILLHUB_PUBLISH_ALLOWED_FILE_EXTENSIONS:" in release_compose
    assert "SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS:" in release_compose
    assert "SKILLHUB_DOWNLOAD_REQUIRE_AUTH" not in release_compose
    assert "SKILLHUB_SECURITY_SCANNER_BASE_URL:" in release_compose
    assert "SKILLHUB_LOCAL_REGISTRATION_ENABLED:" in release_compose
    assert "SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID:" in release_compose
    assert "SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI:" in release_compose
    assert "OAUTH2_GITHUB" not in release_compose
    assert "OAUTH2_GITLAB" not in release_compose
    assert "SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID=" in release_env
    assert "SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI=" in release_env
    assert "SKILLHUB_PUBLISH_ALLOWED_FILE_EXTENSIONS=" in release_env
    assert "SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS=12" in release_env
    assert "SKILLHUB_DOWNLOAD_REQUIRE_AUTH" not in release_env
    assert "SKILLHUB_LOCAL_REGISTRATION_ENABLED=true" in release_env
    assert "OAUTH2_GITHUB" not in release_env
    assert "OAUTH2_GITLAB" not in release_env
    assert "SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY" not in release_env
    assert "SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY" not in release_compose
    assert "http://localhost:8080/api/v1/health" in release_compose
    assert "/actuator/health" not in release_compose


def test_web_dockerfile_normalizes_runtime_entrypoint_line_endings() -> None:
    dockerfile = read("web/Dockerfile")
    copy_entrypoint = (
        "COPY docker-entrypoint.d/30-runtime-config.sh "
        "/docker-entrypoint.d/30-runtime-config.sh"
    )
    normalize_entrypoint = (
        "RUN sed -i 's/\\r$//' /docker-entrypoint.d/30-runtime-config.sh"
    )
    chmod_entrypoint = "RUN chmod +x /docker-entrypoint.d/30-runtime-config.sh"

    assert copy_entrypoint in dockerfile
    assert normalize_entrypoint in dockerfile
    assert chmod_entrypoint in dockerfile
    assert (
        dockerfile.index(copy_entrypoint)
        < dockerfile.index(normalize_entrypoint)
        < dockerfile.index(chmod_entrypoint)
    )


def test_cli_registry_url_override_is_wired_only_to_frontend_runtime() -> None:
    release_env = read(".env.release.example")
    release_compose = read("compose.release.yml")
    runtime_template = read("web/runtime-config.js.template")
    entrypoint = read("web/docker-entrypoint.d/30-runtime-config.sh")
    base_config = read("deploy/k8s/base/configmap.yaml")
    plain_config = read("deploy/k8s/plain/backend/config.yaml")
    base_frontend = read("deploy/k8s/base/frontend-deployment.yaml")
    plain_frontend = read("deploy/k8s/plain/frontend/deployment.yaml")
    base_backend = read("deploy/k8s/base/backend-deployment.yaml")
    plain_backend = read("deploy/k8s/plain/backend/deployment.yaml")
    readme = read("deploy/k8s/README.md")
    env_manual = read("deploy/k8s/environment-variables.zh.md")

    server_service = release_compose.partition("\n  server:\n")[2].partition("\n  web:\n")[0]
    web_service = release_compose.partition("\n  web:\n")[2].partition("\nvolumes:\n")[0]
    cli_registry_env = """            - name: SKILLHUB_WEB_CLI_REGISTRY_URL
              valueFrom:
                configMapKeyRef:
                  name: skillhub-config
                  key: cli-registry-url
                  optional: true"""

    assert server_service
    assert web_service
    assert "SKILLHUB_WEB_CLI_REGISTRY_URL=" in release_env
    assert (
        "SKILLHUB_WEB_CLI_REGISTRY_URL: ${SKILLHUB_WEB_CLI_REGISTRY_URL:-}"
        in web_service
    )
    assert "SKILLHUB_PUBLIC_BASE_URL" in web_service
    assert "SKILLHUB_WEB_CLI_REGISTRY_URL" not in server_service
    assert 'cliRegistryUrl: "${SKILLHUB_WEB_CLI_REGISTRY_URL}"' in runtime_template
    assert ': "${SKILLHUB_WEB_CLI_REGISTRY_URL:=}"' in entrypoint
    runtime_substitution = entrypoint.partition("# Generate runtime-config.js")[2].partition(
        "# Generate registry/skill.md"
    )[0]
    assert "${SKILLHUB_WEB_CLI_REGISTRY_URL}" in runtime_substitution

    assert 'cli-registry-url: ""' in base_config
    assert 'cli-registry-url: ""' in plain_config
    for frontend in (base_frontend, plain_frontend):
        assert cli_registry_env in frontend
        assert "SKILLHUB_PUBLIC_BASE_URL" not in frontend
    assert "SKILLHUB_WEB_CLI_REGISTRY_URL" not in base_backend
    assert "SKILLHUB_WEB_CLI_REGISTRY_URL" not in plain_backend

    assert "public-base-url:" in base_config
    assert "public-base-url:" in plain_config
    assert "SKILLHUB_PUBLIC_BASE_URL" in release_compose
    assert "SKILLHUB_PUBLIC_BASE_URL" in runtime_template

    normalized_readme = " ".join(readme.split())
    assert (
        "Optional frontend-only registry override used in copied CLI install commands."
        in normalized_readme
    )
    assert "full absolute HTTP or HTTPS URL without a trailing slash" in normalized_readme
    assert (
        "When blank, it falls back to the existing frontend app URL; in the current "
        "K8s manifests that is browser origin."
    ) in normalized_readme
    assert (
        "`public-base-url` still controls backend OAuth callbacks and generated public "
        "links, while browser API and OAuth traffic are unchanged."
    ) in normalized_readme
    assert "HTTP sends the CLI Bearer token in plaintext without TLS." in normalized_readme
    assert (
        "CLI credentials and installed-skill inventory are scoped by the exact registry URL"
        in normalized_readme
    )
    assert "skillhub login --registry http://host --token <token>" in normalized_readme
    assert "SKILLHUB_TOKEN" in normalized_readme
    assert "HTTP endpoint must not redirect the CLI back to HTTPS." in normalized_readme

    normalized_manual = " ".join(env_manual.split())
    assert (
        "frontend-only install command override，只調整 Skill 頁面複製的 CLI 指令。"
        in normalized_manual
    )
    assert "完整的 absolute HTTP/HTTPS URL，且不要加 trailing slash" in normalized_manual
    assert (
        "留空時會 fallback 到既有 frontend app URL；目前 K8s manifests 的該值是 "
        "browser origin。"
    ) in normalized_manual
    assert (
        "`public-base-url` 仍控制 backend OAuth callback 與 public-link 行為；"
        "browser API/OAuth traffic 不受影響。"
    ) in normalized_manual
    assert (
        "HTTP 會讓 CLI Bearer token 在沒有 TLS 的情況下以明文傳輸。"
        in normalized_manual
    )
    assert (
        "CLI credential 與 installed-skill inventory 依 exact registry URL 分開"
        in normalized_manual
    )
    assert "skillhub login --registry http://host --token <token>" in normalized_manual
    assert "SKILLHUB_TOKEN" in normalized_manual
    assert "HTTP endpoint 不可 redirect CLI 回 HTTPS。" in normalized_manual

    assert "# Blank falls back to SKILLHUB_PUBLIC_BASE_URL." in release_env
    for document in (readme, env_manual, release_env):
        assert "NODE_TLS_REJECT_UNAUTHORIZED=0" not in document


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
    assert "SKILLHUB_LOCAL_REGISTRATION_ENABLED" in readme
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
    assert "SKILLHUB_PUBLISH_ALLOWED_FILE_EXTENSIONS" in manual
    assert "SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS" in manual
    assert "SKILLHUB_DOWNLOAD_REQUIRE_AUTH" not in manual
    assert "redis://:password@redis.example.internal:6379/0" in manual
    assert "SKILLHUB_STORAGE_S3_ENDPOINT" in manual
    assert "SKILLHUB_STORAGE_S3_PROXY_ENDPOINT" in manual
    assert "SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI" in manual
    assert "SKILLHUB_LOCAL_REGISTRATION_ENABLED" in manual
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
    assert "SKILLHUB_PUBLISH_ALLOWED_FILE_EXTENSIONS" in manual
    assert "SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS" in manual
    assert "SKILLHUB_DOWNLOAD_REQUIRE_AUTH" not in manual
    assert "SKILLHUB_LOCAL_REGISTRATION_ENABLED" in manual
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
    assert "SKILLHUB_PUBLISH_ALLOWED_FILE_EXTENSIONS" in backend
    assert "publish-allowed-file-extensions:" in backend_config
    assert "SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS" in backend
    assert "download-analytics-retention-months: \"12\"" in backend_config
    assert "SKILLHUB_DOWNLOAD_REQUIRE_AUTH" not in backend
    assert "download-require-auth" not in backend_config
    assert "SKILLHUB_LOCAL_REGISTRATION_ENABLED" in backend
    assert "local-registration-enabled: \"false\"" in backend_config
    assert "SKILLHUB_LOCAL_REGISTRATION_ENABLED" in frontend
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
