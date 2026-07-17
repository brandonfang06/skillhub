# Product Suite Namespace Admin 同步手冊

這份手冊說明如何把組織內 product suite 的現任 owner，每日同步成對應
SkillHub namespace 的 `ADMIN`。

同步功能是獨立的 Python command，不會在 FastAPI backend Deployment 內啟動
scheduler，也不會修改 OAuth callback。正式環境建議使用選用的 Kubernetes
CronJob 每日執行一次。

## 行為摘要

每次同步會：

1. 透過組織自有的 Python source module 取得完整 product suite owner 清單。
2. 依 `namespaceSlug` 找到既有 SkillHub namespace。
3. 依 Keycloak `identity_binding.login_name` 比對 Windows account。
4. 將尚未加入 namespace 的使用者加入為 `ADMIN`。
5. 將既有 `MEMBER` 升為 `ADMIN`。
6. 保留既有 `ADMIN` 與 `OWNER`，不會降級或移除任何人。

這個同步是 additive、idempotent 的。相同資料重跑不會建立重複 membership，
也不會反覆更新已經正確的資料。

### 為什麼使用者必須先登入一次

Namespace membership 必須指向既有的 `user_account.id`。這個 SkillHub UUID 是
使用者第一次完成 Keycloak 登入後才會建立，同時也會建立
`identity_binding`。

因此只知道 Windows account 時，不能安全地預先建立假帳號或猜 UUID。尚未登入
的 owner 會被計入 `waitingForLogin`，不視為失敗；他登入後，下一次每日同步就會
補上 `ADMIN`。

## 內部 Source Module 契約

公共程式不直接實作組織內 PIC API、authentication、pagination 或 response
mapping。請把既有的內部 `.py` 包成一個可 import 的 module，並提供這個 async
function：

```python
from collections.abc import Sequence

from app.integrations.product_suite import (
    ProductSuiteOwnerRecord,
    ProductSuiteSourceConfig,
)


async def fetch_product_suite_owners(
    config: ProductSuiteSourceConfig,
) -> Sequence[ProductSuiteOwnerRecord]:
    ...
```

`ProductSuiteSourceConfig` 提供：

| 欄位 | 說明 |
| --- | --- |
| `api_url` | `SKILLHUB_PRODUCT_SUITE_API_URL` 或 `--api-url` |
| `timeout_seconds` | bounded HTTP timeout，範圍大於 `0` 且不超過 `300` 秒 |

每個 `ProductSuiteOwnerRecord` 必須提供：

| 欄位 | 說明 |
| --- | --- |
| `external_suite_id` | 組織 API 內穩定且唯一的 product suite ID |
| `namespace_slug` | 已存在的 SkillHub TEAM namespace slug |
| `owner_windows_account` | Keycloak `preferred_username` 對應的 Windows account |

禁止用 product suite display name 猜 namespace slug。若 API 沒有直接提供
`namespaceSlug`，請在內部 module 以穩定的 `externalSuiteId` 做明確 mapping。

### 可改寫的 PIC API 範例

假設內部 package 為 `company_pic/product_suite_source.py`：

```python
from __future__ import annotations

from collections.abc import Sequence
import os

import httpx

from app.integrations.product_suite import (
    ProductSuiteOwnerRecord,
    ProductSuiteSourceConfig,
)


def read_pic_token() -> str:
    token = os.environ["PIC_API_TOKEN"].strip()
    if not token:
        raise RuntimeError("PIC_API_TOKEN must not be empty")
    return token


async def fetch_product_suite_owners(
    config: ProductSuiteSourceConfig,
) -> Sequence[ProductSuiteOwnerRecord]:
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(
            config.api_url,
            headers={"Authorization": f"Bearer {read_pic_token()}"},
        )
        response.raise_for_status()
        payload = response.json()

    return [
        ProductSuiteOwnerRecord.create(
            external_suite_id=item["productSuiteId"],
            namespace_slug=item["namespaceSlug"],
            owner_windows_account=item["ownerWindowsAccount"],
        )
        for item in payload["items"]
    ]
```

實際 API 若有 pagination，內部 module 必須先取完所有頁面，確認是完整 snapshot
後再一次 return。不要在部分頁面失敗時回傳不完整資料。

`httpx` 目前只在公共專案的 development dependency group。若正式 image 內的
內部 module 使用 `httpx`，組織版 image 必須把它加入 production dependencies；
也可以改用 Python standard library 或 image 內已安裝的 HTTP client。

