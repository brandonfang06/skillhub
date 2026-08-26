# Ad Hoc Multi-Skill Install Design

## Status

Approved for implementation on 2026-08-25. The user completed the
`grill-with-docs` decision sequence, delegated the remaining implementation
details, and authorized development and verification without commit or push.

## 2026-08-26 Approved Compatibility And Compactness Amendment

This amendment supersedes conflicting Agent, Force, Search-tray, Install-page
ordering, and terminal-identity guidance below.

- The published npm artifact is the contract. `@astron-team/skillhub@latest`
  currently resolves to 0.1.9 and accepts one explicit Agent target per
  non-interactive scoped install. Although newer repository source can return
  multiple explicit targets, that behavior is not present in the published
  bundle and cannot be used by this Web flow.
- Skills remain multi-select, but the shared Agent target is required and
  single-select. The Web emits exactly one `--agent <id>` per generated command.
  It does not change, build, fork, or publish the CLI.
- Every generated command always includes `--force`. The page does not expose a
  Force checkbox. The command copy briefly explains that the latest published
  version replaces the existing target directory and local changes.
- In Skill cards, the selection checkbox is immediately left of the primary
  Skill heading rather than grouped with the namespace badge.
- While Search selection mode is active, selected count, clear, and **Continue
  to install** are rendered above the result grid in a compact sticky action
  row. The user must not need to reach the bottom of the results to continue.
- The Install page is vertically compact and ordered as: (1) shared Scope and
  single Agent target, (2) copyable commands, and (3) a selected-Skills
  disclosure. The disclosure is collapsed by default; when opened, its list is
  capped at the height of three Skill rows and scrolls internally.
- The separate Force control/card and **Verify the Terminal identity** card are
  removed. Existing CLI authentication and per-download attribution behavior
  remain unchanged; removing explanatory UI does not weaken the backend
  authentication boundary.
- Target controls use compact single-choice inputs. Copy remains disabled until
  one supported Agent is selected. Scope continues to default to `user`.

The amendment exists because the earlier design inferred repeatable explicit
Agent installation from repository source and CLI help text. A real published
0.1.9 invocation with `--agent codex --agent cursor` instead exits with
`multiple install targets detected`, while the same command with one Agent
succeeds against the real Python backend and PostgreSQL-backed catalog.

## Relationship To The Collection Design

This design revisits only the prior decision that an arbitrary cross-search
skill basket was out of scope. It does not authorize implementation of the
planned Collection aggregate or silently replace its governance model.

The existing Collection design remains a possible later milestone for curated,
versioned, reusable install sets. Its curator management pages, user discovery
pages, persistence, and publication workflow are deferred from the first
multi-skill-install milestone.

## Confirmed Decisions

### Phase-one product scope

The first milestone provides an ephemeral, user-composed multi-skill install
flow from the existing `/search` catalog:

- the user deliberately enters a multi-select mode;
- skill cards expose selection controls only while that mode is active;
- selections may accumulate while the user browses search results;
- a persistent selection tray shows the selected count and provides clear and
  **Continue to install** actions;
- a dedicated authenticated **Install Skills** page generates copyable install
  commands for the selected skills;
- the selection is not saved as a server resource and does not create a
  Collection; and
- Collection management and Collection discovery are deferred.

Normal skill-card navigation remains unchanged outside multi-select mode.
`/search` is the phase-one selection surface because it already provides
cross-platform-catalog discovery, namespace and label filters, starred skills,
sorting, and pagination.

The selection tray's **Continue to install** action navigates to the logical
route `/install`. The page title is **Install Skills**, not **Review**, because
SkillHub already uses review terminology for namespace governance. The install
page lists the selected skills, permits individual removal or clearing the
whole selection, collects the shared Scope and Agent targets, and previews the
copyable Terminal command block. Returning to search preserves the tab-scoped
selection. On narrow screens the same content uses a single-column page layout
rather than a modal or drawer.

