# SkillHub Python Backend Environment Variables

This file is the backend-owned env var checklist for deploying `server-python/`.
It lists the runtime env var names consumed by the Python backend process. The
Kubernetes manifests may use shorter ConfigMap or Secret keys, but the
Deployment must inject the final names listed here into the backend container.

For full Kubernetes examples, see `deploy/k8s/environment-variables.zh.md`.

## Required For Organization Kubernetes Deployment

| Env var | Source | Example | Notes |
| --- | --- | --- | --- |
| `SKILLHUB_DATABASE_URL` | Secret | `postgresql+asyncpg://skillhub:change-me@postgres.example.internal:5432/skillhub` | Preferred Python backend database URL. |
| `SKILLHUB_STORAGE_PROVIDER` | ConfigMap | `s3` | Use `s3` for MinIO/S3. |
| `SKILLHUB_STORAGE_S3_ENDPOINT` | ConfigMap | `http://minio.example.internal:9000` | Canonical MinIO/S3 endpoint. |
| `SKILLHUB_STORAGE_S3_BUCKET` | ConfigMap | `skillhub-packages` | Bucket for skill package objects. |
| `SKILLHUB_STORAGE_S3_ACCESS_KEY` | Secret | `skillhub` | S3 access key, if your platform requires static credentials. |
| `SKILLHUB_STORAGE_S3_SECRET_KEY` | Secret | `change-me` | S3 secret key, if your platform requires static credentials. |
| `SKILLHUB_STORAGE_S3_REGION` | ConfigMap | `us-east-1` | MinIO commonly accepts `us-east-1`. |
| `SKILLHUB_STORAGE_S3_FORCE_PATH_STYLE` | ConfigMap | `true` | Usually `true` for MinIO. |
| `SKILLHUB_SECURITY_SCANNER_BASE_URL` | ConfigMap | `http://skillhub-scanner:8000` | Backend-to-scanner service URL. |
| `SKILLHUB_SECURITY_SCANNER_MODE` | ConfigMap | `upload` | Keep `upload` for the current scanner API. |

## Publish Package Policy

| Env var | Source | Default | Notes |
| --- | --- | --- | --- |
| `SKILLHUB_PUBLISH_ALLOWED_FILE_EXTENSIONS` | ConfigMap | unset | Optional Java-compatible override for skill package upload extensions. When set, it replaces the default allowlist instead of appending to it. Include every extension you want to allow, for example all defaults plus `.dot`. This does not automatically expand pre-publish credential scanning. |

## Download Analytics

| Env var | Source | Default | Notes |
| --- | --- | --- | --- |
| `SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS` | ConfigMap | `12` | Rolling retention for `local_skill_download_event`. The backend prunes expired rows on startup and then once per day. Set `0` or a negative value to disable automatic pruning. |

## PostgreSQL

Prefer `SKILLHUB_DATABASE_URL`.

| Env var | Source | Default | Notes |
| --- | --- | --- | --- |
| `SKILLHUB_DATABASE_URL` | Secret | `postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub` | Full SQLAlchemy async URL. |
| `SPRING_DATASOURCE_URL` | Secret | unset | Java-compatible fallback, converted from `jdbc:postgresql://...`. |
| `SPRING_DATASOURCE_USERNAME` | Secret | unset | Used only with `SPRING_DATASOURCE_URL`. |
| `SPRING_DATASOURCE_PASSWORD` | Secret | unset | Used only with `SPRING_DATASOURCE_URL`. |

## Redis

Prefer either `SKILLHUB_REDIS_URL` for a single explicit URL, or the
Spring-compatible Redis/Sentinel variables for Java deployment parity.

| Env var | Source | Default | Notes |
| --- | --- | --- | --- |
| `SKILLHUB_REDIS_URL` | Secret | unset | Overrides host/port/Sentinel variables when set. |
| `SPRING_DATA_REDIS_HOST` | ConfigMap | `localhost` | Standalone Redis host. |
| `SPRING_DATA_REDIS_PORT` | ConfigMap | `6379` | Standalone Redis port. |
| `SPRING_DATA_REDIS_DATABASE` | ConfigMap | `0` | Redis logical DB. |
| `SPRING_DATA_REDIS_USERNAME` | Secret | unset | Redis ACL username. |
| `SPRING_DATA_REDIS_PASSWORD` | Secret | unset | Redis password. |
| `SPRING_DATA_REDIS_SSL_ENABLED` | ConfigMap | `false` | Enables TLS for Redis connections. |
| `SPRING_DATA_REDIS_SENTINEL_MASTER` | ConfigMap | unset | Sentinel master name, for example `mymaster`. |
| `SPRING_DATA_REDIS_SENTINEL_NODES` | ConfigMap | unset | Comma-separated `host:port` Sentinel nodes. |
| `SPRING_DATA_REDIS_SENTINEL_USERNAME` | Secret | unset | Sentinel ACL username. |
| `SPRING_DATA_REDIS_SENTINEL_PASSWORD` | Secret | unset | Sentinel password. |
| `SKILLHUB_REDIS_CONNECT_TIMEOUT` | ConfigMap | `PT5S` | Redis connect timeout. |
| `SKILLHUB_REDIS_TIMEOUT` | ConfigMap | `PT5S` | Redis command timeout. |

