from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cli_staging_smoke_script_exercises_real_cli_against_python_backend() -> None:
    script = read("scripts/cli-staging-smoke-test.sh")
    makefile = read("Makefile")

    assert "bun src/index.ts" in script
    assert '"CLI dry-run publish validates the local package through Python backend"' in script
    assert '"CLI publish uploads the package through Python backend"' in script
    assert '"CLI search discovers the approved package through Python backend"' in script
    assert '"CLI install resolves and downloads the approved package through Python backend"' in script
    assert "/api/v1/tokens" in script
    assert "/api/web/reviews/$REVIEW_ID/approve" in script
    assert "cli-staging-smoke:" in makefile
    assert "scripts/cli-staging-smoke-test.sh $(STAGING_API_URL)" in makefile