The install page uses this reading and keyboard order:

1. back to search plus the selected count;
2. selected skills with individual remove and clear-all actions;
3. shared Scope and Agent targets;
4. the optional reinstall-latest control and warning;
5. CLI identity guidance using `skillhub whoami`; and
6. Terminal commands with copy-all and per-command copy actions.

An authenticated visit with no selected skills shows an empty state and a
single action back to `/search`; it does not invent a persisted list or query
the backend for one.

### Cross-shell command output

The install page renders one generic **Terminal** block rather than separate
PowerShell, Bash, or Zsh tabs. It reuses the existing single-skill SkillHub CLI
command contract and emits one independent `npx
@astron-team/skillhub@latest install ...` invocation per selected skill.

The block must not contain shell-specific wrappers, continuation syntax, or
failure checks. It is therefore directly pasteable into PowerShell, Bash, and
Zsh, subject to the same Node.js and `npx` prerequisites as the current
single-skill command.

Each line is an independent installation. A failed line may not stop later
lines, earlier successful installs are not rolled back, and the UI must state
that the user should inspect every command result. Shell-specific stop-on-error
behavior is deferred.

The command section provides one primary **Copy all commands** action and a
separate copy action for each skill command. The Web application does not
receive or infer Terminal execution outcomes and therefore does not mark
commands as installed, successful, or failed. Users retry a failed item by
copying its individual command. Re-running the full block without `--force`
leaves prior successful installs untouched and reports them as already
installed; re-running with the reinstall option enabled downloads and replaces
every destination again.

### Latest published skill resolution

The user selects a skill, not an exact skill version. Generated commands match
the current single-skill install behavior and omit the CLI `--version` option.
Each command therefore resolves the latest installable `PUBLISHED` version when
the user executes it.

The CLI package coordinate also remains aligned with the current single-skill
command as `@astron-team/skillhub@latest`. Exact skill-version pinning and a
version selector are deferred as advanced behavior.

### Authentication and per-skill install tracking

The multi-select mode is authenticated-only. An anonymous user who invokes its
entry action must be sent through the existing Web login flow and returned to
the search page afterward. Public catalog visibility does not make the
multi-select action anonymous.

Generating or copying a command is not an installation and must not create a
download event. Each generated `install` invocation must use the existing CLI
download path. On every successful artifact download, the backend records one
existing `local_skill_download_event` row with:

- the downloaded skill and resolved skill version;
- `source = 'cli'`;
- the authenticated CLI bearer principal as `user_id`; and
- the existing request, client, and user-agent metadata.

The copied block must not contain a browser-session credential, bearer token,
or token placeholder. The Terminal must already be authenticated through the
existing SkillHub CLI login. An unauthenticated CLI download fails instead of
creating an anonymous install event.

Tracking remains per actual skill download rather than per generated list. A
partially successful block therefore records only the skills whose downloads
reached the existing success path. The feature does not add a synthetic batch
download event or claim that copying the block proves installation.

The tracked installer is the authenticated CLI bearer principal, even when it
differs from the Web user who composed the ephemeral list. Web authentication
gates access to the multi-select UI; it does not delegate the browser session
to the Terminal or attest who later executes copied text. The install UI must
tell the user to verify the Terminal identity with the existing CLI `whoami`
command.

Enforcing equality between the Web principal and CLI principal is not part of
the MVP. The design must not introduce a browser-to-CLI handoff token, embed a
browser credential, add an expected-user argument to the CLI, or attribute an
installation to the Web user instead of the authenticated downloader.

### Required tracking verification

Implementation is not complete until an end-to-end test uses the real CLI
download route and real PostgreSQL-backed download-event writer to prove:

- two successful generated install invocations create two `source = 'cli'`
  events for the same authenticated CLI user and the two resolved skills;
- an unauthenticated invocation fails without an anonymous event;
- an invocation that fails before a successful artifact download does not
  create a success event; and
