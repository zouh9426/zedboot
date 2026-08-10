---
name: zedboot
description: 项目开局编排器。从零创建项目时一次性装好三套体系——项目管理体系（管理五件套 + 工作规则）、部署体系（Docker + rsync 直推 + 私有 Git 仓库备份）、UI 体系（调起 uiweft 生成 DESIGN.md）；也用于把缺体系的旧项目改造成"从一开始就装好"的状态（审计 → 差距方案 → 幂等安装）。本 Skill 只在开局/改造时运行一次，装完即退场，日常约束由装进项目的文件承担。Use when starting a new project from scratch, bootstrapping project management / deployment / UI systems, or retrofitting an existing project that lacks these systems.
---

# zedboot — 项目开局编排器

你不是在"写文档"，你是在**把三套体系织进一个项目并让它们互相登记、形成闭环**。装完之后 zedboot 退场：项目的日常运转靠的是装进项目的 `AGENTS.md` + 管理五件套，不再读取本 Skill。

三套体系：

| 体系 | 内容 | 安装产物 | 适用范围 |
|---|---|---|---|
| 项目管理 | AI-Ready 项目管理规范 v1.4 | `docs/project/` 五件套 + 入口文件 + `archive/` | 所有项目 |
| 部署 | 专用账号隔离 + Docker + Git/rsync 工作流 | Dockerfile 等 + `docs/guides/deployment.md` | 仅"可部署代码项目"（含混合项目的代码部分） |
| UI | uiweft 编排工作流 | `DESIGN.md`（由 uiweft 生成） | 仅项目有界面时 |

## 模式判断：init 还是 adopt

- **init（从零创建）**：目录为空或只有零星草稿，用户明确说"从零开始/新项目"。
- **adopt（旧项目改造）**：目录里已有成规模的代码/文档，用户说"改造/补体系/规范化/接入 zedboot"。
- 拿不准就问一句；两者只差一个审计头部，安装逻辑完全复用。

## 环境探测（会话开始时执行）

本 Skill 工具无关（Kimi Code / Claude Code / Codex 等均可），源码里不写死任何安装路径，运行时按以下规则解析：

- **候选技能目录**：`~/.agents/skills/`（通用约定）、`~/.kimi-code/skills/`（Kimi Code）、`~/.claude/skills/`（Claude Code）、`~/.codex/skills/`（Codex）、当前项目的 `.agents/skills/` 与 `.kimi-code/skills/`。当前工具另有约定的技能目录时，以其为准。
- **按名识别，不按目录名**：在候选目录下逐层找 `SKILL.md`，读 frontmatter 的 `name:` 字段匹配（目录名可能与 skill 名不一致）。本 Skill 自身的路径（`references/`、`assets/`、`scripts/` 的基准）同样由"name 为 zedboot 的 SKILL.md 所在目录"解析，命令中的 `<skill路径>` 即指它。

## 依赖自检（任何工作流的第一步）

1. **uiweft 自检**（项目有界面时）：按上面的环境探测规则查找 name 为 `uiweft` 的 SKILL.md。找到 → 记录其路径备用；找不到 → **明确提示用户安装 uiweft**（https://github.com/zouh9426/uiweft），并告知 UI 支线暂停，管理体系与部署体系不受影响继续走。不要试图自己替代 uiweft 定 UI 规范。
2. **GitHub 认证探测**（可部署/混合项目）：`gh auth status` 或检查 `~/.ssh/` 已有 key 与 `ssh -T git@github.com`。已配好 → 只确认账号，不问凭据；没配 → 在信息采集时给用户一次性配置指引，或允许"暂用本地 Git，远程待补"。
3. **Git 本体探测**（所有项目）：`git --version`。不可用 → 给两个选项：引导安装（macOS：`xcode-select --install`）；或登记"暂不启用 Git"——则第 1 步的 Git 与隐私防线条目整组跳过 + 登记 TODO 待补，其余体系照常（与 uiweft 缺失的降级风格一致）。

