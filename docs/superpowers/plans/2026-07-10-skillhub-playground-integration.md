# SkillHub Playground Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a disabled-by-default SkillHub entry point, read-only capability/context contract, and dedicated playground route that remain harmless when the separately deployed sidecar is absent.

**Architecture:** The Python backend signs a short-lived opaque capability and revalidates access when the sidecar fetches a bounded text context bundle. The web app reads runtime flags, opens a dedicated route, and calls the sidecar directly; no SkillHub startup, health check, database schema, lifecycle behavior, or base deployment depends on the sidecar.

**Tech Stack:** Python 3.12, FastAPI, stdlib HMAC/SHA-256, pytest, React 19, TanStack Router/Query, TypeScript, Tailwind, Vitest, native EventSource

---

## File Map

- `server-python/app/playground/capability.py`: issues and verifies scoped, expiring HMAC capabilities.
- `server-python/app/playground/context.py`: selects bounded text context and reuses existing skill readers.
- `server-python/app/playground/contracts.py`: OpenAPI response/request models.
- `server-python/app/api/playground.py`: isolated capability and context routes.
- `server-python/app/core/config.py`: lazy playground token settings; no sidecar health dependency.
- `server-python/app/main.py`: includes the additive router only.
- `web/src/api/client.ts`: runtime config and capability API wrapper.
- `web/src/features/playground/api.ts`: direct sidecar session/message/reset/delete client.
- `web/src/features/playground/use-playground.ts`: TanStack mutation and EventSource lifecycle.
- `web/src/pages/skill-playground.tsx`: dedicated split-view route.
- `web/src/pages/skill-detail.tsx`: feature-gated `Try in Playground` action.
- `web/src/app/router.tsx`: authenticated playground route.
- `web/runtime-config.js.template`, `web/src/bootstrap.ts`, `web/docker-entrypoint.d/30-runtime-config.sh`: disabled-by-default runtime settings.

### Task 1: Issue And Verify Narrow Playground Capabilities

**Files:**
- Create: `server-python/app/playground/__init__.py`
- Create: `server-python/app/playground/capability.py`
- Create: `server-python/tests/test_playground_capability.py`
- Modify: `server-python/app/core/config.py`
- Test: `server-python/tests/test_config.py`

- [ ] **Step 1: Write failing capability tests**

```python
# server-python/tests/test_playground_capability.py
from datetime import UTC, datetime, timedelta

import pytest

from app.playground.capability import CapabilityError, issue_capability, verify_capability


def test_capability_round_trip_is_read_only_and_coordinate_bound() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)
    token = issue_capability(
        secret="test-secret",
        issuer="skillhub-local",
        audience="skill-playground-sidecar",
        subject="user-1",
        namespace="global",
        slug="meeting-notes",
        version="1.2.3",
        ttl_seconds=300,
        now=now,
        token_id="token-1",
    )

    claims = verify_capability(
        token,
        secret="test-secret",
        issuer="skillhub-local",
        audience="skill-playground-sidecar",
        now=now + timedelta(seconds=1),
    )

    assert claims["scope"] == "playground:read"
    assert claims["sub"] == "user-1"
    assert claims["namespace"] == "global"
    assert "install" not in claims["scope"]


def test_capability_rejects_tampering_and_expiry() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)
    token = issue_capability(
        secret="test-secret",
        issuer="skillhub-local",
        audience="skill-playground-sidecar",
        subject="user-1",
        namespace="global",
        slug="meeting-notes",
        version="1.2.3",
        ttl_seconds=1,
        now=now,
        token_id="token-1",
    )

    with pytest.raises(CapabilityError):
        verify_capability(token + "x", secret="test-secret", issuer="skillhub-local", audience="skill-playground-sidecar", now=now)
    with pytest.raises(CapabilityError, match="expired"):
        verify_capability(token, secret="test-secret", issuer="skillhub-local", audience="skill-playground-sidecar", now=now + timedelta(seconds=2))
```

- [ ] **Step 2: Run the test and verify the module is missing**

Run: `cd server-python; uv run pytest tests/test_playground_capability.py -q`

Expected: FAIL because `app.playground.capability` does not exist.

- [ ] **Step 3: Implement a compact HMAC token with constant-time verification**

