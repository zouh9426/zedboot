---
name: zedboot
description: 项目开局编排器。从零创建项目时一次性装好三套体系——项目管理体系（管理五件套 + 工作规则）、部署体系（Docker + rsync 直推 + 私有 Git 仓库备份）、UI 体系（调起 zedui 生成 DESIGN.md）；也用于把缺体系的旧项目改造成"从一开始就装好"的状态（审计 → 差距方案 → 幂等安装）。本 Skill 只在开局/改造时运行一次，装完即退场，日常约束由装进项目的文件承担。Use when the user explicitly asks to initialize a new project with zedboot, bootstrap project management / deployment / UI systems, or retrofit an existing project that lacks these systems. Do not invoke merely because the user is starting a new coding project.
compatibility: Requires Python 3.8+ (audit/verify scripts). Git is recommended and required for the Git/privacy-gate features; core setup can degrade without it. Deployment workflows assume a Unix-like shell with SSH, rsync and Docker on the server side; UI integration optionally requires the zedui skill.
---

# zedboot — 项目开局编排器

你不是在"写文档"，你是在**把三套体系织进一个项目并让它们互相登记、形成闭环**。装完之后 zedboot 退场：项目的日常运转靠的是装进项目的 `AGENTS.md` + 管理五件套，不再读取本 Skill。

三套体系：

| 体系 | 内容 | 安装产物 | 适用范围 |
|---|---|---|---|
| 项目管理 | AI-Ready 项目管理规范 v1.4 | `docs/project/` 五件套 + 入口文件 + `archive/` | 所有项目 |
| 部署 | 专用账号 + Docker（权限分档，见 §2 安全档位）+ Git/rsync 工作流 | Dockerfile 等 + `docs/guides/deployment.md` | 仅"可部署代码项目"（含混合项目的代码部分） |
| UI | zedui 编排工作流 | `DESIGN.md`（由 zedui 生成） | 仅项目有界面时 |

本文件是**控制器**：模式判断、依赖自检、硬性规则在此；Phase 0 采集明细与两条工作流的逐步细则按需加载 `references/` 下对应文件（执行到哪步读哪份）。

## 模式判断：init 还是 adopt

- **init（从零创建）**：目录为空或只有零星草稿，用户明确说"从零开始/新项目"。
- **adopt（旧项目改造）**：目录里已有成规模的代码/文档，用户说"改造/补体系/规范化/接入 zedboot"。
- 拿不准就问一句；两者只差一个审计头部，安装逻辑完全复用。

## 环境探测（会话开始时执行）

本 Skill 工具无关（Kimi Code / Claude Code / Codex 等均可），源码里不写死任何安装路径，运行时按以下规则解析：

- **候选技能目录**：`~/.agents/skills/`（通用约定）、`~/.kimi-code/skills/`（Kimi Code）、`~/.claude/skills/`（Claude Code）、`~/.codex/skills/`（Codex）、当前项目的 `.agents/skills/` 与 `.kimi-code/skills/`。当前工具另有约定的技能目录时，以其为准。
- **按名识别，不按目录名**：在候选目录下逐层找 `SKILL.md`，读 frontmatter 的 `name:` 字段匹配（目录名可能与 skill 名不一致；name 比对不区分大小写）。**用 `find` 实现时加 `-L` 跟随符号链接**——skill 常以符号链接方式安装，裸 `find` 会把它们整棵漏掉。本 Skill 自身的路径（`references/`、`assets/`、`scripts/` 的基准）同样由"name 为 zedboot 的 SKILL.md 所在目录"解析，命令中的 `<skill路径>` 即指它。

## 依赖自检（任何工作流的第一步）

1. **zedui 自检**（项目有界面时）：按上面的环境探测规则查找 name 为 `zedui` 的 SKILL.md（name 比对不区分大小写，兼容改名前安装的旧副本）。找到 → 记录其路径备用；找不到 → **明确提示用户安装 zedui**（https://github.com/zouh9426/zedui），并告知 UI 支线暂停，管理体系与部署体系不受影响继续走。不要试图自己替代 zedui 定 UI 规范。
2. **GitHub 认证探测**（可部署/混合项目）：`gh auth status` 或检查 `~/.ssh/` 已有 key 与 `ssh -T git@github.com`。已配好 → 只确认账号，不问凭据；没配 → 在信息采集时给用户一次性配置指引，或允许"暂用本地 Git，远程待补"。
3. **Git 本体探测**（所有项目）：`git --version`。不可用 → 给两个选项：引导安装（macOS：`xcode-select --install`）；或登记"暂不启用 Git"——则 init 第 1 步的 Git 与隐私防线条目整组跳过 + 登记 TODO 待补，其余体系照常（与 zedui 缺失的降级风格一致）。

## Phase 0：信息采集（init 的硬性前置；adopt 先挖后问）

