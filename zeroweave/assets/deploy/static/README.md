# 静态站部署方案（无容器）

适用：纯静态站点（Astro / Vite / Next.js 静态导出等），构建产物为 `dist/` 目录。
静态站没有服务进程、没有数据库迁移，容器化收益有限，默认走「无容器」方案。

## 流程

1. **本地构建**：`npm run build`，产物输出到 `dist/`
2. **本地直推**：执行 `deploy-rsync-static.sh.tmpl`（落地为脚本后用环境变量传入真实值，见脚本头注释），只把 `dist/` rsync 到服务器 `/opt/<项目名>/dist`
3. **服务器伺服**：共享 Caddy 直接以文件伺服该目录，**不走容器**，无需 docker

> 改完 `dist/` 再次 rsync 即可生效；`file_server` 按请求读盘，无需重启。
> 仅当改动服务器 Caddyfile 后才需要 `caddy reload`。

## 服务器 Caddyfile 片段

```
<域名> {
    root * /opt/<项目名>/dist
    file_server
    encode zstd gzip
}
```

## 若坚持容器化

可用 `caddy:alpine` 镜像挂载 dist 起容器：

- Dockerfile：`FROM caddy:alpine`，把 `/opt/<项目名>/dist` 以 volume 挂入容器（或构建时 COPY 进镜像）
- compose：参照通用模板 `assets/deploy/docker-compose.yml.tmpl` 修改（回环绑定、`.env` 等按需取舍；静态站通常不需要 `./data` 挂载）