```python
# server-python/app/playground/capability.py
from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib
import hmac
import json
from typing import Callable
from uuid import uuid4


class CapabilityError(ValueError):
    pass


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_capability(
    *,
    secret: str,
    issuer: str,
    audience: str,
    subject: str,
    namespace: str,
    slug: str,
    version: str,
    ttl_seconds: int,
    now: datetime | None = None,
    token_id: str | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "namespace": namespace,
        "slug": slug,
        "version": version,
        "scope": "playground:read",
        "iat": int(issued_at.timestamp()),
        "exp": int(issued_at.timestamp()) + ttl_seconds,
        "jti": token_id or str(uuid4()),
    }
    payload = _encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _encode(hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def verify_capability(token: str, *, secret: str, issuer: str, audience: str, now: datetime | None = None) -> dict[str, object]:
    try:
        payload, signature = token.split(".", 1)
        expected = _encode(hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise CapabilityError("invalid signature")
        claims = json.loads(_decode(payload))
    except (ValueError, json.JSONDecodeError) as exc:
        raise CapabilityError("invalid capability") from exc
    current = int((now or datetime.now(UTC)).timestamp())
    if claims.get("iss") != issuer or claims.get("aud") != audience or claims.get("scope") != "playground:read":
        raise CapabilityError("invalid claims")
    if int(claims.get("exp", 0)) <= current:
        raise CapabilityError("expired capability")
    return claims
```

- [ ] **Step 4: Add settings with sidecar-independent defaults**

Add these fields to `Settings` and `get_settings()`:

```python
playground_token_secret: str
playground_token_ttl_seconds: int
playground_token_issuer: str
playground_token_audience: str
playground_context_max_bytes: int
```

```python
playground_token_secret=os.getenv("SKILLHUB_PLAYGROUND_TOKEN_SECRET", ""),
playground_token_ttl_seconds=parse_int(os.getenv("SKILLHUB_PLAYGROUND_TOKEN_TTL_SECONDS"), 300),
playground_token_issuer=os.getenv("SKILLHUB_PLAYGROUND_TOKEN_ISSUER", "skillhub"),
playground_token_audience=os.getenv("SKILLHUB_PLAYGROUND_TOKEN_AUDIENCE", "skill-playground-sidecar"),
playground_context_max_bytes=parse_int(os.getenv("SKILLHUB_PLAYGROUND_CONTEXT_MAX_BYTES"), 120000),
```

Extend `tests/test_config.py` to assert the empty-secret default and explicit overrides. Startup must continue when the secret is empty.

- [ ] **Step 5: Verify and commit**

Run: `cd server-python; uv run pytest tests/test_playground_capability.py tests/test_config.py -q`

Expected: selected tests pass.

```powershell
git add server-python/app/playground server-python/app/core/config.py server-python/tests/test_playground_capability.py server-python/tests/test_config.py
git commit -m "feat(playground): add scoped capability tokens"
```

### Task 2: Build A Bounded Read-Only Context Bundle

**Files:**
- Create: `server-python/app/playground/contracts.py`
- Create: `server-python/app/playground/context.py`
- Create: `server-python/tests/test_playground_context.py`

- [ ] **Step 1: Write failing path-selection and bundle tests**

```python
# server-python/tests/test_playground_context.py
import pytest

from app.playground.context import build_context_bundle, select_context_paths


def test_context_paths_include_skill_docs_and_exclude_scripts() -> None:
    files = [
        {"filePath": "SKILL.md", "fileSize": 100},
        {"filePath": "README.md", "fileSize": 100},
        {"filePath": "references/output-format.md", "fileSize": 100},
        {"filePath": "scripts/run.py", "fileSize": 100},
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
        return {"namespace": namespace, "slug": slug, "displayName": "Notes"}

    async def read_files(namespace, slug, version, current_user_id):
        return [{"filePath": "SKILL.md", "fileSize": 9}]

    async def read_content(namespace, slug, version, path, current_user_id):
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
```

- [ ] **Step 2: Run and verify the context module is missing**

Run: `cd server-python; uv run pytest tests/test_playground_context.py -q`

Expected: FAIL because `app.playground.context` does not exist.

