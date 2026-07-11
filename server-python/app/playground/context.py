from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath

from app.playground.contracts import (
    PlaygroundContextResponse,
    PlaygroundFile,
    PlaygroundSkill,
)


TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}


def select_context_paths(
    files: list[dict[str, object]],
    *,
    max_bytes: int,
) -> list[str]:
    candidates: list[tuple[int, str, int]] = []
    for item in files:
        path = str(item["filePath"])
        normalized = path.replace("\\", "/")
        path_parts = PurePosixPath(normalized).parts
        if ".." in path_parts:
            continue
        lower = normalized.lower()
        if lower == "skill.md":
            priority = 0
        elif lower == "readme.md":
            priority = 1
        elif lower.startswith("references/") and any(
            lower.endswith(suffix) for suffix in TEXT_SUFFIXES
        ):
            priority = 2
        else:
            continue
        size = max(0, int(item.get("fileSize") or 0))
        candidates.append((priority, path, size))

    selected: list[str] = []
    total = 0
    for _, path, size in sorted(candidates, key=lambda item: (item[0], item[1])):
        if total + size <= max_bytes:
            selected.append(path)
            total += size
    return selected


async def build_context_bundle(
    *,
    namespace: str,
    slug: str,
    version: str,
    current_user_id: str,
    read_detail: Callable[..., Awaitable[dict[str, object]]],
    read_files: Callable[..., Awaitable[list[dict[str, object]]]],
    read_content: Callable[..., Awaitable[bytes]],
    max_bytes: int,
) -> PlaygroundContextResponse:
    detail = await read_detail(namespace, slug, current_user_id)
    files = await read_files(namespace, slug, version, current_user_id)
    paths = select_context_paths(files, max_bytes=max_bytes)
    contents: list[PlaygroundFile] = []
    actual_bytes = 0
    for path in paths:
        raw = await read_content(
            namespace,
            slug,
            version,
            path,
            current_user_id,
        )
        actual_bytes += len(raw)
        if actual_bytes > max_bytes:
            raise ValueError("playground context exceeds configured byte limit")
        contents.append(
            PlaygroundFile(
                path=path,
                content=raw.decode("utf-8", errors="replace"),
            )
        )
    return PlaygroundContextResponse(
        skill=PlaygroundSkill(
            namespace=namespace,
            slug=slug,
            displayName=str(detail["displayName"]),
            version=version,
        ),
        files=contents,
    )
