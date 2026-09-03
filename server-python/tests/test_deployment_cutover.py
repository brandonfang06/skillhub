from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

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
    assert "SKILLHUB_GLOBAL_NAMESPACE_AUTO_JOIN_ENABLED" in deployment
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
    assert "global-namespace-auto-join-enabled: \"false\"" in configmap
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
    assert "SKILLHUB_GLOBAL_NAMESPACE_AUTO_JOIN_ENABLED:" in release_compose
    assert 'test: ["CMD", "python", "-c"' in release_compose
    assert "urllib.request.urlopen" in release_compose
    assert 'test: ["CMD", "wget", "-qO-", "http://localhost:8080/api/v1/health"]' not in release_compose
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
    assert "SKILLHUB_GLOBAL_NAMESPACE_AUTO_JOIN_ENABLED=false" in release_env
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


def run_web_base_path_router(
    tmp_path: Path,
    base_path: str,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    shell = shutil.which("sh")
    assert shell is not None
    routing_config = tmp_path / "skillhub-base-path.conf"
    environment = {
        **os.environ,
        "SKILLHUB_WEB_BASE_PATH": base_path,
        "SKILLHUB_NGINX_BASE_PATH_CONFIG": routing_config.as_posix(),
    }
    result = subprocess.run(
        [shell, (ROOT / "web/docker-entrypoint.d/20-base-path-routing.sh").as_posix()],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, routing_config


@pytest.mark.parametrize("base_path", ["", "/"])
def test_web_base_path_router_keeps_root_deployment_unrewritten(
    tmp_path: Path,
    base_path: str,
) -> None:
    result, routing_config = run_web_base_path_router(tmp_path, base_path)

    assert result.returncode == 0, result.stderr
    generated = routing_config.read_text(encoding="utf-8")
    assert "location" not in generated
    assert "rewrite" not in generated


@pytest.mark.parametrize("base_path", ["/skillhub", "/skillhub/"])
def test_web_base_path_router_generates_exact_redirect_and_prefix_rewrite(
    tmp_path: Path,
    base_path: str,
) -> None:
    result, routing_config = run_web_base_path_router(tmp_path, base_path)

    assert result.returncode == 0, result.stderr
    generated = routing_config.read_text(encoding="utf-8")
    assert "location = /skillhub" in generated
    assert "absolute_redirect off;" in generated
    assert "return 301 /skillhub/;" in generated
    assert "location ^~ /skillhub/" in generated
    assert "rewrite ^/skillhub/(.*)$ /$1 last;" in generated


def test_web_image_installs_the_base_path_router_before_runtime_config() -> None:
    dockerfile = read("web/Dockerfile")
    nginx_config = read("web/nginx.conf.template")

    routing_copy = (
        "COPY docker-entrypoint.d/20-base-path-routing.sh "
        "/docker-entrypoint.d/20-base-path-routing.sh"
    )
    runtime_copy = (
        "COPY docker-entrypoint.d/30-runtime-config.sh "
        "/docker-entrypoint.d/30-runtime-config.sh"
    )
    assert routing_copy in dockerfile
    assert dockerfile.index(routing_copy) < dockerfile.index(runtime_copy)
    assert "include /etc/nginx/skillhub-base-path*.conf;" in nginx_config


def test_pr_workflow_runs_the_real_web_base_path_image_smoke_test() -> None:
    workflow = read(".github/workflows/pr-scripts.yml")

    assert "- 'web/**'" in workflow
    assert "bash scripts/tests/web-base-path-nginx-smoke-test.sh" in workflow


def test_operator_docs_preserve_existing_rewrite_and_root_deployment() -> None:
    readme = read("deploy/k8s/README.md")
    env_manual = read("deploy/k8s/environment-variables.zh.md")

    assert "The existing VirtualService rewrite remains supported" in readme
    assert "Root deployments remain unchanged" in readme
    assert "既有 VirtualService rewrite 仍受支援" in env_manual
    assert "root deployment 維持原行為" in env_manual


@pytest.mark.parametrize("base_path", ["/api", "/assets/nested"])
def test_web_runtime_entrypoint_rejects_reserved_first_segments(
    base_path: str,
) -> None:
    shell = shutil.which("sh")
    assert shell is not None
    result = subprocess.run(
        [shell, (ROOT / "web/docker-entrypoint.d/30-runtime-config.sh").as_posix()],
        cwd=ROOT,
        env={**os.environ, "SKILLHUB_WEB_BASE_PATH": base_path},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "SKILLHUB_WEB_BASE_PATH must not start with a reserved segment" in result.stderr


def test_web_runtime_entrypoint_rejects_misaligned_same_origin_api_base() -> None:
    shell = shutil.which("sh")
    assert shell is not None
    result = subprocess.run(
        [shell, (ROOT / "web/docker-entrypoint.d/30-runtime-config.sh").as_posix()],
        cwd=ROOT,
        env={
            **os.environ,
            "SKILLHUB_WEB_BASE_PATH": "/skillhub",
            "SKILLHUB_WEB_API_BASE_URL": "/other",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "SKILLHUB_WEB_API_BASE_URL must match SKILLHUB_WEB_BASE_PATH" in result.stderr


def test_web_image_generates_a_valid_runtime_base_path_document() -> None:
    vite_config = read("web/vite.config.ts")
    index_html = read("web/index.html")
    dockerfile = read("web/Dockerfile")
    runtime_template = read("web/runtime-config.js.template")
    entrypoint = read("web/docker-entrypoint.d/30-runtime-config.sh")

    assert "base: './'" in vite_config
    assert '<base href="/" />' in index_html
    assert '<html lang="zh-CN" translate="no" class="notranslate">' in index_html
    assert '<div id="root" translate="no" class="notranslate"></div>' in index_html
    assert '<div id="skillhub-portals" translate="no" class="notranslate"></div>' in index_html
    assert 'href="./favicon.svg"' in index_html
    assert (
        "sed 's|<base href=\"/\" />|<base href=\"${SKILLHUB_WEB_BASE_HREF}\" />|'"
        in dockerfile
    )
    assert "index.html.template" in dockerfile
    assert ': "${SKILLHUB_WEB_BASE_PATH:=}"' in entrypoint
    assert "Invalid SKILLHUB_WEB_BASE_PATH" in entrypoint
    assert "SKILLHUB_WEB_BASE_HREF" in entrypoint
    runtime_exports = entrypoint.partition("# Export runtime template variables")[2].partition(
        "# Generate index.html"
    )[0]
    for variable in (
        "SKILLHUB_WEB_BASE_HREF",
        "SKILLHUB_WEB_API_BASE_URL",
        "SKILLHUB_PUBLIC_BASE_URL",
        "SKILLHUB_WEB_BASE_PATH",
        "SKILLHUB_WEB_CLI_REGISTRY_URL",
        "SKILLHUB_WEB_AUTH_DIRECT_ENABLED",
        "SKILLHUB_WEB_AUTH_DIRECT_PROVIDER",
        "SKILLHUB_LOCAL_REGISTRATION_ENABLED",
        "SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_ENABLED",
        "SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_PROVIDER",
        "SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_AUTO",
        "SKILLHUB_WEB_PLAYGROUND_ENABLED",
        "SKILLHUB_WEB_PLAYGROUND_BASE_URL",
    ):
        assert variable in runtime_exports
    assert "index.html.template" in entrypoint
    assert 'basePath: "${SKILLHUB_WEB_BASE_PATH}"' in runtime_template


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("SKILLHUB_PUBLIC_BASE_URL", 'https://skills.example.com/";alert(1)//'),
        ("SKILLHUB_WEB_CLI_REGISTRY_URL", "https://skills.example.com\\evil"),
        ("SKILLHUB_WEB_AUTH_DIRECT_PROVIDER", "keycloak\nbroken"),
    ],
)
def test_web_runtime_entrypoint_rejects_javascript_breaking_values(
    variable: str,
    value: str,
) -> None:
    shell = shutil.which("sh")
    assert shell is not None
    environment = {**os.environ, variable: value}

    result = subprocess.run(
        [shell, (ROOT / "web/docker-entrypoint.d/30-runtime-config.sh").as_posix()],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert f"Invalid runtime template value: {variable}" in result.stderr


def test_trusted_forwarded_proto_is_opt_in_across_release_surfaces() -> None:
    release_env = read(".env.release.example")
    release_compose = read("compose.release.yml")
    base_config = read("deploy/k8s/base/configmap.yaml")
    plain_config = read("deploy/k8s/plain/backend/config.yaml")
    base_frontend = read("deploy/k8s/base/frontend-deployment.yaml")
    plain_frontend = read("deploy/k8s/plain/frontend/deployment.yaml")
    readme = read("deploy/k8s/README.md")
    env_manual = read("deploy/k8s/environment-variables.zh.md")

    assert "SKILLHUB_TRUST_FORWARDED_PROTO=false" in release_env
    assert "SKILLHUB_TRUST_FORWARDED_PROTO: ${SKILLHUB_TRUST_FORWARDED_PROTO:-false}" in release_compose
    assert 'trust-forwarded-proto: "false"' in base_config
    assert 'trust-forwarded-proto: "false"' in plain_config
    for frontend in (base_frontend, plain_frontend):
        assert "name: SKILLHUB_TRUST_FORWARDED_PROTO" in frontend
        assert "key: trust-forwarded-proto" in frontend
    assert "trust-forwarded-proto" in readme
    assert "SKILLHUB_TRUST_FORWARDED_PROTO" in env_manual


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
        assert "SKILLHUB_PUBLIC_BASE_URL" in frontend
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
        "`public-base-url` controls backend OAuth callbacks and the frontend public app URL."
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
        "`public-base-url` 控制 backend OAuth callback 與 frontend public app URL，"
        "但不會覆蓋 `cli-registry-url`。"
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


def test_subpath_runtime_contract_is_wired_across_release_and_kubernetes() -> None:
    release_env = read(".env.release.example")
    release_compose = read("compose.release.yml")
    base_config = read("deploy/k8s/base/configmap.yaml")
    plain_config = read("deploy/k8s/plain/backend/config.yaml")
    base_frontend = read("deploy/k8s/base/frontend-deployment.yaml")
    plain_frontend = read("deploy/k8s/plain/frontend/deployment.yaml")
    base_backend = read("deploy/k8s/base/backend-deployment.yaml")
    plain_backend = read("deploy/k8s/plain/backend/deployment.yaml")
    readme = read("deploy/k8s/README.md")
    env_manual = read("deploy/k8s/environment-variables.zh.md")
    server_service = release_compose.partition("\n  server:\n")[2].partition("\n  web:\n")[0]

    assert "SKILLHUB_WEB_BASE_PATH=" in release_env
    assert "SKILLHUB_DEVICE_AUTH_VERIFICATION_URI=" in release_env
    assert "SKILLHUB_WEB_BASE_PATH: ${SKILLHUB_WEB_BASE_PATH:-}" in release_compose
    assert "SKILLHUB_WEB_BASE_PATH: ${SKILLHUB_WEB_BASE_PATH:-}" in server_service
    assert "SKILLHUB_DEVICE_AUTH_VERIFICATION_URI: ${SKILLHUB_DEVICE_AUTH_VERIFICATION_URI:-}" in release_compose

    for config in (base_config, plain_config):
        assert 'web-base-path: ""' in config
        assert 'web-api-base-url: ""' in config
        assert 'device-auth-verification-uri: ""' in config

    for frontend in (base_frontend, plain_frontend):
        assert "name: SKILLHUB_PUBLIC_BASE_URL" in frontend
        assert "key: public-base-url" in frontend
        assert "name: SKILLHUB_WEB_BASE_PATH" in frontend
        assert "key: web-base-path" in frontend
        assert "name: SKILLHUB_WEB_API_BASE_URL" in frontend
        assert "key: web-api-base-url" in frontend

    for backend in (base_backend, plain_backend):
        assert "name: SKILLHUB_WEB_BASE_PATH" in backend
        assert "key: web-base-path" in backend
        assert "name: SKILLHUB_DEVICE_AUTH_VERIFICATION_URI" in backend
        assert "key: device-auth-verification-uri" in backend

    for document in (readme, env_manual):
        assert "https://ai-coding-platform.tsmc.com/skillhub" in document
        assert "https://ai-coding-platform.tsmc.com/skillhub/login/oauth2/code/keycloak" in document
        assert "https://ai-coding-platform.tsmc.com" in document
        assert "Web Origins" in document
        assert "VirtualService" in document
        assert "CNAME" in document
        assert "TLS SNI" in document
        assert "HTTP Host" in document
        assert "credentialName: ai-coding-platform-tls" in document
        assert "skillhub-test.ftest.tsmc.com" in document
        assert "patch fragment" in document


def test_subpath_e2e_builds_the_current_production_bundle_before_startup() -> None:
    package_json = read("web/package.json")
    global_setup = read("web/e2e/helpers/subpath-global-setup.mjs")

    assert (
        '"test:e2e:subpath": "playwright test -c playwright.subpath.config.ts"'
        in package_json
    )
    assert "node_modules/typescript/bin/tsc" in global_setup
    assert "node_modules/vite/bin/vite.js" in global_setup
    assert global_setup.index("await buildSubpathBundle()") < global_setup.index(
        "await import('./subpath-server.mjs')"
    )


def test_well_known_docs_cover_root_and_subpath_api_bases() -> None:
    documents = [
        read(".agents/skills/api-and-namespace-design/SKILL.md"),
        read("web/src/docs/skill.md.template"),
    ]

    for document in documents:
        assert '"apiBase":"/api/v1"' in document
        assert '"apiBase":"/skillhub/api/v1"' in document
        assert "SKILLHUB_WEB_BASE_PATH" in document


def test_subpath_runtime_does_not_depend_on_the_organization_hostname() -> None:
    runtime_sources = [
        "server-python/app/core/public_url.py",
        "server-python/app/core/config.py",
        "web/src/shared/lib/runtime-config.ts",
        "web/docker-entrypoint.d/30-runtime-config.sh",
        "web/runtime-config.js.template",
        "compose.release.yml",
        "deploy/k8s/base/configmap.yaml",
        "deploy/k8s/base/frontend-deployment.yaml",
        "deploy/k8s/base/backend-deployment.yaml",
    ]

    for source in runtime_sources:
        content = read(source)
        assert "ai-coding-platform.tsmc.com" not in content
        assert "skillhub-test.ftest.tsmc.com" not in content


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
