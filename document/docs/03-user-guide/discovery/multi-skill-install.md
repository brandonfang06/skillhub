---
title: 批量安装多个 Skills
sidebar_position: 3
description: 从搜索页面一次选择并安装多个 Skills
---

# 批量安装多个 Skills

批量安装功能让已登录用户从搜索结果中一次选择最多 20 个 Skills，统一指定安装范围，并选择在网页直接指定单一 Agent，或在终端中交互选择多个 Agents／Generic。

## 使用前准备

- 已登录 SkillHub 网页。
- 本机已安装 Node.js，并可使用 `npx`。
- 终端中的 SkillHub CLI 已完成身份验证。网页生成的指令不会包含浏览器登录凭证或 Token。

## 操作步骤

1. 打开 SkillHub 的“搜索”页面，点击 **批量安装多个 Skills**。
2. 勾选 Skill 标题左侧的复选框。你可以继续搜索、筛选或切换分页，当前浏览器分页会保留已选内容。
3. 选择完成后，点击结果列表上方的 **继续安装**。
4. 在 **安装目标** 中选择：
   - **安装方式**：“直接指定 Agent”会生成可直接执行的指令；“终端交互选择”会让 CLI 针对每个 Skill 询问一次安装目标，可多选 Agents 或 Generic。
   - **安装范围**：选择“用户”或“项目”。选择“项目”时，请稍后在目标项目目录中执行指令。
   - **Agent 目标**：仅在“直接指定 Agent”模式选择一个 Agent，或选择 **Generic（共享目录）**；这个选择会套用到所有已选 Skills。
5. 在默认展开的 **已选择 Skills** 区域确认清单；如有需要，可移除单个 Skill 或清空选择。
6. 点击 **复制全部指令**，再将指令贴到终端执行。
7. 如果使用终端交互模式，请依序为每个 Skill 选择安装目标；然后检查每一行的执行结果。每个 Skill 都是独立安装，某一行失败不会撤销已经成功的安装。

## 安装行为

- 每条指令都会安装该 Skill 最新可用的已发布版本。
- 指令默认包含 `--force`，仅替换经过验证的同来源、CLI 管理的现有安装；其中的本地修改可能被覆盖。不要将它当作覆盖任意目录的授权。
- 批量安装使用公开发布的 `@astron-team/skillhub@latest`，不需要另外下载或构建内部 CLI。
- **直接指定 Agent**：网页为所有 Skills 指定同一个 Agent，贴上后不再询问目标。
- **终端交互选择**：生成的指令不包含 `--agent`。公开 CLI 会针对每个 Skill 显示一次目标多选画面，可选择侦测到的多个 Agents 与 Generic。
- 终端交互模式必须在真正的交互式终端中执行，不适用于 GitLab CI、后台任务或其他非交互环境。

## Generic：跨平台共享目录

在“直接指定 Agent”中选择 **Generic（共享目录）**，即可不用终端交互，直接安装到 `.agents/skills`。网页使用公开 npm CLI 的 `--dir`，不需要内部 CLI 或重新构建。

以下语法适用于 **Windows PowerShell、Linux Bash、macOS Bash/Zsh**；双引号保留路径中的空格，`$HOME` 由终端展开。Windows 请使用 PowerShell，不是 CMD。

用户范围（当前用户的共享目录）：

```sh
npx @astron-team/skillhub@latest install @namespace/skill --registry https://your-skillhub.example --dir "$HOME/.agents/skills" --force
```

项目范围（先进入目标项目目录）：

```sh
npx @astron-team/skillhub@latest install @namespace/skill --registry https://your-skillhub.example --dir "./.agents/skills" --force
```

- 示例需替换 namespace、skill 和 registry；网页会自动使用选中 Skills 与平台 URL（包含部署时的 `/skillhub` 前缀）。每个 Skill 仍生成一条指令，CLI 在共享根目录下建立各自的安装子目录。
- Generic 指令**不会同时带 `--scope` 或 `--agent`**，因为 OSS CLI 不允许这些参数与 `--dir` 混用。网页的范围选项直接决定目录。
- 只有会读取 `.agents/skills` 的 Agents 能使用这些 Skills；这不等于复制到所有 Agent 的专属目录。需要指定多个不同目标时，仍可使用“终端交互选择”。
- CLI 将显式 `--dir` 目标标记为 `custom`，并不表示安装失败。核对实际安装路径，不要把该标签当作网页 Generic／项目范围的名称。
- 2026-09-10 已使用 npm `0.1.12` 在 Windows PowerShell 与 Linux Bash 实际安装验证；macOS 按 Bash/Zsh 与 Node 路径规则兼容，尚未进行 Mac 实机验证。`@latest` 后续版本仍以公开 CLI 的实际行为为准。

## 登录与安装记录（所有目标适用）

复制指令本身不会产生下载记录。只有终端成功下载 Skill 时，SkillHub 才会逐一记录安装事件。同一条 Skill 指令即使选择多个安装目标，仍属于该 Skill 的一次成功下载。

安装记录归属于**执行指令时 CLI 登录的用户**，不一定是建立安装清单的网页用户。如果终端返回 `401`，请先完成 CLI 身份验证，再重新执行失败的指令。

## 选择清单的保存范围

选择清单只保存在目前的浏览器分页中，可在同一分页内跨搜索、筛选、翻页和重新载入继续使用。它不会同步到其他分页、浏览器或设备，并会在清空选择、登出或关闭分页后消失。
