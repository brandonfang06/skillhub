# Redis Sentinel Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Python backend support for Redis Sentinel so deployments that previously worked with the Java Redisson/Spring Boot Sentinel configuration can cut over without hitting read-only replica writes.

**Architecture:** Replace direct raw TCP RESP connection ownership with a small Redis adapter that can create either a single-node client or a Sentinel master client. Keep Java-compatible `SPRING_DATA_REDIS_*` and `SPRING_DATA_REDIS_SENTINEL_*` environment variables, preserve existing `SKILLHUB_REDIS_URL` single-node behavior, and route scanner stream publishing/consuming plus device auth through the adapter.

**Tech Stack:** FastAPI lifespan, redis-py asyncio client, Redis Sentinel, pytest, Kubernetes ConfigMap/Secret manifests.

---

## Current Gap

The Java backend recently supported scanner Redis Stream Sentinel through Redisson config:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/config/RedissonConfig.java`
- Upstream commit evidence: `0fcc40cd fix(scanner): support redis sentinel in redisson config (#154)`

Current Python backend only supports single-node `redis://` targets through raw TCP helpers:

- `server-python/app/publish/scanner_handoff.py`
- `server-python/app/publish/scan_consumer.py`
- `server-python/app/auth/device.py`

This cannot discover the current Sentinel master and can write to a replica when the configured Kubernetes service load-balances across Redis pods.

## Environment Contract

### Existing Env To Preserve

- `SKILLHUB_REDIS_URL`
- `SPRING_DATA_REDIS_HOST`
- `SPRING_DATA_REDIS_PORT`
- `SPRING_DATA_REDIS_PASSWORD`
- `SPRING_DATA_REDIS_DATABASE`
- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_PASSWORD`
- `REDIS_DATABASE`

### New Sentinel Env To Add

Support Java/Spring style first:

- `SPRING_DATA_REDIS_SENTINEL_MASTER`
- `SPRING_DATA_REDIS_SENTINEL_NODES`

Support Python-native aliases for operator clarity:

- `SKILLHUB_REDIS_SENTINEL_MASTER`
- `SKILLHUB_REDIS_SENTINEL_NODES`

Optional shared Redis settings:

- `SPRING_DATA_REDIS_USERNAME`
- `SPRING_DATA_REDIS_PASSWORD`
- `SPRING_DATA_REDIS_DATABASE`
- `SPRING_DATA_REDIS_SSL_ENABLED`
- `SPRING_DATA_REDIS_CONNECT_TIMEOUT`
- `SPRING_DATA_REDIS_TIMEOUT`

`SKILLHUB_REDIS_URL` remains highest priority. If it is non-empty, Python uses single-node URL behavior and ignores Sentinel settings. If `SKILLHUB_REDIS_URL` is empty and Sentinel master/nodes are present, Python uses Sentinel. Otherwise it falls back to host/port/password/database.

## Files To Change

### Backend Runtime

- Modify: `server-python/pyproject.toml`
  - Add the Redis client dependency through `uv add redis`.
- Modify: `server-python/uv.lock`
  - Lock the resolved redis-py dependency.
- Modify: `server-python/app/core/config.py`
  - Add structured Redis settings instead of only `redis_url`.
  - Preserve `settings.redis_url` for existing callers during the first refactor.
  - Add fields for `redis_mode`, `redis_sentinel_master`, `redis_sentinel_nodes`, `redis_username`, `redis_password`, `redis_database`, `redis_ssl_enabled`, and timeout values.
- Create: `server-python/app/core/redis.py`
  - Own Redis client construction.
  - Build a single-node `redis.asyncio.Redis.from_url(...)` client when using `SKILLHUB_REDIS_URL`.
  - Build a Sentinel master client when Sentinel settings exist.
  - Expose a small protocol/wrapper with the operations the app actually needs: `execute`, `get`, `set`, `set_if_absent`, `setex`, `delete`, `aclose`.
- Modify: `server-python/app/main.py`
  - Create `app.state.redis_client` during lifespan startup.
  - Close `app.state.redis_client` during shutdown.
  - Pass the same Redis client into scan consumer daemon construction.

### Redis Call Sites

- Modify: `server-python/app/publish/scanner_handoff.py`
  - Stop opening raw TCP connections for scanner task publishing.
  - Keep `build_scan_stream_fields`.
  - Change `RedisScanTaskPublisher` to accept a Redis command client or factory.
  - Use `xadd` or generic `execute_command("XADD", ...)`.
- Modify: `server-python/app/publish/scan_consumer.py`
  - Change `RedisStreamClient` to use the shared Redis command client.
  - Keep parsing logic for `XREADGROUP`, `XAUTOCLAIM`, and stream messages.
  - Remove direct dependency on `open_redis_connection`.
- Modify: `server-python/app/publish/scan_daemon.py`
  - Accept a Redis client from app startup instead of constructing from `settings.redis_url`.
- Modify: `server-python/app/api/publish.py`
  - Build `RedisScanTaskPublisher` from `request.app.state.redis_client`.
- Modify: `server-python/app/api/lifecycle.py`
  - Build `RedisScanTaskPublisher` from `request.app.state.redis_client` for rerelease.
- Modify: `server-python/app/auth/device.py`
  - Change `RedisDeviceStore` to use the shared Redis client.
  - Keep the `DeviceRedis` protocol so tests can still inject fakes.
- Modify: `server-python/app/api/device_auth.py`
  - Construct `RedisDeviceStore(request.app.state.redis_client)` instead of `RedisDeviceStore(settings.redis_url)`.
- Modify: `server-python/app/auth/session.py`
  - Keep existing `RedisSessionStore` shape; it can use the new `app.state.redis_client`.

### Tests

- Modify: `server-python/tests/test_config.py`
  - Add tests for Java-compatible Sentinel env parsing.
  - Assert `SKILLHUB_REDIS_URL` wins over Sentinel env.
  - Assert Sentinel mode wins over host/port when URL is empty.
- Create: `server-python/tests/test_redis_client.py`
  - Unit-test single-node client creation without connecting to real Redis by monkeypatching `redis.asyncio.Redis.from_url`.
  - Unit-test Sentinel client creation by monkeypatching `redis.asyncio.sentinel.Sentinel`.
  - Assert Sentinel nodes parse comma-separated values and trim whitespace.
  - Assert password, username, database, SSL, and timeouts are passed through.
- Modify: `server-python/tests/test_redis_connection.py`
  - Replace or narrow raw TCP parser tests. If raw helpers are removed, delete tests that only cover removed implementation details.
- Modify: `server-python/tests/test_publish_scan_consumer.py`
  - Keep fake Redis stream client tests, but align fakes with the new command-client interface.
- Modify: `server-python/tests/test_publish_scan_daemon.py`
  - Assert the daemon receives the shared Redis client and does not create a separate raw TCP connection.
- Modify: `server-python/tests/test_device_auth.py`
  - Keep behavior tests; add a route-level test that `RedisDeviceStore` is created from app state client.
- Modify: `server-python/tests/test_deployment_cutover.py`
  - Assert Sentinel ConfigMap/Secret keys and env mappings exist.

### Deployment And Docs

- Modify: `deploy/k8s/base/configmap.yaml`
  - Add optional keys:
    - `redis-sentinel-master`
    - `redis-sentinel-nodes`
    - `redis-ssl-enabled`
    - `redis-connect-timeout`
    - `redis-timeout`
- Modify: `deploy/k8s/base/secret.yaml.example`
  - Keep `redis-password`.
  - Add optional `redis-username` if ACL username is needed.
- Modify: `deploy/k8s/base/backend-deployment.yaml`
  - Map ConfigMap/Secret keys to:
    - `SPRING_DATA_REDIS_SENTINEL_MASTER`
    - `SPRING_DATA_REDIS_SENTINEL_NODES`
    - `SPRING_DATA_REDIS_USERNAME`
    - `SPRING_DATA_REDIS_SSL_ENABLED`
    - `SPRING_DATA_REDIS_CONNECT_TIMEOUT`
    - `SPRING_DATA_REDIS_TIMEOUT`
- Modify: `deploy/k8s/plain/backend/config.yaml`
  - Add the same optional Sentinel keys.
- Modify: `deploy/k8s/plain/backend/secret.yaml.example`
  - Add optional `redis-username`.
- Modify: `deploy/k8s/plain/backend/deployment.yaml`
  - Add the same env mappings as base.
- Modify: `deploy/k8s/environment-variables.zh.md`
  - Document single-node vs Sentinel configuration.
  - State that `SKILLHUB_REDIS_URL` disables Sentinel discovery because it is an explicit single-node URL.
  - Provide a Kubernetes example using Sentinel master/nodes.
- Modify: `deploy/k8s/README.md`
  - Mention Redis Sentinel is supported by Python backend through Spring-compatible env names.
- Create: `docs/backend-python-maintenance/results/YYYY-MM-DD-redis-sentinel-support.md`
  - Record implementation, verification commands, and remaining limitations.

## Task 1: Config Contract

**Files:**
- Modify: `server-python/app/core/config.py`
- Modify: `server-python/tests/test_config.py`

- [ ] **Step 1: Add failing config tests**

Add tests that prove these cases:

```python
def test_redis_sentinel_config_uses_spring_env_names(monkeypatch):
    monkeypatch.delenv("SKILLHUB_REDIS_URL", raising=False)
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_MASTER", "mymaster")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_NODES", "redis-sentinel-1:26379, redis-sentinel-2:26379")
    monkeypatch.setenv("SPRING_DATA_REDIS_PASSWORD", "secret")
    monkeypatch.setenv("SPRING_DATA_REDIS_DATABASE", "3")

    settings = get_settings()

    assert settings.redis_mode == "sentinel"
    assert settings.redis_sentinel_master == "mymaster"
    assert settings.redis_sentinel_nodes == ["redis-sentinel-1:26379", "redis-sentinel-2:26379"]
    assert settings.redis_password == "secret"
    assert settings.redis_database == 3
