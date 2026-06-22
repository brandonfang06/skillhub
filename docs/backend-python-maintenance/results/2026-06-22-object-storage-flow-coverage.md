# Object Storage Flow Coverage

Date: 2026-06-22

## Context

The scanner consumer bug showed that a Python cutover path could write skill
packages through the object storage adapter while a later worker still assumed
the bundle lived under the backend pod's local `storage_base_path`.

This follow-up added regression coverage for the same risk class: production
flows that must continue to work when `SKILLHUB_STORAGE_PROVIDER=s3` and skill
objects live in MinIO/S3 instead of the local filesystem.

## Coverage Added

- Publish write stores skill files and bundle through a supplied object storage
  adapter.
- Skill download reads prebuilt bundles through the object storage adapter.
- Review download reads prebuilt bundles through the object storage adapter.
- Rerelease rebuilds package entries from object storage keys.
- Replacement cleanup deletes old objects through the object storage adapter.

Each test uses a fake object storage adapter plus a missing local storage path,
so it fails if the flow regresses to direct local filesystem access.

## Verification

```powershell
cd server-python
uv run pytest tests/test_publish_orchestration.py tests/test_skill_download.py tests/test_review_download.py tests/test_skill_lifecycle_rerelease.py tests/test_publish_replacement.py -q
# 63 passed, 1 warning

uv run pytest tests -q
# 820 passed, 1 warning
```
