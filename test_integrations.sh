#!/bin/bash
# Test script for integration APIs
# 测试外部系统集成API

BASE_URL="http://localhost:8000/api/v1"

echo "=== 智链OS 外部系统集成测试 ==="
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

# 2. Create POS system
echo "2. 创建POS系统配置..."
POS_SYSTEM=$(curl -s -X POST "$BASE_URL/integrations/systems" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "美团POS系统",
    "type": "pos",
    "provider": "Meituan",
    "store_id": "store-001",
    "config": {
      "api_endpoint": "https://api.meituan.com/pos",
      "api_key": "test_key_123",
      "webhook_url": "http://localhost:8000/api/v1/integrations/webhooks/pos"
    }
  }')

POS_SYSTEM_ID=$(echo $POS_SYSTEM | jq -r '.id')
echo "✓ POS系统创建成功: $POS_SYSTEM_ID"
echo $POS_SYSTEM | jq '.'
echo ""

# 3. Create Supplier system
echo "3. 创建供应商系统配置..."
SUPPLIER_SYSTEM=$(curl -s -X POST "$BASE_URL/integrations/systems" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "海底捞供应链系统",
    "type": "supplier",
    "provider": "Haidilao Supply Chain",
    "store_id": "store-001",
    "config": {
      "api_endpoint": "https://api.haidilao.com/supply",
      "api_key": "supplier_key_456"
    }
  }')

SUPPLIER_SYSTEM_ID=$(echo $SUPPLIER_SYSTEM | jq -r '.id')
echo "✓ 供应商系统创建成功: $SUPPLIER_SYSTEM_ID"
echo $SUPPLIER_SYSTEM | jq '.'
echo ""

# 4. Create Member system
echo "4. 创建会员系统配置..."
MEMBER_SYSTEM=$(curl -s -X POST "$BASE_URL/integrations/systems" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "微信会员系统",
    "type": "member",
    "provider": "WeChat",
    "config": {
      "api_endpoint": "https://api.weixin.qq.com/member",
      "api_key": "wechat_key_789"
    }
  }')

MEMBER_SYSTEM_ID=$(echo $MEMBER_SYSTEM | jq -r '.id')
echo "✓ 会员系统创建成功: $MEMBER_SYSTEM_ID"
echo $MEMBER_SYSTEM | jq '.'
echo ""

# 5. Get all systems
echo "5. 获取所有外部系统..."
ALL_SYSTEMS=$(curl -s -X GET "$BASE_URL/integrations/systems" \
  -H "Authorization: Bearer $TOKEN")

SYSTEM_COUNT=$(echo $ALL_SYSTEMS | jq '. | length')
echo "✓ 共有 $SYSTEM_COUNT 个外部系统"
echo $ALL_SYSTEMS | jq '.'
echo ""

# 6. Create POS transaction
echo "6. 创建POS交易记录..."
POS_TRANSACTION=$(curl -s -X POST "$BASE_URL/integrations/pos/$POS_SYSTEM_ID/transactions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "TXN-2024-001",
    "order_number": "ORD-2024-001",
    "type": "sale",
    "subtotal": 288.00,
    "tax": 28.80,
    "discount": 20.00,
    "total": 296.80,
    "payment_method": "wechat_pay",
    "items": [
      {
        "name": "宫保鸡丁",
        "quantity": 2,
        "price": 68.00
      },
      {
        "name": "麻婆豆腐",
        "quantity": 1,
        "price": 48.00
      },
      {
        "name": "米饭",
        "quantity": 3,
        "price": 5.00
      }
    ],
    "customer": {
      "phone": "13800138000",
      "name": "张三"
    }
  }')

echo "✓ POS交易记录创建成功"
echo $POS_TRANSACTION | jq '.'
echo ""

# 7. Get POS transactions
echo "7. 获取POS交易记录..."
POS_TRANSACTIONS=$(curl -s -X GET "$BASE_URL/integrations/pos/transactions?store_id=store-001" \
  -H "Authorization: Bearer $TOKEN")

TRANSACTION_COUNT=$(echo $POS_TRANSACTIONS | jq '. | length')
echo "✓ 共有 $TRANSACTION_COUNT 条POS交易记录"
echo $POS_TRANSACTIONS | jq '.'
echo ""

# 8. Create supplier order
echo "8. 创建供应商订单..."
SUPPLIER_ORDER=$(curl -s -X POST "$BASE_URL/integrations/supplier/$SUPPLIER_SYSTEM_ID/orders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_number": "PO-2024-001",
    "supplier_id": "SUP-001",
    "supplier_name": "蜀海供应链",
    "type": "purchase",
    "status": "pending",
    "subtotal": 5000.00,
    "tax": 500.00,
    "shipping": 200.00,
    "total": 5700.00,
    "items": [
      {
        "name": "鸡肉",
        "quantity": 50,
        "unit": "kg",
        "price": 30.00
      },
      {
        "name": "豆腐",
        "quantity": 100,
        "unit": "盒",
        "price": 8.00
      }
    ],
    "delivery": {
      "address": "北京市朝阳区xxx路xxx号",
      "contact": "李四",
      "phone": "13900139000"
    },
    "expected_delivery": "2024-02-15T10:00:00"
  }')

echo "✓ 供应商订单创建成功"
echo $SUPPLIER_ORDER | jq '.'
echo ""

# 9. Get supplier orders
echo "9. 获取供应商订单..."
SUPPLIER_ORDERS=$(curl -s -X GET "$BASE_URL/integrations/supplier/orders?store_id=store-001" \
  -H "Authorization: Bearer $TOKEN")

ORDER_COUNT=$(echo $SUPPLIER_ORDERS | jq '. | length')
echo "✓ 共有 $ORDER_COUNT 个供应商订单"
echo $SUPPLIER_ORDERS | jq '.'
echo ""

# 10. Sync member data
echo "10. 同步会员数据..."
MEMBER_SYNC=$(curl -s -X POST "$BASE_URL/integrations/member/$MEMBER_SYSTEM_ID/sync" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "member_id": "MEM-001",
    "external_id": "wx_openid_123",
    "phone": "13800138000",
    "name": "张三",
    "email": "zhangsan@example.com",
    "level": "gold",
    "points": 1500,
    "balance": 200.00
  }')

echo "✓ 会员数据同步成功"
echo $MEMBER_SYNC | jq '.'
echo ""

# 11. Test POS webhook
echo "11. 测试POS Webhook..."
WEBHOOK_RESPONSE=$(curl -s -X POST "$BASE_URL/integrations/webhooks/pos/$POS_SYSTEM_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "transaction.created",
    "data": {
      "transaction_id": "TXN-2024-002",
      "total": 150.00
    }
  }')

echo "✓ Webhook测试成功"
echo $WEBHOOK_RESPONSE | jq '.'
echo ""

# 12. Get sync logs
echo "12. 获取同步日志..."
SYNC_LOGS=$(curl -s -X GET "$BASE_URL/integrations/sync-logs?limit=10" \
  -H "Authorization: Bearer $TOKEN")

LOG_COUNT=$(echo $SYNC_LOGS | jq '. | length')
echo "✓ 共有 $LOG_COUNT 条同步日志"
echo $SYNC_LOGS | jq '.'
echo ""

echo "=== 测试完成 ==="
echo ""
echo "总结:"
echo "- 外部系统: $SYSTEM_COUNT 个"
echo "- POS交易: $TRANSACTION_COUNT 条"
echo "- 供应商订单: $ORDER_COUNT 个"
echo "- 同步日志: $LOG_COUNT 条"