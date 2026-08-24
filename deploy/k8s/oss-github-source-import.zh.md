# GitHub OSS Skills 匯入 GitLab Pipeline 中文 SOP

這套流程適用於 GitHub repository **已搬入 internal GitLab** 的來源 project。使用者在
這個 internal GitLab project 觸發 pipeline，輸入原始 GitHub repository URL 作為 upstream
identity；pipeline 內的 shell 呼叫 project 內的 Python 檔案，由 Python `git clone` 自己的
internal GitLab repository、尋找每個 exact-case `SKILL.md`、ZIP 打包及呼叫 SkillHub API。

GitHub URL 只用於 upstream provenance、namespace slug 與 display name；Runner 不連 GitHub，
也不會從使用者輸入的 GitHub URL 下載內容。

Pipeline 成功只代表 skills 已安全匯入或判定可略過，並進入 scanner／namespace owner
review；不代表已直接發布。新版本仍停在 `PENDING_REVIEW`，通過既有 review 才會公開。

## 1. 實際執行方式

```text
GitLab Runner shell
  -> deploy/gitlab/oss-source-import.sh
  -> python tools/oss-source-importer/run_import.py
  -> git clone 自己的 `CI_REPOSITORY_URL`，checkout `CI_COMMIT_SHA`
  -> Python discovery、ZIP 與 httpx client
  -> SkillHub 公開 reverse proxy／Ingress
  -> Python FastAPI backend 的 /api/cli/v1/source-imports/... API
```

- `.sh` 與 `.py` 放在執行 pipeline 的 internal GitLab project。
- Shell 只安裝鎖定的 Python runtime dependencies，然後執行 project 內的 Python 檔案；
  discovery、ZIP、API error handling 與 report 都由 Python 負責。
- 這**不是一般 SkillHub CLI**，不需要 TypeScript/Bun `cli/`、`skillhub login`、
  `skillhub publish` 或 OAuth Device Flow。
- 正式匯入不使用 `curl`。Python `httpx` 統一處理 service token、multipart ZIP、metadata、
  `requestId`、idempotent outcome 與 JSON report；`curl` 只適合人工 health check。
- Importer 不直接連 PostgreSQL、Redis、MinIO/S3 或 scanner，也不操作 React frontend。

Runtime image 只需固定提供 Python 3.12、Git、CA certificates 與 POSIX shell，不包含
importer 程式。因此 importer 改版只要更新 GitLab project，不必重 build importer image。
GitLab Docker executor 仍需清空 runtime image entrypoint：

```yaml
image:
  name: "$SKILLHUB_PYTHON_IMAGE"
  entrypoint: [""]
script:
  - /bin/sh "$CI_PROJECT_DIR/deploy/gitlab/oss-source-import.sh"
```

## 2. SkillHub backend 與服務前置條件

Python backend 必須已套用 source-import migration，並提供：

- `PUT /api/cli/v1/source-imports/namespaces/{namespaceSlug}`
- `POST /api/cli/v1/source-imports/{namespaceSlug}/skills/validate`
- `POST /api/cli/v1/source-imports/{namespaceSlug}/skills`

正式驗證時 PostgreSQL、Redis、MinIO/S3、scanner、backend 與 reverse proxy 都必須實際
啟動；只跑 mocked unit test 不算完整驗收。

三個 endpoints 只接受 `st_` service token，且 token 必須有 `source:import` scope。
即使 `sk_` personal token 的 user 是 `SUPER_ADMIN` 也會被拒絕；pipeline 不需要取得觸發者
自己的 SkillHub bearer token。Service principal 只是 audit actor，不是 skill owner 或版本
的人類匯入者。

Platform Admin 在 `/admin/service-principals` 建立 ACTIVE principal 與 token；公開 subpath
部署則開 `/skillhub/admin/service-principals`。限時 token 最長為建立日起 **3 個曆年**，
也可明確選擇**永不到期**。Raw `st_` token 只顯示一次，應立刻存成 GitLab masked、
protected variable。無論是否到期，都要有定期**輪替**與緊急**撤銷**程序；先更新並驗證
新 token，再撤銷舊 token。

### `SKILLHUB_BASE_URL`

建議填使用者平常開啟的公開 application base：

```text
SKILLHUB_BASE_URL=https://skillhub.example.com/skillhub
實際 API=https://skillhub.example.com/skillhub/api/cli/v1/source-imports/...
```

Importer 不會進 frontend；公開 reverse proxy／Ingress 會處理 `/skillhub` prefix 並把
`/api/...` 導向 Python FastAPI backend。若 Runner 位於同一 Kubernetes network，也可填
`http://skillhub-server.skillhub.svc.cluster.local:8080`，但直接打 backend 時不要附加
公開 `/skillhub` prefix。

## 3. Identity、owner 與 review 規則

`SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE` 通常固定為 `keycloak`。`tsso` 是 Keycloak
OAuth client ID，不是 SkillHub provider code，所以不要填入 provider 變數。Owner 與
trigger login 都填 Keycloak `preferred_username`；SkillHub 以
`oauth_identity.provider_code + login_name` 精確查找。

常見 backend OIDC 對應：

```text
SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI=<realm issuer>
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID=tsso
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_SECRET=<secret>
```

固定 fallback owner 必須已登入 SkillHub，identity 為 ACTIVE 且唯一。觸發者的
`preferred_username` 若能對應到 ACTIVE user，會成為該版本的 `Imported by`；找不到時由
namespace owner 代為提交 review。後續不同使用者重跑只會改變新版本的 importer attribution，
不會改變 skill owner，也不會繞過 namespace owner review。

Skill detail 會依**選定版本**顯示這個 `Imported by`。在此流程中，service principal 只是 audit actor；
它不會改變 skill owner，也不會被顯示成人類匯入者。

## 4. GitLab variables

### 必填

| Variable | 範例／用途 |
| --- | --- |
| `SKILLHUB_PYTHON_IMAGE` | Immutable Python 3.12 + Git runtime image，例如 `registry.example/python-git@sha256:<digest>`；不用 `latest`。 |
| `SKILLHUB_BASE_URL` | 例如 `https://skillhub.example.com/skillhub`；不要自行加 `/api`。 |
| `SKILLHUB_SERVICE_TOKEN` | Platform Admin 建立的 `st_`、`source:import` token；設為 masked/protected。`SKILLHUB_API_TOKEN` 不會 fallback。 |
| `SKILLHUB_SOURCE_REPOSITORY_URL` | 使用者每次 pipeline 輸入的原始 GitHub URL，例如 `https://github.com/mattpocock/skills`；只用於 upstream identity/provenance 與 namespace 命名，不用來 clone。 |
| `SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE` | 固定 fallback owner provider，通常為 `keycloak`。 |
| `SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME` | 固定 fallback owner 的 Keycloak `preferred_username`。 |

`https://github.com/mattpocock/skills` 會轉成 namespace slug
`oss-mattpocock-skills`，display name 為 `OSS-mattpocock-skills`，只有 `OSS` 大寫。

### 選填

| Variable | 預設／用途 |
| --- | --- |
| `SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE` | 預設與 owner provider 相同。 |
| `SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME` | 可信觸發流程提供的使用者 `preferred_username`。 |
| `SKILLHUB_IMPORT_SOURCE_ROOT` | Clone 後 repo 內的相對子路徑；預設 `.`。絕對路徑與 `..` escape 會被拒絕。 |
| `SKILLHUB_IMPORT_REPORT_PATH` | 預設 `skillhub-oss-import-report.json`。 |
| `SKILLHUB_IMPORT_RUNTIME_DIR` | 預設目前 project 下的 `.skillhub-import-runtime`；project mount 唯讀時可指定可寫暫存目錄。 |
| `SKILLHUB_IMPORT_TIMEOUT_SECONDS` | 單次 HTTP timeout，預設 `60` 秒。 |
| `PIP_INDEX_URL`／`PIP_CERT` | 組織使用內部 Python package mirror／CA 時設定。 |
| `SSL_CERT_FILE` | Internal GitLab 或 SkillHub TLS 需額外企業 CA bundle 時設定。 |

GitLab 自動提供的變數有不同用途：

- `CI_PROJECT_DIR` 是目前 internal GitLab project 的 Runner checkout，也是 `.sh`、`.py`
  與 lock file 的位置。
- `CI_REPOSITORY_URL` 是目前 project 的 internal GitLab HTTPS clone URL。它通常帶短效
  `CI_JOB_TOKEN` credential，只交給 `git` 使用，不會送到 SkillHub、寫入 report 或錯誤訊息。
- `CI_COMMIT_SHA` 是本次要匯入的 internal GitLab source commit。Python 會 shallow-fetch
  這個 exact 40-hex SHA，checkout 後再以 `git rev-parse HEAD` 驗證一致。
- `CI_COMMIT_TAG` 優先表示 TAG；否則 `CI_COMMIT_BRANCH` 表示 BRANCH；detached pipeline
  則以 COMMIT 記錄。`CI_COMMIT_REF_NAME` 供操作人確認 GitLab pipeline 選取的 ref。
- `CI_PIPELINE_ID`、`CI_JOB_ID` 用於 report 與 audit trace。

Fallback version `git-<40-char-SHA>`、backend provenance、tag／branch 資訊都使用這次
internal GitLab pipeline 的 source checkout。若希望 SkillHub 的 GitHub exact-commit link
可直接開啟，GitHub 搬入 internal GitLab 時必須保留原始 Git commit SHA，不可重寫 history。

## 5. Internal GitLab source project 設定

執行 pipeline 的 project 保留以下檔案：