PIC token、client certificate、proxy 或其他 credentials 都由內部 module
自行讀取 Secret-backed env。shared command 不解讀這些變數，也不要在 exception
或 log 中輸出 secret。

## 把內部 Module 放進 Image

Source module 必須在 CronJob image 的 Python import path 內。建議基於目前
SkillHub source 建立組織衍生 image，將內部 package 放在
`/workspace/server-python/`：

```dockerfile
FROM ghcr.io/iflytek/skillhub-server-python:<pinned-tag>

COPY company_pic ./company_pic
```

如果需要額外 production dependency，較穩定的作法是在組織分支的
`server-python/pyproject.toml` 與 `uv.lock` 加入並鎖定版本，再用原本
`server-python/Dockerfile` 重建完整 image。

不要透過 ConfigMap 掛載可執行 Python code。衍生 image 可被掃描、版本化與回滾，
也能保證 CronJob 和測試使用相同 source module。

驗證 image 內可 import：

```powershell
docker run --rm <organization-image> `
  uv run python -c "import company_pic.product_suite_source"
```

## Shared 環境變數

| 環境變數 | 必填 | 預設 | 說明 |
| --- | --- | --- | --- |
| `SKILLHUB_DATABASE_URL` | 是 | local PostgreSQL | Python async SQLAlchemy URL；CronJob 與 backend 必須連同一個 SkillHub database |
| `SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE` | 是 | 無 | 內部 module import path，例如 `company_pic.product_suite_source` |
| `SKILLHUB_PRODUCT_SUITE_API_URL` | 是 | 無 | 內部 PIC API URL |
| `SKILLHUB_PRODUCT_SUITE_API_TIMEOUT_SECONDS` | 否 | `30` | Source module timeout，必須大於 `0` 且不超過 `300` |
| `SKILLHUB_PRODUCT_SUITE_IDENTITY_PROVIDER` | 否 | `keycloak` | `identity_binding.provider_code`，必須等於 Keycloak OAuth registration id |

`SKILLHUB_PRODUCT_SUITE_IDENTITY_PROVIDER` 不是登入按鈕顯示名稱。若 OAuth callback
是 `/login/oauth2/code/keycloak`，通常就填 `keycloak`；若組織使用其他
registration id，這裡必須同步修改。

CLI options 會覆蓋同名環境變數：

```text
--source-module
--api-url
--timeout-seconds
--identity-provider
--dry-run
```

`--dry-run` 沒有對應的長期環境變數，避免 CronJob 被誤設成永久只預覽不寫入。

## Local 測試

在 `server-python/` 下使用 `uv`：

```powershell
$env:SKILLHUB_DATABASE_URL = "postgresql+asyncpg://skillhub:password@localhost:5432/skillhub"
$env:SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE = "company_pic.product_suite_source"
$env:SKILLHUB_PRODUCT_SUITE_API_URL = "https://pic.example.internal/api/product-suites"
$env:SKILLHUB_PRODUCT_SUITE_API_TIMEOUT_SECONDS = "30"
$env:SKILLHUB_PRODUCT_SUITE_IDENTITY_PROVIDER = "keycloak"
$env:PIC_API_TOKEN = "<internal-secret>"

uv run python -m app.integrations.product_suite --dry-run
```

確認 dry-run 的 `administratorsAdded`、`membersPromoted`、
`waitingForLogin` 和 `issues` 正確後，再執行正式同步：

```powershell
uv run python -m app.integrations.product_suite
```

也可以全部改用 CLI 傳入非 secret 設定：

```powershell
uv run python -m app.integrations.product_suite `
  --source-module company_pic.product_suite_source `
  --api-url https://pic.example.internal/api/product-suites `
  --timeout-seconds 30 `
  --identity-provider keycloak `
  --dry-run
