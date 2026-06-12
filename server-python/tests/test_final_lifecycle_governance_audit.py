from __future__ import annotations

import re
from pathlib import Path

from app.main import create_app


ROOT = Path(__file__).resolve().parents[2]


def _route_shape(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{param}", path)


def _route_registry_rows() -> dict[tuple[str, str], str]:
    registry = (ROOT / "docs" / "backend-python-migration" / "route-registry.md").read_text(encoding="utf-8")
    rows: dict[tuple[str, str], str] = {}
    for line in registry.splitlines():
        match = re.match(r"^\| ([A-Z*]+) \| `([^`]+)` \| ([^| ]+) \|", line)
        if match:
            method, path, owner = match.groups()
            rows[(method, _route_shape(path))] = owner
    return rows


def _app_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in create_app().routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path is None or methods is None:
            continue
        for method in methods:
            if method not in {"HEAD", "OPTIONS"}:
                routes.add((method, _route_shape(path)))
    return routes


LIFECYCLE_GOVERNANCE_ROUTES = {
    ("POST", "/api/v1/reviews"),
    ("POST", "/api/web/reviews"),
    ("GET", "/api/v1/reviews"),
    ("GET", "/api/web/reviews"),
    ("GET", "/api/v1/reviews/{review_task_id}"),
    ("GET", "/api/web/reviews/{review_task_id}"),
    ("GET", "/api/v1/reviews/{review_task_id}/skill-detail"),
    ("GET", "/api/web/reviews/{review_task_id}/skill-detail"),
    ("GET", "/api/v1/reviews/{review_task_id}/file"),
    ("GET", "/api/web/reviews/{review_task_id}/file"),
    ("GET", "/api/v1/reviews/{review_task_id}/download"),
    ("GET", "/api/web/reviews/{review_task_id}/download"),
    ("POST", "/api/v1/reviews/{review_task_id}/approve"),
    ("POST", "/api/web/reviews/{review_task_id}/approve"),
    ("POST", "/api/v1/reviews/{review_task_id}/reject"),
    ("POST", "/api/web/reviews/{review_task_id}/reject"),
    ("POST", "/api/v1/reviews/{review_task_id}/withdraw"),
    ("POST", "/api/web/reviews/{review_task_id}/withdraw"),
    ("POST", "/api/v1/promotions"),
    ("POST", "/api/web/promotions"),
    ("GET", "/api/v1/promotions"),
    ("GET", "/api/web/promotions"),
    ("GET", "/api/v1/promotions/{promotion_id}"),
    ("GET", "/api/web/promotions/{promotion_id}"),
    ("POST", "/api/v1/promotions/{promotion_id}/approve"),
    ("POST", "/api/web/promotions/{promotion_id}/approve"),
    ("POST", "/api/v1/promotions/{promotion_id}/reject"),
    ("POST", "/api/web/promotions/{promotion_id}/reject"),
    ("POST", "/api/v1/skills/{namespace}/{slug}/archive"),
    ("POST", "/api/web/skills/{namespace}/{slug}/archive"),
    ("DELETE", "/api/v1/skills/{namespace}/{slug}/versions/{version}"),
    ("DELETE", "/api/web/skills/{namespace}/{slug}/versions/{version}"),
    ("POST", "/api/v1/skills/{namespace}/{slug}/versions/{version}/rerelease"),
    ("POST", "/api/web/skills/{namespace}/{slug}/versions/{version}/rerelease"),
    ("POST", "/api/v1/admin/skills/{skill_id}/hide"),
    ("POST", "/api/v1/admin/skills/versions/{version_id}/yank"),
    ("POST", "/api/v1/admin/skill-reports/{report_id}/resolve"),
    ("POST", "/api/v1/admin/profile-reviews/{request_id}/approve"),
    ("POST", "/api/v1/skills/{namespace}/{slug}/reports"),
    ("POST", "/api/web/skills/{namespace}/{slug}/reports"),
    ("PUT", "/api/v1/skills/{namespace}/{slug}/labels/{label_slug}"),
    ("PUT", "/api/web/skills/{namespace}/{slug}/labels/{label_slug}"),
    ("PUT", "/api/v1/skills/{namespace}/{slug}/tags/{tagName}"),
    ("PUT", "/api/web/skills/{namespace}/{slug}/tags/{tagName}"),
    ("PUT", "/api/v1/skills/{skill_id}/star"),
    ("DELETE", "/api/v1/skills/{skill_id}/star"),
    ("PUT", "/api/v1/skills/{skill_id}/subscription"),
    ("DELETE", "/api/v1/skills/{skill_id}/subscription"),
    ("PUT", "/api/v1/skills/{skill_id}/rating"),
    ("POST", "/api/v1/namespaces/{slug}/freeze"),
    ("POST", "/api/web/namespaces/{slug}/freeze"),
    ("POST", "/api/v1/namespaces/{slug}/transfer-ownership"),
    ("POST", "/api/web/namespaces/{slug}/transfer-ownership"),
    ("GET", "/api/v1/governance/summary"),
    ("GET", "/api/web/governance/summary"),
    ("GET", "/api/v1/governance/inbox"),
    ("GET", "/api/web/governance/inbox"),
    ("GET", "/api/v1/governance/activity"),
    ("GET", "/api/web/governance/activity"),
    ("GET", "/api/v1/governance/notifications"),
    ("POST", "/api/v1/governance/notifications/{notification_id}/read"),
    ("GET", "/api/v1/notifications/sse"),
    ("GET", "/api/web/notifications/sse"),
}


def test_lifecycle_governance_routes_are_registered_and_documented_as_python_owned() -> None:
    app_routes = _app_routes()
    registry_rows = _route_registry_rows()
    expected_routes = {(method, _route_shape(path)) for method, path in LIFECYCLE_GOVERNANCE_ROUTES}

    missing_from_app = sorted(expected_routes - app_routes)
    missing_from_registry = sorted(expected_routes - set(registry_rows))
    non_python = sorted(route for route in expected_routes if registry_rows.get(route) != "python")

    assert missing_from_app == []
    assert missing_from_registry == []
    assert non_python == []


def test_lifecycle_governance_registry_notes_do_not_keep_stale_java_deferred_wording() -> None:
    registry = (ROOT / "docs" / "backend-python-migration" / "route-registry.md").read_text(encoding="utf-8")
    forbidden_fragments = [
        "Detail and file/download remain Java-owned",
        "detail and file/download remain Java-owned",
        "keeps write routes Java-owned",
        "Other review routes remain Java-owned",
        "keeps namespace lifecycle/profile APIs Java-owned",
        "Active notification fanout remains deferred",
    ]

    offenders = [fragment for fragment in forbidden_fragments if fragment in registry]

    assert offenders == []


def test_lifecycle_governance_audit_result_documents_each_deferred_bucket() -> None:
    result_path = ROOT / "docs" / "backend-python-migration" / "results" / "2026-06-12-lifecycle-governance-deferred-audit.md"
    result = result_path.read_text(encoding="utf-8")

    for heading in [
        "Publish Side Effects",
        "Review And Promotion Transitions",
        "Admin Governance Actions",
        "Skill Tag Label Report Social Delete Flows",
        "Governance Summary Inbox Activity Notifications",
    ]:
        assert f"## {heading}" in result

    assert "No broad lifecycle/governance deferred bucket remains" in result
