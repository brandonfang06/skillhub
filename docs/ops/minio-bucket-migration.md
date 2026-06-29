# SkillHub MinIO / S3 Bucket Migration

這份文件說明如何使用 `scripts/ops/migrate_minio_bucket.py`，把 SkillHub 既有
MinIO/S3 bucket 內的 package objects 搬到另一個 bucket、endpoint 或 access
key。常見情境是換 bucket、換 MinIO account，或 source/destination endpoint 都不同。

## 遷移策略

SkillHub Python backend 存在資料庫裡的是相對 object key，不是 bucket name。
目前需要搬的 key prefix 是：

```text
skills/
packages/
```

script 會逐一列出 source bucket 內這兩個 prefix 下的 object，並用相同 key 寫入
destination bucket。例如：

```text
source bucket:      skills/1/10/SKILL.md
destination bucket: skills/1/10/SKILL.md
```

不要搬成以下形式，否則 backend 會找不到檔案：

```text
old-bucket/skills/1/10/SKILL.md
skillhub/skills/1/10/SKILL.md
some-prefix/skills/1/10/SKILL.md
```

## 安全行為

- 預設只搬 `skills/` 與 `packages/`。
- 預設不刪除 destination bucket 多出來的 object。
- 預設遇到 destination 已有相同 key 且 size 相同會 skip，方便重跑。
- 預設遇到 destination 已有相同 key 但 size 不同會失敗，不會覆蓋。
- 若要覆蓋目的端物件，必須明確加 `--overwrite-existing`。
- `--verify-read-back` 會在上傳後重新讀 destination object，做 SHA-256 比對。
- `--verify-existing` 會對同 size 的既有 destination object 做 source/destination SHA-256 比對後才 skip。
- `--manifest` 會輸出 JSON Lines log，紀錄 copied、dry_run、skipped_existing 或 verified_existing。

## 前置檢查

1. 確認新 bucket 已建立。
2. 確認 destination account 至少有 `PutObject`、`GetObject`、`HeadObject` 權限。
3. 確認 source account 有 `ListBucket`、`GetObject`、`HeadObject` 權限。
4. 遷移期間暫停 publish、upload、delete，避免同步期間又有新 object 寫入。
5. 正式切換前先執行 dry-run。

## Dry Run

PowerShell 範例：

```powershell
$env:SRC_ENDPOINT = "http://old-minio.example.internal:9000"
$env:SRC_BUCKET = "old-skillhub-packages"
$env:SRC_ACCESS_KEY = Read-Host "Source access key"
$env:SRC_SECRET_KEY = Read-Host "Source secret key"

$env:DST_ENDPOINT = "http://new-minio.example.internal:9000"
$env:DST_BUCKET = "new-skillhub-packages"
$env:DST_ACCESS_KEY = Read-Host "Destination access key"
$env:DST_SECRET_KEY = Read-Host "Destination secret key"

uv --project server-python run python scripts/ops/migrate_minio_bucket.py `
  --source-endpoint $env:SRC_ENDPOINT `
  --source-bucket $env:SRC_BUCKET `
  --source-access-key $env:SRC_ACCESS_KEY `
  --source-secret-key $env:SRC_SECRET_KEY `
  --dest-endpoint $env:DST_ENDPOINT `
  --dest-bucket $env:DST_BUCKET `
  --dest-access-key $env:DST_ACCESS_KEY `
  --dest-secret-key $env:DST_SECRET_KEY `
  --dry-run
```

dry-run 只會列出會搬的 object，不會寫入 destination bucket。

如果 destination MinIO 需要透過標準 HTTP proxy 才能連線，加入：

```powershell
  --dest-proxy-url "http://proxy.example.internal:8080"
```

如果你的組織提供的是「S3/MinIO API proxy endpoint」，而不是 HTTP proxy，則直接把該
proxy endpoint 填到 `--dest-endpoint`，不用再加 `--dest-proxy-url`。

## 正式搬遷

建議正式搬遷加上 `--verify-read-back` 與 `--manifest`：

```powershell
uv --project server-python run python scripts/ops/migrate_minio_bucket.py `
  --source-endpoint $env:SRC_ENDPOINT `
  --source-bucket $env:SRC_BUCKET `
  --source-access-key $env:SRC_ACCESS_KEY `
  --source-secret-key $env:SRC_SECRET_KEY `
  --dest-endpoint $env:DST_ENDPOINT `
  --dest-bucket $env:DST_BUCKET `
  --dest-access-key $env:DST_ACCESS_KEY `
  --dest-secret-key $env:DST_SECRET_KEY `
  --verify-read-back `
  --manifest .dev/minio-migration-manifest.jsonl
