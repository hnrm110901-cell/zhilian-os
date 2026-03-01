"""
ARCH-004: 指令注册表

定义所有可执行指令的元数据：权限级别、金额熔断阈值、路由方式。
"""
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel


class ExecutionLevel(str, Enum):
    """执行路由级别"""
    NOTIFY = "notify"    # 仅通知，无需审批，自动执行
    APPROVE = "approve"  # 需要上级审批后执行
    AUTO = "auto"        # 自动执行，无需审批（低风险操作）


class CommandDef(BaseModel):
    """指令定义"""
    command_type: str
    display_name: str
    level: ExecutionLevel
    # 金额熔断阈值（元）。超过此金额自动升级为 APPROVE
    amount_circuit_breaker: Optional[float] = None
    # 哪些角色可以直接执行（无需审批）
    allowed_roles: List[str] = []
    # 哪些角色可以审批
    approver_roles: List[str] = []
    description: str = ""


# ==================== 指令注册表 ====================
COMMAND_REGISTRY: dict[str, CommandDef] = {
    "discount_apply": CommandDef(
        command_type="discount_apply",
        display_name="折扣申请",
        level=ExecutionLevel.APPROVE,
        amount_circuit_breaker=500.0,   # 超过500元必须审批
        allowed_roles=["store_manager", "assistant_manager"],
        approver_roles=["store_manager", "admin", "super_admin"],
        description="申请订单折扣，需要店长审批",
    ),
    "shift_report": CommandDef(
        command_type="shift_report",
        display_name="班次报表",
        level=ExecutionLevel.AUTO,
        allowed_roles=["store_manager", "assistant_manager", "floor_manager", "finance"],
        approver_roles=[],
        description="生成班次运营报表，自动执行无需审批",
    ),
    "stock_alert": CommandDef(
        command_type="stock_alert",
        display_name="库存告警",
        level=ExecutionLevel.NOTIFY,
        allowed_roles=["store_manager", "warehouse_manager", "procurement"],
        approver_roles=[],
        description="触发库存预警通知，无需审批",
    ),
    "price_adjustment": CommandDef(
        command_type="price_adjustment",
        display_name="价格调整",
        level=ExecutionLevel.APPROVE,
        amount_circuit_breaker=100.0,
        allowed_roles=["store_manager"],
        approver_roles=["admin", "super_admin"],
        description="调整菜品价格，需要管理员审批",
    ),
    "staff_overtime": CommandDef(
        command_type="staff_overtime",
        display_name="加班申请",
        level=ExecutionLevel.APPROVE,
        allowed_roles=["floor_manager", "store_manager"],
        approver_roles=["store_manager", "admin"],
        description="员工加班申请，需要店长审批",
    ),
    "inventory_write_off": CommandDef(
        command_type="inventory_write_off",
        display_name="库存核销",
        level=ExecutionLevel.APPROVE,
        amount_circuit_breaker=1000.0,
        allowed_roles=["warehouse_manager", "store_manager"],
        approver_roles=["store_manager", "admin", "super_admin"],
        description="库存损耗核销，超过阈值需要审批",
    ),
}


def get_command_def(command_type: str) -> CommandDef:
    """获取指令定义，不存在则抛出异常"""
    if command_type not in COMMAND_REGISTRY:
        raise ValueError(
            f"未知指令类型: '{command_type}'。已注册指令: {list(COMMAND_REGISTRY.keys())}"
        )
    return COMMAND_REGISTRY[command_type]
