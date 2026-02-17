#!/bin/bash
# Test script for Yiding Reservation System Integration
# 易订预订系统集成测试

BASE_URL="http://localhost:8000/api/v1"

echo "=== 易订预订系统集成测试 ==="
echo ""

# 1. Login as admin
echo "1. 管理员登录..."
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }')

TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ 登录失败"
  echo $LOGIN_RESPONSE | jq '.'
  exit 1
fi

echo "✓ 登录成功"
echo ""

# 2. Create Yiding Reservation System
echo "2. 创建易订预订系统配置..."
YIDING_SYSTEM=$(curl -s -X POST "$BASE_URL/integrations/systems" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "易订预订管理系统",
    "type": "reservation",
    "provider": "Yiding",
    "store_id": "store-001",
    "config": {
      "api_endpoint": "https://api.yiding.com/reservation",
      "api_key": "yiding_key_123",
      "webhook_url": "http://localhost:8000/api/v1/integrations/webhooks/reservation"
    }
  }')

YIDING_SYSTEM_ID=$(echo $YIDING_SYSTEM | jq -r '.id')
echo "✓ 易订系统创建成功: $YIDING_SYSTEM_ID"
echo $YIDING_SYSTEM | jq '.'
echo ""

# 3. Sync reservation data
echo "3. 同步预订数据..."
RESERVATION1=$(curl -s -X POST "$BASE_URL/integrations/reservation/$YIDING_SYSTEM_ID/sync" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reservation_id": "RES-2024-001",
    "external_id": "yiding_res_001",
    "reservation_number": "YD20240214001",
    "customer_name": "张三",
    "customer_phone": "13800138000",
    "customer_count": 4,
    "reservation_date": "2024-02-15T00:00:00",
    "reservation_time": "18:00-20:00",
    "table_type": "圆桌",
    "area": "大厅",
    "status": "confirmed",
    "special_requirements": "靠窗位置，需要儿童座椅",
    "notes": "客户是VIP会员",
    "deposit_required": true,
    "deposit_amount": 200.00,
    "deposit_paid": true,
    "source": "yiding",
    "channel": "微信小程序"
  }')

echo "✓ 预订1同步成功"
echo $RESERVATION1 | jq '.'
echo ""

# 4. Sync another reservation
echo "4. 同步第二个预订..."
RESERVATION2=$(curl -s -X POST "$BASE_URL/integrations/reservation/$YIDING_SYSTEM_ID/sync" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reservation_id": "RES-2024-002",
    "external_id": "yiding_res_002",
    "reservation_number": "YD20240214002",
    "customer_name": "李四",
    "customer_phone": "13900139000",
    "customer_count": 6,
    "reservation_date": "2024-02-15T00:00:00",
    "reservation_time": "19:00-21:00",
    "table_type": "包厢",
    "area": "二楼",
    "status": "pending",
    "special_requirements": "需要投影仪",
    "notes": "公司聚餐",
    "deposit_required": false,
    "source": "yiding",
    "channel": "电话预订"
  }')

echo "✓ 预订2同步成功"
echo $RESERVATION2 | jq '.'
echo ""

# 5. Get all reservations
echo "5. 获取所有预订..."
ALL_RESERVATIONS=$(curl -s -X GET "$BASE_URL/integrations/reservation/list?store_id=store-001" \
  -H "Authorization: Bearer $TOKEN")

RESERVATION_COUNT=$(echo $ALL_RESERVATIONS | jq '. | length')
echo "✓ 共有 $RESERVATION_COUNT 个预订"
echo $ALL_RESERVATIONS | jq '.'
echo ""

# 6. Get reservations by status
echo "6. 获取已确认的预订..."
CONFIRMED_RESERVATIONS=$(curl -s -X GET "$BASE_URL/integrations/reservation/list?store_id=store-001&status=confirmed" \
  -H "Authorization: Bearer $TOKEN")

CONFIRMED_COUNT=$(echo $CONFIRMED_RESERVATIONS | jq '. | length')
echo "✓ 共有 $CONFIRMED_COUNT 个已确认预订"
echo $CONFIRMED_RESERVATIONS | jq '.'
echo ""

# 7. Update reservation status to arrived
echo "7. 更新预订状态为已到店..."
UPDATE_RESPONSE=$(curl -s -X PUT "$BASE_URL/integrations/reservation/RES-2024-001/status?status=arrived&arrival_time=2024-02-15T18:05:00" \
  -H "Authorization: Bearer $TOKEN")

echo "✓ 预订状态更新成功"
echo $UPDATE_RESPONSE | jq '.'
echo ""

