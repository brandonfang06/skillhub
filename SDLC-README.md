# SkillHub SDLC README

這份文件給 SkillHub 團隊成員快速理解本專案的開發生命週期、三種本機環境規則，以及
Java 到 FastAPI 共存遷移期間一定要遵守的邊界。完整產品與架構背景請仍以根目錄
`README.md`、`AGENTS.md`、`docs/` 為準。

## 專案定位

SkillHub 是組織內使用的 self-hosted agent skill registry，用來發布、搜尋、審核、治理與
下載可重用的 skill package。現有主系統包含：

- Java Spring Boot backend：目前正式業務 API 來源，執行在 `localhost:8080`。
- React + TypeScript + Vite frontend：開發環境執行在 `localhost:3000`。
- PostgreSQL、Redis、MinIO：本機或組織環境的周邊服務。
- Scanner：既有 Python/FastAPI security scanner，預設 `localhost:8000`。
- 新 Python backend：放在 `server-python/`，逐步承接 Java API，執行在 `localhost:8081`。

## Backend Python Migration

Java 到 FastAPI 的轉換採「共存遷移」，不是一次性重寫。每次只以一個 API 或小型 API group
為 milestone。

- `server/ 不可修改`：Java backend 只作為唯讀參考、比較與測試對象。
- Python backend 固定放在 `server-python/`。
- Python 使用 FastAPI + Python 3.12 + `uv + .venv` 管理。
- Vite dev proxy 以 route ownership 分流：已遷移 API 走 `localhost:8081`，其餘 `/api`
  與 `/oauth2` 走 Java `localhost:8080`。
- 每次 API ownership 變更都要更新
  `docs/backend-python-migration/route-registry.md`。

## Milestone 流程

每次開始前都要先說明本次要實作哪個 API 或 milestone、會改哪些區域、驗收標準是什麼。
完成一個 milestone 後才可以進入下一個。

必要步驟：

1. 先寫 `docs/backend-python-migration/plans/YYYY-MM-DD-<topic>.md`。
2. 實作時只碰允許區域；不得改 `server/`。
3. 跑測試與端到端驗證。
4. 用 `git diff --name-only -- server` 確認沒有任何 `server/` 路徑。
5. 寫 `docs/backend-python-migration/results/YYYY-MM-DD-<topic>.md`。
6. commit 並 push 到 `dev`。

## 本機環境規則

### Windows

Windows 開發機通常位於組織外部，周邊服務可以用 Docker Desktop 啟動。建議使用 PowerShell：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 up
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e-smoke
```

### macOS

macOS 開發機通常位於組織外部，周邊服務可以用 Docker Desktop 或 Colima 啟動。建議使用：

```bash
make dev-all-hybrid
make test-e2e-smoke-hybrid
```

### Ubuntu

Ubuntu 開發機預期位於組織內部網路，不使用 Docker 啟動 PostgreSQL、Redis、MinIO。Ubuntu
開發者需要在本機手動調整：

```text
server/skillhub-app/src/main/resources/application-local.yml
```

這個檔案要指向組織內的 PostgreSQL、Redis、MinIO。這是本機環境設定，不是 migration
實作內容；除非 project owner 明確要求，否則不要 commit 這個檔案的修改。Agent 也不得替
使用者修改任何 `server/` 底下檔案。

Ubuntu 測試時建議分別啟動 Java、Python、Vite：

```bash
cd server
./scripts/run-dev-app.sh
```

```bash
cd server-python
UV_CACHE_DIR=.uv-cache uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

```bash
cd web
corepack pnpm install --frozen-lockfile
corepack pnpm run dev -- --host 0.0.0.0 --strictPort
```

## 常用驗證

Python backend：

```bash
cd server-python
UV_CACHE_DIR=.uv-cache uv run pytest
```

Python health 直連與 Vite proxy：

```bash
curl -i http://localhost:8081/api/v1/health
curl -i http://localhost:3000/api/v1/health
```

Frontend smoke E2E：

```bash
cd web
corepack pnpm run test:e2e:smoke
```

不可修改邊界：

```bash
git diff --name-only -- server
```

如果這個命令有任何輸出，就代表本次改動碰到 Java backend 邊界，必須先停止並釐清。
