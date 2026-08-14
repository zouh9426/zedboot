# 工作流 init 细则：从零创建（zedboot）

> 本文件由 SKILL.md 指向，执行到对应步骤时阅读。前置：依赖自检（SKILL.md）+ Phase 0 信息采集（`info-collection.md`）。

```text
0. 依赖自检 + 信息采集
1. 装管理体系（所有模式）
2. 装部署体系（可部署/混合）
3. 装 UI 体系（有界面）
4. 收口闭环
```

## 1. 装管理体系

- 用 `assets/project/` 模板生成：`README.md`、`AGENTS.md`、`CHANGELOG.md`、`docs/README.md`、`docs/project/` 五件套（PROJECT_RULES 见下、PROJECT_INDEX、PROJECT_STATE、TODO、DECISION_LOG）、`archive/README.md`；模板头部的安装说明注释（"本文件是…模板"类）与注释包裹的示例条目（如 DECISION_LOG 的示例决议）落盘时一律删除。
- **PROJECT_RULES.md = 复制 `references/project-rules-compact.md` 全文**进 `docs/project/PROJECT_RULES.md`（AI 日常读项目内的副本，不读 Skill）。
- 完整参考版（`references/project-rules-reference.md`）默认**不复制进项目**；此时 AGENTS.md 里"完整参考版位置"一行注明"未随项目安装，见 zedboot skill 的 references/ 目录"。用户明确要求随项目安装时，复制到 `docs/reference/PROJECT_RULES_REFERENCE.md` 并改写该行。
- 项目模式写入 PROJECT_INDEX 与 PROJECT_STATE；项目代码确定后，TODO 第一个任务 = 本项目的上线 Checklist（可部署项目）或第一个真实任务。
- 只创建当前实际需要的目录，不机械全建（管理规范 §4 自适应目录规则）。
- **Git 与隐私防线（所有启用 Git 的项目；可部署/混合默认启用，无部署项目按 Phase 0.B 的选择）**：初始化本地仓库 + `main` 分支 + 首次 commit，按 Phase 0.B 关联私有远程（**此时不 push**——push 随首次发布进行）；`.gitignore` 必须含 `.env*`（附 `!.env.example` / `!.env.sample` / `!.env.template` 例外行，保证模板文件可入库）、`data/`、`backups/`、`docs/private/`；安装 pre-push 隐私闸门（`assets/hooks/pre-push.tmpl` 复制为 `.git/hooks/pre-push` 并 `chmod +x`，**安装时把模板顶部的 `<项目名>` 替换为项目名**（未替换时闸门自动降级，仅放行目录名派生路径）；**服务器账号无需安装时配置**——闸门运行时读取 `docs/private/deploy.env` 的 `DEPLOY_USER`（`ops.md`「机器可读字段」为旧项目 fallback；三事实分离，见 `info-collection.md` 存储纪律）；已存在则不覆盖，提示人工合并；`.git/hooks` 不随 clone 携带，新机器/重新克隆后重跑本步骤重装）；装完探测 `git config core.hooksPath`——非空时 `.git/hooks` 会被整体忽略，须确认该 hooksPath 下的全局钩子会链式调用项目级钩子，无法确认则醒目警告用户并把结论记入 PROJECT_STATE（结论用 `~/…` 相对表达，不写本机绝对路径——入库文件纪律））。

## 2. 装部署体系（可部署/混合项目）

- 按技术栈选 `assets/deploy/` 模板落盘根目录（幂等：已存在的文件跳过不覆盖，防回滚人工修改；需更新时提示人工合并）：Dockerfile（nextjs/python/go 之一；不在库中按 `references/deployment-guide.md` §3 设计点现场编写。Go 栈：先检测项目实际 main package（如 `cmd/server`），与 Dockerfile 的 `GO_MAIN_PACKAGE` ARG 对齐——默认 `./cmd/server`，单 main package 项目用 `--build-arg GO_MAIN_PACKAGE=.` 覆盖）、`docker-compose.yml`、`docker-entrypoint.sh`（nextjs/python 栈；go 栈 ENTRYPOINT 烤进镜像、无此文件）、`backup.sh`、`deploy-rsync.sh`、`.dockerignore`（`dockerignore.tmpl`，**不可省**——防止 `COPY . .` 把 `.env*`/`data/` 拷进镜像）。
  - 静态站点：无应用容器，按 `assets/deploy/static/README.md`——本地构建、rsync 只推发布目录（`STATIC_OUTPUT_DIR`：Vite/Astro=`dist`、Next.js 静态导出=`out`、纯 HTML=`public`）、服务器共享 Caddy 直接伺服。**不装 backup.sh**（容器栈数据备份脚本；静态站无应用数据，其数据备份由 zedback 经 manifest 的 `ZB_PULLS` 拉取站点产物目录（如 `dist/`）承担，见 `assets/project/backup-manifest.conf.tmpl` 注释）。
  - 脚本落盘后统一 `chmod +x`（执行位兜底，防模板来源或拷贝方式丢位）：`docker-entrypoint.sh`（nextjs/python 栈；go 栈无此文件，跳过）、`backup.sh`、`deploy-rsync.sh`（静态站点为 `deploy-rsync-static.sh`）。
