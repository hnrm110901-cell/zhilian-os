"""
Claude Tool Use 工具注册表

为屯象OS每个Agent定义标准化工具集（Claude Tool Use JSON Schema格式）。
工具执行路由器负责将 Claude 的 tool_use 请求分发到对应的业务服务。

使用方式：
    from .agent_tools import get_tools_for_agent, ToolExecutor

    tools = get_tools_for_agent("schedule")
    executor = ToolExecutor(db=db, store_id=store_id)
    result = await llm_client.generate_with_tools(
        messages=messages,
        tools=tools,
        tool_executor=executor.execute,
        system_prompt=system_prompt,
    )
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# 工具定义 — Claude Tool Use JSON Schema 格式
# ─────────────────────────────────────────────────────────────────────────────

# ── ScheduleAgent 工具集 ──────────────────────────────────────────────────────
SCHEDULE_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "query_staff_availability",
        "description": "查询指定门店在某日期范围内员工的可用性和排班状态",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "date": {"type": "string", "description": "日期，格式 YYYY-MM-DD"},
                "shift_type": {
                    "type": "string",
                    "enum": ["morning", "afternoon", "evening", "all"],
                    "description": "班次类型",
                },
            },
            "required": ["store_id", "date"],
        },
    },
    {
        "name": "get_customer_flow_forecast",
        "description": "获取门店指定日期的客流预测数据（基于历史数据和节假日因素）",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "date": {"type": "string", "description": "日期，格式 YYYY-MM-DD"},
            },
            "required": ["store_id", "date"],
        },
    },
    {
        "name": "get_historical_schedule",
        "description": "获取门店历史排班数据，用于分析排班规律",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "days_back": {"type": "integer", "description": "往前查询天数，默认30", "default": 30},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "create_schedule_recommendation",
        "description": "根据分析结果生成排班建议并写入系统",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "date": {"type": "string", "description": "日期"},
                "recommended_staff": {"type": "integer", "description": "建议排班人数"},
                "shift_breakdown": {
                    "type": "object",
                    "description": "各班次人数分配，如 {morning: 3, afternoon: 4, evening: 3}",
                },
                "reasoning": {"type": "string", "description": "排班建议的推理依据"},
            },
            "required": ["store_id", "date", "recommended_staff"],
        },
    },
]

# ── OrderAgent 工具集 ─────────────────────────────────────────────────────────
ORDER_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_order_details",
        "description": "获取订单详情，包括菜品、金额、状态等",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "订单ID"},
                "store_id": {"type": "string", "description": "门店ID（可选，用于验证）"},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "query_orders_by_condition",
        "description": "按条件查询订单列表（状态、时间范围、桌号等）",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "confirmed", "in_progress", "completed", "cancelled"],
                    "description": "订单状态",
                },
                "date": {"type": "string", "description": "日期 YYYY-MM-DD"},
                "table_number": {"type": "string", "description": "桌号"},
                "limit": {"type": "integer", "description": "返回数量上限，默认20", "default": 20},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "get_menu_recommendations",
        "description": "根据客户历史偏好和当前热销菜品，生成个性化菜品推荐",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "customer_id": {"type": "string", "description": "客户ID（可选）"},
                "party_size": {"type": "integer", "description": "用餐人数"},
                "budget_per_person": {"type": "number", "description": "人均预算（元）"},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "update_order_status",
        "description": "更新订单状态（需要 Human-in-the-Loop 确认的操作会自动标记）",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "订单ID"},
                "new_status": {
                    "type": "string",
                    "enum": ["confirmed", "in_progress", "completed", "cancelled"],
                },
                "reason": {"type": "string", "description": "状态变更原因"},
            },
            "required": ["order_id", "new_status"],
        },
    },
    {
        "name": "calculate_bill",
        "description": "计算订单账单，包含折扣、优惠券、服务费等",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "订单ID"},
                "coupon_code": {"type": "string", "description": "优惠券码（可选）"},
                "member_id": {"type": "string", "description": "会员ID（可选，用于会员折扣）"},
            },
            "required": ["order_id"],
        },
    },
]

# ── InventoryAgent 工具集 ─────────────────────────────────────────────────────
INVENTORY_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_inventory_status",
        "description": "获取门店当前库存状态，包括库存量、安全库存、预警状态",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "category": {"type": "string", "description": "食材分类（可选，不填则返回全部）"},
                "alert_only": {"type": "boolean", "description": "是否只返回预警库存", "default": False},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "get_consumption_trend",
        "description": "获取食材消耗趋势，用于预测补货需求",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "ingredient_id": {"type": "string", "description": "食材ID（可选）"},
                "days": {"type": "integer", "description": "分析天数，默认30", "default": 30},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "create_purchase_order",
        "description": "创建采购订单（超过阈值需要店长审批）",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "items": {
                    "type": "array",
                    "description": "采购清单",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ingredient_id": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit": {"type": "string"},
                        },
                    },
                },
                "urgency": {
                    "type": "string",
                    "enum": ["normal", "urgent", "critical"],
                    "description": "紧急程度",
                },
            },
            "required": ["store_id", "items"],
        },
    },
    {
        "name": "check_expiry_alerts",
        "description": "检查即将过期的食材，返回需要优先使用或处理的清单",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "days_ahead": {"type": "integer", "description": "提前预警天数，默认3", "default": 3},
            },
            "required": ["store_id"],
        },
    },
]

# ── ServiceAgent 工具集 ───────────────────────────────────────────────────────
SERVICE_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_customer_feedback",
        "description": "获取门店客户反馈和评价数据",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "days": {"type": "integer", "description": "查询天数，默认7", "default": 7},
                "sentiment": {
                    "type": "string",
                    "enum": ["positive", "negative", "neutral", "all"],
                    "description": "情感倾向筛选",
                    "default": "all",
                },
                "limit": {"type": "integer", "description": "返回数量", "default": 20},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "get_service_quality_metrics",
        "description": "获取服务质量KPI指标（等待时间、满意度、投诉率等）",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "period": {
                    "type": "string",
                    "enum": ["today", "week", "month"],
                    "description": "统计周期",
                    "default": "week",
                },
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "create_improvement_task",
        "description": "根据服务问题创建改进任务并分配给相关员工",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "issue_type": {"type": "string", "description": "问题类型"},
                "description": {"type": "string", "description": "问题描述"},
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "assignee_role": {"type": "string", "description": "分配给的岗位角色"},
            },
            "required": ["store_id", "issue_type", "description", "priority"],
        },
    },
]

# ── TrainingAgent 工具集 ──────────────────────────────────────────────────────
TRAINING_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_employee_training_status",
        "description": "获取员工培训完成情况、考核成绩和技能认证状态",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "employee_id": {"type": "string", "description": "员工ID（可选，不填则返回全店）"},
                "include_scores": {"type": "boolean", "description": "是否包含考核成绩", "default": True},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "search_knowledge_base",
        "description": "在培训知识库中搜索相关内容（SOP、操作规范、产品知识等）",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词或问题"},
                "category": {
                    "type": "string",
                    "enum": ["sop", "product", "service", "safety", "all"],
                    "description": "知识分类",
                    "default": "all",
                },
                "top_k": {"type": "integer", "description": "返回结果数量", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "assign_training_plan",
        "description": "为员工分配个性化培训计划",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string", "description": "员工ID"},
                "training_modules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "培训模块ID列表",
                },
                "deadline": {"type": "string", "description": "完成截止日期 YYYY-MM-DD"},
                "priority": {"type": "string", "enum": ["normal", "urgent"]},
            },
            "required": ["employee_id", "training_modules"],
        },
    },
]

# ── DecisionAgent 工具集 ──────────────────────────────────────────────────────
DECISION_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_store_kpi_summary",
        "description": "获取门店核心KPI汇总（营收、客流、人效、成本率等）",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "period": {
                    "type": "string",
                    "enum": ["today", "week", "month", "quarter"],
                    "description": "统计周期",
                    "default": "month",
                },
                "compare_with_last": {"type": "boolean", "description": "是否与上期对比", "default": True},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "get_cross_store_benchmark",
        "description": "获取跨门店对标数据，识别优秀门店的最佳实践",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "目标门店ID"},
                "metric": {
                    "type": "string",
                    "enum": ["revenue", "labor_cost", "food_cost", "satisfaction", "turnover"],
                    "description": "对标指标",
                },
                "top_n": {"type": "integer", "description": "返回前N名门店", "default": 5},
            },
            "required": ["store_id", "metric"],
        },
    },
    {
        "name": "run_revenue_forecast",
        "description": "运行营收预测模型，预测未来一段时间的营收趋势",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "forecast_days": {"type": "integer", "description": "预测天数，默认30", "default": 30},
                "include_scenarios": {
                    "type": "boolean",
                    "description": "是否包含乐观/悲观情景",
                    "default": True,
                },
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "get_anomaly_alerts",
        "description": "获取当前异常预警（营收异常、成本超标、客流骤降等）",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID，不填则返回全品牌"},
                "severity": {
                    "type": "string",
                    "enum": ["critical", "warning", "info", "all"],
                    "default": "all",
                },
            },
            "required": [],
        },
    },
]

# ── ReservationAgent 工具集 ───────────────────────────────────────────────────
RESERVATION_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "check_table_availability",
        "description": "查询指定时间段的餐桌可用性",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "date": {"type": "string", "description": "日期 YYYY-MM-DD"},
                "time": {"type": "string", "description": "时间 HH:MM"},
                "party_size": {"type": "integer", "description": "用餐人数"},
                "duration_minutes": {"type": "integer", "description": "预计用餐时长（分钟）", "default": 90},
            },
            "required": ["store_id", "date", "time", "party_size"],
        },
    },
    {
        "name": "create_reservation",
        "description": "创建预订记录并锁定餐桌资源",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "customer_name": {"type": "string", "description": "客户姓名"},
                "customer_phone": {"type": "string", "description": "联系电话"},
                "date": {"type": "string", "description": "预订日期 YYYY-MM-DD"},
                "time": {"type": "string", "description": "预订时间 HH:MM"},
                "party_size": {"type": "integer", "description": "用餐人数"},
                "special_requests": {"type": "string", "description": "特殊要求（可选）"},
                "table_preference": {"type": "string", "description": "桌位偏好（可选）"},
            },
            "required": ["store_id", "customer_name", "customer_phone", "date", "time", "party_size"],
        },
    },
    {
        "name": "get_reservation_list",
        "description": "获取门店预订列表",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "date": {"type": "string", "description": "日期 YYYY-MM-DD"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "confirmed", "seated", "completed", "cancelled", "all"],
                    "default": "all",
                },
            },
            "required": ["store_id", "date"],
        },
    },
    {
        "name": "update_reservation",
        "description": "更新预订信息（改期、改人数、取消等）",
        "input_schema": {
            "type": "object",
            "properties": {
                "reservation_id": {"type": "string", "description": "预订ID"},
                "action": {
                    "type": "string",
                    "enum": ["confirm", "cancel", "reschedule", "update_party_size", "seat"],
                },
                "new_date": {"type": "string", "description": "新日期（改期时必填）"},
                "new_time": {"type": "string", "description": "新时间（改期时必填）"},
                "new_party_size": {"type": "integer", "description": "新人数（改人数时必填）"},
                "reason": {"type": "string", "description": "操作原因"},
            },
            "required": ["reservation_id", "action"],
        },
    },
]

# ── OpsAgent 工具集 ───────────────────────────────────────────────────────────
OPS_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_system_health",
        "description": "获取系统健康状态（POS、网络、打印机、KDS等设备状态）",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "component": {
                    "type": "string",
                    "enum": ["pos", "network", "printer", "kds", "all"],
                    "default": "all",
                },
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "get_error_logs",
        "description": "获取系统错误日志，用于故障诊断",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "hours_back": {"type": "integer", "description": "往前查询小时数", "default": 24},
                "severity": {
                    "type": "string",
                    "enum": ["critical", "error", "warning", "all"],
                    "default": "error",
                },
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "create_maintenance_ticket",
        "description": "创建设备维护工单",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "device_type": {"type": "string", "description": "设备类型"},
                "issue_description": {"type": "string", "description": "故障描述"},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "suggested_action": {"type": "string", "description": "建议处理方案"},
            },
            "required": ["store_id", "device_type", "issue_description", "priority"],
        },
    },
    {
        "name": "query_device_readings",
        "description": "查询IoT设备读数历史（温度/功率/在线状态），用于趋势分析和告警回溯",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "device_name": {"type": "string", "description": "设备名称（可选，不传则返回全部）"},
                "metric_type": {
                    "type": "string",
                    "enum": ["temperature", "power", "online_status", "tpm", "clean_days", "all"],
                    "default": "all",
                    "description": "指标类型",
                },
                "minutes_back": {"type": "integer", "default": 60, "description": "往前查询分钟数"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "query_network_health",
        "description": "查询网络探针历史结果（ICMP/HTTP/DNS/带宽），用于网络质量分析和故障定位",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "probe_type": {
                    "type": "string",
                    "enum": ["icmp", "http", "dns", "bandwidth", "wifi", "vpn", "all"],
                    "default": "all",
                },
                "vlan": {"type": "string", "description": "VLAN区段过滤（vlan10/vlan20/wan等）"},
                "minutes_back": {"type": "integer", "default": 30},
                "alerts_only": {"type": "boolean", "default": False, "description": "仅返回告警记录"},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "query_food_safety",
        "description": "查询食安合规记录（冷链温度/油质/清洁周期/安全设备），支持违规明细查询",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "record_type": {
                    "type": "string",
                    "enum": ["cold_chain", "fridge_power", "ice_machine_clean", "oil_quality", "safety_device", "all"],
                    "default": "all",
                },
                "days_back": {"type": "integer", "default": 7},
                "violations_only": {"type": "boolean", "default": False},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "get_asset_inventory",
        "description": "获取门店IT资产台账（POS/打印机/路由器/AP/摄像头等），含在线状态和最后活跃时间",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "asset_type": {
                    "type": "string",
                    "enum": ["pos", "erp", "member", "printer", "kds", "door_access", "camera",
                             "server", "router", "switch", "ap", "vpn", "all"],
                    "default": "all",
                },
                "status": {
                    "type": "string",
                    "enum": ["online", "offline", "degraded", "all"],
                    "default": "all",
                },
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "get_alert_history",
        "description": "获取门店历史告警列表（OpsEvent），支持按严重程度/状态/时间过滤",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical", "all"],
                    "default": "all",
                },
                "status": {
                    "type": "string",
                    "enum": ["open", "in_progress", "resolved", "all"],
                    "default": "open",
                },
                "hours_back": {"type": "integer", "default": 24},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["store_id"],
        },
    },
]

# ── PerformanceAgent 工具集 ───────────────────────────────────────────────────
PERFORMANCE_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_employee_performance",
        "description": "获取员工绩效数据（KPI达成率、出勤、客户评价等）",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "employee_id": {"type": "string", "description": "员工ID（可选）"},
                "period": {
                    "type": "string",
                    "enum": ["week", "month", "quarter"],
                    "default": "month",
                },
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "calculate_commission",
        "description": "计算员工提成金额（按绩效规则引擎计算）",
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "门店ID"},
                "employee_id": {"type": "string", "description": "员工ID"},
                "period_start": {"type": "string", "description": "统计开始日期 YYYY-MM-DD"},
                "period_end": {"type": "string", "description": "统计结束日期 YYYY-MM-DD"},
            },
            "required": ["store_id", "employee_id", "period_start", "period_end"],
        },
    },
    {
        "name": "get_store_ranking",
        "description": "获取门店绩效排名（跨门店对比）",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["revenue", "satisfaction", "efficiency", "composite"],
                    "description": "排名指标",
                    "default": "composite",
                },
                "period": {"type": "string", "enum": ["week", "month", "quarter"], "default": "month"},
                "top_n": {"type": "integer", "default": 10},
            },
            "required": [],
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 工具注册表
# ─────────────────────────────────────────────────────────────────────────────

_AGENT_TOOLS_REGISTRY: Dict[str, List[Dict[str, Any]]] = {
    "schedule": SCHEDULE_TOOLS,
    "order": ORDER_TOOLS,
    "inventory": INVENTORY_TOOLS,
    "service": SERVICE_TOOLS,
    "training": TRAINING_TOOLS,
    "decision": DECISION_TOOLS,
    "reservation": RESERVATION_TOOLS,
    "ops": OPS_TOOLS,
    "performance": PERFORMANCE_TOOLS,
}


def get_tools_for_agent(agent_type: str) -> List[Dict[str, Any]]:
    """
    获取指定 Agent 的 Claude Tool Use 工具定义列表

    Args:
        agent_type: Agent 类型（schedule/order/inventory/service/training/
                    decision/reservation/ops/performance）

    Returns:
        Claude Tool Use 格式的工具定义列表
    """
    tools = _AGENT_TOOLS_REGISTRY.get(agent_type, [])
    if not tools:
        logger.warning("no_tools_found_for_agent", agent_type=agent_type)
    return tools


def get_all_tool_names(agent_type: str) -> List[str]:
    """获取 Agent 所有工具名称列表"""
    return [t["name"] for t in get_tools_for_agent(agent_type)]


# ─────────────────────────────────────────────────────────────────────────────
# 工具执行路由器
# ─────────────────────────────────────────────────────────────────────────────

class ToolExecutor:
    """
    Claude Tool Use 工具执行路由器

    将 Claude 的 tool_use 请求路由到对应的业务服务方法。
    每个 Agent 实例化时传入所需的服务依赖。

    用法：
        executor = ToolExecutor(
            agent_type="schedule",
            store_id="store_001",
            db=db_session,
            services={"schedule": schedule_service, ...}
        )
        result = await executor.execute("query_staff_availability", {"store_id": "...", "date": "..."})
    """

    def __init__(
        self,
        agent_type: str,
        store_id: Optional[str] = None,
        db: Any = None,
        services: Optional[Dict[str, Any]] = None,
    ):
        self.agent_type = agent_type
        self.store_id = store_id
        self.db = db
        self.services = services or {}

    async def execute(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """
        执行工具调用，路由到对应的业务服务

        Args:
            tool_name:  工具名称（来自 Claude 的 tool_use block）
            tool_input: 工具参数（来自 Claude 的 tool_use block）

        Returns:
            工具执行结果（将被序列化为字符串回传给 Claude）
        """
        logger.info(
            "tool_executor_dispatch",
            agent_type=self.agent_type,
            tool=tool_name,
            store_id=self.store_id,
        )

        # 注入默认 store_id（如果工具参数中未提供）
        if self.store_id and "store_id" not in tool_input:
            tool_input = {**tool_input, "store_id": self.store_id}

        handler = self._get_handler(tool_name)
        if handler is None:
            return {"error": f"未找到工具处理器: {tool_name}", "available_tools": get_all_tool_names(self.agent_type)}

        try:
            result = await handler(tool_input)
            logger.info("tool_executor_success", tool=tool_name)
            return result
        except Exception as e:
            logger.error("tool_executor_error", tool=tool_name, error=str(e), exc_info=e)
            return {"error": str(e), "tool": tool_name}

    def _get_handler(self, tool_name: str) -> Optional[Callable]:
        """根据工具名称返回对应的处理函数"""
        handlers: Dict[str, Callable] = {
            # ── ScheduleAgent ──────────────────────────────────────────────
            "query_staff_availability": self._query_staff_availability,
            "get_customer_flow_forecast": self._get_customer_flow_forecast,
            "get_historical_schedule": self._get_historical_schedule,
            "create_schedule_recommendation": self._create_schedule_recommendation,
            # ── OrderAgent ─────────────────────────────────────────────────
            "get_order_details": self._get_order_details,
            "query_orders_by_condition": self._query_orders_by_condition,
            "get_menu_recommendations": self._get_menu_recommendations,
            "update_order_status": self._update_order_status,
            "calculate_bill": self._calculate_bill,
            # ── InventoryAgent ─────────────────────────────────────────────
            "get_inventory_status": self._get_inventory_status,
            "get_consumption_trend": self._get_consumption_trend,
            "create_purchase_order": self._create_purchase_order,
            "check_expiry_alerts": self._check_expiry_alerts,
            # ── ServiceAgent ───────────────────────────────────────────────
            "get_customer_feedback": self._get_customer_feedback,
            "get_service_quality_metrics": self._get_service_quality_metrics,
            "create_improvement_task": self._create_improvement_task,
            # ── TrainingAgent ──────────────────────────────────────────────
            "get_employee_training_status": self._get_employee_training_status,
            "search_knowledge_base": self._search_knowledge_base,
            "assign_training_plan": self._assign_training_plan,
            # ── DecisionAgent ──────────────────────────────────────────────
            "get_store_kpi_summary": self._get_store_kpi_summary,
            "get_cross_store_benchmark": self._get_cross_store_benchmark,
            "run_revenue_forecast": self._run_revenue_forecast,
            "get_anomaly_alerts": self._get_anomaly_alerts,
            # ── ReservationAgent ───────────────────────────────────────────
            "check_table_availability": self._check_table_availability,
            "create_reservation": self._create_reservation,
            "get_reservation_list": self._get_reservation_list,
            "update_reservation": self._update_reservation,
            # ── OpsAgent ───────────────────────────────────────────────────
            "get_system_health": self._get_system_health,
            "get_error_logs": self._get_error_logs,
            "create_maintenance_ticket": self._create_maintenance_ticket,
            "query_device_readings": self._query_device_readings,
            "query_network_health": self._query_network_health,
            "query_food_safety": self._query_food_safety,
            "get_asset_inventory": self._get_asset_inventory,
            "get_alert_history": self._get_alert_history,
            # ── PerformanceAgent ───────────────────────────────────────────
            "get_employee_performance": self._get_employee_performance,
            "calculate_commission": self._calculate_commission,
            "get_store_ranking": self._get_store_ranking,
        }
        return handlers.get(tool_name)

    # ── 工具实现：优先调用注入的 service，无 service 时返回结构化占位数据 ──────

    async def _call_service(self, service_name: str, method: str, **kwargs) -> Any:
        """通用服务调用辅助方法"""
        svc = self.services.get(service_name)
        if svc and hasattr(svc, method):
            return await getattr(svc, method)(**kwargs)
        # 无服务注入时返回占位数据（便于测试和降级）
        return {"status": "service_unavailable", "service": service_name, "method": method, "params": kwargs}

    # ScheduleAgent handlers
    async def _query_staff_availability(self, p: Dict) -> Any:
        return await self._call_service("schedule", "get_staff_availability",
                                        store_id=p["store_id"], date=p["date"],
                                        shift_type=p.get("shift_type", "all"))

    async def _get_customer_flow_forecast(self, p: Dict) -> Any:
        return await self._call_service("analytics", "get_flow_forecast",
                                        store_id=p["store_id"], date=p["date"])

    async def _get_historical_schedule(self, p: Dict) -> Any:
        return await self._call_service("schedule", "get_history",
                                        store_id=p["store_id"], days_back=p.get("days_back", 30))

    async def _create_schedule_recommendation(self, p: Dict) -> Any:
        return await self._call_service("schedule", "save_recommendation",
                                        store_id=p["store_id"], date=p["date"],
                                        recommended_staff=p["recommended_staff"],
                                        shift_breakdown=p.get("shift_breakdown"),
                                        reasoning=p.get("reasoning", ""))

    # OrderAgent handlers
    async def _get_order_details(self, p: Dict) -> Any:
        return await self._call_service("order", "get_by_id", order_id=p["order_id"])

    async def _query_orders_by_condition(self, p: Dict) -> Any:
        return await self._call_service("order", "query",
                                        store_id=p["store_id"], status=p.get("status"),
                                        date=p.get("date"), table_number=p.get("table_number"),
                                        limit=p.get("limit", 20))

    async def _get_menu_recommendations(self, p: Dict) -> Any:
        return await self._call_service("recommendation", "get_menu_recs",
                                        store_id=p["store_id"], customer_id=p.get("customer_id"),
                                        party_size=p.get("party_size"), budget=p.get("budget_per_person"))

    async def _update_order_status(self, p: Dict) -> Any:
        return await self._call_service("order", "update_status",
                                        order_id=p["order_id"], new_status=p["new_status"],
                                        reason=p.get("reason", ""))

    async def _calculate_bill(self, p: Dict) -> Any:
        return await self._call_service("order", "calculate_bill",
                                        order_id=p["order_id"], coupon_code=p.get("coupon_code"),
                                        member_id=p.get("member_id"))

    # InventoryAgent handlers
    async def _get_inventory_status(self, p: Dict) -> Any:
        return await self._call_service("inventory", "get_status",
                                        store_id=p["store_id"], category=p.get("category"),
                                        alert_only=p.get("alert_only", False))

    async def _get_consumption_trend(self, p: Dict) -> Any:
        return await self._call_service("inventory", "get_consumption_trend",
                                        store_id=p["store_id"], ingredient_id=p.get("ingredient_id"),
                                        days=p.get("days", 30))

    async def _create_purchase_order(self, p: Dict) -> Any:
        return await self._call_service("inventory", "create_purchase_order",
                                        store_id=p["store_id"], items=p["items"],
                                        urgency=p.get("urgency", "normal"))

    async def _check_expiry_alerts(self, p: Dict) -> Any:
        return await self._call_service("inventory", "check_expiry",
                                        store_id=p["store_id"], days_ahead=p.get("days_ahead", 3))

    # ServiceAgent handlers
    async def _get_customer_feedback(self, p: Dict) -> Any:
        return await self._call_service("service", "get_feedback",
                                        store_id=p["store_id"], days=p.get("days", 7),
                                        sentiment=p.get("sentiment", "all"), limit=p.get("limit", 20))

    async def _get_service_quality_metrics(self, p: Dict) -> Any:
        return await self._call_service("service", "get_quality_metrics",
                                        store_id=p["store_id"], period=p.get("period", "week"))

    async def _create_improvement_task(self, p: Dict) -> Any:
        return await self._call_service("service", "create_task",
                                        store_id=p["store_id"], issue_type=p["issue_type"],
                                        description=p["description"], priority=p["priority"],
                                        assignee_role=p.get("assignee_role"))

    # TrainingAgent handlers
    async def _get_employee_training_status(self, p: Dict) -> Any:
        return await self._call_service("training", "get_status",
                                        store_id=p["store_id"], employee_id=p.get("employee_id"),
                                        include_scores=p.get("include_scores", True))

    async def _search_knowledge_base(self, p: Dict) -> Any:
        return await self._call_service("rag", "search",
                                        query=p["query"], category=p.get("category", "all"),
                                        top_k=p.get("top_k", 5))

    async def _assign_training_plan(self, p: Dict) -> Any:
        return await self._call_service("training", "assign_plan",
                                        employee_id=p["employee_id"],
                                        modules=p["training_modules"],
                                        deadline=p.get("deadline"),
                                        priority=p.get("priority", "normal"))

    # DecisionAgent handlers
    async def _get_store_kpi_summary(self, p: Dict) -> Any:
        return await self._call_service("decision", "get_kpi_summary",
                                        store_id=p["store_id"], period=p.get("period", "month"),
                                        compare_with_last=p.get("compare_with_last", True))

    async def _get_cross_store_benchmark(self, p: Dict) -> Any:
        return await self._call_service("benchmark", "get_cross_store",
                                        store_id=p["store_id"], metric=p["metric"],
                                        top_n=p.get("top_n", 5))

    async def _run_revenue_forecast(self, p: Dict) -> Any:
        return await self._call_service("analytics", "run_forecast",
                                        store_id=p["store_id"],
                                        forecast_days=p.get("forecast_days", 30),
                                        include_scenarios=p.get("include_scenarios", True))

    async def _get_anomaly_alerts(self, p: Dict) -> Any:
        return await self._call_service("analytics", "get_anomalies",
                                        store_id=p.get("store_id"),
                                        severity=p.get("severity", "all"))

    # ReservationAgent handlers
    async def _check_table_availability(self, p: Dict) -> Any:
        return await self._call_service("reservation", "check_availability",
                                        store_id=p["store_id"], date=p["date"],
                                        time=p["time"], party_size=p["party_size"],
                                        duration_minutes=p.get("duration_minutes", 90))

    async def _create_reservation(self, p: Dict) -> Any:
        return await self._call_service("reservation", "create",
                                        store_id=p["store_id"], customer_name=p["customer_name"],
                                        customer_phone=p["customer_phone"], date=p["date"],
                                        time=p["time"], party_size=p["party_size"],
                                        special_requests=p.get("special_requests"),
                                        table_preference=p.get("table_preference"))

    async def _get_reservation_list(self, p: Dict) -> Any:
        return await self._call_service("reservation", "list_by_date",
                                        store_id=p["store_id"], date=p["date"],
                                        status=p.get("status", "all"))

    async def _update_reservation(self, p: Dict) -> Any:
        return await self._call_service("reservation", "update",
                                        reservation_id=p["reservation_id"],
                                        action=p["action"],
                                        new_date=p.get("new_date"),
                                        new_time=p.get("new_time"),
                                        new_party_size=p.get("new_party_size"),
                                        reason=p.get("reason", ""))

    # OpsAgent handlers
    async def _get_system_health(self, p: Dict) -> Any:
        return await self._call_service("ops", "get_health",
                                        store_id=p["store_id"], component=p.get("component", "all"))

    async def _get_error_logs(self, p: Dict) -> Any:
        return await self._call_service("ops", "get_logs",
                                        store_id=p["store_id"],
                                        hours_back=p.get("hours_back", 24),
                                        severity=p.get("severity", "error"),
                                        limit=p.get("limit", 50))

    async def _create_maintenance_ticket(self, p: Dict) -> Any:
        return await self._call_service("ops", "create_ticket",
                                        store_id=p["store_id"], device_type=p["device_type"],
                                        issue_description=p["issue_description"],
                                        priority=p["priority"],
                                        suggested_action=p.get("suggested_action", ""))

    async def _query_device_readings(self, p: Dict) -> Any:
        """查询IoT设备读数历史，直接查 ops_device_readings 表。"""
        session = self.services.get("db_session")
        if not session:
            return {"status": "service_unavailable", "service": "ops", "method": "query_device_readings"}
        from sqlalchemy import select, and_
        from datetime import datetime, timedelta, timezone
        from ..models.ops import OpsDeviceReading
        since = datetime.now(timezone.utc) - timedelta(minutes=p.get("minutes_back", 60))
        stmt = (
            select(OpsDeviceReading)
            .where(OpsDeviceReading.store_id == p["store_id"],
                   OpsDeviceReading.recorded_at >= since)
        )
        if p.get("device_name"):
            stmt = stmt.where(OpsDeviceReading.device_name == p["device_name"])
        if p.get("metric_type") and p["metric_type"] != "all":
            stmt = stmt.where(OpsDeviceReading.metric_type == p["metric_type"])
        stmt = stmt.order_by(OpsDeviceReading.recorded_at.desc()).limit(p.get("limit", 50))
        rows = (await session.execute(stmt)).scalars().all()
        return {
            "total": len(rows),
            "readings": [
                {"device_name": r.device_name, "metric_type": r.metric_type,
                 "value_float": r.value_float, "value_bool": r.value_bool,
                 "unit": r.unit, "is_alert": r.is_alert,
                 "alert_message": r.alert_message,
                 "recorded_at": r.recorded_at.isoformat()}
                for r in rows
            ],
        }

    async def _query_network_health(self, p: Dict) -> Any:
        """查询网络探针历史结果，直接查 ops_network_health 表。"""
        session = self.services.get("db_session")
        if not session:
            return {"status": "service_unavailable", "service": "ops", "method": "query_network_health"}
        from sqlalchemy import select
        from datetime import datetime, timedelta, timezone
        from ..models.ops import OpsNetworkHealth
        since = datetime.now(timezone.utc) - timedelta(minutes=p.get("minutes_back", 30))
        stmt = (
            select(OpsNetworkHealth)
            .where(OpsNetworkHealth.store_id == p["store_id"],
                   OpsNetworkHealth.recorded_at >= since)
        )
        if p.get("probe_type") and p["probe_type"] != "all":
            stmt = stmt.where(OpsNetworkHealth.probe_type == p["probe_type"])
        if p.get("vlan"):
            stmt = stmt.where(OpsNetworkHealth.vlan == p["vlan"])
        if p.get("alerts_only"):
            stmt = stmt.where(OpsNetworkHealth.is_alert.is_(True))
        stmt = stmt.order_by(OpsNetworkHealth.recorded_at.desc()).limit(50)
        rows = (await session.execute(stmt)).scalars().all()
        return {
            "total": len(rows),
            "probes": [
                {"probe_type": r.probe_type, "target": r.target, "vlan": r.vlan,
                 "is_available": r.is_available, "latency_ms": r.latency_ms,
                 "packet_loss_pct": r.packet_loss_pct, "bandwidth_mbps": r.bandwidth_mbps,
                 "is_alert": r.is_alert, "alert_message": r.alert_message,
                 "recorded_at": r.recorded_at.isoformat()}
                for r in rows
            ],
        }

    async def _query_food_safety(self, p: Dict) -> Any:
        """查询食安合规记录，直接查 ops_food_safety_records 表。"""
        session = self.services.get("db_session")
        if not session:
            return {"status": "service_unavailable", "service": "ops", "method": "query_food_safety"}
        from sqlalchemy import select
        from datetime import datetime, timedelta, timezone
        from ..models.ops import OpsFoodSafetyRecord
        since = datetime.now(timezone.utc) - timedelta(days=p.get("days_back", 7))
        stmt = (
            select(OpsFoodSafetyRecord)
            .where(OpsFoodSafetyRecord.store_id == p["store_id"],
                   OpsFoodSafetyRecord.recorded_at >= since)
        )
        if p.get("record_type") and p["record_type"] != "all":
            stmt = stmt.where(OpsFoodSafetyRecord.record_type == p["record_type"])
        if p.get("violations_only"):
            stmt = stmt.where(OpsFoodSafetyRecord.is_compliant.is_(False))
        stmt = stmt.order_by(OpsFoodSafetyRecord.recorded_at.desc()).limit(50)
        rows = (await session.execute(stmt)).scalars().all()
        return {
            "total": len(rows),
            "violations": sum(1 for r in rows if not r.is_compliant),
            "records": [
                {"record_type": r.record_type, "device_name": r.device_name,
                 "is_compliant": r.is_compliant, "value_float": r.value_float,
                 "unit": r.unit, "notes": r.notes,
                 "requires_action": r.requires_action,
                 "recorded_at": r.recorded_at.isoformat()}
                for r in rows
            ],
        }

    async def _get_asset_inventory(self, p: Dict) -> Any:
        """获取门店IT资产台账，直接查 ops_assets 表。"""
        session = self.services.get("db_session")
        if not session:
            return {"status": "service_unavailable", "service": "ops", "method": "get_asset_inventory"}
        from sqlalchemy import select
        from ..models.ops import OpsAsset
        stmt = select(OpsAsset).where(OpsAsset.store_id == p["store_id"])
        if p.get("asset_type") and p["asset_type"] != "all":
            stmt = stmt.where(OpsAsset.asset_type == p["asset_type"])
        if p.get("status") and p["status"] != "all":
            stmt = stmt.where(OpsAsset.status == p["status"])
        stmt = stmt.order_by(OpsAsset.asset_type, OpsAsset.name)
        rows = (await session.execute(stmt)).scalars().all()
        return {
            "total": len(rows),
            "online": sum(1 for r in rows if r.status == "online"),
            "offline": sum(1 for r in rows if r.status == "offline"),
            "assets": [
                {"id": str(r.id), "asset_type": r.asset_type, "name": r.name,
                 "ip_address": r.ip_address, "status": r.status,
                 "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                 "firmware_version": r.firmware_version}
                for r in rows
            ],
        }

    async def _get_alert_history(self, p: Dict) -> Any:
        """获取门店历史告警，直接查 ops_events 表。"""
        session = self.services.get("db_session")
        if not session:
            return {"status": "service_unavailable", "service": "ops", "method": "get_alert_history"}
        from sqlalchemy import select
        from datetime import datetime, timedelta, timezone
        from ..models.ops import OpsEvent
        since = datetime.now(timezone.utc) - timedelta(hours=p.get("hours_back", 24))
        stmt = (
            select(OpsEvent)
            .where(OpsEvent.store_id == p["store_id"],
                   OpsEvent.created_at >= since)
        )
        if p.get("severity") and p["severity"] != "all":
            stmt = stmt.where(OpsEvent.severity == p["severity"])
        if p.get("status") and p["status"] != "all":
            stmt = stmt.where(OpsEvent.status == p["status"])
        stmt = stmt.order_by(OpsEvent.created_at.desc()).limit(p.get("limit", 20))
        rows = (await session.execute(stmt)).scalars().all()
        return {
            "total": len(rows),
            "alerts": [
                {"id": str(r.id), "event_type": r.event_type, "severity": r.severity,
                 "component": r.component, "description": r.description,
                 "status": r.status, "created_at": r.created_at.isoformat(),
                 "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None}
                for r in rows
            ],
        }

    # PerformanceAgent handlers
    async def _get_employee_performance(self, p: Dict) -> Any:
        return await self._call_service("performance", "get_employee_kpi",
                                        store_id=p["store_id"],
                                        employee_id=p.get("employee_id"),
                                        period=p.get("period", "month"))

    async def _calculate_commission(self, p: Dict) -> Any:
        return await self._call_service("performance", "calc_commission",
                                        store_id=p["store_id"], employee_id=p["employee_id"],
                                        period_start=p["period_start"], period_end=p["period_end"])

    async def _get_store_ranking(self, p: Dict) -> Any:
        return await self._call_service("performance", "get_ranking",
                                        metric=p.get("metric", "composite"),
                                        period=p.get("period", "month"),
                                        top_n=p.get("top_n", 10))
