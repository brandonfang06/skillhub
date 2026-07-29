# Cisco Skill Scanner Adapter（教學版）

這是一個獨立、同步、無狀態的 Python 參考實作，示範其他團隊如何：

1. 準備一個 skill ZIP。
2. 呼叫已部署的 Cisco Skill Scanner REST API。
3. 選擇是否要求 LLM analyzer，並示範自架 OpenAI-compatible 與 Gemini 的設定邊界。
4. 將 scanner response 整理成較穩定的 JSON contract。

這個目錄與 SkillHub 無關，不會 import `server-python/`，也沒有資料庫、Redis、
queue、worker、callback 或額外的 FastAPI proxy。它是 integration 教材，不是
production scanning platform。

## 元件分工

- **Cisco Skill Scanner**：由團隊自行部署的 scanner/API container，接收 ZIP 並執行
  static、behavioral、LLM 等 analyzers。
- **LLM analyzer**：Skill Scanner 內的 optional semantic analyzer。模型連線由
  scanner container 建立，可指向自架 OpenAI-compatible endpoint 或 Gemini。
- **Cisco AI Defense analyzer**：Skill Scanner 裡的 optional cloud analyzer，需要在
  scanner container 設定 `AI_DEFENSE_API_KEY`。
- **本 adapter**：只送出 `POST /scan-upload`、等待同步 response、normalize JSON。

LLM 的 API key、model 與 base URL 都應留在 scanner container。本 adapter 只送
`use_llm` 與 `llm_provider`，不讀也不轉送 `SKILL_SCANNER_LLM_*`。AI Defense
credential 同樣不由 adapter 傳送。

這版 MVP 不要求 Cisco AI Defense cloud analyzer，也不把 cloud AI Defense 納入
live test。`SCANNER_USE_AI_DEFENSE` 預設為 `false`。

> Cisco 官方文件指出 API server 預設沒有驗證。只應綁定 localhost，或放在有網路
> 隔離與存取控制的 private service network；不要直接公開到 Internet。

## 1. 部署 Cisco Skill Scanner container

這裡部署的是 **Cisco Skill Scanner API container**，不是 Cisco Enterprise AI
Defense cloud／hybrid appliance。Container 內執行開源
`cisco-ai-skill-scanner`；cloud AI Defense 只是其中一個 optional analyzer。

本 repo 的 image contract：

| 項目 | 值 |
| --- | --- |
| 預設 image | `ghcr.io/iflytek/skillhub-scanner:latest` |
| 目前 package baseline | `cisco-ai-skill-scanner==1.0.2` |
| Container command | `skill-scanner-api --host 0.0.0.0 --port 8000` |
| Container port | `8000` |
| Health endpoint | `/health` |
| Analyzer inventory | `/analyzers` |

`latest` 只適合教學。正式環境必須將 `SKILL_SCANNER_IMAGE` 或 Kustomize image tag
改成 immutable version tag／digest，避免重新部署時無預警升版。

> Cisco 官方 API server 預設沒有 authentication。Compose 範例因此只綁
> `127.0.0.1`，Kubernetes 只建立 `ClusterIP` Service；不要直接建立 Internet-facing
> Ingress、LoadBalancer 或 NodePort。

### 1.1 哪些是 Env、哪些是 Secret

以下前三個只控制 Docker Compose，不會傳進 scanner process：

| 變數 | 預設值 | Secret | 適用 profile／時機 | 所屬層 |
| --- | --- | --- | --- | --- |
| `SKILL_SCANNER_IMAGE` | `ghcr.io/iflytek/skillhub-scanner:latest` | 否 | 所有 profile；正式環境要 pin tag／digest | Compose 部署層 |
| `SCANNER_BIND_ADDRESS` | `127.0.0.1` | 否 | 所有 profile；控制 host bind address | Compose 部署層 |
| `SCANNER_PORT` | `8000` | 否 | 所有 profile；控制 host published port | Compose 部署層 |

Scanner container 接收的設定：

