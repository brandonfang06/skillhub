# Skill Collections、GitLab 匯入與 Nexus CLI 部署操作手冊

更新日期：2026-07-27

本手冊供平台、Kubernetes 與 SkillHub 維運人員部署下列能力：

- first-class versioned collections；
- 由內部 GitLab mirror 匯入 repository；
- 透過內部 Nexus npm group 發布與安裝支援 collection 的 SkillHub CLI；
- 在 Web UI 顯示可複製的一鍵安裝指令。

這次變更維持 full-Python runtime。Backend 仍是
`server-python/` 的 FastAPI 應用；不需要 Java、Maven、Spring Boot 或額外
hybrid runtime。Scanner 沒有新增環境變數。

## 部署結論

若直接使用本 repository 的 K8s base/plain manifest 或
`compose.release.yml`，新環境變數已接到 backend 與 web container。維運人員
需要做的是：

1. 先保持四個 feature flags 為 `false`。
2. 設定內部 GitLab origin、allowlist、backend-only token 與必要的 CA mount。
3. 用專用 CLI release workflow 將新的 immutable CLI version 發布到 Nexus。
4. 把 Nexus group URL、內部 package name 與確切 CLI version 設到 web runtime。
5. 依序啟用 backend collections、web collections、backend GitLab import、
   web GitLab import，每一步都執行 smoke test。

Backend flags 是權威；web flags 只控制 UI。更新 ConfigMap 或 Secret 後，
Kubernetes 不會自動重建 Pod，必須明確 rollout restart。

## 需要新增或確認的設定

### Backend ConfigMap

| Pod env | K8s ConfigMap key | 建議初始值 | 何時需要 |
| --- | --- | --- | --- |
| `SKILLHUB_COLLECTIONS_ENABLED` | `collections-enabled` | `false` | 啟用 versioned collection APIs。 |
| `SKILLHUB_GITLAB_IMPORT_ENABLED` | `gitlab-import-enabled` | `false` | 啟用內部 GitLab 匯入；collections 未啟用時此值不生效。 |
| `SKILLHUB_GITLAB_BASE_URL` | `gitlab-base-url` | empty | 固定內部 GitLab HTTPS origin，例如 `https://gitlab.example.internal`；不要包含 `/api/v4`。 |
| `SKILLHUB_GITLAB_ALLOWED_GROUPS` | `gitlab-allowed-groups` | empty | 以逗號分隔的 project path prefix，例如 `oss-mirrors,approved/tools`。 |
| `SKILLHUB_GITLAB_CA_BUNDLE_PATH` | `gitlab-ca-bundle-path` | empty | 內部 CA bundle 在 backend container 內的絕對路徑；使用系統 trust store 時留空。 |
| `SKILLHUB_GITLAB_CONNECT_TIMEOUT_MS` | `gitlab-connect-timeout-ms` | `5000` | GitLab DNS/TCP/TLS 連線 timeout。 |
| `SKILLHUB_GITLAB_READ_TIMEOUT_MS` | `gitlab-read-timeout-ms` | `60000` | GitLab API 與 archive read timeout。 |
| `SKILLHUB_GITLAB_ARCHIVE_MAX_BYTES` | `gitlab-archive-max-bytes` | `52428800` | 壓縮 archive 上限，預設部署值為 50 MiB。 |
| `SKILLHUB_GITLAB_ARCHIVE_MAX_FILES` | `gitlab-archive-max-files` | `500` | ZIP 非目錄檔案數上限。 |
| `SKILLHUB_GITLAB_ARCHIVE_MAX_SINGLE_FILE_BYTES` | `gitlab-archive-max-single-file-bytes` | `5242880` | 單檔解壓縮上限（5 MiB）。 |
| `SKILLHUB_GITLAB_ARCHIVE_MAX_EXPANDED_BYTES` | `gitlab-archive-max-expanded-bytes` | `52428800` | 解壓縮總量上限（50 MiB）。 |
| `SKILLHUB_GITLAB_IMPORT_MAX_CANDIDATES` | `gitlab-import-max-candidates` | `100` | 單次 preview 的 Skill candidate 上限。 |

`SKILLHUB_GITLAB_BASE_URL` 只接受 HTTPS origin。Backend 不跟隨 redirect，
所以此 URL 必須直接到達正式 GitLab origin。使用者只輸入 project path 與
branch/tag/commit，不能覆寫 host。

