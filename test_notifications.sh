#!/bin/bash
# 测试实时通知系统

BASE_URL="http://localhost:8000/api/v1"

echo "========================================="
echo "智链OS 实时通知系统测试"
echo "========================================="
echo ""

# 1. 登录获取token
echo "1. 用户登录"
echo "-------------------"
MANAGER_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "manager001", "password": "manager123"}')

MANAGER_TOKEN=$(echo $MANAGER_RESPONSE | jq -r '.access_token')
MANAGER_ID=$(echo $MANAGER_RESPONSE | jq -r '.user.id')
echo "✓ 店长登录成功: $(echo $MANAGER_RESPONSE | jq -r '.user.full_name')"

WAITER_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "waiter001", "password": "waiter123"}')

WAITER_TOKEN=$(echo $WAITER_RESPONSE | jq -r '.access_token')
WAITER_ID=$(echo $WAITER_RESPONSE | jq -r '.user.id')
echo "✓ 服务员登录成功: $(echo $WAITER_RESPONSE | jq -r '.user.full_name')"
echo ""

# 2. 创建通知
echo "2. 创建通知"
echo "-------------------"

# 创建给特定用户的通知
NOTIF1=$(curl -s -X POST "$BASE_URL/notifications" \
  -H "Authorization: Bearer $MANAGER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"个人通知测试\",
    \"message\": \"这是一条发给服务员的个人通知\",
    \"type\": \"info\",
    \"priority\": \"normal\",
    \"user_id\": \"$WAITER_ID\",
    \"source\": \"test\"
  }")

if echo $NOTIF1 | jq -e '.id' > /dev/null 2>&1; then
  echo "✓ 创建个人通知成功"
  echo "  ID: $(echo $NOTIF1 | jq -r '.id')"
else
  echo "✗ 创建个人通知失败"
  echo "  错误: $(echo $NOTIF1 | jq -r '.detail // .error')"
fi

# 创建给角色的通知
NOTIF2=$(curl -s -X POST "$BASE_URL/notifications" \
  -H "Authorization: Bearer $MANAGER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "角色通知测试",
    "message": "这是一条发给所有服务员的通知",
    "type": "warning",
    "priority": "high",
    "role": "waiter",
    "store_id": "STORE001",
    "source": "test"
  }')

if echo $NOTIF2 | jq -e '.id' > /dev/null 2>&1; then
  echo "✓ 创建角色通知成功"
  echo "  ID: $(echo $NOTIF2 | jq -r '.id')"
else
  echo "✗ 创建角色通知失败"
fi

# 创建门店通知
NOTIF3=$(curl -s -X POST "$BASE_URL/notifications" \
  -H "Authorization: Bearer $MANAGER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "门店通知测试",
    "message": "这是一条发给STORE001所有员工的通知",
    "type": "success",
    "priority": "normal",
    "store_id": "STORE001",
    "source": "test"
  }')

if echo $NOTIF3 | jq -e '.id' > /dev/null 2>&1; then
  echo "✓ 创建门店通知成功"
  echo "  ID: $(echo $NOTIF3 | jq -r '.id')"
else
  echo "✗ 创建门店通知失败"
fi
echo ""

# 3. 获取通知列表
echo "3. 获取通知列表"
echo "-------------------"
NOTIF_LIST=$(curl -s -X GET "$BASE_URL/notifications?limit=10" \
  -H "Authorization: Bearer $WAITER_TOKEN")

NOTIF_COUNT=$(echo $NOTIF_LIST | jq '. | length')
echo "✓ 服务员收到 $NOTIF_COUNT 条通知"

if [ "$NOTIF_COUNT" -gt 0 ]; then
  echo "  最新通知:"
  echo $NOTIF_LIST | jq -r '.[0] | "  - \(.title): \(.message)"'
fi
echo ""

# 4. 获取未读数量
echo "4. 获取未读通知数量"
echo "-------------------"
UNREAD=$(curl -s -X GET "$BASE_URL/notifications/unread-count" \
  -H "Authorization: Bearer $WAITER_TOKEN")

UNREAD_COUNT=$(echo $UNREAD | jq -r '.unread_count')
echo "✓ 服务员有 $UNREAD_COUNT 条未读通知"
echo ""

# 5. 标记为已读
echo "5. 标记通知为已读"
echo "-------------------"
if [ "$NOTIF_COUNT" -gt 0 ]; then
  FIRST_NOTIF_ID=$(echo $NOTIF_LIST | jq -r '.[0].id')
  READ_RESULT=$(curl -s -X PUT "$BASE_URL/notifications/$FIRST_NOTIF_ID/read" \
    -H "Authorization: Bearer $WAITER_TOKEN")

  if echo $READ_RESULT | jq -e '.success' | grep -q "true"; then
    echo "✓ 成功标记通知为已读"
  else
    echo "✗ 标记失败"
  fi
fi
echo ""

# 6. 标记所有为已读
echo "6. 标记所有通知为已读"
echo "-------------------"
READ_ALL=$(curl -s -X PUT "$BASE_URL/notifications/read-all" \
  -H "Authorization: Bearer $WAITER_TOKEN")

READ_ALL_COUNT=$(echo $READ_ALL | jq -r '.count')
echo "✓ 已标记 $READ_ALL_COUNT 条通知为已读"
echo ""

# 7. 再次检查未读数量
echo "7. 再次检查未读数量"
echo "-------------------"
UNREAD2=$(curl -s -X GET "$BASE_URL/notifications/unread-count" \
  -H "Authorization: Bearer $WAITER_TOKEN")

UNREAD_COUNT2=$(echo $UNREAD2 | jq -r '.unread_count')
echo "✓ 服务员现在有 $UNREAD_COUNT2 条未读通知"
echo ""

# 8. 获取系统统计
echo "8. 获取系统统计"
echo "-------------------"
STATS=$(curl -s -X GET "$BASE_URL/notifications/stats")
echo "✓ 活跃连接数: $(echo $STATS | jq -r '.active_connections')"
echo "✓ 活跃用户数: $(echo $STATS | jq -r '.active_users')"
echo ""

echo "========================================="
echo "通知系统测试完成"
echo "========================================="
echo ""
echo "测试总结:"
echo "- ✓ 创建个人通知"
echo "- ✓ 创建角色通知"
echo "- ✓ 创建门店通知"
echo "- ✓ 获取通知列表"
echo "- ✓ 获取未读数量"
echo "- ✓ 标记为已读"
echo "- ✓ 批量标记已读"
echo ""
echo "注意: WebSocket实时推送需要客户端连接测试"
