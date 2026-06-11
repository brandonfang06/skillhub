# Skill Hard Delete Migration Plan

## Milestone

Move the whole-skill hard-delete routes to Python while keeping ClawHub placeholder
delete/undelete routes Java-owned.

## Route Ownership

Python-owned after this milestone:

- `DELETE /api/v1/skills/id/{skillId}`
- `DELETE /api/v1/skills/{namespace}/{slug}`
- `DELETE /api/web/skills/id/{skillId}`
- `DELETE /api/web/skills/{namespace}/{slug}`

Still Java-owned:

- `DELETE /api/v1/skills/{canonicalSlug}`
- `POST /api/v1/skills/{canonicalSlug}/undelete`

The Vite proxy rules must be method-aware so skill version delete, tag delete, label
detach, ClawHub delete, and ClawHub undelete retain their existing owners.

## Java References

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillDeleteController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillLifecycleDeleteController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillDeleteAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillHardDeleteService.java`
- `server/skillhub-app/src/test/java/com/iflytek/skillhub/service/SkillDeleteAppServiceTest.java`

## API Contract

- Successful delete response uses the standard Java envelope with localized delete success
  message and data `{ skillId, namespace, slug, deleted }`.
- Slug delete is idempotent for missing or ambiguous targets and returns
  `{ skillId: null, namespace, slug, deleted: false }`.
- ID delete rejects missing skill or namespace as `error.skill.notFound` /
  `error.namespace.notFound`.
- `namespace` may include a leading `@`; Python must normalize it like Java.

## Authorization

- `/api/v1/skills/...` hard delete requires `SUPER_ADMIN`.
- `/api/web/skills/...` hard delete allows `SUPER_ADMIN` or the skill owner.
- Anonymous or missing mock-user requests return `401`.
- Non-owner/non-super-admin portal users return `403`.

## Data and Side Effects

Python must mirror the Java hard-delete transaction:

- Remove `skill_search_document` for the skill.
- Clear `skill.latest_version_id`, set `updated_by`, then delete dependent rows.
- Delete pending review tasks for all skill versions.
- Delete promotion requests where the skill is source or target.
- Delete skill tags, stars, ratings, reports, version stats, security audits,
  skill files, versions, and finally the skill row.
- Record `DELETE_SKILL_HARD` audit with `namespaceId` and `slug`.
- Delete local storage keys after DB commit where possible. If local deletion fails,
  record `skill_storage_delete_compensation`.

## Java Parity Checklist

- API contract: covered.
- Authorization/session behavior: covered for local `X-Mock-User-Id`; Spring Session and
  bearer-token filters remain deferred per migration plan.
- Database transaction atomicity: covered for DB mutations in one transaction. Storage deletion
  remains after-commit/compensated, matching Java.
- Audit actor/timestamp fields: covered.
- Storage and side effects: covered for local storage keys and compensation records.
- Live verification evidence: required before commit.

## Tests

- Add focused Python unit tests for route envelopes, auth, idempotent slug delete,
  and hard-delete SQL/storage behavior.
- Update Vite proxy tests for method-aware route ownership and ClawHub delete/undelete
  boundaries.
- Add a Windows live gate action comparing Java/Python/proxy stable contracts and DB
  deletion evidence.

## Boundaries

- Do not modify `server/`.
- Do not change generated OpenAPI files.
- Do not migrate ClawHub delete/undelete placeholders.
- Do not implement final auth/session/bearer-token replacement in this milestone.
