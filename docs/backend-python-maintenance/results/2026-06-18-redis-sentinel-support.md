# Redis Sentinel Support

Date: 2026-06-18

## Scope

The Python backend now supports Redis Sentinel for Redis-backed scanner queues,
device auth, and session/runtime Redis access. This closes the cutover gap where
the Python backend used direct single-node Redis connections and could write to
a read-only replica when Kubernetes service discovery pointed at a replica pod.

## Runtime Changes

- Added `redis>=8.0.0` and a shared async Redis adapter in
  `server-python/app/core/redis.py`.
- `SKILLHUB_REDIS_URL` remains highest priority. If it is non-empty, backend
  uses single-node Redis URL behavior.
- If `SKILLHUB_REDIS_URL` is empty and Sentinel master/nodes are configured,
  backend uses Redis Sentinel master discovery.
- Scanner stream publisher/consumer, rerelease scan publish, device auth, and
  FastAPI lifespan now share the app-level Redis client.
- Split single-node Redis env with `SPRING_DATA_REDIS_SSL_ENABLED=true` now
  builds a `rediss://` URL.
- Split single-node Redis env with `SPRING_DATA_REDIS_USERNAME` now includes
  the ACL username in the generated Redis URL.

## Supported Env Names

Sentinel:

```text
SPRING_DATA_REDIS_SENTINEL_MASTER
SPRING_DATA_REDIS_SENTINEL_NODES
SPRING_DATA_REDIS_SENTINEL_USERNAME
SPRING_DATA_REDIS_SENTINEL_PASSWORD
SKILLHUB_REDIS_SENTINEL_MASTER
SKILLHUB_REDIS_SENTINEL_NODES
SKILLHUB_REDIS_SENTINEL_USERNAME
SKILLHUB_REDIS_SENTINEL_PASSWORD
```

Shared Redis settings:

```text
SPRING_DATA_REDIS_USERNAME
SPRING_DATA_REDIS_PASSWORD
SPRING_DATA_REDIS_DATABASE
SPRING_DATA_REDIS_SSL_ENABLED
SPRING_DATA_REDIS_CONNECT_TIMEOUT
SPRING_DATA_REDIS_TIMEOUT
REDIS_USERNAME
REDIS_PASSWORD
REDIS_DATABASE
```

## Kubernetes Updates

- Kustomize base and plain backend manifests now expose optional Sentinel keys.
- `deploy/k8s/environment-variables.zh.md` documents single-node vs Sentinel
  priority and Bitnami Sentinel deployment notes.
- `deploy/k8s/README.md` documents Redis/Sentinel env compatibility and
  operator-facing ConfigMap/Secret keys.

## Bitnami Redis Sentinel Notes

Bitnami's Redis chart documents that with `architecture=replication` and
`sentinel.enabled=true`, writers should query Sentinel for the current master.
The chart service exposes Redis read-only traffic on `6379` and Sentinel on
`26379`. See:

- https://hub.docker.com/r/bitnamicharts/redis
- https://github.com/bitnami/charts/blob/main/bitnami/redis/values.yaml

For SkillHub:

```text
SKILLHUB_REDIS_URL=
SPRING_DATA_REDIS_SENTINEL_MASTER=mymaster
SPRING_DATA_REDIS_SENTINEL_NODES=<bitnami-release>-redis:26379
SPRING_DATA_REDIS_PASSWORD=<redis password>
SPRING_DATA_REDIS_SENTINEL_PASSWORD=<sentinel password if auth.sentinel=true>
SPRING_DATA_REDIS_DATABASE=0
```

If using explicit Pod DNS instead of the service, confirm names with:

```powershell
kubectl get svc,endpoints -n <redis-namespace>
```

Then use entries such as:

```text
<release>-redis-node-0.<release>-redis-headless.<namespace>.svc.cluster.local:26379
```

## Verification

Backend tests:

```powershell
cd server-python
uv run pytest tests -q
```

Result:

```text
778 passed, 1 warning in 57.58s
```

Focused config/deployment tests after documentation updates:

```powershell
cd server-python
uv run pytest tests/test_config.py tests/test_redis_client.py tests/test_deployment_cutover.py -q
```

Result:

```text
30 passed in 0.17s
```

Manifest and packaging checks:

```powershell
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config
docker build -t skillhub-server-python:verify -f server-python\Dockerfile .
git diff --check
```

Results:

- `kubectl kustomize deploy\k8s\base`: rendered successfully.
- `docker compose ... config`: rendered successfully.
- `docker build ...`: completed successfully with `redis==8.0.0` installed.
- `git diff --check`: no whitespace errors; only Windows LF-to-CRLF warnings.

Plain YAML offline parse:

```powershell
server-python\.venv\Scripts\python -
```

Parsed:

```text
deploy\k8s\plain\backend\config.yaml
deploy\k8s\plain\backend\service.yaml
deploy\k8s\plain\backend\deployment.yaml
deploy\k8s\plain\backend\secret.yaml.example
deploy\k8s\base\configmap.yaml
deploy\k8s\base\backend-deployment.yaml
deploy\k8s\base\secret.yaml.example
```

## Limitation

There is no local Redis Sentinel Docker fixture in this repository yet, so this
milestone verifies Sentinel behavior through config parsing, redis-py
constructor tests, call-site injection tests, full backend regression tests, and
deployment rendering. A future live failover smoke test should start a real
Sentinel topology, write to the stream, fail over, and write again.
