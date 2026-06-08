# Review Parity Fixes: Download and Publish Foundations

## Scope

Accepted reviewer feedback that directly affected Java/Python behavior parity:

- Download read path must not hardcode `s.visibility = 'PUBLIC'` in Python-owned download
  resolution queries.
- Publish package validation must match Java `SkillPackagePolicy.ALLOWED_EXTENSIONS`.
- Publish dry-run slug generation must preserve Java `SlugValidator` symbol characters
  (`\p{So}`), such as `♥` and emoji.

No `server/` files were modified. Java files were read-only references.

## Route Ownership

No new route ownership was added.

- Existing Python-owned download routes remain Python-owned through the current Vite proxy split.
- Publish upload routes remain Java-owned/unowned by Python. The publish smoke checks confirmed
  proxy responses still match Java for the publish route set.

## Changes

- Removed public-only visibility filtering from the Python download version/latest/tag lookup path
  so private and namespace-only skills can proceed to the existing authorization checks.
- Aligned Python package allowed extensions with Java, including Office files, XML schema files,
  config files, and source/script extensions.
- Removed Python-only package extensions that Java rejects: `.markdown`, `.tsx`, `.jsx`, `.scss`.
- Added dotfile extension handling for `.env`.
- Replaced Python `\w`-based slugification with Unicode category checks matching Java
  `\p{L}\p{N}\p{So}`.

## Tests

Passed:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
Push-Location server-python
try {
  uv run pytest tests/test_skill_download.py tests/test_publish_package.py tests/test_publish_dry_run.py -q
} finally {
  Pop-Location
}
```

Result: `89 passed, 1 warning`.

Passed:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-download-smoke
```

Result: download Java/Python/proxy contract comparison passed; Playwright `6 passed`.

Passed:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-dry-run-smoke
```

Result: dry-run unit tests `19 passed`; route ownership smoke passed; Playwright `6 passed`.

Passed:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-foundation-smoke
```

Result: package foundation tests `49 passed`; route ownership smoke passed; Playwright `6 passed`.

Additional checks:

- `git diff --name-only -- server` returned empty output.
- `git diff --check` returned no whitespace errors.
- Port check showed only `TIME_WAIT` entries for checked local ports, no listener left behind.

## Deferred Feedback

- Data access strategy documentation feedback: approved by reviewer; no code change needed.
- Publish upload plan feedback: approved by reviewer; no code change needed.

## Risks and Follow-Up

- Download authorization still relies on the current Python authorization helpers after the lookup
  stage. Future download changes must compare private, namespace-only, anonymous, owner, namespace
  member, and admin cases against Java.
- Publish upload is still not route-owned by Python. Continue to keep publish route ownership
  checks in every publish-related milestone until the takeover plan explicitly changes ownership.
