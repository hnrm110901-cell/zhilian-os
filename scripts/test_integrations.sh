#!/bin/bash
# 屯象OS — 集成接口验证脚本
# 用法: bash scripts/test_integrations.sh

API="http://127.0.0.1:8000"

echo "===== 屯象OS 集成验证 ====="
echo ""

# 1. 登录获取 token
echo "[1/5] 登录..."
LOGIN=$(curl -s -X POST "$API/api/v1/auth/login" \
  -H 'Content-Type:application/json' \
  -d '{"username":"admin","password":"admin123"}')

TK=$(echo "$LOGIN" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)

if [ -z "$TK" ]; then
  echo "  登录失败: $LOGIN"
  exit 1
fi
echo "  登录成功"

AUTH="Authorization:Bearer $TK"

# 2. 查看商户列表
echo ""
echo "[2/5] 商户列表..."
MERCHANTS=$(curl -s "$API/api/v1/merchants" -H "$AUTH")
echo "$MERCHANTS" | python3 -c '
import sys,json
try:
    data=json.load(sys.stdin)
    if isinstance(data, list):
        for m in data:
            print(f"  {m.get(\"brand_name\",\"?\")} ({m.get(\"brand_id\",\"?\")}) - {m.get(\"store_count\",0)}店 - {m.get(\"status\",\"?\")}")
    elif isinstance(data, dict) and "detail" in data:
        print(f"  错误: {data[\"detail\"]}")
    else:
        print(f"  响应: {json.dumps(data,ensure_ascii=False)[:300]}")
except Exception as e:
    print(f"  解析失败: {e}")
'

# 3. 查看已有订单
echo ""
echo "[3/5] 数据库订单统计..."
docker exec zhilian-postgres psql -U zhilian -d zhilian_os -t -c \
  "SELECT coalesce(sales_channel,'unknown') as ch, count(*) as cnt FROM orders GROUP BY sales_channel ORDER BY cnt DESC;" 2>/dev/null
TOTAL=$(docker exec zhilian-postgres psql -U zhilian -d zhilian_os -t -c "SELECT count(*) FROM orders;" 2>/dev/null)
echo "  订单总数: $TOTAL"

# 4. 触发品智POS同步（尝在一起-文化城店，昨天）
echo ""
echo "[4/5] 品智POS同步测试（尝在一起-文化城店）..."
YESTERDAY=$(date -d 'yesterday' '+%Y-%m-%d' 2>/dev/null || date -v-1d '+%Y-%m-%d' 2>/dev/null)
echo "  同步日期: $YESTERDAY"

SYNC_RESULT=$(curl -s -X POST "$API/api/v1/integrations/pos-sync" \
  -H "$AUTH" \
  -H 'Content-Type:application/json' \
  -d "{\"adapter\":\"pinzhi\",\"sync_date\":\"$YESTERDAY\",\"store_ids\":[\"CZYZ-2461\"]}")

echo "$SYNC_RESULT" | python3 -c '
import sys,json
try:
    d=json.load(sys.stdin)
    if "stores" in d:
        for s in d["stores"]:
            print(f"  门店: {s.get("store_name","?")} | DB订单: {s.get("orders_in_db",0)} | POS订单: {s.get("pos_orders",0)} | 差异: {s.get("diff_orders",0)}")
        print(f"  同步成功: {d.get("success",False)}")
    elif "detail" in d:
        print(f"  错误: {d["detail"]}")
    else:
        print(f"  响应: {json.dumps(d,ensure_ascii=False)[:300]}")
except:
    print(f"  原始响应: {sys.stdin.read()[:300] if hasattr(sys.stdin,"read") else "解析失败"}")
' 2>/dev/null

# 5. 品智健康检查
echo ""
echo "[5/5] 适配器健康检查..."
HEALTH=$(curl -s "$API/api/v1/external-systems" -H "$AUTH" 2>/dev/null)
if [ -n "$HEALTH" ]; then
  echo "$HEALTH" | python3 -c '
import sys,json
try:
    d=json.load(sys.stdin)
    if isinstance(d,dict):
        for k,v in d.items():
            st=v.get("status","?") if isinstance(v,dict) else v
            print(f"  {k}: {st}")
    else:
        print(f"  {json.dumps(d,ensure_ascii=False)[:200]}")
except:
    pass
' 2>/dev/null
else
  echo "  (无健康检查端点或无响应)"
fi

echo ""
echo "===== 验证完成 ====="
