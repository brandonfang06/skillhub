# Skill Collections Remediation Task 6 Result

Date: 2026-07-28

Task: Make Web runtime configuration substitution complete.

## Scope and boundary

This task changes the Web image runtime entrypoint and its container build
normalization only. React behavior, backend API contracts, CLI parsing,
collection state, and deployment flag values remain unchanged.

Task 7 was not started while Task 6 was being verified.

## Result

- Every `${NAME}` referenced by `web/runtime-config.js.template` is now:
  - defaulted in `30-runtime-config.sh`;
  - exported to the `envsubst` process;
  - present in the explicit `envsubst` allowlist.
- The five collection/CLI variables default to:

  ```text
  SKILLHUB_WEB_COLLECTIONS_ENABLED=false
  SKILLHUB_WEB_GITLAB_IMPORT_ENABLED=false
  SKILLHUB_WEB_CLI_NPM_REGISTRY=
  SKILLHUB_WEB_CLI_PACKAGE=
  SKILLHUB_WEB_CLI_VERSION=
  ```

- The Dockerfile normalizes CRLF in the copied runtime entrypoint before
  making it executable. This keeps Windows-built images consistent with Linux
  CI checkouts.
- Existing auth, registration, and playground defaults are now actually
  visible to `envsubst`; previously shell parameter expansion created
  unexported variables, causing empty strings in the generated file.

## TDD evidence

The first completeness RED reproduced the exact planned missing set in both
defaults and substitution:

```text
1 failed, 11 passed

SKILLHUB_WEB_COLLECTIONS_ENABLED
SKILLHUB_WEB_GITLAB_IMPORT_ENABLED
SKILLHUB_WEB_CLI_NPM_REGISTRY
SKILLHUB_WEB_CLI_PACKAGE
SKILLHUB_WEB_CLI_VERSION
```

The first local image run then exposed two additional container-boundary
defects:

- a Windows CRLF shebang made the copied entrypoint non-executable;
- defaulted shell variables were not exported to `envsubst`.

Both defects received failing deployment guards before implementation. The
final focused result was:

```text
14 passed in 0.08s
```

## Container evidence

The remediation plan originally used a repository-root build context, but the
Web Dockerfile expects the Web directory as its context. The canonical GitHub
workflows also use `context: ./web`. The plan command was corrected to:

```powershell
cd web
docker build -t skillhub-web:collections-runtime-verify .
```

The image built successfully. A short-lived default container produced:

```text
collectionsEnabled: "false"
gitlabImportEnabled: "false"
cliNpmRegistry: ""
cliPackage: ""
cliVersion: ""
```

A second short-lived container with known values produced:

```text
collectionsEnabled: "true"
gitlabImportEnabled: "true"
cliNpmRegistry: "https://nexus.example/repository/npm-group/"
cliPackage: "@company/skillhub-cli"
cliVersion: "1.2.3"
```

Neither generated file contained a literal `${...}` placeholder. No
long-running container or exposed port was created.

## Core-function assessment

- Existing API, auth, playground, collection, and GitLab feature flags retain
  their documented defaults.
- Supplied environment values still override defaults exactly.
- The explicit allowlist prevents unrelated container secrets from entering
  the public runtime config.
- The line-ending normalization is limited to the copied entrypoint inside the
  image.

No commit, stage, push, deployment, feature enablement, or external service
operation was performed.
