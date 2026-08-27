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
   - **Agent target**: in Direct Agent mode, choose one Agent to apply to every selected Skill.
5. Review the initially expanded **Selected Skills** list. Remove individual Skills or clear the list if needed.
6. Select **Copy all commands**, then paste the commands into your Terminal.
7. In Terminal interactive mode, choose targets for each Skill in sequence. Check the result of every line; each Skill installs independently, so a failed line does not roll back successful installs.

## Installation Behavior

- Each command installs the latest available published version of that Skill.
- Commands include `--force` by default. The CLI downloads the Skill again and replaces every selected target directory, so local changes in those directories are not preserved.
- The flow uses the public `@astron-team/skillhub@latest` package. No internal CLI download or build is required.
- **Direct Agent** applies one Web-selected Agent to every Skill and does not prompt for targets in the Terminal.
- **Terminal interactive** omits `--agent`. The public CLI opens one target multiselect per Skill, where you can choose multiple detected Agents and Generic.
- Terminal interactive mode requires a real interactive Terminal. Do not use it in GitLab CI, background jobs, or other non-interactive environments.

## Authentication and Install Tracking

Copying commands does not create a download event. SkillHub records an install event for each Skill only after the Terminal successfully downloads it. Selecting multiple targets within one Skill command still represents one successful download of that Skill.

The event belongs to the **CLI user authenticated in the Terminal**, which may differ from the Web user who created the list. If the Terminal returns `401`, authenticate the CLI and retry the failed command.

## How Long Selections Last

The list is stored only in the current browser tab. It survives searches, filters, pagination, navigation, and reloads in that tab, but it does not sync to other tabs, browsers, or devices. Clearing the list, signing out, or closing the tab removes it.
