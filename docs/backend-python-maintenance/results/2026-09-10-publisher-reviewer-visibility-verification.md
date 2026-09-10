# Namespace 可審核人員：實作與驗證結果

日期：2026-09-10。分支：`codex/publisher-reviewer-visibility`。

結論：已完成開發與本機實際服務驗收；驗證結束時尚未 commit、push 或 merge。保留原工作目錄的其他未追蹤資料。

## 授權交付前複驗

使用者於 2026-09-10 批准提交並推送 `dev`。已先 fast-forward 整合 `origin/dev` 的 `bf8ceb5c`（OSS skill manifest 大小寫相容），沒有衝突；該提交未變更本次已建置的 backend／web runtime source。複驗：上述相關 backend 命令 **19 passed**；`tools/oss-source-importer` 執行 `uv run --frozen pytest tests -q` 為 **60 passed, 2 skipped**；實際服務的 root／subpath Chromium **4 passed**，前端 typecheck／lint 通過。提交僅包含本功能、測試、generated contract 與專屬文件；不納入混有歷史任務的根目錄 planning files 或其他未追蹤資料。最終提交與遠端狀態以 Git 及本次交付訊息為準。

## 完成範圍

- 新增唯讀 review context API、generated OpenAPI/types、共用「Namespace 可審核人員」卡片。
- Skill detail 優先 owner preview 版本、預設展開；我的審核進度待審列按需展開。每頁 5 人，可查看全部 ACTIVE namespace ADMIN。
- 顯示版本、送審時間、等待分鐘、掃描／namespace 阻塞、空名單及載入失敗；完成結果保留實際 reviewer 證據。
- 支援繁中、簡中、英文、俄文，以及 root／`/skillhub`。
- **不修改** OWNER／ADMIN／SKILL_ADMIN／SUPER_ADMIN 既有核准與自審權限、scanner override、OSS import 判重或 owner／submitter 歸屬。
- 無新 env、migration、CLI build 或第三方套件。

設計：[已確認規格](../plans/2026-09-10-publisher-reviewer-visibility-discussion.md)。使用說明：[中文 manual](../../skillhub/guide/namespace-reviewers.zh-TW.md)。既有 review guide 已加入連結。

## 實際服務

本次 backend／web 使用本工作分支建置，連接既有隔離 smoke stack 的真 PostgreSQL、Redis、MinIO 與 scanner，沒有以 SQLite／mock 取代 runtime。

| 元件 | 驗證環境 |
| --- | --- |
| PostgreSQL | `skillhub-oss-case-smoke-postgres-1`，localhost:55432 |
| Redis | `skillhub-oss-case-smoke-redis-1`，localhost:56379 |
| MinIO | smoke network 的 `minio:9000` |
| Scanner | smoke network 的 `skill-scanner:8000` |
| Python backend | `skillhub-reviewer-display-server-v2`，localhost:58183 |
| Root frontend | `skillhub-reviewer-display-web`，http://127.0.0.1:58180/ |
| Subpath frontend | `skillhub-reviewer-display-subpath`，http://127.0.0.1:58182/skillhub/ |

舊的本次第一版驗證 server 已停止（未刪除）；保留目前驗收 server、前端及所有原有其他 stack 服務。Smoke 資料採唯一前綴，不清空任何 DB；臨時 OSS service tokens 已透過正式 API 撤銷。

驗收帳號：`rc_publisher_ba7851ae`，密碼 `ReviewSmoke123!`，僅為本機 disposable smoke 帳號。

驗收入口：`/space/review-smoke-ba7851ae/reviewer-flow`；已有 v1.0.0 上架、v2.0.0 駁回、v3.0.0 待審，及七位 ADMIN 可驗證分頁。也可查看 `/dashboard/review-progress`。

## 測試與命令

### Backend

於 `server-python/`：

```powershell
uv run pytest tests -q --tb=short
```

結果：**1776 passed, 59 skipped**，314.96 秒。未提供個別外部測試 env 的 integration cases 按既有規則 skip，不能把這 59 項寫成通過。唯一 warning 是既有 Starlette/httpx TestClient deprecation。

再對相關流程明確接上真 PostgreSQL：

```powershell
$env:SKILLHUB_TEST_DATABASE_URL='postgresql+asyncpg://skillhub:skillhub_smoke_db@127.0.0.1:55432/skillhub'
uv run pytest tests/test_review_context_api.py tests/test_review_context_postgres.py tests/test_review_approve.py tests/test_review_progress_postgres.py tests/test_review_requested_visibility_postgres.py tests/test_source_import_submission_postgres.py tests/test_source_import_namespace_postgres.py tests/test_source_import_validation_postgres.py -q --tb=short
```

最終結果：**19 passed**。包含 auth API／既有 approve 單元測試，及 **6 個真 PostgreSQL 測試**，不是 19 項都宣稱為 real-service E2E。

