# Upstream v0.2.14 and CLI v0.1.9 Follow-Up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Follow the applicable behavior and documentation from upstream SkillHub `v0.2.14` and publish the matching local CLI `0.1.9` metadata without changing the Python backend contract.

**Architecture:** Port the upstream TypeScript CLI target-resolution and install-preflight behavior directly, then pin the scanner's validated LiteLLM dependency in the existing Python scanner image. Adopt relevant bilingual operator and integration documentation while preserving the full-Python backend, local scanner backport, and existing deployment contract.

**Tech Stack:** TypeScript, Bun, Python 3.11 Alpine scanner image, Docker, Markdown, Kubernetes/Kustomize.

---

## Upstream Release Evidence

Official GitHub data checked on 2026-07-24:

- App release: `v0.2.14`
- Release URL: <https://github.com/iflytek/skillhub/releases/tag/v0.2.14>
- Published: `2026-07-22T09:33:28Z`
- Tag commit: `982258d032a22ffa0403db445c2736b128ec06b1`
- Compared range: `v0.2.13..v0.2.14`
- CLI release: `cli-v0.1.9` (`CLI 0.1.9`)
- Release URL: <https://github.com/iflytek/skillhub/releases/tag/cli-v0.1.9>
- Published: `2026-07-22T09:47:12Z`
- Tag commit: `ac46ad53913e413e451710a3563590b62d183927`
- CLI-only delta after the app tag: `v0.2.14..cli-v0.1.9`

Evidence commands:

```powershell
git fetch upstream --tags --prune
git log --oneline v0.2.13..v0.2.14
git diff --name-status v0.2.13..v0.2.14
git diff --name-status v0.2.14..cli-v0.1.9
```

The app tag changes only CLI behavior/tests/docs, scanner image dependency
installation, and documentation. The CLI release adds only:

```text
M cli/package.json
M cli/src/generated/pkg-info.ts
```

## Local Baseline Evidence

- App `v0.2.13` is completed in
  `docs/backend-python-maintenance/results/2026-07-04-v0.2.13-follow-up.md`.
- CLI `cli-v0.1.8` is completed in
  `docs/backend-python-maintenance/results/2026-07-01-cli-v0.1.8-follow-up.md`.
- `cli/package.json` is currently `0.1.8`.
- The local CLI already supports project fallback installation to
  `.agents/skills`, but it does not always offer `~/.agents/skills` alongside
  detected user-level agent directories.
- The local CLI deduplicates target paths textually, not by filesystem
  canonical path, and it discovers conflicting destinations only while
  installation is already in progress.
- `scanner/Dockerfile` already pins `cisco-ai-skill-scanner==1.0.2` and applies
  the local base-URL backport, but does not pin the validated transitive
  `litellm==1.90.2`.
- K8s base/plain manifests already expose the scanner LLM API key, base URL,
  and model. Upstream `v0.2.14` does not change their contract.
- The backend remains FastAPI/Python-only. No upstream backend, API, schema, or
  migration change exists in this release range.

## Gap Summary

| Surface | Classification | Required follow-up |
| --- | --- | --- |
| Backend Python | Already covered / no delta | Run focused regression only; do not add Java-derived code. |
| Schema/migration | No delta | No migration or model change. |
| Frontend/API contract | No delta | No generated API or frontend runtime change. |
| CLI | Port now | Add generic user-level target, canonical-path dedupe, all-target preflight, tests, docs, and `0.1.9` metadata. |
| Scanner | Port now | Pin `litellm==1.90.2` while retaining scanner `1.0.2` and the local base-URL backport. |
| Deployment/K8s | Verify only | Render current manifests and confirm no scanner env/image contract change is needed. |
| Documentation | Port selectively | Add Hermes Agent guides and update CLI/FAQ references relevant to this fork; avoid Java/Spring deployment advice. |
| Verification | Required | Run CLI, scanner image, Python regression, docs, K8s, Compose, and whitespace gates. |