- [ ] **Step 3: Add response contracts and bounded selection**

```python
# server-python/app/playground/contracts.py
from pydantic import BaseModel, ConfigDict, Field


class CapabilityRequest(BaseModel):
    version: str


class CapabilityResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token: str
    expires_at: int = Field(alias="expiresAt")


class PlaygroundSkill(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    namespace: str
    slug: str
    display_name: str = Field(alias="displayName")
    version: str


class PlaygroundFile(BaseModel):
    path: str
    content: str


class PlaygroundContextResponse(BaseModel):
    skill: PlaygroundSkill
    files: list[PlaygroundFile]
```

```python
# server-python/app/playground/context.py
from collections.abc import Awaitable, Callable

from app.playground.contracts import PlaygroundContextResponse, PlaygroundFile, PlaygroundSkill

TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}


def select_context_paths(files: list[dict[str, object]], *, max_bytes: int) -> list[str]:
    selected: list[str] = []
    total = 0
    for item in files:
        path = str(item["filePath"])
        normalized = path.replace("\\", "/")
        lower = normalized.lower()
        allowed = lower in {"skill.md", "readme.md"} or (lower.startswith("references/") and any(lower.endswith(suffix) for suffix in TEXT_SUFFIXES))
        size = int(item.get("fileSize") or 0)
        if allowed and total + size <= max_bytes:
            selected.append(path)
            total += size
    return selected


async def build_context_bundle(*, namespace, slug, version, current_user_id, read_detail, read_files, read_content, max_bytes):
    detail = await read_detail(namespace, slug, current_user_id)
    files = await read_files(namespace, slug, version, current_user_id)
    paths = select_context_paths(files, max_bytes=max_bytes)
    contents = []
    actual_bytes = 0
    for path in paths:
        raw = await read_content(namespace, slug, version, path, current_user_id)
        actual_bytes += len(raw)
        if actual_bytes > max_bytes:
            raise ValueError("playground context exceeds configured byte limit")
        contents.append(PlaygroundFile(path=path, content=raw.decode("utf-8", errors="replace")))
    return PlaygroundContextResponse(
        skill=PlaygroundSkill(namespace=namespace, slug=slug, displayName=str(detail["displayName"]), version=version),
        files=contents,
    )
```

- [ ] **Step 4: Verify and commit**

Run: `cd server-python; uv run pytest tests/test_playground_context.py -q`

Expected: `2 passed`.

```powershell
git add server-python/app/playground server-python/tests/test_playground_context.py
git commit -m "feat(playground): build read-only context bundles"
```

### Task 3: Expose Isolated Capability And Context Routes

**Files:**
- Create: `server-python/app/api/playground.py`
- Create: `server-python/tests/test_playground_api.py`
- Modify: `server-python/app/main.py`

- [ ] **Step 1: Write failing endpoint tests**

```python
# server-python/tests/test_playground_api.py
from fastapi.testclient import TestClient

from app.main import create_app


def configured_app():
    app = create_app()
    app.state.settings = type("Settings", (), {
        "playground_token_secret": "test-secret",
        "playground_token_ttl_seconds": 300,
        "playground_token_issuer": "skillhub-test",
        "playground_token_audience": "sidecar-test",
    })()
    app.state.auth_me_reader = lambda user_id: {"userId": user_id, "platformRoles": ["USER"]}
    app.state.playground_version_reader = lambda namespace, slug, version, user_id: {"version": version}
    app.state.playground_context_reader = lambda claims: {
        "skill": {"namespace": claims["namespace"], "slug": claims["slug"], "displayName": "Notes", "version": claims["version"]},
        "files": [{"path": "SKILL.md", "content": "Summarize"}],
    }
    return app


def test_capability_requires_authentication() -> None:
    response = TestClient(configured_app()).post(
        "/api/web/skills/global/notes/playground-capability",
        json={"version": "1.0.0"},
    )
    assert response.status_code == 401


def test_capability_and_context_round_trip() -> None:
    client = TestClient(configured_app())
    token_response = client.post(
        "/api/web/skills/global/notes/playground-capability",
        headers={"X-Mock-User-Id": "user-1"},
        json={"version": "1.0.0"},
    )
    token = token_response.json()["token"]

    context_response = client.get(
        "/api/web/playground/context",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert token_response.status_code == 200
    assert context_response.status_code == 200
    assert context_response.json()["files"][0]["path"] == "SKILL.md"


def test_invalid_capability_never_uses_normal_bearer_auth() -> None:
    app = configured_app()
    app.state.auth_bearer_reader = lambda token: (_ for _ in ()).throw(AssertionError("must not use API token auth"))

    response = TestClient(app).get(
        "/api/web/playground/context",
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 401
```

