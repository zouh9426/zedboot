# CHANGELOG

本项目所有值得记录的变更都写在这里。格式约定：每条目回答两个问题——**改了什么**、**为什么这么改（决策理由）**。

## [0.8.1] - 2026-08-15

多场景实测驱动的修复版（审查主张均先实测复现再修；实战覆盖 Python init / 纯 HTML 静态站 init / Go adopt 三条链路端到端，含部署模拟与 pre-push 实测）。不加功能、不动 Docker 三档架构。

追加修复（三链路实测暴露的模板/文档级问题）：

- **模板与校验器打架三处修复**：TODO.md.tmpl / DECISION_LOG.md.tmpl 的"编号格式"说明行、backup.sh.tmpl 的注释示例自带尖括号中文占位符（`<项目代码>`/`<项目名>`），忠实落盘必触发 verify.py 占位符 FAIL——两个测试员独立踩中。改为示例式/英文占位写法（`XXX-001`、`<PROJECT_NAME>`），语义不变。理由：模板的第一要务是照做不翻车。
- **deployment-static.md.tmpl 纯 HTML 文案补漏**：本轮前半段修了 static/README 与 checklist 的 npm run build 文案，独漏生成给项目日常读的 deployment.md（发布/恢复两处命令链）——纯 HTML 项目照抄必失败，已改"有构建步骤先构建、纯 HTML 直接执行"口径。理由：同一口径的修复必须覆盖所有落地文件，漏一个就等于没修。
- **文档/模板小项十处**：AGENTS 模板悬空 bullet 删除；隐私指针从 skill 内部路径（装后悬空引用）改指项目内 docs/guides/deployment.md；deploy.env.tmpl 补 STATIC_OUTPUT_DIR 安装时填值指引（纯 HTML 首部署必踩 fail-closed 的预防）；info-collection 模式枚举补"静态站归入可部署代码项目"；init-workflow 补"部署件未提交前勿 git reset/stash"警示与 Go 栈 go.sum 前置说明；adopt-workflow 补"仅 git rm --cached 不重写历史时首次 push 必被拦"预告；deploy-rsync 尾行"自动迁移"标注适用范围；backup-manifest 注释说明 ZB_SSH_KEY 与 DEPLOY_KEY 同键不同形；backup-manifest 头部注释同步 zedback"纯数据解析、绝不 source"的消费方式（维护者先行改动，本版一并入库）。
- **实战记录备查**（未修项与理由）：rsync 排除 `.env*` 连 `.env.example` 一起排（服务器不需要该模板，可接受的保守）；audit 对子目录 env 变体只报 basename（不影响处置）；模板"落盘时删除"的 HTML 注释若漏删会触发 verify FAIL（属预期——verify 替你抓到没删干净）。

追加修复（pre-push 语义钉死 + 部署契约收尾）：

