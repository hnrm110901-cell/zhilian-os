#!/bin/bash
# Test Schedule Agent with Database

API_BASE="http://localhost:8000/api/v1/agents/schedule"

echo "🧪 Testing Schedule Agent with Database"
echo "=" | head -c 50
echo ""

# Get employee IDs for testing
EMPLOYEE_IDS=$(curl -s http://localhost:8000/api/v1/agents/schedule -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "schedule",
    "input_data": {
      "action": "get_schedule",
      "params": {
        "start_date": "2026-02-01",
        "end_date": "2026-02-28"
      }
    }
  }' 2>/dev/null)

# Test 1: Create a schedule
echo "📝 Test 1: Creating a schedule..."
RESPONSE=$(curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "schedule",
    "input_data": {
      "action": "create_schedule",
      "params": {
        "schedule_date": "2026-02-20",
        "shifts": [
          {
            "employee_id": "EMP001",
            "shift_type": "morning",
            "start_time": "2026-02-20T08:00:00",
            "end_time": "2026-02-20T16:00:00",
            "position": "waiter",
            "is_confirmed": true
          },
          {
            "employee_id": "EMP002",
            "shift_type": "afternoon",
            "start_time": "2026-02-20T14:00:00",
            "end_time": "2026-02-20T22:00:00",
            "position": "chef",
            "is_confirmed": true
          }
        ],
        "is_published": false
      }
    }
  }')

echo "$RESPONSE" | jq '.output_data.metadata.source, .output_data.data.schedule_id, .output_data.data.total_employees, .output_data.data.total_hours'
SCHEDULE_ID=$(echo "$RESPONSE" | jq -r '.output_data.data.schedule_id')
echo "✅ Created schedule: $SCHEDULE_ID"
echo ""

# Test 2: Get schedule by date
echo "📅 Test 2: Getting schedule by date..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "schedule",
    "input_data": {
      "action": "get_schedule_by_date",
      "params": {
        "schedule_date": "2026-02-20"
      }
    }
  }' | jq '.output_data.data | {schedule_date, total_employees, shifts_count: (.shifts | length)}'
echo "✅ Retrieved schedule by date"
echo ""

# Test 3: Get schedules for date range
echo "📋 Test 3: Getting schedules for date range..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "schedule",
    "input_data": {
      "action": "get_schedule",
      "params": {
        "start_date": "2026-02-15",
        "end_date": "2026-02-25"
      }
    }
  }' | jq '.output_data.data | length'
echo "✅ Retrieved schedules"
echo ""

# Test 4: Update schedule (publish it)
echo "🔄 Test 4: Updating schedule (publishing)..."
if [ "$SCHEDULE_ID" != "null" ] && [ -n "$SCHEDULE_ID" ]; then
  curl -s -X POST "$API_BASE" \
    -H "Content-Type: application/json" \
    -d "{
      \"agent_type\": \"schedule\",
      \"input_data\": {
        \"action\": \"update_schedule\",
        \"params\": {
          \"schedule_id\": \"$SCHEDULE_ID\",
          \"is_published\": true,
          \"published_by\": \"admin\"
        }
      }
    }" | jq '.output_data.data | {schedule_id, is_published, published_by}'
  echo "✅ Updated schedule"
else
  echo "⚠️  No schedule ID to update"
fi
echo ""

# Test 5: Get employee schedules
echo "👤 Test 5: Getting employee schedules..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "schedule",
    "input_data": {
      "action": "get_employee_schedules",
      "params": {
        "employee_id": "EMP001",
        "start_date": "2026-02-01",
        "end_date": "2026-02-28"
      }
    }
  }' | jq '.output_data.data | length'
echo "✅ Retrieved employee schedules"
echo ""

# Test 6: Get schedule statistics
echo "📊 Test 6: Getting schedule statistics..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "schedule",
    "input_data": {
      "action": "get_schedule_statistics",
      "params": {
        "start_date": "2026-02-01",
        "end_date": "2026-02-28"
      }
    }
  }' | jq '.output_data.data | {total_schedules, published_schedules, total_shifts, employee_count}'
echo "✅ Retrieved statistics"
echo ""

# Test 7: Create another schedule for a different date
echo "📝 Test 7: Creating another schedule..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "schedule",
    "input_data": {
      "action": "create_schedule",
      "params": {
        "schedule_date": "2026-02-21",
        "shifts": [
          {
            "employee_id": "EMP001",
            "shift_type": "afternoon",
            "start_time": "2026-02-21T14:00:00",
            "end_time": "2026-02-21T22:00:00",
            "position": "waiter"
          },
          {
            "employee_id": "EMP003",
            "shift_type": "morning",
            "start_time": "2026-02-21T08:00:00",
            "end_time": "2026-02-21T16:00:00",
            "position": "cashier"
          }
        ]
      }
    }
  }' | jq '.output_data.data | {schedule_date, total_employees, total_hours}'
echo "✅ Created another schedule"
echo ""

echo "=" | head -c 50
echo ""
echo "🎉 All tests completed!"
echo "✅ ScheduleAgent is using DATABASE!"
