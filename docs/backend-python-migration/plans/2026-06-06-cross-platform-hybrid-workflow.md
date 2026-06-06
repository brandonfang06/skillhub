# Cross-Platform Hybrid Workflow Plan

## Milestone

Document the hybrid local workflow for the three expected development
environments: Windows, macOS, and Ubuntu.

## Boundary

Allowed changes:

- `docs/backend-python-migration/**`
- `server-python/tests/**`

Forbidden changes:

- `server/**`

## Implementation Steps

1. Add a failing test that requires `hybrid-local-e2e.md` to cover Windows,
   macOS, and Ubuntu.
2. Update the hybrid workflow document with per-platform prerequisites and
   commands.
3. Run Python tests.
4. Verify no `server/` paths changed.
5. Record the result, commit, and push.

## Acceptance Criteria

- Windows workflow documents `scripts/dev-hybrid.ps1`.
- macOS workflow documents `make dev-all-hybrid` and Homebrew/Colima options.
- Ubuntu workflow documents `make dev-all-hybrid`, Docker Engine, and apt
  prerequisites.
- `cd server-python; UV_CACHE_DIR=.uv-cache uv run pytest` passes.
- `git diff --name-only -- server` has no output.

