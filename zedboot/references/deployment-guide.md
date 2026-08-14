# 项目部署体系规范

> 本文件为 zedboot skill 的参考规范；项目落地时由 AI 据此生成项目内 `docs/guides/deployment.md`（入库文件只写占位符，真实运维值存本地 `docs/private/ops.md`，见 §6）。
> 适用范围：单台云服务器上共机运行多个小型项目的部署规范。三层结构：**专用账号 + Docker 容器化 + Git 工作流**（账号的 Docker 权限按 §2 安全档位配置）。
> 文中 `<项目名>`、`<域名>`、`<端口>`、`<账号>` 为可推导/业务占位符，落地时直接填实入库；`<PRODUCTION_SERVER_IP>`、`<DEPLOY_KEY>` 等英文大写占位符为隔离运维值，真实值写入 `docs/private/ops.md` 而非入库文档。

## 1. 体系概览

1. **专用账号 + 分档 Docker 权限**：每项目一个系统账号（无 sudo）+ `/opt/<项目名>`，账号负责文件归属、SSH 部署通道与备份任务；Docker 操作权限按 §2 的安全档位配置。注意：默认 standard 档下账号入 docker 组，而 **docker 组等价 root 级权限**，此时账号隔离只在文件/SSH 归属层面成立，不构成宿主机安全边界（见 §2）。
2. **Docker 容器化**：多阶段构建产出最小运行时镜像，compose 一键起停；容器启动时自动执行数据库迁移；数据绑定挂载到宿主机，容器与镜像随时可丢弃；反向代理（Caddy）对外提供 HTTPS。
3. **Git 工作流 + 本地直推部署**：每项目一个独立私有 GitHub 仓库仅作备份与版本管理；部署时用 rsync 把代码从本地直接推到服务器重建，GitHub 与服务器之间不发生关系，两边都以本地为源头。纪律：**先入库备份、再部署**（push 只与发布绑定，详见 §4），GitHub 和服务器内容就永远一致。任务分支开发 → 合回主干 → 发布打标签，全程可追溯。

**适用前提**：单台云服务器（1C1G 即可跑小型项目）跑多个项目；面向大陆访客优先选香港/新加坡 VPS（免备案，建议优化线路），大陆 VPS 必须 ICP 备案，且备案通过前 80/443 通常被服务商拦截。

## 2. 专用账号约定与安全档位

**约定**：

- 每项目一个专用系统账号：**无 sudo**；是否加入 docker 组取决于下方安全档位
- 应用目录 `/opt/<项目名>`（本地 rsync 的部署目标；服务器上不检出 git、不手工改代码）；数据 `/opt/<项目名>/data`
- SSH 部署密钥仅授权该项目账号，**不放 root**（私钥拷回本地，用于 SSH/rsync 部署登录）
- 备份脚本与 crontab 归属项目账号，备份存 `/opt/<项目名>/backups/`

**安全档位**（按威胁模型选择，可随时升档）：

| 档位 | 机制 | 隔离强度 | 适用场景 |
|---|---|---|---|
| **standard**（默认） | 项目账号入 docker 组，自行执行 `docker compose` | **仅文件/SSH 归属隔离**：docker 组 = root 级权限，账号可经 docker socket 提权控制整台宿主机，不构成安全边界 | 单管理员、全部项目代码可信、共机项目均为己有 |
| **hardened** | 项目账号退出 docker 组；部署由 root 拥有的固定 wrapper（如 `zed-deploy <项目名>`）执行 root 拥有的 compose（`/etc/zedboot/projects/<项目名>/compose.yaml`，写死挂载与端口，禁 privileged / 任意 bind mount / host network）；可选配 SSH forced-command 控制 key | 项目账号无法直接接触 Docker，破坏范围锁死在自己目录 | 服务器上运行不可信代码、多管理员、AI agent 直接在服务器执行任务 |
| **isolated** | 每项目独立 Rootless Docker daemon（systemd user service 管理） | daemon 与容器均运行在非 root user namespace，Docker 层完全隔离 | 强隔离需求；可接受多 daemon 开销与 Rootless 的功能限制 |

> **standard 档必须诚实认知**：专用账号的价值是文件归属、SSH 通道与职责清晰，**不是安全隔离**——Docker 官方文档明确 docker 组成员获得 root 级权限（<https://docs.docker.com/engine/install/linux-postinstall/>）。威胁模型中出现"项目账号会被不可信方使用"（如 AI agent 直接在服务器上以项目账号执行任务）时应升 hardened。hardened 的 wrapper 必须与 root-owned compose 配套：compose 若仍可被项目账号修改（挂载 `/`、`privileged: true`），wrapper 形同虚设。Rootless 模式见 <https://docs.docker.com/engine/security/rootless/>。

