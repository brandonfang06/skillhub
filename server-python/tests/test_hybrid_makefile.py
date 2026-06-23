from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_makefile_defines_python_backend_process_only() -> None:
    makefile = read("Makefile")

    assert "DEV_PYTHON_PID := $(DEV_DIR)/python.pid" in makefile
    assert "DEV_PYTHON_LOG := $(DEV_DIR)/python.log" in makefile
    assert "DEV_PYTHON_URL := http://localhost:8080" in makefile
    assert "DEV_PYTHON_CMD := uv run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload" in makefile
    assert "8081" not in "\n".join(
        line for line in makefile.splitlines() if "DEV_PYTHON" in line or "DEV_API_URL" in line
    )
    assert "DEV_SERVER_PID" not in makefile
    assert "DEV_SERVER_LOG" not in makefile
    assert "BACKEND_TEST_JAVA_OPTIONS" not in makefile


def test_makefile_backend_targets_use_python_backend() -> None:
    makefile = read("Makefile")

    assert "build-backend" in makefile
    assert "cd server-python && uv sync --frozen && uv run python -m compileall app" in makefile
    assert "cd server-python && uv run pytest tests -q" in makefile
    assert "test-backend-app" in makefile
    assert "build-backend-app" in makefile
    assert "cd server &&" not in makefile
    assert "./mvnw" not in makefile
    assert "dev-all-hybrid" not in makefile
    assert "test-e2e-smoke-hybrid" not in makefile
    assert "test-e2e-hybrid" not in makefile


def test_python_ci_workflows_do_not_reference_java_server_runtime() -> None:
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    )

    assert "./server-python/Dockerfile" in workflow_text
    assert "skillhub-server-python" in workflow_text
    assert "server/mvnw" not in workflow_text
    assert "./server/Dockerfile" not in workflow_text
    assert "actions/setup-java" not in workflow_text
    assert "cache: maven" not in workflow_text


def test_python_runtime_no_longer_depends_on_java_migration_directory() -> None:
    dockerfile = read("server-python/Dockerfile")
    migrations = read("server-python/app/migrations.py")

    assert "COPY server-python/app ./app" in dockerfile
    assert "COPY server/skillhub-app" not in dockerfile
    assert 'ROOT / "server-python" / "app" / "db" / "migration"' in migrations
    assert 'ROOT / "server" / "skillhub-app"' not in migrations
