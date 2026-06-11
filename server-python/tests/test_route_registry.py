from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_route_registry() -> str:
    return (ROOT / "docs" / "backend-python-migration" / "route-registry.md").read_text(encoding="utf-8")


def read_migration_sequence_plan() -> str:
    return (ROOT / "docs" / "backend-python-migration" / "migration-sequence-plan.md").read_text(encoding="utf-8")


def test_route_registry_lists_clawhub_placeholders_and_remaining_java_fallbacks() -> None:
    registry = read_route_registry()

    assert (
        "| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}/file` | python | Frontend alias for single version file content bytes."
        in registry
    )
    assert (
        "| GET | `/api/web/skills/{namespace}/{slug}/tags/{tagName}/file` | python | Frontend alias for single tag file content bytes."
        in registry
    )
    assert (
        "| POST | `/api/v1/admin/search/rebuild` | python | Admin search-index rebuild moved to Python. Requires `SUPER_ADMIN`, rejects bearer API-token principals as Java-compatible unsupported admin-route access"
        in registry
    )
    assert (
        "| GET | `/api/v1/admin/labels` | python | Admin label definition list moved to Python. Requires `SUPER_ADMIN`, rejects bearer API-token principals as Java-compatible unsupported admin-route access"
        in registry
    )
    assert (
        "| GET | `/api/v1/admin/users` | python | Admin user list moved to Python. Requires `USER_ADMIN` or `SUPER_ADMIN`, rejects bearer API-token principals as Java-compatible unsupported admin-route access"
        in registry
    )
    assert (
        "| POST | `/api/v1/admin/skills/{skillId}/hide` | python | Platform-admin skill hide moved to Python. `SUPER_ADMIN` only; rejects bearer API-token principals as Java-compatible unsupported admin-route access"
        in registry
    )
    assert (
        "| GET | `/api/v1/admin/skill-reports` | python | Admin skill report list moved to Python. Requires `SKILL_ADMIN` or `SUPER_ADMIN`, rejects bearer API-token principals as Java-compatible unsupported admin-route access"
        in registry
    )
    assert (
        "| DELETE | `/api/v1/skills/{canonicalSlug}` | python | ClawHub placeholder delete moved to Python"
        in registry
    )
    assert (
        "| POST | `/api/v1/skills/{canonicalSlug}/undelete` | python | ClawHub placeholder undelete moved to Python"
        in registry
    )
    assert (
        "| * | `/api/**` unmatched paths | java | Default owner for unregistered or intentionally unmigrated API paths"
        in registry
    )
    assert "| * | `/oauth2/**` | java | OAuth remains Java-owned." in registry


def test_migration_sequence_records_clawhub_placeholder_and_java_fallback_milestones() -> None:
    plan = read_migration_sequence_plan()

    assert "| 104 | Explicit Java proxy exceptions | n/a |" in plan
    assert "ClawHub delete/undelete and unmatched `/api/**` paths are explicitly documented as Java-owned" in plan
    assert "| 105 | `DELETE /api/v1/skills/{canonicalSlug}`, `POST /api/v1/skills/{canonicalSlug}/undelete` | python |" in plan
    assert "| 106 | `GET /api/web/skills/{namespace}/{slug}/versions/{version}/file`, `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/file` | python |" in plan
    assert "| 107 | `POST /api/v1/admin/search/rebuild` | python |" in plan
    assert "| 108 | Admin search rebuild bearer route-policy enforcement | python |" in plan
    assert "| 109 | Admin label definition bearer route-policy enforcement | python |" in plan
    assert "| 110 | Admin route bearer policy cutover | python |" in plan
    assert (
        "Already Python-owned `/api/v1/admin/**` route groups now share Java-compatible bearer API-token unsupported handling"
        in plan
    )
