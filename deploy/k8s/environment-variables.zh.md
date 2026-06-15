# SkillHub K8s 環境變數整理手冊

本文適用於 Python backend cutover 後的 Kubernetes 部署。目標是讓既有 Java
Spring Boot 版部署可以盡量無痛切換到 Python backend。

## 相容原則

Python backend 目前支援兩種設定方式：

- **建議的新 Python 名稱**：新部署檔預設使用這些名稱。
- **Java/Spring 相容名稱**：如果你已經有 Java backend 的 K8s Deployment
  env，可以先保留，Python backend 會讀取這些 fallback。

優先順序通常是「Python 新名稱優先，Java 相容名稱 fallback」。如果兩邊同時設定，
請以 Python 新名稱為準，避免值不一致。

## 需要特別注意的改名/格式

| Java / 舊部署 env | Python preferred env | 是否必須改 | 說明 |
| --- | --- | --- | --- |
| `SPRING_DATASOURCE_URL` + `SPRING_DATASOURCE_USERNAME` + `SPRING_DATASOURCE_PASSWORD` | `SKILLHUB_DATABASE_URL` | 不一定 | Python 已可讀 Java 三段式設定，並把 `jdbc:postgresql://...` 轉成 `postgresql+asyncpg://...`。新部署仍建議直接填 `SKILLHUB_DATABASE_URL`。 |
| `SESSION_COOKIE_SECURE` | `SKILLHUB_SESSION_COOKIE_SECURE` | 不一定 | Python 兩者都讀。HTTPS ingress 請設 `true`。 |
| `SKILLHUB_SECURITY_SCANNER_URL` | `SKILLHUB_SECURITY_SCANNER_BASE_URL` | 不一定 | Python 兩者都讀。新部署建議用 `BASE_URL`。 |
| `SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT` | `SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT_MS` | 不一定 | Python 兩者都讀，單位都是毫秒。 |
| `SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT` | `SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT_MS` | 不一定 | Python 兩者都讀，單位都是毫秒。 |
| `SKILLHUB_SCANNER_USE_LLM` 等 analyzer flags | 同名沿用 | 不需改名 | Python backend 會用這些 flags 決定呼叫 scanner 時送出的 `use_llm`、`use_behavioral` 等欄位。 |
| `OAUTH2_GITHUB_*`, `OAUTH2_GITLAB_*` | 不建議沿用 | 需要調整 | 目前前端只保留 Keycloak/OIDC 登入入口；Python 不會預設 advertise GitHub/GitLab。 |

## PostgreSQL

### 新部署建議

| K8s key | Pod env | 必填 | 範例 | 說明 |
| --- | --- | --- | --- | --- |
| `skillhub-secret/database-url` | `SKILLHUB_DATABASE_URL` | 是 | `postgresql+asyncpg://skillhub:password@postgres.example.internal:5432/skillhub` | Python SQLAlchemy async URL。帳密若含 `@`, `:`, `/`, 空白等特殊字元要 URL encode。 |

### 可沿用 Java 設定

如果你現有 Java Deployment 已經直接設定下列 env，可以先不改：

```text
SPRING_DATASOURCE_URL=jdbc:postgresql://postgres.example.internal:5432/skillhub
SPRING_DATASOURCE_USERNAME=skillhub
SPRING_DATASOURCE_PASSWORD=change-me
```

Python 會轉成：

```text
postgresql+asyncpg://skillhub:change-me@postgres.example.internal:5432/skillhub
```

## Redis

Python backend 支援完整 URL，也支援 Java/Spring 分離式 env。

| K8s key | Pod env | 必填 | 範例 | 說明 |
| --- | --- | --- | --- | --- |
| `skillhub-secret/redis-url` | `SKILLHUB_REDIS_URL` | 否 | `redis://:password@redis.example.internal:6379/0` | 若非空，優先於所有分離式 Redis env。 |
| `skillhub-config/redis-host` | `SPRING_DATA_REDIS_HOST` | 是 | `redis.example.internal` | Redis host。 |
| `skillhub-config/redis-port` | `SPRING_DATA_REDIS_PORT` | 是 | `6379` | Redis port。 |
| `skillhub-config/redis-database` | `SPRING_DATA_REDIS_DATABASE` | 是 | `0` | Redis logical database。 |
| `skillhub-secret/redis-password` | `SPRING_DATA_REDIS_PASSWORD` | 視環境 | `change-me` | Redis 密碼。若 Redis 無密碼可留空。 |

Java fallback 也可沿用：

```text
REDIS_HOST
REDIS_PORT
REDIS_PASSWORD
REDIS_DATABASE
```

## MinIO / S3

