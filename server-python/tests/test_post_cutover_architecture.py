from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVER_ROOT.parent

API_SQL_BRIDGE_ALLOWLIST = {
    "app/api/device_auth.py": "temporary device-flow bridge SQL retained until auth repositories are extracted",
    "app/api/labels.py": "temporary label route bridge SQL retained until label repositories are extracted",
}

POST_CUTOVER_SQL_FACADE_MODULES = {
    "app/admin/audit_logs.py",
    "app/admin/users.py",
    "app/admin/review_reports.py",
    "app/governance/workbench.py",
    "app/reports/skill_reports.py",
}


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if ".venv" not in path.parts)


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _uses_sqlalchemy_text(path: Path) -> bool:
    tree = _tree(path)
    return any(
        isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "text")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "text")
        )
        for node in ast.walk(tree)
    )


def test_route_level_sql_bridge_usage_is_allowlisted() -> None:
    api_root = SERVER_ROOT / "app" / "api"

    actual = {
        path.relative_to(SERVER_ROOT).as_posix()
        for path in _python_files(api_root)
        if _uses_sqlalchemy_text(path)
    }

    assert actual == set(API_SQL_BRIDGE_ALLOWLIST)
    assert all(reason.strip() for reason in API_SQL_BRIDGE_ALLOWLIST.values())


def test_post_cutover_facade_modules_do_not_own_sql() -> None:
    offenders = [
        path
        for path in sorted(POST_CUTOVER_SQL_FACADE_MODULES)
        if _uses_sqlalchemy_text(SERVER_ROOT / path)
    ]

    assert offenders == []


def test_sqlalchemy_declarative_orm_models_stay_in_db_models_module() -> None:
    forbidden_names = {"DeclarativeBase", "declarative_base", "mapped_column", "relationship", "Mapped"}
    allowed_path = "app/db/models.py"
    offenders: list[str] = []

    for path in _python_files(SERVER_ROOT / "app"):
        relative_path = path.relative_to(SERVER_ROOT).as_posix()
        if relative_path == allowed_path:
            continue

        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                offenders.append(f"{relative_path}:{node.lineno}:{node.id}")
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "Base":
                        offenders.append(f"{relative_path}:{node.lineno}:Base")

    assert offenders == []

    models = SERVER_ROOT / allowed_path
    tree = _tree(models)
    mapped_tables = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "Base" for base in node.bases)
    ]

    assert mapped_tables == [
        "UserAccount",
        "Namespace",
        "NamespaceMember",
        "Skill",
        "SkillVersion",
        "ReviewTask",
        "PromotionRequest",
        "ApiToken",
        "AuditLog",
    ]


def test_sql_inventory_script_exposes_categories() -> None:
    script_path = SERVER_ROOT / "scripts" / "sql_inventory.py"
    spec = importlib.util.spec_from_file_location("sql_inventory", script_path)

    assert spec is not None and spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.categorize_path(Path("app/api/skills.py")) == "api-route"
    assert module.categorize_path(Path("app/skills/read_repository.py")) == "repository-query"
    assert (
        module.categorize_path(Path("app/repository_imports/repository.py"))
        == "repository-query"
    )
    assert module.categorize_path(Path("app/bootstrap.py")) == "migration-bootstrap"
    assert module.categorize_path(Path("tests/test_skill_detail.py")) == "test"


def test_post_cutover_maintenance_docs_exist() -> None:
    readme = REPO_ROOT / "docs" / "backend-python-maintenance" / "README.md"
    result = REPO_ROOT / "docs" / "backend-python-maintenance" / "results" / "2026-06-12-architecture-inventory.md"

    assert "post-cutover" in readme.read_text(encoding="utf-8").lower()
    assert "sql inventory" in result.read_text(encoding="utf-8").lower()


def test_agents_mentions_post_cutover_sql_rules() -> None:
    agents = (SERVER_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Post-Cutover Maintenance Rules" in agents
    assert "New SQL must live in repository/query/helper modules" in agents
    assert "ORM models require a milestone plan" in agents
