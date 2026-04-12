#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# 屯象OS Gate 1 手动操作指令
# 服务器: 42.194.229.21
# 执行顺序: 严格按 Step 1→5 执行，不可跳步
# 创建日期: 2026-03-28
# ═══════════════════════════════════════════════════════════════

set -e

echo "╔═══════════════════════════════════════════════════╗"
echo "║  屯象OS Gate 1 安全加固 — 手动操作脚本            ║"
echo "║  请在服务器上逐步执行，每步确认后再继续            ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""

# ─────────────────────────────────────────────────────────────
# Step 1: 安装工具
# ─────────────────────────────────────────────────────────────
echo "=== Step 1: 安装必要工具 ==="
echo ""
echo "执行以下命令:"
echo ""
echo "  pip install git-filter-repo pre-commit"
echo "  brew install git-secrets  # macOS"
echo "  # 或 apt-get install git-secrets  # Ubuntu"
echo ""
echo "按回车继续..."
read -r

# ─────────────────────────────────────────────────────────────
# Step 2: 备份当前凭证（在清除前先保存到安全位置）
# ─────────────────────────────────────────────────────────────
echo "=== Step 2: 备份凭证到安全位置 ==="
echo ""
echo "!! 重要 !! 先把凭证值复制到安全的地方（密码管理器/腾讯云密钥管理）"
echo ""
echo "执行以下命令查看当前凭证（复制后保存）:"
echo ""
echo "  cat config/merchants/.env.czyz"
echo "  cat config/merchants/.env.zqx"
echo "  cat config/merchants/.env.sgc"
echo ""
echo "确认已将所有凭证值保存到安全位置后，按回车继续..."
read -r

# ─────────────────────────────────────────────────────────────
# Step 3: 从git历史中清除泄露的凭证文件
# ─────────────────────────────────────────────────────────────
echo "=== Step 3: 清除git历史中的凭证 ==="
echo ""
echo "!! 警告 !! 此操作不可逆，会重写git历史"
echo "!! 确保已完成Step 2的备份 !!"
echo ""
echo "执行以下命令:"
echo ""
echo "  cd /path/to/tunxiang"
echo ""
echo "  # 3.1 创建安全备份"
echo "  git tag pre-cleanup-backup"
echo ""
echo "  # 3.2 清除3个商户凭证文件（从所有历史中）"
echo "  git filter-repo \\"
echo "    --path config/merchants/.env.czyz \\"
echo "    --path config/merchants/.env.zqx \\"
echo "    --path config/merchants/.env.sgc \\"
echo "    --invert-paths \\"
echo "    --force"
echo ""
echo "  # 3.3 验证清除成功"
echo "  git log --all --full-history -- config/merchants/.env.czyz"
echo "  # 应该返回空（无任何commit记录）"
echo ""
echo "  # 3.4 如果有远程仓库，需要 force push"
echo "  # git remote add origin <url>  # filter-repo会删除remote"
echo "  # git push --force --all"
echo "  # git push --force --tags"
echo ""
echo "按回车继续..."
read -r

# ─────────────────────────────────────────────────────────────
# Step 4: 将凭证迁移到服务器环境变量
# ─────────────────────────────────────────────────────────────
echo "=== Step 4: 配置服务器环境变量 ==="
echo ""
echo "在生产服务器(42.194.229.21)上，将凭证写入 .env.production"
echo "（此文件已在 .gitignore 中，不会被提交）"
echo ""
echo "  vim /path/to/tunxiang/apps/api-gateway/.env.production"
echo ""
echo "添加以下变量（用Step 2保存的真实值替换）:"
echo ""
echo "  # === 尝在一起 ==="
echo "  CZYZ_PINZHI_BASE_URL=https://czyq.pinzhikeji.net"
echo "  CZYZ_PINZHI_API_TOKEN=<从密码管理器获取>"
echo "  CZYZ_AOQIWEI_BASE_URL=<从密码管理器获取>"
echo "  CZYZ_AOQIWEI_APP_ID=<从密码管理器获取>"
echo "  CZYZ_AOQIWEI_APP_KEY=<从密码管理器获取>"
echo "  CZYZ_AOQIWEI_MERCHANT_ID=<从密码管理器获取>"
echo ""
echo "  # === 最黔线 ==="
echo "  ZQX_PINZHI_BASE_URL=<从密码管理器获取>"
echo "  ZQX_PINZHI_API_TOKEN=<从密码管理器获取>"
echo "  ZQX_AOQIWEI_BASE_URL=<从密码管理器获取>"
echo "  ZQX_AOQIWEI_APP_ID=<从密码管理器获取>"
echo "  ZQX_AOQIWEI_APP_KEY=<从密码管理器获取>"
echo "  ZQX_AOQIWEI_MERCHANT_ID=<从密码管理器获取>"
echo ""
echo "  # === 尚宫厨 ==="
echo "  SGC_PINZHI_BASE_URL=<从密码管理器获取>"
echo "  SGC_PINZHI_API_TOKEN=<从密码管理器获取>"
echo "  SGC_AOQIWEI_BASE_URL=<从密码管理器获取>"
echo "  SGC_AOQIWEI_APP_ID=<从密码管理器获取>"
echo "  SGC_AOQIWEI_APP_KEY=<从密码管理器获取>"
echo "  SGC_AOQIWEI_MERCHANT_ID=<从密码管理器获取>"
echo "  SGC_COUPON_BASE_URL=<从密码管理器获取>"
echo "  SGC_COUPON_APP_ID=<从密码管理器获取>"
echo "  SGC_COUPON_APP_KEY=<从密码管理器获取>"
echo ""
echo "按回车继续..."
read -r

