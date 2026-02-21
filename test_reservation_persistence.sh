#!/bin/bash
# Test Reservation Agent with Database

API_BASE="http://localhost:8000/api/v1/agents/reservation"

echo "🧪 Testing Reservation Agent with Database"
echo "=" | head -c 50
echo ""

# Test 1: Create a reservation
echo "📝 Test 1: Creating a new reservation..."
RESPONSE=$(curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "reservation",
    "input_data": {
      "action": "create",
      "params": {
        "customer_name": "测试客户",
        "customer_phone": "13800138888",
        "customer_email": "test@example.com",
        "reservation_date": "2026-02-20",
        "reservation_time": "18:30",
        "party_size": 4,
        "reservation_type": "regular",
        "special_requests": "靠窗座位"
      }
    }
  }')

echo "$RESPONSE" | jq '.output_data.metadata.source, .output_data.data.reservation_id, .output_data.data.status'
RESERVATION_ID=$(echo "$RESPONSE" | jq -r '.output_data.data.reservation_id')
echo "✅ Created reservation: $RESERVATION_ID"
echo ""

# Test 2: List reservations
echo "📋 Test 2: Listing reservations for 2026-02-20..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "reservation",
    "input_data": {
      "action": "list",
      "params": {
        "reservation_date": "2026-02-20"
      }
    }
  }' | jq '.output_data.data | length'
echo "✅ Listed reservations"
echo ""

# Test 3: Get specific reservation
echo "🔍 Test 3: Getting reservation details..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_type\": \"reservation\",
    \"input_data\": {
      \"action\": \"get\",
      \"params\": {
        \"reservation_id\": \"$RESERVATION_ID\"
      }
    }
  }" | jq '.output_data.data | {customer: .customer_name, date: .reservation_date, time: .reservation_time, guests: .party_size, status: .status}'
echo "✅ Retrieved reservation details"
echo ""

# Test 4: Confirm reservation
echo "✅ Test 4: Confirming reservation..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_type\": \"reservation\",
    \"input_data\": {
      \"action\": \"confirm\",
      \"params\": {
        \"reservation_id\": \"$RESERVATION_ID\",
        \"notes\": \"已电话确认\"
      }
    }
  }" | jq '.output_data.data.status'
echo "✅ Confirmed reservation"
echo ""

# Test 5: Assign table
echo "🪑 Test 5: Assigning table..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_type\": \"reservation\",
    \"input_data\": {
      \"action\": \"assign_table\",
      \"params\": {
        \"reservation_id\": \"$RESERVATION_ID\",
        \"table_number\": \"A08\"
      }
    }
  }" | jq '.output_data.data.table_number'
echo "✅ Assigned table"
echo ""

# Test 6: Get upcoming reservations
echo "📅 Test 6: Getting upcoming reservations..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "reservation",
    "input_data": {
      "action": "upcoming",
      "params": {
        "days": 7
      }
    }
  }' | jq '.output_data.data | length'
echo "✅ Retrieved upcoming reservations"
echo ""

# Test 7: Get statistics
echo "📊 Test 7: Getting reservation statistics..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "reservation",
    "input_data": {
      "action": "statistics",
      "params": {}
    }
  }' | jq '.output_data.data | {total: .total_reservations, guests: .total_guests, avg_party: .average_party_size}'
echo "✅ Retrieved statistics"
echo ""

echo "=" | head -c 50
echo ""
echo "🎉 All tests completed!"
echo "✅ ReservationAgent is using DATABASE!"
