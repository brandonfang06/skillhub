# SkillHub K8s 環境變數整理手冊

這份手冊對應 `deploy/k8s/base` 的 manifest。K8s 只部署
`frontend`、`backend-python`、`scanner`；PostgreSQL、Redis、MinIO/S3、
Keycloak/OIDC 請接你組織內已經架好的服務。

## PostgreSQL

| K8s key | Pod env | 必填 | 範例 | 說明 |
| --- | --- | --- | --- | --- |
| `skillhub-secret/database-url` | `SKILLHUB_DATABASE_URL` | 是 | `postgresql+asyncpg://skillhub:password@postgres.example.internal:5432/skillhub` | Python backend 使用的 SQLAlchemy async URL。帳密若含 `@`, `:`, `/` 等特殊字元要 URL encode。 |

## Redis

Python backend 支援兩種 Redis 設定方式。若 `SKILLHUB_REDIS_URL` 非空，會優先使用它；否則會用 Java/Spring 相容的分離環境變數組合 URL。

### 建議方式：分離 host/port/password/database

| K8s key | Pod env | 必填 | 範例 | 說明 |
| --- | --- | --- | --- | --- |
| `skillhub-config/redis-host` | `SPRING_DATA_REDIS_HOST` | 是 | `redis.example.internal` | Redis host。 |
| `skillhub-config/redis-port` | `SPRING_DATA_REDIS_PORT` | 是 | `6379` | Redis port。 |
| `skillhub-config/redis-database` | `SPRING_DATA_REDIS_DATABASE` | 是 | `0` | Redis logical database。 |
| `skillhub-secret/redis-password` | `SPRING_DATA_REDIS_PASSWORD` | 否 | `change-me` | Redis 密碼。沒有密碼時留空。這個 env 與 Java Spring Boot 原本的設定相容。 |

也支援 Java baseline 的 fallback 名稱：`REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD`、`REDIS_DATABASE`。K8s base manifest 預設使用 `SPRING_DATA_REDIS_*`。

### 覆蓋方式：完整 Redis URL

| K8s key | Pod env | 必填 | 範例 | 說明 |
| --- | --- | --- | --- | --- |
| `skillhub-secret/redis-url` | `SKILLHUB_REDIS_URL` | 否 | `redis://:password@redis.example.internal:6379/0` | 完整 Redis URL。若非空，會覆蓋上面的 `SPRING_DATA_REDIS_*`。 |

Redis 目前用在 session、idempotency、device auth、scanner stream 等 Python backend 功能。這次 cutover 已補上 Redis `AUTH` 與 `SELECT`，所以密碼和 database 都會真的送到 Redis 連線。

## MinIO / S3

Python backend 沿用 Java cutover 後的 `SKILLHUB_STORAGE_S3_*` 設定。K8s 預設 `SKILLHUB_STORAGE_PROVIDER=s3`，不再建立本地 PVC。