**职责分层**：

| 层 | 操作方 | 内容 |
|---|---|---|
| 系统层 | 管理员账号 / 云控制台 | 安装与配置反向代理、云平台防火墙、安装系统包、建账号 |
| 应用层 | 项目账号 | 接收本地 rsync 同步的代码、docker compose 起停、容器内运维命令 |
| 数据 | 项目账号 | 备份脚本与定时任务，备份文件在项目目录内 |

**新项目建账号 / 目录 / 密钥**（示例，按发行版微调）：

```bash
# 系统层一次性操作（管理员执行）
sudo useradd -m -s /bin/bash -G docker <账号>        # standard 档：docker 组、无 sudo（hardened/isolated 档去掉 -G docker）
sudo mkdir -p /opt/<项目名> && sudo chown <账号>:<账号> /opt/<项目名>
sudo -u <账号> mkdir -p /home/<账号>/.ssh /opt/<项目名>/backups

# 生成部署密钥，仅授权项目账号（root 不放）
sudo -u <账号> ssh-keygen -t ed25519 -f /home/<账号>/.ssh/<项目名>_deploy -N ""
sudo -u <账号> cp /home/<账号>/.ssh/<项目名>_deploy.pub /home/<账号>/.ssh/authorized_keys
```

> 要点：密钥只进项目账号的 `authorized_keys`；root 的授权里不放任何项目密钥。后续新项目共机沿用同一约定，互不授权。

## 3. Docker 架构（通用设计点）

三个文件各司其职：**Dockerfile**（构建镜像）、**docker-compose.yml**（编排与配置）、**docker-entrypoint.sh**（容器启动入口）。

以下为与具体技术栈无关的通用设计点：

- **多阶段构建产出最小运行时**：先装依赖、再构建产物，最终运行时阶段只拷产物与必要资源，镜像更小、依赖更干净、攻击面更小。
- **原生/被打包依赖显式拷贝**：构建工具（bundler / standalone 打包）的依赖追踪可能不全，原生二进制与被打包进内部 chunk 的库必须显式拷进运行时阶段，否则容器内报模块缺失。
- **迁移 CLI 与运行时隔离**：运行时不需要迁移 CLI，单独阶段/目录存放，镜像更小、依赖更干净。
- **数据卷**：`VOLUME /app/data`，配合 compose 绑定挂载持久化数据库与上传文件；备份 = 打包宿主机 `./data` 目录，迁移服务器 = 拷目录。
- **端口只绑回环**：容器端口只映射到 `127.0.0.1:<端口>`，不直接暴露公网；反向代理按域名路由到各项目端口并自动签发/续期 HTTPS 证书，防火墙只需开 80/443。
- **`.env` 不入库、`.env.example` 入库**：`.env` 提供密钥与开关，永不入库；`.env.example` 入库作为模板。
- **必须有 `.dockerignore`**：构建阶段的 `COPY . .` 会把构建上下文全部拷进镜像——没有 `.dockerignore` 时 `.env`（密钥）、`data/`（线上数据）、`.git` 都会进入镜像层，密钥随镜像泄露。模板见 `assets/deploy/dockerignore.tmpl`。
- **entrypoint 约定**：`set -e` 保证迁移失败即退出（容器进入 restart 循环，日志可见原因）；先迁移后启动——数据库结构和代码版本永远同步，不存在「代码上线了但忘了迁移」的窗口；`exec` 让服务进程成为 PID 1，信号与日志更干净。

> 四栈具体模板见 skill 的 `assets/deploy/` 目录（nextjs / python / go / static）；栈不在库中时，AI 按本节设计点参照现有模板现场编写。

## 4. Git 工作流与部署

- **每项目一个独立私有 GitHub 仓库**，仅作备份与版本管理；GitHub 与服务器之间不发生关系，两边都以本地为源头。
- **push 只与发布绑定**：本地 Commit 照常，开发期不要求每次提交都推送；仅在用户确认部署上线时，随发布流程推送远程仓库。
- **部署 = rsync 本地直推**：部署时把代码从本地直接 rsync 到服务器 `/opt/<项目名>` 重建；服务器上不检出 git、不手工改任何文件。
- **纪律：先 push、再部署**——发布推送在 rsync 之前完成，只要遵守这条，GitHub 和服务器内容就永远一致。
- **分支模型**：长期分支 `main`；任务分支 `task/<编号>-<名称>`；紧急修复 `hotfix/<编号>-<描述>`。不在 main 上直接开发未完成的任务。
- **Commit 规范**：`类型(编号): 说明`（feat / fix / docs / refactor / test / style / security / chore），一条 Commit 表达一件完整事情；发布提交用 `chore(release): 发布 vX.Y.Z`。
- **语义化版本 + 标签**：每个发布打 `vX.Y.Z` 标签，任何历史版本可精确检出。