- a partial multi-command run leaves events only for downloads that actually
  reached the existing success path.

### Search results define the selectable set

Every skill returned by the existing authenticated `/search` catalog may be
selected. The MVP does not add an `installable` field, a second eligibility
query, a disabled selection state, or a new lifecycle concept.

The existing search projection continues to exclude lifecycle and governance
states that do not belong in ordinary catalog discovery. The existing CLI
download route remains the final authority for the CLI bearer principal's
access and for the resolved artifact's download readiness.

Exceptional failures such as legacy data drift, missing object-storage data,
registry unavailability, or a CLI principal lacking the Web principal's
namespace access are reported by the individual CLI invocation. They do not
change search-card selection behavior, and no download event is recorded until
the existing successful download path is reached.

### Browser-tab selection session

The ephemeral install selection is scoped to the current authenticated user
and browser tab. It survives search terms, namespace and label filters, sort
changes, pagination, navigation away from and back to `/search`, and a page
refresh in that same tab.

The frontend stores this UI state in tab-scoped `sessionStorage`; it does not
write a backend resource. The selection and multi-select mode are cleared when
the user explicitly clears them, logs out, changes Web identity, or closes the
tab. They are not synchronized across tabs, browsers, devices, or user
accounts.

The MVP permits at most 20 selected skills. The search page and selection tray
show the current count as `selected / 20`. Once the limit is reached, remaining
unselected controls are disabled with an explanatory message; already selected
skills remain removable. Selection continues to survive search, filter, sort,
pagination, navigation, and refresh within the same authenticated browser-tab
session.

### One target choice applied to every command

Before command generation, the install page requires the user to choose one
install scope (`user` or `project`) and at least one supported Agent profile.
The command renderer applies those choices to every independent install line by
emitting one `--scope` argument and one repeated `--agent` argument per selected
profile.

The install page defaults scope to `user` but does not preselect an Agent. Copying
remains disabled until the user explicitly selects at least one supported Agent.
The selected scope and Agents are retained only for the current browser tab's
session. When `project` is selected, the install page warns that the copied
commands must be run from the intended project directory.

This makes the copied block deterministic and prevents each independent `npx`
process from repeating the CLI's interactive scope and target prompts. Command
copying remains unavailable until both target requirements are satisfied.

The install page also provides an **Update/reinstall existing skills to the
latest version** option. It is off by default. Enabling it appends `--force` to
every generated install command and displays an explicit warning that the CLI
will replace each complete local skill directory, discard local changes, and
perform another real download even when the installed version is already the
latest. The browser does not attempt to inspect local installation state.

Selected skills are unique by canonical `namespace/skill-slug`. Repeated
appearances of the same skill across queries, filters, sorts, or pages reflect
the existing selected state instead of adding duplicates. The install page and
generated commands use a stable ascending namespace-then-skill-slug order.
There is no drag-to-reorder control or install-order dependency; removing and
reselecting a skill returns it to its deterministic sorted position.

The MVP does not expose a custom `--dir` target. It must not combine `--dir`
with `--scope` or `--agent`, infer a different target for each skill, or rely on
the CLI's local Agent-directory detection.

### Reuse the published OSS CLI unchanged

The organization does not build, fork, or publish a SkillHub CLI. The MVP must
align with the behavior already available from the public OSS
`@astron-team/skillhub@latest` npm package and must not require a local CLI
source change, package-version bump, `cli-v*` release, or organization-owned npm
publication.

This removes the proposed promotion of Generic to an explicit CLI profile. The
MVP must either omit Generic from deterministic Web-generated targets or leave
target selection to the released CLI's interactive prompt. It must not emit the
currently invalid `--agent generic`, generate extra downloads solely to reach a
Generic directory, or introduce shell-specific `--dir` commands.

