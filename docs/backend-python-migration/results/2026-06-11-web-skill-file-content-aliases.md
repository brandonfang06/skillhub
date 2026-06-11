# Web Skill File Content Alias Migration Result

## Summary

Moved these web single-file content aliases to Python:

- `GET /api/web/skills/{namespace}/{slug}/versions/{version}/file`
- `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/file`

The routes reuse the already migrated v1 file content readers and preserve Java's raw
`application/octet-stream` response behavior.

## Java Parity Checklist Outcome

- API contract: covered. Java and Python return raw bytes with `application/octet-stream`.
- Authorization/session behavior: covered. The web aliases share the v1 Python handler and forward
  the normalized optional current user.
- Database transaction atomicity: not applicable. Read-only route.
- Audit actor/timestamp fields: not applicable. No audit side effects.
- Storage and side effects: covered. Reuses existing Python storage read path with no mutations.
- Live verification evidence: covered.

## Tests

- Red: `uv run pytest tests/test_skill_file_content.py tests/test_route_registry.py -q`
  failed with four web alias `404` assertions and missing route-registry/sequence assertions.
- Red: `npm.cmd run test -- vite.config.test.ts` failed because web `/file` aliases were not routed
  to Python.
- Green: `uv run pytest tests/test_skill_file_content.py tests/test_route_registry.py -q`
  passed with `21 passed, 1 warning`.
- Green: `npm.cmd run test -- vite.config.test.ts` passed with `46 passed`.

## Live Verification

Hybrid stack:

- Java backend: `http://localhost:8080`
- Python backend: `http://localhost:8081`
- Vite proxy: `http://localhost:3000`

Fixture:

- Namespace: `global`
- Skill: `codex-java-write-20260608223249973`
- Version: `1.0.20260608223249973`
- File path: `SKILL.md`

Positive parity evidence:

| Case | Target | Status | Content-Type | Bytes | SHA-256 |
| --- | --- | --- | --- | --- | --- |
| version web file | Java | 200 | `application/octet-stream` | 613 | `384847275d73aadad089d7ecc85d647269737de445a877215383487167a06f4d` |
| version web file | Python | 200 | `application/octet-stream` | 613 | `384847275d73aadad089d7ecc85d647269737de445a877215383487167a06f4d` |
| version web file | Vite proxy | 200 | `application/octet-stream` | 613 | `384847275d73aadad089d7ecc85d647269737de445a877215383487167a06f4d` |
| tag web file | Java | 200 | `application/octet-stream` | 613 | `384847275d73aadad089d7ecc85d647269737de445a877215383487167a06f4d` |
| tag web file | Python | 200 | `application/octet-stream` | 613 | `384847275d73aadad089d7ecc85d647269737de445a877215383487167a06f4d` |
| tag web file | Vite proxy | 200 | `application/octet-stream` | 613 | `384847275d73aadad089d7ecc85d647269737de445a877215383487167a06f4d` |

Additional negative parity note:

- Fixture `codex-download-team/codex-download-20260608` had empty file metadata; fixture
  `global/java-promotion-approve-20260609180946446` had metadata but missing storage content. Java,
  Python, and proxy all returned `400` for that missing-content case, so it was not used as the
  positive byte fixture.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_file_content.py`
- `server-python/tests/test_route_registry.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-11-web-skill-file-content-aliases.md`

No files under `server/` were modified for this milestone.
