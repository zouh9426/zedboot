# CHANGELOG

分类标题使用英文（Added / Changed / Fixed / Removed / Security），具体内容使用中文。

## [v0.2.0] - 2026-08-07

开源首发。

### Added

- 新增开源必需文件：`LICENSE`（MIT）、`README.md` + `README.en.md`、`SETUP.md` + `SETUP.en.md`（安装引导提示词）、仓库级 `AGENTS.md`（维护规则）、`.github/workflows/no-private-paths.yml`（push 时检查私人路径的 CI）
- README 声明可选依赖 uiweft 的上游地址（已用 `gh repo view` 查证）

### 决策理由

- 选 MIT：文档/脚本类项目，"保留版权声明"即满足署名需求，Apache-2.0 的专利授权条款对此类项目意义有限
- 双语 README：规范内容是中文，目标用户中文为主；英文版降低国际用户门槛
- CI 检查正则用 `/Users/[a-zA-Z0-9_-]+/` 只匹配真实路径，避免误伤规则文件中的描述文字

## [v0.1.0] - 2026-08-07

基线快照（历史留档，不建议新用户使用）。

### Added

- 三体系编排核心 `SKILL.md`：init（从零创建）/ adopt（旧项目改造）两条工作流，六组信息采集 + 待定机制，幂等安装，秘密边界纪律
- 项目管理规范 v1.4 双文件（精简执行版 + 完整参考版）：修正发布流程 Tag 时机冲突、明确 Git push 与发布绑定、根目录白名单纳入部署文件
- 部署规范拆分：栈无关 guide + 四栈模板（Next.js / Python / Go / 静态站）+ 通用件（compose / backup / rsync / dockerignore）
- 项目文件模板 9 个 + Checklist/报告模板 3 个
- `scripts/audit.py`：旧项目只读审计（纯标准库，探测不到标 unknown 交 AI 判断）
- 五个场景实测（3 init + 2 adopt）通过，修复 8 处实测发现的问题
