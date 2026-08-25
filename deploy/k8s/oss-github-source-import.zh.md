# 中央 GitLab Pipeline 匯入 OSS Skills 中文 SOP

本流程適用於組織的 `pull-pipeline-for-user` 呼叫中央 `pull_pipeline`，由 `pull_code`
確認掃描通過並把內容落地至 Dev GitLab，下一個 `publish_skillhub` stage 才將該不可變版本
送入 SkillHub。SkillHub stage 不直接讀外部 OSS GitLab 或 GitHub，也不相信不同 job 共用的
filesystem。

```text
pull-pipeline-for-user
  -> 中央 pull_pipeline
  -> scan
  -> pull_code
       驗證 scan 通過
       將接受的內容推到 Dev GitLab
       產生 pull-code.env dotenv artifact
  -> publish_skillhub
       從 Dev GitLab clone 精確 commit
       驗證 checkout SHA 與 scan SHA
       呼叫 SkillHub source-import API
  -> SkillHub scanner
  -> namespace owner review
```

Pipeline 成功只表示 skills 已建立或安全略過並進入既有 review 流程，不代表直接發布。
新版本仍為 `PENDING_REVIEW`，必須通過 scanner 與 namespace owner review 才能公開。

## 1. 中央 repo 與 runtime

下列檔案必須存在於執行 `pull_pipeline` 的中央 repo：

```text
deploy/gitlab/oss-source-import.yml
deploy/gitlab/oss-source-import.sh
tools/oss-source-importer/run_import.py
tools/oss-source-importer/src/skillhub_oss_importer/...
```

GitLab Runner 會把中央 repo checkout 到 `CI_PROJECT_DIR`，所以 job 可直接執行中央 repo 內的
Python 檔案；不需要 mount 程式碼進 image。GitLab 的 remote `include` 只載入 YAML，不會把
Python 檔案複製到另一個 project，因此 `.sh` 與 `.py` 必須確實存在於中央 pipeline checkout。

Runtime image 只需提供：

- Python 3.8；
- Git；
- CA certificates 與組織信任鏈；
- POSIX shell。

Importer 的正式 runtime 只用 Python 標準函式庫，不使用 `curl`，也不執行 `pip install`。
`pytest` 與 `ruff` 僅為開發驗證工具，不是 production job dependency。既有 runner image
只要已具備 Python、Git、shell 與憑證即可，不需另外 build SkillHub importer image。

```text
GitLab Runner shell
  -> 中央 repo 內的 Python 檔案
  -> git clone Dev GitLab protected branch
  -> 公開 reverse proxy／Ingress
  -> Python FastAPI backend
```

Docker executor 必須清除 runtime image 的預設 entrypoint：

```yaml
image:
  name: "$SKILLHUB_PYTHON_IMAGE"
  entrypoint: [""]
```

Shell 只做 Python／Git preflight，然後執行：

```sh
python "$CI_PROJECT_DIR/tools/oss-source-importer/run_import.py" \
  --json-report "$SKILLHUB_IMPORT_REPORT_PATH"
```

這不是一般 SkillHub CLI，不需要 TypeScript/Bun、`skillhub login`、OAuth Device Flow 或
安裝 `skillhub-oss-import` console command。

## 2. GitLab stage 串接

中央 `.gitlab-ci.yml` 必須把 `pull_code` 放在 `publish_skillhub` 前面，並讓它輸出
`pull-code.env`。範例中的 pull script 是組織既有實作，需替換成實際路徑：

```yaml
stages:
  - scan
  - pull_code
  - publish_skillhub

include:
  - local: /deploy/gitlab/oss-source-import.yml

pull_code:
  stage: pull_code
  script:
    - /bin/sh "$CI_PROJECT_DIR/ci/pull-code.sh"
  artifacts:
    reports:
      dotenv: pull-code.env
    paths:
      - pull-code.env
```

`deploy/gitlab/oss-source-import.yml` 已定義：

```yaml
skillhub_oss_import:
  stage: publish_skillhub
  needs:
    - job: pull_code
      artifacts: true
```

因此 `pull_code` 失敗、scan 未通過、dotenv 不存在或 artifact 無法下載時，SkillHub job
不應執行。不要把 `pull_code` 設成允許失敗，也不要讓 `skillhub_oss_import` 成為可跳過
scan gate 的手動 job。

## 3. pull_code dotenv 契約

`pull_code` 必須以可信任的單行值產生以下 artifact；不得把 access token、credentialed URL
或換行字元寫進 dotenv：

```dotenv
SKILLHUB_SOURCE_REPOSITORY_URL=https://github.com/example/skills
SKILLHUB_SOURCE_REF_TYPE=BRANCH
SKILLHUB_SOURCE_REF=main
SKILLHUB_DEV_GITLAB_REPOSITORY_URL=https://gitlab.example/dev/example-skills.git
SKILLHUB_DEV_GITLAB_BRANCH=main
SKILLHUB_SOURCE_SCAN_STATUS=PASSED
SKILLHUB_SOURCE_SCAN_ID=scan-12345
SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE=keycloak
SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME=alice
```