## Phase 0：信息采集（init 的硬性前置；adopt 先挖后问）

本 Skill 只跑一次，所以开局必须一次性把信息要齐。adopt 模式先从旧项目文件里挖（`.env.example`、README、旧部署脚本里常有答案），挖不到再问用户。

**A. 项目身份（必需，不问齐不动工）**：项目名称、项目代码（任务编号前缀，如 WEB）、项目模式（可部署代码 / 无部署交付 / 混合）、一句话简介、目标用户、内容语言（中/英/双语——UI 支线也要用，一次问两处用）。

**B. Git/GitHub（可部署与混合项目必需；无部署项目可选）**：GitHub 账号；仓库新建还是已有；新建则用 `gh repo create <项目名> --private` 现场建。**规则：每项目一个独立私有仓库；本地 Commit 照常，push 只与发布/交付绑定。**

**C. 服务器（可部署项目；允许"待定"）**：服务器 IP、SSH 端口（默认 22）、项目专用账号名（默认 = 项目名）、部署密钥本地私钥路径（默认 `~/.ssh/<项目名>_deploy`）、服务器所在地区（大陆 VPS 提醒 ICP 备案：备案通过前 80/443 被拦截）、容器端口分配（共机每项目一个，可建议从 3001 起）。落盘目标按下文「存储纪律」分流：可推导值（账号、目录、默认密钥路径约定）入 PROJECT_INDEX/deployment.md；不可推导值（IP、端口、真实密钥路径）只入 `docs/private/ops.md`，入库文件写占位符。系统层操作（建账号、装 Docker、装 Caddy、防火墙放行 443）AI 够不着——列进上线 Checklist 交给用户。

**D. 域名（可部署项目；允许"待定"）**：域名、DNS 托管商、是否已加 A 记录指向服务器。

**E. 应用密钥（可部署项目）**：`.env` 需要的密钥项。能现场生成的（随机密码/密钥）直接生成；用户已有的第三方 key 当场要或登记待补。`.env.example` 只写键名入库；`.env` 永不入库。

**F. 备份策略（有默认值，一问带过）**：保留份数（默认 7 份滚动）、是否同步对象存储异地容灾（默认否，登记为候选任务）。

**"待定"机制**：B~F 任何一项都可以答待定——不阻塞流程。待定项自动生成 TODO 任务 + 在 PROJECT_STATE 标注，之后补上时按存储纪律分流落盘（可推导值入入库文档，不可推导值入 ops.md）。填写约定：**能确定的可推导字段一律当场填实**（如项目账号默认 = 项目名），只有真正待定的项在表格中统一写 `待定（任务编号）`（如"待定（ZWT-002）"）；脚本变量区与 deployment.md 只保留 `<占位符>` + 指向 `docs/private/ops.md` 的注记，真实值（含已定项）一律写入 ops.md。

**存储纪律（隐私线，违反即泄露事故）**：

1. **可推导值可入库**：账号 = 项目名、服务器目录 = `/opt/<项目名>`、本地密钥路径默认约定 = `~/.ssh/<项目名>_deploy`——这类"项目名推导值"本 Skill 已公开，不算隐私，可直接写入入库文档。
2. **不可推导值必须隔离**：服务器 IP、SSH 端口、密钥真实路径（偏离默认约定时）、SSH 别名、crontab 具体调度、备份策略细节，一律只写入 `docs/private/ops.md`（本地文件，`.gitignore` 排除，永不入库）。入库文档（`PROJECT_INDEX.md` 外部资源表、`docs/guides/deployment.md` 等）对应位置只写占位符 + 指向 `docs/private/ops.md` 的注记。占位符命名约定：**隔离值用英文大写词**（`<PRODUCTION_SERVER_IP>`、`<DEPLOY_USER>`、`~/.ssh/<DEPLOY_KEY>`，与部署脚本的环境变量同形），**可推导/业务值用中文语义词**（`<项目名>`、`<域名>`、`<端口>`）——占位符本身即标明"该不该入库"。
3. **秘密本体永不入库**：私钥内容、密码、token 不写入任何入库文件，只存在于服务器 `.env` 和用户本地（ops.md 也只记位置与路径，不记秘密本体）。
4. **域名与公开联系邮箱默认保留**：属公开信息可入库；用户特别要求时才隔离进 ops.md。

