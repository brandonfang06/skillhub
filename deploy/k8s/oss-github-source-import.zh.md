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

三個 endpoints 都只接受 `st_` service token，且 token 必須包含
`source:import` scope。一般使用者的 `sk_` personal token 即使屬於
`SUPER_ADMIN` 也會被拒絕；pipeline 不需要、也不應取得觸發者的 SkillHub token。

Platform Admin 先登入 SkillHub，開啟 `/admin/service-principals`（subpath 部署時為
`/skillhub/admin/service-principals`）：

1. 建立 ACTIVE service principal，例如 code `gitlab-oss-importer`。
2. 建立 scope 為 `source:import` 的 token。限時 token 最長可設定為建立日起 3 個曆年，
   頁面會顯示當下最晚可選日期；若 GitLab automation 必須使用固定憑證，也可由管理員
   明確選擇「永不到期」。永不到期 token 會持續有效，直到被撤銷或 principal 停用，
   因此必須另有定期輪替與撤銷程序。
3. raw `st_` token 只顯示一次，立即存入 GitLab masked、protected variable
   `SKILLHUB_SERVICE_TOKEN`，不要寫入 repository、job log 或 artifact。
4. 限時 token 應在到期前從同頁輪替；永不到期 token 也應依組織排程定期輪替。先更新
   GitLab variable 並驗證，再撤銷舊 token。緊急事件可停用
   principal，所有 token 會立即停止通過驗證；不需要停用建立它的管理員帳號。

管理 API 位於 `/api/v1/admin/service-principals`，只接受登入中的 `SUPER_ADMIN`
session，不接受 personal 或 service bearer token。Service principal 是獨立身分；建立它的
admin 只記錄為管理操作人，admin 日後離職、停權或失去角色不會自動撤銷 service token。

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
| `SKILLHUB_SERVICE_TOKEN` | Platform Admin 建立的 `st_`、`source:import` service token；設為 masked/protected。`SKILLHUB_API_TOKEN` 不會 fallback。 |
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

Skill detail 會依選定版本顯示 `Imported by`，人名來自
`SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME` 對應的 SkillHub user；若 trigger 無法對應，
則顯示實際代為提交 review 的 namespace owner。Service token 所屬的
service principal 只是 audit actor，不是版本的人類匯入者。後續他人重新匯入
只會更新新版本的 importer attribution，不會改變 skill owner。

## Exit code 與故障排查

| Exit | 意義 |
| --- | --- |
| `0` | 全部 imported／skipped。 |
| `2` | 設定錯誤或缺變數。 |
| `3` | discovery、package 或 validation 失敗。 |
| `4` | 缺少／無效／過期／已撤銷的 service token，或缺少 `source:import` scope。 |
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
