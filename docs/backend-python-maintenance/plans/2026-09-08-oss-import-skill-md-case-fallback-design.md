# OSS Import `skill.md` Case Fallback Design

**Status:** Implemented and verified; commit/push authorized on 2026-09-08.

## Problem

The GitLab OSS importer currently discovers only files named exactly
`SKILL.md`. Some GitHub-origin repositories use `skill.md` or another ASCII
case variant, so those skill roots are skipped and a repository containing
only those files fails with `No exact-case SKILL.md files were found`.

The Python backend already canonicalizes any case variant of `skill.md` to
`SKILL.md` while extracting a ZIP. The compatibility gap is therefore in the
standalone importer, not in the backend package contract.

## Proposed Decision

Accept one case-insensitive ASCII match for `SKILL.md` per directory during
OSS importer discovery, then write that manifest into the deterministic ZIP as
canonical `SKILL.md`.

- Keep `SKILL.md` as the only canonical SkillHub package entry and documented
  protocol name.
- Do not rename or modify files in the checked-out GitLab repository.
- Preserve the manifest content byte-for-byte; only its ZIP entry name is
  canonicalized.
- Keep the repository-relative parent directory as `sourcePath`, so changing
  only the manifest filename case does not create a different SkillHub skill.
- If one directory contains multiple case variants, such as both `SKILL.md`
  and `skill.md` on a case-sensitive filesystem, fail discovery as ambiguous.
  Do not silently prefer or discard either file.
- Keep nested-root exclusion unchanged: every discovered manifest parent is an
  independent skill root and is excluded from an ancestor package.
- Emit a metadata-only job-log event when a non-canonical filename is mapped
  to `SKILL.md`; never log manifest content.

## Module Seam

Keep the public importer flow unchanged:

1. `discover_skill_roots(...)` resolves the single manifest filename for each
   root and returns it with the existing source directory identity.
2. `build_skill_package(...)` maps only that selected root manifest to the ZIP
   path `SKILL.md` and preserves every other relative path.
3. The existing source-import HTTP client submits the canonical ZIP without a
   new request field or endpoint.

This keeps compatibility behavior local to the importer and avoids teaching
the orchestrator, backend workflow, scanner, frontend, or public CLI about a
second canonical filename.

## Security Review

- **Confidentiality:** No new data or credential crosses a trust boundary.
  Logs contain only source path and filename, never package content or tokens.
- **Integrity:** Ambiguous case variants fail closed. Manifest bytes remain
  unchanged, the archive exposes exactly one canonical `SKILL.md`, and the
  backend continues to compute the authoritative normalized fingerprint.
- **Availability:** Discovery remains one bounded filesystem walk with no new
  external calls or retries. Invalid or ambiguous repositories terminate with
  the existing discovery/package failure class before API mutation.
- **Trust boundaries:** GitLab checkout content remains untrusted input. The
  existing archive limits, backend validation, scanner, and namespace-owner
  review remain mandatory.

## Verification

Add tests before implementation for:

- exact `SKILL.md`, lowercase `skill.md`, and a mixed-case filename;
- multiple case variants in one directory producing an explicit ambiguity
  error, tested through discovery with a simulated filesystem listing on Windows
  and an actual case-sensitive Linux directory;
- deterministic ZIP output containing `SKILL.md` and not the source-case name;
- byte-for-byte manifest preservation;
- unchanged sorting and nested-root exclusion across mixed filename cases;
- no-skill repositories still failing;
- updated Chinese operator documentation and error guidance.

Then run the importer unit suite and the real Compose OSS import smoke flow
with PostgreSQL, Redis, MinIO/S3, scanner, backend, and `/skillhub` proxy. The
acceptance fixture must contain lowercase `skill.md`; successful validation
must produce a review-bound import whose stored/downloaded package contains
canonical `SKILL.md`.

## Non-goals

- Changing the public SkillHub protocol to advertise `skill.md`.
- Modifying source repositories or opening upstream pull requests.
- Repairing invalid frontmatter or synthesizing missing metadata.
- Supporting alternate manifest names such as `README.md` or `AGENT.md`.
- Bypassing scanner or namespace-owner review.