Aliases also accepted: `REDIS_HOST`, `REDIS_PORT`, `REDIS_DATABASE`,
`REDIS_USERNAME`, `REDIS_PASSWORD`, and `SKILLHUB_REDIS_SSL_ENABLED`.

## MinIO / S3 Storage

Downloads are proxied through the backend. The backend uses S3 `get_object` and
returns the file response itself; it does not redirect clients to object storage.

| Env var | Source | Default | Notes |
| --- | --- | --- | --- |
| `SKILLHUB_STORAGE_PROVIDER` | ConfigMap | `local` | Set to `s3` for MinIO/S3. |
| `SKILLHUB_STORAGE_BASE_PATH` | ConfigMap | repo `.dev/java-storage` | Local filesystem path, used only when provider is `local`. |
| `SKILLHUB_STORAGE_S3_ENDPOINT` | ConfigMap | unset | Canonical MinIO/S3 API endpoint. |
| `SKILLHUB_STORAGE_S3_PROXY_ENDPOINT` | ConfigMap | unset | Backend S3 client endpoint when traffic must go through a proxy. |
| `SKILLHUB_STORAGE_S3_PUBLIC_ENDPOINT` | ConfigMap | unset | Reserved for public object endpoint metadata; downloads do not require direct client access. |
| `SKILLHUB_STORAGE_S3_BUCKET` | ConfigMap | `skillhub-packages` | Object bucket. |
| `SKILLHUB_STORAGE_S3_ACCESS_KEY` | Secret | unset | S3 access key. |
| `SKILLHUB_STORAGE_S3_SECRET_KEY` | Secret | unset | S3 secret key. |
| `SKILLHUB_STORAGE_S3_REGION` | ConfigMap | `us-east-1` | S3 region. |
| `SKILLHUB_STORAGE_S3_FORCE_PATH_STYLE` | ConfigMap | `false` | Set `true` for most MinIO deployments. |
| `SKILLHUB_STORAGE_S3_DISABLE_CHUNKED_ENCODING` | ConfigMap | `false` | Set `true` only if your proxy or S3-compatible service cannot handle chunked upload. |
| `SKILLHUB_STORAGE_S3_AUTO_CREATE_BUCKET` | ConfigMap | `false` | Keep `false` in organization deployments where the bucket is pre-created. |
| `SKILLHUB_STORAGE_S3_MAX_CONNECTIONS` | ConfigMap | `50` | S3 client connection pool size. |
| `SKILLHUB_STORAGE_S3_CONNECTION_ACQUISITION_TIMEOUT` | ConfigMap | `PT10S` | S3 connect timeout. |
| `SKILLHUB_STORAGE_S3_API_CALL_ATTEMPT_TIMEOUT` | ConfigMap | `PT30S` | S3 read timeout per attempt. |
| `SKILLHUB_STORAGE_S3_API_CALL_TIMEOUT` | ConfigMap | `PT1M` | Overall S3 API timeout. |

## Keycloak / OIDC

| Env var | Source | Default | Notes |
| --- | --- | --- | --- |
| `SKILLHUB_PUBLIC_BASE_URL` | ConfigMap | request-derived | External HTTPS origin, for example `https://skills.example.com`. |
| `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID` | Secret | unset | Keycloak client ID. |
| `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_SECRET` | Secret | unset | Keycloak client secret. |
| `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_PROVIDER` | ConfigMap | `keycloak` | Provider id. |
| `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_AUTHORIZATION_GRANT_TYPE` | ConfigMap | `authorization_code` | OAuth grant type. |
| `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_REDIRECT_URI` | ConfigMap | `{baseUrl}/login/oauth2/code/{registrationId}` | Redirect URI template. |
| `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_SCOPE` | ConfigMap | `openid,profile,email` | OAuth scopes. |
| `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_NAME` | ConfigMap | `Keycloak` | Login button display name. |
| `SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI` | ConfigMap | unset | Keycloak realm issuer URL. |
| `SKILLHUB_SESSION_COOKIE_SECURE` | ConfigMap | `false` | Set `true` behind HTTPS ingress. |

## Auth And Bootstrap

