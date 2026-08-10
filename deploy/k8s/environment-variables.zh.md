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
| `skillhub-config/redis-sentinel-master` | `SPRING_DATA_REDIS_SENTINEL_MASTER` | 視環境 | `mymaster` | Redis Sentinel master name。若 `SKILLHUB_REDIS_URL` 非空，Sentinel 設定會被忽略。 |
| `skillhub-config/redis-sentinel-nodes` | `SPRING_DATA_REDIS_SENTINEL_NODES` | 視環境 | `<bitnami-release>-redis:26379` | Redis Sentinel 節點清單，逗號分隔。Bitnami Redis Sentinel 通常可用 chart 產生的 Redis service `26379` port，或確認後改用 headless Pod DNS。 |
| `skillhub-secret/redis-sentinel-username` | `SPRING_DATA_REDIS_SENTINEL_USERNAME` | 視環境 | `default` | Sentinel ACL username。未啟用 Sentinel AUTH 時留空。 |
| `skillhub-secret/redis-sentinel-password` | `SPRING_DATA_REDIS_SENTINEL_PASSWORD` | 視環境 | `change-me` | Sentinel AUTH password。Bitnami 若 Sentinel 需要密碼，通常設成 Redis password 相同值。 |
| `skillhub-secret/redis-username` | `SPRING_DATA_REDIS_USERNAME` | 視環境 | `default` | Redis ACL username。Bitnami 預設通常可留空，只用 password。 |
| `skillhub-secret/redis-password` | `SPRING_DATA_REDIS_PASSWORD` | 視環境 | `change-me` | Redis 密碼。若 Redis 無密碼可留空。 |
| `skillhub-config/redis-ssl-enabled` | `SPRING_DATA_REDIS_SSL_ENABLED` | 視環境 | `false` | Redis/Sentinel 是否使用 TLS。 |
| `skillhub-config/redis-connect-timeout` | `SPRING_DATA_REDIS_CONNECT_TIMEOUT` | 否 | `PT5S` | Redis connect timeout。 |
| `skillhub-config/redis-timeout` | `SPRING_DATA_REDIS_TIMEOUT` | 否 | `PT5S` | Redis socket/read timeout。 |

Java fallback 也可沿用：

```text
REDIS_HOST
REDIS_PORT
REDIS_PASSWORD
REDIS_DATABASE
```

### Redis Sentinel 設定範例

若使用 Bitnami Redis Helm chart 並啟用 Sentinel，請確認填入的是 Sentinel 節點與 master name，不要把會輪詢到 replica 的一般 Redis service 當成 backend 寫入目標。

```text
SKILLHUB_REDIS_URL=
SPRING_DATA_REDIS_SENTINEL_MASTER=mymaster
SPRING_DATA_REDIS_SENTINEL_NODES=<bitnami-release>-redis:26379
SPRING_DATA_REDIS_PASSWORD=change-me
SPRING_DATA_REDIS_SENTINEL_PASSWORD=change-me
SPRING_DATA_REDIS_DATABASE=0
```

Bitnami Redis Sentinel 的 chart 文件說明，在 `architecture=replication` 且
`sentinel.enabled=true` 時，寫入端需要透過 Sentinel 查目前 master；chart
服務的 `6379` 是 Redis read-only port，`26379` 是 Sentinel port。若你不想
依賴 service load balancing，也可以填 headless Pod DNS，例如
`<release>-redis-node-0.<release>-redis-headless.<namespace>.svc.cluster.local:26379`；
實際名稱請以 `kubectl get svc,endpoints -n <namespace>` 為準。

優先順序：

```text
SKILLHUB_REDIS_URL 非空 -> 使用單點 Redis URL，忽略 Sentinel
Sentinel master/nodes 非空 -> 透過 Sentinel 找目前 master
否則 -> 使用 SPRING_DATA_REDIS_HOST / PORT / PASSWORD / DATABASE
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
| `skillhub-config/public-base-url` | `SKILLHUB_PUBLIC_BASE_URL` | 是 | `https://ai-coding-platform.tsmc.com/skillhub` |

