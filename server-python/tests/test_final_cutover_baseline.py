from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DIR = ROOT / "docs" / "backend-python-migration"
FINAL_PLAN = MIGRATION_DIR / "plans" / "2026-06-12-final-python-cutover.md"
MILESTONE_114_RESULT = MIGRATION_DIR / "results" / "2026-06-12-final-cutover-baseline.md"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_route_registry_has_no_java_owned_rows() -> None:
    registry = read_text(MIGRATION_DIR / "route-registry.md")

    java_owned_rows = [line for line in registry.splitlines() if "| java |" in line]

    assert java_owned_rows == []


def test_vite_proxy_has_no_java_backend_target() -> None:
    vite_config = read_text(ROOT / "web" / "vite.config.ts")
    vite_config_test = read_text(ROOT / "web" / "vite.config.test.ts")

    assert "target: 'http://localhost:8080'" not in vite_config
    assert "toBe('http://localhost:8080')" not in vite_config_test


def test_final_cutover_deferred_categories_are_explicit() -> None:
    plan = read_text(ROOT / "docs" / "backend-python-migration" / "migration-sequence-plan.md")
    final_plan = read_text(FINAL_PLAN)

    categories = [
        "OAuth provider redirect/callback/session establishment",
        "Global bearer route-policy enforcement",
        "Active notification SSE fanout",
        "Post-publish lifecycle/governance semantic audit",
        "Python schema migration ownership",
    ]

    for category in categories:
        assert category in plan
        assert category in final_plan


def test_milestone_114_is_recorded_as_completed() -> None:
    final_plan = read_text(FINAL_PLAN)
    result = read_text(MILESTONE_114_RESULT)

    assert "| 114 | Deferred surface audit and cutover baseline | n/a |" in read_text(
        MIGRATION_DIR / "migration-sequence-plan.md"
    )
    assert "- [x] Add tests that assert route registry has no `| java |` owner rows." in final_plan
    assert "- [x] Add tests that assert Vite config has no Java `8080` proxy targets." in final_plan
    assert "- [x] Add tests that assert final deferred categories are explicitly listed as:" in final_plan
    assert "Result: `uv run pytest tests/test_final_cutover_baseline.py tests/test_route_registry.py -q` passed." in result
