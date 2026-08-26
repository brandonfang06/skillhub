---
title: Install Multiple Skills
sidebar_position: 3
description: Select and install multiple Skills from Search
---

# Install Multiple Skills

The multi-skill install flow lets a signed-in user select up to 20 Skills from Search, apply one scope and Agent target, and copy ready-to-run Terminal commands.

## Before You Start

- Sign in to the SkillHub Web application.
- Install Node.js locally and make sure `npx` is available.
- Authenticate the SkillHub CLI in your Terminal. Generated commands never include your browser credential or token.

## Steps

1. Open SkillHub Search and select **Install multiple Skills**.
2. Select the checkbox to the left of each Skill title. You can continue searching, filtering, or changing pages; the current browser tab keeps your selections.
3. When the list is ready, select **Continue to install** above the results.
4. Under **Install targets**, choose:
   - **Install scope**: choose User or Project. For Project scope, run the copied commands from the intended project directory.
   - **Agent target**: choose one Agent. The same target applies to every selected Skill.
5. Review the initially expanded **Selected Skills** list. Remove individual Skills or clear the list if needed.
6. Select **Copy all commands**, then paste the commands into your Terminal.
7. Check the result of every line. Each Skill installs independently, so a failed line does not roll back successful installs.

## Installation Behavior

- Each command installs the latest available published version of that Skill.
- Commands include `--force` by default. The CLI downloads the Skill again and replaces its existing target directory, so local changes in that directory are not preserved.
- The flow uses the public `@astron-team/skillhub@latest` package. No internal CLI download or build is required.
- Batch commands currently support one Agent target. Generic is not available in this flow; use the interactive single-Skill installation when you need Generic.

## Authentication and Install Tracking

Copying commands does not create a download event. SkillHub records an install event for each Skill only after the Terminal successfully downloads it.

The event belongs to the **CLI user authenticated in the Terminal**, which may differ from the Web user who created the list. If the Terminal returns `401`, authenticate the CLI and retry the failed command.

## How Long Selections Last

The list is stored only in the current browser tab. It survives searches, filters, pagination, navigation, and reloads in that tab, but it does not sync to other tabs, browsers, or devices. Clearing the list, signing out, or closing the tab removes it.
