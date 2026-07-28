# Versioned Collections and GitLab Import

A SkillHub collection is a governed snapshot of multiple exact Skill versions.
It removes the need to install every Skill in an open-source toolkit
individually while retaining each Skill's scanner, review, search, download,
and version lifecycle.

## Domain Model

A collection coordinate is:

```text
@<namespace>/<collection>
```

Every published collection version contains exact `PUBLISHED` Skill versions
from the same namespace:

```text
@opensource/superpowers@1.1.0
  -> brainstorming@2.1.0
  -> test-driven-development@3.0.1
  -> systematic-debugging@1.4.2
```

Skill and collection versions are independent. Publishing
`brainstorming@2.2.0` does not change an existing collection. A curator must
edit a draft, accept the update, and publish a new immutable collection
version. Older versions remain resolvable and auditable.

## Who Maintains a Collection

The namespace owns the collection; the MVP does not add a single
`collection_owner`:

- team namespace `OWNER` and `ADMIN` users can create, edit, publish, archive,
  and restore collections;
- ordinary `MEMBER` users can view and install accessible published
  collections but cannot mutate them;
- `SKILL_ADMIN` and `SUPER_ADMIN` curate the global namespace.

SkillHub records creators, updaters, publishers, and audit actors without
making one employee the maintenance bottleneck.

## Maintenance and Versions

1. Clone the latest published version into a draft.
2. Add, remove, reorder, or upgrade members.
3. Review the member diff and newer-version suggestions.
4. Confirm the collection semantic version.
5. Publish the immutable snapshot.

Recommended version semantics:

- patch: member patch upgrades or non-breaking corrections;
- minor: optional members, member minor upgrades, or compatible expansion;
- major: member removal, member major upgrade, or changed install
  expectations.

The UI can suggest a bump, but the curator confirms it. If a member version is
yanked, hidden, archived, or inaccessible, resolve reports the collection as
degraded before local writes. It never silently substitutes `latest`.

## Import from Internal GitLab

The recommended organization source chain is:

```text
public GitHub
  -> organization-controlled internal GitLab mirror
  -> SkillHub preview
  -> scanner/review/publish
  -> collection draft
```

From collection maintenance, choose **Import from GitLab**:

1. Enter an allowlisted project path and branch, tag, or commit.
2. SkillHub resolves the ref to an immutable commit SHA and previews discovered
   `SKILL.md` roots.
3. Explicitly select candidates and confirm target slug, version, and
   visibility.
4. Each candidate enters the existing publish, scanner, and review workflow.
5. Only actual `PUBLISHED` versions can seed the collection draft.

The backend fixes the GitLab host; the browser never receives the token.
Repository scripts, hooks, and code are not executed. Archive traversal,
symlinks, duplicate paths, file counts, and sizes are bounded.

**Check for updates** runs only when a curator requests it. An unchanged SHA
does not download the archive or create a new import. A changed SHA creates a
linked immutable preview, but it never auto-selects, imports, approves,
publishes, or changes a collection.

## Install a Whole Collection

For a CLI distributed through an internal Nexus npm group, the two registry
arguments have different owners:

```bash
npx --yes --registry <Nexus-npm-group> <internal-cli-package>@<exact-version> \
  collection install @opensource/superpowers \
  --registry <SkillHub-base-URL> \
  --scope user
```

- the first `--registry` is consumed by `npx` to fetch the pinned CLI;
- the second is consumed by SkillHub CLI to resolve and download the
  collection;
- collection install always requires the explicit SkillHub registry.

You can also pin the collection:

```bash
skillhub collection install @opensource/superpowers \
  --version 1.1.0 \
  --registry https://skillhub.example.com \
  --scope project \
  --agent codex
```

The CLI preflights every member and destination, downloads and stages every
package, then commits one transaction. Any conflict, download, extraction,
rename, or inventory failure removes new writes and restores `--force`
backups plus the previous inventory.

Collection-level update and remove commands are not part of this release.
Curator source checks and employee local updates never run automatically.

## Enablement and Rollback

Enable in this order:

1. backend collections;
2. web collections after API smoke;
3. verify GitLab CA, allowlist, and read-only token;
4. backend GitLab import;
5. web GitLab import after API smoke.

Rollback in reverse by disabling web/import/collection flags and reverting
application images. Additive `local_*` tables remain as audit evidence; the
existing Skill functions do not depend on these flags.

## MVP Non-Goals

- arbitrary GitHub/GitLab URLs or employee installation of unreviewed sources;
- cross-namespace, nested, or dynamic label collections;
- webhook or background synchronization;
- automatic approval, Skill publication, or collection publication;
- a per-collection owner;
- collection-level CLI update/remove.
