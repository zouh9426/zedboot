# ZeroWeave 安装引导提示词

[English](SETUP.en.md)

把下面分隔线以内的内容贴给你的 AI（Kimi Code / Claude Code / Codex 等），它会完成全套安装与自检。

---

请帮我安装 ZeroWeave skill（项目开局编排器）。步骤：

1. 检查我的 skills 目录存在哪个：`~/.kimi-code/skills/`、`~/.agents/skills/`、当前项目的 `.kimi-code/skills/` 或 `.agents/skills/`。都没有就创建 `~/.agents/skills/`（多工具共享）。
2. 把 ZeroWeave 装进去：`git clone https://github.com/zouh9426/zeroweave <选中目录>/zeroweave`；如果我给的是 zip/本地目录，就复制过去，确保 `zeroweave/SKILL.md` 存在。
3. 可选依赖检测：在同样候选位置查找 `uiweft/SKILL.md`。找到就告诉我路径；没找到就告诉我"UI 支线不可用，可稍后安装 uiweft（https://github.com/zouh9426/uiweft），不影响管理体系与部署体系"。
4. 自检：
   - 读 `zeroweave/SKILL.md`，确认能解析 frontmatter（name/description 存在）；
   - 跑 `python3 zeroweave/scripts/audit.py --help`（或对一个目录试跑），确认审计工具可用；
   - 报告：安装位置、uiweft 检测结果、自检结论。
5. 告诉我怎么触发：新开个 AI 会话，说"用 ZeroWeave 从零初始化这个项目"或"用 ZeroWeave 改造这个旧项目"。

每步失败就停下来报告，不要乱试。

---
