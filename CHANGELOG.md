# CHANGELOG

本项目所有值得记录的变更都写在这里。格式约定：每条目回答两个问题——**改了什么**、**为什么这么改（决策理由）**。

## [0.6.1] - 2026-08-14

外部复检驱动的 verify.py 覆盖缺口修复 + 回归测试补齐。

- **verify.py 扫描范围扩为「已跟踪 + 未跟踪但未被忽略」**：此前只扫 `git ls-files` 的已跟踪文件，未跟踪文件仅计数不扫描；但 zedboot 流程里 verify 跑在装后 commit 之前（init 第 1 步首次 commit，第 2/3 步才落盘部署文件，第 4 步 verify），新落盘的 Dockerfile/deployment.md 等若尚未 add 就恰好漏出占位符与私钥扫描。改为 `git ls-files -co --exclude-standard`（下次 commit 会进去的全部文件），命令失败回退仅扫已跟踪并注明，不臆断。理由：外部复检指出的真实路径漏洞——0.6.0 自测能抓到漏填是因为每步都 commit 了，不换路径就漏。
- **.gitignore 校验从一项扩为四项 + docs/private 跟踪检查**：此前只验证 `.env` 条目，现在 `.env`/`data`/`backups`/`docs/private` 逐项 PASS/FAIL（gitignore 语义匹配：无斜杠模式匹配任意层级、含斜杠锚定根）；新增 `docs/private/` 被 git 跟踪即 FAIL（ops.md / backup-manifest.conf 含服务器 IP 与账号，是整个隐私隔离体系的核心，跟踪即泄露事故）。理由：规则写了四项、verifier 只验一项——校验器必须覆盖规则全文。
- **新增 `tests/test_verify.py`**：verify.py 的回归测试（动态 fixture：装全容器栈 PASS、缺文件 FAIL、已提交/未跟踪占位符 FAIL、被忽略文件不误伤、gitignore 缺项 FAIL、.env 与 docs/private 被跟踪 FAIL、闸门缺失/不可执行 FAIL、core.hooksPath WARN、静态站与 go 栈分支、无部署 SKIP、--json 合法性、只读性快照），把本轮两个修复钉成 regression test。理由：verify.py 已是核心验收程序，不能自身零测试。
- **frontmatter 增加 `compatibility` 字段**（Agent Skills 规范可选字段）：声明 Python 3.8+ / Git 必需，部署工作流假定 Unix-like shell + SSH/rsync/Docker，UI 支线可选依赖 zedui；tests.yml 步骤名同步为双脚本套件。理由：「工具无关」指 Agent client 无关，运行环境要求应如实声明。

## [0.6.0] - 2026-08-14

外部工程化审核驱动的集中升级：秘密边界补对话上下文层、SKILL.md 回归控制器形态、装后校验程序化、测试资产入库。工作流语义不变（逐字搬迁 + 指针替换），无流程改动。

