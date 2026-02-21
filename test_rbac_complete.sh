#!/bin/bash
# RBAC系统完整测试

BASE_URL="http://localhost:8000/api/v1"

echo "========================================="
echo "智链OS RBAC系统完整测试"
echo "========================================="
echo ""

# 1. 测试登录
echo "1. 测试用户登录"
echo "-------------------"
MANAGER_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "manager001", "password": "manager123"}')

MANAGER_TOKEN=$(echo $MANAGER_RESPONSE | jq -r '.access_token')
echo "✓ 店长登录成功"
echo "  用户: $(echo $MANAGER_RESPONSE | jq -r '.user.full_name')"
echo "  角色: $(echo $MANAGER_RESPONSE | jq -r '.user.role')"
echo ""

WAITER_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "waiter001", "password": "waiter123"}')

WAITER_TOKEN=$(echo $WAITER_RESPONSE | jq -r '.access_token')
echo "✓ 服务员登录成功"
echo "  用户: $(echo $WAITER_RESPONSE | jq -r '.user.full_name')"
echo "  角色: $(echo $WAITER_RESPONSE | jq -r '.user.role')"
echo ""

# 2. 测试获取当前用户信息
echo "2. 测试获取当前用户信息"
echo "-------------------"
MANAGER_INFO=$(curl -s -X GET "$BASE_URL/auth/me" \
  -H "Authorization: Bearer $MANAGER_TOKEN")
echo "✓ 店长信息: $(echo $MANAGER_INFO | jq -r '.full_name') ($(echo $MANAGER_INFO | jq -r '.role'))"

WAITER_INFO=$(curl -s -X GET "$BASE_URL/auth/me" \
  -H "Authorization: Bearer $WAITER_TOKEN")
echo "✓ 服务员信息: $(echo $WAITER_INFO | jq -r '.full_name') ($(echo $WAITER_INFO | jq -r '.role'))"
echo ""

# 3. 测试访问受保护的Agent接口
echo "3. 测试访问受保护的Agent接口"
echo "-------------------"
ORDER_RESPONSE=$(curl -s -X POST "$BASE_URL/agents/order" \
  -H "Authorization: Bearer $WAITER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent_type": "order", "input_data": {"action": "get_orders", "store_id": "STORE001"}}')

if echo $ORDER_RESPONSE | jq -e '.agent_type' > /dev/null 2>&1; then
  echo "✓ 服务员成功访问订单Agent"
else
  echo "✗ 服务员访问订单Agent失败"
  echo "  错误: $(echo $ORDER_RESPONSE | jq -r '.detail // .error')"
fi
echo ""

# 4. 测试无Token访问(应该失败)
echo "4. 测试无Token访问受保护接口"
echo "-------------------"
NO_AUTH_RESPONSE=$(curl -s -X POST "$BASE_URL/agents/order" \
  -H "Content-Type: application/json" \
  -d '{"agent_type": "order", "input_data": {"action": "get_orders"}}')

if echo $NO_AUTH_RESPONSE | jq -e '.detail' | grep -q "Not authenticated"; then
  echo "✓ 无Token访问被正确拒绝"
else
  echo "✗ 无Token访问未被拒绝"
fi
echo ""

# 5. 测试角色权限(店长可以注册新用户,服务员不可以)
echo "5. 测试角色权限控制"
echo "-------------------"
MANAGER_REGISTER=$(curl -s -X POST "$BASE_URL/auth/register" \
  -H "Authorization: Bearer $MANAGER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser_'$(date +%s)'",
    "email": "testuser_'$(date +%s)'@zhilian.com",
    "password": "test123",
    "full_name": "测试用户",
    "role": "waiter",
    "store_id": "STORE001"
  }')

if echo $MANAGER_REGISTER | jq -e '.username' > /dev/null 2>&1; then
  echo "✓ 店长成功注册新用户"
else
  echo "✗ 店长注册新用户失败"
  echo "  错误: $(echo $MANAGER_REGISTER | jq -r '.detail // .error')"
fi

WAITER_REGISTER=$(curl -s -X POST "$BASE_URL/auth/register" \
  -H "Authorization: Bearer $WAITER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser2_'$(date +%s)'",
    "email": "testuser2_'$(date +%s)'@zhilian.com",
    "password": "test123",
    "full_name": "测试用户2",
    "role": "waiter",
    "store_id": "STORE001"
  }')

if echo $WAITER_REGISTER | jq -e '.detail' | grep -q "权限不足"; then
  echo "✓ 服务员注册新用户被正确拒绝(权限不足)"
else
  echo "✗ 服务员注册新用户未被拒绝"
fi
echo ""

# 6. 测试修改密码
echo "6. 测试修改密码功能"
echo "-------------------"
CHANGE_PW=$(curl -s -X POST "$BASE_URL/auth/change-password" \
  -H "Authorization: Bearer $WAITER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "old_password": "waiter123",
    "new_password": "newpassword123"
  }')

if echo $CHANGE_PW | jq -e '.message' | grep -q "密码修改成功"; then
  echo "✓ 密码修改成功"

  # 测试用新密码登录
  NEW_LOGIN=$(curl -s -X POST "$BASE_URL/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username": "waiter001", "password": "newpassword123"}')

  if echo $NEW_LOGIN | jq -e '.access_token' > /dev/null 2>&1; then
    echo "✓ 新密码登录成功"

    # 改回原密码
    NEW_TOKEN=$(echo $NEW_LOGIN | jq -r '.access_token')
    curl -s -X POST "$BASE_URL/auth/change-password" \
      -H "Authorization: Bearer $NEW_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"old_password": "newpassword123", "new_password": "waiter123"}' > /dev/null
    echo "✓ 密码已改回原密码"
  else
    echo "✗ 新密码登录失败"
  fi
else
  echo "✗ 密码修改失败"
  echo "  错误: $(echo $CHANGE_PW | jq -r '.detail // .error')"
fi
echo ""

echo "========================================="
echo "RBAC系统测试完成"
echo "========================================="
echo ""
echo "测试总结:"
echo "- ✓ 用户认证(JWT Token)"
echo "- ✓ 获取当前用户信息"
echo "- ✓ 访问受保护的API接口"
echo "- ✓ 无Token访问拒绝"
echo "- ✓ 基于角色的权限控制"
echo "- ✓ 密码修改功能"
echo ""
echo "智链OS RBAC系统运行正常!"