| 變數 | 預設值／建議來源 | Secret | 適用 profile／時機 | 所屬層 |
| --- | --- | --- | --- | --- |
| `SKILL_SCANNER_LLM_API_KEY` | 空；Secret | 是 | B、C；啟用需要 API key 的 LLM provider | Scanner container |
| `SKILL_SCANNER_LLM_BASE_URL` | 空；一般 Env／ConfigMap | 否 | B；自架或自訂 LLM endpoint | Scanner container |
| `SKILL_SCANNER_LLM_MODEL` | 空；一般 Env／ConfigMap | 否 | B、C；啟用 LLM analyzer | Scanner container |
| `AI_DEFENSE_API_KEY` | 空；Secret | 是 | D；`use_aidefense=true` | Scanner container |
| `AI_DEFENSE_API_URL` | 空；一般 Env／ConfigMap | 否 | D；Cisco tenant/onboarding 指定 endpoint | Scanner container |
| `VIRUSTOTAL_API_KEY` | 空；Secret | 是 | 選配 VirusTotal；不屬於 A–D 的 MVP scan | Scanner container |

這些是 **scanner-side** 設定，不是 adapter 設定。Adapter 不會把 provider API key、
model 或 base URL 放進 ZIP scan request。

Static＋behavioral baseline 不需要任何 secret。`VIRUSTOTAL_API_KEY` 已列入 container
部署契約，但目前這個 adapter 沒有 `use_virustotal` option；要使用時需直接依 Cisco
API contract 呼叫，或另行擴充 adapter request contract。

### 1.2 四種設定 profile

#### Profile A：Static＋behavioral baseline

Scanner 的六個 provider 欄位全部留空。Adapter：

```powershell
$env:SCANNER_USE_BEHAVIORAL = "true"
$env:SCANNER_USE_LLM = "false"
$env:SCANNER_USE_AI_DEFENSE = "false"
```

#### Profile B：自架 OpenAI-compatible LLM

Scanner container：

```dotenv
SKILL_SCANNER_LLM_API_KEY=local-not-secret
SKILL_SCANNER_LLM_BASE_URL=http://host.docker.internal:11434/v1
SKILL_SCANNER_LLM_MODEL=openai/qwen2.5-coder:7b
```

若 endpoint 有驗證，請把 `local-not-secret` 換成 Secret。Kubernetes 不使用
`host.docker.internal`，應填 LLM 的 private Service DNS。Model ID 必須和 endpoint
實際提供的名稱一致。

#### Profile C：Gemini

Scanner container：

```dotenv
SKILL_SCANNER_LLM_API_KEY=由部署平台的 Secret 注入
SKILL_SCANNER_LLM_BASE_URL=
SKILL_SCANNER_LLM_MODEL=gemini/gemini-3.6-flash
```

Gemini model 會改版或停用，部署前必須重新檢查 Google models/deprecations。

#### Profile D：選配 Cisco AI Defense cloud analyzer

Scanner container：

```dotenv
AI_DEFENSE_API_KEY=由部署平台的 Secret 注入
AI_DEFENSE_API_URL=由 Cisco tenant/onboarding 提供的 endpoint
```

Adapter：

```powershell
$env:SCANNER_USE_AI_DEFENSE = "true"
```

本 repo 不會建立 Cisco tenant、部署 Enterprise AI Defense 服務或提供 credential。
這個 profile 只有設定教學，不列入本次 live test。

### 1.3 用 Docker Compose 部署

部署範例位於 `scanner-adapter/deploy/`。先準備本機、CI 或 registry 中可取得的
scanner image。若要從本 repo build：

```powershell
docker build -t skillhub-scanner:1.0.2 -f scanner\Dockerfile scanner
```

接著建立不納入 Git 的 `.env`：

```powershell
cd scanner-adapter\deploy
Copy-Item .env.example .env
```

編輯 `.env`，設定：

```dotenv
SKILL_SCANNER_IMAGE=skillhub-scanner:1.0.2
```

再選擇一個 profile。真正的 API key 只能從 secret manager、CI secret 或安全的
部署環境注入，不要寫回 `.env.example`。

