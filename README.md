# zedboot

> weave = 编织。项目管理、部署、UI 三套体系是三条线——zedboot 在项目开局把它们一次织好，日后不返工。

[English](README.en.md) · [安装引导提示词](SETUP.md) · [更新日志](CHANGELOG.md)

zedboot 是一个**项目开局编排 skill**：它自身不定规则、不做设计，而是在新项目从零创建时把三套成熟体系一次性织进项目并让它们互相登记、形成闭环；也能把缺体系的旧项目改造成"从一开始就装好"的状态。装完即退场——项目的日常约束由装进项目的文件承担，不留下对本 skill 的运行时依赖。

适用于所有支持 SKILL.md 技能的 AI 编码工具（Kimi Code / Claude Code / Codex 等）。

## 三套体系

| 体系 | 内容 | 安装产物 | 适用范围 |
|---|---|---|---|
| 项目管理 | AI-Ready 项目管理规范 v1.4 | `docs/project/` 五件套 + 入口文件 + `archive/` | 所有项目 |
| 部署 | 专用账号隔离 + Docker + rsync 直推 + 私有 Git 仓库备份 | Dockerfile 等 + `docs/guides/deployment.md` | 仅可部署代码项目 |
| UI | [zedui](https://github.com/zouh9426/zedui) 编排工作流 | `DESIGN.md`（由 zedui 生成） | 仅项目有界面时 |

## 两条工作流

```
init（从零创建）：依赖自检 → 信息采集（一次问齐，可答"待定"）→ 装管理体系 → 装部署体系 → 装 UI 体系 → 收口闭环
adopt（旧项目改造）：只读审计 → 差距报告 → 改造方案（用户拍板）→ 幂等安装 → 对齐收尾
```

## 核心设计决策

- **装完即退场**：skill 只在开局/改造时运行一次；日常约束全靠装进项目的 `AGENTS.md` + 管理五件套。日常阅读分层加载：每次任务只必读 `AGENTS.md`/`PROJECT_STATE`/`TODO` 等小文件（合计约 6 KB），规范大部头（PROJECT_RULES 等）按触发条件才读，日常 token 开销可控。
- **信息采集一次要齐**：项目身份、GitHub、服务器、域名、应用密钥、备份策略六组信息开局一次问清；任何一组可答"待定"，自动生成 TODO 不阻塞流程。**隐私线**：可推导值（账号 = 项目名、`/opt/<项目名>` 目录）落进 `PROJECT_INDEX.md` 外部资源表与部署文档；不可推导运维真实值（IP/SSH 端口/密钥路径/crontab 调度）只存本地 `docs/private/ops.md`（gitignore，永不入库），入库文档只写占位符——项目随时可转 Public 不泄露基础设施指纹。**秘密本体（私钥/密码/token）永不入库，也不进对话上下文**——采集只问键名不问值，值由用户自行落盘，只登记位置与引用。
- **幂等安装**：adopt 的每个动作都是"检查 → 存在则合并/归档 → 不存在则创建"，跑两遍不出事，允许分次改造；不动业务代码。
- **审计机械化**：`scripts/audit.py`（纯标准库、只读）做机械探测，探测不到的标 `unknown` 交 AI 判断，不硬猜；装完后 `scripts/verify.py`（同口径）机械校验安装承诺——文件齐备、占位符替换干净（含未提交的新文件）、`.gitignore` 四项与 `.env`/`docs/private/` 未跟踪、闸门就位，有 FAIL 即 exit 1。
- **Git 纪律**：每项目一个独立私有仓库；本地 commit 照常，push 只与发布/交付绑定；Git Tag 在部署和线上验证之后打。
- **UI 规范不越权**：UI 支线委托给 zedui；未安装时明确提示并暂停 UI 支线，其余体系照常。

## 前置条件

1. **Python 3.8+**（audit.py 装前审计 + verify.py 装后验收，均纯标准库）——init 与 adopt 的机械校验都需要
2. 可选：[zedui](https://github.com/zouh9426/zedui)（UI 支线；未安装时 UI 之外的功能不受影响）
3. 可选：`gh` CLI 或 SSH key（GitHub 私有仓库创建/关联；没有则指引一次性配置或允许远程待补）

## 安装

**推荐方式（AI 代办）**：打开 [SETUP.md](SETUP.md)，把全文贴给你的 AI agent，它会自动识别环境、安装 skill 并自检。

**手动方式**：把本仓库的 `zedboot/` 子目录拷进你的 AI 工具的技能目录（如 `~/.agents/skills/`、`~/.claude/skills/`、`~/.kimi-code/skills/`、`~/.codex/skills/`）。skill 之间按 frontmatter 的 `name:` 互相识别，不挑目录名、不挑工具。

## 使用

装好后，在你的项目里对 AI 说一句类似的话即可触发：

> "用 zedboot 从零初始化这个项目" / "用 zedboot 改造这个旧项目"

init 会先一次性问齐六组信息（可答"待定"）；adopt 会先只读审计、出改造方案，**你批准后才动手**。

## 仓库结构

```
zedboot/                    ← skill 本体（拷进技能目录的就是它）
├── SKILL.md                  ← 控制器：模式判断、依赖自检、硬性规则（细则按需加载 references/）
├── references/               ← 规范正文 + 工作流细则（信息采集/init/adopt、管理规范两版、部署规范）
├── assets/
│   ├── project/              ← 项目文件模板（AGENTS/README/五件套等）
│   ├── deploy/               ← 四栈部署模板（Next.js/Python/Go/静态站）+ 通用件
│   ├── checklists/           ← 上线 Checklist、审计报告、改造方案模板
│   └── hooks/                ← pre-push 隐私闸门模板
└── scripts/                  ← audit.py（装前只读审计）+ verify.py（装后机械校验，均纯标准库）
tests/                        ← audit.py + verify.py + pre-push hook + deploy 模板自动化测试（unittest，随 CI 运行）
README.md / README.en.md      ← 中英双门面
SETUP.md / SETUP.en.md        ← 安装引导提示词（贴给你的 AI 即可）
CHANGELOG.md                  ← 更新与决策日志
```

## 许可证

[MIT](LICENSE) · Copyright (c) 2026 zouh9426

可选依赖 zedui 的许可证归其作者所有，安装前请查阅其上游仓库。