- **pre-push force-push fail-open 修复（P0）**：existing-ref 分支的 `remote_sha..local_sha` 中 remote_sha 是远端对象 ID、不保证在本地对象库（force-push 独立历史场景），`git log` fatal 被 `2>/dev/null || true` 吞掉 → 扫描为空即放行。修复：推送前 `git cat-file -e "${remote_sha}^{commit}"` 验证，不存在即拒（提示先 fetch）；两处 git log 改为捕获退出码、非零 fail-closed 拦截，"扫描失败"不再被解释成"扫描无命中"。新增 force-push E2E 回归（先红后绿）。理由：与 0.7.0 修的引号 bug 同一根因类——吞错误码的闸门必然 fail-open。
- **pre-push merge 语义修正（P1）**：前半段的 `-m` 让 merge commit 对每个父各出一次 diff，会把第一父侧已接受的旧内容（如已推送的公网 IP）当新增误拦；两处扫描改 `--diff-merges=first-parent`（遍历完整历史，merge 只相对第一父出 diff）。三个场景实测：误报场景放行、冲突解决塞私钥拦、侧分支泄露拦。新增误报对照用例。
- **diff-filter ACR → ACMRT（P1）**：C=Copied 而非 Modified——已跟踪 .env* 修改值在 ACR 下无输出可绕过路径闸门；ACMRT 补齐修改与 type-change。新增"已跟踪 .env.production 改值必拦"用例。
- **CI 红修复（Release Blocker）**：test_pre_push.py 新用例的 `git merge --no-ff` 未注入 identity，CI 无全局 git 配置五矩阵全红（本机绿是因为本机有全局 identity）；fixture 建仓统一本地 `git config user.name/email`。
- **静态 manifest 双拼修复（P1，前半段引入）**：ZB_SERVER_DIR=<REMOTE_DIR> 与静态站 REMOTE_DIR=/opt/<项目名>/dist 组合下，zedback 直拼出 .../dist/dist。模板改分栈指引：容器栈 ZB_SERVER_DIR=REMOTE_DIR；静态站 ZB_SERVER_DIR=REMOTE_DIR 父目录、ZB_PULLS=发布目录名。
- **SSH_PORT 六事实（P1）**：Phase 0 采集了 SSH 端口但机器侧无消费——deploy.env 新增 `SSH_PORT`（默认 22，旧 deploy.env 兼容），两个 rsync 脚本 ssh 加 `-p`；六处"五事实"表述同步六事实；zedback 协议不动，manifest 注释标注非 22 需另行配置。理由：采集了不消费等于白问，非 22 端口部署必挂。
- **文案陷阱与次级项**：deployment.md.tmpl 的 `cd ${REMOTE_DIR}` 在服务器无定义（deploy.env 是本地文件且 docs/private 被 rsync 排除），改为"以 deploy-rsync.sh 结尾输出的服务器命令为准"；compose 示例库文件名与 backup.sh SQLITE_DB 默认统一为 app.db；静态站纯 HTML 无构建的文案不再以 npm run build 开头；README 双语"专用账号隔离"概括、账号=项目名、.env 单数等旧口径同步。
- **本轮未采纳项（记录备查）**：审查建议删除 pre-push/audit 的"目录名/项目名派生 /home/ 路径自动放行"——未采纳。该放行只作用于路径模式（目录名/项目名是公开可推导值），秘密内容由私钥头/值正则独立拦截；删除它会复活 0.5.10/0.5.11 实测过的"合法运维路径被拦 → --no-verify 疲劳"问题，审查方未给出攻击场景论证。
- **已知遗留**：Prisma 7 的 prisma.config.ts 在 runner 中的模块解析（dotenv/config 引用）未经真实 Docker 运行验证，结构断言绿 ≠ 运行绿，列为后续最高优先实测项。

前轮（前半段）：

- **Prisma Dockerfile 修复 v0.8.0 引入的构建回归（P0）**：v0.8.0 为兼容 Prisma 7 把 `COPY prisma ./prisma` 改成 `COPY prisma* ./`——Docker COPY 语义下目录 source 拷的是内容而非目录本身，通配多 source 时 prisma/ 内容被摊平进 /app 根，/app/prisma 不存在导致 runner 的 `COPY --from=prisma-cli /app/prisma` build fail；且 prisma.config.ts 也进不了 runner。恢复目录拷贝，两个 stage 各加一行注释掉的 prisma.config.* 可选拷贝（安装时按项目实际启用），deployment-guide §7.1 同步；test_deploy.py 新增两个结构断言用例防通配回归（本机/CI 无 Docker 构建环境，以模板结构断言替代 build smoke）。理由：修兼容性不能以破坏基础构建为代价。
- **pre-push 去掉 --first-parent（P0）**：v0.8.0 为覆盖 merge 冲突解决引入的敏感行加了 `--first-parent -m`，但 --first-parent 令 git log 完全不遍历第二父代链——feature 分支"加私钥→删除→--no-ff 合回 main"后，侧分支历史中的私钥不在扫描范围，push 放行。两处扫描均删 --first-parent 保留 -m（merge 对双父各出一次 diff，存在性检查下重复无害）。新增回归用例：侧分支泄露后删除再 merge 必须拦（先红后绿实测）。理由：推送的是整段历史，不是主线净变化。
- **pre-push 路径检查覆盖 rename（P1）**：`--diff-filter=A` 对 `git mv .env.example .env.production`（R100）无输出，rename 可绕过 .env* 路径拦截；改为 `ACR`（rename 检出无需显式 -M，--name-only 输出目标路径）。新增 rename 拦截回归用例（先红后绿）。
- **tracked .env* 全量收口（P1）**：verify.py 的跟踪检查只对字面 `.env`、audit.py 的 pathspec `".env*"` 不跨目录（`config/.env.local` 漏检，且内容扫描又因 _is_env_file 跳过——双盲区）。两处统一改为 `git ls-files -z` 全量 + basename 过滤，任意子目录变体覆盖。verify/audit 各补子目录变体跟踪的回归用例。
- **REMOTE_DIR 最后两处收口（P1）**：deployment.md.tmpl 服务器命令不再写死 `cd /opt/<项目名>`（指向 deploy.env 的 REMOTE_DIR）；backup-manifest.conf.tmpl 的 `ZB_SERVER_DIR` 改 `<REMOTE_DIR>` 占位。
- **P2 尾巴清理**：init/adopt 工作流"闸门读 ops.md"旧口径改 deploy.env 真源表述；四处 `.env` 单数表述改 `.env*`（含两份管理规范同步）；tests 描述四处补 test_deploy.py；test_deploy.py 过期注释更新；静态站 Caddyfile 示例补 REMOTE_DIR 一致性注释。

