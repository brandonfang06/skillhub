# SkillHub Kubernetes Deployment

This directory contains Kubernetes manifests for running SkillHub after the
Python backend cutover. The production shape is three application deployments:
frontend, backend-python, and scanner.

## Layout

```text
deploy/k8s/
  base/
    backend-deployment.yaml
    configmap.yaml
    frontend-deployment.yaml
    ingress.yaml
    kustomization.yaml
    scanner-deployment.yaml
    secret.yaml.example
    services.yaml
  overlays/
    external/
    with-infra/
```

Use `overlays/with-infra` when the cluster should also run PostgreSQL and Redis.
Use `overlays/external` when PostgreSQL and Redis are provided outside this
manifest set.

## Runtime Topology

```text
Ingress
  /api, /oauth2, /.well-known -> skillhub-server:8080
  /                         -> skillhub-web:80

skillhub-web
  Nginx static frontend
  SKILLHUB_API_UPSTREAM=http://skillhub-server:8080

skillhub-server
  Python FastAPI backend
  image ghcr.io/iflytek/skillhub-server-python
  health /api/v1/health

skillhub-scanner
  Python scanner service
  health /health
```

The Java backend is not part of the default Kubernetes runtime. Java remains a
read-only reference for hybrid local verification only.

## Required Configuration

Create a namespace:

```bash
kubectl create namespace skillhub
```

Create a secret from the example:

```bash
cd deploy/k8s/base
cp secret.yaml.example secret.yaml
```

Apply the secret before applying an overlay:

```bash
kubectl apply -n skillhub -f deploy/k8s/base/secret.yaml
```

Required secret keys:

| Key | Purpose |
| --- | --- |
| `database-url` | SQLAlchemy async PostgreSQL URL for the Python backend, for example `postgresql+asyncpg://skillhub:password@postgres:5432/skillhub`. URL-encode special characters. |
| `bootstrap-admin-password` | Optional bootstrap admin password when bootstrap is enabled. |
| `oauth2-github-client-id` | Optional GitHub OAuth client ID. |
| `oauth2-github-client-secret` | Optional GitHub OAuth client secret. |
| `oauth2-gitlab-client-id` | Optional GitLab OAuth client ID. |
| `oauth2-gitlab-client-secret` | Optional GitLab OAuth client secret. |
| `skill-scanner-llm-api-key` | Optional scanner LLM API key. |
| `skill-scanner-llm-base-url` | Optional scanner LLM base URL. |
| `skill-scanner-llm-model` | Optional scanner LLM model. |

Important ConfigMap keys:

| Key | Default | Purpose |
| --- | --- | --- |
| `redis-url` | `redis://redis:6379` | Redis URL for sessions, idempotency, and scan streams. |
| `storage-base-path` | `/var/lib/skillhub/storage` | Local bundle storage path mounted from `skillhub-storage-pvc`. |
| `public-base-url` | empty | External HTTPS origin used for OAuth callback construction. |
| `security-scanner-enabled` | `true` | Enables scanner integration in the Python backend. |
| `security-scanner-base-url` | `http://skillhub-scanner:8000` | Scanner service URL. |
| `security-scanner-mode` | `upload` | Scanner handoff mode. |
| `scan-consumer-enabled` | `false` | Enables the Python scan consumer worker loop when configured. |
| `session-cookie-secure` | `false` | Set to `true` behind HTTPS ingress. |
| `auth-direct-enabled` | `false` | Enables direct password auth method exposure. |
| `auth-session-bootstrap-enabled` | `false` | Enables local/dev session bootstrap method exposure. |

The backend deployment maps those keys to Python runtime environment variables:

| Pod environment variable | Source |
| --- | --- |
| `SKILLHUB_DATABASE_URL` | `skillhub-secret/database-url` |
| `SKILLHUB_REDIS_URL` | `skillhub-config/redis-url` |
| `SKILLHUB_STORAGE_BASE_PATH` | `skillhub-config/storage-base-path` |
| `SKILLHUB_SECURITY_SCANNER_BASE_URL` | `skillhub-config/security-scanner-base-url` |
| `SKILLHUB_SECURITY_SCANNER_ENABLED` | `skillhub-config/security-scanner-enabled` |
| `SKILLHUB_SESSION_COOKIE_SECURE` | `skillhub-config/session-cookie-secure` |

## Deploy With In-Cluster PostgreSQL And Redis

```bash
kubectl apply -n skillhub -f deploy/k8s/base/secret.yaml
kubectl apply -k deploy/k8s/overlays/with-infra/
kubectl wait --for=condition=ready pod --all -n skillhub --timeout=300s
```

The `with-infra` overlay includes PostgreSQL and Redis stateful workloads. The
base backend secret example already points `database-url` at
`postgres:5432/skillhub`.

## Deploy With External PostgreSQL And Redis

1. Edit `deploy/k8s/base/secret.yaml` and set `database-url` to the external
   PostgreSQL URL.
2. Edit `deploy/k8s/base/configmap.yaml` and set `redis-url` to the external
   Redis URL.
3. Apply the external overlay:

```bash
kubectl apply -n skillhub -f deploy/k8s/base/secret.yaml
kubectl apply -k deploy/k8s/overlays/external/
kubectl wait --for=condition=ready pod --all -n skillhub --timeout=300s
```

## Verify

Render manifests before applying:

```bash
kubectl kustomize deploy/k8s/base
kubectl kustomize deploy/k8s/overlays/with-infra
```

Check pods and services:

```bash
kubectl get pods -n skillhub
kubectl get svc -n skillhub
```

Port-forward frontend and backend:

```bash
kubectl port-forward svc/skillhub-web -n skillhub 8080:80
kubectl port-forward svc/skillhub-server -n skillhub 8081:8080
```

Health checks:

```bash
curl http://localhost:8081/api/v1/health
curl http://localhost:8080/api/v1/health
```

The first command hits the backend service directly. The second command hits the
frontend Nginx proxy and should still reach the Python backend.

## Images

| Component | Default image |
| --- | --- |
| Frontend | `ghcr.io/iflytek/skillhub-web:edge` |
| Backend Python | `ghcr.io/iflytek/skillhub-server-python:edge` |
| Scanner | `ghcr.io/iflytek/skillhub-scanner:edge` |
| PostgreSQL | `postgres:16-alpine` |
| Redis | `redis:7-alpine` |

## Storage

The Python backend currently uses local filesystem bundle storage in this
deployment path. The base manifest mounts `skillhub-storage-pvc` at
`/var/lib/skillhub/storage` and passes that path through
`SKILLHUB_STORAGE_BASE_PATH`.

## Cleanup

```bash
kubectl delete -k deploy/k8s/overlays/with-infra/
kubectl delete namespace skillhub
```