- [ ] **Step 2: Run and verify the routes are missing**

Run: `cd server-python; uv run pytest tests/test_playground_api.py -q`

Expected: FAIL with `404` responses.

- [ ] **Step 3: Implement the isolated router**

```python
# server-python/app/api/playground.py
import inspect

from fastapi import APIRouter, Header, HTTPException, Request

from app.auth.context import bearer_token, resolve_current_user_or_401
from app.playground.capability import CapabilityError, issue_capability, verify_capability
from app.playground.context import build_context_bundle
from app.playground.contracts import CapabilityRequest, CapabilityResponse, PlaygroundContextResponse
from app.skills.read_repository import (
    SkillResolveError,
    read_skill_detail,
    read_skill_version_detail,
    read_skill_version_file_content,
    read_skill_version_files,
)

router = APIRouter(tags=["Playground"])


@router.post("/api/web/skills/{namespace}/{slug}/playground-capability", response_model=CapabilityResponse)
async def create_playground_capability(namespace: str, slug: str, payload: CapabilityRequest, request: Request, mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"), authorization: str | None = Header(default=None, alias="Authorization")):
    settings = request.app.state.settings
    if not settings.playground_token_secret:
        raise HTTPException(status_code=503, detail="playground_disabled")
    user = await resolve_current_user_or_401(request, mock_user_id, authorization)
    user_id = str(user["userId"])
    reader = getattr(request.app.state, "playground_version_reader", None)
    try:
        if reader is not None:
            result = reader(namespace, slug, payload.version, user_id)
            if inspect.isawaitable(result):
                await result
        else:
            await read_skill_version_detail(request.app.state.db_engine, namespace, slug, payload.version, user_id)
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    token = issue_capability(
        secret=settings.playground_token_secret,
        issuer=settings.playground_token_issuer,
        audience=settings.playground_token_audience,
        subject=user_id,
        namespace=namespace,
        slug=slug,
        version=payload.version,
        ttl_seconds=settings.playground_token_ttl_seconds,
    )
    claims = verify_capability(token, secret=settings.playground_token_secret, issuer=settings.playground_token_issuer, audience=settings.playground_token_audience)
    return CapabilityResponse(token=token, expiresAt=int(claims["exp"]))


@router.get("/api/web/playground/context", response_model=PlaygroundContextResponse)
async def get_playground_context(request: Request, authorization: str | None = Header(default=None, alias="Authorization")):
    settings = request.app.state.settings
    token = bearer_token(authorization)
    if token is None or not settings.playground_token_secret:
        raise HTTPException(status_code=401, detail="invalid_playground_capability")
    try:
        claims = verify_capability(token, secret=settings.playground_token_secret, issuer=settings.playground_token_issuer, audience=settings.playground_token_audience)
    except CapabilityError as exc:
        raise HTTPException(status_code=401, detail="invalid_playground_capability") from exc
    reader = getattr(request.app.state, "playground_context_reader", None)
    if reader is not None:
        result = reader(claims)
        if inspect.isawaitable(result):
            result = await result
        return result

    namespace = str(claims["namespace"])
    slug = str(claims["slug"])
    version = str(claims["version"])
    current_user_id = str(claims["sub"])

    async def detail_reader(ns, skill_slug, user_id):
        return await read_skill_detail(request.app.state.db_engine, ns, skill_slug, user_id)

    async def files_reader(ns, skill_slug, skill_version, user_id):
        return await read_skill_version_files(request.app.state.db_engine, ns, skill_slug, skill_version, user_id)

    async def content_reader(ns, skill_slug, skill_version, path, user_id):
        return await read_skill_version_file_content(
            request.app.state.db_engine,
            settings.storage_base_path,
            ns,
            skill_slug,
            skill_version,
            path,
            user_id,
        )

    try:
        return await build_context_bundle(
            namespace=namespace,
            slug=slug,
            version=version,
            current_user_id=current_user_id,
            read_detail=detail_reader,
            read_files=files_reader,
            read_content=content_reader,
            max_bytes=settings.playground_context_max_bytes,
        )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=413, detail="playground_context_too_large") from exc
```

