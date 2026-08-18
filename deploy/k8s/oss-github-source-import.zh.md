# GitHub OSS Skills 匯入 GitLab Pipeline SOP

這個流程適用於「使用者把 GitHub repository 放到 GitLab，並由 GitLab Runner
將其中每個 `SKILL.md` 所在資料夾送進 SkillHub」的情境。Importer 是獨立的
Python 3.12 batch image；它只讀 `CI_PROJECT_DIR` 既有 checkout，不會自行 clone、
刪除遠端已移除的 skill，也不會繞過 scanner 或 namespace owner review。

Pipeline 成功表示 skill 已匯入或判定為可安全略過，並進入 scanner／review；
不表示已發布。公開前仍會停在 `PENDING_REVIEW`。

## SkillHub backend 前置條件

先部署包含 source-import migration 與下列 endpoints 的 Python backend：

- `PUT /api/cli/v1/source-imports/namespaces/{namespaceSlug}`
- `POST /api/cli/v1/source-imports/{namespaceSlug}/skills/validate`
- `POST /api/cli/v1/source-imports/{namespaceSlug}/skills`

三個 endpoints 都只接受 bearer API token，且同時要求：

- token scope：`source:import`
- token 所屬 user 的 platform role：`SKILL_ADMIN` 或 `SUPER_ADMIN`

一般 token UI／device login 常用的 `skill:read`、`skill:publish` 不會自動包含
`source:import`，而且這三個 endpoints 本身不要求那兩個普通 scopes。請建立專用
service account，授予最小平台角色，再以該帳號的登入 session 呼叫：

```http
POST /api/v1/tokens
Content-Type: application/json

{"name":"GitLab OSS Importer","scopes":["source:import"]}
```

若服務在 `/skillhub`，實際 URL 是 `/skillhub/api/v1/tokens`。回應中的 raw token
只顯示一次；立即存入 GitLab masked、protected variable `SKILLHUB_API_TOKEN`，不要
寫入 repository、job log 或 artifact。

### Keycloak／TSSO 名稱對應

`SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE` 與 trigger provider 應填 SkillHub identity
provider code `keycloak`。`tsso` 是
`SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID` 的值，不是 provider
code，所以不要把 `tsso` 填入 provider 變數。Owner／trigger login 填 Keycloak
`preferred_username`，SkillHub 會用 `oauth_identity.provider_code + login_name` 精確查找。

確認 backend OIDC 設定至少對齊：

```text
SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_KEYCLOAK_ISSUER_URI=<realm issuer>
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_ID=tsso
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_KEYCLOAK_CLIENT_SECRET=<secret>
```

固定 fallback owner 必須已登入過 SkillHub、identity 為 ACTIVE，且同一組
`keycloak + preferred_username` 只能有一筆。Namespace 建立後的 ownership 變更會被
保留；後續 pipeline trigger 不會接管既有 skill owner。

## GitLab variables

### 必填

| Variable | 範例與用途 |
| --- | --- |
| `SKILLHUB_IMPORTER_IMAGE` | `registry.example/skillhub-oss-source-importer:0.1.0` 或 digest；必須 immutable，不用 `latest`。 |
| `SKILLHUB_BASE_URL` | `https://skillhub.example.com/skillhub`；保留 `/skillhub`，不加 `/api`。 |
| `SKILLHUB_API_TOKEN` | 專用 `source:import` token；設為 masked/protected。 |
| `SKILLHUB_SOURCE_REPOSITORY_URL` | 使用者輸入的 HTTPS GitHub URL，例如 `https://github.com/mattpocock/skills`。目前只接受 `github.com`。 |
| `SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE` | 通常固定 `keycloak`。 |
| `SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME` | 固定 fallback owner 的 Keycloak `preferred_username`。 |

`https://github.com/mattpocock/skills` 會固定轉成 namespace slug
`oss-mattpocock-skills`，display name 為 `OSS-mattpocock-skills`；只有 `OSS` 大寫。

### 選填

| Variable | 預設／用途 |
| --- | --- |
| `SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE` | 預設跟 owner provider 相同。 |
| `SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME` | 觸發者的 `preferred_username`；找不到時由現有 namespace owner 提交 review。 |
| `SKILLHUB_IMPORT_SOURCE_ROOT` | `CI_PROJECT_DIR` 內的相對或絕對子路徑；預設整個 checkout。 |
| `SKILLHUB_IMPORT_REPORT_PATH` | 預設 `skillhub-oss-import-report.json`。 |
| `SKILLHUB_IMPORT_TIMEOUT_SECONDS` | 單次 HTTP timeout，預設 `60`。 |
| `SSL_CERT_FILE` | 企業 CA bundle；只有內部 TLS CA 不被 base image 信任時才設定。 |

