#!/usr/bin/env python3
"""Backport SKILL_SCANNER_LLM_BASE_URL support into cisco-ai-skill-scanner 1.0.2."""

from __future__ import annotations

import re
import sys
from pathlib import Path

EXPECTED_DIST_INFO = "cisco_ai_skill_scanner-1.0.2.dist-info"
ROUTER_RELATIVE_PATH = Path("skill_scanner/api/router.py")


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
    dist_info = site_packages / EXPECTED_DIST_INFO
    if not dist_info.exists():
        raise SystemExit(f"Expected {EXPECTED_DIST_INFO} under {site_packages}, but it was not found.")

    router_path = site_packages / ROUTER_RELATIVE_PATH
    content = router_path.read_text(encoding="utf-8")
    content = replace_regex(
        content,
        r'^(?P<indent>\s*)llm_model = os.getenv\("SKILL_SCANNER_LLM_MODEL"\)$',
        r'\g<0>\n\g<indent>llm_base_url = os.getenv("SKILL_SCANNER_LLM_BASE_URL")',
        2,
        "llm_model environment lookup",
    )
    content = replace_exact(
        content,
        "LLMAnalyzer(model=llm_model)",
        "LLMAnalyzer(model=llm_model, base_url=llm_base_url)",
        2,
        "LLMAnalyzer model constructor",
    )
    content = replace_exact(
        content,
        "LLMAnalyzer(provider=provider_str)",
        "LLMAnalyzer(provider=provider_str, base_url=llm_base_url)",
        2,
        "LLMAnalyzer provider constructor",
    )

    router_path.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