The fallback above revalidates both version and file access with `claims["sub"]` and never calls a download reader.

- [ ] **Step 4: Include only the new router in `create_app`**

Import `router as playground_router` and add `app.include_router(playground_router)`. Do not add startup work, health checks, shared tasks, or sidecar calls.

- [ ] **Step 5: Verify API and existing skill regressions**

Run:

```powershell
cd server-python
uv run pytest tests/test_playground_api.py tests/test_skill_detail.py tests/test_skill_file_metadata.py tests/test_skill_file_content.py tests/test_skill_download.py -q
```

Expected: all selected tests pass and download test assertions remain unchanged.

- [ ] **Step 6: Commit**

```powershell
git add server-python/app/api/playground.py server-python/app/main.py server-python/tests/test_playground_api.py
git commit -m "feat(playground): expose isolated context API"
```

### Task 4: Add Disabled-By-Default Web Runtime Configuration

**Files:**
- Modify: `web/src/api/client.ts`
- Modify: `web/src/api/client.test.ts`
- Modify: `web/src/bootstrap.ts`
- Modify: `web/runtime-config.js.template`
- Modify: `web/docker-entrypoint.d/30-runtime-config.sh`

- [ ] **Step 1: Write failing runtime-config tests**

```typescript
// append to web/src/api/client.test.ts
it('keeps playground disabled when runtime config is absent', () => {
  setMockWindow()
  expect(getPlaygroundRuntimeConfig()).toEqual({ enabled: false })
})

it('returns a normalized sidecar URL only when playground is enabled', () => {
  setMockWindow({ playgroundEnabled: 'true', playgroundBaseUrl: 'http://localhost:8091/' })
  expect(getPlaygroundRuntimeConfig()).toEqual({ enabled: true, baseUrl: 'http://localhost:8091' })
})

it('disables playground when enabled has no base URL', () => {
  setMockWindow({ playgroundEnabled: 'true', playgroundBaseUrl: '' })
  expect(getPlaygroundRuntimeConfig()).toEqual({ enabled: false })
})
```

- [ ] **Step 2: Run and verify the accessor is missing**

Run: `cd web; corepack pnpm test -- src/api/client.test.ts`

Expected: FAIL because `getPlaygroundRuntimeConfig` does not exist.

- [ ] **Step 3: Add the runtime fields and accessor**

```typescript
// web/src/api/client.ts
type RuntimeConfig = {
  // existing fields
  playgroundEnabled?: string
  playgroundBaseUrl?: string
}

export type PlaygroundRuntimeConfig = { enabled: false } | { enabled: true; baseUrl: string }

export function getPlaygroundRuntimeConfig(): PlaygroundRuntimeConfig {
  const config = getRuntimeConfig()
  const baseUrl = config.playgroundBaseUrl?.trim().replace(/\/$/, '')
  if (!parseBooleanFlag(config.playgroundEnabled) || !baseUrl) {
    return { enabled: false }
  }
  return { enabled: true, baseUrl }
}
```

Add fallback/template/entrypoint values:

```typescript
playgroundEnabled: 'false',
playgroundBaseUrl: '',
```

```javascript
playgroundEnabled: "${SKILLHUB_WEB_PLAYGROUND_ENABLED}",
playgroundBaseUrl: "${SKILLHUB_WEB_PLAYGROUND_BASE_URL}"
```

Update `envsubst` with both variables and default them to `false`/empty in the shell script.

- [ ] **Step 4: Verify and commit**

Run: `cd web; corepack pnpm test -- src/api/client.test.ts`

Expected: selected tests pass.

```powershell
git add web/src/api/client.ts web/src/api/client.test.ts web/src/bootstrap.ts web/runtime-config.js.template web/docker-entrypoint.d/30-runtime-config.sh
git commit -m "feat(playground): add web runtime flags"
```

