# Skill Scanner Backend Runtime Guide

## Overview

The Python backend owns the security-scanning chain around `skill-scanner`:

1. a publish transaction stores the version, security audit, review intent, and
   durable `scan_task_outbox` row atomically;
2. the outbox daemon claims due rows and publishes each stable `task_id` to the
   Redis Stream;
3. the consumer reclaims pending deliveries, ignores already-completed task IDs,
   stages the bundle, and calls `skill-scanner`;
4. the result is stored in `security_audit`; and
5. the version moves to `PENDING_REVIEW`, or `SCAN_FAILED` after terminal failure.

The Web UI reads audit details through the backend API. It never calls the
scanner directly.

## Runtime Modes

Two runtime modes are supported:

- `local`
  Use `POST /scan` and pass a filesystem path. This only works when SkillHub and `skill-scanner` can see the same files.
- `upload`
  Use `POST /scan-upload` and upload the package archive. This is the safer default for split deployments.

Recommended usage:

- local development with shared filesystem: `local`
- Kubernetes or any split-service deployment: `upload`

## Backend Configuration

Important environment variables:

- `SKILLHUB_SECURITY_SCANNER_ENABLED`
- `SKILLHUB_SECURITY_SCANNER_BASE_URL` (`..._URL` remains a compatibility alias)
- `SKILLHUB_SECURITY_SCANNER_MODE`
- `SKILLHUB_SCAN_STREAM_KEY`
- `SKILLHUB_SCAN_CONSUMER_ENABLED`
- `SKILLHUB_SCAN_CONSUMER_GROUP_NAME`
- `SKILLHUB_SCAN_CONSUMER_NAME`

Outbox tuning variables and defaults:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `SKILLHUB_SECURITY_OUTBOX_BATCH_SIZE` | `50` | Maximum claims per dispatch pass |
| `SKILLHUB_SECURITY_OUTBOX_MAX_ATTEMPTS` | `10` | Terminal-attempt boundary |
| `SKILLHUB_SECURITY_OUTBOX_LEASE` | `120` seconds | Claim lease before reclaim |
| `SKILLHUB_SECURITY_OUTBOX_MAX_BACKOFF` | `300` seconds | Retry backoff cap |
| `SKILLHUB_SECURITY_OUTBOX_DISPATCH_INTERVAL_MS` | `5000` | Daemon poll interval |
| `SKILLHUB_SECURITY_OUTBOX_SENT_RETENTION_DAYS` | `7` | Sent-row retention |
| `SKILLHUB_SECURITY_OUTBOX_CLEANUP_INTERVAL_SECONDS` | `86400` | Cleanup interval |

Changing these values affects delivery load and incident evidence. Keep defaults
unless monitoring proves a need, and coordinate retention with the instance's
privacy policy.

Scanner-side optional environment variables:

- `SKILL_SCANNER_LLM_API_KEY`
- `SKILL_SCANNER_LLM_BASE_URL`
- `SKILL_SCANNER_LLM_MODEL`

If the LLM variables are absent, the scanner should still run with non-LLM analyzers.

## Kubernetes Notes

Current repository manifests assume **separate** `skillhub-server` and `skillhub-scanner` deployments.
Because these deployments do not share a writable package directory, Kubernetes should use:

```text
SKILLHUB_SECURITY_SCANNER_MODE=upload
SKILLHUB_SECURITY_SCANNER_BASE_URL=http://skillhub-scanner:8000
```

Relevant manifests:

- `deploy/k8s/base/scanner-deployment.yaml`
- `deploy/k8s/base/services.yaml`
- `deploy/k8s/base/backend-deployment.yaml`
- `deploy/k8s/base/configmap.yaml`

The scanner service is internal-only by default and is consumed by the backend through cluster DNS.

## Verification

Verify the scanner service itself:

```bash
sh scripts/verify-scanner.sh http://localhost:8000
sh scripts/verify-scanner.sh http://localhost:8000 /path/to/skill.zip
```

Recommended backend checks after enabling the feature:

1. publish a test package
2. confirm the version status becomes `SCANNING`
3. confirm a `security_audit` row is created
4. confirm the matching `scan_task_outbox` row reaches `SENT` and the Redis
   message retains the same `task_id`
5. confirm duplicate delivery does not execute the completed task twice
6. confirm the version eventually moves to `PENDING_REVIEW` or `SCAN_FAILED`
7. call `GET /api/v1/skills/{skillId}/versions/{versionId}/security-audit`

## Audit Query API

Backend audit data is available from:

```text
GET /api/v1/skills/{skillId}/versions/{versionId}/security-audit
```

Response fields include:

- `scanId`
- `scannerType`
- `verdict`
- `isSafe`
- `maxSeverity`
- `findingsCount`
- `findings`
- `scanDurationSeconds`
- `scannedAt`
- `createdAt`

## Failure Semantics

- Redis publication failure leaves a durable outbox row for retry; it does not
  erase the scan intent or roll the published version into a false success state.
- Expired dispatch leases can be reclaimed. Backoff is bounded, and the final
  outbox failure is retained as `FAILED` with the last error for operators.
- Consumer pending messages can be reclaimed. A stable `task_id` prevents a
  completed scan from executing twice after duplicate delivery.
- Terminal scanner failure marks the version `SCAN_FAILED`; the review task
  remains available so the package does not get stuck without governance.
- Sent outbox rows are cleaned only after the configured retention period.

This keeps the existing human review path intact while making scanner failures visible.

Uploaded archives and findings can contain personal, confidential, or credential
data. Operators that use an external or LLM-backed scanner must document that
data flow, redact where feasible, restrict logs, and align outbox/audit retention
with [`PRIVACY_AND_DATA_GOVERNANCE.md`](./PRIVACY_AND_DATA_GOVERNANCE.md).
