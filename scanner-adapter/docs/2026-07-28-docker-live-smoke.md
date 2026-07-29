# Scanner Adapter Docker Live Smoke

日期：2026-07-28

## 範圍

使用本機既有 Docker container `skillhub-skill-scanner-1`，從 repo-root
`scanner-adapter/` 實際執行：

```text
health -> analyzers -> upload ZIP -> normalize response
```

測試 ZIP 由現有 `.agents/skills/backend-module-structure/` 打包，沒有加入 database、
queue 或 SkillHub lifecycle。

## Container evidence

```text
container: skillhub-skill-scanner-1
image: skillhub-skill-scanner
compose project: skillhub
compose service: skill-scanner
health status: healthy
reported API version: 0.2.0
```

`GET /health` 回傳的 analyzers：

```text
static_analyzer
behavioral_analyzer
llm_analyzer
aidefense_analyzer
meta_analyzer
```

`GET /analyzers` 的真實 response 是：

```json
{
  "analyzers": [
    {
      "name": "aidefense_analyzer",
      "available": true,
      "requires_api_key": true
    }
  ]
}
```

這揭露了第一個 integration gap：adapter 原先只接受 top-level list。新增
`test_list_analyzers_unwraps_official_response_envelope` 後先確認失敗，再讓 client
unwrap 官方 envelope。Live `analyzers` command 隨後成功。

## Upload contract evidence

Container 內 API v0.2.0 的 `/scan-upload` 從 query parameters 讀：

```text
use_llm
llm_provider
use_behavioral
use_aidefense
aidefense_api_key
```

目前官方 source 已改為 multipart form fields。原 adapter 只送 form，導致 v0.2.0
靜默使用 `false` defaults；第一次成功 response 因此不是 AI Defense 執行證明。

新增 multipart request regression assertions 後先確認 query parameters 缺失，再讓
adapter 同時送 `use_llm`、`llm_provider`、`use_behavioral`、`use_aidefense` 與
`policy` 到 query 與 form。ZIP 仍只上傳一次，LLM 與 AI Defense credential 都不由
adapter 傳送。

## AI Defense enabled diagnostic（不再是 gate）

修正 request contract 後執行：

```powershell
uv run python scripts/scan_zip.py scan $smokeZip --check-health
```

結果：

```text
HTTP 400
{"detail":"AI Defense API key required"}
adapter exit code: 4
```

Redacted configuration audit：

```text
container AI_DEFENSE_API_KEY: not set
container AI_DEFENSE_API_URL: not set
current process AI_DEFENSE_API_KEY: not set
root env files with non-empty AI Defense key: none
```

`aidefense_analyzer` available 只代表 module 可載入，不代表 cloud credential ready。
使用者後續明確把 cloud AI Defense 排除於 MVP，因此這段只保留為歷史診斷，不需要
補 credential，也不會再把 cloud scan 當成完成條件。Adapter 預設已改為
`SCANNER_USE_AI_DEFENSE=false`。

## LLM analyzer evidence

本機 container 可載入 `llm_analyzer`，並包含：

```text
cisco-ai-skill-scanner: 1.0.2
google-genai: 2.11.0
litellm: 1.91.1
```

Redacted scanner-side configuration：

```text
SKILL_SCANNER_LLM_API_KEY: not set
SKILL_SCANNER_LLM_BASE_URL: not set
SKILL_SCANNER_LLM_MODEL: not set
```

目前不能安全執行真實 LLM live scan：啟用後會使用 provider default 或失敗，且沒有
使用者提供的自架 endpoint 或 Gemini credential。這次只用
`httpx.MockTransport` 驗證 adapter 會在 query 與 form 送出 `use_llm` 和
`llm_provider`。

Scanner v1.0.2 的 `LLMAnalyzer.analyze_async()` 會捕捉 provider exception、在
container log 印出 `LLM analysis failed`，然後回傳空 findings。因此：

- `llm_analyzer` available 不是 provider readiness；
- `analyzers_requested: llm` 不是執行完成證明；
- 真實 smoke 必須同時檢查 scanner log 與 provider-side request/usage。

## Static and behavioral control result

只在該 command process 設定：

```powershell
$env:SCANNER_USE_AI_DEFENSE = "false"
$env:SCANNER_USE_LLM = "false"
uv run python scripts/scan_zip.py scan $smokeZip --check-health
```