| K8s key | Pod env | 必填 | 範例 | 說明 |
| --- | --- | --- | --- | --- |
| `skillhub-config/storage-provider` | `SKILLHUB_STORAGE_PROVIDER` | 是 | `s3` | K8s 建議固定為 `s3`。 |
| `skillhub-config/storage-s3-endpoint` | `SKILLHUB_STORAGE_S3_ENDPOINT` | 是 | `http://minio.example.internal:9000` | MinIO/S3 canonical API endpoint。 |
| `skillhub-config/storage-s3-proxy-endpoint` | `SKILLHUB_STORAGE_S3_PROXY_ENDPOINT` | 否 | `http://minio-proxy.example.internal:9000` | backend 必須先打 proxy 才能到 MinIO 時填這個。實際請求會優先用 proxy endpoint。 |
| `skillhub-config/storage-s3-public-endpoint` | `SKILLHUB_STORAGE_S3_PUBLIC_ENDPOINT` | 否 | `https://objects.example.com` | 產生對外 URL 時使用的 public endpoint。 |
| `skillhub-config/storage-s3-bucket` | `SKILLHUB_STORAGE_S3_BUCKET` | 是 | `skillhub-packages` | skill package bundle bucket。 |
| `skillhub-secret/storage-s3-access-key` | `SKILLHUB_STORAGE_S3_ACCESS_KEY` | 是 | `skillhub` | S3 access key。 |
| `skillhub-secret/storage-s3-secret-key` | `SKILLHUB_STORAGE_S3_SECRET_KEY` | 是 | `change-me` | S3 secret key。 |
| `skillhub-config/storage-s3-region` | `SKILLHUB_STORAGE_S3_REGION` | 是 | `us-east-1` | MinIO 常用 `us-east-1`。 |
| `skillhub-config/storage-s3-force-path-style` | `SKILLHUB_STORAGE_S3_FORCE_PATH_STYLE` | 是 | `true` | MinIO 通常要設 `true`。 |
| `skillhub-config/storage-s3-disable-chunked-encoding` | `SKILLHUB_STORAGE_S3_DISABLE_CHUNKED_ENCODING` | 是 | `false` | 若 proxy 或 OSS 不支援 chunked upload，可改 `true`。 |
| `skillhub-config/storage-s3-auto-create-bucket` | `SKILLHUB_STORAGE_S3_AUTO_CREATE_BUCKET` | 是 | `false` | 正式環境建議由平台預先建立 bucket。 |
| `skillhub-config/storage-s3-presign-expiry` | `SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY` | 是 | `PT10M` | Presigned URL 有效時間。 |

Proxy 範例：

```text
SKILLHUB_STORAGE_S3_ENDPOINT=http://minio.example.internal:9000
SKILLHUB_STORAGE_S3_PROXY_ENDPOINT=http://minio-proxy.example.internal:9000
SKILLHUB_STORAGE_S3_PUBLIC_ENDPOINT=https://objects.example.com
```

沒有 proxy 時，`SKILLHUB_STORAGE_S3_PROXY_ENDPOINT` 留空即可，backend 會使用 `SKILLHUB_STORAGE_S3_ENDPOINT`。

## Keycloak / OIDC

Python backend 保留 Spring Boot 風格的 Keycloak/OIDC env，方便沿用 Java 部署值。

| K8s key | Pod env | 必填 | 範例 | 說明 |
| --- | --- | --- | --- | --- |
| `skillhub-secret/oauth2-keycloak-client-id` | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID` | 否 | `skillhub-web` | Keycloak client ID。留空代表 provider 暫不啟用。 |
| `skillhub-secret/oauth2-keycloak-client-secret` | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_SECRET` | 否 | `change-me` | Keycloak client secret。 |
| manifest literal | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_PROVIDER` | 是 | `keycloak` | provider id。 |
| manifest literal | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_AUTHORIZATION_GRANT_TYPE` | 是 | `authorization_code` | OAuth flow。 |
| manifest literal | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_REDIRECT_URI` | 是 | `{baseUrl}/login/oauth2/code/{registrationId}` | callback template。 |
| `skillhub-config/oauth2-keycloak-scope` | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_SCOPE` | 是 | `openid,profile,email` | OIDC scopes。 |
| `skillhub-config/oauth2-keycloak-client-name` | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_NAME` | 是 | `Keycloak` | UI 顯示名稱。 |
| `skillhub-config/oauth2-keycloak-issuer-uri` | `SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI` | 否 | `https://keycloak.example.com/realms/skillhub` | realm issuer URI。backend 會由 issuer 解析 auth/token/userinfo endpoint。 |

Public base URL：

| K8s key | Pod env | 建議 | 說明 |
| --- | --- | --- | --- |
| `skillhub-config/public-base-url` | `SKILLHUB_PUBLIC_BASE_URL` | `https://skills.example.com` | OAuth redirect URI 和對外連結使用的 origin。 |

Keycloak client 建議加入 redirect URI：

```text
https://skills.example.com/login/oauth2/code/keycloak
```

## Scanner