| Env var | Source | Default | Notes |
| --- | --- | --- | --- |
| `SKILLHUB_AUTH_DIRECT_ENABLED` | ConfigMap | `false` | Direct username/password login toggle. |
| `SKILLHUB_AUTH_SESSION_BOOTSTRAP_ENABLED` | ConfigMap | `false` | Test/session bootstrap toggle. |
| `SKILLHUB_LOCAL_REGISTRATION_ENABLED` | ConfigMap | `true` | Set `false` to block `/api/v1/auth/local/register` while keeping local/admin login available. |
| `BOOTSTRAP_ADMIN_ENABLED` | ConfigMap | `false` | Creates or updates a bootstrap admin on startup. |
| `BOOTSTRAP_ADMIN_USER_ID` | ConfigMap | `docker-admin` | Bootstrap admin user id. |
| `BOOTSTRAP_ADMIN_USERNAME` | ConfigMap | `admin` | Bootstrap admin username. |
| `BOOTSTRAP_ADMIN_PASSWORD` | Secret | `ChangeMe!2026` | Bootstrap admin password. |
| `BOOTSTRAP_ADMIN_DISPLAY_NAME` | ConfigMap | `Platform Admin` | Display name. |
| `BOOTSTRAP_ADMIN_EMAIL` | ConfigMap | `admin@example.com` | Email. |

## Backend Scanner Control

These variables belong to the backend pod. Scanner container LLM credentials
belong to the scanner deployment, not the backend.

| Env var | Source | Default | Notes |
| --- | --- | --- | --- |
| `SKILLHUB_SECURITY_SCANNER_ENABLED` | ConfigMap | `false` | Enables scanner integration. |
| `SKILLHUB_SECURITY_SCANNER_BASE_URL` | ConfigMap | `http://localhost:8000` | Scanner API base URL. |
| `SKILLHUB_SECURITY_SCANNER_HEALTH_PATH` | ConfigMap | `/health` | Scanner health path. |
| `SKILLHUB_SECURITY_SCANNER_SCAN_PATH` | ConfigMap | `/scan-upload` | Upload scan endpoint path. |
| `SKILLHUB_SECURITY_SCANNER_MODE` | ConfigMap | `upload` | Scanner handoff mode. |
| `SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT_MS` | ConfigMap | `5000` | Scanner HTTP connect timeout. |
| `SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT_MS` | ConfigMap | `300000` | Scanner HTTP read timeout. |
| `SKILLHUB_SCAN_CONSUMER_ENABLED` | ConfigMap | `false` | Enables Redis stream scan consumer. |
| `SKILLHUB_SCAN_STREAM_KEY` | ConfigMap | `skillhub:scan:requests` | Redis stream key. |
| `SKILLHUB_SCAN_CONSUMER_GROUP_NAME` | ConfigMap | `skillhub-scan-workers` | Redis consumer group. |
| `SKILLHUB_SCAN_CONSUMER_NAME` | ConfigMap | hostname | Redis consumer name. |
| `SKILLHUB_SCAN_CONSUMER_READ_COUNT` | ConfigMap | `10` | Stream read count. |
| `SKILLHUB_SCAN_CONSUMER_BLOCK_MS` | ConfigMap | `2000` | Stream block timeout. |
| `SKILLHUB_SCAN_CONSUMER_RECLAIM_MIN_IDLE_MS` | ConfigMap | `120000` | Pending message reclaim idle threshold. |
| `SKILLHUB_SCAN_CONSUMER_RECLAIM_COUNT` | ConfigMap | `20` | Pending message reclaim batch size. |
| `SKILLHUB_SCANNER_USE_BEHAVIORAL` | ConfigMap | `true` | Scanner request flag. |
| `SKILLHUB_SCANNER_USE_LLM` | ConfigMap | `false` | Scanner request flag. |
| `SKILLHUB_SCANNER_LLM_PROVIDER` | ConfigMap | `anthropic` | Scanner request flag. |
| `SKILLHUB_SCANNER_USE_META` | ConfigMap | `false` | Scanner request flag. |
| `SKILLHUB_SCANNER_USE_AI_DEFENSE` | ConfigMap | `false` | Scanner request flag. |
| `SKILLHUB_SCANNER_AI_DEFENSE_API_KEY` | Secret | unset | Backend passes this scanner request option when enabled. |
| `SKILLHUB_SCANNER_USE_VIRUSTOTAL` | ConfigMap | `false` | Scanner request flag. |
| `SKILLHUB_SCANNER_USE_TRIGGER` | ConfigMap | `false` | Scanner request flag. |

## Built-In Skills

| Env var | Source | Default | Notes |
| --- | --- | --- | --- |
| `SKILLHUB_BUILTIN_SKILLS_ENABLED` | ConfigMap | `true` | Enables built-in skill bootstrap. |