## Files Expected To Change

- Modify: `README.md`
- Modify: `README_zh.md`
- Modify: `cli/src/platform/paths.ts`
- Modify: `cli/src/agents/resolver.ts`
- Modify: `cli/src/services/install-service.ts`
- Modify: `cli/test/unit/agents/resolver.test.ts`
- Modify: `cli/test/unit/agents/resolver-interactive.test.ts`
- Modify: `cli/test/unit/services/install-service.test.ts`
- Modify: `cli/package.json`
- Regenerate: `cli/src/generated/pkg-info.ts`
- Modify: `cli/README.md`
- Modify: `docs/skillhub/guide/cli.md`
- Modify: `docs/skillhub/en/guide/cli.md`
- Create: `docs/hermes-integration.md`
- Create: `docs/hermes-integration-en.md`
- Modify selectively: `docs/skillhub/faq.md`
- Modify selectively: `docs/skillhub/en/faq.md`
- Create: `server-python/tests/test_scanner_image_contract.py`
- Modify: `scanner/Dockerfile`
- Create after execution:
  `docs/backend-python-maintenance/results/2026-07-24-v0.2.14-cli-v0.1.9-follow-up.md`

Do not manually edit `cli/src/generated/pkg-info.ts`; regenerate it from
`cli/package.json`.

### Task 1: Port CLI generic user target and canonical deduplication

- [x] **Step 1: Add failing resolver and path tests**

Extend `cli/test/unit/agents/resolver.test.ts` and
`cli/test/unit/agents/resolver-interactive.test.ts` to prove:

- interactive `--scope user` includes `~/.agents/skills` even when an
  agent-specific user directory is detected;
- non-interactive resolution retains its existing ambiguity behavior;
- symlinked or otherwise equivalent existing roots are deduplicated by
  canonical path;
- explicit/custom behavior and project fallback remain unchanged.

- [x] **Step 2: Verify the focused tests fail**

```powershell
cd cli
bun test test/unit/agents/resolver.test.ts test/unit/agents/resolver-interactive.test.ts
```

Expected: new generic-user and canonical-deduplication assertions fail against
the `0.1.8` implementation.

- [x] **Step 3: Add canonical path resolution**

In `cli/src/platform/paths.ts`, add an async helper that returns
`fs.promises.realpath(path)` for an existing path and returns the original path
when canonicalization is unavailable.

In `cli/src/agents/resolver.ts`:

- make root deduplication asynchronous;
- deduplicate candidates by the canonical existing root;
- after initial user-scope detection, append the generic
  `${scopedHome}/.agents/skills` candidate only for interactive, non-JSON,
  no-explicit-agent selection;
- deduplicate again so an alias does not produce a duplicate choice.

- [x] **Step 4: Run focused resolver tests**

```powershell
bun test test/unit/agents/resolver.test.ts test/unit/agents/resolver-interactive.test.ts
```

Expected: all focused tests pass.

### Task 2: Preflight all CLI install destinations before download or writes

- [x] **Step 1: Add failing install-service tests**

Extend `cli/test/unit/services/install-service.test.ts` to prove:

- two targets resolving to the same canonical skill directory fail with usage
  error before network download or filesystem mutation;
- any existing destination without `--force` fails before the first target is
  installed;
- distinct targets still install successfully;
- `--force` behavior and rollback remain unchanged.

- [x] **Step 2: Verify the focused tests fail**

```powershell
cd cli
bun test test/unit/services/install-service.test.ts
```

Expected: duplicate-canonical-target and all-target-preflight assertions fail.

- [x] **Step 3: Implement minimal preflight**

In `cli/src/services/install-service.ts`, prepare every target before creating
the API client:

- canonicalize each root;
- join it with the requested slug;
- reject duplicate canonical destinations with `EXIT.usage`;
- reject any existing destination without `--force` with `EXIT.filesystem`;
- return the original target and original destination path for the existing
  installation/rollback loop.