Keycloak client redirect URI 請設定：

```text
https://ai-coding-platform.tsmc.com/skillhub/login/oauth2/code/keycloak
```

Keycloak `Root URL` / `Home URL` 設為
`https://ai-coding-platform.tsmc.com/skillhub`；`Web Origins` 只接受 origin，
因此應設為 `https://ai-coding-platform.tsmc.com`，不可包含 `/skillhub`。

## 子路徑正式入口

以 `https://ai-coding-platform.tsmc.com/skillhub` 作為唯一正式入口時：

| K8s key | Pod env | 值 |
| --- | --- | --- |
| `skillhub-config/public-base-url` | `SKILLHUB_PUBLIC_BASE_URL` | `https://ai-coding-platform.tsmc.com/skillhub` |
| `skillhub-config/web-base-path` | `SKILLHUB_WEB_BASE_PATH` | `/skillhub` |
| `skillhub-config/web-api-base-url` | `SKILLHUB_WEB_API_BASE_URL` | 留空，自動使用 `/skillhub` |
| `skillhub-config/device-auth-verification-uri` | `SKILLHUB_DEVICE_AUTH_VERIFICATION_URI` | 留空，自動產生正式入口下的 `/cli/auth` |
| `skillhub-config/session-cookie-secure` | `SKILLHUB_SESSION_COOKIE_SECURE` | `true` |

DNS CNAME `ai-coding-platform.tsmc.com -> skillhub-test.ftest.tsmc.com` 只讓兩個
名稱到達同一個 load balancer，不會改寫 TLS SNI 或 HTTP Host；兩者仍會是
`ai-coding-platform.tsmc.com`。因此只申請 CNAME 不足夠，既有 Gateway 與
VirtualService 都必須接受 canonical hostname。

憑證只需要涵蓋 hostname `ai-coding-platform.tsmc.com`，不包含 `/skillhub`。
將 full certificate chain 與 private key 建成名為 `ai-coding-platform-tls` 的
`kubernetes.io/tls` Secret，放在 ingress gateway workload 讀取 credential 的
namespace；憑證與私鑰不可提交到 repository。以下只是 patch fragment，不能
當成完整 Gateway manifest 直接 apply。請在既有 `spec.servers` 保留原本
`skillhub-test.ftest.tsmc.com` 與其他 servers，另外加入 canonical HTTPS server：

```yaml
spec:
  servers:
    # 保留所有既有 server，包含 skillhub-test.ftest.tsmc.com
    - port:
        number: 443
        name: https-ai-coding-platform
        protocol: HTTPS
      hosts:
        - ai-coding-platform.tsmc.com
      tls:
        mode: SIMPLE
        credentialName: ai-coding-platform-tls
```

Gateway `servers[].hosts` 是 hostname allowlist；VirtualService 的 `gateways`
則是 Gateway resource reference，不是 hostname。canonical VirtualService 建議寫成：

```yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: skillhub-public
  namespace: skillhub
spec:
  hosts:
    - ai-coding-platform.tsmc.com
  gateways:
    - istio-system/organization-ingress # 替換成既有 Gateway reference
  http:
    - match:
        - uri:
            exact: /skillhub
        - uri:
            prefix: /skillhub/
      rewrite:
        uri: /
      route:
        - destination:
            host: skillhub-web.skillhub.svc.cluster.local
            port:
              number: 80
```

這是內部 path rewrite，不是 browser redirect；使用者網址會持續保留
`/skillhub`。舊 `skillhub-test.ftest.tsmc.com` VirtualService 可暫留維運用途，
不要把它混入 canonical 規則。只有在 Istio gateway 會覆寫 forwarded-proto 且
web Pod 不可被直接存取時，才將 `trust-forwarded-proto` 設為 `"true"`。