# ─────────────────────────────────────────────────────────────
# Step 5: 联系品智/奥琦玮轮换Token
# ─────────────────────────────────────────────────────────────
echo "=== Step 5: 轮换已泄露的Token ==="
echo ""
echo "因为旧Token已在git历史中暴露，必须申请新的:"
echo ""
echo "  [ ] 品智POS — 联系品智技术支持，轮换以下Token:"
echo "      - CZYZ_PINZHI_API_TOKEN（尝在一起）"
echo "      - ZQX_PINZHI_API_TOKEN（最黔线）"
echo "      - SGC_PINZHI_API_TOKEN（尚宫厨）"
echo "      - 各门店独立Token（共14个，见 docs/credential-migration-guide.md）"
echo ""
echo "  [ ] 奥琦玮 — 联系奥琦玮技术支持，轮换以下Key:"
echo "      - CZYZ_AOQIWEI_APP_KEY"
echo "      - ZQX_AOQIWEI_APP_KEY"
echo "      - SGC_AOQIWEI_APP_KEY"
echo ""
echo "  [ ] 尚宫厨优惠券 — 轮换:"
echo "      - SGC_COUPON_APP_KEY"
echo ""
echo "  轮换完成后，更新 .env.production 中的新值"
echo ""
echo "按回车继续..."
read -r

# ─────────────────────────────────────────────────────────────
# Step 6: 执行RLS安全迁移
# ─────────────────────────────────────────────────────────────
echo "=== Step 6: 执行RLS安全迁移 ==="
echo ""
echo "此迁移修复两个CRITICAL安全漏洞:"
echo "  CRITICAL-001: bom_templates/bom_items/waste_events RLS变量不一致"
echo "  CRITICAL-002: RLS策略NULL绕过漏洞"
echo ""
echo "执行以下命令:"
echo ""
echo "  cd /path/to/tunxiang/apps/api-gateway"
echo ""
echo "  # 6.1 检查当前迁移状态"
echo "  alembic current"
echo ""
echo "  # 6.2 查看待执行的迁移"
echo "  alembic history --verbose | head -20"
echo ""
echo "  # 6.3 执行迁移（修复RLS）"
echo "  alembic upgrade head"
echo ""
echo "  # 6.4 验证迁移成功"
echo "  alembic current"
echo "  # 应显示 rls_fix_001 (head)"
echo ""
echo "  # 6.5 验证RLS策略已修复（连接psql）"
echo "  psql -U zhilian -d zhilian_os -c \\"
echo "    \"SELECT tablename, policyname FROM pg_policies"
echo "     WHERE tablename IN ('bom_templates','bom_items','waste_events')"
echo "     ORDER BY tablename, policyname;\""
echo "  # 应显示每张表4条策略（select/insert/update/delete）"
echo "  # 且策略中使用 app.current_tenant（非 app.current_store_id）"
echo ""
echo "按回车继续..."
read -r

# ─────────────────────────────────────────────────────────────
# Step 7: 启用pre-commit + git-secrets
# ─────────────────────────────────────────────────────────────
echo "=== Step 7: 启用代码安全扫描 ==="
echo ""
echo "  cd /path/to/tunxiang"
echo ""
echo "  # 7.1 启用pre-commit"
echo "  pre-commit install"
echo "  pre-commit install --hook-type commit-msg"
echo ""
echo "  # 7.2 配置git-secrets"
echo "  chmod +x scripts/setup-git-secrets.sh"
echo "  ./scripts/setup-git-secrets.sh"
echo ""
echo "  # 7.3 验证 — 全量扫描一次"
echo "  pre-commit run --all-files 2>&1 | tail -20"
echo "  git secrets --scan 2>&1 | tail -10"
echo ""
echo "  # 7.4 运行一次detect-secrets更新baseline"
echo "  pip install detect-secrets"
echo "  detect-secrets scan > .secrets.baseline"
echo ""
echo "按回车继续..."
read -r

# ─────────────────────────────────────────────────────────────
# Step 8: 重启服务验证
# ─────────────────────────────────────────────────────────────
echo "=== Step 8: 重启服务验证 ==="
echo ""
echo "  cd /path/to/tunxiang"
echo ""
echo "  # 8.1 重启所有服务（加载新环境变量）"
echo "  docker compose -f docker-compose.prod.yml down"
echo "  docker compose -f docker-compose.prod.yml up -d"
echo ""
echo "  # 8.2 检查服务健康状态"
echo "  docker compose -f docker-compose.prod.yml ps"
echo "  # 所有容器应为 healthy/running"
echo ""
echo "  # 8.3 验证API可访问"
echo "  curl -sf http://127.0.0.1:8000/api/v1/ready && echo 'API OK'"
echo ""
echo "  # 8.4 验证POS凭证可用（用新Token测试品智API）"
echo "  curl -sf 'https://czyq.pinzhikeji.net/api/ping' \\"
echo "    -H 'Authorization: Bearer \$CZYZ_PINZHI_API_TOKEN'"
echo "  # 应返回200"
echo ""

echo ""
echo "╔═══════════════════════════════════════════════════╗"
echo "║  Gate 1 检查清单                                   ║"
echo "╠═══════════════════════════════════════════════════╣"
echo "║  [ ] git历史中无凭证文件                            ║"
echo "║  [ ] 所有Token已轮换并写入.env.production           ║"
echo "║  [ ] RLS迁移已执行 (alembic current = rls_fix_001) ║"
echo "║  [ ] pre-commit + git-secrets 已启用               ║"
echo "║  [ ] 服务重启后API正常响应                          ║"
echo "║  [ ] POS API用新Token可正常调用                     ║"
echo "╠═══════════════════════════════════════════════════╣"
echo "║  全部打勾 → Gate 1 通过 → 可接入真实客户数据        ║"
echo "╚═══════════════════════════════════════════════════╝"