| K8s key | Pod env | 必填 | 範例 | 說明 |
| --- | --- | --- | --- | --- |
| `skillhub-config/security-scanner-enabled` | `SKILLHUB_SECURITY_SCANNER_ENABLED` | 是 | `true` | 是否啟用 backend 呼叫 scanner。 |
| `skillhub-config/security-scanner-base-url` | `SKILLHUB_SECURITY_SCANNER_BASE_URL` | 是 | `http://skillhub-scanner:8000` | Scanner service URL。 |
| `skillhub-config/security-scanner-mode` | `SKILLHUB_SECURITY_SCANNER_MODE` | 是 | `upload` | K8s 使用 upload handoff。 |
| `skillhub-config/scan-consumer-enabled` | `SKILLHUB_SCAN_CONSUMER_ENABLED` | 是 | `false` | 目前 K8s 不預設啟用 backend scan consumer。 |

Scanner LLM secret：

| K8s key | Pod env | 必填 | 說明 |
| --- | --- | --- | --- |
| `skillhub-secret/skill-scanner-llm-api-key` | scanner container env | 否 | Scanner 使用的 LLM API key。 |
| `skillhub-secret/skill-scanner-llm-base-url` | `SKILL_SCANNER_LLM_BASE_URL` | 否 | LLM base URL。 |
| `skillhub-secret/skill-scanner-llm-model` | scanner container env | 否 | LLM model。 |

## Session 與登入安全

| K8s key | Pod env | 建議 | 說明 |
| --- | --- | --- | --- |
| `skillhub-config/session-cookie-secure` | `SKILLHUB_SESSION_COOKIE_SECURE` | HTTPS ingress 設 `true` | 控制 session cookie Secure flag。 |
| `skillhub-config/auth-direct-enabled` | `SKILLHUB_AUTH_DIRECT_ENABLED` | `false` | 是否啟用 username/password direct auth API。 |
| `skillhub-config/auth-session-bootstrap-enabled` | `SKILLHUB_AUTH_SESSION_BOOTSTRAP_ENABLED` | `false` | local/dev session bootstrap，不建議正式環境開啟。 |

## Bootstrap Admin

| K8s key | Pod env | 建議 | 說明 |
| --- | --- | --- | --- |
| `skillhub-config/bootstrap-admin-enabled` | `BOOTSTRAP_ADMIN_ENABLED` | 首次部署可 `true`，完成後改 `false` | 建立初始 admin。 |
| `skillhub-config/bootstrap-admin-user-id` | `BOOTSTRAP_ADMIN_USER_ID` | `docker-admin` | 初始 admin user id。 |
| `skillhub-config/bootstrap-admin-username` | `BOOTSTRAP_ADMIN_USERNAME` | `admin` | 初始 admin username。 |
| `skillhub-secret/bootstrap-admin-password` | `BOOTSTRAP_ADMIN_PASSWORD` | 強密碼 | 初始 admin password。 |

## 常見完整範例

```text
SKILLHUB_DATABASE_URL=postgresql+asyncpg://skillhub:password@postgres.example.internal:5432/skillhub
SPRING_DATA_REDIS_HOST=redis.example.internal
SPRING_DATA_REDIS_PORT=6379
SPRING_DATA_REDIS_PASSWORD=change-me
SPRING_DATA_REDIS_DATABASE=0
SKILLHUB_STORAGE_PROVIDER=s3
SKILLHUB_STORAGE_S3_ENDPOINT=http://minio.example.internal:9000
SKILLHUB_STORAGE_S3_PROXY_ENDPOINT=http://minio-proxy.example.internal:9000
SKILLHUB_STORAGE_S3_BUCKET=skillhub-packages
SKILLHUB_STORAGE_S3_ACCESS_KEY=skillhub
SKILLHUB_STORAGE_S3_SECRET_KEY=change-me
SKILLHUB_STORAGE_S3_REGION=us-east-1
SKILLHUB_STORAGE_S3_FORCE_PATH_STYLE=true
SKILLHUB_PUBLIC_BASE_URL=https://skills.example.com
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID=skillhub-web
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_SECRET=change-me
SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI=https://keycloak.example.com/realms/skillhub
```
