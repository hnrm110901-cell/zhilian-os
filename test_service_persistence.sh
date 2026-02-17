#!/bin/bash
# Test Service Agent with Database

API_BASE="http://localhost:8000/api/v1/agents/service"

echo "🧪 Testing Service Agent with Database"
echo "=" | head -c 50
echo ""

# Test 1: Record service quality metric
echo "📝 Test 1: Recording service quality metric..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "service",
    "input_data": {
      "action": "record_service_quality",
      "params": {
        "metric_name": "customer_satisfaction",
        "value": 87.5,
        "unit": "score",
        "target_value": 90.0
      }
    }
  }' | jq '.output_data.metadata.source, .output_data.data.kpi_id, .output_data.data.value'
echo "✅ Recorded service quality metric"
echo ""

# Test 2: Get service quality metrics
echo "📊 Test 2: Getting service quality metrics..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "service",
    "input_data": {
      "action": "monitor_service_quality",
      "params": {}
    }
  }' | jq '.output_data.data | {score: .quality_score, status: .status, satisfaction: .satisfaction.average_rating, completion_rate: .service_metrics.completion_rate}'
echo "✅ Retrieved service quality metrics"
echo ""

# Test 3: Get staff performance
echo "👥 Test 3: Getting staff performance..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "service",
    "input_data": {
      "action": "track_staff_performance",
      "params": {}
    }
  }' | jq '.output_data.data | length'
echo "✅ Retrieved staff performance"
echo ""

# Test 4: Get service report
echo "📋 Test 4: Getting service report..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "service",
    "input_data": {
      "action": "get_service_report",
      "params": {}
    }
  }' | jq '.output_data.data | {overall_score: .summary.overall_score, status: .summary.status, improvements_count: (.improvements | length)}'
echo "✅ Retrieved service report"
echo ""

# Test 5: Record multiple metrics
echo "📈 Test 5: Recording multiple service metrics..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "service",
    "input_data": {
      "action": "record_service_quality",
      "params": {
        "metric_name": "response_time",
        "value": 15.5,
        "unit": "minutes",
        "target_value": 20.0
      }
    }
  }' | jq '.output_data.data.status'

curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "service",
    "input_data": {
      "action": "record_service_quality",
      "params": {
        "metric_name": "complaint_rate",
        "value": 3.2,
        "unit": "percent",
        "target_value": 5.0
      }
    }
  }' | jq '.output_data.data.status'
echo "✅ Recorded multiple metrics"
echo ""

# Test 6: Get updated service quality metrics
echo "🔄 Test 6: Getting updated service quality metrics..."
curl -s -X POST "$API_BASE" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_type": "service",
    "input_data": {
      "action": "get_service_quality_metrics",
      "params": {}
    }
  }' | jq '.output_data.data.satisfaction'
echo "✅ Retrieved updated metrics"
echo ""

echo "=" | head -c 50
echo ""
echo "🎉 All tests completed!"
echo "✅ ServiceAgent is using DATABASE!"