GitLab 會提供 `CI_PROJECT_DIR`、`CI_COMMIT_SHA`、`CI_COMMIT_TAG`、
`CI_COMMIT_BRANCH`、`CI_COMMIT_REF_NAME`、`CI_PIPELINE_ID`、`CI_JOB_ID`。Importer
會先確認 `git -C $CI_PROJECT_DIR rev-parse HEAD` 等於 40-hex `CI_COMMIT_SHA`，再做
任何 API mutation。Tag 優先，其次 branch；detached checkout 以 COMMIT 記錄。

## Pipeline 使用方式

把本 repo 的 `deploy/gitlab/oss-source-import.yml` 複製或以 GitLab include 引入。
組織自己的 pipeline 必須明確提供使用者輸入的 GitHub URL；不要把它寫死成
`mattpocock/skills`。

```yaml
include:
  - project: platform/skillhub
    ref: v0.1.0
    file: /deploy/gitlab/oss-source-import.yml

variables:
  SKILLHUB_IMPORTER_IMAGE: registry.example/skillhub-oss-source-importer@sha256:<digest>
  SKILLHUB_BASE_URL: https://skillhub.example.com/skillhub
  SKILLHUB_IMPORT_REPORT_PATH: skillhub-oss-import-report.json
  SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE: keycloak
  SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME: platform-skill-owner

skillhub_oss_import:
  variables:
    SKILLHUB_SOURCE_REPOSITORY_URL: $USER_SELECTED_GITHUB_REPOSITORY_URL
    SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE: keycloak
    SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME: $PIPELINE_TRIGGER_PREFERRED_USERNAME
```

`PIPELINE_TRIGGER_PREFERRED_USERNAME` 是組織自行從可信觸發流程傳入的變數；GitLab
不保證內建變數就是 Keycloak `preferred_username`。不要用未驗證的 display name。

Job 只需執行：

```bash
skillhub-oss-import --json-report "$SKILLHUB_IMPORT_REPORT_PATH"
```

Report artifact 使用 `when: always`，會包含 repository、commit/ref、namespace、
pipeline/job ID、每個 source path 的 validation/submission outcome、coordinate、version、
review task 與 `requestId`，但不含 token。

## 執行與 review SOP

1. Importer 找 exact-case `SKILL.md`，每個 parent folder 產生一包；nested skill root
   會獨立打包，不會被重複塞進 parent ZIP。
2. 沒有 version 時使用 `git-<完整 40 字元 commit SHA>`，不修改來源 `SKILL.md`。
3. Namespace 只 ensure 一次，接著先 validate 全部 package。任何 validation 失敗時
   提交數必須是 0。
4. Validation 全通過後循序提交。Scanner 與 namespace owner review 都照既有流程。
5. Namespace owner 到既有 review 頁檢查內容、scanner 結果與 GitHub exact-commit
   provenance，確認後才 approve。
6. 重跑相同 commit/content 會回 `SKIPPED_ALREADY_IMPORTED` 或
   `SKIPPED_UNCHANGED`，視為成功；不會新增 duplicate version。

## Exit code 與故障排查

| Exit | 意義 |
| --- | --- |
| `0` | 全部 imported／skipped。 |
| `2` | 設定錯誤或缺變數。 |
| `3` | discovery、package 或 validation 失敗。 |
| `4` | token、scope 或 platform role 不符。 |
| `5` | DNS、timeout、TLS 等 transport failure。 |
| `6` | 部分提交；查看 report 後安全重跑。 |
| `10` | 未預期 importer 錯誤。 |

- identity not found／disabled／ambiguous：確認該 user 已登入、provider 是 `keycloak`、
  login 是 exact `preferred_username`，且 identity 為 ACTIVE 且唯一。
- namespace/source collision：同一 namespace 不可綁不同 GitHub repository；確認使用者
  輸入 URL 與 slug 規則。
- explicit-version conflict：來源宣告同版號但內容不同時必須改 upstream version，不能覆寫。
- `0 個 SKILL.md`：檢查大小寫必須是 `SKILL.md`，以及 `SKILLHUB_IMPORT_SOURCE_ROOT`。
- commit mismatch：Runner checkout 與 `CI_COMMIT_SHA` 不一致；不要略過驗證。
- 憑證錯誤：把完整企業 CA chain 以 file variable 掛入 image，並設定 `SSL_CERT_FILE`。
- 部分提交：不要人工刪資料；保留 report，以相同 commit 重跑，已成功項目會 idempotent skip。
- SQL／500：用 report 的 `requestId` 對 backend log，再檢查 migration、PostgreSQL、Redis、
  MinIO/S3 與 scanner 是否都健康。
