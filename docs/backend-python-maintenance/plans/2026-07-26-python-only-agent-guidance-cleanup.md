# Python-Only Agent Guidance Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop active repository skills from directing coding agents toward the
retired Java backend while preserving migration history.

**Architecture:** Keep existing skill names and routing stable. Rewrite only the
six stale `.agents/skills/` documents around the current FastAPI, pytest, `uv`,
and Python migration workflow; do not touch runtime code or historical docs.

**Tech Stack:** Markdown agent skills, FastAPI, pytest, `uv`, Make.

---

## Scope

Modify only:

- `.agents/skills/api-and-namespace-design/SKILL.md`
- `.agents/skills/backend-module-structure/SKILL.md`
- `.agents/skills/code-conventions/SKILL.md`
- `.agents/skills/dev-workflow/SKILL.md`
- `.agents/skills/skill-lifecycle/SKILL.md`
- `.agents/skills/testing-and-ci/SKILL.md`

Do not modify README files, deployment manifests, runtime code,
`docs/backend-python-migration/`, or other historical Java evidence.

### Task 1: Replace stale backend architecture and coding guidance

**Files:**
- Modify: `.agents/skills/backend-module-structure/SKILL.md`
- Modify: `.agents/skills/code-conventions/SKILL.md`

- [x] **Step 1: Confirm the stale guidance is present**

Run:

```powershell
git grep -n -I -i -E "mvnw|maven|spring boot|spring data|src/test/java|server/pom.xml|server/skillhub|com\.iflytek" -- .agents/skills
```

Expected: matches in both target files.

- [x] **Step 2: Rewrite the two skills**

Document these current boundaries:

- backend source: `server-python/app/`;
- routes: `server-python/app/api/`;
- orchestration and domain workflows: focused modules below `app/`;
- SQL: repository/query/helper modules, never route handlers;
- migrations: `server-python/app/db/migration/`;
- tests: `server-python/tests/`;
- commands: `uv run pytest tests -q` and
  `uv run python -m app.migrations upgrade`.

Keep the existing frontend guidance in `code-conventions`.

### Task 2: Replace stale workflow and test commands

**Files:**
- Modify: `.agents/skills/dev-workflow/SKILL.md`
- Modify: `.agents/skills/testing-and-ci/SKILL.md`

- [x] **Step 1: Rewrite prerequisites and commands**

Use Python 3.12, `uv`, Node.js/pnpm, Docker Compose, and the existing Make
targets. Describe backend tests as pytest tests under `server-python/tests/`.
Replace Flyway reset wording with the Python migration runner.

- [x] **Step 2: Correct smoke and troubleshooting guidance**

Use:

- health: `/api/v1/health`;
- metrics: `/api/v1/metrics/prometheus`;
- scanner health: `http://localhost:8000/health`;
- backend troubleshooting: `uv sync --frozen`, Python logs, and
  `server-python/Dockerfile`.

### Task 3: Correct API reference endpoints

**Files:**
- Modify: `.agents/skills/api-and-namespace-design/SKILL.md`

- [x] **Step 1: Replace retired endpoint and Java package guidance**

Replace Actuator endpoints with the FastAPI health and metrics endpoints.
Describe route handlers as transport-only modules under
`server-python/app/api/` and generated contracts under
`web/src/api/generated/`.

### Task 4: Verify the active skill boundary

**Files:**
- Modify: `.agents/skills/skill-lifecycle/SKILL.md`

- [x] **Step 1: Replace retired lifecycle implementation references**

Keep the product state model, but replace Java class, service, method, and
camelCase field references with the current Python lifecycle, publish, review,
and read-model modules. Correct the `latest_version_id` rules for private
uploads versus public resolution.

### Task 5: Verify the active skill boundary

**Files:**
- Verify: `.agents/skills/**/*.md`

- [x] **Step 1: Run the focused stale-command scan**

Run:

```powershell
git grep -n -I -i -E "mvnw|maven|spring boot|spring data|actuator|flyway|jdk|java[[:space:]]+21|\.java|src/test/java|server/pom.xml|server/skillhub|com\.iflytek|SkillPublishService|SkillGovernanceService|latestVersionId|publishedAt|createdAt|setHidden" -- .agents/skills
```

Expected: no matches.

- [x] **Step 2: Run existing cutover tests**

Run:

```powershell
cd server-python
uv run pytest tests/test_final_cutover_baseline.py tests/test_deployment_cutover.py tests/test_python_runtime_cutover.py -q
```

Expected: all tests pass.

- [x] **Step 3: Run repository checks**

Run:

```powershell
cd ..
git diff --check
git status --short
```

Expected: only this plan and the six intended skill files are modified.