### Backend Secret

| Pod env | K8s Secret key | 何時需要 |
| --- | --- | --- |
| `SKILLHUB_GITLAB_TOKEN` | `gitlab-token` | GitLab import 啟用前必填。使用僅能讀取 allowlisted mirror groups、具有 `read_api` 與 `read_repository` 的 organization/project access token。 |

Token 只能存在 backend Secret，不可寫入 ConfigMap、web runtime config、
Git repository、CLI package或操作截圖。

### Web runtime ConfigMap

| Pod env | K8s ConfigMap key | 建議初始值 | 說明 |
| --- | --- | --- | --- |
| `SKILLHUB_WEB_COLLECTIONS_ENABLED` | `web-collections-enabled` | `false` | 顯示 collection routes 與 maintenance UI。 |
| `SKILLHUB_WEB_GITLAB_IMPORT_ENABLED` | `web-gitlab-import-enabled` | `false` | 顯示 GitLab import actions。 |
| `SKILLHUB_WEB_CLI_NPM_REGISTRY` | `web-cli-npm-registry` | empty | 員工使用的 Nexus npm **group** URL。 |
| `SKILLHUB_WEB_CLI_PACKAGE` | `web-cli-package` | empty | 內部 CLI package coordinate，例如 `@company/skillhub`。 |
| `SKILLHUB_WEB_CLI_VERSION` | `web-cli-version` | empty | 已發布並驗證的確切 immutable version，例如 `0.1.10`。 |

三個 `SKILLHUB_WEB_CLI_*` 值必須同時存在，且 version 不可為 `latest` 或
range；否則 UI 不會產生 collection 安裝指令。這些值是公開 runtime config，
不得放 Nexus token。

UI 產生的命令會包含兩個用途不同的 registry：

```bash
npx --yes --registry https://nexus.example.internal/repository/npm-group/ \
  @company/skillhub@0.1.10 \
  collection install @opensource/superpowers \
  --version 1.0.0 \
  --registry https://skillhub.example.internal \
  --scope user
```

- 第一個 `--registry` 由 `npx` 使用，從 Nexus group 下載 CLI。
- 第二個 `--registry` 由 SkillHub CLI 使用，連到 SkillHub API。
- `collection install` 強制明確提供第二個 `--registry`。

### 不需新增的設定

- Scanner 不需新增 env。
- PostgreSQL、Redis、MinIO/S3 與 Keycloak/OIDC 沿用既有設定。
- Ingress 沿用 `/api` 到 backend、其他路徑到 web 的既有 routing。
- 不新增 collection owner；team namespace 的 `OWNER`/`ADMIN` 維護
  collections，global namespace 由 `SKILL_ADMIN`/`SUPER_ADMIN` 維護。

## K8s 設定範例

先以關閉狀態填入
[`deploy/k8s/base/configmap.yaml`](base/configmap.yaml)：

```yaml
data:
  collections-enabled: "false"
  gitlab-import-enabled: "false"
  gitlab-base-url: "https://gitlab.example.internal"
  gitlab-allowed-groups: "oss-mirrors,approved/tools"
  gitlab-ca-bundle-path: "/etc/skillhub/gitlab-ca/ca.crt"
  gitlab-connect-timeout-ms: "5000"
  gitlab-read-timeout-ms: "60000"
  gitlab-archive-max-bytes: "52428800"

  web-collections-enabled: "false"
  web-gitlab-import-enabled: "false"
  web-cli-npm-registry: "https://nexus.example.internal/repository/npm-group/"
  web-cli-package: "@company/skillhub"
  web-cli-version: "0.1.10"
```

只有在 `0.1.10` 的實際 artifact 已包含 collection CLI 並已經由 Nexus group
驗證時，才可使用該版本。不要因為本機 `package.json` 仍是舊版，就把未發布
或不包含本次功能的舊版填進 production。

在不納入版控的 Secret 檔案中填入：

```yaml
stringData:
  gitlab-token: "<read-only-gitlab-token>"
```

本 repository 已將上述 K8s keys 接到：

- `deploy/k8s/base/backend-deployment.yaml`
- `deploy/k8s/base/frontend-deployment.yaml`
- `deploy/k8s/plain/backend/deployment.yaml`
- `deploy/k8s/plain/frontend/deployment.yaml`

若使用公司自己的 Helm chart 或 Deployment template，必須加入相同 env
mapping；不能只建立 ConfigMap key 而未注入 container。

