# OSS Import GitLab Job Logging

Date: 2026-08-26

Status: Implemented and verified

## Goal

The central `publish_skillhub` job must be diagnosable from the GitLab job
console without downloading and manually inspecting the JSON report. The JSON
report remains the complete machine-readable audit artifact.

## Console contract

The Python importer emits UTC timestamped, single-line `key=value` events for:

- importer start and validated non-secret configuration;
- Dev GitLab branch clone start and derived revision;
- skill discovery and package count;
- namespace ensure start and outcome;
- validation start, outcome, version, and request ID for every skill;
- submission, idempotent skip, failure, version, and request ID for every skill;
- report path, final status, exit code, and aggregate counts.

Known failures include their stable failure class and safe error text in the
console before the process exits. Unexpected failures expose only the exception
type, matching the JSON report behavior.

## Security boundary

Console output must never include the SkillHub service token, GitLab job token,
authorization headers, multipart bodies, ZIP contents, SKILL.md contents, or
complete API payloads. Dynamic strings are JSON-quoted and length-bounded so
control characters cannot inject fake job-log lines.

Safe diagnostic fields include repository URLs that have already passed the
credential-free URL validators, branch/ref, namespace slug, source path,
derived commit SHA, outcome, version, pipeline/job/scan IDs, and SkillHub
request ID.

## Verification

- CLI tests assert that success and known failures are visible in captured job
  output while both token values remain absent.
- Workflow tests assert discovery, namespace, per-skill validation/submission,
  skip/failure, and final summary events.
- Existing JSON report, exit-code, idempotency, branch checkout, Python 3.8,
  and standard-library-only contracts remain unchanged.
- The full Docker smoke must show these events from the stock Python 3.8 job
  container while exercising PostgreSQL, Redis, MinIO, scanner, backend, root
  proxy, and `/skillhub` proxy.
