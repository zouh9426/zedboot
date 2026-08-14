# 新项目上线 Checklist

> 来源：zedboot 参考规范 `references/deployment-guide.md` §5。
> 使用：复制进项目 TODO；可推导占位符（`<项目名>`、`<域名>`、`<端口>`、`<账号>`）落地时替换。
> 隐私线：本清单入库，服务器 IP 等真实运维值不要写进来——真实值统一查本地 `docs/private/ops.md`（不入库）。

## 静态站点（无容器）替代说明

> 若本项目为静态站（Astro / Vite / Next.js 静态导出等，构建产物为发布目录：Vite/Astro=`dist`、Next.js 静态导出=`out`、纯 HTML=`public`，见 zedboot `assets/deploy/static/README.md`），走「无容器」方案，下列 Docker 相关条目**剔除不适用**，按下表替换；其余条目照常。

- **A「安装 Docker；创建项目账号（docker 组、无 sudo）」** → 剔除 Docker 安装；创建项目账号（无 sudo，无需 docker 组）；服务器需已装共享 Caddy
- **A「安装并配置反向代理：`<域名>` → `127.0.0.1:<端口>`」** → 改为配置共享 Caddy：`root * /opt/<项目名>/dist` + `file_server`（无容器端口）
- **B「Dockerfile / docker-compose.yml / docker-entrypoint.sh」** → 剔除；替换为：有构建步骤的项目先构建（`npm run build`）；纯 HTML 无构建，直接维护 `public/` 后执行部署脚本；确认发布目录（`STATIC_OUTPUT_DIR`，dist/out/public 按框架）存在且为最新
- **B「备份脚本 + crontab（存 `/opt/<项目名>/backups/`）」** → 剔除 backup.sh 数据备份；静态站无应用数据，备份 = 仓库本身 + 服务器 `/opt/<项目名>/dist` 目录
- **C「首次部署：rsync 全量代码 → `docker compose up -d --build`」** → 替换为：本地执行 `deploy-rsync-static.sh`（已带可执行位），只把发布目录 rsync 到服务器 `REMOTE_DIR`（如 `/opt/<项目名>/dist`），共享 Caddy 直接伺服即生效
- **D「发布 = rsync → `docker compose up -d --build`」** → 替换为：有构建步骤的项目先构建（`npm run build`）→ `./deploy-rsync-static.sh`；纯 HTML 无构建，直接维护 `public/` 后执行部署脚本
- **D「看日志 `docker compose logs` / 重启 `docker compose restart`」** → 剔除；无容器、无应用日志、无需重启，改完发布目录重新 rsync 即生效；仅改动服务器 Caddyfile 后才需 `caddy reload`

## A. 系统层一次性操作（管理员执行）

- [ ] 开通云服务器（免备案地区 / 大陆需 ICP 备案）
- [ ] DNS：添加 A 记录，`<域名>` → 服务器 IP
- [ ] 云控制台防火墙放行 80/443（部分厂商默认只放行 80，**443 要手动加**）
- [ ] 安装 Docker；创建项目账号（docker 组、无 sudo）
- [ ] 安装并配置反向代理（如 Caddy）：`<域名>` → `127.0.0.1:<端口>`
- [ ] 建 `/opt/<项目名>` 并授权项目账号；配置 SSH 部署密钥（不放 root，私钥拷回本地用于 rsync 部署）

## B. 项目侧文件（可模板化）

- [ ] Dockerfile：多阶段构建，原生/特殊模块显式拷贝
- [ ] docker-compose.yml：回环绑定、`./data` 挂载、`env_file: .env`
- [ ] docker-entrypoint.sh：先迁移再启动
- [ ] `cp .env.example .env` 并设置强密码/密钥
- [ ] 初始化脚本（建管理员、种子数据，按项目而定）
- [ ] 备份脚本 + crontab（归属项目账号，备份存 `/opt/<项目名>/backups/`，保留 N 份滚动）

## C. Git 与首次部署

- [ ] 私有仓库（备份用）；服务器不配 deploy key、不检出 git
- [ ] 首次部署：本地配好 `docs/private/deploy.env`（部署六事实）后执行 `./deploy-rsync.sh`，在服务器配好 `.env` 后 `docker compose up -d --build`
- [ ] 更新 `docs/private/backup-manifest.conf`：ZB_DEPLOYED=true + 填实服务器字段（zedback 每日备份据此拉取服务器数据，不改卡则服务器数据静默不进备份）

## D. 日常维护（一句话）

- [ ] 发布 = 本地 push（备份）→ `./deploy-rsync.sh`（读取 `docs/private/deploy.env` 六事实）→ 服务器 `docker compose up -d --build`（自动迁移）
- [ ] 看日志：`docker compose logs -f <项目名>`；重启：`docker compose restart <项目名>`
- [ ] 备份按 crontab 自动执行，建议再同步到对象存储做异地容灾