### 內部 CA mount

只設定 `gitlab-ca-bundle-path` 不會自動掛載憑證。若 GitLab 使用公司 CA，
先建立 CA Secret：

```bash
kubectl -n skillhub create secret generic skillhub-gitlab-ca \
  --from-file=ca.crt=company-root-and-intermediate-ca.pem \
  --dry-run=client -o yaml | kubectl apply -f -
```

在公司 overlay 加入 `gitlab-ca-patch.yaml`：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: skillhub-server
spec:
  template:
    spec:
      containers:
        - name: backend-python
          volumeMounts:
            - name: gitlab-ca
              mountPath: /etc/skillhub/gitlab-ca
              readOnly: true
      volumes:
        - name: gitlab-ca
          secret:
            secretName: skillhub-gitlab-ca
```

並在 overlay `kustomization.yaml` 加入：

```yaml
patches:
  - path: gitlab-ca-patch.yaml
```

確認 ConfigMap 的 `gitlab-ca-bundle-path` 為
`/etc/skillhub/gitlab-ca/ca.crt`。不要用 `NODE_TLS_REJECT_UNAUTHORIZED=0`、
`verify=false` 或停用 TLS 驗證來繞過 CA 問題。

## Compose 設定

使用 `compose.release.yml` 時，在 `.env.release` 加入：

```dotenv
SKILLHUB_COLLECTIONS_ENABLED=false
SKILLHUB_GITLAB_IMPORT_ENABLED=false
SKILLHUB_GITLAB_BASE_URL=https://gitlab.example.internal
SKILLHUB_GITLAB_ALLOWED_GROUPS=oss-mirrors,approved/tools
SKILLHUB_GITLAB_TOKEN=<read-only-gitlab-token>
SKILLHUB_GITLAB_CA_BUNDLE_PATH=
SKILLHUB_GITLAB_CONNECT_TIMEOUT_MS=5000
SKILLHUB_GITLAB_READ_TIMEOUT_MS=60000
SKILLHUB_GITLAB_ARCHIVE_MAX_BYTES=52428800
SKILLHUB_GITLAB_ARCHIVE_MAX_FILES=500
SKILLHUB_GITLAB_ARCHIVE_MAX_SINGLE_FILE_BYTES=5242880
SKILLHUB_GITLAB_ARCHIVE_MAX_EXPANDED_BYTES=52428800
SKILLHUB_GITLAB_IMPORT_MAX_CANDIDATES=100

SKILLHUB_WEB_COLLECTIONS_ENABLED=false
SKILLHUB_WEB_GITLAB_IMPORT_ENABLED=false
SKILLHUB_WEB_CLI_NPM_REGISTRY=https://nexus.example.internal/repository/npm-group/
SKILLHUB_WEB_CLI_PACKAGE=@company/skillhub
SKILLHUB_WEB_CLI_VERSION=0.1.10
```

若 Compose container 也需要公司 CA，需額外把 CA file read-only mount 到
backend service，並將 `SKILLHUB_GITLAB_CA_BUNDLE_PATH` 設為 container 內路徑。
不要只填 host 上的檔案路徑。

先驗證展開後的設定：

```bash
docker compose --env-file .env.release -f compose.release.yml config
```

## Nexus CLI release pipeline

本次功能需要發布包含 `collection install` 的客製化 CLI。Repository 已提供
專用 workflow：

- PR gate：`.github/workflows/pr-cli.yml`
- release：`.github/workflows/release-cli.yml`
- 操作細節：`cli/RELEASE.md`

在 GitHub repository 的 **Settings → Secrets and variables → Actions** 設定：

### Secret

- `NPM_TOKEN`：可寫入 Nexus hosted repository，並可從 group repository
  讀取的 automation token。

### Variables

- `NPM_PUBLISH_REGISTRY`：必要的 Nexus npm hosted URL。
- `NPM_INSTALL_REGISTRY`：必要的員工 Nexus npm group URL。
- `NPM_PACKAGE_NAME`：內部 package coordinate，例如 `@company/skillhub`。

正式 publish job 不接受 `NPM_REGISTRY` 或 npmjs fallback；publish 與 install
兩個 URL 任一缺少就會在寫入前失敗。

範例：

```text
NPM_PUBLISH_REGISTRY=https://nexus.example.internal/repository/npm-hosted/
NPM_INSTALL_REGISTRY=https://nexus.example.internal/repository/npm-group/
NPM_PACKAGE_NAME=@company/skillhub
```

### Runner 網路與憑證

`build-and-test` 保持使用 `ubuntu-latest`，不接觸 Nexus 或發布憑證。
`publish-npm` 固定使用具有 `self-hosted`、`linux`、`skillhub-nexus` 三個
labels 的受管 runner。這是 release control-plane 設定，不是 application env。

Runner 必須：

- 能解析 Nexus DNS 並連到 HTTPS port；
- 信任 Nexus 的公司 CA；
- 只允許 release workflow 使用具 publish 權限的 token；
- 具有 `npm`、Node.js 與 `sha256sum`；
- 讓 workflow 只把 token 寫入
  `${{ runner.temp }}/skillhub-cli-release.npmrc`，並由 `if: always()` step
  刪除該檔案。

若 Nexus 使用公司 CA，優先安裝到 runner OS/Node trust store；不要關閉 npm
`strict-ssl`。

### 發布順序

1. 合併包含 collection CLI 的 release PR。
2. 建立新的 `cli-vX.Y.Z` tag；不可重用已發布 version。
3. 先由 **Actions → Release CLI → Run workflow** 對既有 tag 執行
   `dry_run=true`。
4. 下載 `cli-package` artifact，核對 package name、version、source commit、
   tarball SHA-256 與內容。
5. 執行正式 workflow，發布同一份 immutable tarball 到 hosted repository。
6. 確認 workflow 分別由 hosted 與 group repository 下載該 version，且兩份
   tarball SHA-256 都等於 build artifact 的 SHA-256。
7. 完成 Nexus 驗證後，才更新 `web-cli-package` 與 `web-cli-version`。

正式驗證：

```bash
npm view @company/skillhub@0.1.10 version \
  --registry https://nexus.example.internal/repository/npm-group/