```

## JSON 結果

stdout 永遠是一行 JSON，適合由 CronJob log collector 或監控規則解析：

```json
{"status":"ok","exitCode":0,"summary":{"suitesFetched":60,"namespacesResolved":60,"administratorsAdded":2,"membersPromoted":1,"membershipsUnchanged":54,"waitingForLogin":3,"blocked":0,"identityConflicts":0,"issues":[],"dryRun":false}}
```

| 欄位 | 說明 |
| --- | --- |
| `suitesFetched` | Source snapshot 筆數 |
| `namespacesResolved` | 找到的 namespace 數量，包含狀態不允許寫入者 |
| `administratorsAdded` | 新增為 `ADMIN` 的人數；dry-run 時是預計值 |
| `membersPromoted` | `MEMBER` 升成 `ADMIN` 的人數；dry-run 時是預計值 |
| `membershipsUnchanged` | 原本已是 `ADMIN` 或 `OWNER` |
| `waitingForLogin` | 尚無 Keycloak identity，等待使用者首次登入 |
| `blocked` | namespace 不存在/不可寫或使用者 disabled/merged |
| `identityConflicts` | 同一 Windows account 對到多個 active identity |
| `issues` | 需要操作人員處理的穩定 code 與非敏感說明 |
| `dryRun` | 是否完全沒有寫入 membership |

Exit code：

| Code | 意義 |
| --- | --- |
| `0` | 成功；可以有 `waitingForLogin` |
| `1` | 有效資料已提交，但存在 blocked 或 identity conflict，需要人工處理 |
| `2` | 設定、module import、PIC fetch、snapshot validation 或 DB transaction 失敗 |

Exit code `2` 時，整個 membership transaction 不會部分提交。stderr 會有簡短
fatal 訊息，不會輸出 Python traceback。

## Owner 變更與人工移除

當 PIC source 從 owner A 改成 owner B：

- 下一次同步會把已登入的 B 加為 `ADMIN`。
- A 不會被自動移除。
- Namespace 原本的 `OWNER` 不會被改動。

若管理員移除已不在 snapshot 的 A，後續不會再加回。若管理員移除仍是當前
product suite owner 的 B，下一次同步會再把 B 加回，因為目前 snapshot 是
additive `ADMIN` grant 的權威來源。

## 常見問題

### `No module named company_pic`

CronJob 使用的 image 沒有內部 package，或
`SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE` 填錯。先在相同 image 內執行 import 驗證。

### `waitingForLogin` 一直增加

確認 owner 已用指定 Keycloak registration 登入過 SkillHub，並檢查：

```sql
SELECT ib.user_id, ib.provider_code, ib.login_name, ua.status
FROM identity_binding ib
JOIN user_account ua ON ua.id = ib.user_id
WHERE ib.provider_code = 'keycloak'
  AND LOWER(BTRIM(ib.login_name)) = LOWER('hcfange');
```

不要直接修改 SkillHub UUID。若 `provider_code` 不是 `keycloak`，修正
`SKILLHUB_PRODUCT_SUITE_IDENTITY_PROVIDER`。

### `NAMESPACE_NOT_FOUND`

PIC module 回傳的 `namespace_slug` 在 SkillHub 不存在。修正內部 mapping 或先由
管理流程建立 namespace；同步 command 不會自動建立 namespace。

### `NAMESPACE_BLOCKED`

Namespace 不是 ACTIVE TEAM namespace，例如已 frozen、archived，或指到
`global`。同步不會繞過 namespace lifecycle。

### `IDENTITY_CONFLICT`

同一個 provider/login name 對到多個 active identity。為避免把管理權授予錯人，
該筆會 fail closed；先整理 identity binding 後再重跑。

### `USER_BLOCKED`

找到的使用者已 disabled 或 merged。同步不會恢復帳號或沿著 merge 目標猜測新的
使用者。

### Exit code `2`

先看 CronJob Pod stderr 與單行 JSON。PIC fetch 或 validation 失敗會發生在建立
DB engine 前；DB 寫入失敗則會 rollback 整批 membership。修正原因後可直接重跑，
因為操作是 idempotent。

## 上線前檢查

1. 內部 module 可在 organization image 內 import。
2. Source module 能取完所有 pagination，且回傳非空的完整 snapshot。
3. 每筆 suite ID、namespace slug 唯一。
4. `--dry-run` 結果與實際 namespace/owner 抽查一致。
5. `SKILLHUB_PRODUCT_SUITE_IDENTITY_PROVIDER` 等於 OAuth registration id。
6. CronJob 與 backend 指向同一個 `SKILLHUB_DATABASE_URL`。
7. PIC credentials 只來自 Secret，且 exception/log 不包含 secret。
8. 先以測試 namespace 執行正式同步，再啟用每日排程。

Kustomize 與 plain CronJob 範例請看
[`../deploy/k8s/addons/product-suite-admin-sync/README.md`](../deploy/k8s/addons/product-suite-admin-sync/README.md)。
