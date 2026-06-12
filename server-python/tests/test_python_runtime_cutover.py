from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def make_target(makefile: str, target: str) -> str:
    start = makefile.index(f"{target}:")
    next_target = makefile.find("\n", start + 1)
    while next_target != -1:
        candidate = makefile.find("\n", next_target + 1)
        line = makefile[next_target + 1 : candidate if candidate != -1 else len(makefile)]
        if line and not line.startswith(("\t", " ", "@")) and ":" in line:
            return makefile[start:next_target]
        next_target = candidate
    return makefile[start:]


def test_default_make_targets_start_python_without_java_backend() -> None:
    makefile = read("Makefile")
    dev_all = make_target(makefile, "dev-all")

    assert "$(DEV_PROCESS) start --pid-file $(DEV_PYTHON_PID)" in dev_all
    assert "--cwd server-python" in dev_all
    assert "command -v pnpm" in dev_all
    assert "$(DEV_WEB_URL)/api/v1/health" in dev_all
    assert "$(DEV_PROCESS) start --pid-file $(DEV_SERVER_PID)" not in dev_all
    assert "--cwd server --" not in dev_all
    assert "$(DEV_API_URL)/actuator/health" not in dev_all


def test_staging_builds_and_runs_python_backend_image() -> None:
    makefile = read("Makefile")
    staging_compose = read("docker-compose.staging.yml")

    assert "STAGING_SERVER_IMAGE := skillhub-server-python:staging" in makefile
    assert "docker build -t $(STAGING_SERVER_IMAGE) -f server-python/Dockerfile ." in makefile
    assert "if command -v pnpm" in makefile
    assert "cd server && ./mvnw package" not in makefile
    assert "server/Dockerfile.dev" not in makefile
    assert "image: skillhub-server-python:staging" in staging_compose
    assert "SKILLHUB_DATABASE_URL: postgresql+asyncpg://skillhub:skillhub_dev@postgres:5432/skillhub" in staging_compose
    assert "http://localhost:8080/api/v1/health" in staging_compose
    assert "http://localhost:8080/actuator/health" not in staging_compose


def test_python_backend_container_has_schema_migration_startup() -> None:
    dockerfile = read("server-python/Dockerfile")

    assert "uv sync --frozen --no-dev" in dockerfile
    assert "COPY server/skillhub-app/src/main/resources/db/migration" in dockerfile
    assert "python -m app.migrations upgrade" in dockerfile
    assert "uvicorn app.main:app --host 0.0.0.0 --port 8080" in dockerfile


def test_staging_smoke_test_targets_python_health_endpoints() -> None:
    smoke_test = read("scripts/smoke-test.sh")

    assert "$BASE_URL/api/v1/health" in smoke_test
    assert "$BASE_URL/api/v1/metrics/prometheus" in smoke_test
    assert "PASS: Namespaces API with session" in smoke_test
    assert "$BASE_URL/actuator/health" not in smoke_test
    assert "$BASE_URL/actuator/prometheus" not in smoke_test


def test_final_cutover_result_is_recorded() -> None:
    final_plan = read("docs/backend-python-migration/plans/2026-06-12-final-python-cutover.md")
    sequence = read("docs/backend-python-migration/migration-sequence-plan.md")
    result = read("docs/backend-python-migration/results/2026-06-12-java-runtime-deprecation.md")

    assert "| 120 | Java runtime deprecation and staging cutover | python |" in sequence
    assert "- [x] Java runtime deprecation from default local/staging paths is complete." in final_plan
    assert "make dev-all" in result
    assert "make staging" in result