测试：86 → 97 个 unittest 用例全绿。

## [0.8.0] - 2026-08-14

外部第五轮审查驱动的隐私链路补全 + 部署契约收敛。审查的两项 P0（.env* 变体、multi-remote 漏扫）均经 /tmp 实测复现确认后修复；pre-push 所有修复均先红后绿。

- **`.env*` 变体全链路保护（P0）**：此前整条链只护字面量 `.env`，`.env.local`/`.env.production` 可进 Git、镜像与服务器。①init 的 gitignore 要求改为 `.env*` + `!.env.example/.sample/.template` 例外；②verify.py 的 gitignore 检查收紧为只接受 `.env*` 覆盖，哨兵探针新增 `.env.local`/`.env.production`；③dockerignore 与两个 rsync 脚本排除同步为 `.env*`（含例外名）；④pre-push 新增路径级拦截——revs 范围内新增的 `.env*` 文件（例外名除外）直接拦，且独立于内容扫描执行（无新增行时也生效）；⑤audit.py 新增 `_is_env_file` 口径，被跟踪的 `.env*` 变体出专项风险项；⑥verify.py 降级扫描的跳过逻辑同步扩为 `.env*`（避免读到变体内容）。理由：变体文件是各框架惯例（Next/Vite 都生成 `.env.local`），字面量防护等于在惯例上开口子。
- **pre-push multi-remote 漏扫修复（P0）**：新引用场景 `--not --remotes` 排除所有远程的 tracking refs——私有 origin 有脏历史时，新增 public remote 首推会把脏历史整体排除、未经扫描推往 public。改为用 pre-push 入参 `$1` 只排除当前目标远程（`--remotes="${remote_name}"`；目标远程本地无 refs 时排除集为空、自动退化全历史扫描，fail-closed）；另防御 `remote_name` 为空时 `--remotes=` 空模式等价排除所有远程的 fail-open 陷阱。理由：多远程是私有备份 + 公开发布的常见拓扑，排除范围必须是"目标远程"而非"所有远程"。
- **pre-push merge commit 漏扫修复（P1）**：`git log -p` 默认不显示 merge diff，--no-ff 合回 main 时冲突解决引入的敏感行会漏扫；内容扫描与路径检查均加 `--first-parent -m`（主线视角出一次 diff，实测可命中冲突解决新增行）。新增 6 个回归用例（multi-remote 拦截、merge 藏私拦截、`.env.production`/子目录变体拦截、`.env.example` 放行对照、deploy.env 账号放行）。
- **deploy.env 收为唯一机器真源（P1）**：pre-push 与 audit.py 的服务器账号改从 `docs/private/deploy.env` 的 `DEPLOY_USER` 读取（去引号去空白），ops.md「机器可读字段」保留为旧项目 fallback；ops.md.tmpl 与 info-collection 标注"deploy.env 机读、ops.md 人读"分工。verify.py 部署检查新增 deploy.env 存在性项（只查存在不读内容，缺失 FAIL）。理由：同一事实两个真源必然漂移；脚本没 deploy.env 跑不了而 verify 却 PASS，是验收器的直接漏项。
- **静态站发布目录越界防护（P1）**：0.7.0 的 fail-closed 只防"目录缺失"，`STATIC_OUTPUT_DIR=.` 或 `../x` 仍可指回项目根或越出项目；新增 canonical path 校验（`cd + pwd -P` POSIX 便携写法），发布目录必须是项目真子目录。新增 `tests/test_deploy.py`（7 例：deploy.env 缺失报错、五事实注入、越界拒绝等，fake rsync 捕获实参）。
- **backup.sh SQLite 路径不再从目录名推导（P1）**：`SQLITE_DB` 改为显式变量（默认 `${DATA_DIR}/app.db`，注释指引与 DATABASE_URL 对齐），basename 只留作备份包命名；库文件缺失从静默跳过改为输出提示。理由：服务器目录名 ≠ 数据库文件名，推导失败时一致性备份静默不执行。
- **Prisma 7 配置兼容（P1）**：prisma-cli stage `COPY prisma ./prisma` → `COPY prisma* ./`，prisma.config.ts/js/mjs 可进 CLI stage（prisma/ 恒存在，通配不会空匹配失败）。
- **部署契约漂移清理（P1/P2）**：容器版 deployment.md.tmpl 删除 0.5.8 时代的内联 rsync 命令块，改为 `git push && ./deploy-rsync.sh`（文档引用脚本、脚本负责实现，根除双写漂移）；go-live-checklist 容器条目同步 deploy.env 口径；裸 `DEPLOYED=true` 残留改 `ZB_DEPLOYED`；项目 AGENTS 模板自检命令改 `git ls-files -coz | xargs -0`（NUL-safe）并补 deploy.env 隐私指针；init 补 Go 主包检测指引；静态站"一律 dist"残留按框架口径清理。

