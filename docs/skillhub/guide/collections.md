# 版本化集合与 GitLab 导入

SkillHub 集合（Collection）是一组经过治理的 Skill 版本快照。它解决的是
「一个开源工具包包含多个 Skills，但员工必须逐一安装」的问题，同时保留
每个 Skill 原有的扫描、审核、搜索、下载与版本生命周期。

## 领域模型

集合坐标为：

```text
@<namespace>/<collection>
```

一个已发布的集合版本只包含同一 namespace 内的精确 `PUBLISHED` Skill
版本。例如：

```text
@opensource/superpowers@1.1.0
  -> brainstorming@2.1.0
  -> test-driven-development@3.0.1
  -> systematic-debugging@1.4.2
```

Skill 与集合各自维护独立版本线。发布 `brainstorming@2.2.0` 不会改变已经
发布的集合；curator 必须建立或修改草稿、接受升级，再发布新的集合版本。
旧集合版本仍可解析与审计。

## 谁可以维护集合

集合属于 namespace，不新增单一 `collection owner`：

- team namespace 的 `OWNER` 与 `ADMIN` 可建立、编辑、发布、封存与恢复；
- 普通 `MEMBER` 可查看及安装可访问的已发布集合，但不可修改；
- global namespace 由平台 `SKILL_ADMIN` 与 `SUPER_ADMIN` 维护。

系统会记录建立者、更新者、发布者与 audit actor，但不会把维护能力锁定在
单一人员。若未来需要更窄的授权，可另行增加 collection maintainer role。

## 维护与版本策略

1. 从最新发布版本建立草稿。
2. 添加、移除、排序或升级成员。
3. 检查 UI 显示的 member diff 与较新版本提示。
4. curator 确认集合 semantic version。
5. 发布不可变快照。

建议的版本语义：

- patch：成员 patch 升级或不改变工作流的修正；
- minor：新增可选成员、成员 minor 升级或向后兼容的能力扩展；
- major：移除成员、成员 major 升级或安装行为发生破坏性变化。

SkillHub 会建议版本，但最后由 curator 确认。若成员版本被 yank、隐藏、封存
或失去访问权限，解析会在安装前报告 degraded；系统不会静默改用 `latest`。

## 从内部 GitLab 导入

组织建议的来源链：

```text
public GitHub
  -> organization-controlled internal GitLab mirror
  -> SkillHub preview
  -> scanner/review/publish
  -> collection draft
```

在 collection maintenance 页面选择「从 GitLab 导入」：

1. 输入 allowlist 内的 GitLab project path 与 branch/tag/commit。
2. SkillHub 将 ref 解析为 immutable commit SHA 并显示候选 `SKILL.md`。
3. 明确勾选候选、确认目标 slug、版本与 visibility。
4. 每个候选进入既有 publish、scanner 与 review 流程。
5. 只有实际为 `PUBLISHED` 的版本才能加入 collection draft。

GitLab host 由 backend 固定配置，browser 不接触 token。Backend 不执行
repository 中的 script、hook 或 code；archive 会经过 traversal、symlink、
重复路径、档案数量与大小限制。

「检查更新」只在 curator 点击时执行。若固定 ref 的 SHA 未变化，不下载
archive，也不建立记录；若 SHA 改变，则建立 linked preview。它不会自动选择、
导入、审核、发布 Skill，也不会自动发布 collection。

## 一次安装整个集合

公司内部 CLI 由 Nexus npm group 提供时，命令中有两个不同的 registry：

```bash
npx --yes --registry <Nexus-npm-group> <internal-cli-package>@<exact-version> \
  collection install @opensource/superpowers \
  --registry <SkillHub-base-URL> \
  --scope user
```

- 第一个 `--registry` 由 `npx` 使用，下载明确版本的 CLI；
- 第二个 `--registry` 由 SkillHub CLI 使用，解析集合和下载 Skills；
- collection install 强制明确提供 SkillHub `--registry`。

也可锁定集合版本：

```bash
skillhub collection install @opensource/superpowers \
  --version 1.1.0 \
  --registry https://skillhub.example.com \
  --scope project \
  --agent codex
```

CLI 会先预检所有成员与目标，再下载并暂存全部 package，最后以一个 transaction
写入。如果任一冲突、下载、解压、rename 或 inventory 写入失败，先前安装会被
移除，`--force` 备份与旧 inventory 会恢复，不留下半套集合。

当前版本没有 collection-level update/remove 命令；检查上游更新是 curator
流程，员工更新本机集合也不会自动发生。

## 功能开关与回滚

启用顺序：

1. backend `SKILLHUB_COLLECTIONS_ENABLED=true`
2. API smoke 后启用 web collections
3. 验证 GitLab CA、allowlist 与 read-only token
4. backend `SKILLHUB_GITLAB_IMPORT_ENABLED=true`
5. API smoke 后启用 web GitLab import

回滚时反向关闭 web/import/collection flags 并回退应用 image。Additive
`local_*` tables 保留 audit evidence；既有 Skill functions 不依赖这些开关。

## MVP 不包含

- 任意 GitHub/GitLab URL 或员工未审核来源安装；
- cross-namespace、nested 或 label 动态集合；
- webhook/background 自动同步；
- 自动审核、Skill 发布或 collection 发布；
- per-collection owner；
- collection-level CLI update/remove。