- **秘密边界扩展到对话上下文**：Phase 0.E 改为「只向用户问键名，绝不让用户把 key 值贴进对话」，现场生成的密钥用命令直接写入 `.env` 不回显；存储纪律第 3 条与硬性规则第 3 条同步补「秘密本体不进对话上下文」；README 双语同步。理由：外部审核发现原隐私线只防「入库」不防「进聊天上下文」——用户按旧指引把第三方 key 贴进对话即进入模型上下文与会话历史，泄露面多一层且无法收回。
- **description 触发范围收紧**：英文触发尾句由「starting a new project from scratch」改为「用户明确要求用 zedboot 初始化/改造」并加反向约束（用户只是要开个新编码项目时不触发）。理由：description 是 Agent 自动选 Skill 的主要依据，原措辞会在「帮我做个 Todo App」这类场景泛触发一个会写十几个文件、建仓库的重型 Skill。
- **SKILL.md 瘦身，回归控制器形态**（23394 B → 8669 B）：Phase 0 采集细则、init/adopt 两 workflow 的逐步细则逐字迁出至 `references/info-collection.md`、`references/init-workflow.md`、`references/adopt-workflow.md`（仅交叉引用改写为文件名指针，规则文字零改动）；SKILL.md 保留模式判断、环境探测、依赖自检、六组信息概要与三条红线、workflow 骨架、硬性规则、文件索引，并注明「执行到哪步读哪份」。理由：Agent Skills 规范建议控制器约 5000 tokens 内、细节渐进式披露；审核指出 SKILL.md 塞了过多实现细节。附带收益：装后校验接入点（下条）在控制器与细则中各出现一次，层级清晰。
- **新增 `scripts/verify.py` 装后机械校验**（纯标准库、绝对只读、--json、git 命令带超时、无法确认一律 WARN/SKIP 不臆断，与 audit.py 同口径）：管理文件齐备、中文占位符残留、`.gitignore` 含 `.env` 且 `.env` 未被跟踪、pre-push 闸门就位（含 core.hooksPath 探测）、按项目模式校验部署产物、入库文件私钥头快扫，任何 FAIL 即 exit 1；init 第 4 步与 adopt D 步接入为收口动作。理由：安装正确性此前只有提示词级保证（instruction-level idempotence ≠ actual idempotence），装后机械校验用约两成工程量拿到确定性验收的大头收益；自测两个假项目（装全 / 缺漏坏）exit 0/1 与逐项报告均符合预期。
- **audit.py fixture 测试矩阵重建并入库**：0.5.7 声称的「10 项 fixture 测试矩阵」从未提交、测试资产丢失；现重建为 `tests/`（6 静态 fixture + 4 动态 fixture，27 个 unittest 用例：跑通/JSON 合法/只读性快照对比/探测正确性抽查），新增 CI `tests.yml`（push/PR 触发，Python 3.8–3.12 矩阵）。fixture 的隐私测试值（私钥头、.env、本机路径）全部运行时拼接/动态构造，不入库字面量，与全局 pre-push 隐私闸门兼容。理由：Skill 复杂度早已超过「零测试」能兜住的水平；fixture 不入库等于每次改动都靠回忆回归。
- **装进项目的 AGENTS.md 模板改分层阅读**：原「强制阅读顺序」6 份文件（约 24 KB 固定开销）改为「每次任务必读小文件（AGENTS/STATE/TODO/任务引用，约 6 KB）+ 按触发读大部头（PROJECT_RULES 流程裁决与同步时、INDEX 定位资源时、deployment.md 部署时、DESIGN.md UI 时等）」；README 双语「不增加日常 token 负担」改为如实的分层加载口径。理由：审核指出原表述与强制阅读清单的实际 context 成本矛盾，名不副实。
- **装前自检（0.6.0 发布前第一遍复查）四处修复**：①管理规范两份文件的阅读口径同步为分层加载——compact §0.1 旧口径「按 AGENTS 顺序读 README/规则/索引/状态/TODO」与新模板直接冲突且会随安装拷进每个项目（compact §11.3 本就是新口径，§0.1 属没删干净的旧残留），reference §1.1 与 §5.2 推荐模板同步；②go 栈 entrypoint 三向对齐——go 栈 ENTRYPOINT 烤进镜像、无 docker-entrypoint.sh，init 落盘清单与 chmod 清单注明适用范围、SKILL.md 文件索引措辞修正、verify.py 改为「Dockerfile 引用 docker-entrypoint 才必查」（缺失但 Dockerfile 自含 ENTRYPOINT 判 PASS）；③audit.py docstring 过期指针「SKILL.md 存储纪律」改指 references/info-collection.md；④tests/fixtures 的 .DS_Store 加 .gitignore 例外（防索引重建后 CI 静默翻车）。理由：发布前模拟安装走查发现的真冲突与三向不一致，同步修复避免把矛盾装进新项目。
- **发布前第二遍端到端模拟验证（沙盒项目实测）一处修复**：`backup.sh.tmpl` 头部注释的 crontab 示例行用了中文占位符（`<分> <时> <项目目录>`），照流程安装的项目会被自己的 verify.py 判占位符残留 FAIL——模板与校验器自相矛盾，示例行已改为英文隔离占位符（`<MIN> <HOUR> <PROJECT_DIR>`，与存储纪律的占位符命名约定一致）。模拟本身结论：init 全流程（管理体系 + python 栈部署体系 + 闸门安装）跑通，verify.py 拦下两处安装漏填（deployment.md 的 `<仓库地址>`/`<DNS托管商>`）并指引修复后全 PASS；pre-push 闸门功能实测——私钥头/本机路径/公网 IP 推送均拦截、干净提交与 RFC 5737 文档段 IP 放行，且在全局 `core.hooksPath` 机器上经全局钩子链式调用实际生效（verify.py 对该场景正确 WARN 提示人工确认）；adopt 全流程跑通——audit.py 正确检出 .env 被跟踪与入库公网 IP，幂等安装后管理文档 1/10 → 10/10、verify 全 PASS；幂等重跑零意外 diff。

## [0.5.11] - 2026-08-12

隐私闸门两项放行机制修正（某生产项目发布实测驱动）。

