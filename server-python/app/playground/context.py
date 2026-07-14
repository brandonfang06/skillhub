from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath

from app.playground.contracts import (
    PlaygroundContextResponse,
    PlaygroundFile,
    PlaygroundSkill,
)


TEXT_SUFFIXES = {
    ".bash",
    ".c",
    ".cfg",
    ".cpp",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_FILENAMES = {"dockerfile", "license", "makefile", "notice"}


def _safe_path(value: object) -> str | None:
    normalized = str(value).replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or ".." in path.parts
        or (path.parts and path.parts[0].endswith(":"))
    ):
        return None
    return path.as_posix()


def _priority(path: str) -> int:
    lower = path.lower()
    if lower == "skill.md":
        return 0
    if lower == "readme.md":
        return 1
    if lower.startswith("references/"):
        return 2
    return 3


def _is_text_path(path: str) -> bool:
    pure_path = PurePosixPath(path)
    return (
        pure_path.suffix.lower() in TEXT_SUFFIXES
        or pure_path.name.lower() in TEXT_FILENAMES
    )


def select_context_paths(
    files: list[dict[str, object]],
    *,
    max_bytes: int,
) -> list[str]:
    candidates: list[tuple[int, str, int]] = []
    for item in files:
        path = _safe_path(item["filePath"])
        if path is None or not _is_text_path(path):
            continue
        size = max(0, int(item.get("fileSize") or 0))
        candidates.append((_priority(path), path, size))

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
    selected_paths = set(paths)
    safe_paths = {
        path
        for item in files
        if (path := _safe_path(item["filePath"])) is not None
    }
    contents: list[PlaygroundFile] = []
    actual_bytes = 0
    for path in sorted(safe_paths, key=lambda item: (_priority(item), item)):
        if path not in selected_paths:
            contents.append(
                PlaygroundFile(
                    path=path,
                    content="",
                    includedInPrompt=False,
                )
            )
            continue
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
                includedInPrompt=True,
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
