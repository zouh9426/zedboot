# AGENTS.md（ZeroWeave 仓库维护规则）

本文件约束 ZeroWeave skill 本体的迭代维护。注意区分：`assets/project/AGENTS.md.tmpl` 是装进用户项目的模板，本文件是本仓库自己的规则。

## 红线

- **无私有路径**：任何文件不得包含个人绝对路径（`/Users/<名>/` 等）、个人账号信息、真实服务器 IP/域名。路径一律用 `~/` 相对表达或占位符 `<项目名>` 风格。CI（`.github/workflows/no-private-paths.yml`）会在 push 时硬检查。
- **零秘密**：密钥、密码、token 永不入库；模板与文档只登记"位置与引用"。
- **依赖声明不编造**：引用第三方 skill/库必须查证上游地址；查不到就如实写"请自行获取"。

## 迭代纪律

- 每次迭代：commit 说明写清"改了什么 + 为什么"；用户可见变化同步 `CHANGELOG.md`。
- **双语文档同步**：改 `README.md` 必同步 `README.en.md`；`SETUP.md` 与 `SETUP.en.md` 同理。
- `references/` 两份管理规范的版本号必须一致；强制规则以精简版为准，参考版不得覆盖。
- 模板（`assets/`）改动后，检查 `SKILL.md` 的文件索引与流程描述是否仍然成立。

## 发版

- 语义化版本；发布 = commit + push + CHANGELOG 条目 + 打 tag + GitHub Release（写清变更摘要与安装入口）。
- 测试产物、交接文档等临时文件不进仓库，用完即删。
