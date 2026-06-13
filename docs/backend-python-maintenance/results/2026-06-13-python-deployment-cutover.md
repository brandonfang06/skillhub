# Python Deployment Cutover Result

Date: 2026-06-13

Milestone: Post Python Cutover Hardening Milestone 9

## Scope

This milestone updated production deployment assets after the backend Python
cutover. Kubernetes and release Compose now start the Python backend, frontend,
and scanner without Spring Boot environment variables, Java backend images, or
actuator health probes.

## Changes

- Added `server-python/tests/test_deployment_cutover.py` to guard deployment
  assets against reintroducing Spring Boot env names, Java backend images, or
  `/actuator/health` probes.
- Updated `deploy/k8s/base/backend-deployment.yaml`:
  - image: `ghcr.io/iflytek/skillhub-server-python:edge`
  - container name: `backend-python`
  - Python env: `SKILLHUB_DATABASE_URL`, `SKILLHUB_REDIS_URL`,
    `SKILLHUB_STORAGE_BASE_PATH`, `SKILLHUB_SECURITY_SCANNER_BASE_URL`,
    scanner/session/auth/bootstrap/OAuth env
  - probes: `/api/v1/health`
- Updated `deploy/k8s/base/configmap.yaml` and
  `deploy/k8s/base/secret.yaml.example` to expose Python runtime inputs.
- Updated `deploy/k8s/overlays/with-infra/postgres-statefulset.yaml` to use
  `postgres-username` and `postgres-password` instead of old Spring datasource
  secret keys.
- Updated `deploy/k8s/base/kustomization.yaml` so image overrides target
  `ghcr.io/iflytek/skillhub-server-python`.
- Rewrote `deploy/k8s/README.md` around the post-cutover three-deployment
  topology: frontend, backend-python, and scanner.
- Updated `compose.release.yml` to use the Python backend image, Python runtime
  env, and `/api/v1/health`.
- Updated the maintenance plan with the completed Milestone 9 checklist.

## Verification

| Command | Result |
| --- | --- |
| `cd server-python; uv run pytest tests/test_deployment_cutover.py -q` | Red before implementation: `4 failed`; green after implementation: `4 passed`. |
| `cd server-python; uv run pytest tests -q` | Passed: `731 passed, 1 warning in 72.27s`. Warning is the existing Starlette/httpx `TestClient` deprecation. |
| `kubectl kustomize deploy\k8s\base` | Passed. |
| `kubectl kustomize deploy\k8s\overlays\with-infra` | Passed. |
| `kubectl kustomize deploy\k8s\overlays\external` | Passed. |
| `docker compose -f compose.release.yml config` | Passed. |
| `rg -n "SPRING_\|spring-datasource\|/actuator/health\|ghcr\.io/iflytek/skillhub-server(:|\})" deploy\k8s compose.release.yml` | Passed with no matches. |
| `git diff --check` | Passed; Git reported only CRLF working-copy normalization warnings. |

## Deployment Notes

- `deploy/k8s/base/secret.yaml.example` remains an example file. Operators must
  copy it to `deploy/k8s/base/secret.yaml`, fill values, and apply it manually:

```bash
kubectl create namespace skillhub
kubectl apply -n skillhub -f deploy/k8s/base/secret.yaml
kubectl apply -k deploy/k8s/overlays/with-infra/
```

- The backend service name remains `skillhub-server` to avoid changing frontend
  and ingress routing, but the workload is now the Python FastAPI backend.
- The Python backend currently uses local PVC-backed bundle storage in this
  deployment path via `SKILLHUB_STORAGE_BASE_PATH`.

## Residual Risk

- These checks validate manifest rendering and release Compose configuration,
  not a live Kubernetes cluster rollout. A real cluster smoke test should be run
  after image publication and environment-specific secret values are available.
- PostgreSQL credentials appear both as `postgres-username/password` for the
  in-cluster PostgreSQL StatefulSet and inside `database-url` for the Python
  backend. Keep them synchronized or use an external secret management pipeline
  to generate both values from the same source.
