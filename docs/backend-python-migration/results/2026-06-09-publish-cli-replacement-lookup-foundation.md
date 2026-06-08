# Publish CLI Replacement Lookup Foundation Result

## Summary

Implemented route-level replacement lookup for the direct Python CLI publish write route.

The route still is not owned by Python through Vite/proxy. This milestone only lets the direct
Python backend on port `8081` find a same-owner same-slug same-version replaceable version and pass
it into the existing replacement cleanup orchestration.

## Routes Changed

No route ownership changed.

| Route | Before | After |
| --- | --- | --- |
| `POST /api/cli/v1/skills/{namespace}/publish` | Java-owned through proxy; direct Python route existed | Same ownership; direct Python route performs replacement lookup before write |

## Implemented

- Added `find_replaceable_version(...)` in Python replacement module.
- Direct CLI publish route now:
  - resolves namespace id;
  - uses dry-run to reject already published same-version conflicts;
  - finds a non-published same-version replacement for the same owner/slug;
  - passes `ReplaceableVersion` into `PublishWriteInput`.
- Existing orchestration performs cleanup:
  - review task delete;
  - old file row delete;
  - security audit soft delete;
  - old version row delete;
  - old local bundle/object deletion after commit.
- Added Windows live gate `verify-publish-cli-replacement-lookup-smoke`.

## Verification

Commands:

- `cd server-python; uv run pytest tests/test_publish_replacement.py tests/test_publish_http_validate.py tests/test_publish_orchestration.py tests/test_hybrid_makefile.py -q`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-cli-replacement-lookup-smoke`

Results:

- Narrow Python tests: `26 passed, 1 warning`.
- Windows live gate:
  - Python replacement tests: `26 passed, 1 warning`.
  - First direct Python publish: HTTP `200`.
  - Second direct Python publish with same slug/version: HTTP `200`.
  - DB version count for the slug/version after replacement: `1`.
  - First version id was replaced by a new version id.
  - Old bundle object existed before replacement and was deleted after replacement.
  - Vite/proxy publish write ownership still matched Java unauthenticated status.
  - Playwright smoke: `6 passed`.

## Deferred

- Pending-review auto-withdraw for other pending versions before creating a new version.
- Storage-failure cleanup evidence for route ownership.
- Scanner result/consumer processing.
- Full repeated publish Java/Python matrix before route ownership move.
- Portal publish write route ownership.

## Server Directory Guard

`server/` remained unmodified for this milestone.
