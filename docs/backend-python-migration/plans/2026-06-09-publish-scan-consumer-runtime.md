# Publish Scan Consumer Runtime Plan

## Milestone

Add the Python Redis Stream consumer runtime for scan tasks.

The previous milestone proved that Python can process one parsed scan task. This milestone wraps
that boundary with Java-compatible Redis consumer group operations:

1. create the stream consumer group if needed;
2. read never-delivered messages with `XREADGROUP`;
3. process each message through the existing one-task worker;
4. acknowledge invalid, successful, retried, and permanently failed messages;
5. republish failed messages with incremented `retryCount` while retry count is below Java's max;
6. reclaim pending messages with `XAUTOCLAIM` and process them through the same handler.

## Scope

Implemented:

- dependency-free Redis Stream command helpers for `XGROUP CREATE`, `XREADGROUP`, `XACK`, `XADD`,
  and `XAUTOCLAIM`;
- consumer group initialization;
- one-batch `consume_once(...)` runtime for never-delivered messages;
- one-pass `reclaim_once(...)` runtime for idle pending messages;
- Java-compatible max retry count of `3`;
- retry republish preserving task id, version id, `skillPath`/`bundleKey`, scanner type, and
  incrementing `retryCount`;
- deterministic fixture script for Windows live verification.

Not implemented:

- long-running background process manager;
- daemon lifecycle / supervisor integration;
- scanner HTTP client;
- Redis auth, TLS, non-default DB selection, or Sentinel/Cluster support.

Those remain separate milestones. This milestone deliberately keeps scanner calls behind the
existing `ScannerClient` abstraction.

## Java Parity Checklist

- Java reference files:
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/AbstractStreamConsumer.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/ScanTaskConsumer.java`
  - `server/skillhub-app/src/main/java/com/iflytek/skillhub/stream/RedissonScanTaskProducer.java`
- API contract: not applicable. This milestone does not expose or move an HTTP route.
- Authorization/session behavior: not applicable. Scan consumers are internal workers.
- Database transaction atomicity: covered at one-task processing level. Redis ACK occurs after
  processing, retry republish, invalid-message discard, or permanent failure marking completes.
- Audit actor/timestamp fields: covered through the existing scanner result application boundary.
- Storage and side effects: covered for bundle staging/cleanup through the one-task worker.
  Consumer runtime adds Redis retry/ACK/reclaim behavior.
- Live verification evidence: required through
  `verify-publish-scan-consumer-runtime-smoke`.

## Route Ownership

No route ownership changes.

## Verification

- `cd server-python; uv run pytest tests/test_publish_scan_consumer.py tests/test_publish_scan_worker.py tests/test_publish_scanner_result.py tests/test_hybrid_makefile.py -q`
- Windows live gate:
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-scan-consumer-runtime-smoke`
- `git diff --name-only -- server` must be empty.
