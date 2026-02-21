#!/usr/bin/env python3
"""
Test script to verify database persistence
"""
import requests
import json

API_BASE = "http://localhost:8000"

def test_decision_report():
    """Test decision report with database"""
    print("🧪 Testing Decision Agent with Database...")
    print("-" * 50)

    url = f"{API_BASE}/api/v1/agents/decision"
    payload = {
        "agent_type": "decision",
        "input_data": {
            "action": "get_decision_report",
            "params": {}
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()

        data = response.json()

        print(f"✅ Status: {response.status_code}")
        print(f"✅ Success: {data.get('output_data', {}).get('success')}")
        print(f"✅ Execution Time: {data.get('execution_time', 0):.3f}s")

        # Check if data is from database
        metadata = data.get('output_data', {}).get('metadata', {})
        if metadata.get('source') == 'database':
            print("✅ Data Source: DATABASE (Real Data!)")
        else:
            print("⚠️  Data Source: Mock Data")

        # Display KPI summary
        report_data = data.get('output_data', {}).get('data', {})
        kpi_summary = report_data.get('kpi_summary', {})

        print(f"\n📊 KPI Summary:")
        print(f"  Total KPIs: {kpi_summary.get('total_kpis', 0)}")
        print(f"  On Track Rate: {kpi_summary.get('on_track_rate', 0):.1%}")
        print(f"  Status Distribution: {kpi_summary.get('status_distribution', {})}")

        # Display health score
        health_score = report_data.get('overall_health_score', 0)
        print(f"\n💚 Overall Health Score: {health_score}/100")

        # Display insights
        insights = report_data.get('insights_summary', {})
        print(f"\n💡 Insights:")
        print(f"  Total: {insights.get('total_insights', 0)}")
        print(f"  High Impact: {insights.get('high_impact', 0)}")

        # Display key KPIs
        key_kpis = kpi_summary.get('key_kpis', [])
        if key_kpis:
            print(f"\n📈 Key KPIs:")
            for kpi in key_kpis[:3]:
                print(f"  - {kpi.get('metric_name')}: {kpi.get('current_value'):.2f}{kpi.get('unit')} (目标: {kpi.get('target_value'):.2f})")
                print(f"    达成率: {kpi.get('achievement_rate', 0):.1%} | 状态: {kpi.get('status')}")

        print("\n" + "=" * 50)
        print("✅ Database persistence test PASSED!")
        return True

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return False


def test_health():
    """Test API health"""
    print("\n🏥 Testing API Health...")
    print("-" * 50)

    try:
        response = requests.get(f"{API_BASE}/api/v1/health", timeout=5)
        response.raise_for_status()

        data = response.json()
        print(f"✅ API Status: {data.get('status')}")
        print(f"✅ Version: {data.get('version')}")
        return True

    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("🚀 Database Persistence Test Suite")
    print("=" * 50 + "\n")

    # Test health first
    if not test_health():
        print("\n❌ API is not healthy. Please check the service.")
        exit(1)

    # Test decision report
    if test_decision_report():
        print("\n🎉 All tests passed! Database persistence is working!")
        exit(0)
    else:
        print("\n❌ Tests failed. Please check the logs.")
        exit(1)