ops.md 不进 Git、没有版本备份——落盘时提醒用户为它配独立私有备份通道（如私有 ops-notes 仓库），否则换机即丢。

**转 Public 前置**：仓库 Private → Public 前，必须先清理 Git 历史中的运维真实值（`git filter-repo` 或重建仓库）——只改工作区文件不够，历史里仍有残留。配套兜底：本 Skill 提供项目级 pre-push 隐私闸门（`assets/hooks/pre-push.tmpl`，装进 `.git/hooks/pre-push`，自包含 bash、不依赖 Skill 路径），命中私钥/本机路径/公网 IP 即拒推，安装见 init 第 1 步（Git 与隐私防线条目）与 adopt 第 C 步；本机若另有全局 hooksPath 闸门（`~/.git-hooks/pre-push`），两者共存、互不覆盖。

## 工作流 init：从零创建

```text
0. 依赖自检 + 信息采集（见上）
1. 装管理体系（所有模式）
2. 装部署体系（可部署/混合）
3. 装 UI 体系（有界面）
4. 收口闭环
```

### 1. 装管理体系

- 用 `assets/project/` 模板生成：`README.md`、`AGENTS.md`、`CHANGELOG.md`、`docs/README.md`、`docs/project/` 五件套（PROJECT_RULES 见下、PROJECT_INDEX、PROJECT_STATE、TODO、DECISION_LOG）、`archive/README.md`。
- **PROJECT_RULES.md = 复制 `references/project-rules-compact.md` 全文**进 `docs/project/PROJECT_RULES.md`（AI 日常读项目内的副本，不读 Skill）。
- 完整参考版（`references/project-rules-reference.md`）默认**不复制进项目**；此时 AGENTS.md 里"完整参考版位置"一行注明"未随项目安装，见 zedboot skill 的 references/ 目录"。用户明确要求随项目安装时，复制到 `docs/reference/PROJECT_RULES_REFERENCE.md` 并改写该行。
- 项目模式写入 PROJECT_INDEX 与 PROJECT_STATE；项目代码确定后，TODO 第一个任务 = 本项目的上线 Checklist（可部署项目）或第一个真实任务。
- 只创建当前实际需要的目录，不机械全建（管理规范 §4 自适应目录规则）。
- **Git 与隐私防线（所有启用 Git 的项目；可部署/混合默认启用，无部署项目按 Phase 0.B 的选择）**：初始化本地仓库 + `main` 分支 + 首次 commit，按 Phase 0.B 关联私有远程（**此时不 push**——push 随首次发布进行）；`.gitignore` 必须含 `.env`、`data/`、`backups/`、`docs/private/`；安装 pre-push 隐私闸门（`assets/hooks/pre-push.tmpl` 复制为 `.git/hooks/pre-push` 并 `chmod +x`；已存在则不覆盖，提示人工合并；`.git/hooks` 不随 clone 携带，新机器/重新克隆后重跑本步骤重装）。

### 2. 装部署体系（可部署/混合项目）

- 按技术栈选 `assets/deploy/` 模板落盘根目录：Dockerfile（nextjs/python/go 之一；不在库中按 `references/deployment-guide.md` §3 设计点现场编写）、`docker-compose.yml`、`docker-entrypoint.sh`、`backup.sh`、`deploy-rsync.sh`、`.dockerignore`（`dockerignore.tmpl`，**不可省**——防止 `COPY . .` 把 `.env`/`data/` 拷进镜像）。
  - 静态站点：无应用容器，按 `assets/deploy/static/README.md`——本地构建、rsync 只推 `dist/`、服务器共享 Caddy 直接伺服。
