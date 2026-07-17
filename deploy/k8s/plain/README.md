# SkillHub plain Kubernetes manifests

This directory contains non-kustomize manifests for operators who prefer direct
`kubectl apply -f` workflows.

The plain manifests deploy only the three SkillHub workloads:

- `backend/`: `skillhub-config`, `skillhub-secret`, `skillhub-server` Service and Deployment
- `scanner/`: `skillhub-scanner-secret`, `skillhub-scanner` Service and Deployment
- `frontend/`: `skillhub-web` Service and Deployment

PostgreSQL, Redis, MinIO/S3, and Keycloak/OIDC are external services. Edit the
placeholder values in `backend/config.yaml`, `backend/secret.yaml`, and
`scanner/secret.yaml` before applying.

## Apply

```bash
kubectl create namespace skillhub
cp deploy/k8s/plain/backend/secret.yaml.example deploy/k8s/plain/backend/secret.yaml
cp deploy/k8s/plain/scanner/secret.yaml.example deploy/k8s/plain/scanner/secret.yaml
kubectl -n skillhub apply -f deploy/k8s/plain/backend/
kubectl -n skillhub apply -f deploy/k8s/plain/scanner/
kubectl -n skillhub apply -f deploy/k8s/plain/frontend/
kubectl -n skillhub wait --for=condition=ready pod --all --timeout=300s
```

## Verify

```bash
kubectl -n skillhub get deploy,svc
kubectl -n skillhub port-forward svc/skillhub-web 3000:80
kubectl -n skillhub port-forward svc/skillhub-server 8080:8080
```

Health checks:

```bash
curl http://localhost:8080/api/v1/health
curl http://localhost:3000/api/v1/health
```

## Optional Product Suite Admin Sync

The optional CronJob remains
`backend/product-suite-admin-sync-cronjob.yaml.example`, so applying the plain
backend directory does not enable it by default.

Build an organization image containing the private PIC source module, create
`skillhub-product-suite-sync-secret`, then copy and edit the example:

```bash
kubectl -n skillhub create secret generic skillhub-product-suite-sync-secret \
  --from-literal=PIC_API_TOKEN='<internal-secret>'
cp \
  deploy/k8s/plain/backend/product-suite-admin-sync-cronjob.yaml.example \
  deploy/k8s/plain/backend/product-suite-admin-sync-cronjob.yaml
kubectl -n skillhub apply \
  -f deploy/k8s/plain/backend/product-suite-admin-sync-cronjob.yaml
```

The shared source-module, API URL, timeout, identity-provider, dry-run, and
result contracts are documented in
[`../../../server-python/PRODUCT_SUITE_ADMIN_SYNC.zh.md`](../../../server-python/PRODUCT_SUITE_ADMIN_SYNC.zh.md).

For the environment variable manual, see
[`../environment-variables.zh.md`](../environment-variables.zh.md).
