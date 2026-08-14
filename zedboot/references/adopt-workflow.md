# 工作流 adopt 细则：旧项目改造（zedboot）

> 本文件由 SKILL.md 指向，执行到对应步骤时阅读。与 init 复用第 1~4 步（见 `init-workflow.md`），但前置审计头部，且所有安装动作改为幂等。

## A. 审计（只读）

- 跑 `python3 <skill路径>/scripts/audit.py <项目路径>` 拿机械探测报告；报告中标注 `unknown` 的项由你亲自补查。
- 补查 AI 判断项：现有文档质量、现有结构与框架的匹配度、根目录卫生、有无"服务器上手工改代码"的痕迹、`.env` 是否已被 git 跟踪（安全风险，发现即醒目提示）、入库文件是否含运维真实值（公网 IP / 本机绝对路径 / 私钥格式，audit.py 已机械探测，命中即列入风险项，改造方案中给出"移入 docs/private/ops.md + 历史清理评估"的处置）。
- 产出《审计报告》（模板：`assets/checklists/audit-report.md.tmpl`）：现状清单 + 三体系各自差距 + 风险项。**报告落盘到目标项目 `docs/project/AUDIT_REPORT.md`**（docs/project/ 此时可先行创建）。

## B. 出改造方案（硬性卡点）

- 用 `assets/checklists/adoption-plan.md.tmpl` 出方案：每个差距项给处置——**新建 / 合并（旧内容搬进新结构）/ 归档（进 `archive/`）/ 不动**。**方案落盘到目标项目 `docs/project/ADOPTION_PLAN.md`**，与审计报告一起作为改造任务的正式记录（改造完成验收后保留在 docs/project/，不归档）。
- 冲突逐条列出让用户裁决，例如：旧 README 内容如何并入新模板；已有异构部署（CI 推送、服务器拉 git）是否迁移到 rsync 体系。
- **用户批准后才动手**。方案本身登记为改造任务进 TODO；重大改动预判决议编号。
- 若旧项目没有 Git 或在 main 上裸奔开发：把"建 Git / 建分支纪律"列为方案的可选档，由用户选择，不强制执行。

## C. 幂等安装

每个动作都是"检查 → 存在则合并或跳过 → 不存在则创建"，所以 adopt 跑两遍不出事，也允许分次改造（这次只装管理体系，下次再装部署）：

- 缺的补：走 init 同款模板（见 `init-workflow.md`）。
- 有的合：旧 README/TODO 的有效内容搬进新结构，旧文件归档进 `archive/`，索引记录替代关系。
- 管理规范副本的版本对齐：`docs/project/PROJECT_RULES.md` 用 `references/project-rules-compact.md` 全文重拷对齐到当前版（项目本地增补需保留时提示人工合并）；若项目同时随装了完整参考版（`docs/reference/PROJECT_RULES_REFERENCE.md`），必须同步用 `references/project-rules-reference.md` 重拷——两份副本的版本号与署名保持一致，只更新精简版会留下旧版残留。顺带 grep 项目入库文件中的本 Skill 历史名称（旧名 ZeroWeave），命中即更新为当前名。
- 部署体系：已有 Docker 但缺纪律 → 只补账号/rsync/备份与文档；已有全套异构部署 → 按 B 的用户裁决执行（迁移 or 仅文档对齐）；同时补生成 `docs/private/backup-manifest.conf`（已存在则跳过）。
- UI：无 DESIGN.md → 自检 zedui 后调起其 Phase 0；有 DESIGN.md → 只登记不重定。
- pre-push 隐私闸门（项目已启用 Git 时）：`.git/hooks/pre-push` 不存在则用 `assets/hooks/pre-push.tmpl` 安装（复制后 `chmod +x`，安装时把模板顶部的 `<项目名>` 替换为项目名（未替换时闸门自动降级））；服务器账号无需安装时配置（运行时读 `docs/private/ops.md`，见 `info-collection.md` 存储纪律三事实分离）；已存在则跳过并提示人工合并；装完按 init 第 1 步同款探测 `core.hooksPath`，非空且无法确认全局钩子会链式调用项目级钩子时，醒目警告用户并记入 PROJECT_STATE（同样用 `~/…` 相对表达，不写本机绝对路径）。
- 已被 git 跟踪的 `.env` 等敏感文件（audit §3 会报）：`git rm --cached <文件>` 解除跟踪 + 确认 `.gitignore` 覆盖——`.gitignore` 不会解除已跟踪文件；并提醒用户：历史提交里仍有残留，彻底清理需历史重写（口径见 `info-collection.md`「转 Public 前置」），已泄露的密钥应同时轮换。
- zedback 中央登记簿：同 init 第 4 步，把项目绝对路径追加进 `~/Documents/Backups/projects.index`（幂等）。
- **绝不改动业务代码逻辑**；改造只动管理层、部署层、文档层。

## D. 对齐收尾

- 跑 `scripts/verify.py <项目路径>` 做装后机械校验，FAIL 项修复后再往下走（同 init 第 4 步）。
- DECISION_LOG 写一条"体系改造"决议：审计结论 + 处置 + 用户裁决记录。若该项目此前在无规范状态下运行，决议中补一段**前因说明**（改造前的工作方式、为何改造、自何版本起生效）。
- PROJECT_STATE 初始内容**从审计结果回填**（真实状态，不是空白模板）。
- 核对三体系交界面三个文件（同 init 第 4 步），输出项目识别摘要请用户确认。
- 效果对齐"一开始就装好"：入口文件、五件套、索引、归档关系全部就位。