```text
deploy/gitlab/oss-source-import.yml
deploy/gitlab/oss-source-import.sh
tools/oss-source-importer/run_import.py
tools/oss-source-importer/requirements-runtime.txt
tools/oss-source-importer/src/skillhub_oss_importer/...
```

`.gitlab-ci.yml` 可以用同 project 的 local include：

```yaml
stages:
  - publish

include:
  - local: /deploy/gitlab/oss-source-import.yml

variables:
  SKILLHUB_PYTHON_IMAGE: registry.example/python-git@sha256:<digest>
  SKILLHUB_BASE_URL: https://skillhub.example.com/skillhub
  SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE: keycloak
  SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME: platform-skill-owner
```

在 GitLab **Run pipeline** 頁面，使用者至少輸入：

```text
SKILLHUB_SOURCE_REPOSITORY_URL=https://github.com/mattpocock/skills
SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE=keycloak
SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME=<觸發者的 preferred_username>
```

Branch/tag 不用另設 source variable；在 GitLab **Run pipeline** 頁面的 ref selector 選擇，
GitLab 會提供對應的 `CI_COMMIT_SHA`、`CI_COMMIT_TAG`、`CI_COMMIT_BRANCH` 與
`CI_COMMIT_REF_NAME`。

`SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME` 必須由可信登入／觸發流程帶入，不能把任意 display name
當作已驗證身分。Pipeline 實際只需執行：

```sh
/bin/sh "$CI_PROJECT_DIR/deploy/gitlab/oss-source-import.sh"
```

Wrapper 使用 `pip --require-hashes` 安裝 `requirements-runtime.txt`，再呼叫：

```sh
python "$CI_PROJECT_DIR/tools/oss-source-importer/run_import.py" \
  --json-report "$SKILLHUB_IMPORT_REPORT_PATH"
```

Report artifact 採 `when: always`，包含 upstream GitHub repository identity、internal GitLab
source commit/ref、namespace、
pipeline/job ID、每個 source path 的 validation/submission outcome、coordinate、version、review
task 與 `requestId`，不含 service token。

## 6. Import 與 review SOP

1. Python 使用 `CI_REPOSITORY_URL` 在暫存目錄初始化 checkout，以 `CI_COMMIT_SHA` 做
   shallow fetch 與 detached checkout；不抓 submodules，也不連 GitHub。
2. 找出 exact-case `SKILL.md`；每個 parent folder 各自打 ZIP。Nested skill root 獨立打包，
   不會重複塞入 parent ZIP。
3. 沒有 explicit version 時使用 `git-<真正 source 40-hex commit>`，不修改來源檔。
4. Ensure namespace 一次，再先 validate 全部 packages；任何 validation 失敗時提交數必須是 0。
5. Validation 全通過後循序提交。Scanner 與 namespace owner review 都走既有流程。
6. Namespace owner 檢查內容、scanner 結果與 source exact-commit provenance 後才 approve。
7. 重跑相同 commit/content 回 `SKIPPED_ALREADY_IMPORTED` 或 `SKIPPED_UNCHANGED`，視為成功，
   不建立 duplicate version。

## 7. Exit code 與排錯

| Exit | 意義 |
| --- | --- |
| `0` | 全部 imported／skipped。 |
| `2` | 缺少或錯誤的 variables。 |
| `3` | Git clone、discovery、package 或 validation 失敗。 |
| `4` | Service token 無效、過期、已撤銷或缺少 `source:import`。 |
| `5` | DNS、timeout、TLS 等 transport failure。 |
| `6` | 部分提交；查看 report 後以相同 GitLab commit 安全重跑。 |
| `10` | 未預期 importer 錯誤。 |

- `0 個 SKILL.md`：確認檔名大小寫及 `SKILLHUB_IMPORT_SOURCE_ROOT` 是否指向 clone 內子目錄。
- Clone 失敗：確認 `CI_REPOSITORY_URL` 可由 job token 讀取、`CI_COMMIT_SHA` 存在，且 Runner
  有 Git、internal GitLab DNS 與企業 CA。
- Identity not found／disabled／ambiguous：確認 provider 為 `keycloak`、login 是 exact
  `preferred_username`，user 已登入且 identity 為 ACTIVE、唯一。
- Namespace/source collision：同一 namespace 不能綁不同 GitHub repository。
- Explicit-version conflict：來源同版號但內容不同時應在 upstream 提升 version，不能覆寫。
- 憑證錯誤：補完整企業 CA chain，依連線位置設定 `SSL_CERT_FILE`、`PIP_CERT`。
- 部分提交：不要人工刪資料；保留 report，以相同 GitLab commit 重跑，已成功項目會 idempotent skip。
- SQL／500：用 report 的 `requestId` 查 backend log，再確認 migration、PostgreSQL、Redis、
  MinIO/S3 與 scanner 都健康。
