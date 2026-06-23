# SkillHub Full-Python 本機測試操作手冊

本文件用於 `codex/full-python` 分支，目標是讓你用新的 Python backend
測試完整 SkillHub 流程：上傳 skill、review、search、下載與常見管理操作。

## 1. 本機服務位置

啟動後請使用：

| 服務 | URL |
| --- | --- |
| Web UI | `http://localhost:3000` |
| Python backend | `http://localhost:8080` |
| Web proxy 到 backend | `http://localhost:3000/api/v1/health` |
| Scanner | `http://localhost:8000/health` |
| MinIO Console | `http://localhost:9001` |

MinIO 預設帳密：

```text
minioadmin / minioadmin
```

Bootstrap admin 預設帳密：

```text
admin / ChangeMe!2026
```

## 2. 建議測試帳號

### UI 測試

1. 用 `admin / ChangeMe!2026` 登入，測管理員、審核、標籤、使用者管理。
2. 到註冊頁建立一般使用者，測一般發布、送審、搜尋、收藏、評分。

### API 快速測試

本機開發環境支援 mock header：

```powershell
$admin = @{ "X-Mock-User-Id" = "docker-admin" }
$user = @{ "X-Mock-User-Id" = "local-user" }
```

如果你是直接用 curl，可加：

```bash
-H "X-Mock-User-Id: docker-admin"
```

## 3. 建立最小測試 Skill ZIP

在 PowerShell 建立一個可上傳的 skill package：

```powershell
$work = ".dev\manual-test-skill"
Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $work | Out-Null
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText((Join-Path $work "SKILL.md"), @'
---
name: manual-test-skill
description: SkillHub full-Python manual upload test.
version: 1.0.0
---

# Manual Test Skill

This package is used to verify publish, review, search, and download flows.
'@, $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $work "README.md"), @'
Use this skill to verify SkillHub local testing.
'@, $utf8NoBom)
Compress-Archive -Path "$work\*" -DestinationPath ".dev\manual-test-skill.zip" -Force
```

## 4. UI 測試流程

### 4.1 健康檢查

1. 打開 `http://localhost:3000`。
2. 確認首頁可以載入。
3. 打開 `http://localhost:3000/api/v1/health`，應看到健康檢查回應。

### 4.2 登入與帳號

1. 點 Login。
2. 使用 `admin / ChangeMe!2026` 登入。
3. 進入 Dashboard，確認可以看到管理員相關入口。
4. 登出後建立一個一般使用者，或用後端 API mock header 做一般使用者流程。

### 4.3 上傳 Skill

1. 進入 `http://localhost:3000/dashboard/publish`。
2. Namespace 選 `global` 或你建立的 team namespace。
3. Visibility 先選 `PUBLIC`。
4. 上傳 `.dev\manual-test-skill.zip`。
5. 送出後觀察提示：
   - 一般使用者上傳通常會進入 review/pending 流程。
   - SUPER_ADMIN 上傳可直接 published。

### 4.4 Review

1. 用 admin 登入。
2. 進入 `http://localhost:3000/dashboard/reviews`。
3. 找到剛上傳的 review task。
4. 打開 review detail，檢查：
   - metadata 是否正確。
   - 檔案列表是否能看到 `SKILL.md` 和 `README.md`。
   - 檔案 preview/download 是否可用。
5. 按 Approve。
6. 回到 skill detail 或 search，確認狀態成為 published。

### 4.5 Search

1. 進入 `http://localhost:3000/search`。
2. 搜尋 `manual-test-skill` 或 `manual upload`。
3. 檢查搜尋結果是否出現剛發布的 skill。
4. 測試排序：
   - relevance
   - newest
   - downloads
5. 點進 skill detail，確認：
   - namespace / slug / version 正確。
   - summary 和 metadata 正確。
   - 下載按鈕可用。

### 4.6 Skill detail 常見操作

在 skill detail 頁測：

1. Star / Unstar。
2. Subscribe / Unsubscribe。
3. Rating。
4. Download。
5. Version list。
6. File preview。
7. Version compare，如果你再上傳第二版。

### 4.7 Namespace

1. 進入 `http://localhost:3000/dashboard/namespaces`。
2. 建立 team namespace，例如 `qa-team`。
3. 新增成員。
4. 用該 namespace 上傳另一個 skill。
5. 到 namespace detail 頁確認 skill list 與 members 正常。

### 4.8 Admin

用 admin 測：

1. `http://localhost:3000/admin/users`
2. `http://localhost:3000/admin/labels`
3. `http://localhost:3000/admin/audit-log`
4. 建立 label、調整排序、刪除 label。
5. 檢查 audit log 是否記錄對應操作。

## 5. API 快速檢查

以下 API 直接打 Python backend `8080`。

### 5.1 Health

```powershell
Invoke-RestMethod http://localhost:8080/api/v1/health
```

### 5.2 Auth me

```powershell
Invoke-RestMethod http://localhost:8080/api/v1/auth/me -Headers @{ "X-Mock-User-Id" = "docker-admin" }
```

### 5.3 List namespaces

```powershell
Invoke-RestMethod http://localhost:8080/api/v1/namespaces -Headers @{ "X-Mock-User-Id" = "docker-admin" }
```

### 5.4 Upload skill

```powershell
$zip = (Resolve-Path ".dev\manual-test-skill.zip").Path
curl.exe `
  -H "X-Mock-User-Id: local-user" `
  -F "file=@$zip" `
  -F "visibility=PUBLIC" `
  "http://localhost:8080/api/web/skills/global/publish"
```

### 5.5 Search

```powershell
Invoke-RestMethod "http://localhost:8080/api/v1/search?q=manual-test-skill&page=0&size=10" `
  -Headers @{ "X-Mock-User-Id" = "docker-admin" }
```

### 5.6 Review list

```powershell
Invoke-RestMethod "http://localhost:8080/api/web/reviews?status=PENDING&page=0&size=20" `
  -Headers @{ "X-Mock-User-Id" = "docker-admin" }
```

### 5.7 Approve review

先從 review list 找出 `id`，再執行：

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8080/api/web/reviews/<review_id>/approve" `
  -Method Post `
  -Headers @{ "X-Mock-User-Id" = "docker-admin" } `
  -ContentType "application/json" `
  -Body '{"comment":"Manual approval from full-Python local test."}'
```

## 6. 停止服務

如果是我幫你啟動的本機 process，可用：

```powershell
Get-Content .dev\python.pid, .dev\web.pid
Stop-Process -Id (Get-Content .dev\python.pid) -ErrorAction SilentlyContinue
Stop-Process -Id (Get-Content .dev\web.pid) -ErrorAction SilentlyContinue
docker compose -p skillhub down --remove-orphans
```

若要清掉資料庫與 MinIO volume：

```powershell
docker compose -p skillhub down -v --remove-orphans
Remove-Item -Recurse -Force .dev -ErrorAction SilentlyContinue
```

## 7. 已知注意事項

- Web UI 不會自動帶 `X-Mock-User-Id`，UI 測試建議用 local login/register。
- API 快速測試可用 `X-Mock-User-Id` 直接繞過 UI 登入流程。
- Scanner 在本機 compose 中會啟動；若沒有設定 LLM key，實際 scan verdict 可能依 scanner 預設行為而定。
- Web/docs 目前仍有 Vite/esbuild build-toolchain audit advisory；不要用強制升級
  `esbuild@0.28.1` 修，因為目前會破壞 production build。
