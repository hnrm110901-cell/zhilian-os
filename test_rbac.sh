#!/bin/bash
# 测试RBAC系统

BASE_URL="http://localhost:8000/api/v1"

echo "========================================="
echo "智链OS RBAC系统测试"
echo "========================================="
echo ""

# 1. 测试登录 - 管理员
echo "1. 测试管理员登录..."
ADMIN_TOKEN=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' | jq -r '.access_token')

if [ "$ADMIN_TOKEN" != "null" ] && [ -n "$ADMIN_TOKEN" ]; then
  echo "✓ 管理员登录成功"
  echo "Token: ${ADMIN_TOKEN:0:50}..."
else
  echo "✗ 管理员登录失败"
fi
echo ""

# 2. 测试登录 - 店长
echo "2. 测试店长登录..."
MANAGER_TOKEN=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "manager001", "password": "manager123"}' | jq -r '.access_token')

if [ "$MANAGER_TOKEN" != "null" ] && [ -n "$MANAGER_TOKEN" ]; then
  echo "✓ 店长登录成功"
  echo "Token: ${MANAGER_TOKEN:0:50}..."
else
  echo "✗ 店长登录失败"
fi
echo ""

# 3. 测试登录 - 服务员
echo "3. 测试服务员登录..."
WAITER_TOKEN=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "waiter001", "password": "waiter123"}' | jq -r '.access_token')

if [ "$WAITER_TOKEN" != "null" ] && [ -n "$WAITER_TOKEN" ]; then
  echo "✓ 服务员登录成功"
  echo "Token: ${WAITER_TOKEN:0:50}..."
else
  echo "✗ 服务员登录失败"
fi
echo ""

# 4. 测试获取当前用户信息
echo "4. 测试获取当前用户信息 (管理员)..."
curl -s -X GET "$BASE_URL/auth/me" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.'
echo ""

echo "5. 测试获取当前用户信息 (店长)..."
curl -s -X GET "$BASE_URL/auth/me" \
  -H "Authorization: Bearer $MANAGER_TOKEN" | jq '.'
echo ""

echo "6. 测试获取当前用户信息 (服务员)..."
curl -s -X GET "$BASE_URL/auth/me" \
  -H "Authorization: Bearer $WAITER_TOKEN" | jq '.'
echo ""

# 7. 测试无Token访问受保护接口
echo "7. 测试无Token访问受保护接口 (应该失败)..."
RESPONSE=$(curl -s -X POST "$BASE_URL/agents/order" \
  -H "Content-Type: application/json" \
  -d '{"agent_type": "order", "input_data": {"action": "get_orders"}}')
echo "$RESPONSE" | jq '.'
echo ""

# 8. 测试有Token访问受保护接口
echo "8. 测试有Token访问受保护接口 (服务员访问订单Agent)..."
curl -s -X POST "$BASE_URL/agents/order" \
  -H "Authorization: Bearer $WAITER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent_type": "order", "input_data": {"action": "get_orders", "store_id": "STORE001"}}' | jq '.'
echo ""

# 9. 测试注册新用户 (仅管理员和店长可操作)
echo "9. 测试店长注册新用户..."
curl -s -X POST "$BASE_URL/auth/register" \
  -H "Authorization: Bearer $MANAGER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser001",
    "email": "testuser001@zhilian.com",
    "password": "test123",
    "full_name": "测试用户",
    "role": "waiter",
    "store_id": "STORE001"
  }' | jq '.'
echo ""

# 10. 测试服务员尝试注册新用户 (应该失败)
echo "10. 测试服务员尝试注册新用户 (应该失败)..."
curl -s -X POST "$BASE_URL/auth/register" \
  -H "Authorization: Bearer $WAITER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser002",
    "email": "testuser002@zhilian.com",
    "password": "test123",
    "full_name": "测试用户2",
    "role": "waiter",
    "store_id": "STORE001"
  }' | jq '.'
echo ""

# 11. 测试修改密码
echo "11. 测试服务员修改密码..."
curl -s -X POST "$BASE_URL/auth/change-password" \
  -H "Authorization: Bearer $WAITER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "old_password": "waiter123",
    "new_password": "newpassword123"
  }' | jq '.'
echo ""

# 12. 测试用旧密码登录 (应该失败)
echo "12. 测试用旧密码登录 (应该失败)..."
curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "waiter001", "password": "waiter123"}' | jq '.'
echo ""

# 13. 测试用新密码登录
echo "13. 测试用新密码登录..."
curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "waiter001", "password": "newpassword123"}' | jq '.'
echo ""

# 14. 改回原密码
echo "14. 改回原密码..."
NEW_WAITER_TOKEN=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "waiter001", "password": "newpassword123"}' | jq -r '.access_token')

curl -s -X POST "$BASE_URL/auth/change-password" \
  -H "Authorization: Bearer $NEW_WAITER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "old_password": "newpassword123",
    "new_password": "waiter123"
  }' | jq '.'
echo ""

echo "========================================="
echo "RBAC系统测试完成"
echo "========================================="