### Task 5: Add Core And Sidecar API Clients

**Files:**
- Modify: `web/src/api/client.ts`
- Modify: `web/src/api/types.ts`
- Create: `web/src/features/playground/api.ts`
- Create: `web/src/features/playground/api.test.ts`
- Modify: `web/src/api/generated/schema.d.ts`

- [ ] **Step 1: Generate the updated backend contract**

Start the backend in a separate PowerShell process with `SKILLHUB_PLAYGROUND_TOKEN_SECRET=local-playground-secret` and wait for `http://localhost:8080/actuator/health`, then run:

```powershell
cd web
corepack pnpm run generate-api
```

Expected: `src/api/generated/schema.d.ts` contains the two `/api/web/...playground...` paths and their response schemas.

- [ ] **Step 2: Add generated-derived frontend types and failing sidecar-client tests**

```typescript
// web/src/features/playground/api.test.ts
import { afterEach, expect, it, vi } from 'vitest'
import { createSidecarSession, sendSidecarMessage } from './api'

afterEach(() => vi.unstubAllGlobals())

it('creates a session without leaking the capability into the URL', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    sessionId: 'session-1', modelKey: 'primary', skill: {}, contextFiles: [{ path: 'SKILL.md', content: 'Summarize' }],
  }), { status: 201, headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetchMock)

  await createSidecarSession('http://localhost:8091', 'capability')

  expect(fetchMock).toHaveBeenCalledWith('http://localhost:8091/v1/playground/sessions', expect.objectContaining({ method: 'POST' }))
  expect(String(fetchMock.mock.calls[0][0])).not.toContain('capability')
})

it('posts chat messages to the scoped session endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ accepted: true }), { status: 202 }))
  vi.stubGlobal('fetch', fetchMock)
  await sendSidecarMessage('http://localhost:8091', 'session-1', 'hello')
  expect(fetchMock).toHaveBeenCalledWith('http://localhost:8091/v1/playground/sessions/session-1/messages', expect.any(Object))
})
```

- [ ] **Step 3: Implement capability and sidecar clients**

```typescript
// in web/src/api/client.ts
export const playgroundCapabilityApi = {
  async create(namespace: string, slug: string, version: string): Promise<PlaygroundCapability> {
    return fetchJson(`${WEB_API_PREFIX}/skills/${encodeURIComponent(namespace)}/${encodeURIComponent(slug)}/playground-capability`, {
      method: 'POST',
      headers: await ensureCsrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ version }),
    })
  },
}
```

```typescript
// web/src/features/playground/api.ts
export type SidecarSession = {
  sessionId: string
  modelKey: string
  skill: { namespace: string; slug: string; displayName: string; version: string }
  contextFiles: Array<{ path: string; content: string }>
}

async function sidecarJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) throw new Error(`sidecar_${response.status}`)
  return response.json() as Promise<T>
}

export function createSidecarSession(baseUrl: string, capability: string): Promise<SidecarSession> {
  return sidecarJson(`${baseUrl}/v1/playground/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ productId: 'skillhub', source: { provider: 'skillhub', accessToken: capability } }),
  })
}

export function sendSidecarMessage(baseUrl: string, sessionId: string, content: string): Promise<{ accepted: boolean }> {
  return sidecarJson(`${baseUrl}/v1/playground/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }),
  })
}

export function sidecarEventsUrl(baseUrl: string, sessionId: string): string {
  return `${baseUrl}/v1/playground/sessions/${encodeURIComponent(sessionId)}/events`
}
```

- [ ] **Step 4: Verify and commit**

Run:

```powershell
cd web
corepack pnpm test -- src/api/client.test.ts src/features/playground/api.test.ts
corepack pnpm run typecheck
```

Expected: tests and typecheck pass.

```powershell
git add web/src/api web/src/features/playground
git commit -m "feat(playground): add sidecar API clients"
```

### Task 6: Add The Dedicated Playground Route And Chat UI

**Files:**
- Create: `web/src/features/playground/use-playground.ts`
- Create: `web/src/features/playground/playground-chat.tsx`
- Create: `web/src/pages/skill-playground.tsx`
- Create: `web/src/pages/skill-playground.test.tsx`
- Modify: `web/src/app/router.tsx`
- Modify: `web/src/app/router.test.ts`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh-TW.json`
- Modify: `web/src/i18n/locales/zh.json`

- [ ] **Step 1: Write failing route and page-state tests**

```typescript
// append to web/src/app/router.test.ts
it('registers the dedicated playground route', () => {
  const children = (router.routeTree.children ?? []) as Array<{ fullPath?: string }>
  expect(children.some((route) => route.fullPath === '/space/$namespace/$slug/playground')).toBe(true)
})
```

```tsx
// web/src/pages/skill-playground.test.tsx
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ namespace: 'global', slug: 'notes' }),
  Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}))