Render 與啟動：

```powershell
docker compose --env-file .env -f docker-compose.yml config
docker compose --env-file .env -f docker-compose.yml up -d
docker compose --env-file .env -f docker-compose.yml ps
```

> `docker compose config` 會把插值後的 secret 顯示在 terminal。不要把輸出貼進
> ticket、聊天、CI artifact 或公開 log。

驗證與查看 log：

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/analyzers
docker compose --env-file .env -f docker-compose.yml logs --tail 100 skill-scanner
```

停止這個獨立範例：

```powershell
docker compose --env-file .env -f docker-compose.yml down
```

若 host 的 `8000` 已被占用，在 `.env` 將 `SCANNER_PORT` 改為其他 loopback port，
adapter 的 `SCANNER_API_BASE_URL` 也要使用相同 port。

### 1.4 用 Kubernetes 部署

Kubernetes 範例位於 `scanner-adapter/deploy/k8s/`：

- `configmap.yaml`：model、base URL、AI Defense URL 等非秘密設定。
- `secret.example.yaml`：只列 Secret key 名稱，不會被 Kustomize 套用。
- `deployment.yaml`：port、probe、resource、security context 與 `/tmp` volume。
- `service.yaml`：僅提供 namespace 內的 `ClusterIP`。

目前 repo scanner image 以 `uid=100(app)`、`gid=101(app)` 執行；範例明確設定
`runAsNonRoot`、相同 UID/GID 與 `fsGroup`，讓 `/tmp` 的 `emptyDir` 保持可寫。若團隊
改用不同 image，必須同步確認該 image 的實際 UID/GID，而不是直接沿用這組數字。

先 pin `deployment.yaml`／`kustomization.yaml` 的 image，再編輯 `configmap.yaml`。
Baseline 不需要建立 Secret。需要外部 provider 時，先建立 namespace，再從部署系統
已注入的環境變數建立 Secret：

```powershell
kubectl apply -f scanner-adapter\deploy\k8s\namespace.yaml
$env:SKILL_SCANNER_LLM_API_KEY = "value supplied by the deployment secret source"
$env:AI_DEFENSE_API_KEY = ""
$env:VIRUSTOTAL_API_KEY = ""
kubectl create secret generic skill-scanner-secrets `
  --namespace skill-scanner `
  --from-literal=SKILL_SCANNER_LLM_API_KEY="$env:SKILL_SCANNER_LLM_API_KEY" `
  --from-literal=AI_DEFENSE_API_KEY="$env:AI_DEFENSE_API_KEY" `
  --from-literal=VIRUSTOTAL_API_KEY="$env:VIRUSTOTAL_API_KEY"