本 Skill 只跑一次，开局一次性把信息要齐：**A 项目身份 / B Git·GitHub / C 服务器 / D 域名 / E 应用密钥 / F 备份策略**六组；B~F 任何一组都可答"待定"（自动生成 TODO，不阻塞流程）。三条红线先记住：

- **密钥采集只问键名不问值**——绝不让用户把 key 值贴进对话；秘密本体不进聊天上下文、永不入库，值由用户自行落盘 `.env`。
- 运维真实值（IP / SSH 端口 / 密钥真实路径 / crontab 调度）只存本地 `docs/private/ops.md`（gitignore），入库文件一律写占位符；部署脚本消费的六事实另存 `docs/private/deploy.env`（同为 gitignore，永不入库）。
- 可推导值（账号 = 项目名、`/opt/<项目名>` 目录）可直接入库。

→ 六组采集项明细、"待定"机制、存储纪律、三事实分离、转 Public 前置：**执行 Phase 0 前必读 `references/info-collection.md`**。

## 工作流 init：从零创建

```text
0. 依赖自检 + 信息采集（见上）
1. 装管理体系（所有模式）
2. 装部署体系（可部署/混合）
3. 装 UI 体系（有界面）
4. 收口闭环（含 verify.py 装后机械校验）
```

→ 每步的安装产物、模板路径与幂等规则：**执行到对应步骤时阅读 `references/init-workflow.md`**。

## 工作流 adopt：旧项目改造

与 init 复用第 1~4 步，但前置审计头部，且所有安装动作改为幂等：

```text
A. 审计（只读）：audit.py 机械探测 + AI 补查 → 《审计报告》落盘 docs/project/
B. 出改造方案（硬性卡点）：逐项给处置（新建/合并/归档/不动），用户批准后才动手
C. 幂等安装：缺的补、有的合，已存在且有效的内容不覆盖；不动业务代码
D. 对齐收尾：verify.py 校验 → 决议 + 状态回填 + 三体系交界面核对
```

→ 各步细则：**执行到对应步骤时阅读 `references/adopt-workflow.md`**。

## 硬性规则（任何阶段适用）

1. **信息采集不齐（或明确登记待定）不动工**；adopt 的方案未经用户批准不动手。
2. **幂等**：一切安装动作可重复执行；已存在且有效的内容不覆盖，走合并/归档。
3. **秘密边界**：私钥内容、密码、token 永不写入入库文件，也永不进入对话上下文（采集只问键名不问值，值由用户自行落盘）；只登记位置与引用。运维真实值（服务器 IP、SSH 端口、密钥真实路径、crontab 调度、本机绝对路径）同样不入库，统一存本地 `docs/private/ops.md`（已 gitignore）。
4. **UI 规范不归 zedboot 定**：zedui 未安装就提示安装，不越权替代。
5. **装完即退场**：不在项目里留对本 Skill 的运行时依赖；项目文件不得引用 Skill 内路径作为日常必读（"完整参考版位置"这类注明除外）。
6. **Git 纪律**：每项目独立私有仓库；本地 Commit 照常；push 只与发布/交付绑定；Git Tag 在部署和线上验证之后打。
7. 改造只动管理/部署/文档层，**不动业务代码**。

## 文件索引

| 用途 | 路径（Skill 内） |
|---|---|
| 信息采集细则（Phase 0 执行前必读） | `references/info-collection.md` |
| init 工作流细则（按步阅读） | `references/init-workflow.md` |
| adopt 工作流细则（按步阅读） | `references/adopt-workflow.md` |
| 强制规则（复制进项目） | `references/project-rules-compact.md` |
| 完整参考版（按需查） | `references/project-rules-reference.md` |
| 部署规范正文 | `references/deployment-guide.md` |
| 项目文件模板 | `assets/project/`（AGENTS/README/CHANGELOG/五件套/archive/ops.md.tmpl/deploy.env.tmpl——ops.md 与 deploy.env 落到项目 `docs/private/`） |
| 备份清单模板（zedback 联动） | `assets/project/backup-manifest.conf.tmpl`（落到项目 `docs/private/`，zedback 每日备份消费） |
| 部署模板（四栈 + 通用件） | `assets/deploy/`（nextjs/python/go/static 四个栈目录，entrypoint 在 nextjs/python 栈目录内（go 栈 ENTRYPOINT 烤进镜像、无独立 entrypoint）；compose/backup/rsync/dockerignore/deployment.md.tmpl（含静态站变体 deployment-static.md.tmpl）在目录根部） |
| Checklist 与报告模板 | `assets/checklists/`（go-live / audit-report / adoption-plan） |
| pre-push 隐私闸门模板 | `assets/hooks/pre-push.tmpl`（装进项目 `.git/hooks/`，自包含） |
| 旧项目审计脚本 | `scripts/audit.py` |
| 装后机械校验脚本 | `scripts/verify.py` |
