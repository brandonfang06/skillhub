# Skill Collections Remediation Task 7 Result

Date: 2026-07-28

Task: Align the Web install command with the CLI parser.

## Scope and boundary

This task changes one Web command coordinate and its unit/E2E expectations.
The CLI parser remains strict and unchanged. Registry flags, exact CLI and
collection versions, install scope, backend APIs, and single-Skill install
behavior remain unchanged.

Task 8 was not started while Task 7 was being verified.

## Result

The generated command now uses the canonical CLI coordinate:

```text
collection install @opensource/superpowers
```

The command still contains:

- the exact CLI package version;
- the Nexus `npx --registry` value;
- the SkillHub `--registry` value;
- the exact collection `--version`;
- `--scope user`.

`parseCollectionName` was not loosened. Unscoped or otherwise unsafe
coordinates still fail with usage exit code `5`.

## TDD evidence

After changing the expected command first, the focused unit test failed only
on the missing `@`:

```text
1 failed, 10 passed

Expected: collection install @opensource/superpowers
Received: collection install opensource/superpowers
```

After the one-line implementation:

```text
Collection command unit: 11 passed
Collection command Playwright E2E: 1 passed
CLI parser/help regression: 27 passed
TypeScript typecheck: passed
Focused ESLint: passed with zero warnings
CLI build: passed
```

The PATH-provided pnpm 11 attempted to rebuild dependencies created by the
project-pinned pnpm 10.33.0 and could not do so in the network-restricted
environment. Existing local project binaries were therefore used directly for
Vitest, Playwright, TypeScript, ESLint, and Vite. This did not change source or
test behavior.

## Copied-command contract

The built CLI accepted:

```powershell
node dist/index.js collection install @opensource/superpowers `
  --registry https://skills.example.com --scope user --json
```

It reached the registry boundary and returned:

```json
{
  "ok": false,
  "message": "registry unreachable",
  "exitCode": 3
}
```

The result proves parsing succeeded: it did not return
`collection must use @namespace/collection` or usage exit code `5`.

## Core-function assessment

- Only the copied collection coordinate changed.
- The CLI parser and its unsafe-coordinate rejection suite remain unchanged.
- The ordinary CLI command routing, registry requirement, and help contract
  remained green.
- The Web E2E retained its focusable copy action and both registry fragments.

No commit, stage, push, deployment, package publication, or external registry
mutation was performed.
