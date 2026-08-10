from __future__ import annotations

from collections import Counter
from threading import Lock

_SEARCH_REBUILD_TRIGGERS = {"batch", "single"}
_search_rebuild_failures: Counter[str] = Counter()
_metrics_lock = Lock()


def increment_search_rebuild_failure(trigger: str) -> None:
    if trigger not in _SEARCH_REBUILD_TRIGGERS:
        raise ValueError(f"Unsupported search rebuild trigger: {trigger}")
    with _metrics_lock:
        _search_rebuild_failures[trigger] += 1


def render_prometheus_metrics() -> str:
    with _metrics_lock:
        search_rebuild_failures = dict(_search_rebuild_failures)

    lines = [
        "# HELP skillhub_python_backend_up SkillHub Python backend availability.",
        "# TYPE skillhub_python_backend_up gauge",
        "skillhub_python_backend_up 1",
        "# HELP skillhub_search_rebuild_failure_total Failed label-triggered search document rebuilds.",
        "# TYPE skillhub_search_rebuild_failure_total counter",
    ]
    lines.extend(
        f'skillhub_search_rebuild_failure_total{{trigger="{trigger}"}} {count}'
        for trigger, count in sorted(search_rebuild_failures.items())
    )
    lines.append("")
    return "\n".join(lines)


__all__ = ["increment_search_rebuild_failure", "render_prometheus_metrics"]