npx --yes \
  --registry https://nexus.example.internal/repository/npm-group/ \
  @company/skillhub@0.1.10 version

npx --yes \
  --registry https://nexus.example.internal/repository/npm-group/ \
  @company/skillhub@0.1.10 help collection
```

若 hosted publish 成功但 group lookup 失敗，修正 Nexus group membership、
content selector、routing/cache 或 read permission，再驗證同一 immutable
version；不要用同一版號重建或 republish 不同 bytes。

若 hosted 已存在同版號，workflow 仍會下載並核對 bytes；只要 digest 不同就
fail closed，不會因為 version 已存在而跳過驗證後宣告成功。

## 建議 rollout

### Phase 0：部署前檢查

1. 備份 PostgreSQL，記錄目前 backend/web image digest。
2. 確認四個 feature flags 都是 `false`。
3. Render manifests：

   ```bash
   kubectl kustomize deploy/k8s/base
   kubectl kustomize deploy/k8s/overlays/external
   ```

4. 在可連內部服務的執行環境驗證 GitLab 與 Nexus DNS/TLS。
5. 執行既有 SkillHub regression smoke：登入、search、單一 Skill install、
   scanner/publish workflow 與 `/api/v1/health`。

成功條件：舊功能維持正常，且 production 尚未出現 collection/GitLab UI。

### Phase 1：部署程式，保持功能關閉

部署新的 backend 與 web image，但所有 flags 仍為 `false`。Stock Python
backend image 的啟動命令會先執行：

```bash
uv run python -m app.migrations upgrade
```

這會新增 collection 與 repository import 所需的 additive `local_*` tables。
Pod 只有在 migration 成功後才會啟動 API。若公司將 container command
覆寫，必須在部署前以相同 image、database env 執行一次 migration Job。

```bash
kubectl apply -n skillhub -f deploy/k8s/base/secret.yaml
kubectl apply -k deploy/k8s/overlays/external/
kubectl rollout status deployment/skillhub-server -n skillhub --timeout=300s
kubectl rollout status deployment/skillhub-web -n skillhub --timeout=300s
```

驗證：

```bash
curl -fsS https://skillhub.example.internal/api/v1/health
curl -i https://skillhub.example.internal/api/web/namespaces/opensource/collections
```

第二個 request 在 backend flag 關閉時應回 `404`。再重跑 Phase 0 的既有
SkillHub regression smoke。

### Phase 2：發布 CLI 與填入 Web distribution 設定

完成 Nexus dry run、正式 publish 與 group lookup。填入三個
`web-cli-*` ConfigMap keys，但保持兩個 web feature flags 為 `false`。

成功條件：Nexus 可執行 `version` 與 `help collection`，SkillHub UI 尚未
顯示 collection routes。

### Phase 3：只啟用 backend collections

```yaml
collections-enabled: "true"
web-collections-enabled: "false"
gitlab-import-enabled: "false"
web-gitlab-import-enabled: "false"
```

套用 ConfigMap 後重啟 backend：

```bash
kubectl apply -k deploy/k8s/overlays/external/
kubectl rollout restart deployment/skillhub-server -n skillhub
kubectl rollout status deployment/skillhub-server -n skillhub --timeout=300s
```

使用具有適當權限的 API token 測試：

```bash
curl -fsS \
  -H "Authorization: Bearer ${SKILLHUB_API_TOKEN}" \
  https://skillhub.example.internal/api/web/namespaces/opensource/collections
