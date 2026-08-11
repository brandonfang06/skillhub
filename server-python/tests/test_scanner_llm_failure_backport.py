from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKPORT_PATH = ROOT / "scanner" / "backports" / "apply_1_0_2_llm_failure_backport.py"

LLM_ANALYZER_SOURCE = '''class LLMAnalyzer(BaseAnalyzer):
    async def analyze_async(self, skill):
        try:
            findings = await self.request_handler.request(
                messages, context=f"threat analysis for {skill.name}"
            )
        except Exception as e:
            print(f"LLM analysis failed for {skill.name}: {e}")
            # Return empty findings - don't pollute results with errors
            return []

        return findings
'''

LLM_REQUEST_HANDLER_SOURCE = '''class LLMRequestHandler:
    async def request(self, context, attempt, delay):
        for attempt in range(self.max_retries + 1):
            try:
                return "ok"
            except Exception as e:
                if True:
                    if attempt < self.max_retries:
                        print(
                            f"Rate limit hit for {context}, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
                        )
                print(f"LLM API error for {context}: {e}")
                raise

    async def google_request(self):
        for attempt in range(self.max_retries + 1):
            try:
                return "ok"
            except Exception as e:
                print(f"LLM analysis failed: {e}")
                raise
'''

ROUTER_SOURCE = '''class ScanResponse(BaseModel):
    """Response model for scan results."""

    scan_id: str
    findings: list[dict]


def response(result):
    return ScanResponse(
        scan_id="scan-id",
        findings=[f.to_dict() for f in result.findings],
    )
'''


def load_backport() -> ModuleType:
    assert BACKPORT_PATH.exists(), "LLM failure backport must exist"
    spec = importlib.util.spec_from_file_location("scanner_llm_failure_backport", BACKPORT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("error_type", "error_text", "expected"),
    [
        ("Timeout", "request timed out", "LLM_TIMEOUT"),
        ("ReadTimeout", "", "LLM_TIMEOUT"),
        ("APIConnectionError", "connection refused", "LLM_UNAVAILABLE"),
        ("InternalServerError", "OpenAIException - Connection error.", "LLM_UNAVAILABLE"),
        ("RuntimeError", "service temporarily unavailable", "LLM_UNAVAILABLE"),
        ("AuthenticationError", "invalid api key", "LLM_ERROR"),
    ],
)
def test_classifies_only_normalized_llm_failures(error_type: str, error_text: str, expected: str) -> None:
    module = load_backport()

    assert module.classify_llm_failure(error_type, error_text) == expected


def test_backport_propagates_sanitized_failure_and_exposes_analyzers(tmp_path: Path) -> None:
    site_packages = tmp_path / "site-packages"
    (site_packages / "cisco_ai_skill_scanner-1.0.2.dist-info").mkdir(parents=True)
    analyzer_path = site_packages / "skill_scanner" / "core" / "analyzers" / "llm_analyzer.py"
    request_handler_path = site_packages / "skill_scanner" / "core" / "analyzers" / "llm_request_handler.py"
    router_path = site_packages / "skill_scanner" / "api" / "router.py"
    analyzer_path.parent.mkdir(parents=True)
    router_path.parent.mkdir(parents=True)
    analyzer_path.write_text(LLM_ANALYZER_SOURCE, encoding="utf-8")
    request_handler_path.write_text(LLM_REQUEST_HANDLER_SOURCE, encoding="utf-8")
    router_path.write_text(ROUTER_SOURCE, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(BACKPORT_PATH), str(site_packages)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    patched_analyzer = analyzer_path.read_text(encoding="utf-8")
    patched_request_handler = request_handler_path.read_text(encoding="utf-8")
    patched_router = router_path.read_text(encoding="utf-8")
    assert "SKILLHUB_LLM_ANALYSIS_FAILED:{failure_code}" in patched_analyzer
    assert "return []" not in patched_analyzer
    assert "skill.name" not in patched_analyzer
    assert "from e" not in patched_analyzer
    assert "from None" in patched_analyzer
    assert "LLM API error" not in patched_request_handler
    assert "LLM analysis failed:" not in patched_request_handler
    assert "Rate limit hit for {context}" not in patched_request_handler
    assert "analyzers_used: list[str]" in patched_router
    assert "analyzers_used=result.analyzers_used" in patched_router
    compile(patched_analyzer, str(analyzer_path), "exec")
    compile(patched_request_handler, str(request_handler_path), "exec")
    compile(patched_router, str(router_path), "exec")


def test_backport_fails_closed_when_upstream_source_changes(tmp_path: Path) -> None:
    site_packages = tmp_path / "site-packages"
    (site_packages / "cisco_ai_skill_scanner-1.0.2.dist-info").mkdir(parents=True)
    analyzer_path = site_packages / "skill_scanner" / "core" / "analyzers" / "llm_analyzer.py"
    router_path = site_packages / "skill_scanner" / "api" / "router.py"
    analyzer_path.parent.mkdir(parents=True)
    router_path.parent.mkdir(parents=True)
    analyzer_path.write_text("# upstream changed\n", encoding="utf-8")
    router_path.write_text(ROUTER_SOURCE, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(BACKPORT_PATH), str(site_packages)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "LLM failure handler" in result.stderr
