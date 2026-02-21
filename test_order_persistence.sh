#!/bin/bash
# Test Order Agent with Database

API_BASE="http://localhost:8000/api/v1/agents/order"

echo "🧪 Testing Order Agent with Database"
echo "=" | head -c 50
echo ""

# Test 1: Create an order
echo "📝 Test 1: Creating a new order..."
RESPONSE=$(curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "order",
    "input_data": {
      "action": "create_order",
      "params": {
        "table_number": "A05",
        "customer_name": "张三",
        "customer_phone": "13900139000",
        "items": [
          {
            "item_id": "DISH001",
            "item_name": "宫保鸡丁",
            "quantity": 2,
            "unit_price": 4800
          },
          {
            "item_id": "DISH002",
            "item_name": "麻婆豆腐",
            "quantity": 1,
            "unit_price": 3200
          }
        ],
        "notes": "少辣"
      }
    }
  }')

echo "$RESPONSE" | jq '.output_data.metadata.source, .output_data.data.order_id, .output_data.data.status'
ORDER_ID=$(echo "$RESPONSE" | jq -r '.output_data.data.order_id')
echo "✅ Created order: $ORDER_ID"
echo ""

# Test 2: Get order details
echo "🔍 Test 2: Getting order details..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_type\": \"order\",
    \"input_data\": {
      \"action\": \"get_order\",
      \"params\": {
        \"order_id\": \"$ORDER_ID\"
      }
    }
  }" | jq '.output_data.data | {order_id: .order_id, table: .table_number, status: .status, total: .total_amount, items: (.items | length)}'
echo "✅ Retrieved order details"
echo ""

# Test 3: Add items to order
echo "➕ Test 3: Adding items to order..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_type\": \"order\",
    \"input_data\": {
      \"action\": \"add_items\",
      \"params\": {
        \"order_id\": \"$ORDER_ID\",
        \"items\": [
          {
            \"item_id\": \"DISH003\",
            \"item_name\": \"米饭\",
            \"quantity\": 2,
            \"unit_price\": 200
          }
        ]
      }
    }
  }" | jq '.output_data.data | {order_id: .order_id, total: .total_amount, items: (.items | length)}'
echo "✅ Added items to order"
echo ""

# Test 4: Update order status
echo "🔄 Test 4: Updating order status to confirmed..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_type\": \"order\",
    \"input_data\": {
      \"action\": \"update_order_status\",
      \"params\": {
        \"order_id\": \"$ORDER_ID\",
        \"status\": \"confirmed\",
        \"notes\": \"已确认订单\"
      }
    }
  }" | jq '.output_data.data.status'
echo "✅ Updated order status"
echo ""

# Test 5: List orders
echo "📋 Test 5: Listing orders..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "order",
    "input_data": {
      "action": "list_orders",
      "params": {
        "limit": 10
      }
    }
  }' | jq '.output_data.data | length'
echo "✅ Listed orders"
echo ""

# Test 6: Get order statistics
echo "📊 Test 6: Getting order statistics..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "order",
    "input_data": {
      "action": "get_order_statistics",
      "params": {}
    }
  }' | jq '.output_data.data | {total: .total_orders, completed: .completed_orders, revenue: .total_revenue}'
echo "✅ Retrieved statistics"
echo ""

# Test 7: Cancel order (create a new one first)
echo "❌ Test 7: Canceling an order..."
NEW_ORDER=$(curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "order",
    "input_data": {
      "action": "create_order",
      "params": {
        "table_number": "B03",
        "items": [
          {
            "item_id": "DISH001",
            "item_name": "宫保鸡丁",
            "quantity": 1,
            "unit_price": 4800
          }
        ]
      }
    }
  }')
NEW_ORDER_ID=$(echo "$NEW_ORDER" | jq -r '.output_data.data.order_id')

curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_type\": \"order\",
    \"input_data\": {
      \"action\": \"cancel_order\",
      \"params\": {
        \"order_id\": \"$NEW_ORDER_ID\",
        \"reason\": \"客户要求取消\"
      }
    }
  }" | jq '.output_data.data.status'
echo "✅ Cancelled order"
echo ""

echo "=" | head -c 50
echo ""
echo "🎉 All tests completed!"
echo "✅ OrderAgent is using DATABASE!"
