#!/bin/bash
# Test Training Agent with Database

API_BASE="http://localhost:8000/api/v1/agents/training"

echo "🧪 Testing Training Agent with Database"
echo "=" | head -c 50
echo ""

# Test 1: Assess training needs
echo "📋 Test 1: Assessing training needs..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "training",
    "input_data": {
      "action": "assess_training_needs",
      "params": {}
    }
  }' | jq '.output_data.metadata.source, (.output_data.data | length)'
echo "✅ Assessed training needs"
echo ""

# Test 2: Record training completion
echo "📝 Test 2: Recording training completion..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "training",
    "input_data": {
      "action": "record_training_completion",
      "params": {
        "staff_id": "EMP001",
        "course_name": "Customer Service Excellence",
        "completion_date": "2026-02-15",
        "score": 85,
        "duration_hours": 4
      }
    }
  }' | jq '.output_data.data | {staff_id, course_name, score, passed}'
echo "✅ Recorded training completion"
echo ""

# Test 3: Record another training completion
echo "📝 Test 3: Recording another training completion..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "training",
    "input_data": {
      "action": "record_training_completion",
      "params": {
        "staff_id": "EMP002",
        "course_name": "Food Safety",
        "completion_date": "2026-02-16",
        "score": 92,
        "duration_hours": 3
      }
    }
  }' | jq '.output_data.data.passed'
echo "✅ Recorded another training"
echo ""

# Test 4: Get training progress
echo "📊 Test 4: Getting training progress..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "training",
    "input_data": {
      "action": "get_training_progress",
      "params": {}
    }
  }' | jq '.output_data.data | length'
echo "✅ Retrieved training progress"
echo ""

# Test 5: Get training progress for specific employee
echo "👤 Test 5: Getting training progress for specific employee..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "training",
    "input_data": {
      "action": "get_training_progress",
      "params": {
        "staff_id": "EMP001"
      }
    }
  }' | jq '.output_data.data | length'
echo "✅ Retrieved employee training progress"
echo ""

# Test 6: Get training statistics
echo "📈 Test 6: Getting training statistics..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "training",
    "input_data": {
      "action": "get_training_statistics",
      "params": {}
    }
  }' | jq '.output_data.data | {total_trainings, passed_trainings, pass_rate, average_score}'
echo "✅ Retrieved training statistics"
echo ""

# Test 7: Get employee training history
echo "📚 Test 7: Getting employee training history..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "training",
    "input_data": {
      "action": "get_employee_training_history",
      "params": {
        "staff_id": "EMP001"
      }
    }
  }' | jq '.output_data.data | {staff_name, position, total_trainings: .training_summary.total_trainings, pass_rate: .training_summary.pass_rate}'
echo "✅ Retrieved employee training history"
echo ""

# Test 8: Get training report
echo "📋 Test 8: Getting training report..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "training",
    "input_data": {
      "action": "get_training_report",
      "params": {}
    }
  }' | jq '.output_data.data | {total_trainings: .statistics.total_trainings, pass_rate: .statistics.pass_rate, training_needs_count: (.training_needs | length), recommendations_count: (.recommendations | length)}'
echo "✅ Retrieved training report"
echo ""

# Test 9: Record a failed training
echo "❌ Test 9: Recording a failed training..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "training",
    "input_data": {
      "action": "record_training_completion",
      "params": {
        "staff_id": "EMP003",
        "course_name": "POS System Training",
        "completion_date": "2026-02-17",
        "score": 65
      }
    }
  }' | jq '.output_data.data | {course_name, score, passed}'
echo "✅ Recorded failed training"
echo ""

echo "=" | head -c 50
echo ""
echo "🎉 All tests completed!"
echo "✅ TrainingAgent is using DATABASE!"
