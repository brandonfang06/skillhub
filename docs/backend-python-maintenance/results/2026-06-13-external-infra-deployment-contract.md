# External Infra Deployment Contract

Date: 2026-06-13

## Scope

This milestone aligns Kubernetes deployment with the intended organization
runtime:

- The repo deploys only `frontend`, `backend-python`, and `scanner`.
- PostgreSQL, Redis, MinIO/S3, and Keycloak/OIDC are external operator-owned
  services.
- Python backend runtime now supports the Java-compatible S3/MinIO
  `SKILLHUB_STORAGE_S3_*` env names.
- Python backend runtime now supports Spring Boot style Keycloak/OIDC env names
  for cutover reuse.
- Python backend runtime now supports Java-compatible Redis env names,
  including `SPRING_DATA_REDIS_PASSWORD` and `REDIS_PASSWORD`, plus Redis
  `AUTH` and database `SELECT` during scanner/device-flow Redis operations.
- A Chinese K8s environment variable manual is available at
  `deploy/k8s/environment-variables.zh.md`.

## Implementation Notes

- Added `app.object_storage` with local and S3 adapters.
- Publish, skill download/file content, review preview/download, rerelease, and
  storage cleanup paths now route through the storage adapter boundary.
- Added `SKILLHUB_STORAGE_S3_PROXY_ENDPOINT` as a Python extension. When set,
  it is used as the effective S3 API endpoint; when empty, the backend uses
  `SKILLHUB_STORAGE_S3_ENDPOINT`.
- Added Spring-style OIDC registration parsing for env names like
  `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID` and
  `SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI`.
- Removed the `deploy/k8s/overlays/with-infra` resources and local storage PVC
  from K8s manifests.
- Redis can be configured either with the optional full `SKILLHUB_REDIS_URL`
  override or with split Java-compatible values:
  `SPRING_DATA_REDIS_HOST`, `SPRING_DATA_REDIS_PORT`,
  `SPRING_DATA_REDIS_PASSWORD`, and `SPRING_DATA_REDIS_DATABASE`.
- Release compose now starts the local Redis container with `--requirepass`
  when `REDIS_PASSWORD` is set, and the Python backend consumes the same value
  through `SPRING_DATA_REDIS_PASSWORD`.

## Verification

```text
cd server-python; .\.venv\Scripts\python.exe -m pytest tests -q
738 passed, 1 warning in 71.24s
```

```text
cd server-python; .\.venv\Scripts\python.exe -m pytest tests\test_config.py tests\test_redis_connection.py tests\test_publish_scan_consumer.py tests\test_device_auth.py -q
23 passed, 1 warning in 1.87s
```

```text
kubectl kustomize deploy\k8s\base
success
```

```text
kubectl kustomize deploy\k8s\overlays\external
success
```

```text
rg -n "StatefulSet|PersistentVolumeClaim|skillhub-storage-pvc|overlays/with-infra|with-infra|SKILLHUB_STORAGE_BASE_PATH|/actuator/health" deploy\k8s
no matches
```

## Residual Risk

- S3 behavior is covered with adapter and config tests, but this milestone did
  not connect to a real organization MinIO instance.
- Keycloak/OIDC env parsing and redirect generation are covered by tests, but
  this milestone did not perform a live Keycloak login.