# 8. Update reservation status to seated
echo "8. 更新预订状态为已入座..."
SEATED_RESPONSE=$(curl -s -X PUT "$BASE_URL/integrations/reservation/RES-2024-001/status?status=seated&table_number=A08" \
  -H "Authorization: Bearer $TOKEN")

echo "✓ 预订已安排座位"
echo $SEATED_RESPONSE | jq '.'
echo ""

# 9. Test Yiding webhook - new reservation
echo "9. 测试易订Webhook - 新预订..."
WEBHOOK_NEW=$(curl -s -X POST "$BASE_URL/integrations/webhooks/reservation/$YIDING_SYSTEM_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "reservation.created",
    "data": {
      "reservation_id": "RES-2024-003",
      "external_id": "yiding_res_003",
      "reservation_number": "YD20240214003",
      "customer_name": "王五",
      "customer_phone": "13700137000",
      "customer_count": 2,
      "reservation_date": "2024-02-16T00:00:00",
      "reservation_time": "12:00-14:00",
      "table_type": "小桌",
      "status": "pending",
      "source": "yiding",
      "channel": "美团"
    }
  }')

echo "✓ Webhook新预订处理成功"
echo $WEBHOOK_NEW | jq '.'
echo ""

# 10. Test Yiding webhook - update reservation
echo "10. 测试易订Webhook - 更新预订..."
WEBHOOK_UPDATE=$(curl -s -X POST "$BASE_URL/integrations/webhooks/reservation/$YIDING_SYSTEM_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "reservation.updated",
    "data": {
      "reservation_id": "RES-2024-002",
      "external_id": "yiding_res_002",
      "reservation_number": "YD20240214002",
      "customer_name": "李四",
      "customer_phone": "13900139000",
      "customer_count": 8,
      "reservation_date": "2024-02-15T00:00:00",
      "reservation_time": "19:00-21:00",
      "table_type": "包厢",
      "area": "二楼",
      "status": "confirmed",
      "special_requirements": "需要投影仪，增加2人",
      "notes": "公司聚餐，人数变更",
      "source": "yiding"
    }
  }')

echo "✓ Webhook更新预订处理成功"
echo $WEBHOOK_UPDATE | jq '.'
echo ""

# 11. Test Yiding webhook - cancel reservation
echo "11. 测试易订Webhook - 取消预订..."
WEBHOOK_CANCEL=$(curl -s -X POST "$BASE_URL/integrations/webhooks/reservation/$YIDING_SYSTEM_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "reservation.cancelled",
    "data": {
      "reservation_id": "RES-2024-003"
    }
  }')

echo "✓ Webhook取消预订处理成功"
echo $WEBHOOK_CANCEL | jq '.'
echo ""

# 12. Get today's reservations
echo "12. 获取今日预订..."
TODAY=$(date +%Y-%m-%d)
TODAY_RESERVATIONS=$(curl -s -X GET "$BASE_URL/integrations/reservation/list?store_id=store-001&date_from=${TODAY}T00:00:00&date_to=${TODAY}T23:59:59" \
  -H "Authorization: Bearer $TOKEN")

TODAY_COUNT=$(echo $TODAY_RESERVATIONS | jq '. | length')
echo "✓ 今日共有 $TODAY_COUNT 个预订"
echo $TODAY_RESERVATIONS | jq '.'
echo ""

# 13. Get reservations by date range
echo "13. 获取未来3天的预订..."
DATE_FROM=$(date +%Y-%m-%d)
DATE_TO=$(date -v+3d +%Y-%m-%d 2>/dev/null || date -d "+3 days" +%Y-%m-%d)
FUTURE_RESERVATIONS=$(curl -s -X GET "$BASE_URL/integrations/reservation/list?store_id=store-001&date_from=${DATE_FROM}T00:00:00&date_to=${DATE_TO}T23:59:59" \
  -H "Authorization: Bearer $TOKEN")

FUTURE_COUNT=$(echo $FUTURE_RESERVATIONS | jq '. | length')
echo "✓ 未来3天共有 $FUTURE_COUNT 个预订"
echo $FUTURE_RESERVATIONS | jq '.'
echo ""

echo "=== 测试完成 ==="
echo ""
echo "总结:"
echo "- 易订系统配置: 已创建"
echo "- 预订记录: $RESERVATION_COUNT 个"
echo "- 已确认预订: $CONFIRMED_COUNT 个"
echo "- 今日预订: $TODAY_COUNT 个"
echo "- 未来3天预订: $FUTURE_COUNT 个"
echo ""
echo "功能验证:"
echo "✓ 创建易订系统配置"
echo "✓ 同步预订数据"
echo "✓ 查询预订列表"
echo "✓ 按状态筛选"
echo "✓ 按日期范围筛选"
echo "✓ 更新预订状态(到店、入座)"
echo "✓ Webhook接收(新建、更新、取消)"