**发布闭环**：

```text
本地验证 → 用户验收 → --no-ff 合回 main → push 远程仓库（先入库备份）
→ rsync 代码到服务器 → docker compose up -d --build（启动时自动迁移）
→ 线上验证 → chore(release) 提交 + 打 tag + push tag → 删除任务分支
```

**rsync 部署命令**（本地执行，推送到项目账号）：

```bash
# 排除敏感与运行时内容：.env 只在服务器维护，data/backups 是线上数据，docs/private 是本地私有资料，绝不可上服务器
rsync -az --delete \
  --exclude .git --exclude node_modules --exclude .env \
  --exclude data --exclude backups --exclude docs/private \
  -e "ssh -i ~/.ssh/<DEPLOY_KEY>" \
  ./ <DEPLOY_USER>@<PRODUCTION_SERVER_IP>:/opt/<项目名>/
```

> 要点：`--delete` 保证服务器目录与本地精确一致；排除项必须包含 `.env`、`data/`、`backups/`、`docs/private/`，否则一次部署就会覆盖线上密钥和数据、或把本地私有运维资料同步上服务器。

## 5. 新项目上线 Checklist

> 同内容已整理为可复制进项目 TODO 的清单：`assets/checklists/go-live-checklist.md`。

### A. 系统层一次性操作（管理员执行）

- [ ] 开通云服务器（免备案地区 / 大陆需 ICP 备案）
- [ ] DNS：添加 A 记录，`<域名>` → 服务器 IP
- [ ] 云控制台防火墙放行 80/443（部分厂商默认只放行 80，**443 要手动加**）
- [ ] 安装 Docker；创建项目账号（无 sudo；standard 档入 docker 组，按 §2 安全档位选择）
- [ ] 安装并配置反向代理（如 Caddy）：`<域名>` → `127.0.0.1:<端口>`
- [ ] 建 `/opt/<项目名>` 并授权项目账号；配置 SSH 部署密钥（不放 root，私钥拷回本地用于 rsync 部署）

### B. 项目侧文件（可模板化）

- [ ] Dockerfile：多阶段构建，原生/特殊模块显式拷贝
- [ ] docker-compose.yml：回环绑定、`./data` 挂载、`env_file: .env`
- [ ] docker-entrypoint.sh：先迁移再启动
- [ ] `cp .env.example .env` 并设置强密码/密钥
- [ ] 初始化脚本（建管理员、种子数据，按项目而定）
- [ ] 备份脚本 + crontab（归属项目账号，备份存 `/opt/<项目名>/backups/`，保留 N 份滚动）

### C. Git 与首次部署

- [ ] 私有仓库（备份用）；服务器不配 deploy key、不检出 git
- [ ] 首次部署：本地 rsync 全量代码到 `/opt/<项目名>`，在服务器配好 `.env` 后 `docker compose up -d --build`

### D. 日常维护（一句话）

发布 = 本地 push（备份）→ rsync 同步到服务器 → 服务器 `docker compose up -d --build`（自动迁移）；看日志 `docker compose logs -f <项目名>`；重启 `docker compose restart <项目名>`；备份按 crontab 自动执行，建议再同步到对象存储做异地容灾。

## 6. 信息登记与秘密边界

**信息登记**（「位置与引用」类信息）分两层：

- **可推导值可入库**：项目账号（建议默认 = 项目名，可独立修改）、应用/数据/备份目录（`/opt/<项目名>` 系）、默认密钥路径约定（`~/.ssh/<项目名>_deploy`）——登记进项目 `docs/project/PROJECT_INDEX.md` 的外部资源表与 `docs/guides/deployment.md`（骨架模板见 `assets/deploy/deployment.md.tmpl`）。域名、DNS 托管商与公开联系邮箱属公开信息，默认同样入库。
- **不可推导值必须隔离**：服务器 IP、SSH 端口、密钥真实路径（偏离默认约定时）、SSH 别名、crontab 具体调度、备份策略细节——只写入本地 `docs/private/ops.md`（`.gitignore` 排除，永不入库，需配独立私有备份通道）；其中部署脚本需要的五项（项目名/账号/服务器目录/IP/密钥路径）另以机器可读形式写进 `docs/private/deploy.env`（见下条）。入库文档对应位置只写占位符（`<PRODUCTION_SERVER_IP>`、`<DEPLOY_USER>` 等）+ 指向 ops.md 的注记。容器端口分配可入库（本机回环端口不构成基础设施指纹）。
- **部署脚本读取 `docs/private/deploy.env`**：部署五事实（`PROJECT_NAME` / `DEPLOY_USER` / `REMOTE_DIR` / `SERVER_IP` / `DEPLOY_KEY`）由该文件显式提供（模板见 `assets/project/deploy.env.tmpl`），脚本不从本地路径推导——三事实分离的落地载体就是它。同属 `.gitignore` 排除范围，永不入库。

