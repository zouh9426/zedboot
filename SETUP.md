# zedboot 安装引导提示词

> **用法**：把本文件**全部内容**（从下面分隔线开始）复制贴给你的 AI agent（Kimi Code / Claude Code / Codex 等均可），它会自动完成全套安装与自检。
> English version: [SETUP.en.md](SETUP.en.md)

---

你是安装助手。请帮我安装 **zedboot**（项目开局编排 skill）。按以下步骤执行，每步完成后告诉我结果；任何一步失败，停下来报告，不要跳过。

## 第 1 步：识别环境

1. 确认你是什么工具（Kimi Code / Claude Code / Codex / 其他），确定你的技能目录。常见候选：
   - `~/.agents/skills/`（通用约定）
   - `~/.kimi-code/skills/`（Kimi Code）
   - `~/.claude/skills/`（Claude Code）
   - `~/.codex/skills/`（Codex）
   如果你的工具另有约定的技能目录，以你的约定为准。
2. 检查依赖工具：`python3 --version`（adopt 工作流的审计脚本需要，纯标准库）。缺就先告诉我安装方法并停下。

## 第 2 步：检查已有安装

在技能目录下逐层找 `SKILL.md`，读 frontmatter 的 `name:` 字段，检查以下 skill 是否已安装（**按 name 匹配，不按目录名**——目录名可能与 skill 名不同）：

| skill 名 | 作用 | 必需性 |
|---|---|---|
| `zedboot` | 编排层本体 | 必需 |
| `zedui` | UI 支线（生成 DESIGN.md） | 可选 |

列出"已有 / 缺失"清单给我。

## 第 3 步：安装缺失的 skill

- **zedboot（必需）**：`git clone https://github.com/zouh9426/zedboot` 到临时目录，把其中的 `zedboot/` 子目录拷进技能目录（注意：仓库根不是 skill 本体，子目录才是），用完删除临时目录。
- **zedui（可选）**：如果我需要 UI 体系而你第 2 步没找到，告诉我并可按 https://github.com/zouh9426/zedui 的 SETUP 指引安装；不装也不影响管理体系与部署体系。
- 安装后再次按 `name:` 核实。

## 第 4 步：自检

依次运行（路径用第 2/3 步解析出的实际位置）：

1. 读 `<zedboot>/SKILL.md`，确认 frontmatter 可解析（有 `name:` 和 `description:`）。
2. `python3 <zedboot>/scripts/audit.py --help` —— 应输出用法说明；再对一个真实目录试跑一次，应输出结构化审计报告而非报错。

两项全过后，向我汇报：zedboot 的安装路径、zedui 检测结果、以及一句确认——"zedboot 安装完成，对你的项目说『用 zedboot 从零初始化这个项目』或『用 zedboot 改造这个旧项目』即可开始"。

---