Keep the later race check before the final rename. Do not weaken atomic
installation or rollback behavior.

- [x] **Step 4: Run focused and full CLI tests**

```powershell
bun test test/unit/services/install-service.test.ts
bun run typecheck
bun run lint
bun run test
bun run build
```

Expected: typecheck, lint, and build pass; the full CLI test suite has zero
failures.

### Task 3: Pin the scanner dependency reproducibly

- [x] **Step 1: Add a static regression assertion**

Create `server-python/tests/test_scanner_image_contract.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_scanner_image_pins_validated_dependency_contract() -> None:
    dockerfile = (ROOT / "scanner" / "Dockerfile").read_text(encoding="utf-8")

    assert '"cisco-ai-skill-scanner==${SKILL_SCANNER_VERSION}"' in dockerfile
    assert '"litellm==1.90.2"' in dockerfile
    assert "apply_1_0_2_llm_base_url_backport.py" in dockerfile
```

- [x] **Step 2: Verify the new assertion fails**

```powershell
cd server-python
uv run pytest tests/test_scanner_image_contract.py -q
```

Expected: fail because `litellm==1.90.2` is absent from `scanner/Dockerfile`.

- [x] **Step 3: Update `scanner/Dockerfile`**

Install the pinned scanner and LiteLLM versions in the same `pip install`
layer. Preserve:

- Alpine `python:3.11`;
- `SKILL_SCANNER_VERSION=1.0.2`;
- the local LLM base-URL backport;
- build-dependency cleanup;
- the non-root runtime user and health check.

- [x] **Step 4: Verify the scanner**

```powershell
docker build -t skillhub-scanner:v0.2.14-verify -f scanner/Dockerfile scanner
docker run --rm skillhub-scanner:v0.2.14-verify python -c "import importlib.metadata as m; assert m.version('litellm') == '1.90.2'; assert m.version('cisco-ai-skill-scanner') == '1.0.2'"
& 'C:\Program Files\Git\bin\bash.exe' scripts/tests/scanner-llm-base-url-test.sh
```

Expected: image build, dependency assertions, and scanner base-URL smoke pass.
If Docker Desktop is unavailable, record that environmental blocker in the
result document; do not treat static checks as an image-build pass.

### Task 4: Adopt relevant CLI and integration documentation

- [x] **Step 1: Update CLI target documentation**

Update `cli/README.md`, `docs/skillhub/guide/cli.md`, and
`docs/skillhub/en/guide/cli.md` to describe the always-available user-level
`~/.agents/skills` target, interactive multi-target selection, and canonical
destination conflict rejection.

- [x] **Step 2: Add bilingual Hermes Agent guides**

Create `docs/hermes-integration.md` and `docs/hermes-integration-en.md` from
the upstream `v0.2.14` guides. Adapt commands only where the local CLI or
Python-only deployment differs. Preserve install, discovery, forced update,
conflict handling, and removal coverage.

Update `README.md` and `README_zh.md` with the matching Hermes integration
entry and links to the new guides.

- [x] **Step 3: Port FAQ entries selectively**

Review the `v0.2.13..v0.2.14` FAQ diff and port entries that apply to:

- CLI publishing and package validation;
- generic agent installation;
- database compatibility at the product-contract level;
- scanner and deployment troubleshooting valid for the Python runtime.

Reject or rewrite instructions that require Java, Maven, Spring Boot,
Actuator, or the removed `server/` tree.

- [x] **Step 4: Check links and forbidden runtime drift**

```powershell
rg -n "server/|mvnw|Maven|Spring Boot|actuator" README.md README_zh.md docs/hermes-integration.md docs/hermes-integration-en.md docs/skillhub/faq.md docs/skillhub/en/faq.md docs/skillhub/guide/cli.md docs/skillhub/en/guide/cli.md cli/README.md
```

