from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DOCS = ROOT / "docs" / "backend-python-migration"


def test_java_parity_checklist_exists_and_covers_risk_areas() -> None:
    checklist = (MIGRATION_DOCS / "java-parity-checklist.md").read_text(encoding="utf-8")

    assert "Java Reference Sources" in checklist
    assert "API Contract Parity" in checklist
    assert "Authorization And Session Parity" in checklist
    assert "Database Transaction Atomicity" in checklist
    assert "Audit Actor And Timestamp Fields" in checklist
    assert "Storage And Side Effects" in checklist
    assert "Live Verification Evidence" in checklist
    assert "Deferral Rules" in checklist
    assert "controller" in checklist
    assert "service" in checklist
    assert "updated_by" in checklist
    assert "created_by" in checklist


def test_python_agent_entrypoint_links_java_parity_checklist() -> None:
    agent_doc = (ROOT / "server-python" / "AGENTS.md").read_text(encoding="utf-8")

    assert "docs/backend-python-migration/java-parity-checklist.md" in agent_doc
    assert "Java parity checklist" in agent_doc
    assert "transaction boundary" in agent_doc
    assert "audit actor" in agent_doc


def test_migration_sequence_requires_parity_sections_in_plans_and_results() -> None:
    sequence = (MIGRATION_DOCS / "migration-sequence-plan.md").read_text(encoding="utf-8")

    assert "Java Parity Checklist Gate" in sequence
    assert "Every milestone plan must include a Java parity checklist section" in sequence
    assert "Every result document must record the checklist outcome" in sequence
    assert "Do not move route ownership when parity gaps are unresolved" in sequence
