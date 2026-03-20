"""
门店全天业务流程节点管理服务

核心能力：
  1. 每日流程自动实例化（从模板生成当天 11 节点 + N 任务）
  2. 节点生命周期管理（进入 → 执行 → 完成/超时/跳过）
  3. 任务提交 + 审核
  4. 异常上报 + 升级
  5. 全天进度聚合（供店长看板/总部巡检）
  6. 与现有日清日结系统对接
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from uuid import uuid4

import structlog

logger = structlog.get_logger()


# ══════════════════════════════════════════════════════════════
#  纯函数（无 DB 依赖，可独立测试）
# ══════════════════════════════════════════════════════════════

def build_node_instances(
    store_id: str,
    brand_id: str,
    biz_date: date,
    flow_instance_id: str,
    node_templates: List[Dict],
    business_mode: str = "lunch_dinner",
) -> List[Dict]:
    """
    从节点模板列表生成当天的节点实例。

    Args:
        store_id: 门店ID
        brand_id: 品牌ID
        biz_date: 营业日
        flow_instance_id: 流程实例ID
        node_templates: 节点模板列表
        business_mode: 营业模式（lunch_dinner/全天/夜宵）

    Returns:
        节点实例字典列表
    """
    instances = []
    for tpl in node_templates:
        # 夜宵节点仅在支持夜宵的模式下生成
        is_optional = tpl.get("optional", tpl.get("is_optional", False))
        if is_optional and business_mode == "lunch_dinner":
            continue

        start_h, start_m = map(int, tpl["start"].split(":"))
        end_h, end_m = map(int, tpl["end"].split(":"))

        # 处理跨日（如 22:00-02:00）和 24:00 边界
        scheduled_start = datetime(biz_date.year, biz_date.month, biz_date.day, start_h, start_m)
        if end_h >= 24:
            next_day = biz_date + timedelta(days=1)
            scheduled_end = datetime(next_day.year, next_day.month, next_day.day, end_h - 24, end_m)
        elif end_h < start_h:
            next_day = biz_date + timedelta(days=1)
            scheduled_end = datetime(next_day.year, next_day.month, next_day.day, end_h, end_m)
        else:
            scheduled_end = datetime(biz_date.year, biz_date.month, biz_date.day, end_h, end_m)

        instances.append({
            "id": str(uuid4()),
            "flow_instance_id": flow_instance_id,
            "store_id": store_id,
            "biz_date": biz_date,
            "node_code": tpl["code"],
            "node_name": tpl["name"],
            "node_order": tpl["order"],
            "scheduled_start": scheduled_start,
            "scheduled_end": scheduled_end,
            "status": "pending",
            "owner_role": tpl.get("role", "store_manager"),
            "is_optional": is_optional,
            "pass_condition": tpl.get("pass_condition"),
            "total_tasks": 0,
            "completed_tasks": 0,
        })

    return instances


def calc_flow_progress(nodes: List[Dict]) -> Dict:
    """
    计算全天流程进度。

    Returns:
        {
            "total_nodes": int,
            "completed_nodes": int,
            "progress_pct": float,
            "current_node": Optional[Dict],
            "overdue_nodes": List[str],
            "status": str,  # pending/running/completed/has_overdue
        }
    """
    total = len(nodes)
    completed = sum(1 for n in nodes if n.get("status") == "completed")
    overdue = [n["node_name"] for n in nodes if n.get("status") == "overdue"]

    # 找当前节点：第一个 in_progress 或第一个 pending
    current = None
    for n in sorted(nodes, key=lambda x: x.get("node_order", 0)):
        if n.get("status") == "in_progress":
            current = n
            break
    if not current:
        for n in sorted(nodes, key=lambda x: x.get("node_order", 0)):
            if n.get("status") == "pending":
                current = n
                break

    if total == 0:
        status = "pending"
    elif completed == total:
        status = "completed"
    elif overdue:
        status = "has_overdue"
    elif any(n.get("status") == "in_progress" for n in nodes):
        status = "running"
    else:
        status = "pending"

    return {
        "total_nodes": total,
        "completed_nodes": completed,
        "progress_pct": round(completed / total * 100, 1) if total > 0 else 0,
        "current_node": current,
        "overdue_nodes": overdue,
        "status": status,
    }


def check_node_completion(node: Dict, tasks: List[Dict]) -> Dict:
    """
    检查节点是否满足完成条件。

    默认规则：所有必需任务已完成。
    自定义规则通过 node["pass_condition"] 扩展。

    Returns:
        {"can_complete": bool, "blocking_reasons": List[str]}
    """
    reasons = []
    required_tasks = [t for t in tasks if t.get("is_required", True)]
    done_required = [t for t in required_tasks if t.get("status") == "done"]

    if len(done_required) < len(required_tasks):
        pending = [t["task_name"] for t in required_tasks if t.get("status") != "done"]
        reasons.append(f"还有 {len(pending)} 个必需任务未完成：{'、'.join(pending[:3])}")

    # 检查是否有未关闭的高危异常
    pass_cond = node.get("pass_condition") or {}
    if pass_cond.get("no_open_critical_incidents"):
        reasons.append("存在未关闭的紧急异常")

    return {
        "can_complete": len(reasons) == 0,
        "blocking_reasons": reasons,
    }


def should_auto_enter_node(node: Dict, now: datetime) -> bool:
    """判断节点是否应自动进入（到达计划开始时间且状态为 pending）"""
    if node.get("status") != "pending":
        return False
    scheduled = node.get("scheduled_start")
    if not scheduled:
        return False
    if isinstance(scheduled, str):
        scheduled = datetime.fromisoformat(scheduled)
    return now >= scheduled


def should_mark_overdue(node: Dict, now: datetime) -> bool:
    """判断节点是否已超时"""
    if node.get("status") not in ("pending", "in_progress"):
        return False
    scheduled_end = node.get("scheduled_end")
    if not scheduled_end:
        return False
    if isinstance(scheduled_end, str):
        scheduled_end = datetime.fromisoformat(scheduled_end)
    return now > scheduled_end


def escalation_needed(incident: Dict, now: datetime) -> Optional[str]:
    """
    判断异常是否需要升级。

    规则（PRD V1）：
    - 30分钟未响应 → 升级到店长
    - 2小时未解决 → 升级到区域经理
    - 食品安全类 → 直接升级到总部
    """
    status = incident.get("status", "new")
    if status in ("closed", "escalated"):
        return None

    severity = incident.get("severity", "medium")
    if severity == "critical" and incident.get("incident_type") == "food_safety":
        return "hq"

    created_str = incident.get("created_at")
    if not created_str:
        return None
    if isinstance(created_str, str):
        created = datetime.fromisoformat(created_str)
    else:
        created = created_str

    elapsed_minutes = (now - created).total_seconds() / 60

    # 120分钟优先判断（比30分钟更严重）
    if status in ("new", "accepted", "in_process") and elapsed_minutes > 120:
        return "regional_manager"
    if status == "new" and elapsed_minutes > 30:
        return "store_manager"

    return None


def build_store_daily_summary(
    store_id: str,
    biz_date: date,
    flow_progress: Dict,
    incident_counts: Dict,
    settlement_status: str,
) -> Dict:
    """
    构建门店当日汇总（供总部巡检看板）。

    Returns:
        {
            "store_id", "biz_date", "flow_status", "progress_pct",
            "current_node", "overdue_count", "incident_summary",
            "settlement_status", "risk_level",
        }
    """
    overdue_count = len(flow_progress.get("overdue_nodes", []))
    critical_incidents = incident_counts.get("critical", 0)
    high_incidents = incident_counts.get("high", 0)

    # 风险等级
    if critical_incidents > 0 or overdue_count >= 3:
        risk = "high"
    elif high_incidents > 0 or overdue_count >= 1:
        risk = "medium"
    else:
        risk = "low"

    current_node = flow_progress.get("current_node")

    return {
        "store_id": store_id,
        "biz_date": str(biz_date),
        "flow_status": flow_progress.get("status", "pending"),
        "progress_pct": flow_progress.get("progress_pct", 0),
        "current_node_name": current_node.get("node_name") if current_node else None,
        "completed_nodes": flow_progress.get("completed_nodes", 0),
        "total_nodes": flow_progress.get("total_nodes", 0),
        "overdue_count": overdue_count,
        "overdue_nodes": flow_progress.get("overdue_nodes", []),
        "incident_summary": incident_counts,
        "settlement_status": settlement_status,
        "risk_level": risk,
    }


# ══════════════════════════════════════════════════════════════
#  标准任务模板（PRD V1 各节点的默认任务）
# ══════════════════════════════════════════════════════════════

STANDARD_TASKS = {
    "opening_prep": [
        {"code": "staff_checkin", "name": "员工到岗签到", "order": 1, "required": True, "role": "store_staff", "proof": "checklist"},
        {"code": "health_check", "name": "健康检查", "order": 2, "required": True, "role": "store_staff", "proof": "checklist"},
        {"code": "equipment_check", "name": "设备开机检查", "order": 3, "required": True, "role": "store_staff", "proof": "checklist"},
        {"code": "material_receive", "name": "食材验收", "order": 4, "required": True, "role": "store_staff", "proof": "photo"},
        {"code": "morning_meeting", "name": "晨会", "order": 5, "required": True, "role": "store_manager", "proof": "text"},
    ],
    "ready_check": [
        {"code": "pos_kds_test", "name": "POS/KDS系统测试", "order": 1, "required": True, "role": "store_staff", "proof": "checklist"},
        {"code": "table_setup", "name": "前厅摆台", "order": 2, "required": True, "role": "store_staff", "proof": "photo"},
        {"code": "menu_sync", "name": "菜单同步确认", "order": 3, "required": True, "role": "store_manager", "proof": "checklist"},
        {"code": "stock_check", "name": "主打菜品库存确认", "order": 4, "required": True, "role": "store_staff", "proof": "number"},
    ],
    "lunch_warmup": [
        {"code": "peak_staffing", "name": "高峰人员到位确认", "order": 1, "required": True, "role": "store_manager", "proof": "checklist"},
        {"code": "vip_confirm", "name": "VIP预订确认", "order": 2, "required": False, "role": "store_staff", "proof": "text"},
        {"code": "line_check", "name": "出品线检查", "order": 3, "required": True, "role": "store_staff", "proof": "checklist"},
    ],
    "lunch_peak": [
        {"code": "queue_mgmt", "name": "排队管理", "order": 1, "required": False, "role": "store_staff", "proof": "none"},
        {"code": "output_monitor", "name": "出品时效监控", "order": 2, "required": True, "role": "store_manager", "proof": "none"},
        {"code": "shortage_handle", "name": "沽清处理", "order": 3, "required": False, "role": "store_staff", "proof": "text"},
    ],
    "lunch_wrapup": [
        {"code": "lunch_summary", "name": "午市数据小结", "order": 1, "required": True, "role": "store_manager", "proof": "none"},
        {"code": "refund_review", "name": "退菜退款审核", "order": 2, "required": True, "role": "store_manager", "proof": "text"},
        {"code": "restock_suggest", "name": "补货建议", "order": 3, "required": True, "role": "store_staff", "proof": "text"},
        {"code": "cleaning_2nd", "name": "二次清洁", "order": 4, "required": True, "role": "store_staff", "proof": "photo"},
    ],
    "dinner_prep": [
        {"code": "dinner_targets", "name": "晚市目标确认", "order": 1, "required": True, "role": "store_manager", "proof": "text"},
        {"code": "reservation_review", "name": "预订复核", "order": 2, "required": True, "role": "store_staff", "proof": "checklist"},
        {"code": "evening_prep", "name": "二次备料", "order": 3, "required": True, "role": "store_staff", "proof": "checklist"},
        {"code": "evening_staffing", "name": "晚班人员确认", "order": 4, "required": True, "role": "store_manager", "proof": "checklist"},
    ],
    "dinner_peak": [
        {"code": "concurrent_orders", "name": "并发订单管理", "order": 1, "required": False, "role": "store_manager", "proof": "none"},
        {"code": "output_timing", "name": "出品时效", "order": 2, "required": True, "role": "store_manager", "proof": "none"},
        {"code": "service_handling", "name": "服务异常处理", "order": 3, "required": False, "role": "store_staff", "proof": "text"},
    ],
    "closing": [
        {"code": "stop_orders", "name": "停止接单", "order": 1, "required": True, "role": "store_manager", "proof": "checklist"},
        {"code": "clear_tables", "name": "清台收桌", "order": 2, "required": True, "role": "store_staff", "proof": "checklist"},
        {"code": "inventory_count", "name": "库存盘点", "order": 3, "required": True, "role": "store_staff", "proof": "number"},
        {"code": "equipment_shutdown", "name": "设备关闭", "order": 4, "required": True, "role": "store_staff", "proof": "checklist"},
        {"code": "cleaning_final", "name": "最终清洁", "order": 5, "required": True, "role": "store_staff", "proof": "photo"},
        {"code": "handover", "name": "交接班确认", "order": 6, "required": True, "role": "store_manager", "proof": "signature"},
    ],
    "settlement": [
        {"code": "cash_reconcile", "name": "现金核对", "order": 1, "required": True, "role": "store_manager", "proof": "number"},
        {"code": "platform_match", "name": "平台对账", "order": 2, "required": True, "role": "store_manager", "proof": "checklist"},
        {"code": "damage_verify", "name": "报损确认", "order": 3, "required": True, "role": "store_manager", "proof": "text"},
        {"code": "incident_confirm", "name": "异常事件确认", "order": 4, "required": True, "role": "store_manager", "proof": "text"},
        {"code": "next_day_todo", "name": "明日待办", "order": 5, "required": True, "role": "store_manager", "proof": "text"},
    ],
}
