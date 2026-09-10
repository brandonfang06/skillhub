# Generic 共用目錄多技能安裝：實作與驗證

日期：2026-09-10。分支：`codex/generic-dir-multi-install`，基底 `c8c925c3`。
開發驗收完成時尚未 commit、merge 或 push；其後使用者已授權提交至 dev。
交付前確認遠端 dev 仍為 `c8c925c3`，重跑 55 個相關前端測試通過；只納入本功能檔案，保留其他未追蹤文件及工作內容。

## 完成內容

- 安裝頁 Direct Agent 加入 Generic（共用目錄）。User：`--dir "$HOME/.agents/skills"`；Project：`--dir "./.agents/skills"`。
- 不混用 `--scope`／`--agent`。保留 `--force`、每 Skill 獨立命令、registry subpath、單一 Agent／終端互動模式與使用者隔離的分頁選擇清單。
- 所有現有 UI locale（en、zh、zh-TW、ru）補齊文案；中英文 multi-skill feature manual 已同步。
- Generic 是共用目錄，不是複製到所有 Agent 專屬目錄；是否可使用取決於 Agent 是否讀取該目錄。OSS CLI 將 explicit directory 標記為 `custom`，以實際目錄為準。
- 發現並修復既有 Nginx `/install` 與靜態文件目錄同名造成的 301。exact location 回傳 SPA，避免重載遺失 port／prefix；`/install/skillhub.md` 保留 200 text/plain。

## 已發布 CLI 證據與平台界線

