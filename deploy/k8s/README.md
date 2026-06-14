# SkillHub Kubernetes deployment

This manifest set is for the Python cutover runtime. It deploys only the three
SkillHub workloads:

- `skillhub-web`: frontend Nginx container
- `skillhub-server`: Python FastAPI backend
- `skillhub-scanner`: Python scanner service

PostgreSQL, Redis, MinIO/S3, and Keycloak/OIDC are external dependencies. Point
the ConfigMap and Secret values at the services your organization already runs.

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
  plain/
    backend.yaml
    frontend.yaml
    scanner.yaml
  overlays/
    external/
  environment-variables.zh.md
```

## Runtime

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

The Java backend is not part of this Kubernetes runtime. Spring-compatible
environment names are intentionally kept where they are part of the existing
deployment contract, for example Redis and OIDC.

## Configure

Create the namespace:

```bash
kubectl create namespace skillhub
```

Create a Secret from the example:

```bash
cd deploy/k8s/base
cp secret.yaml.example secret.yaml
```

Edit these required Secret values:

| Key | Meaning |
| --- | --- |
| `database-url` | Feeds `SKILLHUB_DATABASE_URL`. PostgreSQL SQLAlchemy async URL, for example `postgresql+asyncpg://skillhub:password@postgres.example.internal:5432/skillhub`. URL-encode special characters. |
| `redis-password` | Feeds `SPRING_DATA_REDIS_PASSWORD`. Leave empty only when Redis has no password. |
| `redis-url` | Feeds optional `SKILLHUB_REDIS_URL`. If non-empty, it wins over `redis-host`, `redis-port`, `redis-database`, and `redis-password`. |
| `storage-s3-access-key` | Feeds `SKILLHUB_STORAGE_S3_ACCESS_KEY`. MinIO/S3 access key. |
| `storage-s3-secret-key` | Feeds `SKILLHUB_STORAGE_S3_SECRET_KEY`. MinIO/S3 secret key. |
| `oauth2-keycloak-client-id` | Feeds `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID`. Leave empty until the provider is ready. |
| `oauth2-keycloak-client-secret` | Feeds `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_SECRET`. Leave empty until the provider is ready. |
| `bootstrap-admin-password` | Feeds `BOOTSTRAP_ADMIN_PASSWORD`. Rotate or disable after first setup. |

Edit these common ConfigMap values:

| Key | Pod env | Meaning |
| --- | --- | --- |
| `redis-host` | `SPRING_DATA_REDIS_HOST` | External Redis hostname. |
| `redis-port` | `SPRING_DATA_REDIS_PORT` | External Redis port. |
| `redis-database` | `SPRING_DATA_REDIS_DATABASE` | Redis logical database number. |
| `storage-s3-endpoint` | `SKILLHUB_STORAGE_S3_ENDPOINT` | MinIO/S3 API endpoint. |
| `storage-s3-proxy-endpoint` | `SKILLHUB_STORAGE_S3_PROXY_ENDPOINT` | Optional proxy endpoint used by the backend when it must reach MinIO through a proxy. |
| `storage-s3-public-endpoint` | `SKILLHUB_STORAGE_S3_PUBLIC_ENDPOINT` | Optional public endpoint used for generated object URLs. |
| `storage-s3-bucket` | `SKILLHUB_STORAGE_S3_BUCKET` | Bucket for skill package bundles. |
| `public-base-url` | `SKILLHUB_PUBLIC_BASE_URL` | External HTTPS origin used for OAuth callbacks and generated links. |
| `oauth2-keycloak-issuer-uri` | `SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI` | Keycloak realm issuer URI. |
| `security-scanner-base-url` | `SKILLHUB_SECURITY_SCANNER_BASE_URL` | Scanner service URL, usually `http://skillhub-scanner:8000`. |

For the full environment variable manual, see
[environment-variables.zh.md](environment-variables.zh.md).

## Apply

```bash
kubectl apply -n skillhub -f deploy/k8s/base/secret.yaml
kubectl apply -k deploy/k8s/overlays/external/
kubectl wait --for=condition=ready pod --all -n skillhub --timeout=300s
```

For a non-kustomize workflow, edit `deploy/k8s/plain/backend.yaml` and apply the
plain workload files directly:

```bash
kubectl -n skillhub apply -f deploy/k8s/plain/backend.yaml
kubectl -n skillhub apply -f deploy/k8s/plain/scanner.yaml
kubectl -n skillhub apply -f deploy/k8s/plain/frontend.yaml
```

## Verify

Render manifests before applying:

```bash
kubectl kustomize deploy/k8s/base
kubectl kustomize deploy/k8s/overlays/external
kubectl apply --dry-run=client --validate=false -f deploy/k8s/plain/
```

Check pods and services:

```bash
kubectl get pods -n skillhub
kubectl get svc -n skillhub
```

Port-forward:

```bash
kubectl port-forward svc/skillhub-web -n skillhub 8080:80
kubectl port-forward svc/skillhub-server -n skillhub 8081:8080
```

Health checks:

```bash
curl http://localhost:8081/api/v1/health
curl http://localhost:8080/api/v1/health
```

## Images

| Component | Default image |
| --- | --- |
| Frontend | `ghcr.io/iflytek/skillhub-web:edge` |
| Backend Python | `ghcr.io/iflytek/skillhub-server-python:edge` |
| Scanner | `ghcr.io/iflytek/skillhub-scanner:edge` |

## Cleanup

```bash
kubectl delete -k deploy/k8s/overlays/external/
kubectl delete namespace skillhub
```