- 生成 `docs/guides/deployment.md`（用 `assets/deploy/deployment.md.tmpl`；入库文件只写占位符，真实运维值按下条入 ops.md）。
- 生成 `docs/private/ops.md`（用 `assets/project/ops.md.tmpl`，填入 Phase 0 采集的真实运维值），并提醒用户：ops.md 不进 Git、无版本备份，需配独立私有备份通道（如私有 ops-notes 仓库）。
- 上线 Checklist（`assets/checklists/go-live-checklist.md`）登记为 TODO 任务。
- `.env.example` 只写键名入库；`.env` 永不入库（`.gitignore` 纪律见第 1 步的 Git 条目）。

### 3. 装 UI 体系（项目有界面时）

- 调起自检通过的 uiweft，进入它的 Phase 0（提问 → UUPM 出方案 → 用户确认 → 生成 DESIGN.md）。zedboot 不碰 UI 内容本身。
- 完成后三件事：确认 `DESIGN.md` 落盘在项目根；登记进 PROJECT_INDEX；AGENTS.md 的"UI 规范"行就位（模板已带，确认内容语言一致）。
- 若用户选择把 UI Phase 0 延后（不在 init 当场做）：登记 TODO 任务，AGENTS.md 的"UI 规范"行保留但注明"DESIGN.md 尚未生成，见 <任务编号>"，INDEX 的「图片与设计」表状态写"待生成"。

### 4. 收口闭环

- 三体系交界面只有三个文件，逐一核对：`AGENTS.md`（引用 PROJECT_RULES、DESIGN.md、deployment.md）、`PROJECT_INDEX.md`（外部资源表填好：GitHub 仓库/服务器/域名/端口/备份）、`TODO.md`（初始任务建好）。
- 向用户输出**项目识别摘要**（管理规范 §7.1 的第一次实践），请用户确认。
- 全部信息一次要齐、一次落盘；之后本 Skill 退场。

## 工作流 adopt：旧项目改造

与 init 复用第 1~4 步，但前置审计头部，且所有安装动作改为幂等。

### A. 审计（只读）

- 跑 `python3 <skill路径>/scripts/audit.py <项目路径>` 拿机械探测报告；报告中标注 `unknown` 的项由你亲自补查。
- 补查 AI 判断项：现有文档质量、现有结构与框架的匹配度、根目录卫生、有无"服务器上手工改代码"的痕迹、`.env` 是否已被 git 跟踪（安全风险，发现即醒目提示）、入库文件是否含运维真实值（公网 IP / 本机绝对路径 / 私钥格式，audit.py 已机械探测，命中即列入风险项，改造方案中给出"移入 docs/private/ops.md + 历史清理评估"的处置）。
- 产出《审计报告》（模板：`assets/checklists/audit-report.md.tmpl`）：现状清单 + 三体系各自差距 + 风险项。**报告落盘到目标项目 `docs/project/AUDIT_REPORT.md`**（docs/project/ 此时可先行创建）。

### B. 出改造方案（硬性卡点）

- 用 `assets/checklists/adoption-plan.md.tmpl` 出方案：每个差距项给处置——**新建 / 合并（旧内容搬进新结构）/ 归档（进 `archive/`）/ 不动**。**方案落盘到目标项目 `docs/project/ADOPTION_PLAN.md`**，与审计报告一起作为改造任务的正式记录（改造完成验收后保留在 docs/project/，不归档）。
- 冲突逐条列出让用户裁决，例如：旧 README 内容如何并入新模板；已有异构部署（CI 推送、服务器拉 git）是否迁移到 rsync 体系。
- **用户批准后才动手**。方案本身登记为改造任务进 TODO；重大改动预判决议编号。
- 若旧项目没有 Git 或在 main 上裸奔开发：把"建 Git / 建分支纪律"列为方案的可选档，由用户选择，不强制执行。