- **隐私闸门三事实分离改造**：放行口径由「仓库目录名 + 项目名」两来源扩为三来源——第三个独立事实「服务器账号」登记在 `docs/private/ops.md` 新增的「机器可读字段」节（`- 服务器账号: <值>` 单行，键后中/英文冒号均可），pre-push 闸门运行时读取并加入 `/home/<账号>/` 放行集合（ops.md 缺失时静默降级），audit.py 的 home_allow 同步纳入该来源，解析口径与闸门一致；ops.md.tmpl 补机器可读字段说明，SKILL.md 存储纪律补「三事实分离」约定并在 init/adopt 两处安装步骤注明「账号无需安装时配置」。理由：2026-08-12 某生产项目实测——仓库目录名与服务器账号不一致（大小写与命名均不同），合法运维路径（如 /home/<账号>/ 下的 systemd 单元）因账号无处机器可读，每次发布被自家闸门拦截、只能 --no-verify；账号是独立事实，须在专用隐私文件记录一次、闸门与审计各自读取。
- **新引用推送只扫"远程还没有的提交"**：此前推新 tag（remote_sha 全零）一律全历史扫描，历史中含闸门启用前遗留值的仓库每次发版推 tag 都会被自家闸门拦；现改为远程已有引用时按 `git rev-list <sha> --not --remotes` 取增量（远程全空的真·首次推送仍全历史扫描）。理由：全历史重复拦截让闸门形同虚设（每次都得 --no-verify），增量语义与全局 privacy-gate 既有实现一致。

## [0.5.10] - 2026-08-12

全量审计（模板逐件核对 + audit.py 冒烟实测）后的集中修复。

- **「十项管理文档」口径对齐**：`audit.py` 的 `CORE_MANAGEMENT_DOCS` 此前误含 `DESIGN.md`、漏 `archive/README.md`，与管理规范正典（audit-report 模板与 project-rules-compact §16）错位，adopt 审计的 N/10 计数会与报告模板对不上；已改为正典十项，DESIGN.md 保留在 UI 节单独检查。理由：同一事实两套口径是 0.5.7 口径对齐工作的遗漏，审计输出必须与管理规范逐字一致。
- **部署模板镜像升 EOL 版本**：Next.js 模板 `node:20-alpine` → `node:22-alpine`（Node 20 已 EOL，22 LTS 支持至 2027-04）；Go 模板 `golang:1.22-alpine` → `golang:1.24-alpine`。理由：用停止安全修复的基础镜像开局等于自带漏洞出生。
- **文档与注释修正**：CHANGELOG 0.5.9 条目中悬空版本号 0.3.4 改写为 0.3.x（仓库无此版本）；pre-push 与 audit.py 三处"口径一致"注释改为如实描述（hook 正则要求尾部斜杠、匹配范围比 audit.py 窄，属宁漏勿滥的刻意设计）；AGENTS.md 真源纪律节标题去掉"不进任何仓库文件"的自相矛盾表述；`.gitignore` 补 `__pycache__/`、`*.pyc`。理由：夸大或悬空的表述会在下一次对齐工作中再次误导。
- **SKILL.md backup-manifest 键名对齐**：部署流程指令中的 `DEPLOYED/SSH_TARGET/SERVER_PULLS` 等简写改为模板真实键名（`ZB_DEPLOYED`/`ZB_SSH_TARGET`/`ZB_PULLS` 等，ZB_ 前缀），并注明以模板注释为准。理由：实测核对发现照简写实现会写出无前缀/错名键（`SERVER_PULLS` 并不存在），zedback 消费端会静默读不到。

以下 4 项为 2026-08-12 模拟项目开局/改造链路实测暴露的协作摩擦点：

- **静态站 backup.sh 归属矛盾双修**：SKILL.md 部署落盘清单注明静态站不装 backup.sh（容器栈数据备份脚本，静态站的数据备份由 zedback 经 manifest 的 `ZB_PULLS` 拉取 `dist/` 承担）；`backup.sh.tmpl` 加 data/ 存在性守卫——无 data/ 时日志说明并 exit 0，不产残缺包。理由：实测静态站跑 backup.sh 因 tar 找不到 data/ 直接 exit=1，与静态站部署文档「无数据备份步骤」自相矛盾；守卫让误装也无害。
- **隐私闸门放行口径与「按项目名填实」对齐**：pre-push 闸门新增 `PROJECT_NAME="<项目名>"` 占位（未替换自动降级为空），放行逻辑同时允许 `/home/<目录名>/` 与 `/home/<项目名>/`（非空时）；audit.py 的 home_allow 改为放行集合，在目录名基础上把项目根 AGENTS.md「项目名称」行的值（中/英文冒号均可）一并纳入；SKILL.md init/adopt 两处 pre-push 安装步骤补「安装时替换 `<项目名>`」。理由：SKILL.md 要求可推导字段（账号 = 项目名）当场填实，但目录名≠项目名时合法的 `/home/<项目名>/` 被自家闸门拦截——实测模拟（目录名≠项目名）验证含 `/home/<项目名>/` 的推送放行、`/home/<其他账号>/` 仍拦截，audit.py 对含该路径的入库文件不再报隐私。
- **静态部署脚本无构建适配**：`deploy-rsync-static.sh.tmpl` 前置检查从「必须存在 dist/」改为形态适配——有 dist/ 推 dist/（构建型），无 dist/ 推站点根网页文件（index.html 与 css/ 等，无构建型），模板注释写明两种形态。理由：实测发现无构建纯静态站没有 dist/，硬性前置检查使部署第一步即断。
- **backup-manifest 模板补静态站说明**：`backup-manifest.conf.tmpl` 注释注明静态站改 `ZB_PULLS="dist/"`（或站点产物目录），容器栈保持默认 `data/ backups/ .env`。理由：默认值面向容器栈，静态站无 data/.env，照抄会导致服务器数据拉取清单为空。