| K8s key | Pod env | 必填 | 範例 | 說明 |
| --- | --- | --- | --- | --- |
| `skillhub-config/storage-provider` | `SKILLHUB_STORAGE_PROVIDER` | 是 | `s3` | K8s 接組織內 MinIO/S3 時設為 `s3`。 |
| `skillhub-config/storage-s3-endpoint` | `SKILLHUB_STORAGE_S3_ENDPOINT` | 是 | `http://minio.example.internal:9000` | MinIO/S3 canonical endpoint。 |
| `skillhub-config/storage-s3-proxy-endpoint` | `SKILLHUB_STORAGE_S3_PROXY_ENDPOINT` | 否 | `http://minio-proxy.example.internal:9000` | backend 需要先打 proxy 再到 MinIO 時設定。 |
| `skillhub-config/storage-s3-public-endpoint` | `SKILLHUB_STORAGE_S3_PUBLIC_ENDPOINT` | 否 | `https://objects.example.com` | 對外產生物件 URL 時使用。 |
| `skillhub-config/storage-s3-bucket` | `SKILLHUB_STORAGE_S3_BUCKET` | 是 | `skillhub-packages` | skill package bundle bucket。 |
| `skillhub-secret/storage-s3-access-key` | `SKILLHUB_STORAGE_S3_ACCESS_KEY` | 視環境 | `skillhub` | S3 access key。 |
| `skillhub-secret/storage-s3-secret-key` | `SKILLHUB_STORAGE_S3_SECRET_KEY` | 視環境 | `change-me` | S3 secret key。 |
| `skillhub-config/storage-s3-region` | `SKILLHUB_STORAGE_S3_REGION` | 是 | `us-east-1` | MinIO 通常可用 `us-east-1`。 |
| `skillhub-config/storage-s3-force-path-style` | `SKILLHUB_STORAGE_S3_FORCE_PATH_STYLE` | 是 | `true` | MinIO 通常設 `true`。 |
| `skillhub-config/storage-s3-disable-chunked-encoding` | `SKILLHUB_STORAGE_S3_DISABLE_CHUNKED_ENCODING` | 是 | `false` | proxy 或 OSS 不支援 chunked upload 時設 `true`。 |
| `skillhub-config/storage-s3-auto-create-bucket` | `SKILLHUB_STORAGE_S3_AUTO_CREATE_BUCKET` | 是 | `false` | 正式環境建議由平台預先建立 bucket。 |
| `skillhub-config/storage-s3-presign-expiry` | `SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY` | 是 | `PT10M` | Presigned URL 有效時間。 |

Proxy 範例：

```text
SKILLHUB_STORAGE_S3_ENDPOINT=http://minio.example.internal:9000
SKILLHUB_STORAGE_S3_PROXY_ENDPOINT=http://minio-proxy.example.internal:9000
SKILLHUB_STORAGE_S3_PUBLIC_ENDPOINT=https://objects.example.com
```

## Keycloak / OIDC

Python backend 支援 Spring Boot OIDC env naming。Keycloak 建議沿用這組：

| K8s key | Pod env | 必填 | 範例 |
| --- | --- | --- | --- |
| `skillhub-secret/oauth2-keycloak-client-id` | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID` | 是 | `skillhub-web` |
| `skillhub-secret/oauth2-keycloak-client-secret` | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_SECRET` | 是 | `change-me` |
| manifest literal | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_PROVIDER` | 是 | `keycloak` |
| manifest literal | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_AUTHORIZATION_GRANT_TYPE` | 是 | `authorization_code` |
| manifest literal | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_REDIRECT_URI` | 是 | `{baseUrl}/login/oauth2/code/{registrationId}` |
| `skillhub-config/oauth2-keycloak-scope` | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_SCOPE` | 是 | `openid,profile,email` |
| `skillhub-config/oauth2-keycloak-client-name` | `SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_NAME` | 是 | `Keycloak` |
| `skillhub-config/oauth2-keycloak-issuer-uri` | `SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI` | 是 | `https://keycloak.example.com/realms/skillhub` |
| `skillhub-config/public-base-url` | `SKILLHUB_PUBLIC_BASE_URL` | 是 | `https://skills.example.com` |

Keycloak client redirect URI 請設定：

```text
https://skills.example.com/login/oauth2/code/keycloak
```

## Backend 呼叫 Scanner

這些 env 是 **backend** 用來決定怎麼呼叫 scanner；不是 scanner container 的 LLM API key。