`pull-code.env` 檔案本身是 publish job 的**唯一可信來源**。GitLab 仍會把 dotenv report
匯出成環境變數，但 trigger、project、group 或 instance variables 的優先序可能更高，不能只讀
環境變數判斷 scan gate。Importer 會直接讀取 `$CI_PROJECT_DIR/pull-code.env`，限制檔案必須
位於中央 checkout、只包含下表允許的 keys、不得重複且不超過 64 KiB；任何同名環境變數與
artifact 不一致都會 fail fast。不要在 project/group variables 預先定義這些 handoff keys。

| Variable | 規則 |
| --- | --- |
| `SKILLHUB_SOURCE_REPOSITORY_URL` | 原始、無 credential 的 `https://github.com/<owner>/<repo>`；GitHub URL 只用於 upstream provenance、namespace 命名與 UI 連結。 |
| `SKILLHUB_SOURCE_REF_TYPE` | 只能是 `TAG`、`BRANCH` 或 `COMMIT`。 |
| `SKILLHUB_SOURCE_REF` | `TAG`／`BRANCH` 必填；`COMMIT` 必須留空。 |
| `SKILLHUB_DEV_GITLAB_REPOSITORY_URL` | `pull_code` 落地後的無 credential HTTPS clone URL；HTTP 會被拒絕，避免 job token 明文傳輸。 |
| `SKILLHUB_DEV_GITLAB_BRANCH` | `pull_code` 落地的 Dev GitLab protected branch；只能由受控落地流程更新。 |
| `SKILLHUB_SOURCE_SCAN_STATUS` | 必須精確為 `PASSED`，其他值 fail fast。 |
| `SKILLHUB_SOURCE_SCAN_ID` | 選填；寫入 JSON report 供稽核。 |

Runner 不連 GitHub。實際 ZIP 一律來自 Dev GitLab branch checkout；原始 GitHub URL 僅用於
來源追溯與 namespace identity。`pull_code` 必須保證只有 scan 通過的內容才會落地，且 branch
必須禁止人工或其他 job 在落地後、publish 前改寫。Importer 在 clone 後自行取得 HEAD SHA，
只用於既有 SkillHub provenance API 與 report，不是 handoff variable。落地時必須保留原始 Git
commit object 與 hash，不可把檔案重新 commit 成另一個 SHA；SkillHub 會以 derived SHA 組合原始
GitHub browse URL，若改寫 commit，UI 的來源連結就會失效。

若多條 pipeline 會寫入同一個 Dev branch，必須把每一條 pipeline 的 `pull_code` 到
`publish_skillhub` 整段序列化，或改用每次 pipeline 專屬且 immutable 的 landing branch。只鎖
`pull_code` 或只鎖 `publish_skillhub` 都不夠，否則較晚的 landing 可能被較早的 publish job 抓走。

## 4. Project／group variables

### 必填

| Variable | 用途 |
| --- | --- |
| `SKILLHUB_PYTHON_IMAGE` | 組織核准、immutable 的 Python 3.8 + Git image，使用固定 tag 或 digest，不用 `latest`。 |
| `SKILLHUB_BASE_URL` | 使用者可到達的 SkillHub base，例如 `https://skillhub.example.com/skillhub`；不要自行加 `/api`。 |
| `SKILLHUB_SERVICE_TOKEN` | Platform Admin 建立的 `st_` token，必須有 `source:import` scope，設為 masked/protected。 |
| `SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE` | fallback owner provider，通常為 `keycloak`。 |
| `SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME` | fallback owner 的 exact `preferred_username`。 |

`SKILLHUB_API_TOKEN` 不會 fallback。即使 `sk_` personal token 的 user 是 `SUPER_ADMIN`，
source-import endpoints 仍會拒絕。

### 選填

| Variable | 預設／用途 |
| --- | --- |
| `SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE` | 預設與 owner provider 相同。 |
| `SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME` | 可信觸發流程提供的使用者 `preferred_username`。 |
| `SKILLHUB_IMPORT_SOURCE_ROOT` | Dev checkout 內相對子目錄，預設 `.`；禁止絕對路徑與 `..` escape。 |
| `SKILLHUB_IMPORT_REPORT_PATH` | 預設 `skillhub-oss-import-report.json`。 |
| `SKILLHUB_IMPORT_TIMEOUT_SECONDS` | 單次 HTTP timeout，預設 60 秒。 |
| `SSL_CERT_FILE` | Internal GitLab 或 SkillHub 使用企業 CA 時指定完整 CA bundle。 |

GitLab 自動提供 `CI_PROJECT_DIR`、`CI_JOB_TOKEN`、`CI_PIPELINE_ID` 與 `CI_JOB_ID`。
`CI_PROJECT_DIR` 只代表中央 `pull_pipeline` checkout；它不是待匯入來源。`CI_JOB_TOKEN`
只用於讀取 Dev GitLab，不會寫入 report、dotenv 或傳給 SkillHub。

Dev GitLab project 必須允許中央 pipeline project 使用 job token 讀 repository，且觸發 pipeline
的使用者必須具有來源 project 所需權限。若組織政策完全禁止 cross-project job token，本版
流程會 fail closed；需先另外設計並驗證替代 credential adapter，不能把 personal/project token
直接塞入 `pull-code.env` 或 clone URL。

