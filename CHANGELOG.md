# CHANGELOG

本项目所有值得记录的变更都写在这里。格式约定：每条目回答两个问题——**改了什么**、**为什么这么改（决策理由）**。

## [0.2.0] - 2026-08-07

开源发布 + 工具无关化。

- **skill 负载移入 `zeroweave/` 子目录**：仓库根只留门面粉件（README/SETUP/CHANGELOG/AGENTS/LICENSE/CI），skill 本体（SKILL.md + references/ + assets/ + scripts/）独立成目录。理由：clone 下来的仓库不等于可直接加载的 skill 目录，门面与负载分离后结构清晰，也避免仓库级文件被误拷进技能目录。
- **SKILL.md 新增「环境探测」一节**：候选技能目录覆盖 `~/.agents/skills/`、`~/.kimi-code/skills/`、`~/.claude/skills/`、`~/.codex/skills/` 及项目级目录；skill 之间**按 frontmatter 的 `name:` 字段互相识别**，不按目录名；自身路径也由 name 解析。理由：面向所有支持 SKILL.md 的工具（Kimi Code / Claude Code / Codex 等），路径硬编码等于私有；目录名与 skill 名可能不一致，必须按名解析。
- **新增 README.md（中文主门面）/ README.en.md**：三套体系、两条工作流、核心设计决策、前置条件、安装与触发方式、仓库结构。理由：开源门面；中文为主是因为目标用户群是中文用户。
- **新增 SETUP.md / SETUP.en.md 安装引导提示词**：用户贴给自己的 AI agent 即可完成环境识别、按名查重、安装与自检。理由：安装涉及"仓库根 ≠ skill 目录"的细节，让 AI 代办最不容易错。
- **新增 LICENSE（MIT，Copyright (c) 2026 zouh9426）**。理由：MIT 的「保留版权声明」条款即署名保留，满足作者诉求；skill 类项目无专利考量，不需要 Apache-2.0 的重量。
- **新增 AGENTS.md（仓库级维护规则）**：维护者 agent 与使用方 agent 分离、无私有路径红线、双语同步、发版纪律。
- **新增 GitHub Actions 私有路径检查 CI**：检查正则用 `/Users/[a-zA-Z0-9_-]+/` 只匹配真实路径。理由：设计已消除私有路径的必要性，CI 做兜底防止后续迭代回潮。

## [0.1.0] - 2026-08-07

基线快照。首次构建完成时的原始版本（仓库根即 skill 目录、路径候选未覆盖全工具），仅供历史留档，不建议新用户使用。

该版本已包含的核心架构（沿用至今，详见 README）：

- 三体系编排：项目管理（规范 v1.4 双文件）+ 部署（栈无关 guide + 四栈模板）+ UI（委托 uiweft，零复制不漂移）。
- init / adopt 两条工作流：六组信息采集 + 待定机制、幂等安装、秘密边界、装完即退场。
- 管理规范 v1.4：修正发布流程 Git Tag 时机冲突（改为部署与线上验证后打 Tag）、明确 push 与发布绑定、根目录白名单纳入部署文件。
- `scripts/audit.py` 只读审计：纯标准库，探测不到标 unknown 交 AI 判断。
- 经五场景实测（3 init + 2 adopt，含乱套旧项目与异构部署冲突裁决），累计修进 8 处实测发现的问题。
