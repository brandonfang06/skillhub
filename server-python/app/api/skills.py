from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.core.response import ok
from app.skills.read_repository import *  # noqa: F403

router = APIRouter()

async def _resolve_reader_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def resolve_clawhub_download_coordinate(
    request: Request,
    slug: str,
    current_user_id: str | None,
) -> tuple[str, str]:
    reader = getattr(request.app.state, "clawhub_download_coordinate_reader", None)
    if reader is not None:
        coordinate = reader(slug, current_user_id)
        coordinate = await _resolve_reader_result(coordinate)
    else:
        legacy_reader = getattr(request.app.state, "clawhub_legacy_slug_reader", None)
        if legacy_reader is not None:
            coordinate = legacy_reader(slug)
            coordinate = await _resolve_reader_result(coordinate)
        elif "--" in slug:
            coordinate = from_clawhub_canonical_slug(slug)
        else:
            db_engine = getattr(request.app.state, "db_engine", None)
            coordinate = (
                from_clawhub_canonical_slug(slug)
                if db_engine is None
                else await read_clawhub_legacy_slug_coordinate(db_engine, slug)
            )

    if isinstance(coordinate, dict):
        return str(coordinate["namespace"]), str(coordinate["slug"])
    namespace, skill_slug = coordinate
    return str(namespace), str(skill_slug)


def build_download_redirect(namespace: str, slug: str, version: str | None) -> RedirectResponse:
    namespace_path = quote(namespace, safe="")
    slug_path = quote(slug, safe="")
    if version is None or version == "latest":
        location = f"/api/v1/skills/{namespace_path}/{slug_path}/download"
    else:
        location = (
            f"/api/v1/skills/{namespace_path}/{slug_path}/versions/"
            f"{quote(version, safe='')}/download"
        )
    return RedirectResponse(location, status_code=302)


