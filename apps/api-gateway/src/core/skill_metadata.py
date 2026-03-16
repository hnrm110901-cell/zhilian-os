"""
Skill 业务元数据声明

40+ 个现有 Tool 的业务意图、影响品类、可组合声明、效果指标。
SkillRegistry._bootstrap_from_legacy() 读取此字典覆盖默认值。

格式：
    "agent_type.tool_name": {
        "business_intent":        str,   # 业务语义描述
        "impact_category":        str,   # cost_optimization | revenue_growth | risk_mitigation | operational
        "estimated_impact_yuan":  float, # 每次调用的估算¥影响
        "requires":               list,  # 前置 skill_ids
        "provides":               list,  # 输出标签
        "chains_with":            list,  # 可组合的 skill_ids
        "effect_metric":          str,   # 评估指标名
        "evaluation_delay_hours": int,   # N小时后评估效果
    }
"""

SKILL_BUSINESS_METADATA = {
    # ═══════════════════════════════════════════════════════════════
    # ScheduleAgent（排班）
    # ═══════════════════════════════════════════════════════════════
    "schedule.query_staff_availability": {
        "business_intent": "查询门店指定日期的员工排班可用性，为排班决策提供数据支撑",
        "impact_category": "cost_optimization",
        "estimated_impact_yuan": 200.0,
        "provides": ["staff_availability_data"],
        "chains_with": ["schedule.create_schedule_recommendation"],
        "effect_metric": "labor_cost_ratio",
        "evaluation_delay_hours": 72,
    },
    "schedule.get_customer_flow_forecast": {
        "business_intent": "预测门店客流量趋势，为人力排布和备货提供前瞻性数据",
        "impact_category": "revenue_growth",
        "estimated_impact_yuan": 150.0,
        "provides": ["customer_flow_forecast"],
        "chains_with": ["schedule.query_staff_availability", "schedule.create_schedule_recommendation"],
        "effect_metric": "labor_cost_ratio",
        "evaluation_delay_hours": 72,
    },
    "schedule.get_historical_schedule": {
        "business_intent": "查询历史排班记录，为排班优化提供基线对比数据",
        "impact_category": "cost_optimization",
        "estimated_impact_yuan": 50.0,
        "provides": ["historical_schedule_data"],
        "chains_with": ["schedule.create_schedule_recommendation"],
        "effect_metric": "labor_cost_ratio",
        "evaluation_delay_hours": 72,
    },
    "schedule.create_schedule_recommendation": {
        "business_intent": "生成智能排班建议，综合客流预测、员工可用性和成本约束",
        "impact_category": "cost_optimization",
        "estimated_impact_yuan": 500.0,
        "requires": ["schedule.query_staff_availability"],
        "provides": ["schedule_recommendation"],
        "effect_metric": "labor_cost_ratio",
        "evaluation_delay_hours": 72,
    },
    # ═══════════════════════════════════════════════════════════════
    # OrderAgent（订单）
    # ═══════════════════════════════════════════════════════════════
    "order.get_order_details": {
        "business_intent": "查询订单详情，用于订单异常分析和客户服务",
        "impact_category": "operational",
        "estimated_impact_yuan": 0.0,
        "provides": ["order_detail_data"],
        "chains_with": ["order.calculate_bill"],
        "evaluation_delay_hours": 24,
    },
    "order.query_orders_by_condition": {
        "business_intent": "按条件批量查询订单，用于营收分析和异常检测",
        "impact_category": "revenue_growth",
        "estimated_impact_yuan": 100.0,
        "provides": ["order_list_data"],
        "effect_metric": "revenue_daily",
        "evaluation_delay_hours": 24,
    },
    "order.get_menu_recommendations": {
        "business_intent": "获取菜品推荐列表，提升客单价和点餐体验",
        "impact_category": "revenue_growth",
        "estimated_impact_yuan": 300.0,
        "provides": ["menu_recommendation"],
        "effect_metric": "avg_order_value",
        "evaluation_delay_hours": 168,
    },
    "order.update_order_status": {
        "business_intent": "更新订单状态，驱动订单生命周期流转",
        "impact_category": "operational",
        "estimated_impact_yuan": 0.0,
        "provides": ["order_status_updated"],
        "evaluation_delay_hours": 24,
    },
    "order.calculate_bill": {
        "business_intent": "计算订单账单，含折扣、优惠和最终金额",
        "impact_category": "operational",
        "estimated_impact_yuan": 0.0,
        "requires": ["order.get_order_details"],
        "provides": ["bill_data"],
        "evaluation_delay_hours": 24,
    },
    # ═══════════════════════════════════════════════════════════════
    # InventoryAgent（库存）
    # ═══════════════════════════════════════════════════════════════
    "inventory.get_inventory_status": {
        "business_intent": "查询门店食材库存实时状态，为补货和损耗预警提供依据",
        "impact_category": "cost_optimization",
        "estimated_impact_yuan": 150.0,
        "provides": ["inventory_status_data"],
        "chains_with": ["inventory.create_purchase_order", "inventory.check_expiry_alerts"],
        "effect_metric": "waste_rate",
        "evaluation_delay_hours": 48,
    },
    "inventory.get_consumption_trend": {
        "business_intent": "分析食材消耗趋势，预测未来用量，减少过量采购导致的损耗",
        "impact_category": "cost_optimization",
        "estimated_impact_yuan": 200.0,
        "provides": ["consumption_trend_data"],
        "chains_with": ["inventory.create_purchase_order"],
        "effect_metric": "waste_rate",
        "evaluation_delay_hours": 48,
    },
    "inventory.create_purchase_order": {
        "business_intent": "生成采购建议单，基于库存状态和消耗预测优化采购量",
        "impact_category": "cost_optimization",
        "estimated_impact_yuan": 500.0,
        "requires": ["inventory.get_inventory_status"],
        "provides": ["purchase_order"],
        "effect_metric": "purchase_cost",
        "evaluation_delay_hours": 72,
    },
    "inventory.check_expiry_alerts": {
        "business_intent": "检查临期食材预警，及时处理避免损耗",
        "impact_category": "risk_mitigation",
        "estimated_impact_yuan": 300.0,
        "provides": ["expiry_alert_data"],
        "chains_with": ["inventory.get_inventory_status"],
        "effect_metric": "waste_rate",
        "evaluation_delay_hours": 48,
    },
    # ═══════════════════════════════════════════════════════════════
    # ServiceAgent（服务质量）
    # ═══════════════════════════════════════════════════════════════
    "service.get_service_quality_metrics": {
        "business_intent": "获取服务质量指标（翻台率、等位时间、差评率），定位服务短板",
        "impact_category": "revenue_growth",
        "estimated_impact_yuan": 100.0,
        "provides": ["service_quality_data"],
        "effect_metric": "customer_satisfaction",
        "evaluation_delay_hours": 168,
    },
    "service.analyze_customer_feedback": {
        "business_intent": "分析客户反馈和评价，提取改进方向",
        "impact_category": "revenue_growth",
        "estimated_impact_yuan": 100.0,
        "provides": ["feedback_analysis"],
        "effect_metric": "customer_satisfaction",
        "evaluation_delay_hours": 168,
    },
    "service.get_wait_time_analysis": {
        "business_intent": "分析等位时间分布，优化排队策略减少客流损失",
        "impact_category": "revenue_growth",
        "estimated_impact_yuan": 200.0,
        "provides": ["wait_time_data"],
        "effect_metric": "queue_conversion_rate",
        "evaluation_delay_hours": 168,
    },
    # ═══════════════════════════════════════════════════════════════
    # TrainingAgent（培训）
    # ═══════════════════════════════════════════════════════════════
    "training.get_training_needs": {
        "business_intent": "分析员工培训需求，基于绩效数据和技能差距定位薄弱环节",
        "impact_category": "operational",
        "estimated_impact_yuan": 50.0,
        "provides": ["training_needs_data"],
        "chains_with": ["training.create_training_plan"],
        "effect_metric": "employee_skill_score",
        "evaluation_delay_hours": 168,
    },
    "training.create_training_plan": {
        "business_intent": "生成个性化培训计划，提升员工技能和服务质量",
        "impact_category": "operational",
        "estimated_impact_yuan": 100.0,
        "requires": ["training.get_training_needs"],
        "provides": ["training_plan"],
        "effect_metric": "employee_skill_score",
        "evaluation_delay_hours": 168,
    },
    "training.get_training_progress": {
        "business_intent": "追踪培训执行进度，确保培训计划落地",
        "impact_category": "operational",
        "estimated_impact_yuan": 0.0,
        "provides": ["training_progress_data"],
        "evaluation_delay_hours": 168,
    },
    # ═══════════════════════════════════════════════════════════════
    # DecisionAgent（决策）
    # ═══════════════════════════════════════════════════════════════
    "decision.analyze_revenue_anomaly": {
        "business_intent": "分析营收异常原因，定位收入波动的根因并给出应对建议",
        "impact_category": "revenue_growth",
        "estimated_impact_yuan": 1000.0,
        "provides": ["revenue_anomaly_analysis"],
        "effect_metric": "revenue_recovery",
        "evaluation_delay_hours": 24,
    },
    "decision.evaluate_business_impact": {
        "business_intent": "评估业务决策的预期影响，为店长提供量化参考",
        "impact_category": "operational",
        "estimated_impact_yuan": 0.0,
        "provides": ["business_impact_assessment"],
        "evaluation_delay_hours": 72,
    },
    "decision.get_decision_history": {
        "business_intent": "查询历史决策记录和执行效果，支持决策复盘",
        "impact_category": "operational",
        "estimated_impact_yuan": 0.0,
        "provides": ["decision_history_data"],
        "evaluation_delay_hours": 72,
    },
    # ═══════════════════════════════════════════════════════════════
    # ReservationAgent（预订）
    # ═══════════════════════════════════════════════════════════════
    "reservation.query_reservations": {
        "business_intent": "查询预订列表，支持按日期/状态/客户筛选",
        "impact_category": "operational",
        "estimated_impact_yuan": 0.0,
        "provides": ["reservation_list_data"],
        "evaluation_delay_hours": 24,
    },
    "reservation.check_availability": {
        "business_intent": "检查桌位/包间可用性，为预订决策提供实时信息",
        "impact_category": "revenue_growth",
        "estimated_impact_yuan": 100.0,
        "provides": ["table_availability_data"],
        "chains_with": ["reservation.create_reservation"],
        "effect_metric": "table_utilization_rate",
        "evaluation_delay_hours": 24,
    },
    "reservation.create_reservation": {
        "business_intent": "创建预订记录，锁定桌位并触发备餐流程",
        "impact_category": "revenue_growth",
        "estimated_impact_yuan": 200.0,
        "requires": ["reservation.check_availability"],
        "provides": ["reservation_created"],
        "effect_metric": "reservation_show_rate",
        "evaluation_delay_hours": 24,
    },
    "reservation.update_reservation_status": {
        "business_intent": "更新预订状态，驱动预订生命周期流转（到店/入座/完成/取消）",
        "impact_category": "operational",
        "estimated_impact_yuan": 0.0,
        "provides": ["reservation_status_updated"],
        "evaluation_delay_hours": 24,
    },
    # ═══════════════════════════════════════════════════════════════
    # OpsAgent（运营）
    # ═══════════════════════════════════════════════════════════════
    "ops.get_store_health": {
        "business_intent": "获取门店运营健康度综合评分，涵盖营收/成本/服务/人效四个维度",
        "impact_category": "operational",
        "estimated_impact_yuan": 0.0,
        "provides": ["store_health_data"],
        "chains_with": ["ops.get_ops_alerts"],
        "evaluation_delay_hours": 24,
    },
    "ops.get_ops_alerts": {
        "business_intent": "获取运营告警列表，包含异常事件和处理建议",
        "impact_category": "risk_mitigation",
        "estimated_impact_yuan": 300.0,
        "provides": ["ops_alert_data"],
        "effect_metric": "alert_resolution_time",
        "evaluation_delay_hours": 24,
    },
    "ops.get_daily_report": {
        "business_intent": "生成门店日报，汇总营收/客流/成本/异常等核心指标",
        "impact_category": "operational",
        "estimated_impact_yuan": 0.0,
        "provides": ["daily_report_data"],
        "evaluation_delay_hours": 24,
    },
    # ═══════════════════════════════════════════════════════════════
    # PerformanceAgent（绩效）
    # ═══════════════════════════════════════════════════════════════
    "performance.get_employee_performance": {
        "business_intent": "获取员工绩效数据，含KPI达成率/排名/趋势",
        "impact_category": "operational",
        "estimated_impact_yuan": 50.0,
        "provides": ["employee_performance_data"],
        "chains_with": ["performance.calculate_commission"],
        "effect_metric": "employee_productivity",
        "evaluation_delay_hours": 168,
    },
    "performance.calculate_commission": {
        "business_intent": "计算员工提成/奖金，基于绩效规则自动核算",
        "impact_category": "cost_optimization",
        "estimated_impact_yuan": 100.0,
        "requires": ["performance.get_employee_performance"],
        "provides": ["commission_data"],
        "effect_metric": "labor_cost_ratio",
        "evaluation_delay_hours": 168,
    },
    "performance.get_store_ranking": {
        "business_intent": "获取多门店排名对比，发现标杆门店和待改进门店",
        "impact_category": "revenue_growth",
        "estimated_impact_yuan": 200.0,
        "provides": ["store_ranking_data"],
        "effect_metric": "composite_score",
        "evaluation_delay_hours": 168,
    },
}