| K8s key | Pod env | 範例 | 說明 |
| --- | --- | --- | --- |
| `skillhub-config/security-scanner-enabled` | `SKILLHUB_SECURITY_SCANNER_ENABLED` | `true` | 是否啟用安全掃描。 |
| `skillhub-config/security-scanner-base-url` | `SKILLHUB_SECURITY_SCANNER_BASE_URL` | `http://skillhub-scanner:8000` | Scanner service URL。也可沿用 `SKILLHUB_SECURITY_SCANNER_URL`。 |
| `skillhub-config/security-scanner-mode` | `SKILLHUB_SECURITY_SCANNER_MODE` | `upload` | K8s 建議使用 upload handoff。 |
| `skillhub-config/scan-consumer-enabled` | `SKILLHUB_SCAN_CONSUMER_ENABLED` | `false` | 是否啟動 backend scan consumer。 |
| `skillhub-config/scanner-use-behavioral` | `SKILLHUB_SCANNER_USE_BEHAVIORAL` | `true` | 是否傳 `use_behavioral` 給 scanner。 |
| `skillhub-config/scanner-use-llm` | `SKILLHUB_SCANNER_USE_LLM` | `true` | 是否傳 `use_llm` 給 scanner。要啟用 LLM scan，這裡和 scanner LLM API key 都要設定。 |
| `skillhub-config/scanner-llm-provider` | `SKILLHUB_SCANNER_LLM_PROVIDER` | `anthropic` | 傳給 scanner 的 LLM provider。 |
| `skillhub-config/scanner-use-meta` | `SKILLHUB_SCANNER_USE_META` | `false` | 是否啟用 meta analyzer。 |
| `skillhub-config/scanner-use-ai-defense` | `SKILLHUB_SCANNER_USE_AI_DEFENSE` | `false` | 是否啟用 AI Defense analyzer。 |
| `skillhub-secret/scanner-ai-defense-api-key` | `SKILLHUB_SCANNER_AI_DEFENSE_API_KEY` | `change-me` | backend 會用 `X-AIDefense-Key` header 傳給 Cisco scanner。 |
| `skillhub-config/scanner-use-virustotal` | `SKILLHUB_SCANNER_USE_VIRUSTOTAL` | `false` | 是否啟用 VirusTotal analyzer。 |
| `skillhub-config/scanner-use-trigger` | `SKILLHUB_SCANNER_USE_TRIGGER` | `false` | 是否啟用 trigger specificity analyzer。 |

## Scanner Container LLM

這些 env 只應該放在 **scanner** deployment。backend 不需要也不應該拿這些值。

| K8s key | Pod env | 必填 | 說明 |
| --- | --- | --- | --- |
| `skillhub-scanner-secret/skill-scanner-llm-api-key` | `SKILL_SCANNER_LLM_API_KEY` | 啟用 LLM 時必填 | Scanner 連 LLM provider 的 API key。Kustomize base 仍可使用 `skillhub-secret` 同名 key。 |
| `skillhub-scanner-secret/skill-scanner-llm-base-url` | `SKILL_SCANNER_LLM_BASE_URL` | 視 provider | LLM base URL。 |
| `skillhub-scanner-secret/skill-scanner-llm-model` | `SKILL_SCANNER_LLM_MODEL` | 視 provider | LLM model。 |

啟用 LLM scan 時至少要同時設定：

```text
# backend deployment
SKILLHUB_SCANNER_USE_LLM=true

# scanner deployment
SKILL_SCANNER_LLM_API_KEY=...
SKILL_SCANNER_LLM_BASE_URL=...
SKILL_SCANNER_LLM_MODEL=...
```

## Session And Local Auth

| K8s key | Pod env | 範例 | 說明 |
| --- | --- | --- | --- |
| `skillhub-config/session-cookie-secure` | `SKILLHUB_SESSION_COOKIE_SECURE` | `true` | HTTPS ingress 請設 `true`。也可沿用 Java 的 `SESSION_COOKIE_SECURE`。 |
| `skillhub-config/auth-direct-enabled` | `SKILLHUB_AUTH_DIRECT_ENABLED` | `false` | 是否啟用 username/password direct auth API。 |
| `skillhub-config/auth-session-bootstrap-enabled` | `SKILLHUB_AUTH_SESSION_BOOTSTRAP_ENABLED` | `false` | local/dev session bootstrap，正式環境建議 `false`。 |

## Bootstrap Admin

| K8s key | Pod env | 範例 | 說明 |
| --- | --- | --- | --- |
| `skillhub-config/bootstrap-admin-enabled` | `BOOTSTRAP_ADMIN_ENABLED` | `true` | 首次初始化可設 `true`，完成後建議關閉。 |
| `skillhub-config/bootstrap-admin-user-id` | `BOOTSTRAP_ADMIN_USER_ID` | `docker-admin` | Bootstrap admin user id。 |
| `skillhub-config/bootstrap-admin-username` | `BOOTSTRAP_ADMIN_USERNAME` | `admin` | Bootstrap admin username。 |
| `skillhub-secret/bootstrap-admin-password` | `BOOTSTRAP_ADMIN_PASSWORD` | `ChangeMe!2026` | Bootstrap admin password。 |

## 最小可用範例

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
SKILLHUB_SCANNER_USE_LLM=true
SKILL_SCANNER_LLM_API_KEY=change-me
```
