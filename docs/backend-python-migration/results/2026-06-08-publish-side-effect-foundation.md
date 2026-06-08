# Publish Side-Effect Foundation Result

Date: 2026-06-08

## Summary

Completed the Python publish side-effect foundation. This milestone adds helper logic for the
publish workflow steps that happen after the DB transaction foundation: review task creation,
scanner audit/task planning, version scan-state transition, event intents, and ClawHub publish audit
payloads.

No publish HTTP route ownership changed. Java remains the owner for all publish POST routes.

## Route Ownership

| Route | Owner Before | Owner After | Notes |
| --- | --- | --- | --- |
| `POST /api/v1/skills` | Java | Java | Verified through Vite ownership gate. |
| `POST /api/v1/publish` | Java | Java | Verified through Vite ownership gate. |
| `POST /api/v1/skills/{namespace}/publish` | Java | Java | Verified through Vite ownership gate. |
| `POST /api/web/skills/{namespace}/publish` | Java | Java | Verified through Vite ownership gate. |
| `POST /api/cli/v1/skills/{namespace}/publish/validate` | Java | Java | No proxy ownership change. |
| `POST /api/cli/v1/skills/{namespace}/publish` | Java | Java | No proxy ownership change. |

## Implemented

- Added `server-python/app/publish/side_effects.py`.
- Added Java-compatible side-effect planning:
  - `PENDING_REVIEW` creates review task and `ReviewSubmittedEvent` intent.
  - `PUBLISHED` creates `SkillPublishedEvent` intent.
  - `UPLOADED` / private publish creates neither review task nor published event.
- Added security scan foundation behavior:
  - creates `security_audit` seed row values matching Java defaults;
  - builds scan task payload for upload mode using bundle key;
  - builds scan task payload for local mode using temp skill path;
  - changes non-published versions to `SCANNING` when scanner is enabled;
  - keeps `PUBLISHED` versions published when scanner is enabled.
- Added ClawHub compat publish audit payload and `audit_log` insert helper.
- Added `verify-publish-side-effects-foundation-smoke` to the Windows hybrid verification script.

## Explicitly Not Implemented

- No Python publish HTTP route.
- No Vite publish POST ownership change.
- No live Python DB mutation through HTTP.
- No actual scanner HTTP call.
- No Redis stream publishing.
- No notification delivery.
- No replacement cleanup or storage compensation.
- No CSRF/session bridge changes.

## Verification

Focused checks:

```text
cd server-python
uv run pytest tests/test_publish_side_effects.py tests/test_hybrid_makefile.py -q
16 passed in 0.33s
```

Final verification:

```text
cd server-python
uv run pytest
220 passed, 1 warning in 3.51s
```

```text
cd web
.\node_modules\.bin\vitest.CMD vite.config.test.ts --run
1 passed, 18 tests passed
```

```text
cd web
.\node_modules\.bin\tsc.CMD --noEmit
exit 0
```

```text
scripts\dev-hybrid.ps1 verify-publish-side-effects-foundation-smoke
10 passed
allProxyMatchesJava: true
6 passed
```

```text
netstat -ano | Select-String ':3000\s|:8080\s|:8081\s'
Only TIME_WAIT entries; no LISTENING ports remained.
```

```text
git diff --check
Only CRLF conversion warnings; no whitespace errors.
```

```text
git diff --name-only -- server
No output.
```

## Risks

- The helper returns event/scan-task intents; it does not yet publish them to Java-compatible async
  infrastructure.
- Scanner behavior is covered as DB/task payload foundation only; scanner worker integration and
  result processing remain future route/workflow work.
- Review task and audit log SQL are fake-connection tested in this milestone. A real DB write gate
  should be added before a Python publish route is enabled.

## Follow-Up

The next milestone should decide whether to:

- add replacement cleanup and storage compensation before route ownership; or
- implement a first internal publish POST route and run a real DB/storage/scanner/review workflow
  gate against deterministic fixtures.
