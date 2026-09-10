---
title: Install Multiple Skills
sidebar_position: 3
description: Select and install multiple Skills from Search
---

# Install Multiple Skills

The multi-skill install flow lets a signed-in user select up to 20 Skills from Search, apply one scope, and either choose one Agent in the Web application or choose multiple Agents and Generic interactively in the Terminal.

## Before You Start

- Sign in to the SkillHub Web application.
- Install Node.js locally and make sure `npx` is available.
- Authenticate the SkillHub CLI in your Terminal. Generated commands never include your browser credential or token.

## Steps

1. Open SkillHub Search and select **Install multiple Skills**.
2. Select the checkbox to the left of each Skill title. You can continue searching, filtering, or changing pages; the current browser tab keeps your selections.
3. When the list is ready, select **Continue to install** above the results.
4. Under **Install targets**, choose:
   - **Install method**: Direct Agent creates ready-to-run commands. Terminal interactive asks for targets once per Skill and supports multiple Agents or Generic.
   - **Install scope**: choose User or Project. For Project scope, run the copied commands from the intended project directory.
   - **Agent target**: in Direct Agent mode, choose one Agent or **Generic (shared directory)** to apply to every selected Skill.
5. Review the initially expanded **Selected Skills** list. Remove individual Skills or clear the list if needed.
6. Select **Copy all commands**, then paste the commands into your Terminal.
7. In Terminal interactive mode, choose targets for each Skill in sequence. Check the result of every line; each Skill installs independently, so a failed line does not roll back successful installs.

## Installation Behavior

- Each command installs the latest available published version of that Skill.
- Commands include `--force` by default. It only replaces a verified same-source, CLI-managed installation; local changes there may be overwritten. It is not permission to overwrite arbitrary directories.
- The flow uses the public `@astron-team/skillhub@latest` package. No internal CLI download or build is required.
- **Direct Agent** applies one Web-selected Agent to every Skill and does not prompt for targets in the Terminal.
- **Terminal interactive** omits `--agent`. The public CLI opens one target multiselect per Skill, where you can choose multiple detected Agents and Generic.
- Terminal interactive mode requires a real interactive Terminal. Do not use it in GitLab CI, background jobs, or other non-interactive environments.

## Generic: Cross-Platform Shared Directory

Choose **Generic (shared directory)** in Direct Agent mode to install into `.agents/skills` without interactive prompts. This uses the public npm CLI's `--dir`; no internal CLI or rebuild is required.

The same syntax works in **Windows PowerShell, Linux Bash, and macOS Bash/Zsh**. Double quotes preserve spaces and the shell expands `$HOME`. Use PowerShell on Windows, not CMD.

User scope:

```sh
npx @astron-team/skillhub@latest install @namespace/skill --registry https://your-skillhub.example --dir "$HOME/.agents/skills" --force
```

Project scope (run from the intended project directory):

```sh
npx @astron-team/skillhub@latest install @namespace/skill --registry https://your-skillhub.example --dir "./.agents/skills" --force
```

- Replace example coordinates and registry. The Web UI supplies selected Skills and the platform URL, including a deployed `/skillhub` prefix. Each Skill gets its own command and installation subdirectory.
- Generic commands omit both `--scope` and `--agent`: the OSS CLI rejects combining either with `--dir`. The Web scope selection determines the directory instead.
- Only Agents that read `.agents/skills` can use these Skills. This does not populate every Agent's private directory. Terminal interactive mode remains available for choosing multiple distinct targets.
- The CLI labels explicit `--dir` targets as `custom`. Check the actual installed path; that inventory label is not the Web Generic or Project scope label.
- Verified on 2026-09-10 using npm `0.1.12` on Windows PowerShell and Linux Bash. macOS compatibility follows Bash/Zsh and Node path handling; no native Mac verification was available. Future `@latest` versions remain subject to the public CLI's behavior.

## Authentication and Install Tracking

Copying commands does not create a download event. SkillHub records an install event for each Skill only after the Terminal successfully downloads it. Selecting multiple targets within one Skill command still represents one successful download of that Skill.

The event belongs to the **CLI user authenticated in the Terminal**, which may differ from the Web user who created the list. If the Terminal returns `401`, authenticate the CLI and retry the failed command.

## How Long Selections Last

The list is stored only in the current browser tab. It survives searches, filters, pagination, navigation, and reloads in that tab, but it does not sync to other tabs, browsers, or devices. Clearing the list, signing out, or closing the tab removes it.