結果：

```text
scan_id: 17c28e95-f32e-48d2-a328-94bda0a0800f
skill_name: backend-module-structure
is_safe: true
max_severity: SAFE
findings_count: 0
analyzers_requested: static, behavioral
adapter exit code: 0
```

這證明實際 Docker HTTP upload、同步等待、response validation 與 normalization 路徑
可運作。

LLM adapter amendment 完成後，以新的一次性 ZIP 再執行相同 baseline，確認新增的
`use_llm=false` 與 `llm_provider=openai` 不影響現有掃描：

```text
scan_id: 7db8d72f-10b8-4073-8f09-eb989c318cee
skill_name: backend-module-structure
is_safe: true
max_severity: SAFE
findings_count: 0
scan_duration_seconds: 0.005549430847167969
analyzers_requested: static, behavioral
adapter exit code: 0
```

這次 health、analyzers、scan 都使用 `uv --no-cache` 執行並回傳 exit code `0`。測試
ZIP 在完成後已從 OS temp 目錄刪除。

## 後續可選的 LLM live smoke

只有在團隊明確提供自架 OpenAI-compatible endpoint 或 Gemini credential 時才執行：

1. 把 `SKILL_SCANNER_LLM_MODEL`、`SKILL_SCANNER_LLM_BASE_URL`（如需要）與
   `SKILL_SCANNER_LLM_API_KEY` 注入 scanner container。
2. 重新建立 scanner container，確認 `llm_analyzer` 可載入。
3. Adapter 設定 `SCANNER_USE_LLM=true` 並重跑 ZIP scan。
4. Scanner log 不含 `LLM analysis failed`。
5. 自架 endpoint access log 或 Gemini usage 能證明 request 實際送出。
6. Adapter 回傳 completed normalized result。

Cloud AI Defense 不在這個 gate 內。

## 2026-07-29 standalone deployment reference 驗證

新增 `scanner-adapter/deploy/` 後，從 `scanner-adapter/` 執行完整離線檢查：

```text
uv --no-cache run pytest -p no:cacheprovider tests -q
83 passed in 0.11s

uv --no-cache run ruff check .
All checks passed!
```

Compose render：

```text
docker compose --env-file deploy\.env.example -f deploy\docker-compose.yml config
exit code: 0
services: skill-scanner only
host bind: 127.0.0.1:8000
scanner provider environment: six keys present, example values empty
health check: http://127.0.0.1:8000/health
```

Kubernetes render：

```text
kubectl kustomize deploy\k8s
exit code: 0
resources: Namespace, ConfigMap, ClusterIP Service, Deployment
Secret rendered: no
Ingress / NodePort / LoadBalancer rendered: no
readiness and liveness path: /health
```

既有 image 檢查結果為 `uid=100(app)`、`gid=101(app)`。Focused deployment
contract test 先因 manifest 未宣告 runtime identity 而失敗；加入
`runAsNonRoot`、`runAsUser: 100`、`runAsGroup: 101` 與 `fsGroup: 101` 後通過，
確保掛載的 `/tmp` scratch volume 可由 non-root scanner process 寫入。

接著重用既有本機 container：

```text
container: skillhub-skill-scanner-1
image: skillhub-skill-scanner
status: healthy
published port: 8000
reported API version: 0.2.0
```

在 command process 明確設定：

```powershell
$env:SCANNER_USE_LLM = "false"
$env:SCANNER_USE_AI_DEFENSE = "false"
```

Health、analyzers 與新的 ZIP upload 都回傳 exit code `0`。Normalized scan：

```text
scan_id: 7974ba84-643c-46ae-8463-bf002ef47582
skill_name: backend-module-structure
is_safe: true
max_severity: SAFE
findings_count: 0
scan_duration_seconds: 0.002962827682495117
analyzers_requested: static, behavioral
```

本次沒有呼叫自架 LLM、Gemini、Cisco AI Defense cloud 或 VirusTotal。測試 ZIP 位於
OS temp 的
`C:\Users\USER\AppData\Local\Temp\scanner-deploy-smoke-20260729-codex.zip`；自動刪除
被本機 destructive-operation guard 拒絕，未繞過保護，需由 workspace owner 視需要
移除。