```

正式環境建議使用 External Secrets、Sealed Secrets 或組織的 secret controller，
不要把真實值寫進 `secret.example.yaml`。

Render、套用與等待 rollout：

```powershell
kubectl kustomize scanner-adapter\deploy\k8s
kubectl apply -k scanner-adapter\deploy\k8s
kubectl -n skill-scanner rollout status deployment/skill-scanner
```

透過本機 port-forward 驗證，不需要公開 Service：

```powershell
kubectl -n skill-scanner port-forward service/skill-scanner 8000:8000
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/analyzers
```

Kubernetes 內的 adapter 可使用：

```text
same namespace:  http://skill-scanner:8000
other namespace: http://skill-scanner.skill-scanner.svc.cluster.local:8000
```

### 1.5 Container readiness 不等於 provider readiness

`/health` healthy 與 `/analyzers` 列出 analyzer，只代表 scanner API 與 module
可使用。LLM、Gemini、AI Defense 或 VirusTotal 是否真的完成，還需檢查 scanner
log 與 provider-side request／usage evidence。

## 2. 安裝 adapter

需求：

- Python 3.12 以上
- [uv](https://docs.astral.sh/uv/)

```powershell
cd scanner-adapter
uv sync --frozen
```

## 3. 設定 endpoint 與 scan options

設定由 `scanner_adapter/config.py` 讀取 process environment。`.env.example` 是欄位
說明，不會被程式自動載入；可由 shell、container environment、Kubernetes ConfigMap
或部署平台注入。

| Environment variable | 預設值 | 用途 |
| --- | --- | --- |
| `SCANNER_API_BASE_URL` | `http://localhost:8000` | Scanner API host/base URL |
| `SCANNER_SCAN_PATH` | `/scan-upload` | ZIP upload endpoint |
| `SCANNER_HEALTH_PATH` | `/health` | Health endpoint |
| `SCANNER_ANALYZERS_PATH` | `/analyzers` | Analyzer inventory endpoint |
| `SCANNER_CONNECT_TIMEOUT_SECONDS` | `5` | 建立連線 timeout |
| `SCANNER_READ_TIMEOUT_SECONDS` | `300` | 等待同步 scan response timeout |
| `SCANNER_MAX_ZIP_BYTES` | `52428800` | Adapter upload 上限（50 MiB） |
| `SCANNER_USE_BEHAVIORAL` | `true` | 要求 behavioral analyzer |
| `SCANNER_USE_LLM` | `false` | 要求 scanner 使用 LLM analyzer |
| `SCANNER_LLM_PROVIDER` | `openai` | Scanner API provider hint，只接受 `openai` 或 `anthropic` |
| `SCANNER_USE_AI_DEFENSE` | `false` | 要求 Cisco AI Defense cloud analyzer |
| `SCANNER_POLICY` | `balanced` | `strict`、`balanced` 或 `permissive` |

PowerShell 範例：

```powershell
$env:SCANNER_API_BASE_URL = "http://skill-scanner.internal:8000"
$env:SCANNER_USE_BEHAVIORAL = "true"
$env:SCANNER_USE_LLM = "false"
$env:SCANNER_USE_AI_DEFENSE = "false"
$env:SCANNER_POLICY = "balanced"
```

Base URL 只接受 `http`/`https`，不得夾帶 username/password、query 或 fragment。
`.env.example` 只用來列出 adapter 設定，不會被程式自動載入。

## 4. 執行完整生命週期

### Health check

```powershell
uv run python scripts/scan_zip.py health
```

### 查詢 scanner 公告的 analyzers

```powershell
uv run python scripts/scan_zip.py analyzers
```

Scanner API 原始 response 目前使用 `{"analyzers": [...]}` envelope；adapter CLI
會 unwrap 後只輸出 analyzer list。Client 也接受早期 integration mock 常見的
top-level list。

### 同步上傳一個 skill ZIP

```powershell
uv run python scripts/scan_zip.py scan C:\packages\example-skill.zip
```

一次完成 health preflight 與 scan：

```powershell
uv run python scripts/scan_zip.py scan C:\packages\example-skill.zip --check-health
```

明確將 normalized result 寫到本機檔案：

```powershell
uv run python scripts/scan_zip.py scan C:\packages\example-skill.zip `
  --output C:\scan-results\example-skill.json
```

預設的 unsafe result 仍代表「scanner 成功完成」，exit code 是 `0`。若要示範 CI gate：

```powershell
uv run python scripts/scan_zip.py scan C:\packages\example-skill.zip `
  --fail-on-unsafe
```

此時程式會先輸出完整 result，再於 `is_safe=false` 時回傳 `5`。

## 5. 使用 LLM analyzer

LLM 設定分成兩層，請不要把它們混在同一個 request：

```text
adapter           -> ZIP + use_llm + llm_provider
scanner container -> model + base URL + API key
scanner container -> 呼叫實際 LLM provider
```

Adapter 端只有：

```powershell
$env:SCANNER_USE_LLM = "true"
$env:SCANNER_LLM_PROVIDER = "openai"
$env:SCANNER_USE_AI_DEFENSE = "false"
```

`SCANNER_LLM_PROVIDER` 是 scanner 公開 API 的相容欄位，只接受 `openai` 或
`anthropic`。它不是 Gemini 選項。只要 scanner container 設定了
`SKILL_SCANNER_LLM_MODEL`，本 repo 鎖定的 v1.0.2 與目前上游都會由 model string
選擇實際 backend。

