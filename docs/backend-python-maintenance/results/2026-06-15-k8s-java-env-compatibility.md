# K8s Java Env Compatibility

Date: 2026-06-15

## Summary

Python backend now accepts the main Java/Spring deployment environment names so
an existing Java Kubernetes deployment can switch to the Python backend with
fewer Secret/ConfigMap rewrites.

## Runtime Changes

- PostgreSQL:
  - `SKILLHUB_DATABASE_URL` remains the preferred Python env.
  - `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, and
    `SPRING_DATASOURCE_PASSWORD` are accepted as fallback.
  - `jdbc:postgresql://...` is converted to `postgresql+asyncpg://...`.
- Redis:
  - Existing Spring-compatible Redis support remains in place.
- Session:
  - `SESSION_COOKIE_SECURE` is accepted as fallback for
    `SKILLHUB_SESSION_COOKIE_SECURE`.
- Scanner:
  - `SKILLHUB_SECURITY_SCANNER_URL` is accepted as fallback for
    `SKILLHUB_SECURITY_SCANNER_BASE_URL`.
  - `SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT` and
    `SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT` are accepted as fallback for the
    Python `_MS` names.
  - Java scanner analyzer flags such as `SKILLHUB_SCANNER_USE_LLM` now populate
    `ScannerHttpClient` options.
  - `SKILLHUB_SCANNER_AI_DEFENSE_API_KEY` is sent to Cisco scanner as the
    `X-AIDefense-Key` header.

## Deployment Docs

- `deploy/k8s/environment-variables.zh.md` now documents Java-compatible envs,
  Python preferred envs, and the values that still need format conversion.
- Kustomize and plain backend manifests expose backend scanner analyzer flags.
- Scanner LLM provider secrets remain on the scanner deployment, not backend.

## Verification

```powershell
cd server-python
python -m pytest tests\test_config.py tests\test_session_auth.py tests\test_publish_scan_daemon.py tests\test_publish_scanner_client.py -q
```

Result:

```text
39 passed
```