## [0.5.9] - 2026-08-11

- **维护纪律修正：实测依据匿名化**。此前 0.3.x/0.5.8 等早期版本的 CHANGELOG、commit message、Release notes 在"实测依据"中含用户项目可识别信息（项目名/内部任务编号/项目内路径），已连 git 历史一起改写清除（rebase + force push + Release notes 修订）；AGENTS.md 红线新增第 6 条把匿名化固化为维护规则。理由：公开仓库里可识别信息与隐私同罪，仅靠"不含密钥"的标准不够。

## [0.5.8] - 2026-08-11

adopt 实战（某生产项目第二轮改造验收）暴露的残留缺口修复。

- **adopt 幂等安装补"管理规范副本版本对齐"条目**：`PROJECT_RULES.md` 重拷精简版对齐当前版；项目随装了完整参考版（`docs/reference/PROJECT_RULES_REFERENCE.md`）时必须同步重拷，两份副本版本号与署名保持一致；并 grep 项目入库文件中的本 Skill 历史名称（旧名 ZeroWeave）命中即改。理由：某生产项目第二轮 adopt 实测——精简版署名已对齐 zedboot，参考版仍残留"由 ZeroWeave skill 分发"（第一轮改名前安装的副本，adopt 流程只覆盖了精简版），旧署名将随每次 adopt 在每个改造项目里复发。

## [0.5.7] - 2026-08-11

双场景实战自查（init 模拟 + adopt 模拟各跑一遍完整流程）暴露的缺陷集中修复：脚本执行位、hooksPath 语义纠错、audit.py 误报治理与覆盖缺口、static 栈模板适配、契约默认值。