```

如果曾經中斷後重跑，且想驗證已經存在的相同大小 object 內容也一致，可以加：

```powershell
  --verify-existing
```

如果 destination 已有相同 key 但 size 不同，script 會停止。只有在你確認要用 source
覆蓋 destination 時才加：

```powershell
  --overwrite-existing
```

## 參數

| 參數 | 說明 |
| --- | --- |
| `--source-endpoint` | Source MinIO/S3 endpoint URL。 |
| `--source-bucket` | Source bucket name。 |
| `--source-access-key` | Source access key。 |
| `--source-secret-key` | Source secret key。 |
| `--source-region` | Source region，預設 `us-east-1`。 |
| `--source-no-verify-ssl` | Source endpoint 使用自簽憑證或內部測試憑證時可用。 |
| `--source-proxy-url` | Source S3 client 專用 HTTP proxy URL。 |
| `--dest-endpoint` | Destination MinIO/S3 endpoint URL。 |
| `--dest-bucket` | Destination bucket name。 |
| `--dest-access-key` | Destination access key。 |
| `--dest-secret-key` | Destination secret key。 |
| `--dest-region` | Destination region，預設 `us-east-1`。 |
| `--dest-no-verify-ssl` | Destination endpoint 使用自簽憑證或內部測試憑證時可用。 |
| `--dest-proxy-url` | Destination S3 client 專用 HTTP proxy URL。 |
| `--prefix` | 要搬的 prefix，可重複指定；預設 `skills/` 與 `packages/`。 |
| `--dry-run` | 只列出計畫搬遷的 object，不寫入 destination。 |
| `--verify-read-back` | 上傳後讀回 destination object，做 SHA-256 比對。 |
| `--verify-existing` | 對同 size 的既有 destination object 做 SHA-256 比對後才 skip。 |
| `--overwrite-existing` | 允許覆蓋 destination 已存在的 object。 |
| `--manifest` | JSON Lines migration log 路徑。 |
| `--no-path-style` | 不強制 path-style S3 addressing；一般 MinIO 不需要。 |

## 切換 SkillHub

搬遷完成後，更新 backend deployment 的 MinIO/S3 設定：

```text
SKILLHUB_STORAGE_S3_ENDPOINT
SKILLHUB_STORAGE_S3_PROXY_ENDPOINT
SKILLHUB_STORAGE_S3_BUCKET
SKILLHUB_STORAGE_S3_ACCESS_KEY
SKILLHUB_STORAGE_S3_SECRET_KEY
SKILLHUB_STORAGE_S3_REGION
```

如果 endpoint 不變，只換 bucket/account，通常只需要改：

```text
SKILLHUB_STORAGE_S3_BUCKET
SKILLHUB_STORAGE_S3_ACCESS_KEY
SKILLHUB_STORAGE_S3_SECRET_KEY
```

K8s 對應位置：

- ConfigMap：`storage-s3-endpoint`、`storage-s3-proxy-endpoint`、`storage-s3-bucket`、`storage-s3-region`
- Secret：`storage-s3-access-key`、`storage-s3-secret-key`

更新後重啟 backend deployment。

## 切換後驗證

至少驗證：

1. 下載一個既有 published skill。
2. 開啟 skill detail，確認檔案列表與檔案內容可讀。
3. 下載一個 review task package。
4. 上傳一個新的測試 skill，確認新 object 寫到 destination bucket。
5. 刪除或替換一個測試 skill，確認 destination account 有 delete 權限。

## Rollback

舊 bucket 建議先保留唯讀一段時間。若切換後發現問題：

1. 將 backend env 切回舊 bucket、舊 account、舊 endpoint。
2. 重啟 backend deployment。
3. 驗證既有 skill download。

如果切換後已經有新 skill 寫入新 bucket，rollback 前要先評估這些新 object 是否也要補回舊 bucket。
