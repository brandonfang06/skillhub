from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_scanner_image_pins_upstream_runtime_dependencies() -> None:
    dockerfile = (ROOT / "scanner" / "Dockerfile").read_text(encoding="utf-8")

    assert '"cisco-ai-skill-scanner==${SKILL_SCANNER_VERSION}"' in dockerfile
    assert '"litellm==1.90.2"' in dockerfile
    assert "apply_1_0_2_llm_base_url_backport.py" in dockerfile
    assert "apply_1_0_2_llm_failure_backport.py" in dockerfile