`npm view @astron-team/skillhub version dist.tarball repository.url --json` 回傳 `0.1.12`。
以 `npm pack @astron-team/skillhub@0.1.12 --ignore-scripts` 取得
[官方 npm artifact](https://registry.npmjs.org/@astron-team/skillhub/-/skillhub-0.1.12.tgz)，
SHA-1：`195ca114be6088a13be813a944c93cc0999c2ce9`。
解包後以 Node 執行原封未改的 `dist/index.js`，不是本地 CLI build，也未發布套件。
UI 仍輸出 `npx @astron-team/skillhub@latest`；未來 latest 變動不屬於此次固定版本證據。

Windows PowerShell 與 Linux Bash 已真實下載、解包及記錄事件。
macOS 無實機環境，不宣稱原生 macOS E2E；相容性依相同 Node POSIX 路徑與
[Bash 雙引號](https://www.gnu.org/s/bash/manual/html_node/Double-Quotes.html)、
[Zsh 引號](https://zsh.sourceforge.io/Doc/Release/Shell-Grammar.html#Quoting)
的參數展開規則推論。Windows 使用 PowerShell，不能將 `$HOME` 指令原樣貼入 CMD。
Windows 參照 [PowerShell quoting rules](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules)。

## 真實服務與執行結果

沿用本機 disposable smoke stack 的 PostgreSQL（55432）、Redis、MinIO、scanner，
Python backend `skillhub-reviewer-display-server-v2`（58183）。不是 mock API／SQLite。
前端新 image：`skillhub-web:generic-dir-verify-v2`，image ID
`sha256:f415c98133a9fc4a927fd5c38b478ca089b56caf67ff3763b21c57daf0675409`。

| 驗證 | 命令／結果 |
| --- | --- |
| 前端完整測試 | `cd web; corepack pnpm run test`：245 files、1057 tests passed |
| 型別／lint | `corepack pnpm run typecheck`、`corepack pnpm run lint`：passed |
| Web production image | `docker build -t skillhub-web:generic-dir-verify-v2 -f web/Dockerfile web`：passed |
| 真瀏覽器 | `corepack pnpm exec playwright test e2e/generic-dir-install.spec.ts --reporter=line`：4 passed（21.0s） |
| 真 CLI／DB | `cd server-python; uv run python -m scripts.verify_generic_dir_install`：每輪 8 次成功，涵蓋兩個 Skills × Windows/Linux × User/Project |
| 部署契約 | `uv run pytest tests/test_deployment_cutover.py -q`：31 passed |
| K8s／Compose | `kubectl kustomize deploy/k8s/base`、`docker compose --env-file .env.release.example -f compose.release.yml config --quiet`：passed |
| Diff | `git diff --check`：passed |

瀏覽器測試從真實搜尋結果勾選兩個 Skills，驗證 Generic 文案、兩條命令、真剪貼簿、
User/Project 切換、重载 persistence、互動模式保留、Codex 不退化、無 failing API／page errors。
覆蓋 root `http://127.0.0.1:58280` 和 subpath `http://127.0.0.1:58282/skillhub`，
各 1440px／390px；已檢視 screenshot，無水平溢出，主要複製按鈕首屏可見。
首次剪貼簿比較因 Windows CRLF 而失敗，測試改為只正規化換行，不更改命令內容。
原 `/install` reload 測試確實先失敗，修正後 GET 不再 301，重載通過。

CLI 驗證先以 root backend 執行，再將 `GENERIC_SMOKE_BASE_URL` 改為前端 `/skillhub`
入口重跑；Windows 安裝使用此 public registry，Linux 容器則使用 smoke network 的 backend DNS。
最後一輪產生 8 筆 PostgreSQL `local_skill_download_event`，均屬於真正 CLI token 的使用者，
`source=cli` 且兩個 Skill ID 正確。找不到 Skill、未認證的指令都失敗且沒有新增事件。
Windows HOME 與專案含空格，實際 `SKILL.md` 存在且安裝路徑位於隔離測試目錄。

### 重跑環境

CLI script 所需環境（不可將實際秘密提交進 Git）：

- `SKILLHUB_TEST_DATABASE_URL`：本機 disposable PostgreSQL asyncpg URL。
- `GENERIC_SMOKE_BASE_URL`：本機 backend 或 public subpath URL。
- `GENERIC_SMOKE_CLI`：上述未修改 npm artifact 的 `dist/index.js` 絕對路徑。
- `GENERIC_SMOKE_USERNAME`／`GENERIC_SMOKE_PASSWORD`：擁有至少兩個 PUBLISHED fixture Skills 的 smoke 帳號。
- `GENERIC_SMOKE_LINUX=1`：以 `node:22-bookworm` 執行 Linux Bash；script 固定使用既有 `skillhub-oss-case-smoke_default` network 與 reviewer-display backend DNS，僅適合此 disposable stack。

Browser script 另需 `GENERIC_SMOKE_WEB_URLS`（以上兩個 URL，以逗號分隔）、
`E2E_BASE_URL=http://127.0.0.1:58280`，避免 Playwright 自行啟動 Vite。
Screenshot 位於 `web/test-results/generic-dir-install-*/generic-user.png`，不是產品檔案。

## 安全與限制

- **C**：沒有把網頁 session/token 放進安裝命令；不新增身份或資料 API。下載仍需 CLI 身份。測試 token 為一小時、僅 `skill:download`，以子程序環境傳入並於 finally 撤銷。
- **I**：不修改 owner、下載歸屬或 schema；固定目錄片段無任意路徑輸入，沒有 `--agent generic` 兼容性猜測。沿用 OSS 同來源 managed install 的 `--force` 保護。
- **A**：不改 pool／後端工作流程。每條命令獨立，失敗不撤回先前成功；安裝頁 reload 的可用性問題已加入真代理回歸測試。
- 測試只使用新 temp home／container 路徑，沒有寫入使用者真實 `.agents/skills`。只停止本次舊版 Generic 測試 web containers，其他服務不動；沒有刪除資料或 volume。
- 本次沒有 backend application／schema／CLI source 變更，未重跑全 backend suite；實際下載 API、DB 事件與 31 部署契約測試已執行。
- 手冊內容已檢查；document/node_modules 不存在，未宣稱 Docusaurus 全站 build 通過。
- 若內部使用自製前端 image，需帶入更新後 web bundle 與 exact `/install` Nginx location；不需要新 env variable、backend migration 或 CLI build。