### 5.1 自架 OpenAI-compatible endpoint

以下以 host 上提供 `/v1` API 的本機模型服務為例。`qwen2.5-coder:7b` 只是示範；
請換成 endpoint 真正提供的 model ID：

```dotenv
# deploy/.env
SKILL_SCANNER_LLM_API_KEY=local-not-secret
SKILL_SCANNER_LLM_BASE_URL=http://host.docker.internal:11434/v1
SKILL_SCANNER_LLM_MODEL=openai/qwen2.5-coder:7b
```

```powershell
cd deploy
docker compose --env-file .env -f docker-compose.yml up -d --force-recreate
cd ..
```

目前鎖定的 scanner 在使用 `openai/...` model 時要求 API key 非空；若自架 endpoint
不驗證，可使用上面的非秘密相容值。若 endpoint 需要驗證，請改由 secret manager
注入真實值，不要寫進 `.env.example` 或 adapter request。若 LLM 也在 Kubernetes，
`SKILL_SCANNER_LLM_BASE_URL` 應改成 private Service DNS，不要使用
`host.docker.internal`。

啟用 adapter request：

```powershell
$env:SCANNER_USE_LLM = "true"
$env:SCANNER_LLM_PROVIDER = "openai"
$env:SCANNER_USE_AI_DEFENSE = "false"
uv run python scripts/scan_zip.py scan C:\packages\example-skill.zip --check-health
```

### 5.2 Gemini

Gemini 仍由 scanner container 直接呼叫。使用目前可用的 model ID；以下採 Google
在 2026-07-29 公告的 stable `gemini-3.6-flash`：

```dotenv
# deploy/.env
SKILL_SCANNER_LLM_API_KEY=由 secret manager 注入或只寫在 ignored .env
SKILL_SCANNER_LLM_MODEL=gemini/gemini-3.6-flash
SKILL_SCANNER_LLM_BASE_URL=
```

```powershell
cd deploy
docker compose --env-file .env -f docker-compose.yml up -d --force-recreate
cd ..
```

Adapter 端仍然只要求啟用 LLM。`SCANNER_LLM_PROVIDER=openai` 是 API 相容 hint；
scanner-side 的 `gemini/...` model string 會主導 Gemini 路由：

```powershell
$env:SCANNER_USE_LLM = "true"
$env:SCANNER_LLM_PROVIDER = "openai"
$env:SCANNER_USE_AI_DEFENSE = "false"
uv run python scripts/scan_zip.py scan C:\packages\example-skill.zip --check-health
```

