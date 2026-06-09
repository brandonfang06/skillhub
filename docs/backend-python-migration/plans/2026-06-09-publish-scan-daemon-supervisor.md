# Publish Scan Daemon Supervisor Plan

## Milestone

Add a Python scan consumer daemon/supervisor that can run inside the FastAPI process.

The scanner pipeline already supports one-pass consume/reclaim and real scanner HTTP calls. This
milestone wires that runtime into the FastAPI lifespan behind an explicit environment flag so local
and production-like runs can process scan tasks without manually invoking fixture scripts.

## Scope

Implemented:

- `SKILLHUB_SCAN_CONSUMER_ENABLED` flag, default `false`;
- scan consumer group/consumer name/count/block/reclaim interval settings;
- background daemon class that loops:
  - `consume_once(...)`;
  - `reclaim_once(...)`;
  - sleep briefly on errors;
  - stop on cancellation/shutdown;
- FastAPI lifespan startup/shutdown integration;
- unit tests for disabled startup, enabled startup, loop execution, and graceful shutdown;
- Windows live gate that starts Python backend with daemon enabled, publishes a Redis scan task,
  and verifies it is consumed without invoking the fixture consumer.

Not implemented:

- separate worker process or process supervisor outside FastAPI;
- multi-consumer scaling policy;
- advanced Redis auth/TLS/cluster support;
- route ownership changes.

## Java Parity Checklist

- Java reference files:
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/AbstractStreamConsumer.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/ScanTaskConsumer.java`
- API contract: not applicable. This milestone does not expose or move an HTTP route.
- Authorization/session behavior: not applicable. Scan daemon is internal backend work.
- Database transaction atomicity: unchanged from scan consumer runtime. Each message is processed
  through the same one-message transaction and ACK/retry/failure flow.
- Audit fields: unchanged from scanner result application.
- Storage and side effects: unchanged from worker boundary; staged bundles are still cleaned after
  message processing.
- Live verification evidence: required through
  `verify-publish-scan-daemon-supervisor-smoke`.

## Route Ownership

No route ownership changes.

## Verification

- `cd server-python; uv run pytest tests/test_publish_scan_daemon.py tests/test_publish_scanner_client.py tests/test_publish_scan_consumer.py tests/test_publish_scan_worker.py tests/test_publish_scanner_result.py tests/test_config.py tests/test_hybrid_makefile.py -q`
- Windows live gate:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-scan-daemon-supervisor-smoke`
- `git diff --name-only -- server` must be empty.
