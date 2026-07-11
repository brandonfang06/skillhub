import pytest

from app.playground.context import build_context_bundle, select_context_paths


def test_context_paths_include_skill_docs_and_exclude_scripts() -> None:
    files = [
        {"filePath": "scripts/run.py", "fileSize": 100},
        {"filePath": "references/output-format.md", "fileSize": 100},
        {"filePath": "README.md", "fileSize": 100},
        {"filePath": "SKILL.md", "fileSize": 100},
        {"filePath": "references/archive.zip", "fileSize": 100},
    ]

    assert select_context_paths(files, max_bytes=1000) == [
        "SKILL.md",
        "README.md",
        "references/output-format.md",
    ]


@pytest.mark.anyio
async def test_bundle_uses_existing_readers_without_download_side_effects() -> None:
    calls: list[str] = []

    async def read_detail(namespace, slug, current_user_id):
        assert current_user_id == "user-1"
        return {
            "namespace": namespace,
            "slug": slug,
            "displayName": "Notes",
        }

    async def read_files(namespace, slug, version, current_user_id):
        return [{"filePath": "SKILL.md", "fileSize": 9}]

    async def read_content(
        namespace,
        slug,
        version,
        path,
        current_user_id,
    ):
        calls.append(path)
        return b"Summarize"

    bundle = await build_context_bundle(
        namespace="global",
        slug="notes",
        version="1.0.0",
        current_user_id="user-1",
        read_detail=read_detail,
        read_files=read_files,
        read_content=read_content,
        max_bytes=1000,
    )

    assert bundle.skill.version == "1.0.0"
    assert bundle.files[0].content == "Summarize"
    assert calls == ["SKILL.md"]


@pytest.mark.anyio
async def test_bundle_enforces_limit_against_actual_content_bytes() -> None:
    async def read_detail(namespace, slug, current_user_id):
        return {"displayName": "Notes"}

    async def read_files(namespace, slug, version, current_user_id):
        return [{"filePath": "SKILL.md", "fileSize": 1}]

    async def read_content(namespace, slug, version, path, current_user_id):
        return b"larger than metadata"

    with pytest.raises(ValueError, match="byte limit"):
        await build_context_bundle(
            namespace="global",
            slug="notes",
            version="1.0.0",
            current_user_id="user-1",
            read_detail=read_detail,
            read_files=read_files,
            read_content=read_content,
            max_bytes=4,
        )