**秘密边界**：秘密本体（私钥内容、密码、token）**永不进 Git**，只存在于服务器 `.env` 与用户本地。`.env.example` 入库仅作为结构模板，不带任何真实值。

## 7. 栈附录

### 7.1 Next.js + Prisma + SQLite（示例栈，模板见 `assets/deploy/nextjs/`）

Dockerfile 多阶段构建（四阶段）：

| 阶段 | 职责与关键点 |
|---|---|
| `deps` | `npm ci` 安装依赖；`npm rebuild <原生模块>` 兜底（postinstall 可能被 npm 脚本策略拦截） |
| `builder` | 复用 deps 的 node_modules，生成 Prisma Client，构建 standalone 产物 |
| `prisma-cli` | 单独安装 Prisma CLI，仅用于容器启动时执行迁移，与运行时依赖隔离 |
| `runner` | 最小生产运行时：拷 standalone 产物 + 必要资源 + entrypoint；按需装 sqlite3（容器内在线备份用） |

**关键设计点**：

- **standalone 依赖追踪不全，原生/特殊模块显式拷贝**：如 sharp 要拷整个 `sharp` + `@img` 目录；被打包进内部 chunk 的库（如 bcryptjs）若被独立脚本引用，也要显式拷一份。换栈时同类问题同理：先跑起来，报模块缺失就显式拷贝。
- **迁移 CLI 与运行时隔离**：运行时不需要迁移 CLI，单独阶段/目录存放，镜像更小、依赖更干净。
- **数据卷**：`VOLUME /app/data`，配合 compose 绑定挂载持久化数据库与上传文件。
- **绝对路径**：standalone 运行时一律用绝对路径（相对路径解析基准会变化），`DATABASE_URL` 等一律写绝对路径。

### 7.2 栈相关踩坑记录

- **npm rebuild 兜底原生模块**：原生依赖（如 Prisma engines、sharp）的 postinstall 可能被 npm 脚本策略拦截，依赖阶段与 CLI 阶段都要显式 rebuild。
- **standalone 依赖追踪不全**：原生二进制与被打包进 chunk 的库必须显式拷进运行时阶段，否则容器内报模块缺失。
- **迁移 CLI 找不到**：容器报 `prisma: not found` 之类 → 检查 entrypoint 引用的是独立 CLI 目录，而不是运行时 node_modules。
- **数据路径用绝对路径**：容器内/standalone 场景下相对路径解析基准会变化，`DATABASE_URL` 等一律写绝对路径。

> 其他栈（Python / Go / 静态站）模板见 `assets/deploy/` 对应目录；栈不在库中时，按 §3 通用设计点参照现有模板现场编写。

## 8. 踩坑记录（通用）

- **443 端口默认不放行**：部分云厂商实例模板默认放行 80 但不放行 443；HTTP 正常而 HTTPS 超时（curl 返回 000）时先查云平台防火墙。
- **服务器时间不准**：会导致 Cookie/证书时间校验异常（如后台登录后立即跳出），校准系统时间（chrony/ntpdate）。
- **大陆 VPS 备案前 80/443 被拦截**：域名无法访问属正常现象，先用免备案地区路线。
- **SQLite 在线备份一致性**：用 `sqlite3 <库文件> ".backup '<备份文件>'"` 在线备份保证一致性，再打包数据目录；恢复 = 停容器 → 覆盖数据目录 → 重启。
- **异地容灾缺口**：备份只在本机等于没有容灾，建议同步备份包到对象存储或另一台机器。
- **本机代理干扰验证与推送**：本机有 HTTP 代理时，`curl` 验证线上握手失败可加 `--noproxy '*'` 绕过；`git push` 直连 GitHub 超时或报 HTTP2 错误时，走代理推送：`git -c http.proxy=http://127.0.0.1:<代理端口> push`。