- **部署脚本执行位**：5 个 `.sh.tmpl` 加执行位（git 100644→100755），SKILL.md init 第 2 步补"脚本落盘后统一 `chmod +x`"指示。理由：实测按流程字面执行后 `./deploy-rsync-static.sh` 直接 Permission denied（模板 git mode 644，落盘即不可执行），部署流程第一步即断；chmod 步骤是防模板来源/拷贝方式丢位的兜底。
- **pre-push 闸门与 audit.py 的路径口径对齐**：闸门第 2 项检查改为逐条比对——`/home/<项目目录名>/`（= 可推导部署账号的服务器端路径）放行，与 audit.py 的 home_allow 口径一致；`/Users/` 与其他 `/home/<名>/` 照拦。理由：二轮回归实测干净 init 项目首次 push 被自己的闸门拦（deployment.md 落地后的 `/home/<项目名>/.ssh/` 假阳性）——上一轮只统一了 IP 口径，路径口径没跟上；拦错的闸门会被 `--no-verify` 绕过，形同虚设。
- **backup.sh SQLite 容错**：`.backup` 失败从"set -e 中止全备份 + 留 0 字节孤儿文件"改为告警继续（tar 打包是主备份）并清掉半成品；恒真的 `[ -n "${SQLITE_DB}" ]` 守卫一并去掉。理由：坏库/非 SQLite 同名文件会让每日备份静默全灭，孤儿文件永不进滚动保留。
- **audit.py 三处补丁**：§5 部署脚本探测排除文档扩展名（`deploy-notes.md` 不再虚增部署痕迹）；§9 管理文档降级匹配改小写口径（与 §4 的大小写不敏感检测一致，`Docs/Project/TODO.md` 变体不再漏降级）；repo 模式新增未跟踪文件数量提醒（防脏仓库含密草稿被 `git add` 直接扫进提交）。
- **adopt 流程补两个经典缺口**：① 已被 git 跟踪的 `.env` 处置——`git rm --cached` 解除跟踪 + 提醒历史残留需历史重写、密钥应轮换（`.gitignore` 不解除已跟踪文件，此前全流程走完泄露原样保留）；② hooksPath 探测结论记入 PROJECT_STATE 时强制 `~/…` 相对表达（原样写绝对路径既违反自己的入库纪律，又会触发本机全局隐私闸门拒推）。
- **部署文件幂等语义**：init 第 2 步明确"已存在的部署文件跳过不覆盖，需更新时提示人工合并"。理由：二轮回归实测幂等重跑把 compose 的人工端口修改静默回滚成模板默认值。
- **模板细节**：PROJECT_INDEX 域名行的组合占位符 `<域名，DNS 托管于 <服务商>>` 拆开（逐个替换后外层无法消解、必残留）；docs-README 模板第 2 行安装指示注释补"落盘时删除"。
- **hooksPath 静默失效纠错**：SKILL.md 改掉"全局 hooksPath 闸门与项目级钩子共存、互不覆盖"的错误结论——git 语义是 `core.hooksPath` 一旦设置就整体忽略 `.git/hooks`，本机成立纯属全局钩子显式链式调用的特例；init 第 1 步与 adopt 第 C 步新增 `core.hooksPath` 探测条目：非空且无法确认链式调用时醒目警告用户并记入 PROJECT_STATE。理由：非链式全局钩子的机器上隐私闸门"以为装了、实际没装"，且静默失效无任何报错。
- **audit.py 误报治理与覆盖缺口**（7 项）：① IP 排除清单与 `pre-push.tmpl` 对齐（补 0.0.0.0/8、169.254/16、RFC 5737 文档段、受限广播），消除两组件对同一 IP 结论相反的口径分叉；② 本机路径正则排除 `[` `]`，AGENTS.md 自检命令里的 `/Users/[a-zA-Z0-9_-]+/` 字符类不再误报；③ `/home/<项目目录名>` 按"账号=项目名"的可推导服务器路径放行（deployment.md 填实后不再必报）；④ zedboot 生成的管理文档（AGENTS/TODO/DECISION_LOG/PROJECT_INDEX/PROJECT_STATE/AUDIT_REPORT/ADOPTION_PLAN）命中降级单列、不计入风险结论——这些文档按工作流必须记录风险，其 IP/路径字样多为元描述；⑤ 非 git 项目从"§9 整体跳过"改为工作区降级扫描（跳过依赖/构建噪音目录，500 文件上限），补上改造前风险期的机械覆盖；⑥ 嵌套仓库边界校验：`show-toplevel` 与被审计根不符时按非仓库处理，git 节与 §9 不再被外层仓库污染；⑦ 超 2MB 文件的截断事实记入"未能探测"汇总，不再静默漏报。理由：adopt 模拟实测——改造后重跑审计 13 条命中里 9 条是自己产出的管理文档（该抓的抓不到：无 git 项目硬编码 IP 与 .env 零机械检出；不该抓的全被抓），信噪比崩坏。改动经 10 项 fixture 测试矩阵验证全绿（含只读性校验和对比、JSON 模式、嵌套仓库、截断提示）。
- **static 栈模板适配**：新增 `assets/deploy/deployment-static.md.tmpl`（无容器运维速查：构建→rsync 只推 dist→共享 Caddy 伺服），`go-live-checklist.md` 新增「静态站点（无容器）替代说明」区块（逐条映射 Docker 条目的剔除与替换），SKILL.md 的 deployment.md 生成与 Checklist 登记改为按栈路由。理由：init 模拟中 static 项目拿到一份全是 `docker compose` 命令的运维文档和永远完不成的 Docker 清单条目，与 static README 的部署方式直接矛盾。
- **zedback 契约默认值修正**：`backup-manifest.conf.tmpl` 的 `ZB_DEPLOYED` 默认改 `false` 并加醒目契约注释（翻 true 必须同时填实 SSH 字段）。理由：模板默认 true 与"首次部署完成后才翻 true"的流程自相矛盾，照抄会让未上线项目被 zedback 当作已部署、每日对占位符 SSH 目标拉取失败。
- **模板卫生**：DECISION_LOG 示例决议改用 HTML 注释包裹并标注"安装时删除"（对齐 TODO 模板惯例）；archive/docs README 模板头注释补"落盘时删除本注释"；deployment.md.tmpl 命令示例 `<DEPLOY_USER>@` 改 `<项目名>@`（账号=项目名是可推导值，不该用隔离值占位符）；SKILL.md 同步补"可推导占位符全文替换（含代码块内示例）"与"模板头注释/示例条目落盘时删除"两条指示。理由：字面复制即残留的虚构示例决议、元注释、漏替换占位符在两轮模拟中均实际出现。

## [0.5.6] - 2026-08-11

zedback 深度绑定：开局/改造登记进中央登记簿，首次部署绑定更新身份证。

- **中央登记簿**：init 收口与 adopt 安装新增一步——项目绝对路径追加进 `~/Documents/Backups/projects.index`（幂等，绝不覆盖）；**部署绑卡**：init 部署体系步骤与上线 Checklist 明确"首次部署后必须更新 backup-manifest.conf（DEPLOYED=true + 服务器字段）"；AGENTS.md 迭代纪律新增第 7 条把两条契约固化为维护规则。理由：zedback 已改为登记簿+身份证双件驱动（/opt 探测提醒机制废弃），登记与改卡必须由 zedboot 流程承担，否则服务器数据静默漏备。

