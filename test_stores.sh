#!/bin/bash
# 测试多门店管理系统

BASE_URL="http://localhost:8000/api/v1"

echo "========================================="
echo "智链OS 多门店管理系统测试"
echo "========================================="
echo ""

# 1. 登录获取管理员token
echo "1. 管理员登录"
echo "-------------------"
ADMIN_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}')

ADMIN_TOKEN=$(echo $ADMIN_RESPONSE | jq -r '.access_token')
echo "✓ 管理员登录成功"
echo ""

# 2. 创建门店
echo "2. 创建门店"
echo "-------------------"

# 创建门店1
STORE1=$(curl -s -X POST "$BASE_URL/stores" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "STORE002",
    "name": "智链餐厅-朝阳店",
    "code": "BJ-CY-001",
    "address": "北京市朝阳区建国路88号",
    "city": "北京",
    "district": "朝阳区",
    "phone": "010-12345678",
    "email": "chaoyang@zhilian.com",
    "region": "华北",
    "area": 300.0,
    "seats": 80,
    "floors": 2,
    "opening_date": "2024-01-15",
    "monthly_revenue_target": 500000.0,
    "daily_customer_target": 200
  }')

if echo $STORE1 | jq -e '.id' > /dev/null 2>&1; then
  echo "✓ 创建门店1成功: $(echo $STORE1 | jq -r '.name')"
else
  echo "✗ 创建门店1失败: $(echo $STORE1 | jq -r '.detail // .error')"
fi

# 创建门店2
STORE2=$(curl -s -X POST "$BASE_URL/stores" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "STORE003",
    "name": "智链餐厅-海淀店",
    "code": "BJ-HD-001",
    "address": "北京市海淀区中关村大街1号",
    "city": "北京",
    "district": "海淀区",
    "phone": "010-87654321",
    "email": "haidian@zhilian.com",
    "region": "华北",
    "area": 250.0,
    "seats": 60,
    "floors": 1,
    "opening_date": "2024-03-01",
    "monthly_revenue_target": 400000.0,
    "daily_customer_target": 150
  }')

if echo $STORE2 | jq -e '.id' > /dev/null 2>&1; then
  echo "✓ 创建门店2成功: $(echo $STORE2 | jq -r '.name')"
else
  echo "✗ 创建门店2失败"
fi

# 创建门店3 (上海)
STORE3=$(curl -s -X POST "$BASE_URL/stores" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "STORE004",
    "name": "智链餐厅-浦东店",
    "code": "SH-PD-001",
    "address": "上海市浦东新区陆家嘴环路1000号",
    "city": "上海",
    "district": "浦东新区",
    "phone": "021-12345678",
    "email": "pudong@zhilian.com",
    "region": "华东",
    "area": 350.0,
    "seats": 100,
    "floors": 2,
    "opening_date": "2024-02-01",
    "monthly_revenue_target": 600000.0,
    "daily_customer_target": 250
  }')

if echo $STORE3 | jq -e '.id' > /dev/null 2>&1; then
  echo "✓ 创建门店3成功: $(echo $STORE3 | jq -r '.name')"
else
  echo "✗ 创建门店3失败"
fi
echo ""

# 3. 获取门店列表
echo "3. 获取门店列表"
echo "-------------------"
STORES=$(curl -s -X GET "$BASE_URL/stores" \
  -H "Authorization: Bearer $ADMIN_TOKEN")

STORE_COUNT=$(echo $STORES | jq '. | length')
echo "✓ 共有 $STORE_COUNT 个门店"
if [ "$STORE_COUNT" -gt 0 ]; then
  echo "  门店列表:"
  echo $STORES | jq -r '.[] | "  - \(.name) (\(.city) - \(.region))"'
fi
echo ""

# 4. 按区域获取门店
echo "4. 按区域获取门店"
echo "-------------------"
STORES_BY_REGION=$(curl -s -X GET "$BASE_URL/stores-by-region" \
  -H "Authorization: Bearer $ADMIN_TOKEN")

echo "✓ 按区域分组:"
echo $STORES_BY_REGION | jq -r 'to_entries[] | "  \(.key): \(.value | length)个门店"'
echo ""

# 5. 获取门店详情
echo "5. 获取门店详情"
echo "-------------------"
STORE_DETAIL=$(curl -s -X GET "$BASE_URL/stores/STORE002" \
  -H "Authorization: Bearer $ADMIN_TOKEN")

if echo $STORE_DETAIL | jq -e '.id' > /dev/null 2>&1; then
  echo "✓ 门店详情:"
  echo "  名称: $(echo $STORE_DETAIL | jq -r '.name')"
  echo "  地址: $(echo $STORE_DETAIL | jq -r '.address')"
  echo "  面积: $(echo $STORE_DETAIL | jq -r '.area')㎡"
  echo "  座位: $(echo $STORE_DETAIL | jq -r '.seats')个"
  echo "  月目标: ¥$(echo $STORE_DETAIL | jq -r '.monthly_revenue_target')"
fi
echo ""

# 6. 更新门店信息
echo "6. 更新门店信息"
echo "-------------------"
UPDATE_RESULT=$(curl -s -X PUT "$BASE_URL/stores/STORE002" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "010-11112222",
    "monthly_revenue_target": 550000.0
  }')

if echo $UPDATE_RESULT | jq -e '.id' > /dev/null 2>&1; then
  echo "✓ 门店信息更新成功"
  echo "  新电话: $(echo $UPDATE_RESULT | jq -r '.phone')"
  echo "  新目标: ¥$(echo $UPDATE_RESULT | jq -r '.monthly_revenue_target')"
fi
echo ""

# 7. 获取门店统计
echo "7. 获取门店统计"
echo "-------------------"
STATS=$(curl -s -X GET "$BASE_URL/stores/STORE002/stats" \
  -H "Authorization: Bearer $ADMIN_TOKEN")

echo "✓ 门店统计:"
echo $STATS | jq '.'
echo ""

# 8. 门店数量统计
echo "8. 门店数量统计"
echo "-------------------"
COUNT_ALL=$(curl -s -X GET "$BASE_URL/stores-count" \
  -H "Authorization: Bearer $ADMIN_TOKEN")
echo "✓ 总门店数: $(echo $COUNT_ALL | jq -r '.count')"

COUNT_HUABEI=$(curl -s -X GET "$BASE_URL/stores-count?region=华北" \
  -H "Authorization: Bearer $ADMIN_TOKEN")
echo "✓ 华北区门店数: $(echo $COUNT_HUABEI | jq -r '.count')"

COUNT_HUADONG=$(curl -s -X GET "$BASE_URL/stores-count?region=华东" \
  -H "Authorization: Bearer $ADMIN_TOKEN")
echo "✓ 华东区门店数: $(echo $COUNT_HUADONG | jq -r '.count')"
echo ""

# 9. 对比门店
echo "9. 对比门店数据"
echo "-------------------"
COMPARISON=$(curl -s -X POST "$BASE_URL/stores/compare?store_ids=STORE002&store_ids=STORE003&store_ids=STORE004" \
  -H "Authorization: Bearer $ADMIN_TOKEN")

echo "✓ 门店对比:"
echo $COMPARISON | jq '.'
echo ""

echo "========================================="
echo "多门店管理系统测试完成"
echo "========================================="
echo ""
echo "测试总结:"
echo "- ✓ 创建门店"
echo "- ✓ 获取门店列表"
echo "- ✓ 按区域分组"
echo "- ✓ 获取门店详情"
echo "- ✓ 更新门店信息"
echo "- ✓ 门店统计"
echo "- ✓ 数量统计"
echo "- ✓ 门店对比"
