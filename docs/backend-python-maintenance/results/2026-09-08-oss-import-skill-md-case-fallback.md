# OSS manifest filename compatibility verification

Baseline: `668896a7` (`dev`, synced on 2026-09-08).
Branch: `codex/oss-import-skill-md-fallback`.

## Delivered behavior

The standalone Python importer discovers ASCII case variants of `SKILL.md`,
records the actual manifest name, and writes it as canonical `SKILL.md` in the
ZIP. Source bytes and checkout files are unchanged. Multiple case variants in
one directory fail before any API call. Manifest symlinks are not followed.
Nested skill roots remain independent. Case-only changes produce identical ZIP
bytes. A sanitized metadata-only event records canonicalization.

Chinese SOP updated in `deploy/k8s/oss-github-source-import.zh.md`. Operators
copy the updated importer Python files into their pipeline project. No new
runtime dependency, variable, endpoint, migration, or CLI build is needed.

## Tests and commands

- Red: `uv run pytest tests/test_package.py -q`: lowercase and mixed-case
  fixtures failed discovery (2 failed, 1 passed) before implementation.
- Windows final: `uv run --project tools/oss-source-importer pytest
  tools/oss-source-importer/tests server-python/tests/test_oss_source_import_docs.py
  --noconftest -q`: 64 passed, 2 platform skips.
- `uv run --project tools/oss-source-importer ruff check
  tools/oss-source-importer/src tools/oss-source-importer/tests`: passed.
- Linux `python:3.8-bookworm`, read-only source mount, pytest <8.4 + tomli
  installed for testing only: full importer suite 62 passed, no skips.
- Separate Linux directory containing both `SKILL.md` and `skill.md`: discovery
  raised the expected ambiguity error.
- `git diff --check`: passed.

## Real service verification

Built current backend, scanner and Web images and started a fresh Compose
project with PostgreSQL, Redis, MinIO, scanner, FastAPI, root Web and subpath
Web. All seven services healthy.

Commands (repository root):

```powershell
docker compose -p skillhub-oss-case-smoke --env-file .env.release.example -f compose.release.yml -f docker-compose.oss-source-import-test.yml up -d --build
./scripts/oss-source-import-smoke-test.ps1 -ComposeProject skillhub-oss-case-smoke -KeepTemporaryRoot
```

Successful run: `e871a7c9636a`, 2026-09-08 12:01 UTC.
Initial fixture SHA: `d8141b64261d6ae187a01e3f702d29b2b9c673e5`.
Changed SHA: `1e043ceb6895935dcf2dca31c56e27e0d2e7dff6`.

- Python 3.8 runner shallow-cloned a Git repository with lowercase
  `skills/alpha/skill.md`; the existing Git transport rewrite models internal
  GitLab using a local read-only repository. External GitLab credentials and
  network were not exercised.
- First import: 3 imported; all actual scanner results SAFE; review attribution,
  owner, namespace membership and service-principal audit assertions passed.
- Approved Alpha via review endpoint, downloaded via authenticated HTTP, and
  verified exactly one `SKILL.md`, no lowercase entry, and identical source bytes.
- Retry: 3 skipped, zero new submissions.
- Changed Alpha via `/skillhub`: 1 imported, 2 skipped. Original owner retained;
  second initiator recorded as review submitter.
- Final PostgreSQL: Alpha original PUBLISHED/SAFE; its new version and two other
  skills PENDING_REVIEW/SAFE. Zero active smoke service tokens and zero idle-in-
  transaction sessions. No backend errors after test configuration correction.

## Verification issues resolved

The existing smoke Compose placed scan staging at
`/var/lib/skillhub/storage-scan-temp`; its parent is root-owned in the current
non-root backend image. The first run correctly failed review with scan errors
for uppercase and lowercase skills alike. The test Compose now places
`SKILLHUB_STORAGE_BASE_PATH` at `/var/lib/skillhub/storage/local`, keeping the
derived staging directory inside the writable volume. The smoke assertion now
requires `security_audit.is_safe=true` before approval.

A second attempt found Windows Git line-ending conversion in the temporary
fixture. The fixture repo now explicitly disables `core.autocrlf`, allowing an
exact byte comparison with the Linux-cloned source. Importer content processing
was not changed to work around line endings.

Deployment follow-up: any S3 scan-consumer deployment using the same default
storage path must ensure its derived `-scan-temp` sibling is writable. This
change fixes only the smoke configuration; production manifests/image defaults
were not changed.

## Security and retained state

CIA review: no new identity or data boundary; logs use existing quoting and
redaction. Ambiguous manifests fail closed; canonical ZIP content remains bound
to the existing backend fingerprint, scanner and review workflow. No bypass was
used. Test tokens are revoked in the smoke script's finally block.

Isolated test database and object storage remain for inspection. Temporary
fixture/report directories under the OS temp directory were intentionally
retained using `-KeepTemporaryRoot`; no existing user data was removed. Services
remain at ports 58080 (root), 58081 (backend), 58082 (`/skillhub`).

User authorized commit and push to `dev` on 2026-09-08 after verification.