既有 VirtualService rewrite 仍受支援，也是組織首次升級時的建議做法。新版
web image 也能直接接收 `/skillhub/...` 並在容器內移除設定的 prefix；未來只有
在相同 image 與 browser 驗證通過後，才可考慮省略 VirtualService 的 `rewrite`。
`web-base-path` 留空時 root deployment 維持原行為，本次 image 升級不要求移除
既有 rewrite。

上線前必須確認 Secret 位於正確 credential namespace、憑證 SAN 包含
`ai-coding-platform.tsmc.com`、Gateway 沒有 invalid credential 錯誤，並驗證
TLS SNI 與 HTTP Host 都能命中 canonical VirtualService。

## CLI Registry URL

| K8s key | Pod env | 必填 | 範例 | 說明 |
| --- | --- | --- | --- | --- |
| `skillhub-config/cli-registry-url` | `SKILLHUB_WEB_CLI_REGISTRY_URL` | 否 | `http://skills.example.com` | frontend-only install command override，只調整 Skill 頁面複製的 CLI 指令。 |

請填完整的 absolute HTTP/HTTPS URL，且不要加 trailing slash。留空時會
fallback 到既有 frontend app URL；目前 K8s manifests 的該值是 browser
origin。`public-base-url` 控制 backend OAuth callback 與 frontend public
app URL，但不會覆蓋 `cli-registry-url`。HTTP 會讓 CLI Bearer token
在沒有 TLS 的情況下以明文傳輸。CLI credential 與 installed-skill
inventory 依 exact registry URL 分開，因此 HTTP 與 HTTPS 是不同 scope；
切換到 HTTP 後必須對該 HTTP registry 執行 `skillhub login --registry
http://host --token <token>`，或設定 `SKILLHUB_TOKEN`。HTTP endpoint
不可 redirect CLI 回 HTTPS。

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

## Publish Upload Allowlist

| K8s key | Pod env | Required | Example | Notes |
| --- | --- | --- | --- | --- |
| `skillhub-config/publish-allowed-file-extensions` | `SKILLHUB_PUBLISH_ALLOWED_FILE_EXTENSIONS` | No | `.md,.txt,.json,.yaml,.yml,.py,.sh,.dot` | Optional Java-compatible override for skill package upload extensions. When set, it replaces the default allowlist instead of appending to it, so include every extension you want to allow. It does not automatically expand pre-publish credential scanning. |

## Download Analytics

| K8s key | Pod env | Required | Example | Notes |
| --- | --- | --- | --- | --- |
| `skillhub-config/download-analytics-retention-months` | `SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS` | No | `12` | Rolling retention for `local_skill_download_event`. Default is 12 months. Set `0` or a negative value to disable automatic pruning. The backend runs pruning at startup and then once per day. |

## Optional Skill Playground Sidecar

Skill Playground 是獨立部署的可選 sidecar。SkillHub Kustomize base 不部署、探測或等待 sidecar；sidecar 停止時，SkillHub 的啟動、health、搜尋、詳細頁、安裝、發布與審核必須維持正常。

| Target | Pod env | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| backend | `SKILLHUB_PLAYGROUND_TOKEN_SECRET` | 啟用時必填 | empty | 簽發短效唯讀 capability 的 backend-only secret。留空時 capability endpoint 回傳 disabled，但 backend 正常啟動。 |
| backend | `SKILLHUB_PLAYGROUND_TOKEN_TTL_SECONDS` | No | `300` | Capability 存活秒數。 |
| backend | `SKILLHUB_PLAYGROUND_TOKEN_ISSUER` | No | `skillhub` | Capability issuer。 |
| backend | `SKILLHUB_PLAYGROUND_TOKEN_AUDIENCE` | No | `skill-playground-sidecar` | Capability audience。 |
| backend | `SKILLHUB_PLAYGROUND_CONTEXT_MAX_BYTES` | No | `120000` | 傳給 sidecar 的唯讀文字 context 上限。 |
| web | `SKILLHUB_WEB_PLAYGROUND_ENABLED` | No | `false` | 是否在 Skill 詳細頁顯示 Playground 入口。 |
| web | `SKILLHUB_WEB_PLAYGROUND_BASE_URL` | 啟用時必填 | empty | 瀏覽器可連線的 sidecar URL，例如 `https://playground.example.com`。 |

