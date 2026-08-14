# 静态站部署方案（无容器）

适用：纯静态站点（Astro / Vite / Next.js 静态导出 / 纯 HTML 等）。发布目录按框架而定：
Vite/Astro → `dist/`，Next.js 静态导出 → `out/`，纯 HTML → 建议 `public/`。
静态站没有服务进程、没有数据库迁移，容器化收益有限，默认走「无容器」方案。

## 部署事实（docs/private/deploy.env）

- 部署五事实（`PROJECT_NAME` / `DEPLOY_USER` / `REMOTE_DIR` / `SERVER_IP` / `DEPLOY_KEY`）统一由
  本地 `docs/private/deploy.env` 提供（已 gitignore，永不入库；模板见 `assets/project/deploy.env.tmpl`）。
- 三事实分离：本地目录名 ≠ 项目名 ≠ 服务器账号，脚本不从路径推导部署事实。
- 发布目录由 `STATIC_OUTPUT_DIR` 控制（Vite/Astro=`dist`、Next.js 静态导出=`out`、纯 HTML=`public`）；
  找不到发布目录即报错退出（fail-closed，**绝不发布项目根**；含 `STATIC_OUTPUT_DIR=.` 或越出项目的路径会被拒绝）。

## 流程

1. **本地构建**：`npm run build`，产物输出到发布目录（`dist/` / `out/` / `public/`）
2. **配置 deploy.env**：在 `docs/private/deploy.env` 填好五事实；`REMOTE_DIR` 填服务器发布目录
   （静态站如 `/opt/<项目名>/dist`）；发布目录非默认时加一行 `STATIC_OUTPUT_DIR="out"`（或 `public`）
3. **本地直推**：执行 `deploy-rsync-static.sh.tmpl`（落地为脚本），只把发布目录 rsync 到服务器
4. **服务器伺服**：共享 Caddy 直接以文件伺服该目录，**不走容器**，无需 docker

> 改完发布目录再次 rsync 即可生效；`file_server` 按请求读盘，无需重启。
> 仅当改动服务器 Caddyfile 后才需要 `caddy reload`。

## 服务器 Caddyfile 片段

```
<域名> {
    # 路径与 deploy.env 的 REMOTE_DIR 一致
    root * /opt/<项目名>/dist
    file_server
    encode zstd gzip
}
```

## 若坚持容器化

可用 `caddy:alpine` 镜像挂载发布目录起容器：

- Dockerfile：`FROM caddy:alpine`，把 `/opt/<项目名>/dist` 以 volume 挂入容器（或构建时 COPY 进镜像）
- compose：参照通用模板 `assets/deploy/docker-compose.yml.tmpl` 修改（回环绑定、`.env` 等按需取舍；静态站通常不需要 `./data` 挂载）