## [0.5.5] - 2026-08-11

新增 zedback 联动：开局/改造时产出备份清单，服务器项目纳入每日备份零脚本改动。

- **备份清单模板**：新增 `assets/project/backup-manifest.conf.tmpl`，init 第 2 步与 adopt 第 C 步生成 `docs/private/backup-manifest.conf`（ZB_* 键值，含服务器真实值，随 docs/private/ 一并 gitignore）；SKILL.md 的 Phase 0.C、init、adopt、文件索引四处同步。理由：zedback 每日备份改为按清单驱动服务器数据拉取，项目登记信息从备份脚本硬编码迁回各项目本地私有文件，新部署项目纳入备份不再需要改备份脚本。
- **zedui 检测匹配值大小写跟进**：上游 zedui frontmatter `name:` 由小写 `zedui` 改为品牌大小写 `zedui`，SKILL.md 依赖自检与 SETUP 双语检测表的匹配值同步为 `zedui`，自检与 SETUP 的匹配规则补充"不区分大小写"以兼容改名前安装的旧副本。理由：上游更名跟进，避免依赖自检失配；小修不新开版本，并入 0.5.5。
- **环境探测补 `find -L` 说明**：SKILL.md 按名识别规则与 SETUP 双语第 2 步补充"用 `find` 时加 `-L` 跟随符号链接"。理由：端到端实测发现裸 `find` 不跟随符号链接，会把符号链接安装的 skill（含本 skill 与 zedui）整棵漏掉。

## [0.5.4] - 2026-08-11

符号链接部署模式经实测验证生效，AGENTS.md 回退预案降级为极端情况保留。

- **加载器验证**：在 Kimi Code v0.34.0 上做对照实验——同一 skills 目录下并列符号链接 skill 与真实目录 skill，两者均正常加载；再用新会话默认发现路径验证符号链接的 zedboot 出现在 skill 列表。理由：为 0.5.3 的真源纪律补上实测依据；zedui 仓库早年"加载器不跟随符号链接"的记录同步证伪。

## [0.5.3] - 2026-08-11

维护者本机部署模式改为"真源 + 符号链接"，AGENTS.md 部署位说明同步改写为真源纪律。

- **真源纪律**：`~/.kimi-code/skills/zedboot` 由真实目录副本改为指向仓库 `zedboot/` 的符号链接，AGENTS.md 原"rsync 手动同步"一节改写为真源纪律（含线上变回普通目录时的迁移方法、加载器不跟随符号链接时的回退预案）。理由：与 zedback 真源纪律统一，消除副本漂移；公开安装指引（README/SETUP 的拷贝安装）面向普通用户，不受影响。

## [0.5.2] - 2026-08-11

上游可选 UI 依赖 skill 更名（显示名 zedui，frontmatter name 为小写形式），随后其 GitHub 仓库也完成更名；仓库内引用与安装 URL 一并同步。

- **引用同步**：SKILL.md、README / SETUP 双语、CHANGELOG 历史条目、assets 模板中的原名拼写按语境更新——正文/显示语境统一为显示名 zedui；SKILL.md 与 SETUP 双语中按 `name:` 字段检测已安装 skill 的表格/自检规则，匹配值同步为与上游 frontmatter 一致的小写形式。理由：上游依赖更名。
- **URL 同步**：上游 GitHub 仓库更名后，README / SETUP 双语与 SKILL.md 中 7 处安装指引 URL 更新为 `https://github.com/zouh9426/zedui`。理由：上游仓库更名，以新地址为准。

## [0.5.1] - 2026-08-11

名字大小写形式统一：skill 名、skill 本体目录、以及全部文档/模板/代码引用由小写形式统一为 zedboot。

- **命名统一**：SKILL.md frontmatter `name:`、skill 本体子目录（`zedboot/`）、references/ 两份规范、assets/ 全部模板、scripts/audit.py 中的代码标识符（如 `zedboot_readiness` 键），以及 README / SETUP 双语、GitHub 仓库路径引用中的原名小写拼写，全部统一为 zedboot 这一大小写形式。理由：用户要求统一大小写形式。
- **历史条目同步**：CHANGELOG 既有历史条目中的原名小写拼写一并更新为 zedboot，仓库零小写残留。

## [0.5.0] - 2026-08-11

skill 品牌更名：显示名与 skill 名由原名统一改为 zedboot / `zedboot`，仓库结构与全部引用同步。

- **skill 改名**：SKILL.md frontmatter `name:` 与显示名更新为 `zedboot` / zedboot，SKILL.md、references/ 两份规范、assets/ 全部模板、scripts/audit.py 中的名称引用同步。理由：品牌更名。
- **目录改名**：skill 本体子目录更名为 `zedboot/`。理由：品牌更名。
- **门面与仓库引用同步**：README / SETUP 双语、AGENTS.md、CHANGELOG 历史条目、GitHub 仓库路径引用中的名称与路径一并更新。理由：品牌更名后全仓库命名保持一致。