- 生成 `docs/guides/deployment.md`（容器栈用 `assets/deploy/deployment.md.tmpl`，静态站点用 `assets/deploy/deployment-static.md.tmpl`；入库文件只写占位符，真实运维值按下条入 ops.md）。
- 生成 `docs/private/ops.md`（用 `assets/project/ops.md.tmpl`，填入 Phase 0 采集的真实运维值；其中 `deploy.env` 的 `DEPLOY_USER` 是 pre-push 闸门与 audit.py 运行时放行的机器真源（旧项目无 deploy.env 时回退 `ops.md`「机器可读字段」节的「服务器账号」行），见 `info-collection.md` 存储纪律三事实分离），并提醒用户：ops.md 不进 Git、无版本备份，需配独立私有备份通道（如私有 ops-notes 仓库）。
- 生成 `docs/private/deploy.env`（模板 `assets/project/deploy.env.tmpl`：部署六事实 `PROJECT_NAME`/`DEPLOY_USER`/`REMOTE_DIR`/`SERVER_IP`/`DEPLOY_KEY`/`SSH_PORT` 由该文件显式提供，脚本不从本地路径推导——三事实分离的落地载体；同属 `.gitignore` 排除，私有不入库）。
- 生成 `docs/private/backup-manifest.conf`（模板 `assets/project/backup-manifest.conf.tmpl`）：zedback 每日备份按它拉取服务器数据，字段含义见模板注释；无部署项目不生成；**首次部署完成后必须更新该清单**：`ZB_DEPLOYED` 翻为 true 并填实 `ZB_SSH_TARGET`/`ZB_SSH_KEY`/`ZB_SERVER_DIR`/`ZB_PULLS`（键名以模板注释为准，一律 ZB_ 前缀；部署动作与改卡是同一流程的一部分）。
- 上线 Checklist（`assets/checklists/go-live-checklist.md`）登记为 TODO 任务；静态站点先按文件内「静态站点（无容器）替代说明」区块裁剪再登记，剔除永远完不成的 Docker 条目。
- `.env.example` 只写键名入库；`.env` 永不入库（`.gitignore` 纪律见第 1 步的 Git 条目）。

## 3. 装 UI 体系（项目有界面时）

- 调起自检通过的 zedui，进入它的 Phase 0（提问 → UUPM 出方案 → 用户确认 → 生成 DESIGN.md）。zedboot 不碰 UI 内容本身。
- 完成后三件事：确认 `DESIGN.md` 落盘在项目根；登记进 PROJECT_INDEX；AGENTS.md 的"UI 规范"行就位（模板已带，确认内容语言一致）。
- 若用户选择把 UI Phase 0 延后（不在 init 当场做）：登记 TODO 任务，AGENTS.md 的"UI 规范"行保留但注明"DESIGN.md 尚未生成，见 <任务编号>"，INDEX 的「图片与设计」表状态写"待生成"。

## 4. 收口闭环

- 跑 `python3 <skill路径>/scripts/verify.py <项目路径>` 做装后机械校验（文件齐备、占位符替换干净、`.env*` 未跟踪、闸门就位等），FAIL 项修复后再往下走。
- 登记进 zedback 中央登记簿：把项目绝对路径追加一行到 `~/Documents/Backups/projects.index`（文件不存在则创建；路径已在簿中则跳过，幂等；**追加，绝不覆盖重写**）。无 zedback 环境（该文件体系不存在且用户未使用 zedback）时跳过此步。
- 三体系交界面只有三个文件，逐一核对：`AGENTS.md`（引用 PROJECT_RULES、DESIGN.md、deployment.md）、`PROJECT_INDEX.md`（外部资源表填好：GitHub 仓库/服务器/域名/端口/备份）、`TODO.md`（初始任务建好）。
- 向用户输出**项目识别摘要**（管理规范 §7.1 的第一次实践），请用户确认。
- 全部信息一次要齐、一次落盘；之后本 Skill 退场。