## [0.7.0] - 2026-08-14

外部第四轮全仓库审查驱动的**部署体系可靠性/安全性修复版**（审查范围首次覆盖部署模板、pre-push 实际 Git 语义与项目模板全文；编排核心无改动）。含一处行为反转与一处行为变更，见第 1、2 条。

- **修复 pre-push 闸门「新引用推送」场景静默失效（P0，行为修复）**：`assets/hooks/pre-push.tmpl` 在远端已有其他引用、首次推新 branch/tag 时构造 `revs="$local_sha --not --remotes"` 并以 `"$revs"` 整体引用——git 收到的是单个含空格参数，报 `fatal: ambiguous argument`，错误被 `2>/dev/null || true` 吞掉，扫描结果为空即放行，隐私闸门在该场景下从未真正执行（0.5.11 的增量扫描特性形同虚设）。`revs` 改为 bash array、调用处 `"${revs[@]}"`。`tests/test_pre_push.py` 新增两个反向回归用例（新 tag / 新 branch 携带私钥头必须被拦，先实测修复前红、修复后绿）。理由：现有测试只断言"干净提交放行"，扫描没执行时同样绿——闸门类代码必须有"脏内容必拦"的反向用例才算被测试。
- **静态站发布目录改 fail-closed（P0，行为反转）**：0.5.10 为适配无构建纯 HTML 站加入的「无 dist/ 则推项目根」fallback 会把 `docs/private/`（含服务器 IP/账号的 ops.md）等整个仓库根发布到 Caddy 文件伺服目录，属真实安全漏洞，删除。发布目录改由 `STATIC_OUTPUT_DIR` 显式控制（Vite/Astro=`dist`、Next.js 静态导出=`out`、纯 HTML=`public`），目录不存在即报错退出并给出框架指引，**绝不发布项目根**。迁移说明：无构建纯 HTML 站把网页文件收进 `public/`，或在 `docs/private/deploy.env` 设 `STATIC_OUTPUT_DIR`。理由：发布目录永远不应自动猜，猜错的代价是把私有资料公网化。
- **Docker 账号安全模型诚实化 + 三档模型（P0，文档级架构修正）**：deployment-guide 原表述「docker 组账号 = 多项目互不越权、最大破坏范围是自己的目录」不成立——Docker 官方文档明确 docker 组等价 root 级权限（可经 docker socket 提权控制整台宿主机）。§2 改为安全档位表：**standard**（默认，保留 docker 组的便利性，但明确标注不构成宿主机安全边界，适用单管理员全可信场景）、**hardened**（账号退出 docker 组 + root-owned 固定 wrapper 与 compose 的受控部署入口，适用不可信代码/AI agent 直接在服务器执行的场景；写明 wrapper 必须与 root-owned compose 配套否则形同虚设）、**isolated**（每项目 Rootless Docker，给官方文档指针与限制说明）。SKILL.md 概览措辞同步。理由：安全声明必须诚实——虚假的安全感比没有安全措施更危险；hardened/isolated 先落成文档方案而非一键模板，避免在可靠性修复版里引入不可测的复杂机制。
- **Python Dockerfile 修复构建必挂（P0）**：原模板 `USER appuser` 之后才 `COPY` entrypoint + `RUN chmod`——COPY 产物属 root，非 root 非属主 chmod 必然 Operation not permitted，照模板构建直接失败。改为 `COPY --chown=appuser:appuser --chmod=755` 一步到位后再切 USER。理由：模板的第一职责是构建能过。
- **部署脚本落实三事实分离 + rsync 排除 docs/private（P1）**：两个 rsync 脚本模板删除 `basename` 链路推导（本地目录名→项目名→账号→服务器目录），改为 source `docs/private/deploy.env`（新增 `assets/project/deploy.env.tmpl`，部署五事实 `PROJECT_NAME`/`DEPLOY_USER`/`REMOTE_DIR`/`SERVER_IP`/`DEPLOY_KEY` 显式提供、私有不入库）后逐项 `:?` 强制校验；rsync 排除项追加 `--exclude docs/private`（此前每次部署都把定义为"本地私有"的 ops.md 同步上服务器）；deployment-guide §4 示例命令与 §6 信息登记同步。理由：三事实分离是 info-collection 的既有设计，脚本层却在默认重新合并；REMOTE_DIR 此前连覆盖口都没有。
- **Go / Next.js 模板修正（P1）**：Go 模板 `go build -o ... ./...` 参数化为 `ARG GO_MAIN_PACKAGE=./cmd/server`（`./...` 多 package 配 `-o` 单文件在典型 cmd/server 布局报错）；Next.js 模板 Prisma CLI 版本从硬编码 `prisma@5` 改为构建时读项目 package.json（prisma-cli 阶段补 `COPY package.json ./`），entrypoint 从内部路径 `prisma/build/index.js` 改为公开入口 `.bin/prisma`。理由：模板要么通用要么参数化，硬编码大版本与内部布局都会随上游演进悄悄坏掉。
- **项目模板与文档口径清理（P1/P2）**：①项目 AGENTS 模板机械三查从全仓库递归 grep（会扫 .env/docs/private/node_modules，与"永不读 .env"自相矛盾）改为 `git ls-files -co --exclude-standard` 的 git candidate 口径，与 verify.py 一致；②docs-README 模板"接手当前任务"清单与 AGENTS 分层加载对齐（RULES/INDEX 按需）；③info-collection L23 推导值表述标注"建议默认约定、以 deploy.env 为准"，消除与三事实分离的内部张力；④init/adopt 的 verify 收口命令改为完整形式 `python3 <skill路径>/scripts/verify.py`（verify.py 不进目标项目、无执行位）；⑤init/adopt 落盘清单补 deploy.env；⑥README 双语、tests.yml step 名、根 AGENTS.md 的 tests 描述补上 pre-push hook 测试。理由：口径不一致的文件会随安装拷进每个新项目，矛盾复制比矛盾本身更贵。

