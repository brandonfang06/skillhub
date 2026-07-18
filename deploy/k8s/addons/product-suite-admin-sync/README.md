# Product Suite Admin Sync Addon

這是選用的每日同步 CronJob，不屬於 `deploy/k8s/base`。Backend Deployment
不會執行 scheduler；只有套用這個 addon 才會啟用同步。

完整 Python source contract、local `uv` 測試與結果說明請看
[`../../../../server-python/PRODUCT_SUITE_ADMIN_SYNC.zh.md`](../../../../server-python/PRODUCT_SUITE_ADMIN_SYNC.zh.md)。

## 前置條件

1. 已部署 SkillHub Python backend，且 `skillhub-secret/database-url` 存在。
2. 建立包含內部 PIC source module 的 organization image。
3. Source module 可在 image 內 import，且必要 production dependencies 已安裝。
4. PIC credentials 已存入獨立 Secret。

CronJob 使用 `uv run --no-sync`，不會在啟動時下載或安裝套件。所有 production
dependencies 必須在 organization image build 階段完成。

請先修改 `kustomization.yaml` 的 `newName`、`newTag`，指向實際的
organization image。不要直接使用不含內部 source module 的公共 backend image。

再修改 `cronjob.yaml`：

- `SKILLHUB_PRODUCT_SUITE_SOURCE_MODULE`
- `SKILLHUB_PRODUCT_SUITE_API_URL`
- `SKILLHUB_PRODUCT_SUITE_API_TIMEOUT_SECONDS`
- `SKILLHUB_PRODUCT_SUITE_IDENTITY_PROVIDER`
- `spec.schedule`

預設 `0 2 * * *` 是每日 02:00。未設定 `spec.timeZone` 時會使用 Kubernetes
controller 的時區，許多叢集是 UTC。若叢集版本支援 CronJob `timeZone`，可明確
設定，例如 `timeZone: Asia/Taipei`。

每次 Job 最長執行 900 秒，避免 PIC 或 database 連線卡住時，因
`concurrencyPolicy: Forbid` 持續阻擋後續排程。若內部 API 合理執行時間更長，
請連同 source timeout 與 `activeDeadlineSeconds` 一起評估。

## 建立 PIC Secret

複製 example，依內部 module 實際讀取的 env key 修改：

```powershell
Copy-Item `
  deploy/k8s/addons/product-suite-admin-sync/secret.yaml.example `
  deploy/k8s/addons/product-suite-admin-sync/secret.yaml
kubectl apply -f deploy/k8s/addons/product-suite-admin-sync/secret.yaml
```

`secret.yaml` 不應提交。`secret.yaml.example` 的 `PIC_API_TOKEN` 只是示意名稱；
shared command 不規定 PIC token、certificate 或 proxy env 名稱。

## Render 與套用

```powershell
kubectl kustomize deploy/k8s/addons/product-suite-admin-sync
kubectl apply -k deploy/k8s/addons/product-suite-admin-sync
kubectl get cronjob -n skillhub skillhub-product-suite-admin-sync
```

Addon 沒有修改 backend、frontend、scanner Deployment，也不會安裝 PostgreSQL、
Redis、MinIO 或 Keycloak。

## 第一次先做 Dry-run

從 CronJob 產生暫存 Job YAML：

```powershell
kubectl create job `
  --from=cronjob/skillhub-product-suite-admin-sync `
  skillhub-product-suite-admin-sync-dry-run `
  -n skillhub `
  --dry-run=client `
  -o yaml > product-suite-admin-sync-dry-run.yaml
```

在產生檔案的 container `command` 最後加上：

```yaml
- --dry-run
```

再套用並看 log：

```powershell
kubectl apply -f product-suite-admin-sync-dry-run.yaml
kubectl logs -n skillhub job/skillhub-product-suite-admin-sync-dry-run
kubectl delete job -n skillhub skillhub-product-suite-admin-sync-dry-run
```

確認 `administratorsAdded`、`membersPromoted`、`waitingForLogin` 和 `issues`
符合預期後，再讓正式 CronJob 依排程執行。

## 手動正式執行

```powershell
$jobName = "skillhub-product-suite-admin-sync-manual"
kubectl create job `
  --from=cronjob/skillhub-product-suite-admin-sync `
  $jobName `
  -n skillhub
kubectl logs -n skillhub -f "job/$jobName"
```

Command stdout 是單行 JSON。Exit code `0` 是完成、`1` 是有 blocked/conflict
需處理、`2` 是 source/config/DB fatal failure。

## 暫停與移除

暫停排程但保留設定：

```powershell
kubectl patch cronjob -n skillhub skillhub-product-suite-admin-sync `
  --type=merge `
  -p '{"spec":{"suspend":true}}'
```

恢復：

```powershell
kubectl patch cronjob -n skillhub skillhub-product-suite-admin-sync `
  --type=merge `
  -p '{"spec":{"suspend":false}}'
```

移除排程：

```powershell
kubectl delete cronjob -n skillhub skillhub-product-suite-admin-sync
```

刪除 CronJob 不會撤銷已授予的 namespace `ADMIN`。
