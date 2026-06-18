# Remove Presigned Download Config

Date: 2026-06-18

## Scope

Organization deployments do not allow client-facing object storage signed URLs.
The Python backend download path already proxies downloads through the backend:

1. client calls the SkillHub download API
2. backend reads package bytes from local storage or S3/MinIO
3. backend returns the file response to the client

No browser or CLI client needs direct MinIO/S3 access.

## Changes

- Removed unused S3 signed URL generation from `S3ObjectStorage`.
- Removed `SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY` from Python settings.
- Removed the presign ConfigMap key and env injection from kustomize and plain
  Kubernetes backend manifests.
- Removed the presign row from the Kubernetes environment variable manual.
- Removed the presign entry from `.env.release.example`.
- Added `server-python/ENVIRONMENT_VARIABLES.md` as the backend-owned runtime env
  var checklist for deployment.

## Verification

```powershell
cd server-python
uv run pytest tests/test_config.py tests/test_deployment_cutover.py tests/test_skill_download.py tests/test_publish_storage.py tests/test_publish_orchestration.py -q
```

Result:

```text
67 passed, 1 warning
```

Search verification:

```powershell
rg -n "presign|PRESIGN|storage-s3-presign|storage_s3_presign|generate_presigned_url|SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY|Presigned URL" server-python/app deploy/k8s .env.release.example .env.local.example server-python/ENVIRONMENT_VARIABLES.md compose.release.yml docker-compose.yml
```

Result: no matches.

Render verification:

```powershell
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config
git diff --check
```

Results:

```text
kustomize base rendered
release compose config rendered
no whitespace errors; only Windows LF-to-CRLF warnings
```