```

成功條件：API 不再因 feature gate 回 `404`；既有 Skill API、scanner 與
single-skill CLI regression smoke 仍通過。

### Phase 4：啟用 Web collections

```yaml
web-collections-enabled: "true"
```

```bash
kubectl apply -k deploy/k8s/overlays/external/
kubectl rollout restart deployment/skillhub-web -n skillhub
kubectl rollout status deployment/skillhub-web -n skillhub --timeout=300s
curl -fsS https://skillhub.example.internal/runtime-config.js
```

確認：

- collection catalog 與 namespace maintenance routes 可見；
- `runtime-config.js` 包含已核准的 Nexus URL、package 與 exact version；
- `runtime-config.js` 不含 GitLab/Nexus token；
- `OWNER`/`ADMIN` 可維護，`MEMBER` 只能查看/安裝；
- 發布一個測試 collection 後，UI 產生含兩個 registry 的命令。

用臨時安裝目錄執行 transaction smoke：

```bash
npx --yes \
  --registry https://nexus.example.internal/repository/npm-group/ \
  @company/skillhub@0.1.10 \
  collection install @opensource/superpowers \
  --version 1.0.0 \
  --registry https://skillhub.example.internal \
  --dir /tmp/skillhub-collection-smoke \
  --json
```

成功條件：所有 members 安裝成功；故意製造一個 destination conflict 時，
命令在寫入前失敗，不留下半套 collection。

### Phase 5：只啟用 backend GitLab import

先確認：

- backend Pod 可解析並連到固定 GitLab HTTPS origin；
- CA file 存在於設定路徑；
- token 只讀且可讀 allowlisted mirror project；
- allowlist 沒有使用過寬的根 group；
- backend egress policy 允許 GitLab HTTPS。

```yaml
gitlab-import-enabled: "true"
web-gitlab-import-enabled: "false"
```

套用後重啟 backend，再用 curator API token preview 一個已核准的 mirror：

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${SKILLHUB_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"projectPath":"oss-mirrors/superpowers","ref":"main","upstreamUrl":"https://github.com/example/superpowers"}' \
  https://skillhub.example.internal/api/web/namespaces/opensource/repository-imports/preview
```

成功條件：

- response 記錄 immutable 40-character commit SHA；
- 只列出 archive 中找到的候選 `SKILL.md`；
- 不執行 repository script、hook 或其他 code；
- 不在 response、logs 或 runtime config 出現 GitLab token；
- allowlist 外的 project 回 `403`。

### Phase 6：啟用 Web GitLab import

```yaml
web-gitlab-import-enabled: "true"
```

套用並重啟 web。由 namespace collection maintenance 頁面完成一次：

1. preview；
2. 明確選擇候選 Skills；
3. ingest 到既有 scanner/review/publish workflow；
4. 只把實際 `PUBLISHED` versions 加入 collection draft；
5. 手動執行一次「檢查更新」。

成功條件：UI 不要求使用者輸入 GitLab host/token；更新檢查不會自動 ingest、
publish Skill 或 publish collection。

## Rollback

Feature rollback 依下列反向順序，每次 ConfigMap 變更後都重啟對應 workload：

1. `web-gitlab-import-enabled=false`，restart web。
2. `gitlab-import-enabled=false`，restart backend。
3. `web-collections-enabled=false`，restart web。
4. `collections-enabled=false`，restart backend。
5. 若仍有 regression，回退 backend/web image 到 rollout 前 digest。

