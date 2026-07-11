# Global Destructive Operation Guard Design

**Status:** Approved for a limited trial
**Date:** 2026-07-11
**Scope:** User-level Codex configuration on this Windows host

## Goal

Reduce the chance that Codex with full host access accidentally performs a
high-blast-radius deletion, while keeping ordinary development work fast. The
guard should focus on catastrophic, broad, ambiguous, or externally
irreversible operations. It should not create a checkpoint for every routine
file deletion.

The current user-level Codex configuration uses `approval_policy = "never"`
and `sandbox_mode = "danger-full-access"`. The guard is therefore a
defense-in-depth measure for accidental behavior, not an operating-system
security boundary.

## Non-goals

- Prevent deletion performed manually or by programs outside Codex.
- Protect against a deliberately malicious process running with the same user
  privileges.
- Guarantee interception of every Codex tool path. Codex documents
  `PreToolUse` as a guardrail with incomplete interception of `unified_exec`.
- Back up every file that Codex deletes.
- Automatically snapshot arbitrary databases, containers, or cloud services.
- Run `git gc`, rewrite normal Git history, or modify existing branches,
  tags, stashes, or commits.

## Design Summary

Use a user-level Codex `PreToolUse` hook plus a narrow global `AGENTS.md`
instruction:

1. A cheap lexical fast path immediately allows commands and edits that do not
   look destructive.
2. Known generated directories and small, explicit, non-recursive deletions
   are allowed without a checkpoint.
3. High-risk local filesystem or Git operations receive a targeted,
   capacity-bounded checkpoint before they run.
4. Catastrophic, ambiguous, over-capacity, or externally irreversible
   operations are denied until the user gives an exact, one-time approval.
5. Any failure after an operation has been recognized as destructive denies
   the operation rather than allowing an unprotected deletion.

## Installation Surfaces

The implementation will use user-level locations so the policy applies to all
Codex projects:

- `~/.codex/hooks.json` for the hook registration.
- `~/.codex/hooks/destructive-guard/` for the implementation and tests.
- `~/.codex/destructive-guard/` for checkpoints, manifests, pending approvals,
  and the storage index.
- `~/.codex/AGENTS.md` for a short instruction that large, ambiguous, or
  irreversible deletions must use the guard. Existing content must be
  preserved; the installer adds and removes only a clearly delimited section.
- `~/.codex/config.toml` with `[features].hooks = true` set explicitly while
  preserving all unrelated configuration.

The hook matchers cover shell commands, `apply_patch` file deletion, and MCP
tool names that explicitly contain destructive verbs such as `delete`,
`remove`, `drop`, or `truncate`. The implementation does not claim that name
matching can identify every destructive MCP operation.

## Fast Path and Classification

The hook reads the event JSON from standard input. For shell calls it first
performs a lexical check for destructive command families, including common
PowerShell, cmd, POSIX, Git, SQL, Docker, Kubernetes, and cloud CLI verbs. For
`apply_patch`, it checks for file-deletion directives. For MCP calls, it checks
the canonical tool name before inspecting arguments.

If no destructive signature is present, the hook exits successfully without
running Git, enumerating paths, reading file contents, or writing state. This
is the normal path for most tool calls.

Once a destructive signature is found, the guard classifies it using the
following precedence. A higher-risk rule always wins over a lower-risk rule.

### Tier 0: generated-content deletion

Allow without a checkpoint when every resolved target is wholly inside an
explicit generated-content directory, such as:

- `node_modules`
- `.venv`
- `dist`
- `build`
- `coverage`
- `__pycache__`
- `.pytest_cache`
- recognized operating-system temporary directories

Protected-root rules still override this allowlist. A mixed command that also
targets any non-generated path is not Tier 0.

### Tier 1: routine deletion

Allow without a checkpoint only when all of these conditions hold:

- Every target is an explicit, fully resolved local path.
- The operation is non-recursive and contains no wildcard, glob, command
  substitution, or unresolved variable expansion.
- Fewer than 10 files are targeted.
- The combined target size is less than 50 MiB.
- No protected root or external resource is involved.

An empty directory may be removed non-recursively under the same rules.

### Tier 2: high-risk local operation

Create a targeted checkpoint before allowing the operation when it is local
and recoverable but includes any of the following:

- Recursive deletion of a non-generated directory.
- Wildcards or globs whose targets can be resolved safely.
- At least 10 targets or at least 50 MiB of affected data.
- Broad Git operations such as `git clean`, `git reset --hard`, or broad
  `git checkout`/`git restore` forms that discard work.
- A multi-file deletion through `apply_patch` that crosses the routine
  thresholds.

If the targets cannot be resolved without executing shell expansion, the
operation is Tier 3 instead.

### Tier 3: catastrophic or externally irreversible operation

Deny and require exact one-time approval for:

- Recursive deletion of a drive root, user-home root, Desktop root, Documents
  root, Downloads root, repository root, or checkpoint-storage root.
- A path that resolves to or escapes through an unsafe junction, symlink, or
  Windows reparse point.
- Dynamic or ambiguous targets the parser cannot resolve conservatively.
- A local checkpoint whose compressed content would exceed 250 MiB.
- Database `DROP`/`TRUNCATE`, container volume deletion, broad prune commands,
  namespace deletion, and destructive cloud-resource operations.
- Any detected destructive operation for which classification, checkpointing,
  hashing, manifest writing, or capacity validation fails.

## Checkpoint Format

