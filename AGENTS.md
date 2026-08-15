# AGENTS.md — zedboot 项目级规则

本文件约束**本仓库的维护者 agent**（迭代 zedboot skill 本身时的纪律）。`zedboot/SKILL.md` 约束的是**使用方 agent**（在用户项目里跑开局/改造工作流时的行为），两者别混。

## 仓库性质

- 公开开源仓库（GitHub: `zedboot`），MIT 协议，Copyright (c) 2026 zouh9426。
- 仓库内容：`zedboot/`（skill 本体：SKILL.md + references/ + assets/ + scripts/）、`tests/`（audit.py + verify.py + pre-push hook + deploy 模板测试，unittest，随 CI 运行）、双语文档（README / SETUP）、CHANGELOG、LICENSE、CI。
- 面向所有 AI 编码工具（Kimi Code / Claude Code / Codex 等），**不得偏向任何单一工具**：skill 内部不写死任何工具的安装路径，运行时按「环境探测」规则解析。

## 红线

1. **任何文件不得包含私人绝对路径**（`/Users/...`、个人 home 目录、本机特有配置）、真实服务器 IP/域名、个人账号信息。路径一律用 `~/` 相对表达或 `<项目名>` 风格占位符。
2. 提交前必须跑：`grep -rnE '/Users/[a-zA-Z0-9_-]+/' . --exclude-dir=.git`，有输出就不许 commit（该模式只匹配真实路径，不会误伤规则自身的描述文字）。CI（`.github/workflows/no-private-paths.yml`）会在 push 时兜底检查，红了必须修。
3. **零秘密**：密钥、密码、token 永不入库；模板与文档只登记"位置与引用"。
4. **依赖声明不编造**：引用第三方 skill/库必须查证上游地址；查不到就如实写"请自行获取"。
5. 不留垃圾文件：交接文档、测试产物等用完即删，不进仓库。
6. **实测依据一律匿名化**：CHANGELOG / commit message / Release notes / 文档中引用实战项目时，禁止出现用户项目名、内部任务编号、项目内路径等可识别信息——一律写"某生产项目"这类通用表述。公开仓库里，可识别信息与隐私同罪；已发生泄漏时连 git 历史一起改写清除。

## 迭代纪律（每次改动都要做到）

1. **改代码必写 CHANGELOG.md**：条目回答两个问题——改了什么、为什么这么改（决策理由）。
2. **改完同步 GitHub**：commit + push；每个正式版本打 tag 并建 GitHub Release，历史版本快照永不删除。
3. **双语文档同步**：README.md ↔ README.en.md、SETUP.md ↔ SETUP.en.md，改了一边另一边必须在同一次迭代里跟上。中文是主门面，英文版跟随。
4. **规范一致性**：`references/` 两份管理规范版本号必须一致，强制规则以精简版为准；`assets/` 模板改动后，检查 `SKILL.md` 的文件索引与流程描述是否仍然成立。
5. **工作流改动要克制**：SKILL.md 的两条工作流经过多场景实测，改动需在 CHANGELOG 里写明实测依据，不凭感觉改。
6. **收尾自检**：每次迭代收尾按项目模板同款五维自检执行（安全红线 grep / 交叉引用一致性 / 失效残留清理 / 脚本 `bash -n` 与 audit.py、verify.py 冒烟 / `python3 -m unittest discover -s tests` / CHANGELOG 同步），修复后复跑机械检查 + 纵览完整 diff；发版本前加查：README 双语同步、references 两份规范版本号一致、CI 绿。
7. **zedback 联动纪律**：涉及开局/改造/部署流程的改动，必须保持两条契约成立——①项目路径以追加式（幂等）写进 zedback 中央登记簿 `~/Documents/Backups/projects.index`，绝不覆盖重写；②首次部署流程必须同步更新项目 `docs/private/backup-manifest.conf`（ZB_DEPLOYED=true + 服务器字段）。破坏任一契约即视为流程缺陷，需在同次改动中修复。
