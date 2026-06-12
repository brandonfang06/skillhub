import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("app", "tests")


@dataclass(frozen=True)
class SqlUsage:
    path: Path
    category: str
    text_calls: int


def categorize_path(path: Path) -> str:
    normalized = path.as_posix()
    name = path.name

    if normalized.startswith("tests/"):
        return "test"
    if normalized in {"app/bootstrap.py", "app/migrations.py"} or normalized.startswith("alembic/"):
        return "migration-bootstrap"
    if normalized.startswith("app/api/"):
        return "api-route"
    if name.endswith("_repository.py") or name.endswith("_query.py") or "/repository/" in normalized:
        return "repository-query"
    return "service-domain"


def _python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for scan_root in SCAN_ROOTS:
        base = root / scan_root
        if base.exists():
            files.extend(path for path in base.rglob("*.py") if ".venv" not in path.parts)
    return sorted(files)


def _text_call_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "text":
            count += 1
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "text":
            count += 1
    return count


def collect_inventory(root: Path = SERVER_ROOT) -> list[SqlUsage]:
    usages: list[SqlUsage] = []
    for path in _python_files(root):
        count = _text_call_count(path)
        if count:
            relative_path = path.relative_to(root)
            usages.append(SqlUsage(relative_path, categorize_path(relative_path), count))
    return usages


def format_inventory(usages: list[SqlUsage]) -> str:
    if not usages:
        return "No sqlalchemy.text usage found."

    lines = ["category,text_calls,path"]
    for usage in sorted(usages, key=lambda item: (-item.text_calls, item.category, item.path.as_posix())):
        lines.append(f"{usage.category},{usage.text_calls},{usage.path.as_posix()}")

    by_category = Counter()
    for usage in usages:
        by_category[usage.category] += usage.text_calls

    lines.append("")
    lines.append("summary")
    for category, count in sorted(by_category.items()):
        lines.append(f"{category},{count}")
    return "\n".join(lines)


def main() -> None:
    print(format_inventory(collect_inventory()))


if __name__ == "__main__":
    main()
