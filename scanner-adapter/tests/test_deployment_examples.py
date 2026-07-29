from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
DEPLOY = ROOT / "deploy"
K8S = DEPLOY / "k8s"

SCANNER_ENV_NAMES = {
    "SKILL_SCANNER_LLM_API_KEY",
    "SKILL_SCANNER_LLM_BASE_URL",
    "SKILL_SCANNER_LLM_MODEL",
    "AI_DEFENSE_API_KEY",
    "AI_DEFENSE_API_URL",
    "VIRUSTOTAL_API_KEY",
}

SECRET_ENV_NAMES = {
    "SKILL_SCANNER_LLM_API_KEY",
    "AI_DEFENSE_API_KEY",
    "VIRUSTOTAL_API_KEY",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_compose_deploys_only_scanner_on_loopback() -> None:
    compose = read(DEPLOY / "docker-compose.yml")

    assert compose.count("\n  skill-scanner:\n") == 1
    assert "${SCANNER_BIND_ADDRESS:-127.0.0.1}:${SCANNER_PORT:-8000}:8000" in compose
    assert "http://127.0.0.1:8000/health" in compose
    assert "server:" not in compose
    assert "postgres:" not in compose
    assert "redis:" not in compose


def test_compose_and_env_example_cover_scanner_environment() -> None:
    compose = read(DEPLOY / "docker-compose.yml")
    example = read(DEPLOY / ".env.example")

    for name in SCANNER_ENV_NAMES:
        assert name in compose
        assert name in example


def test_kustomization_excludes_secret_example() -> None:
    kustomization = read(K8S / "kustomization.yaml")

    for resource in (
        "namespace.yaml",
        "configmap.yaml",
        "deployment.yaml",
        "service.yaml",
    ):
        assert f"- {resource}" in kustomization
    assert "secret.example.yaml" not in kustomization


def test_kubernetes_service_is_internal_only() -> None:
    service = read(K8S / "service.yaml")

    assert "type: ClusterIP" in service
    assert "port: 8000" in service
    assert "NodePort" not in service
    assert "LoadBalancer" not in service
    assert "Ingress" not in service


def test_kubernetes_separates_config_and_secrets() -> None:
    configmap = read(K8S / "configmap.yaml")
    secret = read(K8S / "secret.example.yaml")
    deployment = read(K8S / "deployment.yaml")

    for name in SECRET_ENV_NAMES:
        assert name not in configmap
        assert f'{name}: ""' in secret
    for name in SCANNER_ENV_NAMES - SECRET_ENV_NAMES:
        assert f'{name}: ""' in configmap
    assert "optional: true" in deployment
    assert "path: /health" in deployment
    assert "runAsNonRoot: true" in deployment
    assert "runAsUser: 100" in deployment
    assert "runAsGroup: 101" in deployment
    assert "fsGroup: 101" in deployment
