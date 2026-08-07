# ZeroWeave

[English](README.en.md)

**项目开局编排器 Skill**：新项目从零创建时，一次性把三套体系织进项目——**项目管理体系**（管理五件套 + AI 工作规则）、**部署体系**（专用账号 + Docker + rsync 直推 + 私有 Git 仓库备份）、**UI 体系**（调起 uiweft 生成 DESIGN.md）；也能把缺体系的旧项目改造成"从一开始就装好"的状态。

ZeroWeave 只在开局/改造时运行一次，装完即退场——项目的日常约束由装进项目的文件（`AGENTS.md` + 管理五件套）承担，不留下对本 Skill 的运行时依赖。

## 适用环境

任何支持 Agent Skills（`SKILL.md` 格式）的 AI 编码工具：Kimi Code、Claude Code、Codex 等。

## 前置条件

- **必需**：无。
- **可选**：UI 支线依赖 [uiweft](https://github.com/zouh9426/uiweft)。未安装时 ZeroWeave 会提示你安装并暂停 UI 支线，管理体系与部署体系不受影响。
- 部署体系按项目模式裁剪：仅"可部署代码项目"安装；无部署交付项目（报告/PPT 等）只装管理体系。

## 安装

把本仓库复制到你的 skills 目录（任一即可）：

```bash
# Kimi Code
git clone https://github.com/zouh9426/zeroweave ~/.kimi-code/skills/zeroweave
# 或通用位置（多工具共享）
git clone https://github.com/zouh9426/zeroweave ~/.agents/skills/zeroweave
```

新开会话即可被自动触发。也可以把 `SETUP.md` 里的安装引导提示词贴给你的 AI，让它完成安装与自检。

## 快速上手

对你的 AI 说：

- **新项目**："用 ZeroWeave 从零初始化这个项目"——它会一次性问齐项目身份、GitHub、服务器、域名等信息（答"待定"也行，会登记成任务），然后装好三体系。
- **旧项目**："用 ZeroWeave 改造这个旧项目"——它会先只读审计、出差距报告和改造方案，**你批准后才动手**；已有内容走合并/归档，不动业务代码。

## 两条工作流

| 工作流 | 场景 | 流程 |
|---|---|---|
| init | 从零创建 | 依赖自检 → 信息采集 → 装管理体系 → 装部署体系 → 装 UI 体系 → 收口闭环 |
| adopt | 旧项目改造 | 审计（`scripts/audit.py` 只读探测）→ 差距报告 → 改造方案（用户拍板）→ 幂等安装 → 对齐收尾 |

## 文件结构

```text
zeroweave/
├── SKILL.md                 # 编排逻辑：模式判断、信息采集、两条工作流
├── references/              # 规范正文（管理规范精简版/完整参考版、部署规范）
├── assets/
│   ├── project/             # 项目文件模板（AGENTS/README/五件套等）
│   ├── deploy/              # 四栈部署模板（Next.js/Python/Go/静态站）+ 通用件
│   └── checklists/          # 上线 Checklist、审计报告、改造方案模板
└── scripts/audit.py         # 旧项目只读审计工具（纯标准库）
```

## 许可证

MIT，见 [LICENSE](LICENSE)。
