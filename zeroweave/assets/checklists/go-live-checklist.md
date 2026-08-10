# 新项目上线 Checklist

> 来源：ZeroWeave 参考规范 `references/deployment-guide.md` §5。
> 使用：复制进项目 TODO；可推导占位符（`<项目名>`、`<域名>`、`<端口>`、`<账号>`）落地时替换。
> 隐私线：本清单入库，服务器 IP 等真实运维值不要写进来——真实值统一查本地 `docs/private/ops.md`（不入库）。

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
- [ ] 首次部署：本地 rsync 全量代码到 `/opt/<项目名>`，在服务器配好 `.env` 后 `docker compose up -d --build`

## D. 日常维护（一句话）

- [ ] 发布 = 本地 push（备份）→ rsync 同步到服务器 → 服务器 `docker compose up -d --build`（自动迁移）
- [ ] 看日志：`docker compose logs -f <项目名>`；重启：`docker compose restart <项目名>`
- [ ] 备份按 crontab 自动执行，建议再同步到对象存储做异地容灾