Checkpoints live in the central user-level guard directory so their actual
disk use can be measured and capped without creating unreachable Git objects.
Each checkpoint contains a versioned JSON manifest and only the data needed to
restore the threatened state.

For a Git worktree, the manifest records the repository root, branch or
detached state, base commit, command hash, timestamp, and affected paths.
Clean tracked files are recoverable from the base commit and are not copied.
Staged and unstaged changes are stored as binary-capable patches. Affected
untracked files are compressed into the checkpoint. Broad Git operations save
all staged, unstaged, and affected untracked state that the operation could
discard.

For local paths outside Git, the checkpoint contains the exact resolved target
contents plus original paths, file metadata needed for restoration, and
content hashes. Junctions and reparse points are not followed implicitly.

The operation is allowed only after the checkpoint has been written, reopened,
validated, and indexed successfully.

## Capacity and Retention

The checkpoint store uses these initial trial limits:

- Maximum compressed size per checkpoint: 250 MiB.
- Maximum actual checkpoint-store size: 1 GiB globally.
- Maximum retained checkpoints per repository or non-repository root: 10.
- Maximum age: 14 days.

Before creating a checkpoint, the guard may remove only its own expired
checkpoints or the oldest checkpoint above the per-root count. It never removes
ordinary project files or Git refs. If the new checkpoint still cannot fit,
the destructive operation is denied. The guard does not run automatic Git
garbage collection.

## One-time Approval

When Tier 3 is denied, the guard creates a pending request containing a random
nonce, normalized command hash, working directory, classified reason, and a
10-minute expiry. It reports the nonce and a human-readable summary to Codex.

The user must explicitly approve that nonce in a new message using exactly
`批准 <nonce>` or `approve <nonce>`. Only after receiving one of those exact
forms may Codex call the guard helper to authorize the pending request. The
helper verifies that the nonce is pending and then binds the authorization to
the original command hash and working directory. It expires after 10 minutes
and is consumed once. The global `AGENTS.md` rule forbids Codex from invoking
the authorization helper without the exact user message.

Because Codex and the guard run with the same operating-system account, this
nonce workflow protects against accidental execution and accidental retries;
it is not a security boundary against a malicious agent with full access.

## Failure Behavior

- A non-destructive fast-path result performs no backup work.
- Tier 0 and Tier 1 operations are allowed without persistent guard state.
- Tier 2 is fail-closed after detection: any parse, archive, hash, validation,
  or indexing error denies the operation.
- Tier 3 is always denied unless a matching one-time authorization is consumed.
- The implementation catches internal errors after destructive detection and
  emits the documented `PreToolUse` deny response or exit code `2`.
- If Codex fails to launch the hook at all, the hook cannot enforce policy. The
  global instruction is the secondary behavioral guard, and the limitation is
  documented rather than hidden.

## Performance Requirements

- The fast path must not call Git, enumerate directories, inspect file sizes,
  or write to disk.
- The fast-path hook process should complete within 100 ms at the 95th
  percentile on this host during the trial.
- Filesystem enumeration occurs only after a destructive signature is found.
- Checkpoint time is proportional to the threatened dirty or non-Git data, not
  the entire repository size.
- No logging is written for ordinary non-destructive tool calls.

## Testing and Verification

Implementation follows TDD. Tests operate only in temporary directories and
temporary Git repositories.

Required coverage:

- Command-parser fixtures for PowerShell, cmd, POSIX shell, Git, SQL, Docker,
  Kubernetes, and representative cloud CLI operations.
- Fast-path tests proving ordinary commands create no files and invoke no Git
  or directory enumeration.
- Tier 0 and Tier 1 tests proving routine development deletion does not create
  checkpoints.
- Protected-root, wildcard, recursive, reparse-point, size, and target-count
  classification tests.
- Git checkpoint-and-restore tests for clean tracked, staged, unstaged,
  untracked, ignored, and binary files.
- Non-Git checkpoint-and-restore tests with original-path and hash validation.
- Capacity, retention, corrupt-manifest, partial-write, and disk-full tests.
- One-time approval tests for wrong nonce, changed command, changed working
  directory, expiry, replay, and successful single use.
- Hook-protocol tests using realistic `PreToolUse` JSON for shell,
  `apply_patch`, and MCP tool calls.
- A manual smoke test in a disposable directory after reviewing and trusting
  the hook through Codex's hook-management UI.

Verification must demonstrate both sides of the policy: a normal development
flow remains checkpoint-free, and a simulated high-blast-radius deletion is
blocked or recoverably checkpointed before any target is removed.

## Trial, Observability, and Adjustment

The trial records metadata only for Tier 2/Tier 3 events: timestamp, risk tier,
reason code, normalized target count and size, checkpoint size, and outcome.
It does not record file contents or full commands in the event log. Checkpoint
manifests necessarily contain restoration paths and command hashes.

After the trial, thresholds and allowlists may be adjusted if the guard is too
slow or noisy. Routine deletions must not be promoted merely to collect more
telemetry.

## Rollback

Rollback removes only the guard's hook entry and delimited global instruction,
then sets or leaves `[features].hooks` according to the user's remaining hook
needs. Existing checkpoints remain recoverable until the user explicitly
removes them or the guard's normal retention cleanup runs. The rollback does
not alter project repositories.

## Accepted Limitation

This design materially reduces accidental high-blast-radius deletions from
recognized Codex tool calls. It cannot provide the same guarantee as a sandbox,
Windows ACL, File History, or a system snapshot while Codex retains
unrestricted full-host access.