## [0.4.0] - 2026-08-11

新增「每任务收尾自检」机制：自检从"用户提醒才做"变为流程默认动作。

- **`AGENTS.md.tmpl` 收尾检查改写为两档五维自检**：轻版（每任务收尾自动执行）= 机械三查命令块（私有路径/私钥头/git status）+ 五维检查（安全红线 / 一致性冲突 / 失效残留 / 功能 / 同步完整）+ 处置查表（修为默认；产物类直删；git 跟踪文件双命中可删；拿不准登记 TODO）+ 修复后复跑机械检查与纵览 diff 的闭环 + 交付附一行自检结论；全版（发版本前）= 五维全量 + 死文件候选排查 + 项目既有验证复跑。清单开头声明位阶：最低必查而非检查上限，现场判断优先；条目可代谢（新漏检类型补入、长期未命中降级）。理由：维护者每次需口头提醒 agent 自检，且提醒时可能遗漏检查面——自检必须自动触发、默认全覆盖、处置成本按风险分级。
- **references 两份管理规范同步**：compact §7.3 与 reference 内嵌 AGENTS.md 样例各增收尾自检条目（纯增量，规范版本保持 v1.4 不变）。
- **仓库自身 AGENTS.md 迭代纪律加第 6 条**：维护者版自检，发版本前加查双语同步、规范版本一致性、CI 状态。

## [0.3.0] - 2026-08-11

隐私线升级：运维真实值移出入库文件，项目随时可转 Public。

- **SKILL.md「存储纪律」改写为四层隐私线**：可推导值（账号 = 项目名、`/opt/<项目名>`、默认密钥路径约定）可入库；不可推导值（服务器 IP、SSH 端口、密钥真实路径、SSH 别名、crontab 具体调度、备份策略细节）只存本地 `docs/private/ops.md`（gitignore，永不入库），入库文档只写占位符（`<PRODUCTION_SERVER_IP>` 等）+ 指向 ops.md 的注记；秘密本体永不入库（原纪律保留）；域名与公开联系邮箱默认保留。理由：全账号隐私审计发现旧纪律把完整基础设施指纹写进 PROJECT_INDEX/deployment.md 等入库文件，项目转 Public 即泄露。
- **新增 `assets/project/ops.md.tmpl`**：init/adopt 安装时生成 `docs/private/ops.md` 模板；`.gitignore` 必须含 `docs/private/`；SKILL.md 提醒用户 ops.md 不进 Git、需配独立私有备份通道（如私有 ops-notes 仓库）。
- **部署模板改造**：`deployment.md.tmpl`、`PROJECT_INDEX.md.tmpl` 外部资源表改为占位符 + ops.md 注记；`backup.sh.tmpl` 改为 `PROJECT_DIR` 脚本位置自推导、crontab 具体调度移出脚本体；两个 `deploy-rsync` 模板加隐私线注记；`go-live-checklist.md` 占位符说明同步（真实运维值不入清单）。理由：入库文件只留可推导约定值，真实值不落地。
- **`AGENTS.md.tmpl` 新增常驻规则**：运维真实值统一存 `docs/private/`、入库只写占位符、禁止密钥/IP/本机绝对路径入库。
- **audit.py 新增第 9 节「入库文件隐私泄露」检查**：扫描 git 跟踪文件中的疑似公网 IPv4、本机绝对路径（`/Users/`、`/home/`，占位符除外）、私钥格式头，以及 `docs/private/` 文件被跟踪的风险；命中列入审计报告风险项。理由：adopt 改造时机械发现存量泄露，不靠人工翻。
- **新增「转 Public」指引**：Private → Public 前必须先清理 Git 历史中的运维真实值（filter-repo 或重建仓库）；配套 pre-push 闸门见下条，本机全局 hooksPath 闸门可与其共存兜底。
- **占位符词汇统一约定**：隔离运维值用英文大写占位符（`<PRODUCTION_SERVER_IP>` 等，与 shell 环境变量同形），可推导/业务值用中文语义词（`<项目名>`、`<域名>`）——占位符本身即标明该不该入库；存量项目后续按此对齐。
- **rsync 部署模板改环境变量覆盖**：`deploy-rsync.sh.tmpl` / `deploy-rsync-static.sh.tmpl` 的账号、密钥路径默认值直接由项目名推导，服务器 IP 经 `PRODUCTION_SERVER_IP` 环境变量传入（未传则报错退出），脚本本体永远保持占位符、永远可提交。理由：消除"填真实值才能跑"导致的脏工作树与误提交风险。
- **Git 初始化/`.gitignore`/pre-push 闸门下沉到管理体系步骤**：这三条原来挂在「装部署体系」内，"服务器待定暂缓部署"或"无部署但用 Git"的项目会漏掉 Git 初始化、`.gitignore` 纪律与 hook 安装（Phase 0.B 甚至可能已建远程仓库而本地无人 init）。现归入「装管理体系（所有模式）」，按"启用 Git"条件执行。依据：无服务器场景流程推演发现的结构性缺口。
- **依赖自检新增 Git 本体探测**：`git --version` 不可用时引导安装或登记"暂不启用 Git"（相关步骤整组跳过 + TODO 待补），与 zedui 缺失的降级风格一致。理由：原自检只探测 GitHub 认证，git 命令本身缺失时流程无降级路径。
- **新增 pre-push 隐私闸门（`assets/hooks/pre-push.tmpl`）**：自包含 bash，装进项目 `.git/hooks/pre-push`，扫描本次推送新增行，拦截私钥格式头、本机绝对路径、公网 IPv4（排除私网与 RFC 5737 文档段）；宁漏勿滥、误报可 `--no-verify`；init/adopt 幂等安装。理由：存储纪律（不该入库）与 audit.py（改造时发现存量）之外，补上日常防新增泄露的第三道防线。设计上不触碰 `core.hooksPath`（与本机全局闸门共存、互不覆盖），hook 不调用 audit.py（装完即退场，不留对 Skill 路径的运行时依赖）。
- **一致性同步**：`references/deployment-guide.md` §6 信息登记分两层改写；`README.md`/`README.en.md` 双语同步；`audit-report.md.tmpl` 风险项补充。

