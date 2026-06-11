# ClawHub Delete Undelete Placeholder Result

## Summary

Moved the ClawHub placeholder delete/undelete routes to Python:

- `DELETE /api/v1/skills/{canonicalSlug}`
- `POST /api/v1/skills/{canonicalSlug}/undelete`

The routes preserve Java's current placeholder contract: authenticated route boundary and plain
JSON `{ ok: true }`, with no database or storage side effects.

## Java Reference

Java `ClawHubCompatController` delegates both routes to:

- `ClawHubCompatAppService.deleteSkill()`
- `ClawHubCompatAppService.undeleteSkill()`

Both methods return `new ClawHubDeleteResponse()`, whose default constructor sets `ok = true`.
The canonical slug is accepted by the controller but not used by the service.

## Routes Changed

| Method | Path | Owner before | Owner after | Behavior |
| --- | --- | --- | --- | --- |
| DELETE | `/api/v1/skills/{canonicalSlug}` | java | python | Requires current user; returns plain `{ ok: true }`. |
| POST | `/api/v1/skills/{canonicalSlug}/undelete` | java | python | Requires current user; returns plain `{ ok: true }`. |

## Tests

Red route test before implementation:

```powershell
cd server-python
uv run pytest tests/test_clawhub_skill_detail.py -q
```

Result before implementation: `1 failed, 4 passed`; `DELETE /api/v1/skills/demo` returned `405`
because Python did not own the placeholder route yet.

Passed after FastAPI route implementation:

```powershell
cd server-python
uv run pytest tests/test_clawhub_skill_detail.py -q
```

Result: `5 passed, 1 warning`.

Red proxy test before Vite rules:

```powershell
cd web
npm.cmd run test -- vite.config.test.ts
```

Result before proxy rules: `2 failed, 44 passed`; one-segment ClawHub delete/undelete still routed
to Java fallback.

Passed after proxy rules and doc guard updates:

```powershell
cd web
npm.cmd run test -- vite.config.test.ts
```

Result: `46 passed`.

```powershell
cd server-python
uv run pytest tests/test_clawhub_skill_detail.py tests/test_route_registry.py -q
```

Result: `7 passed, 1 warning`.

## Live Verification

Hybrid stack startup:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 -Action up
```

Result: Java, Python, scanner, Vite, and Vite proxy health routes became ready.

Live HTTP checks:

- Unauthenticated `DELETE /api/v1/skills/codex-placeholder` returned `401` on Java, direct Python,
  and Vite proxy.
- Unauthenticated `POST /api/v1/skills/codex-placeholder/undelete` returned `401` on Java, direct
  Python, and Vite proxy.
- Mock-authenticated direct Python delete/undelete returned `{ ok: true }`.
- Mock-authenticated Vite proxy delete/undelete returned `{ ok: true }`.

Direct Java mock-authenticated comparison was not possible with `X-Mock-User-Id` because the Java
ClawHub controller uses `@AuthenticationPrincipal PlatformPrincipal`; the mock header does not
construct that principal for this controller. The unauthenticated Java boundary and Java DTO/service
code were used as the Java reference evidence.

Hybrid shutdown:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 -Action down
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 -Action status
```

Result: Java backend, Python backend, and Vite frontend were stopped; Docker compose had no running
project services.

## Review Pass

- Java source under `server/` was read-only.
- Python route order keeps one-segment ClawHub delete separate from two-segment namespace/slug hard
  delete.
- Vite rules match only one-segment delete and one-segment undelete; nested SkillHub hard-delete,
  version-delete, tag-delete, and label-delete rules remain Python-owned through their existing
  specific patterns.
- The broad unmatched `/api/**` fallback remains Java-owned.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/tests/test_clawhub_skill_detail.py`
- `server-python/tests/test_route_registry.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-11-clawhub-delete-undelete-placeholders.md`
- `docs/backend-python-migration/results/2026-06-11-clawhub-delete-undelete-placeholders.md`