vi.mock('@/features/playground/use-playground', () => ({
  usePlayground: () => ({ state: 'unavailable', messages: [], send: vi.fn(), reset: vi.fn() }),
}))

import { SkillPlaygroundPage } from './skill-playground'

describe('SkillPlaygroundPage', () => {
  it('shows a local unavailable state without affecting navigation', () => {
    const html = renderToStaticMarkup(<SkillPlaygroundPage />)
    expect(html).toContain('playground.unavailableTitle')
    expect(html).toContain('playground.backToSkill')
  })
})
```

- [ ] **Step 2: Run and verify the page and route are missing**

Run: `cd web; corepack pnpm test -- src/app/router.test.ts src/pages/skill-playground.test.tsx`

Expected: FAIL because the route/page do not exist.

- [ ] **Step 3: Implement `usePlayground` with TanStack mutations and EventSource**

The hook must:

```typescript
type PlaygroundState = 'connecting' | 'ready' | 'unavailable' | 'expired'
type ChatMessage = { id: string; role: 'user' | 'assistant'; content: string; streaming?: boolean }
```

- create a capability, then a sidecar session;
- open `new EventSource(sidecarEventsUrl(...))` only after session creation;
- append `message.delta` data to one assistant message;
- map provider errors to `unavailable` without changing any global query state;
- close EventSource and delete the session on unmount;
- expose `send`, `reset`, session metadata, messages, and local state.

- [ ] **Step 4: Implement the split-view page**

Use an unframed two-column layout with stable tracks `minmax(240px, 320px) minmax(0, 1fr)`, collapsing to one column below `lg`. The left panel shows skill name/version, read-only badge, and file list. The right panel shows transcript, prompt textarea, icon send button (`Send` from `lucide-react`), reset icon button (`RotateCcw`), provider error state, and `Back to install` action. Do not add an IDE, file editor, upload, tool controls, model selector, or nested cards.

- [ ] **Step 5: Register the authenticated route**

```typescript
const SkillPlaygroundPage = createLazyRouteComponent(() => import('@/pages/skill-playground'), 'SkillPlaygroundPage')

const skillPlaygroundRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/space/$namespace/$slug/playground',
  beforeLoad: requireAuth,
  component: SkillPlaygroundPage,
})
```

Add it beside `skillDetailRoute` in `routeTree`.

- [ ] **Step 6: Add i18n keys and verify**

Add the same `playground.*` key set to English, Traditional Chinese, and Simplified Chinese: title, readOnly, toolsDisabled, promptPlaceholder, send, reset, unavailableTitle, unavailableDescription, expiredTitle, backToSkill, backToInstall, emptyState.

Run:

```powershell
cd web
corepack pnpm test -- src/app/router.test.ts src/pages/skill-playground.test.tsx
corepack pnpm run typecheck
corepack pnpm run lint
```

Expected: selected tests, typecheck, and lint pass.

- [ ] **Step 7: Commit**

```powershell
git add web/src/app/router.tsx web/src/app/router.test.ts web/src/features/playground web/src/pages/skill-playground.tsx web/src/pages/skill-playground.test.tsx web/src/i18n/locales
git commit -m "feat(playground): add dedicated chat route"
```

### Task 7: Add The Feature-Gated Skill Detail Entry Point

**Files:**
- Modify: `web/src/pages/skill-detail.tsx`
- Modify: `web/src/pages/skill-detail.test.tsx`

- [ ] **Step 1: Write failing visibility tests**

Add tests that mock `getPlaygroundRuntimeConfig()`:

```tsx
it('hides Try in Playground when runtime config is disabled', () => {
  runtimeConfig.playgroundEnabled = false
  expect(renderSkillDetail()).not.toContain('skillDetail.tryInPlayground')
})

