#!/usr/bin/env python3
"""
智链OS业务流程演示脚本
演示7个Agent在真实餐厅场景中的协同工作
"""

import requests
import json
import time
from datetime import datetime
from typing import Dict, Any

# API配置
API_BASE_URL = "http://localhost:8000/api/v1/agents"

class Colors:
    """终端颜色"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    """打印标题"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text:^80}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.END}\n")

def print_section(text: str):
    """打印章节"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}>>> {text}{Colors.END}\n")

def print_success(text: str):
    """打印成功信息"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_info(text: str):
    """打印信息"""
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")

def print_warning(text: str):
    """打印警告"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.END}")

def call_agent(agent_type: str, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """调用Agent"""
    url = f"{API_BASE_URL}/{agent_type}"
    data = {
        "agent_type": agent_type,
        "input_data": {
            "action": action,
            "params": params
        }
    }

    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print_warning(f"Agent调用失败: {e}")
        return {"error": str(e)}

def demo_scenario_1():
    """场景1: 智能排班"""
    print_header("场景1: 新的一天开始 - 智能排班")

    print_section("业务需求: 为2024年1月15日安排员工排班")

    print_info("调用 ScheduleAgent...")
    result = call_agent("schedule", "run", {
        "store_id": "STORE001",
        "date": "2024-01-15",
        "employees": [
            {"id": "EMP001", "name": "张三", "role": "waiter", "skill_level": 0.9},
            {"id": "EMP002", "name": "李四", "role": "chef", "skill_level": 0.95},
            {"id": "EMP003", "name": "王五", "role": "waiter", "skill_level": 0.85},
            {"id": "EMP004", "name": "赵六", "role": "cashier", "skill_level": 0.88}
        ]
    })

    if "output_data" in result and result["output_data"]["success"]:
        data = result["output_data"]["data"]
        prediction = data.get("traffic_prediction", {})
        requirements = data.get("requirements", {})

        print_success("排班计划生成成功!")
        print(f"\n📊 客流预测:")
        print(f"  • 早班: {prediction.get('predicted_customers', {}).get('morning', 0)}人")
        print(f"  • 午班: {prediction.get('predicted_customers', {}).get('afternoon', 0)}人")
        print(f"  • 晚班: {prediction.get('predicted_customers', {}).get('evening', 0)}人")
        print(f"  • 置信度: {prediction.get('confidence', 0):.0%}")

        print(f"\n👥 人员需求:")
        for shift, needs in requirements.items():
            total = sum(needs.values())
            print(f"  • {shift}班: {total}人 (服务员{needs.get('waiter', 0)} + 厨师{needs.get('chef', 0)} + 收银{needs.get('cashier', 0)})")

        print(f"\n⏱️  执行时间: {result['execution_time']:.3f}秒")
    else:
        print_warning("排班计划生成失败")

    time.sleep(2)

def demo_scenario_2():
    """场景2: 预定与排队管理"""
    print_header("场景2: 早餐时段 - 预定与排队管理")

    # 2.1 创建预定
    print_section("2.1 客户通过小程序预定座位")
    print_info("调用 ReservationAgent...")

    result = call_agent("reservation", "create_reservation", {
        "customer_id": "CUST001",
        "customer_name": "陈先生",
        "customer_phone": "13800138000",
        "reservation_date": "2024-01-15",
        "reservation_time": "12:00",
        "party_size": 4,
        "special_requests": "靠窗座位"
    })

    if "output_data" in result and result["output_data"]["success"]:
        data = result["output_data"]["data"]
        print_success("预定创建成功!")
        print(f"  • 预定ID: {data.get('reservation_id', 'N/A')}")
        print(f"  • 客户: {data.get('customer_name', 'N/A')}")
        print(f"  • 人数: {data.get('party_size', 0)}人")
        print(f"  • 时间: {data.get('reservation_date', '')} {data.get('reservation_time', '')}")
        print(f"  • 预估消费: ¥{data.get('estimated_amount', 0)/100:.2f}")
        print(f"  • 定金: ¥{data.get('deposit_amount', 0)/100:.2f}")
    else:
        print_warning("预定创建失败")

    time.sleep(1)

    # 2.2 现场排队
    print_section("2.2 客户现场排队")
    print_info("调用 OrderAgent...")

    result = call_agent("order", "join_queue", {
        "store_id": "STORE001",
        "customer_name": "刘女士",
        "customer_phone": "13900139000",
        "party_size": 2
    })

    if "output_data" in result and result["output_data"]["success"]:
        data = result["output_data"]["data"]
        print_success("排队成功!")
        print(f"  • 排队号: {data.get('queue_number', 'N/A')}")
        print(f"  • 前面等待: {data.get('ahead_count', 0)}桌")
        print(f"  • 预计等待: {data.get('estimated_wait_time', 0)}分钟")
    else:
        print_warning("排队失败")

    time.sleep(2)

def demo_scenario_3():
    """场景3: 点单与推荐"""
    print_header("场景3: 午餐高峰 - 点单与推荐")

    # 3.1 创建订单
    print_section("3.1 客户入座，创建订单")
    print_info("调用 OrderAgent...")

    result = call_agent("order", "create_order", {
        "store_id": "STORE001",
        "table_id": "T05",
        "customer_id": "CUST001"
    })

    if "output_data" in result and result["output_data"]["success"]:
        data = result["output_data"]["data"]
        print_success("订单创建成功!")
        print(f"  • 订单ID: {data.get('order_id', 'N/A')}")
        print(f"  • 桌号: {data.get('table_id', 'N/A')}")
    else:
        print_warning("订单创建失败")

    time.sleep(1)

    # 3.2 智能推荐
    print_section("3.2 AI智能推荐菜品")
    print_info("调用 OrderAgent...")

    result = call_agent("order", "recommend_dishes", {
        "order_id": "ORD001",
        "customer_preferences": ["川菜", "不辣"],
        "budget": 300
    })

    if "output_data" in result and result["output_data"]["success"]:
        data = result["output_data"]["data"]
        recommendations = data.get("recommendations", [])
        print_success(f"推荐{len(recommendations)}道菜品:")
        for i, dish in enumerate(recommendations[:3], 1):
            print(f"  {i}. {dish.get('name', 'N/A')} - ¥{dish.get('price', 0)/100:.2f}")
            print(f"     {dish.get('reason', '')}")
    else:
        print_warning("推荐失败")

    time.sleep(1)

    # 3.3 检查库存
    print_section("3.3 检查食材库存")
    print_info("调用 InventoryAgent...")

    result = call_agent("inventory", "monitor_inventory", {
        "category": "主菜食材"
    })

    if "output_data" in result and result["output_data"]["success"]:
        items = result["output_data"]["data"]
        print_success(f"库存检查完成，共{len(items)}项")
        if len(items) > 0:
            print("  前3项库存状态:")
            for item in items[:3]:
                status_icon = "✓" if item.get("status") == "sufficient" else "⚠"
                print(f"  {status_icon} {item.get('item_name', 'N/A')}: {item.get('current_stock', 0)}{item.get('unit', '')}")
    else:
        print_info("暂无库存数据")

    time.sleep(2)

def demo_scenario_4():
    """场景4: 库存预警与补货"""
    print_header("场景4: 下午时段 - 库存预警与补货")

    # 4.1 生成补货提醒
    print_section("4.1 系统自动生成补货提醒")
    print_info("调用 InventoryAgent...")

    result = call_agent("inventory", "generate_restock_alerts", {
        "category": "全部"
    })

    if "output_data" in result and result["output_data"]["success"]:
        alerts = result["output_data"]["data"]
        if len(alerts) > 0:
            print_warning(f"发现{len(alerts)}个补货提醒:")
            for alert in alerts[:3]:
                level_icon = "🔴" if alert.get("alert_level") == "urgent" else "🟡"
                print(f"  {level_icon} {alert.get('item_name', 'N/A')}")
                print(f"     当前库存: {alert.get('current_stock', 0)}")
                print(f"     建议补货: {alert.get('recommended_quantity', 0)}")
                print(f"     原因: {alert.get('reason', '')}")
        else:
            print_success("库存充足，无需补货")
    else:
        print_info("暂无补货提醒")

    time.sleep(2)

def demo_scenario_5():
    """场景5: 服务质量监控"""
    print_header("场景5: 晚餐时段 - 服务质量监控")

    # 5.1 监控服务质量
    print_section("5.1 实时监控服务质量")
    print_info("调用 ServiceAgent...")

    result = call_agent("service", "monitor_service_quality", {
        "start_date": "2024-01-15",
        "end_date": "2024-01-15"
    })

    if "output_data" in result and result["output_data"]["success"]:
        data = result["output_data"]["data"]
        print_success("服务质量监控完成!")
        print(f"  • 平均响应时间: {data.get('avg_response_time', 0)}分钟")
        print(f"  • 客户满意度: {data.get('satisfaction_rate', 0):.1%}")
        print(f"  • 投诉率: {data.get('complaint_rate', 0):.1%}")
        print(f"  • 服务评分: {data.get('service_score', 0):.1f}/5.0")
    else:
        print_info("暂无服务数据")

    time.sleep(2)

def demo_scenario_6():
    """场景6: 数据分析与决策"""
    print_header("场景6: 营业结束 - 数据分析与决策")

    # 6.1 分析KPI
    print_section("6.1 分析当日KPI指标")
    print_info("调用 DecisionAgent...")

    result = call_agent("decision", "analyze_kpis", {
        "start_date": "2024-01-15",
        "end_date": "2024-01-15"
    })

    if "output_data" in result and result["output_data"]["success"]:
        kpis = result["output_data"]["data"]
        print_success(f"KPI分析完成，共{len(kpis)}个指标:")
        for kpi in kpis[:3]:
            status_icon = "✓" if kpi.get("status") == "on_track" else "⚠"
            print(f"  {status_icon} {kpi.get('metric_name', 'N/A')}")
            print(f"     当前值: {kpi.get('current_value', 0):.2f}{kpi.get('unit', '')}")
            print(f"     目标值: {kpi.get('target_value', 0):.2f}{kpi.get('unit', '')}")
            print(f"     达成率: {kpi.get('achievement_rate', 0):.1%}")
    else:
        print_info("暂无KPI数据")

    time.sleep(1)

    # 6.2 生成业务洞察
    print_section("6.2 生成业务洞察")
    print_info("调用 DecisionAgent...")

    result = call_agent("decision", "generate_insights", {})

    if "output_data" in result and result["output_data"]["success"]:
        insights = result["output_data"]["data"]
        if len(insights) > 0:
            print_success(f"发现{len(insights)}个业务洞察:")
            for insight in insights[:2]:
                print(f"  💡 {insight.get('title', 'N/A')}")
                print(f"     {insight.get('description', '')}")
                print(f"     影响程度: {insight.get('impact_level', 'N/A')}")
        else:
            print_info("暂无特殊洞察")
    else:
        print_info("暂无洞察数据")

    time.sleep(1)

    # 6.3 生成改进建议
    print_section("6.3 生成改进建议")
    print_info("调用 DecisionAgent...")

    result = call_agent("decision", "generate_recommendations", {})

    if "output_data" in result and result["output_data"]["success"]:
        recommendations = result["output_data"]["data"]
        if len(recommendations) > 0:
            print_success(f"生成{len(recommendations)}条改进建议:")
            for rec in recommendations[:2]:
                priority_icon = "🔴" if rec.get("priority") == "critical" else "🟡"
                print(f"  {priority_icon} {rec.get('title', 'N/A')}")
                print(f"     优先级: {rec.get('priority', 'N/A')}")
                print(f"     预期影响: {rec.get('expected_impact', '')}")
        else:
            print_info("暂无改进建议")
    else:
        print_info("暂无建议数据")

    time.sleep(2)

def demo_scenario_7():
    """场景7: 员工培训"""
    print_header("场景7: 每周培训 - 员工技能提升")

    # 7.1 评估培训需求
    print_section("7.1 评估员工培训需求")
    print_info("调用 TrainingAgent...")

    result = call_agent("training", "assess_training_needs", {
        "staff_id": "EMP001"
    })

    if "output_data" in result and result["output_data"]["success"]:
        needs = result["output_data"]["data"]
        if len(needs) > 0:
            print_success(f"识别{len(needs)}个培训需求:")
            for need in needs[:2]:
                print(f"  📚 {need.get('staff_name', 'N/A')} - {need.get('skill_gap', 'N/A')}")
                print(f"     当前水平: {need.get('current_level', 'N/A')}")
                print(f"     目标水平: {need.get('target_level', 'N/A')}")
                print(f"     优先级: {need.get('priority', 'N/A')}")
        else:
            print_info("暂无培训需求")
    else:
        print_info("暂无需求数据")

    time.sleep(1)

    # 7.2 生成培训计划
    print_section("7.2 生成培训计划")
    print_info("调用 TrainingAgent...")

    result = call_agent("training", "generate_training_plan", {
        "staff_id": "EMP001"
    })

    if "output_data" in result and result["output_data"]["success"]:
        plan = result["output_data"]["data"]
        print_success("培训计划生成成功!")
        print(f"  • 计划ID: {plan.get('plan_id', 'N/A')}")
        print(f"  • 员工: {plan.get('staff_name', 'N/A')}")
        print(f"  • 课程数: {len(plan.get('courses', []))}")
        print(f"  • 总时长: {plan.get('total_hours', 0)}小时")
        print(f"  • 开始日期: {plan.get('start_date', 'N/A')}")
        print(f"  • 结束日期: {plan.get('end_date', 'N/A')}")
    else:
        print_info("暂无计划数据")

    time.sleep(2)

def main():
    """主函数"""
    print_header("智链OS 业务流程演示")
    print(f"{Colors.BOLD}演示7个智能Agent在真实餐厅场景中的协同工作{Colors.END}\n")
    print(f"API地址: {API_BASE_URL}")
    print(f"演示时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    input(f"\n{Colors.CYAN}按Enter键开始演示...{Colors.END}")

    try:
        # 执行所有场景
        demo_scenario_1()  # 智能排班
        demo_scenario_2()  # 预定与排队
        demo_scenario_3()  # 点单与推荐
        demo_scenario_4()  # 库存预警
        demo_scenario_5()  # 服务监控
        demo_scenario_6()  # 数据分析
        demo_scenario_7()  # 员工培训

        # 总结
        print_header("演示完成")
        print_success("所有业务场景演示完成!")
        print(f"\n{Colors.BOLD}系统优势:{Colors.END}")
        print("  ✓ 7个智能Agent协同工作")
        print("  ✓ 覆盖餐厅全业务流程")
        print("  ✓ 数据驱动智能决策")
        print("  ✓ 持续学习优化")

        print(f"\n{Colors.BOLD}业务价值:{Colors.END}")
        print("  • 降低人力成本 15-20%")
        print("  • 降低库存成本 20%")
        print("  • 提升客户满意度至 92%")
        print("  • 提升营收 15-20%")

    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}演示被用户中断{Colors.END}")
    except Exception as e:
        print(f"\n\n{Colors.FAIL}演示出错: {e}{Colors.END}")

if __name__ == "__main__":
    main()