Gemini model 名稱與生命週期會變動。部署前請查
[Google Gemini models](https://ai.google.dev/gemini-api/docs/models) 與
[deprecations](https://ai.google.dev/gemini-api/docs/deprecations)，不要沿用已關閉的
`gemini-2.0-*` 範例。

### 5.3 如何確認 LLM 真的執行

`analyzers_requested` 只能證明 adapter 送出了 `use_llm=true`。目前 scanner v1.0.2
會捕捉 provider failure 並回傳空 findings，因此 HTTP 200 或
`analyzers_requested=["llm"]` 都不能單獨證明 LLM 成功。

真實驗證至少要同時看到：

1. `/health` 或 `/analyzers` 有 `llm_analyzer`。
2. Scanner log 沒有 `LLM analysis failed`。
3. 自架 endpoint access log 或 Gemini usage 顯示收到這次 request。
4. Adapter 收到完成的 normalized response。

本 repo compose 可查看 scanner log：

```powershell
docker compose --env-file deploy\.env -f deploy\docker-compose.yml `
  logs --tail 100 skill-scanner
```

目前本機 scanner 的 LLM key、base URL、model 都未設定，所以本次只驗證 adapter
request contract，不發出自架 LLM 或 Gemini 呼叫。真實 provider 可能產生成本，也
可能把 skill 內容送出團隊控制邊界；執行前應先確認資料分類、網路路徑與費用政策。

## 6. Adapter 實際送出的 request

Adapter 不解壓 ZIP，只會以 streamed multipart upload 呼叫 scanner：

```text
POST {SCANNER_API_BASE_URL}{SCANNER_SCAN_PATH}
Content-Type: multipart/form-data

file=<skill.zip>
policy=balanced
use_behavioral=true
use_llm=false
llm_provider=openai
use_aidefense=false
```

為了兼容部署中的 Skill Scanner API v0.2.0 與目前官方版本，adapter 會把
`policy`、`use_behavioral`、`use_llm`、`llm_provider`、`use_aidefense` 同時放在
query parameters 和 multipart form fields：

- v0.2.0 的 `/scan-upload` 從 query 讀 analyzer flags；
- 目前官方實作從 form fields 讀取；
- ZIP 內容只會傳一次，仍然是 multipart `file`；
- LLM key、model、base URL 與 AI Defense key 都不會放進 query、form 或 header。

這個 dual-contract request 可避免舊 container 靜默忽略 form flags，誤把 static
scan 當成 LLM scan。

Adapter 先檢查路徑、`.zip` 副檔名與 50 MiB 大小。Scanner 官方另外限制最多 500 個
ZIP entries 與 200 MB 解壓後大小；這些 archive-level 檢查由 scanner 執行。

這個 MVP 不 retry。LLM provider 可能有成本，retry/idempotency 應由正式服務按
organization policy 設計。

## 7. Normalized response

Safe 範例：

```json
{
  "schema_version": "1",
  "scan_id": "72bcbd2e-d8af-4eb8-92ea-32c834679247",
  "skill_name": "safe-example",
  "is_safe": true,
  "max_severity": "INFO",
  "findings_count": 0,
  "scan_duration_seconds": 0.42,
  "analyzers_requested": [
    "static",
    "behavioral"
  ],
  "findings": []
}
```

Unsafe 範例：

```json
{
  "schema_version": "1",
  "scan_id": "8d90cb21-0698-4708-b6d1-a368506c17ec",
  "skill_name": "unsafe-example",
  "is_safe": false,
  "max_severity": "HIGH",
  "findings_count": 1,
  "scan_duration_seconds": 1.25,
  "analyzers_requested": [
    "static",
    "behavioral",
    "llm"
  ],
  "findings": [
    {
      "rule_id": "RULE-001",
      "severity": "HIGH",
      "category": "data-exfiltration",
      "title": "Potential data exfiltration",
      "description": "Description from the scanner",
      "file_path": "scripts/run.py",
      "line_number": 12,
      "remediation": "Review the outbound request",
      "analyzer": "llm"
    }
  ]
}
```

`analyzers_requested` 是 adapter 根據 request options 整理的「要求項目」，不是每個
analyzer 都成功完成的證明。官方目前的 HTTP scan response 不包含底層
`analyzers_used`；請搭配 `/health`、`/analyzers` 與 scanner logs 判讀部署狀態。

Library caller 可同時取得 normalized 與 raw response：

```python
from pathlib import Path

from scanner_adapter import ScannerAdapterConfig, ScannerClient

config = ScannerAdapterConfig.from_env()
with ScannerClient(config) as client:
    result = client.scan_zip(Path("example-skill.zip"))

print(result.normalized.to_dict())
print(result.raw_response)
```

CLI 只輸出 normalized contract，不會把 raw response 重複寫到磁碟。

## 8. Exit codes

| Exit code | 意義 |
| --- | --- |
| `0` | Scanner 完成；預設也包含 `is_safe=false` |
| `2` | CLI usage 或 adapter configuration 錯誤 |
| `3` | ZIP 不存在、不是檔案、副檔名錯誤或超過大小 |
| `4` | Scanner 連線、timeout、non-2xx、bad JSON 或 response contract 錯誤 |
| `5` | 使用 `--fail-on-unsafe` 且完成結果為 unsafe |

## 9. 常見問題

### `scanner request failed`

確認 `SCANNER_API_BASE_URL`、DNS/Service name、port、NetworkPolicy 與 scanner
process。長時間分析可調高 `SCANNER_READ_TIMEOUT_SECONDS`，但本 adapter 不會自動
retry。

### `/analyzers` 沒有 `llm_analyzer`

確認 scanner image 安裝了 LLM optional dependencies。`/analyzers` 顯示 available
只代表 module 可載入，仍須另外確認 scanner container 的 model、base URL、API key
與對外網路。

### `LLM analysis failed` 或啟用後仍是空 findings

先讀 scanner log，不要只看 adapter response。常見原因是
`SKILL_SCANNER_LLM_API_KEY` 空白、model ID 不存在、base URL 從 scanner container
無法連線、provider 不支援 structured output，或 rate limit。Scanner v1.0.2 對這類
錯誤會 graceful degradation 成空 findings，因此這是需要額外觀測的 analyzer
failure，不是「已證明沒有風險」。

### `AI Defense API key required`

代表呼叫端啟用了 cloud AI Defense，但 scanner container 沒有 credential。本 MVP
不測這條路徑；請保持 `SCANNER_USE_AI_DEFENSE=false`。若其他專案要使用，應另依
Cisco cloud 服務的 onboarding 與 secret 管理流程設計。

### HTTP 400/422

ZIP 必須包含 scanner 可辨識的 skill structure（通常包含 `SKILL.md`）。也要符合
50 MB upload、500 entries 與 200 MB uncompressed guardrails。

### `is_safe=false`

這是正常完成的 security finding，不是 integration failure。Review `findings`，
修正 skill 後再重新 scan。

### `is_safe=true` 或沒有 findings

這不等於安全認證。Cisco 官方明確說明 scanner 可能有 false positive/false
negative，也無法涵蓋未知攻擊；human review 與其他 defense-in-depth controls 仍然
必要。

## 10. 正式服務化前要補的能力

若團隊要把範例升級成共用服務，應另開設計並至少決定：

- caller authentication、authorization、rate limiting 與 network policy；
- ZIP/result 的 retention、encryption、PII/secret handling 與資料庫 schema；
- queue、job status、idempotency、timeout、retry 與 LLM cost control；
- scanner version pinning、analyzer readiness、metrics、tracing、audit log 與 ownership；
- malicious archive isolation、resource limits、capacity 與多 replica 行為；
- contract versioning、consumer tests 與人工 review/escalation 流程。

不要直接把這個同步 CLI 當成上述 production controls 的替代品。

## 11. 測試

Unit tests 全部使用 `httpx.MockTransport`，不需要 scanner 或網路：

```powershell
uv run pytest tests -q
uv run ruff check .
```

不需要外部 provider 的 baseline Docker smoke：

```text
health -> analyzers -> scan ZIP with LLM/AI Defense off -> inspect normalized JSON
```

有明確提供的自架 endpoint 或 Gemini credential 時，才做 LLM live smoke：

```text
configure scanner -> enable adapter LLM flag -> scan -> inspect scanner/provider logs
```

本機 Docker 實測紀錄見
[`docs/2026-07-28-docker-live-smoke.md`](docs/2026-07-28-docker-live-smoke.md)。

## 官方參考

- [Skill Scanner overview](https://cisco-ai-defense.github.io/docs/skill-scanner)
- [Installation](https://cisco-ai-defense.github.io/docs/skill-scanner/installation)
- [REST API reference](https://cisco-ai-defense.github.io/docs/skill-scanner/api-reference)
- [Python SDK](https://cisco-ai-defense.github.io/docs/skill-scanner/python-sdk)
- [Architecture](https://cisco-ai-defense.github.io/docs/skill-scanner/architecture)
- [LLM analyzer](https://github.com/cisco-ai-defense/skill-scanner/blob/main/docs/llm-analyzer.md)
- [Official GitHub repository](https://github.com/cisco-ai-defense/skill-scanner)
- [Google Gemini models](https://ai.google.dev/gemini-api/docs/models)
- [Google Gemini deprecations](https://ai.google.dev/gemini-api/docs/deprecations)