若只需要停止宣傳有問題的 CLI，清空三個 `web-cli-*` 值或改回上一個已驗證的
exact version，然後 restart web。已發布到 Nexus 的 immutable package 不需
刪除。

不要 drop 下列 additive tables：

- `local_collection`
- `local_collection_version`
- `local_collection_version_member`
- `local_repository_import`
- `local_repository_import_candidate`

既有 Skill core functions 不依賴這些 tables。保留它們可維持 provenance、
audit 與未完成 draft evidence，也讓 feature flags 可安全重新啟用。

## Token 輪替

### GitLab token

1. 建立同樣 read-only scope 的 replacement token。
2. 更新 `skillhub-secret/gitlab-token`。
3. Restart backend。
4. 執行 allowlisted preview 與 allowlist-deny smoke。
5. 確認 logs 無 credential。
6. 最後才撤銷舊 token。

### Nexus token

1. 建立 hosted-write/group-read replacement token。
2. 更新 GitHub Actions `NPM_TOKEN` secret。
3. 執行 CLI package `dry_run`。
4. 用新的 exact version 完成一次正式 publish 與 group verification。
5. 最後才撤銷舊 token。

## 常見問題

| 症狀 | 檢查 |
| --- | --- |
| Collection API 回 `404` | Backend `SKILLHUB_COLLECTIONS_ENABLED` 是否為 `true`，以及 backend 是否已 restart。 |
| GitLab API 回 `404` | Collections 與 backend GitLab import 兩個 flags 都必須為 `true`。 |
| GitLab API 回 `503` | `base-url`、`allowed-groups`、`gitlab-token` 是否都有值。 |
| GitLab project 回 `403` | Project path 是否符合 allowlisted prefix，token 是否有 project read 權限。 |
| GitLab 回 `422` | Base URL 是否為直接 HTTPS origin；project path/ref 格式是否正確。 |
| GitLab 回 `502`/`504` | DNS、egress、CA chain、GitLab API/archive latency 與 timeout。 |
| Backend Pod 卡在啟動 | 查看 migration output：`kubectl logs deployment/skillhub-server -n skillhub -c backend-python`。 |
| UI 沒有 collection routes | Web flag 是否為 `true`，web Pod 是否已 restart。 |
| UI 有 collection 但沒有安裝命令 | 三個 `web-cli-*` 值是否完整，version 是否為 exact version 而非 `latest`。 |
| `npx` 找不到 package | 第一個 registry 是否為 Nexus group、scope/package name 是否正確、group 是否包含 hosted repository。 |
| CLI 無法解析 collection | 第二個 registry 是否為 SkillHub base URL、CLI token 是否可讀該 namespace、collection 是否已 `PUBLISHED`。 |
| Nexus publish 成功但 group 查不到 | Group membership、content selector、routing/cache、read permission；不要 republish 同版號。 |

## 上線簽核清單

- [ ] 新 backend/web images 以 flags-off 狀態通過既有 core regression smoke。
- [ ] Python-owned migrations 成功，沒有 Java/Maven/Spring runtime。
- [ ] GitLab URL 是固定 HTTPS origin，redirect、DNS、egress 與 CA 已驗證。
- [ ] GitLab token 只有 `read_api`/`read_repository`，且只存在 backend Secret。
- [ ] GitLab group allowlist 已由 namespace/platform owner 審核。
- [ ] CLI workflow dry run 的 package、source commit 與 SHA-256 已留存。
- [ ] 新 CLI exact version 已經由 Nexus group 驗證。
- [ ] Web runtime config 沒有任何 token，且不使用 `latest`。
- [ ] 四個 flags 已依 backend → web 的順序逐步啟用。
- [ ] Collection transaction install 與 rollback smoke 通過。
- [ ] GitLab preview、allowlist deny、manual update check smoke 通過。
- [ ] 每一 phase 後都重跑 login/search/single-skill/scanner/publish core smoke。
- [ ] Rollback image digest、flag 操作人與 token owner 已記錄。

## 相關文件

- [K8s deployment README](README.md)
- [K8s 環境變數完整清單](environment-variables.zh.md)
- [CLI release guide](../../cli/RELEASE.md)
- [Collections 使用與治理說明](../../docs/skillhub/guide/collections.md)
- [最終驗證結果](../../docs/backend-python-maintenance/results/2026-07-27-skill-collections-final-verification.md)