## [0.6.2] - 2026-08-14

外部第三轮复检驱动的校验语义补全 + 文档口径清理。

- **verify.py 的 .gitignore 校验加「生效语义」第二层**：条目存在 ≠ 最终生效——`.env` 后写 `!.env` 这类反向规则会让防护静默失效（实测：该场景下 git 实际不忽略 .env，而 0.6.1 的条目检查会 PASS）。新增 `gitignore_effective` 检查：对四个哨兵路径（`.env`、`data/`、`backups/`、`docs/private/` 下探针文件）跑 `git check-ignore -q --no-index`，把顺序/取反/层级语义交还给 git 自己判；非 git 仓库 SKIP、命令异常 WARN，不臆断。test_verify.py 补两个回归钉（`!.env` 反向抵消 FAIL + 正向对照 PASS），全 PASS 用例的精确计数同步 30→31。理由：verifier 自写解析器不可能完整复刻 gitignore 语义，假 PASS 比 FAIL 更危险。
- **compatibility 口径修正**：0.6.1 写 "Requires Python 3.8+ and Git"，与依赖自检第 3 条「Git 不可用可降级」矛盾；改为 Git 推荐（隐私闸门等 Git 功能需要），核心安装可降级。理由：9 分以后该消灭规则自相矛盾。
- **文档残留清理**：README/SETUP 双语的 Python 前置说明从「adopt 工作流需要」改为「3.8+，audit.py 与 verify.py 均需要」（init 第 4 步收口也跑 verify）；README 仓库结构 tests 行补 verify.py。
- **CI 新增 skill-spec 校验**：`spec-validation.yml` 用 Agent Skills 官方参考校验器 `skills-ref validate ./zedboot`（从 git 子目录安装并钉死 commit——PyPI 0.1.1 版 CLI 名有上游打包问题，上游 main 是移动目标）。本地实测当前 skill 通过校验（"Valid skill: zedboot"）。理由：防 frontmatter 回归（如 name 大写这类历史问题复发），且工具真实性已按仓库「依赖不编造」红线核实。
- **新增 `tests/test_pre_push.py`**：pre-push 隐私闸门的行为回归（真实 git push 端到端触发，覆盖私钥头/本机路径/公网 IP 拦截、目录名/项目名/ops.md 服务器账号三类放行、私网与 RFC 5737 文档段不误伤、新 tag 增量扫描语义、`<项目名>` 未替换降级）。理由：闸门是装出去的每个项目的推送防线，此前只有手工实测无自动回归；测试补齐不碰架构，符合「停止架构迭代、真实项目喂养」的阶段定位。

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
- **audit.py fixture 测试矩阵重建并入库**：0.5.8 声称的「10 项 fixture 测试矩阵」从未提交、测试资产丢失；现重建为 `tests/`（6 静态 fixture + 4 动态 fixture，27 个 unittest 用例：跑通/JSON 合法/只读性快照对比/探测正确性抽查），新增 CI `tests.yml`（push/PR 触发，Python 3.8–3.12 矩阵）。fixture 的隐私测试值（私钥头、.env、本机路径）全部运行时拼接/动态构造，不入库字面量，与全局 pre-push 隐私闸门兼容。理由：Skill 复杂度早已超过「零测试」能兜住的水平；fixture 不入库等于每次改动都靠回忆回归。
- **装进项目的 AGENTS.md 模板改分层阅读**：原「强制阅读顺序」6 份文件（约 24 KB 固定开销）改为「每次任务必读小文件（AGENTS/STATE/TODO/任务引用，约 6 KB）+ 按触发读大部头（PROJECT_RULES 流程裁决与同步时、INDEX 定位资源时、deployment.md 部署时、DESIGN.md UI 时等）」；README 双语「不增加日常 token 负担」改为如实的分层加载口径。理由：审核指出原表述与强制阅读清单的实际 context 成本矛盾，名不副实。
- **装前自检（0.6.0 发布前第一遍复查）四处修复**：①管理规范两份文件的阅读口径同步为分层加载——compact §0.1 旧口径「按 AGENTS 顺序读 README/规则/索引/状态/TODO」与新模板直接冲突且会随安装拷进每个项目（compact §11.3 本就是新口径，§0.1 属没删干净的旧残留），reference §1.1 与 §5.2 推荐模板同步；②go 栈 entrypoint 三向对齐——go 栈 ENTRYPOINT 烤进镜像、无 docker-entrypoint.sh，init 落盘清单与 chmod 清单注明适用范围、SKILL.md 文件索引措辞修正、verify.py 改为「Dockerfile 引用 docker-entrypoint 才必查」（缺失但 Dockerfile 自含 ENTRYPOINT 判 PASS）；③audit.py docstring 过期指针「SKILL.md 存储纪律」改指 references/info-collection.md；④tests/fixtures 的 .DS_Store 加 .gitignore 例外（防索引重建后 CI 静默翻车）。理由：发布前模拟安装走查发现的真冲突与三向不一致，同步修复避免把矛盾装进新项目。
- **发布前第二遍端到端模拟验证（沙盒项目实测）一处修复**：`backup.sh.tmpl` 头部注释的 crontab 示例行用了中文占位符（`<分> <时> <项目目录>`），照流程安装的项目会被自己的 verify.py 判占位符残留 FAIL——模板与校验器自相矛盾，示例行已改为英文隔离占位符（`<MIN> <HOUR> <PROJECT_DIR>`，与存储纪律的占位符命名约定一致）。模拟本身结论：init 全流程（管理体系 + python 栈部署体系 + 闸门安装）跑通，verify.py 拦下两处安装漏填（deployment.md 的 `<仓库地址>`/`<DNS托管商>`）并指引修复后全 PASS；pre-push 闸门功能实测——私钥头/本机路径/公网 IP 推送均拦截、干净提交与 RFC 5737 文档段 IP 放行，且在全局 `core.hooksPath` 机器上经全局钩子链式调用实际生效（verify.py 对该场景正确 WARN 提示人工确认）；adopt 全流程跑通——audit.py 正确检出 .env 被跟踪与入库公网 IP，幂等安装后管理文档 1/10 → 10/10、verify 全 PASS；幂等重跑零意外 diff。

