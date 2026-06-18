from __future__ import annotations

from difflib import SequenceMatcher


COMPARE_MAX_FILE_BYTES = 1024 * 1024
COMPARE_MAX_LINES = 5000
BINARY_FILE_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".zip",
    ".tar",
    ".gz",
    ".jar",
    ".war",
    ".class",
    ".so",
    ".dll",
    ".exe",
    ".pdf",
)


def is_binary_compare_path(path: str) -> bool:
    lower_path = path.lower()
    return any(lower_path.endswith(extension) for extension in BINARY_FILE_EXTENSIONS)


def split_compare_lines(content: str | None) -> list[str]:
    if not content:
        return []
    lines = content.splitlines()
    if content.endswith(("\n", "\r")):
        lines.append("")
    return lines


def build_compare_hunks(old_content: str, new_content: str) -> list[dict[str, object]]:
    old_lines = split_compare_lines(old_content)
    new_lines = split_compare_lines(new_content)
    hunks: list[dict[str, object]] = []
    matcher = SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue

        lines: list[dict[str, object]] = []
        for offset, line in enumerate(old_lines[old_start:old_end], start=old_start + 1):
            lines.append(
                {
                    "type": "DELETE",
                    "content": line,
                    "oldLineNumber": offset,
                    "newLineNumber": None,
                }
            )
        for offset, line in enumerate(new_lines[new_start:new_end], start=new_start + 1):
            lines.append(
                {
                    "type": "ADD",
                    "content": line,
                    "oldLineNumber": None,
                    "newLineNumber": offset,
                }
            )

        hunks.append(
            {
                "oldStart": old_start + 1,
                "oldLines": old_end - old_start,
                "newStart": new_start + 1,
                "newLines": new_end - new_start,
                "lines": lines,
            }
        )
    return hunks


def build_compare_file(
    path: str,
    from_file: dict[str, object] | None,
    to_file: dict[str, object] | None,
) -> dict[str, object] | None:
    if from_file is not None and to_file is not None and from_file.get("sha256") == to_file.get("sha256"):
        return None

    if from_file is None:
        change_type = "ADDED"
        old_size = None
        new_size = int(to_file["file_size"]) if to_file is not None else None
        old_content = ""
        new_content = str(to_file.get("content") or "") if to_file is not None else ""
    elif to_file is None:
        change_type = "REMOVED"
        old_size = int(from_file["file_size"])
        new_size = None
        old_content = str(from_file.get("content") or "")
        new_content = ""
    else:
        change_type = "MODIFIED"
        old_size = int(from_file["file_size"])
        new_size = int(to_file["file_size"])
        old_content = str(from_file.get("content") or "")
        new_content = str(to_file.get("content") or "")

    binary = is_binary_compare_path(path)
    old_lines = split_compare_lines(old_content)
    new_lines = split_compare_lines(new_content)
    truncated = (
        (old_size is not None and old_size > COMPARE_MAX_FILE_BYTES)
        or (new_size is not None and new_size > COMPARE_MAX_FILE_BYTES)
        or len(old_lines) > COMPARE_MAX_LINES
        or len(new_lines) > COMPARE_MAX_LINES
    )
    hunks = [] if binary or truncated else build_compare_hunks(old_content, new_content)
    return {
        "path": path,
        "changeType": change_type,
        "oldSize": old_size,
        "newSize": new_size,
        "binary": binary,
        "truncated": truncated,
        "hunks": hunks,
    }


def build_compare_response(
    from_version: str,
    to_version: str,
    from_files: dict[str, dict[str, object]],
    to_files: dict[str, dict[str, object]],
) -> dict[str, object]:
    files = [
        file
        for path in sorted(set(from_files) | set(to_files))
        if (file := build_compare_file(path, from_files.get(path), to_files.get(path))) is not None
    ]
    added_files = sum(1 for file in files if file["changeType"] == "ADDED")
    removed_files = sum(1 for file in files if file["changeType"] == "REMOVED")
    modified_files = sum(1 for file in files if file["changeType"] == "MODIFIED")
    added_lines = sum(
        1
        for file in files
        for hunk in file["hunks"]
        for line in hunk["lines"]
        if line["type"] == "ADD"
    )
    removed_lines = sum(
        1
        for file in files
        for hunk in file["hunks"]
        for line in hunk["lines"]
        if line["type"] == "DELETE"
    )
    return {
        "from": from_version,
        "to": to_version,
        "summary": {
            "totalFiles": len(files),
            "addedFiles": added_files,
            "modifiedFiles": modified_files,
            "removedFiles": removed_files,
            "addedLines": added_lines,
            "removedLines": removed_lines,
        },
        "files": files,
    }


__all__ = [
    "BINARY_FILE_EXTENSIONS",
    "COMPARE_MAX_FILE_BYTES",
    "COMPARE_MAX_LINES",
    "build_compare_file",
    "build_compare_hunks",
    "build_compare_response",
    "is_binary_compare_path",
    "split_compare_lines",
]