真 DB 覆蓋：ACTIVE ADMIN／OWNER／MEMBER／停用帳號／SUPER_ADMIN、分頁、可辨識 login、角色與 namespace 狀態變化、GLOBAL、owner≠submitter、另一版本未授權、未送審、掃描 PENDING／FAILED／PARTIAL／COMPLETE、已完成 reviewer、原有進度／歷史與 OSS 歸屬回歸。

### Running HTTP / scanner / storage

```powershell
$env:REVIEW_SMOKE_BASE_URL='http://127.0.0.1:58183'
uv run python -m scripts.smoke_review_context
# 使用上一個命令印出的唯一 suffix；本次第一次 fixture 為 ba7851ae
$env:REVIEW_SMOKE_SUFFIX='ba7851ae'
uv run python -m scripts.verify_review_context_flow
uv run python -m scripts.verify_review_context_oss
```

這些脚本僅允許 localhost URL／DB；建立一次性資料供驗收，不會自動清除。`verify_review_context_flow` 會建立固定三個版本，重跑請先使用新的 fixture suffix。

通過：

- 正常 local login/session → 新 API 200；anonymous 401、無關使用者 403、錯誤分頁 422、不存在版本 404、private/no-store。
- 真 ZIP 上傳與 MinIO 儲存 → scanner → PENDING_REVIEW；namespace ADMIN 正式 approve／reject API 成功，卡片回讀實際 reviewer。保留第三版待審供 UI 驗收。
- 正式 service principal/token API → OSS namespace ensure → 兩版 OSS ZIP import → 真 scanner → 正式 approve。
- OSS 第二版換 triggerer，stable owner 不變；新版 submitter 能讀名單，不靠 service token 推測作者。
- 真正驗證目前 OSS namespace creation 的角色：fallback user 是 OWNER、選定平台管理者是 namespace ADMIN；本次沒有互換或改寫這項既有行為。名單依實際 membership，與使用者內部部署可能不同。
- OWNER 自審仍可成功；將測試平台帳號的 namespace membership 改成 MEMBER 後，名單變空，但 SUPER_ADMIN 正式 approve 仍成功，證明顯示名單不是新增授權限制。
- 驗證完以 `pg_stat_activity` 點查 `idle in transaction` 為 **0**。此為當次觀察，不宣稱完成連線池容量壓測。

### Frontend

於 `web/`：

```powershell
corepack pnpm run generate-api:review-context
corepack pnpm run test
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm run build
$env:REVIEW_SMOKE_SUFFIX='ba7851ae'
$env:E2E_BASE_URL='http://127.0.0.1:58180'
.\node_modules\.bin\playwright.cmd test e2e/namespace-reviewers-display.spec.ts --reporter=list
```

結果：**245 test files / 1054 tests passed**；typecheck、lint、production build 成功；實際 Chromium **4 passed**（root、subpath，各 1440px／390px）。確認預覽版本不混用上架版、完整分頁、progress 展開、水平無溢出，相關 API 失敗與 pageerror 均為 0。已檢視 desktop detail 及 mobile progress 截圖。

初次失敗已解決：既有頁面單元測試沒有新 child component 的 query seam；補上明確元件 mock 並保留獨立卡片測試。Browser 初次 assertion 錯把 `rc_…` 姓名預期在第二頁，實際按姓名排序在第一頁；修正測試後四組重跑通過，未改排序。

既有非阻擋提示：jsdom 跨文件 navigation not implemented；Vite font/runtime-config build-time path 與 chunk size warning。未為本功能擴大處理相鄰問題。

### Build / review

```powershell
docker build -t skillhub-server-python:reviewer-display-verify-v2 -f server-python/Dockerfile .
docker build -t skillhub-web:reviewer-display-verify -f web/Dockerfile web
git diff --check
```

均成功。已自行核對 route 私有資料邊界、參數化 SQL、bounded query、版本選擇、cached user isolation、React 文字 escaping，以及 `approval.py`／source-import runtime 沒有變更。

## CIA 與限制

- **機密性**：新增受授權的姓名／login／review metadata 投影；DB 層再查 ACTIVE 與 namespace／owner／submitter／platform 身分。無公開 email／claims／raw findings／套件內容。版本與 user-scoped query key 防跨版本／帳號誤用。
- **完整性**：新 endpoint 只有 SELECT，正式 approve/reject 交易、audit actor、自審與 scanner override 完全沿用；名單不可當作權限 oracle。
- **可用性**：分頁上限、按需展開、30 秒前景刷新、明確 error/retry；context manager 正常歸還 DB connection。
- 本次沒有連到使用者內部 GitLab、Keycloak 或公司 K8s；OAuth identity mapping 以本機 Keycloak identity fixtures 驗證，沒有宣稱測過公司 OIDC 登入。
- 內部 source_path→slug-only 改動只依使用者告知；本功能不讀 source_path，但未取得內部程式，不能宣稱已整合測過該私有差異。