## [0.2.0] - 2026-08-07

开源发布 + 工具无关化。

- **skill 负载移入 `zedboot/` 子目录**：仓库根只留门面粉件（README/SETUP/CHANGELOG/AGENTS/LICENSE/CI），skill 本体（SKILL.md + references/ + assets/ + scripts/）独立成目录。理由：clone 下来的仓库不等于可直接加载的 skill 目录，门面与负载分离后结构清晰，也避免仓库级文件被误拷进技能目录。
- **SKILL.md 新增「环境探测」一节**：候选技能目录覆盖 `~/.agents/skills/`、`~/.kimi-code/skills/`、`~/.claude/skills/`、`~/.codex/skills/` 及项目级目录；skill 之间**按 frontmatter 的 `name:` 字段互相识别**，不按目录名；自身路径也由 name 解析。理由：面向所有支持 SKILL.md 的工具（Kimi Code / Claude Code / Codex 等），路径硬编码等于私有；目录名与 skill 名可能不一致，必须按名解析。
- **新增 README.md（中文主门面）/ README.en.md**：三套体系、两条工作流、核心设计决策、前置条件、安装与触发方式、仓库结构。理由：开源门面；中文为主是因为目标用户群是中文用户。
- **新增 SETUP.md / SETUP.en.md 安装引导提示词**：用户贴给自己的 AI agent 即可完成环境识别、按名查重、安装与自检。理由：安装涉及"仓库根 ≠ skill 目录"的细节，让 AI 代办最不容易错。
- **新增 LICENSE（MIT，Copyright (c) 2026 zouh9426）**。理由：MIT 的「保留版权声明」条款即署名保留，满足作者诉求；skill 类项目无专利考量，不需要 Apache-2.0 的重量。
- **新增 AGENTS.md（仓库级维护规则）**：维护者 agent 与使用方 agent 分离、无私有路径红线、双语同步、发版纪律。
- **新增 GitHub Actions 私有路径检查 CI**：检查正则用 `/Users/[a-zA-Z0-9_-]+/` 只匹配真实路径。理由：设计已消除私有路径的必要性，CI 做兜底防止后续迭代回潮。

## [0.1.0] - 2026-08-07

基线快照。首次构建完成时的原始版本（仓库根即 skill 目录、路径候选未覆盖全工具），仅供历史留档，不建议新用户使用。

该版本已包含的核心架构（沿用至今，详见 README）：

- 三体系编排：项目管理（规范 v1.4 双文件）+ 部署（栈无关 guide + 四栈模板）+ UI（委托 zedui，零复制不漂移）。
- init / adopt 两条工作流：六组信息采集 + 待定机制、幂等安装、秘密边界、装完即退场。
- 管理规范 v1.4：修正发布流程 Git Tag 时机冲突（改为部署与线上验证后打 Tag）、明确 push 与发布绑定、根目录白名单纳入部署文件。
- `scripts/audit.py` 只读审计：纯标准库，探测不到标 unknown 交 AI 判断。
- 经五场景实测（3 init + 2 adopt，含乱套旧项目与异构部署冲突裁决），累计修进 8 处实测发现的问题。