sidecar 的 OpenAI-compatible provider、model catalog、API key 與 SkillHub context adapter URL 都由 sidecar repo 自己管理，不放入 SkillHub base manifest。

完整移除流程：

1. 將 `SKILLHUB_WEB_PLAYGROUND_ENABLED=false` 並清空 `SKILLHUB_WEB_PLAYGROUND_BASE_URL`。
2. 移除獨立部署的 sidecar workload。
3. 視需要清空 backend 的 `SKILLHUB_PLAYGROUND_TOKEN_SECRET`。

不需要資料庫 migration、資料清理、Redis 清理或 SkillHub rollout dependency 變更。

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
| `skillhub-config/local-registration-enabled` | `SKILLHUB_LOCAL_REGISTRATION_ENABLED` | `false` | 是否開放本機帳號自助註冊；設為 `false` 只會隱藏/阻擋註冊，不會關閉 local/admin 登入。 |

## Bootstrap Admin

| K8s key | Pod env | 範例 | 說明 |
| --- | --- | --- | --- |
| `skillhub-config/bootstrap-admin-enabled` | `BOOTSTRAP_ADMIN_ENABLED` | `true` | 首次初始化可設 `true`，完成後建議關閉。 |
| `skillhub-config/bootstrap-admin-user-id` | `BOOTSTRAP_ADMIN_USER_ID` | `docker-admin` | Bootstrap admin user id。 |
| `skillhub-config/bootstrap-admin-username` | `BOOTSTRAP_ADMIN_USERNAME` | `admin` | Bootstrap admin username。 |
| `skillhub-secret/bootstrap-admin-password` | `BOOTSTRAP_ADMIN_PASSWORD` | `ChangeMe!2026` | Bootstrap admin password。 |

## Built-in Skills Bootstrap

| K8s key | Pod env | 範例 | 說明 |
| --- | --- | --- | --- |
| `skillhub-config/builtin-skills-enabled` | `SKILLHUB_BUILTIN_SKILLS_ENABLED` | `true` | 是否在 backend 啟動後背景同步 upstream 內建 skill manifest。若正式環境不能連外到 `bjcdn.openstorage.cn`，可設為 `false`。 |
| manifest volume/env override | `SKILLHUB_BUILTIN_SKILLS_MANIFEST_PATH` | `/app/app/builtin_skills/manifest.json` | 可選。預設使用映像內建 manifest；只有要覆蓋 manifest 時才需要設定。 |

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
SKILLHUB_PUBLIC_BASE_URL=https://ai-coding-platform.tsmc.com/skillhub
SKILLHUB_WEB_BASE_PATH=/skillhub
SKILLHUB_WEB_API_BASE_URL=
SKILLHUB_DEVICE_AUTH_VERIFICATION_URI=
SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS=12
SKILLHUB_BUILTIN_SKILLS_ENABLED=true
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID=skillhub-web
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_SECRET=change-me
SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI=https://keycloak.example.com/realms/skillhub
SKILLHUB_SCANNER_USE_LLM=true
SKILL_SCANNER_LLM_API_KEY=change-me
```

## Trusted Forwarded Protocol

`skillhub-config/trust-forwarded-proto` 對應 web pod 的
`SKILLHUB_TRUST_FORWARDED_PROTO`，預設為 `false`。只有在可信任的 ingress
會覆寫 `X-Forwarded-Proto`，而且外部無法直接連到 web pod 時，才能設為
`true`。未啟用時，web nginx 會忽略 client 自帶的 forwarded protocol，
避免偽造 HTTPS 來源。
