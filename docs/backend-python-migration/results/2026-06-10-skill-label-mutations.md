# Skill Label Mutations Result

## Summary

Moved skill label attach/detach routes to FastAPI:

- `PUT /api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`
- `PUT /api/web/skills/{namespace}/{slug}/labels/{labelSlug}`
- `DELETE /api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`
- `DELETE /api/web/skills/{namespace}/{slug}/labels/{labelSlug}`

This completes the skill-label route family after public label reads and admin label-definition management had already moved to Python.

## Behavior Implemented

- Attach:
  - Requires an authenticated mock user.
  - Allows skill owner, namespace `ADMIN`, namespace `OWNER`, or `SUPER_ADMIN`.
  - Rejects `PRIVILEGED` label attach unless the actor is `SUPER_ADMIN`.
  - Preserves Java max-label guard at 10 labels per skill.
  - Preserves existing-label idempotency.
  - Returns Java-compatible `SkillLabelDto` and update envelope.
  - Writes `SKILL_LABEL_ATTACH` audit on target type `SKILL`.
- Detach:
  - Uses the same permission rules as attach.
  - Rejects missing skill-label with `label.skill.not_found`.
  - Returns `{"message":"Label detached"}` and delete envelope.
  - Writes `SKILL_LABEL_DETACH` audit on target type `SKILL`.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_skill_label_mutations.py tests/test_labels.py tests/test_hybrid_makefile.py -q`
  - Passed: 16 tests.
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Passed: 34 tests.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-skill-label-mutation-smoke`
  - Passed.
  - Compared Java direct, Python direct, and Vite proxy for attach and detach.
  - Compared response envelopes, DB `skill_label` state, and `audit_log` entries.

## Notes

- The live gate uses owner-managed `RECOMMENDED` labels. Unit tests cover namespace-admin idempotency, `PRIVILEGED` restriction, max-label guard, route envelopes, and missing detach behavior.
- The fixture SQL initially exposed PL/pgSQL variable-name ambiguity (`skill_id`, `label_id`); fixed by using non-conflicting variable names in the live gate fixture.

## Remaining Work

- Admin password reset remains Java-owned.
- Legacy governance notification mark-read remains Java-owned.
- Notification SSE remains Java-owned.
- Web download aliases remain Java-owned unless product usage requires Python ownership.
- Auth/OAuth/token surfaces remain Java-owned and should be handled with a dedicated security plan.
