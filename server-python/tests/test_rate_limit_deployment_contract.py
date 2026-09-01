from pathlib import Path

import yaml

from app.core.config import RATE_LIMIT_CATEGORIES

REPO_ROOT = Path(__file__).resolve().parents[2]
RATE_LIMIT_CONFIG_MAP = "skillhub-rate-limit-config"


def _rate_limit_environment_names() -> list[str]:
    names = ["SKILLHUB_RATELIMIT_ENABLED"]
    for category in RATE_LIMIT_CATEGORIES:
        prefix = f"SKILLHUB_RATELIMIT_CATEGORIES_{category.replace('-', '_').upper()}_"
        names.extend(
            (
                f"{prefix}AUTHENTICATED",
                f"{prefix}ANONYMOUS",
                f"{prefix}WINDOW_SECONDS",
            )
        )
    return names


def _yaml_documents(relative_path: str) -> list[dict[str, object]]:
    path = REPO_ROOT / relative_path
    return [
        document
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if isinstance(document, dict)
    ]


def _named_document(relative_path: str, kind: str, name: str) -> dict[str, object]:
    for document in _yaml_documents(relative_path):
        metadata = document.get("metadata")
        if (
            document.get("kind") == kind
            and isinstance(metadata, dict)
            and metadata.get("name") == name
        ):
            return document
    raise AssertionError(f"missing {kind} {name} in {relative_path}")


def test_release_compose_forwards_every_supported_rate_limit_setting() -> None:
    example_env = (REPO_ROOT / ".env.release.example").read_text(encoding="utf-8")
    compose = (REPO_ROOT / "compose.release.yml").read_text(encoding="utf-8")

    for name in _rate_limit_environment_names()[1:]:
        assert f"{name}=" in example_env
        assert f"{name}: ${{{name}:-}}" in compose

    assert "SKILLHUB_RATELIMIT_ENABLED=false" in example_env
    assert (
        "SKILLHUB_RATELIMIT_ENABLED: ${SKILLHUB_RATELIMIT_ENABLED:-false}"
        in compose
    )


def test_kubernetes_manifests_expose_the_complete_disabled_by_default_contract() -> None:
    expected_names = set(_rate_limit_environment_names())
    config_paths = (
        "deploy/k8s/base/configmap.yaml",
        "deploy/k8s/plain/backend/config.yaml",
    )
    deployment_paths = (
        "deploy/k8s/base/backend-deployment.yaml",
        "deploy/k8s/plain/backend/deployment.yaml",
    )

    for path in config_paths:
        config_map = _named_document(path, "ConfigMap", RATE_LIMIT_CONFIG_MAP)
        data = config_map.get("data")
        assert isinstance(data, dict)
        assert set(data) == expected_names
        assert data["SKILLHUB_RATELIMIT_ENABLED"] == "false"
        assert all(
            value == ""
            for name, value in data.items()
            if name != "SKILLHUB_RATELIMIT_ENABLED"
        )

    for path in deployment_paths:
        deployment = _named_document(path, "Deployment", "skillhub-server")
        pod_spec = deployment["spec"]["template"]["spec"]
        container = next(
            item for item in pod_spec["containers"] if item["name"] == "backend-python"
        )
        assert {entry["configMapRef"]["name"] for entry in container["envFrom"]} == {
            RATE_LIMIT_CONFIG_MAP
        }
