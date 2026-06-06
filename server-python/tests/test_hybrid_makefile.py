from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_makefile() -> str:
    return (ROOT / "Makefile").read_text(encoding="utf-8")


def read_hybrid_doc() -> str:
    return (ROOT / "docs" / "backend-python-migration" / "hybrid-local-e2e.md").read_text(encoding="utf-8")


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

    assert "[ValidateSet('up', 'down', 'status', 'e2e-smoke', 'e2e')]" in script
    assert "Start-ManagedProcess" in script
    assert "server-python" in script
    assert "uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload" in script
    assert "node_modules\\.bin\\vite.CMD" in script
    assert "playwright.smoke.config.ts" in script
    assert "playwright.config.ts" in script
    assert '$WebUrl/api/v1/health' in script
    assert "Docker CLI not available" in script


def test_hybrid_local_e2e_doc_covers_windows_macos_and_ubuntu() -> None:
    doc = read_hybrid_doc()

    assert "## Windows" in doc
    assert "## macOS" in doc
    assert "## Ubuntu" in doc
    assert "Docker Desktop" in doc
    assert "Colima" in doc
    assert "Docker Engine" in doc
    assert "Git for Windows" in doc
    assert "brew install make" in doc
    assert "sudo apt-get install" in doc
    assert "powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\\dev-hybrid.ps1 up" in doc
    assert "make dev-all-hybrid" in doc
    assert "make test-e2e-smoke-hybrid" in doc