## [0.5.11] - 2026-08-12

隐私闸门两项放行机制修正（某生产项目发布实测驱动）。

- **隐私闸门三事实分离改造**：放行口径由「仓库目录名 + 项目名」两来源扩为三来源——第三个独立事实「服务器账号」登记在 `docs/private/ops.md` 新增的「机器可读字段」节（`- 服务器账号: <值>` 单行，键后中/英文冒号均可），pre-push 闸门运行时读取并加入 `/home/<账号>/` 放行集合（ops.md 缺失时静默降级），audit.py 的 home_allow 同步纳入该来源，解析口径与闸门一致；ops.md.tmpl 补机器可读字段说明，SKILL.md 存储纪律补「三事实分离」约定并在 init/adopt 两处安装步骤注明「账号无需安装时配置」。理由：2026-08-12 某生产项目实测——仓库目录名与服务器账号不一致（大小写与命名均不同），合法运维路径（如 /home/<账号>/ 下的 systemd 单元）因账号无处机器可读，每次发布被自家闸门拦截、只能 --no-verify；账号是独立事实，须在专用隐私文件记录一次、闸门与审计各自读取。
- **新引用推送只扫"远程还没有的提交"**：此前推新 tag（remote_sha 全零）一律全历史扫描，历史中含闸门启用前遗留值的仓库每次发版推 tag 都会被自家闸门拦；现改为远程已有引用时按 `git rev-list <sha> --not --remotes` 取增量（远程全空的真·首次推送仍全历史扫描）。理由：全历史重复拦截让闸门形同虚设（每次都得 --no-verify），增量语义与全局 privacy-gate 既有实现一致。