Clone 時 authentication header 只存在於 Git subprocess environment，command arguments 與
temporary Git remote 都不含 token；HTTP redirect 也會被拒絕。

## 5. SkillHub 與身分前置條件

Python backend 必須已套用 source-import migration，並提供：

- `PUT /api/cli/v1/source-imports/namespaces/{namespaceSlug}`
- `POST /api/cli/v1/source-imports/{namespaceSlug}/skills/validate`
- `POST /api/cli/v1/source-imports/{namespaceSlug}/skills`

正式驗證必須實際啟動 PostgreSQL、Redis、MinIO/S3、scanner、Python backend 與 reverse
proxy／Ingress；mocked unit tests 只能補充，不能取代 runtime 驗證。

Platform Admin 在 `/admin/service-principals` 建立 ACTIVE principal 與 token；subpath 部署則是
`/skillhub/admin/service-principals`。限時 token 最長為建立日起 **3 個曆年**，也可以選擇
**永不到期**。無論期限為何都要有定期**輪替**與緊急**撤銷**程序。

`SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE` 通常填 `keycloak`。`tsso` 是 OAuth client ID，
不是 SkillHub provider code。Owner 與 trigger login 都使用 exact `preferred_username`，且該
user 必須曾登入 SkillHub、identity 為 ACTIVE 且唯一。

若 trigger 能對應 ACTIVE user，該版本會顯示 `Imported by` 該使用者；否則由 fallback
namespace owner 代為送審。`Imported by` 依**選定版本**顯示。service principal 只是 audit actor，
不會改變 skill owner，也不會成為顯示的人類 importer。

## 6. 匯入與 review 行為

1. Python 使用 `SKILLHUB_DEV_GITLAB_REPOSITORY_URL`，由 `CI_JOB_TOKEN` 驗證身分，shallow-fetch
   `refs/heads/$SKILLHUB_DEV_GITLAB_BRANCH` 並 detached checkout。
2. Clone 後以 `git rev-parse HEAD` 取得 provenance revision；不抓 submodules，也不使用共享 job 目錄。
3. 找出 exact-case `SKILL.md`；每個 skill root 獨立 ZIP，nested root 不重複塞進 parent ZIP。
4. Ensure namespace 一次，再 validate 所有 packages；任一 validation 失敗時提交數必須為 0。
5. 全部 validation 通過後循序 submit。SkillHub 仍執行 scanner 與 namespace owner review。
6. 相同來源與內容重跑可回 `SKIPPED_ALREADY_IMPORTED` 或 `SKIPPED_UNCHANGED`，視為成功。
7. explicit version 同版不同內容時必須在來源升版，不能覆寫既有 immutable version。
8. `SKILL.md` 未提供 version 時，由 backend 沿用一般 publish 的 UTC `YYYYMMDDHHMMSS` fallback。

公開 `/skillhub` 部署可設定：

```text
SKILLHUB_BASE_URL=https://skillhub.example.com/skillhub
```

Importer 會呼叫 `https://skillhub.example.com/skillhub/api/...`。若直接打 cluster 內 backend，
可使用 `http://skillhub-server.skillhub.svc.cluster.local:8080`，此時不要附加公開 subpath。

## 7. Report、exit code 與排錯

Report artifact 使用 `when: always`，包含：

- `repositoryUrl`、clone 後取得的 `commitSha`、`sourceRefType`、`sourceRef`；
- `scanStatus`、`scanId`；
- namespace、pipeline/job ID；
- 每個 skill 的 validation/submission outcome、coordinate、version、review task 與 `requestId`。

Report 不得包含 service token、job token 或 credentialed URL。

| Exit | 意義 |
| --- | --- |
| `0` | 全部 imported／skipped。 |
| `2` | 缺少或錯誤的 variables、branch 或 scan 狀態。 |
| `3` | Dev GitLab clone、discovery、package 或 validation 失敗。 |
| `4` | Service token 無效、過期、已撤銷或缺少 `source:import`。 |
| `5` | DNS、timeout、TLS 等 transport failure。 |
| `6` | 部分提交；保留 report，修正失敗原因後重跑 protected branch。 |
| `10` | 未預期 importer 錯誤。 |

- `0 個 SKILL.md`：確認大小寫與 `SKILLHUB_IMPORT_SOURCE_ROOT`。
- scan mismatch：確認 `pull_code.env` 的 scan SHA 與 Dev SHA 來自同一落地 revision。
- Clone 失敗：確認 Dev URL、commit 存在、job-token allowlist、Runner Git/DNS 與企業憑證。
- Identity not found／disabled／ambiguous：確認 `keycloak` 與 exact `preferred_username`。
- Namespace/source collision：同一 namespace 不可綁不同 GitHub repository。
- 部分提交：不要人工刪資料；用同一組原始 SHA、Dev SHA 與 report 重跑，成功項目會 idempotent skip。
- SQL／500：用 report 的 `requestId` 查 backend log，並確認 migration、PostgreSQL、Redis、
  MinIO/S3 與 scanner 健康。
