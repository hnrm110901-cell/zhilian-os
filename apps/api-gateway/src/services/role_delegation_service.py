"""
岗位代班委派服务（Role Delegation Service）

解决的问题：
  店长休息时，副店长/值班经理/跨店店长代班，
  需要无缝继承工作流节点、任务、审批权限，不影响门店运营。

核心机制：
  1. 每日角色委派表（DailyRoleAssignment）：今天谁扮演什么角色
  2. 角色解析器（resolve_role_holder）：任何需要"找店长"的场景，
     先查委派表，没有委派才用默认人员
  3. 权限继承：代班人获得该角色的全部操作权限
  4. 审计留痕：所有操作记录实际操作人 + 代班的角色
  5. 跨店支持：A店店长可以委派给B店的人

委派来源：
  - 排班系统自动生成（基于调休/请假审批）
  - 店长手动指定（今日代班人）
  - 总部紧急指派（跨店调配）
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import uuid4

import structlog

logger = structlog.get_logger()


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class RoleAssignment:
    """单条岗位委派"""
    id: str
    store_id: str
    biz_date: date
    role_code: str              # store_manager / chef_leader / floor_manager / ...
    role_name: str
    default_holder_id: str      # 默认岗位持有人ID
    default_holder_name: str
    actual_holder_id: str       # 实际今日执行人ID（可能是代班人）
    actual_holder_name: str
    is_delegated: bool          # 是否为代班
    delegation_type: Optional[str]  # leave(请假) / dayoff(调休) / cross_store(跨店) / emergency(紧急)
    delegation_reason: Optional[str]
    delegated_by: Optional[str]  # 委派人（通常是店长或总部）
    source_store_id: Optional[str]  # 代班人原所属门店（跨店时有值）
    status: str                  # active / cancelled / expired
    created_at: str
    permissions: List[str]       # 继承的权限列表


@dataclass
class RoleResolveResult:
    """角色解析结果"""
    role_code: str
    role_name: str
    holder_id: str
    holder_name: str
    is_delegated: bool
    delegation_type: Optional[str]
    source_store_id: Optional[str]  # 跨店时原门店


# ── 标准岗位定义 ──────────────────────────────────────────────────────────────

STANDARD_ROLES = {
    "store_manager": {
        "name": "店长",
        "permissions": [
            "node_complete", "node_skip", "task_review",
            "incident_handle", "settlement_submit", "shift_approve",
            "menu_adjust", "procurement_approve", "staff_dispatch",
        ],
        "delegate_to": ["assistant_manager", "duty_manager", "store_manager_other"],
    },
    "assistant_manager": {
        "name": "副店长",
        "permissions": [
            "node_complete", "task_review", "incident_handle",
            "settlement_submit", "staff_dispatch",
        ],
        "delegate_to": ["duty_manager", "senior_staff"],
    },
    "chef_leader": {
        "name": "厨师长",
        "permissions": [
            "kitchen_node_complete", "quality_check", "inventory_count",
            "waste_report", "recipe_adjust", "prep_approve",
        ],
        "delegate_to": ["sous_chef", "senior_cook"],
    },
    "floor_manager": {
        "name": "楼面经理",
        "permissions": [
            "queue_manage", "table_assign", "service_handle",
            "checkout_approve", "complaint_handle",
        ],
        "delegate_to": ["senior_waiter", "duty_manager"],
    },
    "duty_manager": {
        "name": "值班经理",
        "permissions": [
            "node_complete", "task_review", "incident_handle",
            "staff_dispatch",
        ],
        "delegate_to": ["senior_staff"],
    },
}


# ── 纯函数 ────────────────────────────────────────────────────────────────────

def resolve_role_holder(
    role_code: str,
    store_id: str,
    biz_date: date,
    assignments: List[RoleAssignment],
    default_holders: Dict[str, Dict],
) -> RoleResolveResult:
    """
    解析某个角色今天由谁执行。

    优先级：
    1. 查委派表中该门店该日期该角色的 active 记录
    2. 没有委派 → 使用默认持有人
    3. 默认持有人也没有 → 返回空（需要紧急指派）

    Args:
        role_code: 角色代码
        store_id: 门店ID
        biz_date: 营业日
        assignments: 当天所有委派记录
        default_holders: 默认岗位持有人 {role_code: {id, name}}
    """
    role_def = STANDARD_ROLES.get(role_code, {})
    role_name = role_def.get("name", role_code)

    # 查委派表
    for a in assignments:
        if (a.store_id == store_id and a.biz_date == biz_date
                and a.role_code == role_code and a.status == "active"):
            return RoleResolveResult(
                role_code=role_code,
                role_name=role_name,
                holder_id=a.actual_holder_id,
                holder_name=a.actual_holder_name,
                is_delegated=a.is_delegated,
                delegation_type=a.delegation_type,
                source_store_id=a.source_store_id,
            )

    # 使用默认
    default = default_holders.get(role_code, {})
    if default.get("id"):
        return RoleResolveResult(
            role_code=role_code,
            role_name=role_name,
            holder_id=default["id"],
            holder_name=default.get("name", ""),
            is_delegated=False,
            delegation_type=None,
            source_store_id=None,
        )

    # 无人可用
    return RoleResolveResult(
        role_code=role_code,
        role_name=role_name,
        holder_id="",
        holder_name="[未指派]",
        is_delegated=False,
        delegation_type=None,
        source_store_id=None,
    )


def create_delegation(
    store_id: str,
    biz_date: date,
    role_code: str,
    default_holder_id: str,
    default_holder_name: str,
    actual_holder_id: str,
    actual_holder_name: str,
    delegation_type: str,
    delegation_reason: str,
    delegated_by: str,
    source_store_id: Optional[str] = None,
) -> RoleAssignment:
    """创建一条委派记录"""
    role_def = STANDARD_ROLES.get(role_code, {})

    return RoleAssignment(
        id=str(uuid4()),
        store_id=store_id,
        biz_date=biz_date,
        role_code=role_code,
        role_name=role_def.get("name", role_code),
        default_holder_id=default_holder_id,
        default_holder_name=default_holder_name,
        actual_holder_id=actual_holder_id,
        actual_holder_name=actual_holder_name,
        is_delegated=True,
        delegation_type=delegation_type,
        delegation_reason=delegation_reason,
        delegated_by=delegated_by,
        source_store_id=source_store_id,
        status="active",
        created_at=datetime.utcnow().isoformat(),
        permissions=role_def.get("permissions", []),
    )


def check_delegation_authority(
    delegated_by_role: str,
    target_role: str,
) -> Dict:
    """
    检查委派人是否有权委派目标角色。

    规则：
    - 店长可以委派所有门店角色
    - 副店长只能委派值班经理和高级员工
    - 总部可以委派任何角色（跨店）
    - 不能自己委派自己的角色给自己
    """
    # 总部权限最高
    if delegated_by_role in ("hq_admin", "regional_manager"):
        return {"authorized": True, "reason": "总部/区域经理有全部委派权限"}

    role_def = STANDARD_ROLES.get(delegated_by_role, {})
    allowed = role_def.get("delegate_to", [])

    # 店长可以委派所有门店角色
    if delegated_by_role == "store_manager":
        return {"authorized": True, "reason": "店长有门店全部委派权限"}

    if target_role in allowed or f"{target_role}_other" in allowed:
        return {"authorized": True, "reason": f"{delegated_by_role}可以委派{target_role}"}

    return {
        "authorized": False,
        "reason": f"{delegated_by_role}无权委派{target_role}角色",
    }


def build_daily_role_map(
    store_id: str,
    biz_date: date,
    assignments: List[RoleAssignment],
    default_holders: Dict[str, Dict],
) -> List[RoleResolveResult]:
    """
    构建门店今日完整角色映射表。
    遍历所有标准岗位，逐一解析今天由谁执行。
    """
    results = []
    for role_code in STANDARD_ROLES:
        result = resolve_role_holder(
            role_code, store_id, biz_date, assignments, default_holders,
        )
        results.append(result)
    return results


def get_user_today_roles(
    user_id: str,
    store_id: str,
    biz_date: date,
    assignments: List[RoleAssignment],
    default_holders: Dict[str, Dict],
) -> List[Dict]:
    """
    查询某个人今天在某门店扮演的所有角色。
    用于前端显示"今日身份"和权限判断。
    """
    role_map = build_daily_role_map(store_id, biz_date, assignments, default_holders)
    user_roles = []
    for r in role_map:
        if r.holder_id == user_id:
            role_def = STANDARD_ROLES.get(r.role_code, {})
            user_roles.append({
                "role_code": r.role_code,
                "role_name": r.role_name,
                "is_delegated": r.is_delegated,
                "delegation_type": r.delegation_type,
                "permissions": role_def.get("permissions", []),
                "source_store_id": r.source_store_id,
            })
    return user_roles


def integrate_with_daily_flow(
    role_map: List[RoleResolveResult],
    nodes: List[Dict],
    tasks: List[Dict],
) -> tuple:
    """
    将角色映射注入到全天流程的节点和任务中。

    规则：
    - 节点的 owner_role → 查角色映射 → 替换为实际今日执行人
    - 任务的 assignee_role → 同理替换
    - 保留 _original_role 字段供审计

    Returns:
        (更新后的nodes, 更新后的tasks)
    """
    role_lookup = {r.role_code: r for r in role_map}

    updated_nodes = []
    for node in nodes:
        n = dict(node)
        owner_role = n.get("owner_role", "store_manager")
        resolved = role_lookup.get(owner_role)
        if resolved:
            n["owner_user_id"] = resolved.holder_id
            n["owner_user_name"] = resolved.holder_name
            n["owner_is_delegated"] = resolved.is_delegated
            n["owner_delegation_type"] = resolved.delegation_type
        n["_original_role"] = owner_role
        updated_nodes.append(n)

    updated_tasks = []
    for task in tasks:
        t = dict(task)
        assignee_role = t.get("assignee_role", "store_staff")
        resolved = role_lookup.get(assignee_role)
        if resolved:
            t["assignee_user_id"] = resolved.holder_id
            t["assignee_user_name"] = resolved.holder_name
            t["assignee_is_delegated"] = resolved.is_delegated
        t["_original_role"] = assignee_role
        updated_tasks.append(t)

    return updated_nodes, updated_tasks


def build_handover_checklist(
    delegator_name: str,
    delegate_name: str,
    role_name: str,
    delegation_type: str,
    nodes_today: List[Dict],
) -> List[Dict]:
    """
    生成代班交接清单。

    当代班发生时自动生成，提醒代班人今天的关键事项。
    """
    checklist = []

    checklist.append({
        "item": f"确认身份：今日由{delegate_name}代替{delegator_name}担任{role_name}",
        "type": "confirm",
        "priority": "high",
    })

    # 提取今日关键节点
    pending_nodes = [n for n in nodes_today if n.get("status") in ("pending", "in_progress")]
    if pending_nodes:
        node_names = "、".join(n.get("node_name", "") for n in pending_nodes[:5])
        checklist.append({
            "item": f"今日待完成节点：{node_names}",
            "type": "info",
            "priority": "high",
        })

    # 代班类型特定提醒
    if delegation_type == "cross_store":
        checklist.append({
            "item": "跨店代班：请先熟悉本店特有流程和人员",
            "type": "warning",
            "priority": "high",
        })
    elif delegation_type == "emergency":
        checklist.append({
            "item": "紧急代班：请尽快联系交接人了解当前情况",
            "type": "warning",
            "priority": "high",
        })

    checklist.append({
        "item": f"代班结束后请确认所有任务已完成或已交接",
        "type": "confirm",
        "priority": "medium",
    })

    return checklist