## [0.5.10] - 2026-08-12

全量审计（模板逐件核对 + audit.py 冒烟实测）后的集中修复。

- **「十项管理文档」口径对齐**：`audit.py` 的 `CORE_MANAGEMENT_DOCS` 此前误含 `DESIGN.md`、漏 `archive/README.md`，与管理规范正典（audit-report 模板与 project-rules-compact §16）错位，adopt 审计的 N/10 计数会与报告模板对不上；已改为正典十项，DESIGN.md 保留在 UI 节单独检查。理由：同一事实两套口径是 0.5.8 口径对齐工作的遗漏，审计输出必须与管理规范逐字一致。
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

双场景实战自查（init 模拟 + adopt 模拟）+ adopt 实战（某生产项目第二轮改造验收）暴露的缺陷集中修复：脚本执行位、hooksPath 语义纠错、audit.py 误报治理与覆盖缺口、static 栈模板适配、契约默认值、幂等安装缺口。

adopt 实战残留缺口：

- **adopt 幂等安装补"管理规范副本版本对齐"条目**：`PROJECT_RULES.md` 重拷精简版对齐当前版；项目随装了完整参考版（`docs/reference/PROJECT_RULES_REFERENCE.md`）时必须同步重拷，两份副本版本号与署名保持一致；并 grep 项目入库文件中的本 Skill 历史名称（旧名 ZeroWeave）命中即改。理由：某生产项目第二轮 adopt 实测——精简版署名已对齐 zedboot，参考版仍残留"由 ZeroWeave skill 分发"（第一轮改名前安装的副本，adopt 流程只覆盖了精简版），旧署名将随每次 adopt 在每个改造项目里复发。

实战自查集中修复：

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
