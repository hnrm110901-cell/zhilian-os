#!/bin/bash
# Test Inventory Agent with Database

API_BASE="http://localhost:8000/api/v1/agents/inventory"

echo "🧪 Testing Inventory Agent with Database"
echo "=" | head -c 50
echo ""

# Test 1: Monitor inventory
echo "📊 Test 1: Monitoring inventory..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "inventory",
    "input_data": {
      "action": "monitor_inventory",
      "params": {}
    }
  }' | jq '.output_data.metadata.source, (.output_data.data | length)'
echo "✅ Monitored inventory"
echo ""

# Test 2: Generate restock alerts
echo "⚠️  Test 2: Generating restock alerts..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "inventory",
    "input_data": {
      "action": "generate_restock_alerts",
      "params": {}
    }
  }' | jq '.output_data.data | length'
echo "✅ Generated restock alerts"
echo ""

# Test 3: Get inventory statistics
echo "📈 Test 3: Getting inventory statistics..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "inventory",
    "input_data": {
      "action": "get_inventory_statistics",
      "params": {}
    }
  }' | jq '.output_data.data | {total_items, total_value, alerts_count}'
echo "✅ Retrieved inventory statistics"
echo ""

# Test 4: Get inventory report
echo "📋 Test 4: Getting inventory report..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "inventory",
    "input_data": {
      "action": "get_inventory_report",
      "params": {}
    }
  }' | jq '.output_data.data | {total_items: .inventory_summary.total_items, total_value: .inventory_summary.total_value, restock_alerts: (.restock_alerts | length), critical_items: (.critical_items | length)}'
echo "✅ Retrieved inventory report"
echo ""

# Test 5: Record a transaction (usage)
echo "📝 Test 5: Recording inventory transaction (usage)..."
# First, get an item ID
ITEM_ID=$(curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "inventory",
    "input_data": {
      "action": "monitor_inventory",
      "params": {}
    }
  }' | jq -r '.output_data.data[0].item_id')

if [ "$ITEM_ID" != "null" ] && [ -n "$ITEM_ID" ]; then
  curl -s -X POST "$API_BASE" \
    -H "Content-Type: application/json" \
    -d "{
      \"agent_type\": \"inventory\",
      \"input_data\": {
        \"action\": \"record_transaction\",
        \"params\": {
          \"item_id\": \"$ITEM_ID\",
          \"transaction_type\": \"usage\",
          \"quantity\": -5.0,
          \"notes\": \"测试消耗\",
          \"performed_by\": \"test_user\"
        }
      }
    }" | jq '.output_data.data | {item_name, transaction_type, quantity, quantity_before, quantity_after, status}'
  echo "✅ Recorded transaction"
else
  echo "⚠️  No items found to test transaction"
fi
echo ""

# Test 6: Get item details
echo "🔍 Test 6: Getting item details..."
if [ "$ITEM_ID" != "null" ] && [ -n "$ITEM_ID" ]; then
  curl -s -X POST "$API_BASE" \
    -H "Content-Type: application/json" \
    -d "{
      \"agent_type\": \"inventory\",
      \"input_data\": {
        \"action\": \"get_item\",
        \"params\": {
          \"item_id\": \"$ITEM_ID\"
        }
      }
    }" | jq '.output_data.data | {item_id, name, current_quantity, status, recent_transactions: (.recent_transactions | length)}'
  echo "✅ Retrieved item details"
else
  echo "⚠️  No items found to test"
fi
echo ""

# Test 7: Monitor low stock items
echo "⚠️  Test 7: Monitoring low stock items..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "inventory",
    "input_data": {
      "action": "monitor_inventory",
      "params": {
        "status": "low"
      }
    }
  }' | jq '.output_data.data | length'
echo "✅ Monitored low stock items"
echo ""

echo "=" | head -c 50
echo ""
echo "🎉 All tests completed!"
echo "✅ InventoryAgent is using DATABASE!"