Expected: no newly introduced instruction depends on the removed Java runtime.
Intentional historical or explicit non-goal wording must be reviewed manually.

### Task 5: Bump CLI metadata and record the result

- [x] **Step 1: Update the source version**

Change `cli/package.json` from `0.1.8` to `0.1.9`.

- [x] **Step 2: Regenerate package information**

```powershell
cd cli
bun run scripts/generate-pkg-info.ts
bun test test/unit/scripts/generate-pkg-info.test.ts
```

Expected: generated metadata reports `0.1.9` and its focused test passes.

- [x] **Step 3: Create the maintenance result**

Create
`docs/backend-python-maintenance/results/2026-07-24-v0.2.14-cli-v0.1.9-follow-up.md`
with:

- both upstream release URLs, publication timestamps, tag commits, and diff
  ranges;
- the implemented CLI, scanner, and documentation changes;
- explicit no-op conclusions for backend Python, schema/migration,
  frontend/API contract, and K8s contract;
- exact verification commands and results;
- any Docker or environment blockers.

### Task 6: Run final release-follow-up verification

- [x] **Step 1: Run backend regression**

```powershell
cd server-python
uv run pytest tests -q
```

Expected: full Python backend suite passes with no new release-specific
backend change.

- [x] **Step 2: Run frontend static gates**

```powershell
cd ..\web
corepack pnpm run typecheck
corepack pnpm run lint
corepack pnpm exec vitest run
```

Expected: typecheck, lint, and unit tests pass.

- [x] **Step 3: Render deployment configuration**

```powershell
cd ..
kubectl kustomize deploy\k8s\base
kubectl kustomize deploy\k8s\overlays\external
docker compose --env-file .env.release.example -f compose.release.yml config
```

Expected: all configurations render without changing the existing
Python-backend/scanner deployment contract.

- [x] **Step 4: Run final repository checks**

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only the intended follow-up files and any
pre-existing unrelated files are present.

## Explicit Non-Goals

- Do not reintroduce Java, Maven, Spring Boot, the removed `server/` tree, or a
  hybrid runtime.
- Do not change FastAPI routes, authorization, OpenAPI contracts, database
  schema, migrations, frontend runtime behavior, or generated frontend API
  types; upstream `v0.2.14` contains no such delta.
- Do not replace the local scanner `1.0.2` base-URL backport unless a separately
  validated scanner release makes it unnecessary.
- Do not change K8s secrets, scanner environment names, image topology, or
  external-service ergonomics without evidence of a changed upstream contract.
- Do not copy Java/Spring-specific FAQ or deployment instructions into the
  Python-only documentation.
- Do not commit, push, publish the CLI package, or open a PR without explicit
  authorization.

## Paste-Ready Prompt For Another Session

```text
Execute the plan at:
C:\Users\USER\projects\skillhub\docs\backend-python-maintenance\plans\2026-07-24-follow-upstream-v0.2.14-cli-v0.1.9.md

Follow C:\Users\USER\projects\skillhub\AGENTS.md and any applicable CLAUDE.md
and skill instructions. Use TDD and verify each task before continuing.

The repository is a full-Python backend project. Do not reintroduce Java,
Maven, Spring Boot, the removed server/ tree, or a hybrid runtime. Port only
the applicable upstream v0.2.14 and cli-v0.1.9 CLI, scanner, and documentation
changes. Preserve the existing scanner 1.0.2 LLM base-URL backport and current
K8s/external-service deployment ergonomics.

Before editing, inspect git status and preserve all unrelated worktree changes.
Do not manually edit generated files. Record exact commands and results in:
C:\Users\USER\projects\skillhub\docs\backend-python-maintenance\results\2026-07-24-v0.2.14-cli-v0.1.9-follow-up.md

Do not commit, push, publish, or open a PR unless I explicitly request it.
```