it('shows Try in Playground for any visible selected skill when enabled', () => {
  runtimeConfig.playgroundEnabled = true
  expect(renderSkillDetail()).toContain('skillDetail.tryInPlayground')
})
```

- [ ] **Step 2: Run and verify the action is absent**

Run: `cd web; corepack pnpm test -- src/pages/skill-detail.test.tsx`

Expected: the enabled test fails.

- [ ] **Step 3: Add the icon action without changing detail data flow**

Read `getPlaygroundRuntimeConfig()` once during render. When enabled and `selectedVersionEntry` exists, render a `Play` icon button next to the existing download/share actions. Navigate to `/space/$namespace/$slug/playground`; anonymous users go through the existing `requireLogin` flow. Do not fetch sidecar health from the detail page.

- [ ] **Step 4: Verify and commit**

Run: `cd web; corepack pnpm test -- src/pages/skill-detail.test.tsx`

Expected: selected tests pass.

```powershell
git add web/src/pages/skill-detail.tsx web/src/pages/skill-detail.test.tsx web/src/i18n/locales
git commit -m "feat(playground): add skill detail entry point"
```

### Task 8: Prove Sidecar Failure Cannot Break SkillHub

**Files:**
- Create: `scripts/verify-playground-isolation.ps1`
- Create: `docs/backend-python-maintenance/results/2026-07-10-skill-playground-integration.md`
- Modify: `deploy/k8s/environment-variables.zh.md`

- [ ] **Step 1: Add a PowerShell smoke script that starts only SkillHub**

The script must:

1. set `SKILLHUB_WEB_PLAYGROUND_ENABLED=false` and an empty base URL;
2. start backend/web using existing repo commands;
3. assert backend health, search, skill detail, and generated web runtime config respond without a sidecar process;
4. set the web base URL to an unreachable `http://127.0.0.1:65534`, rebuild runtime config, and assert only the playground client reports unavailable;
5. stop only processes started by the script in `finally`.

- [ ] **Step 2: Document operator settings and removal procedure**

Document:

```text
SKILLHUB_WEB_PLAYGROUND_ENABLED=false
SKILLHUB_WEB_PLAYGROUND_BASE_URL=
SKILLHUB_PLAYGROUND_TOKEN_SECRET=<backend-only secret when enabled>
SKILLHUB_PLAYGROUND_TOKEN_TTL_SECONDS=300
```

State that SkillHub base manifests never deploy or probe the sidecar. Removal is: disable the two web runtime values, remove the separately deployed sidecar, and leave SkillHub schema/runtime untouched.

- [ ] **Step 3: Run the full regression gates**

Run:

```powershell
cd server-python
uv run pytest tests -q
cd ..\web
corepack pnpm test
corepack pnpm run typecheck
corepack pnpm run lint
cd ..
git diff --check
```

Expected: backend tests, 185+ frontend test files, typecheck, lint, and whitespace check all pass.

- [ ] **Step 4: Run container/config verification**

Run:

```powershell
docker build -t skillhub-server-python:playground-verify -f server-python/Dockerfile .
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config
```

Expected: all commands exit `0`; rendered base manifests contain no required sidecar workload or probe.

- [ ] **Step 5: Commit the isolation gate and result note**

```powershell
git add scripts/verify-playground-isolation.ps1 deploy/k8s/environment-variables.zh.md docs/backend-python-maintenance/results/2026-07-10-skill-playground-integration.md
git commit -m "test(playground): verify failure isolation"
```

## SkillHub Completion Gate

- Playground disabled: existing SkillHub behavior and health are unchanged.
- Playground enabled but sidecar absent: only the dedicated route is unavailable.
- Capability scope is exactly `playground:read` and expires in five minutes by default.
- Context access is revalidated using the token subject and never mutates download metrics.
- No schema migration, lifecycle state, search ranking, install behavior, readiness probe, or base deployment dependency is added.
- Full backend/frontend suites and the failure-isolation smoke pass.
