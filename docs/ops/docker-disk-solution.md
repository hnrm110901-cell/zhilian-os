# Docker 磁盘空间管理方案

## 根因分析

| 原因 | 影响 | 频次 |
|------|------|------|
| `--no-cache` 全量构建 | 每次产生~2GB新层，旧层不自动删 | 每次部署 |
| 多阶段构建 builder 缓存 | 中间层缓存 3-5GB | 累积 |
| 悬空镜像(dangling) | 旧版本镜像未标记删除 | 每次构建 |
| 服务器磁盘 118GB | Docker+OS+代码 占80%+ | 固定 |

## 方案实施

### 1. 自动清理 Cron（已实施）

```bash
# 每天凌晨3点自动清理悬空镜像和构建缓存
echo '0 3 * * * docker image prune -f && docker builder prune -f --keep-storage=5GB 2>/dev/null' | crontab -
```

### 2. 构建策略优化

```bash
# ✅ 正确：利用缓存，只在requirements.txt变化时才--no-cache
docker compose -f docker-compose.prod.yml build api-gateway

# ❌ 避免：每次都全量构建
# docker compose -f docker-compose.prod.yml build api-gateway --no-cache
```

### 3. 部署后清理（加入部署脚本）

```bash
# 部署完成后立即清理旧镜像
docker image prune -f
```

### 4. 未来：GitHub Actions 构建（推荐）

将构建转移到 CI/CD，服务器只 pull 不 build：
- 构建在 GitHub Actions 的临时环境完成
- 推到 GitHub Container Registry (ghcr.io)
- 服务器 `docker pull` + `docker compose up -d`
- 彻底解决磁盘问题