The MVP chooses deterministic batch installation and therefore omits Generic
from the Web Agent multiselect. The UI explains that Generic is not supported
for batch installation. Existing single-skill CLI installation remains
unchanged and can continue to offer Generic through its interactive user-scope
target picker. If a future public OSS CLI release makes Generic explicitly
addressable, Web support can be reconsidered against that released contract.

The Agent multiselect exposes the 14 profiles that the released CLI accepts
explicitly, in CLI detector order: Claude Code, Codex, Cursor, GitHub Copilot,
Gemini CLI, OpenHands, Windsurf, OpenClaw, Kiro CLI, Roo, Trae, Trae CN,
OpenCode, and Kilo. The command renderer emits their stable CLI IDs, not their
localized display labels.

### Rollout, localization, accessibility, and telemetry

The authenticated MVP ships directly without a runtime feature flag. Rollback
is a frontend code rollback; no server resource or migration requires cleanup.
All new user-facing copy is present in English, Simplified Chinese, and
Traditional Chinese.

Selection controls use native accessible checkboxes and labels. Selection
mode, the 20-item limit, disabled reasons, selected count, clear/remove actions,
Scope, Agents, reinstall warning, and copy actions must be keyboard accessible.
The selected count uses a polite live region, and route transitions or clearing
the list move focus to a useful heading or action instead of losing focus.

The MVP adds no synthetic analytics event for entering selection mode,
selecting, generating, or copying commands. Existing successful CLI downloads
remain the only install/download evidence and retain their current PostgreSQL
event semantics.

## Repository Evidence

- The current `/search` page renders the shared `SkillCard` grid and already
  owns catalog filtering, sorting, and pagination.
- The shared `SkillCard` currently treats the whole card as navigation and has
  no selection control.
- The current single-skill install UI generates one `npx
  @astron-team/skillhub@latest install ...` command.
- The CLI accepts repeatable `--agent` arguments, and its interactive `Select
  install targets` prompt is a multiselect. For interactive user-scope installs
  it adds `generic` (`~/.agents/skills`) as a fallback candidate; the existing
  resolver test covers selecting Generic alongside a detected Agent target.
- Generic is not currently registered in the CLI's explicit `profileMap`.
  Consequently, the interactive picker can select Generic, but a generated
  non-interactive command using `--agent generic` is rejected as an unknown
  Agent. The Web command contract cannot represent Generic plus other selected
  Agents deterministically until this explicit-profile gap is resolved.
- This distinction was reproduced against the published npm `@latest` package
  (`@astron-team/skillhub` `0.1.9`): the user-scope interactive multiselect
  displayed both `codex` and `generic`, while the same package invoked with
  `--scope user --agent generic --json` returned `unknown agent: generic`.
- For an existing destination, the released CLI fails before registry download
  unless `--force` is present. With `--force`, it resolves and downloads the
  latest installable version, then transactionally replaces the complete local
  skill directory; it does not compare the installed version first. Local or
  stale files disappear after a successful replacement, and even the same
  version is downloaded again. The CLI `update` command updates the CLI package
  itself, not installed skills.
- Existing CLI download routes require an authenticated content identity and
  pass `source = 'cli'` plus that identity into the existing download-event
  writer after resolving the actual installable version.
- Collection pages, APIs, and frontend feature modules described by the older
  implementation plan are not present in the current checkout.

## Explicitly Deferred

- Collection curator management pages.
- Collection catalog, detail, version, publication, and discovery pages.
- Saving, naming, sharing, or publishing an ad hoc selection.
- A backend resource representing the ephemeral selection.
- Separate PowerShell, Bash, or Zsh command renderers and shell-specific
  stop-on-error behavior.
- Exact skill-version pinning and version selection in the install-list UI.
- An **Add to install list** action on skill detail pages.
- Enforcing equality between the Web list composer and the CLI installer.
- Custom install-directory input and `--dir` command generation.
- Web multi-Agent commands until a public npm release is verified to support
  multiple explicit install targets.
