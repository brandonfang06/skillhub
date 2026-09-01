"""Runnable search/download and publish examples for ``SkillHubClient``."""

from __future__ import annotations

import os
import sys
from typing import Any

from skillhub_client import SkillHubClient, SkillHubError


def _pick(value: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        if isinstance(value, dict) and value.get(key) is not None:
            return value[key]
    return default


def demo_read(client: SkillHubClient) -> None:
    result = client.search(keyword="email", size=5)
    items = _pick(
        result,
        "items",
        "content",
        "results",
        default=result if isinstance(result, list) else [],
    )
    if not items:
        print("No skills found. Try a different keyword or registry.")
        return

    for skill in items:
        slug = _pick(skill, "slug", "name", default="(unnamed)")
        namespace = _pick(skill, "namespace", default="")
        version = _pick(skill, "version", "latestVersion", default="?")
        coordinate = f"{namespace}/{slug}" if namespace else slug
        print(f"{coordinate} v{version}")

    first = items[0]
    namespace = _pick(first, "namespace", default="")
    slug = _pick(first, "slug", "name")
    if namespace and slug:
        resolved = client.resolve(namespace, slug)
        version = _pick(resolved, "version", default=None)
        destination = client.download(namespace, slug, version=version)
        print(f"downloaded {destination} ({os.path.getsize(destination)} bytes)")


def demo_publish(client: SkillHubClient, zip_path: str, namespace: str) -> None:
    if not client.token:
        raise SystemExit("Publishing requires SKILLHUB_TOKEN to be set.")
    print(client.publish(zip_path, namespace))


def main() -> None:
    try:
        client = SkillHubClient()
        args = sys.argv[1:]
        if args and args[0] == "publish":
            if len(args) != 3:
                raise SystemExit(
                    "usage: python example_usage.py publish <zip_path> <namespace>"
                )
            demo_publish(client, args[1], args[2])
        else:
            demo_read(client)
    except (SkillHubError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
