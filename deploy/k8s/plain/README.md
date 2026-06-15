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
kubectl -n skillhub port-forward svc/skillhub-web 8080:80
kubectl -n skillhub port-forward svc/skillhub-server 8081:8080
```

Health checks:

```bash
curl http://localhost:8081/api/v1/health
curl http://localhost:8080/api/v1/health
```

For the environment variable manual, see
[`../environment-variables.zh.md`](../environment-variables.zh.md).
