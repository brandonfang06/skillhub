#!/usr/bin/env python3
"""Backport observable LLM failures into cisco-ai-skill-scanner 1.0.2."""

from __future__ import annotations

import re
import sys
from pathlib import Path

EXPECTED_DIST_INFO = "cisco_ai_skill_scanner-1.0.2.dist-info"
ANALYZER_RELATIVE_PATH = Path("skill_scanner/core/analyzers/llm_analyzer.py")
ROUTER_RELATIVE_PATH = Path("skill_scanner/api/router.py")
REQUEST_HANDLER_RELATIVE_PATH = Path("skill_scanner/core/analyzers/llm_request_handler.py")

TIMEOUT_TYPE_MARKERS = ("timeout", "timedout")
TIMEOUT_TEXT_MARKERS = ("timed out", "timeout")
UNAVAILABLE_TYPE_MARKERS = ("apiconnectionerror", "connectionerror", "serviceunavailable")
UNAVAILABLE_TEXT_MARKERS = (
    "connection error",
    "connection refused",
    "connection reset",
    "name or service not known",
    "no healthy upstream",
    "service temporarily unavailable",
    "service unavailable",
    "temporary failure in name resolution",
)

CLASSIFIER_SOURCE = '''def _skillhub_classify_llm_failure(error: Exception) -> str:
    error_type = type(error).__name__.lower()
    error_text = str(error).lower()
    if any(marker in error_type for marker in ("timeout", "timedout")) or any(
        marker in error_text for marker in ("timed out", "timeout")
    ):
        return "LLM_TIMEOUT"
    if any(
        marker in error_type for marker in ("apiconnectionerror", "connectionerror", "serviceunavailable")
    ) or any(
        marker in error_text
        for marker in (
            "connection error",
            "connection refused",
            "connection reset",
            "name or service not known",
            "no healthy upstream",
            "service temporarily unavailable",
            "service unavailable",
            "temporary failure in name resolution",
        )
    ):
        return "LLM_UNAVAILABLE"
    return "LLM_ERROR"


'''

OLD_FAILURE_HANDLER = '''        except Exception as e:
            print(f"LLM analysis failed for {skill.name}: {e}")
            # Return empty findings - don't pollute results with errors
            return []
'''

NEW_FAILURE_HANDLER = '''        except Exception as e:
            failure_code = _skillhub_classify_llm_failure(e)
            raise RuntimeError(f"SKILLHUB_LLM_ANALYSIS_FAILED:{failure_code}") from None
'''

OLD_RATE_LIMIT_LOG = '''                        print(
                            f"Rate limit hit for {context}, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
                        )
'''

NEW_RATE_LIMIT_LOG = '''                        print(
                            f"LLM API rate limited; retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
                        )
'''


def classify_llm_failure(error_type: str, error_text: str) -> str:
    normalized_type = error_type.lower()
    normalized_text = error_text.lower()
    if any(marker in normalized_type for marker in TIMEOUT_TYPE_MARKERS) or any(
        marker in normalized_text for marker in TIMEOUT_TEXT_MARKERS
    ):
        return "LLM_TIMEOUT"
    if any(marker in normalized_type for marker in UNAVAILABLE_TYPE_MARKERS) or any(
        marker in normalized_text for marker in UNAVAILABLE_TEXT_MARKERS
    ):
        return "LLM_UNAVAILABLE"
    return "LLM_ERROR"


def replace_exact(content: str, old: str, new: str, expected_count: int, label: str) -> str:
    actual_count = content.count(old)
    if actual_count != expected_count:
        raise SystemExit(f"Expected {expected_count} occurrences of {label}, found {actual_count}.")
    return content.replace(old, new, expected_count)


def replace_regex(content: str, pattern: str, replacement: str, expected_count: int, label: str) -> str:
    updated, actual_count = re.subn(pattern, replacement, content, count=expected_count, flags=re.MULTILINE)
    if actual_count != expected_count:
        raise SystemExit(f"Expected {expected_count} regex replacements for {label}, found {actual_count}.")
    return updated


def main() -> int:
    site_packages = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/usr/local/lib/python3.11/site-packages")
    if not (site_packages / EXPECTED_DIST_INFO).exists():
        raise SystemExit(f"Expected {EXPECTED_DIST_INFO} under {site_packages}, but it was not found.")

    analyzer_path = site_packages / ANALYZER_RELATIVE_PATH
    analyzer_content = analyzer_path.read_text(encoding="utf-8")
    analyzer_content = replace_exact(
        analyzer_content,
        OLD_FAILURE_HANDLER,
        NEW_FAILURE_HANDLER,
        1,
        "LLM failure handler",
    )
    analyzer_content = replace_exact(
        analyzer_content,
        "class LLMAnalyzer(BaseAnalyzer):",
        f"{CLASSIFIER_SOURCE}class LLMAnalyzer(BaseAnalyzer):",
        1,
        "LLM analyzer class",
    )
    analyzer_content = replace_exact(
        analyzer_content,
        'messages, context=f"threat analysis for {skill.name}"',
        'messages, context="threat analysis"',
        1,
        "LLM request context",
    )
    analyzer_path.write_text(analyzer_content, encoding="utf-8")

    request_handler_path = site_packages / REQUEST_HANDLER_RELATIVE_PATH
    request_handler_content = request_handler_path.read_text(encoding="utf-8")
    request_handler_content = replace_exact(
        request_handler_content,
        OLD_RATE_LIMIT_LOG,
        NEW_RATE_LIMIT_LOG,
        1,
        "LLM rate-limit log",
    )
    request_handler_content = replace_exact(
        request_handler_content,
        '                print(f"LLM API error for {context}: {e}")',
        '                print("LLM API request failed")',
        1,
        "LLM API error log",
    )
    request_handler_content = replace_exact(
        request_handler_content,
        '                print(f"LLM analysis failed: {e}")',
        '                print("LLM API request failed")',
        1,
        "Google LLM error log",
    )
    request_handler_path.write_text(request_handler_content, encoding="utf-8")

    router_path = site_packages / ROUTER_RELATIVE_PATH
    router_content = router_path.read_text(encoding="utf-8")
    router_content = replace_exact(
        router_content,
        "    findings: list[dict]\n",
        "    findings: list[dict]\n    analyzers_used: list[str]\n",
        1,
        "ScanResponse findings field",
    )
    router_content = replace_regex(
        router_content,
        r"^(?P<indent>\s*)findings=\[f\.to_dict\(\) for f in result\.findings\],$",
        r"\g<0>\n\g<indent>analyzers_used=result.analyzers_used,",
        1,
        "ScanResponse findings value",
    )
    router_path.write_text(router_content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