```

```python
def test_explicit_redis_url_wins_over_sentinel_env(monkeypatch):
    monkeypatch.setenv("SKILLHUB_REDIS_URL", "redis://redis.single:6379/0")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_MASTER", "mymaster")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_NODES", "redis-sentinel-1:26379")

    settings = get_settings()

    assert settings.redis_mode == "single"
    assert settings.redis_url == "redis://redis.single:6379/0"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
cd server-python
uv run pytest tests/test_config.py -q
```

Expected: FAIL because `Settings` has no Sentinel fields.

- [ ] **Step 3: Implement minimal settings support**

Add dataclass fields, helper parsing functions, and mode resolution in `app/core/config.py`.

- [ ] **Step 4: Re-run config tests**

Run:

```powershell
cd server-python
uv run pytest tests/test_config.py -q
```

Expected: PASS.

## Task 2: Redis Client Adapter

**Files:**
- Modify: `server-python/pyproject.toml`
- Modify: `server-python/uv.lock`
- Create: `server-python/app/core/redis.py`
- Create: `server-python/tests/test_redis_client.py`

- [ ] **Step 1: Add dependency**

Run:

```powershell
cd server-python
uv add redis
```

- [ ] **Step 2: Add failing adapter tests**

Test single-node and Sentinel construction by monkeypatching redis-py constructors. Do not require a real Redis instance for these unit tests.

- [ ] **Step 3: Implement adapter**

Implement `create_redis_client(settings)` and a small async wrapper that exposes only operations used by SkillHub.

- [ ] **Step 4: Verify adapter tests**

Run:

```powershell
cd server-python
uv run pytest tests/test_redis_client.py tests/test_config.py -q
```

Expected: PASS.

## Task 3: Replace Raw TCP Redis Usage

**Files:**
- Modify: `server-python/app/publish/scanner_handoff.py`
- Modify: `server-python/app/publish/scan_consumer.py`
- Modify: `server-python/app/publish/scan_daemon.py`
- Modify: `server-python/app/auth/device.py`
- Modify: `server-python/app/api/device_auth.py`
- Modify: `server-python/app/api/publish.py`
- Modify: `server-python/app/api/lifecycle.py`
- Modify tests listed in the Tests section.

- [ ] **Step 1: Add failing tests for shared-client injection**

Add tests proving:

- scan publisher uses the injected Redis client;
- scan daemon receives the app-level Redis client;
- device auth route uses `app.state.redis_client`.

- [ ] **Step 2: Refactor call sites**

Replace `parse_redis_target(...)` and `open_redis_connection(...)` usage with the adapter. Preserve command semantics:

- `XADD`
- `XGROUP CREATE ... MKSTREAM`
- `XREADGROUP`
- `XAUTOCLAIM`
- `XACK`
- `GET`
- `SET ... EX`
- `SET ... NX EX`
- `DEL`
- `SETEX`

- [ ] **Step 3: Keep protocol boundaries**

Keep existing fake-friendly protocols where possible. Tests should not need a live Redis except for explicit smoke gates.

- [ ] **Step 4: Verify focused tests**

Run:

```powershell
cd server-python
uv run pytest tests/test_publish_scan_consumer.py tests/test_publish_scan_daemon.py tests/test_device_auth.py tests/test_session_auth.py tests/test_redis_client.py -q
```

Expected: PASS.

## Task 4: Lifespan Wiring

**Files:**
- Modify: `server-python/app/main.py`
- Modify: `server-python/tests/test_publish_scan_daemon.py` or add a focused lifespan test if a suitable pattern exists.

- [ ] **Step 1: Create Redis client on startup**

In FastAPI lifespan, create `app.state.redis_client = create_redis_client(settings)`.

- [ ] **Step 2: Reuse client**

Pass `app.state.redis_client` to the scan consumer daemon and leave session/device auth to read from `app.state`.

- [ ] **Step 3: Close client on shutdown**

Call `await app.state.redis_client.aclose()` during shutdown after daemon shutdown.

- [ ] **Step 4: Verify lifecycle behavior**

Run:

```powershell
cd server-python
uv run pytest tests/test_publish_scan_daemon.py tests/test_session_auth.py -q
```

Expected: PASS.

## Task 5: Deployment Contract

**Files:**
- Modify: `deploy/k8s/base/configmap.yaml`
- Modify: `deploy/k8s/base/secret.yaml.example`
- Modify: `deploy/k8s/base/backend-deployment.yaml`
- Modify: `deploy/k8s/plain/backend/config.yaml`
- Modify: `deploy/k8s/plain/backend/secret.yaml.example`
- Modify: `deploy/k8s/plain/backend/deployment.yaml`
- Modify: `deploy/k8s/environment-variables.zh.md`
- Modify: `deploy/k8s/README.md`
- Modify: `server-python/tests/test_deployment_cutover.py`

- [ ] **Step 1: Add deployment tests**

Extend `test_deployment_cutover.py` to assert these env names exist:

- `SPRING_DATA_REDIS_SENTINEL_MASTER`
- `SPRING_DATA_REDIS_SENTINEL_NODES`
- `SPRING_DATA_REDIS_USERNAME`
- `SPRING_DATA_REDIS_SSL_ENABLED`

- [ ] **Step 2: Add K8s mapping**

Add ConfigMap/Secret keys and env mappings. Keep all Sentinel keys optional so single-node deployments keep working.

- [ ] **Step 3: Update Chinese deployment manual**

Document examples:

```env
SPRING_DATA_REDIS_SENTINEL_MASTER=mymaster
SPRING_DATA_REDIS_SENTINEL_NODES=redis-sentinel-1:26379,redis-sentinel-2:26379,redis-sentinel-3:26379
SPRING_DATA_REDIS_PASSWORD=change-me
SPRING_DATA_REDIS_DATABASE=0
```

- [ ] **Step 4: Verify deployment rendering**

Run:

```powershell
kubectl kustomize deploy/k8s/base
kubectl apply --dry-run=client --validate=false -f deploy/k8s/plain/backend/
cd server-python
uv run pytest tests/test_deployment_cutover.py -q
```

Expected: PASS.

## Task 6: Live Verification

**Files:**
- Optional modify: `scripts/dev-hybrid.ps1`
- Create: `docs/backend-python-maintenance/results/YYYY-MM-DD-redis-sentinel-support.md`

- [ ] **Step 1: Unit verification**

Run:

```powershell
cd server-python
uv run pytest tests -q
```

Expected: all backend tests pass.

- [ ] **Step 2: Local single-node regression**

Run current local compose Redis flow and verify scanner publish/consume still works:

```powershell
docker compose -p skillhub up -d --wait redis
cd server-python
uv run pytest tests/test_publish_scan_consumer.py tests/test_device_auth.py -q
```

Expected: PASS.

- [ ] **Step 3: Sentinel live gate if infra is available**

If a Sentinel test fixture is added later, verify failover by writing to stream, promoting a new master, and writing again. This can be a follow-up if the current repo does not yet have Sentinel Docker compose.

- [ ] **Step 4: Record result note**

Create the result note with:

- changed files;
- env names;
- single-node regression evidence;
- Sentinel unit-test evidence;
- any missing live Sentinel infra evidence.

## Non-Goals

- Redis Cluster slot routing.
- Lua script migrations.
- Redis-backed notification SSE fanout.
- Changing scanner HTTP behavior.
- Changing public API behavior.