@router.get("/api/v1/download")
async def download_clawhub_skill_by_query(
    request: Request,
    slug: str,
    version: str | None = "latest",
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> RedirectResponse:
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        namespace, skill_slug = await resolve_clawhub_download_coordinate(request, slug, current_user_id)
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_download_redirect(namespace, skill_slug, version)


@router.get("/api/v1/download/{canonicalSlug}")
async def download_clawhub_skill_by_path(
    canonicalSlug: str,
    version: str | None = "latest",
) -> RedirectResponse:
    namespace, slug = from_clawhub_canonical_slug(canonicalSlug)
    return build_download_redirect(namespace, slug, version)


@router.get("/api/web/skills")
async def search_skills(
    request: Request,
    q: str | None = None,
    namespace: str | None = None,
    label: list[str] = Query(default_factory=list),
    sort: str | None = None,
    page: str | None = None,
    size: str | None = None,
) -> dict[str, object]:
    normalized_labels = normalize_label_slugs(label)
    normalized_sort = normalize_search_sort(sort)
    normalized_page = parse_non_negative_int(page, 0)
    normalized_size = parse_positive_int(size, 20)
    reader = getattr(request.app.state, "skill_search_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(
                reader(
                    keyword=q,
                    namespace=namespace,
                    labels=normalized_labels,
                    sort=normalized_sort,
                    page=normalized_page,
                    size=normalized_size,
                )
            )
        else:
            data = await read_skill_search(
                request.app.state.db_engine,
                keyword=q,
                namespace=namespace,
                labels=normalized_labels,
                sort=normalized_sort,
                page=normalized_page,
                size=normalized_size,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/search")
async def search_clawhub_skills(
    request: Request,
    q: str = "",
    page: int = 0,
    limit: int = 20,
) -> dict[str, object]:
    normalized_page = max(page, 0)
    normalized_limit = limit if limit > 0 else 20
    sort = "newest" if q.strip() == "" else "relevance"
    reader = getattr(request.app.state, "clawhub_search_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(
                reader(
                    keyword=q,
                    namespace=None,
                    labels=[],
                    sort=sort,
                    page=normalized_page,
                    size=normalized_limit,
                )
            )
        else:
            data = await read_skill_search(
                request.app.state.db_engine,
                keyword=q,
                namespace=None,
                labels=[],
                sort=sort,
                page=normalized_page,
                size=normalized_limit,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_clawhub_search_response(data)


@router.get("/api/cli/v1/skills/search")
async def search_cli_skills(
    request: Request,
    q: str | None = None,
    limit: int = 20,
) -> dict[str, object]:
    normalized_limit = limit if limit > 0 else 20
    reader = getattr(request.app.state, "cli_skill_search_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(
                reader(
                    keyword=q,
                    namespace=None,
                    labels=[],
                    sort="newest",
                    page=0,
                    size=normalized_limit,
                )
            )
        else:
            data = await read_skill_search(
                request.app.state.db_engine,
                keyword=q,
                namespace=None,
                labels=[],
                sort="newest",
                page=0,
                size=normalized_limit,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", build_cli_search_response(data, normalized_limit), request)


@router.get("/api/v1/resolve")
async def resolve_clawhub_skill_by_query(
    request: Request,
    slug: str,
    version: str | None = None,
    hash: str | None = Query(default=None, alias="hash"),
) -> dict[str, object]:
    try:
        if "--" in slug:
            namespace, skill_slug = from_clawhub_canonical_slug(slug)
        else:
            legacy_reader = getattr(request.app.state, "clawhub_legacy_slug_reader", None)
            if legacy_reader is not None:
                coordinate = legacy_reader(slug)
                if isawaitable(coordinate):
                    coordinate = await coordinate
                if isinstance(coordinate, dict):
                    namespace = str(coordinate["namespace"])
                    skill_slug = str(coordinate["slug"])
                else:
                    namespace, skill_slug = coordinate
            else:
                db_engine = getattr(request.app.state, "db_engine", None)
                if db_engine is None:
                    namespace, skill_slug = from_clawhub_canonical_slug(slug)
                else:
                    namespace, skill_slug = await read_clawhub_legacy_slug_coordinate(db_engine, slug)

        version_selector, tag_selector = clawhub_resolve_selectors(version, default_latest=False)
        reader = getattr(request.app.state, "skill_resolve_reader", None)
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, skill_slug, version_selector, tag_selector, hash))
        else:
            data = await read_skill_resolve(
                request.app.state.db_engine,
                namespace,
                skill_slug,
                version_selector,
                tag_selector,
                hash,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_clawhub_resolve_response(data)


@router.get("/api/cli/v1/skills/{namespace}/{slug}/resolve")
async def resolve_cli_skill(
    request: Request,
    namespace: str,
    slug: str,
    version: str | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    current_user_id = normalized_current_user_id(mock_user_id)
    reader = getattr(request.app.state, "skill_resolve_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version, None, None, current_user_id))
        else:
            data = await read_skill_resolve(
                request.app.state.db_engine,
                namespace,
                slug,
                version,
                None,
                None,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", build_cli_resolve_response(data), request)


@router.get("/api/v1/resolve/{canonicalSlug}")
async def resolve_clawhub_skill_by_path(
    request: Request,
    canonicalSlug: str,
    version: str | None = "latest",
) -> dict[str, object]:
    namespace, slug = from_clawhub_canonical_slug(canonicalSlug)
    version_selector, tag_selector = clawhub_resolve_selectors(version, default_latest=True)
    reader = getattr(request.app.state, "skill_resolve_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version_selector, tag_selector, None))
        else:
            data = await read_skill_resolve(
                request.app.state.db_engine,
                namespace,
                slug,
                version_selector,
                tag_selector,
                None,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_clawhub_resolve_response(data)


@router.get("/api/v1/skills")
async def list_clawhub_skills(
    request: Request,
    page: str | None = None,
    limit: str | None = None,
    sort: str | None = None,
) -> dict[str, object]:
    normalized_page = parse_non_negative_int(page, 0)
    normalized_limit = parse_positive_int(limit, 25)
    normalized_sort = normalize_search_sort(sort)
    reader = getattr(request.app.state, "clawhub_skills_list_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(
                reader(
                    keyword="",
                    namespace=None,
                    labels=[],
                    sort=normalized_sort,
                    page=normalized_page,
                    size=normalized_limit,
                )
            )
        else:
            data = await read_skill_search(
                request.app.state.db_engine,
                keyword="",
                namespace=None,
                labels=[],
                sort=normalized_sort,
                page=normalized_page,
                size=normalized_limit,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_clawhub_skills_list_response(data)


@router.get("/api/v1/skills/{canonicalSlug}")
async def get_clawhub_skill_detail(request: Request, canonicalSlug: str) -> dict[str, object]:
    namespace, slug = from_clawhub_canonical_slug(canonicalSlug)
    reader = getattr(request.app.state, "clawhub_skill_detail_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug))
        else:
            data = await read_clawhub_skill_detail(request.app.state.db_engine, namespace, slug)
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_clawhub_skill_detail_response(data)


def clawhub_delete_placeholder_response(mock_user_id: str | None) -> dict[str, bool]:
    if normalized_current_user_id(mock_user_id) is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return {"ok": True}


@router.delete("/api/v1/skills/{canonicalSlug}")
async def delete_clawhub_skill_placeholder(
    canonicalSlug: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, bool]:
    return clawhub_delete_placeholder_response(x_mock_user_id)


@router.post("/api/v1/skills/{canonicalSlug}/undelete")
async def undelete_clawhub_skill_placeholder(
    canonicalSlug: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, bool]:
    return clawhub_delete_placeholder_response(x_mock_user_id)


@router.get("/api/v1/skills/{namespace}/{slug}")
@router.get("/api/web/skills/{namespace}/{slug}")
async def get_skill_detail(
    namespace: str,
    slug: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_detail_reader", None)
    current_user_id = await optional_current_user_id(request, mock_user_id)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, current_user_id))
        else:
            data = await read_skill_detail(request.app.state.db_engine, namespace, slug, current_user_id)
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/resolve")
@router.get("/api/web/skills/{namespace}/{slug}/resolve")
async def resolve_skill_version(
    namespace: str,
    slug: str,
    request: Request,
    version: str | None = None,
    tag: str | None = None,
    hash_value: str | None = Query(default=None, alias="hash"),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_resolve_reader", None)
    current_user_id = await optional_current_user_id(request, mock_user_id)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version, tag, hash_value, current_user_id))
        else:
            data = await read_skill_resolve(
                request.app.state.db_engine,
                namespace,
                slug,
                version,
                tag,
                hash_value,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/versions/compare")
@router.get("/api/web/skills/{namespace}/{slug}/versions/compare")
async def compare_skill_versions(
    namespace: str,
    slug: str,
    request: Request,
    from_version: str = Query(alias="from"),
    to_version: str = Query(alias="to"),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_version_compare_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, from_version, to_version, current_user_id))
        else:
            data = await read_skill_version_compare(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                namespace,
                slug,
                from_version,
                to_version,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/versions/{version}")
@router.get("/api/web/skills/{namespace}/{slug}/versions/{version}")
async def get_skill_version_detail(
    namespace: str,
    slug: str,
    version: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_version_detail_reader", None)
    current_user_id = mock_user_id.strip() if mock_user_id is not None and mock_user_id.strip() != "" else None
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version, current_user_id))
        else:
            data = await read_skill_version_detail(
                request.app.state.db_engine,
                namespace,
                slug,
                version,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/versions")
@router.get("/api/web/skills/{namespace}/{slug}/versions")
async def list_skill_versions(
    namespace: str,
    slug: str,
    request: Request,
    page: int = 0,
    size: int = 20,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_versions_reader", None)
    page, size = normalize_page_request(page, size)
    current_user_id = mock_user_id.strip() if mock_user_id is not None and mock_user_id.strip() != "" else None
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, page, size, current_user_id))
        else:
            data = await read_skill_versions(request.app.state.db_engine, namespace, slug, page, size, current_user_id)
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/versions/{version}/files")
@router.get("/api/web/skills/{namespace}/{slug}/versions/{version}/files")
async def list_skill_version_files(
    namespace: str,
    slug: str,
    version: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_version_files_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version, current_user_id))
        else:
            data = await read_skill_version_files(
                request.app.state.db_engine,
                namespace,
                slug,
                version,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/tags/{tagName}/files")
@router.get("/api/web/skills/{namespace}/{slug}/tags/{tagName}/files")
async def list_skill_tag_files(
    namespace: str,
    slug: str,
    tagName: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_tag_files_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, tagName, current_user_id))
        else:
            data = await read_skill_tag_files(
                request.app.state.db_engine,
                namespace,
                slug,
                tagName,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/tags")
@router.get("/api/web/skills/{namespace}/{slug}/tags")
async def list_skill_tags_route(
    namespace: str,
    slug: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_tags_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, current_user_id))
        else:
            data = await list_skill_tags(request.app.state.db_engine, namespace, slug, current_user_id)
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.put("/api/v1/skills/{namespace}/{slug}/tags/{tagName}")
@router.put("/api/web/skills/{namespace}/{slug}/tags/{tagName}")
async def create_or_move_skill_tag_route(
    namespace: str,
    slug: str,
    tagName: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    current_user_id = normalized_current_user_id(mock_user_id)
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="error.validation")
    body_tag_name = str(payload.get("tagName") or "").strip()
    target_version = str(payload.get("targetVersion") or "").strip()
    if body_tag_name == "" or target_version == "":
        raise HTTPException(status_code=400, detail="error.validation")

    writer = getattr(request.app.state, "skill_tag_writer", None)
    try:
        if writer is not None:
            data = await _resolve_reader_result(writer(namespace, slug, tagName, target_version, current_user_id))
        else:
            data = await create_or_move_skill_tag(
                request.app.state.db_engine,
                namespace,
                slug,
                tagName,
                target_version,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.delete("/api/v1/skills/{namespace}/{slug}/tags/{tagName}")
@router.delete("/api/web/skills/{namespace}/{slug}/tags/{tagName}")
async def delete_skill_tag_route(
    namespace: str,
    slug: str,
    tagName: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    current_user_id = normalized_current_user_id(mock_user_id)
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    writer = getattr(request.app.state, "skill_tag_delete_writer", None)
    try:
        if writer is not None:
            data = await _resolve_reader_result(writer(namespace, slug, tagName, current_user_id))
        else:
            data = await delete_skill_tag(request.app.state.db_engine, namespace, slug, tagName, current_user_id)
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u5220\u9664\u6210\u529f", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/versions/{version}/file")
@router.get("/api/web/skills/{namespace}/{slug}/versions/{version}/file")
async def get_skill_version_file_content(
    namespace: str,
    slug: str,
    version: str,
    request: Request,
    path: str = Query(...),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    reader = getattr(request.app.state, "skill_version_file_content_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            content = await _resolve_reader_result(reader(namespace, slug, version, path, current_user_id))
        else:
            content = await read_skill_version_file_content(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                namespace,
                slug,
                version,
                path,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(content=content, media_type="application/octet-stream")


@router.get("/api/v1/skills/{namespace}/{slug}/tags/{tagName}/file")
@router.get("/api/web/skills/{namespace}/{slug}/tags/{tagName}/file")
async def get_skill_tag_file_content(
    namespace: str,
    slug: str,
    tagName: str,
    request: Request,
    path: str = Query(...),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    reader = getattr(request.app.state, "skill_tag_file_content_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            content = await _resolve_reader_result(reader(namespace, slug, tagName, path, current_user_id))
        else:
            content = await read_skill_tag_file_content(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                namespace,
                slug,
                tagName,
                path,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(content=content, media_type="application/octet-stream")


@router.get("/api/v1/skills/{namespace}/{slug}/download")
@router.get("/api/web/skills/{namespace}/{slug}/download")
async def download_skill_latest(
    namespace: str,
    slug: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    reader = getattr(request.app.state, "skill_download_latest_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            result = await _resolve_reader_result(reader(namespace, slug, current_user_id))
        else:
            result = await read_skill_download_latest(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                namespace,
                slug,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_download_response(result)


@router.get("/api/v1/skills/{namespace}/{slug}/versions/{version}/download")
@router.get("/api/web/skills/{namespace}/{slug}/versions/{version}/download")
async def download_skill_version(
    namespace: str,
    slug: str,
    version: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    reader = getattr(request.app.state, "skill_download_version_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            result = await _resolve_reader_result(reader(namespace, slug, version, current_user_id))
        else:
            result = await read_skill_download_version(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                namespace,
                slug,
                version,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_download_response(result)


@router.get("/api/cli/v1/skills/{namespace}/{slug}/download")
async def download_cli_skill_latest(
    namespace: str,
    slug: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    return await download_skill_latest(namespace, slug, request, mock_user_id)


@router.get("/api/cli/v1/skills/{namespace}/{slug}/versions/{version}/download")
async def download_cli_skill_version(
    namespace: str,
    slug: str,
    version: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    return await download_skill_version(namespace, slug, version, request, mock_user_id)


@router.get("/api/v1/skills/{namespace}/{slug}/tags/{tagName}/download")
@router.get("/api/web/skills/{namespace}/{slug}/tags/{tagName}/download")
async def download_skill_tag(
    namespace: str,
    slug: str,
    tagName: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    reader = getattr(request.app.state, "skill_download_tag_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            result = await _resolve_reader_result(reader(namespace, slug, tagName, current_user_id))
        else:
            result = await read_skill_download_tag(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                namespace,
                slug,
                tagName,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_download_response(result)