### C. 幂等安装

每个动作都是"检查 → 存在则合并或跳过 → 不存在则创建"，所以 adopt 跑两遍不出事，也允许分次改造（这次只装管理体系，下次再装部署）：

- 缺的补：走 init 同款模板。
- 有的合：旧 README/TODO 的有效内容搬进新结构，旧文件归档进 `archive/`，索引记录替代关系。
- 部署体系：已有 Docker 但缺纪律 → 只补账号/rsync/备份与文档；已有全套异构部署 → 按 B 的用户裁决执行（迁移 or 仅文档对齐）。
- UI：无 DESIGN.md → 自检 uiweft 后调起其 Phase 0；有 DESIGN.md → 只登记不重定。
- pre-push 隐私闸门（项目已启用 Git 时）：`.git/hooks/pre-push` 不存在则用 `assets/hooks/pre-push.tmpl` 安装；已存在则跳过并提示人工合并。
- **绝不改动业务代码逻辑**；改造只动管理层、部署层、文档层。

### D. 对齐收尾

- DECISION_LOG 写一条"体系改造"决议：审计结论 + 处置 + 用户裁决记录。若该项目此前在无规范状态下运行，决议中补一段**前因说明**（改造前的工作方式、为何改造、自何版本起生效）。
- PROJECT_STATE 初始内容**从审计结果回填**（真实状态，不是空白模板）。
- 核对三体系交界面三个文件（同 init 第 4 步），输出项目识别摘要请用户确认。
- 效果对齐"一开始就装好"：入口文件、五件套、索引、归档关系全部就位。

## 硬性规则（任何阶段适用）

1. **信息采集不齐（或明确登记待定）不动工**；adopt 的方案未经用户批准不动手。
2. **幂等**：一切安装动作可重复执行；已存在且有效的内容不覆盖，走合并/归档。
3. **秘密边界**：私钥内容、密码、token 永不写入入库文件；只登记位置与引用。运维真实值（服务器 IP、SSH 端口、密钥真实路径、crontab 调度、本机绝对路径）同样不入库，统一存本地 `docs/private/ops.md`（已 gitignore）。
4. **UI 规范不归 zedboot 定**：uiweft 未安装就提示安装，不越权替代。
5. **装完即退场**：不在项目里留对本 Skill 的运行时依赖；项目文件不得引用 Skill 内路径作为日常必读（"完整参考版位置"这类注明除外）。
6. **Git 纪律**：每项目独立私有仓库；本地 Commit 照常；push 只与发布/交付绑定；Git Tag 在部署和线上验证之后打。
7. 改造只动管理/部署/文档层，**不动业务代码**。

## 文件索引

| 用途 | 路径（Skill 内） |
|---|---|
| 强制规则（复制进项目） | `references/project-rules-compact.md` |
| 完整参考版（按需查） | `references/project-rules-reference.md` |
| 部署规范正文 | `references/deployment-guide.md` |
| 项目文件模板 | `assets/project/`（AGENTS/README/CHANGELOG/五件套/archive/ops.md.tmpl——ops.md 落到项目 `docs/private/`） |
| 部署模板（四栈 + 通用件） | `assets/deploy/`（nextjs/python/go/static 四个栈目录，entrypoint 在栈目录内；compose/backup/rsync/dockerignore/deployment.md.tmpl 在目录根部） |
| Checklist 与报告模板 | `assets/checklists/`（go-live / audit-report / adoption-plan） |
| pre-push 隐私闸门模板 | `assets/hooks/pre-push.tmpl`（装进项目 `.git/hooks/`，自包含） |
| 旧项目审计脚本 | `scripts/audit.py` |
