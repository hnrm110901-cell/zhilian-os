"""
折扣权限分级服务
控制不同角色的折扣权限：收银员最多9折/店长7折/区域经理5折
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class DiscountRole(str, Enum):
    """折扣权限角色"""
    CASHIER = "cashier"            # 收银员
    SHIFT_LEADER = "shift_leader"  # 值班经理
    STORE_MANAGER = "store_manager"  # 店长
    AREA_MANAGER = "area_manager"  # 区域经理
    HQ_ADMIN = "hq_admin"         # 总部管理


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# 默认折扣权限配置：角色 -> 最低折扣（0.5 表示5折）
DEFAULT_DISCOUNT_CONFIG: Dict[str, float] = {
    DiscountRole.CASHIER.value: 0.90,         # 收银员最多9折
    DiscountRole.SHIFT_LEADER.value: 0.80,    # 值班经理8折
    DiscountRole.STORE_MANAGER.value: 0.70,   # 店长7折
    DiscountRole.AREA_MANAGER.value: 0.50,    # 区域经理5折
    DiscountRole.HQ_ADMIN.value: 0.0,         # 总部无限制
}


@dataclass
class DiscountApproval:
    """折扣审批请求"""
    approval_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str = ""
    order_id: str = ""
    requester_id: str = ""
    requester_role: str = ""
    requested_discount: float = 1.0  # 请求的折扣率
    original_amount_fen: int = 0
    discounted_amount_fen: int = 0
    reason: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    approver_id: str = ""
    approver_role: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None


class DiscountPermissionService:
    """折扣权限分级服务"""

    def __init__(self, config: Optional[Dict[str, float]] = None):
        # 可自定义配置，否则使用默认
        self._config = config or dict(DEFAULT_DISCOUNT_CONFIG)
        self._approvals: Dict[str, DiscountApproval] = {}

    def check_permission(
        self,
        role: str,
        discount_rate: float,
    ) -> Dict:
        """
        检查折扣权限
        :param role: 操作员角色
        :param discount_rate: 请求的折扣率（0~1，0.7表示打7折）
        :return: {"allowed": bool, "max_discount": float, "need_approval": bool}
        """
        if discount_rate < 0 or discount_rate > 1:
            raise ValueError("折扣率必须在0到1之间")

        min_discount = self._config.get(role, 1.0)  # 默认不允许打折

        allowed = discount_rate >= min_discount
        return {
            "allowed": allowed,
            "role": role,
            "requested_discount": discount_rate,
            "max_discount_for_role": min_discount,
            "need_approval": not allowed,
            "approval_role_needed": self._find_approver_role(discount_rate) if not allowed else None,
        }

    def get_config(self) -> Dict[str, float]:
        """获取当前折扣权限配置"""
        return dict(self._config)

    def update_config(self, role: str, min_discount: float) -> Dict[str, float]:
        """更新角色折扣权限"""
        if min_discount < 0 or min_discount > 1:
            raise ValueError("折扣下限必须在0到1之间")
        self._config[role] = min_discount
        logger.info("更新折扣权限", role=role, min_discount=min_discount)
        return dict(self._config)

    def request_approval(
        self,
        store_id: str,
        order_id: str,
        requester_id: str,
        requester_role: str,
        discount_rate: float,
        original_amount_fen: int,
        reason: str = "",
    ) -> DiscountApproval:
        """发起折扣审批请求"""
        check = self.check_permission(requester_role, discount_rate)
        if check["allowed"]:
            # 权限内，直接通过
            approval = DiscountApproval(
                store_id=store_id,
                order_id=order_id,
                requester_id=requester_id,
                requester_role=requester_role,
                requested_discount=discount_rate,
                original_amount_fen=original_amount_fen,
                discounted_amount_fen=int(original_amount_fen * discount_rate),
                reason=reason,
                status=ApprovalStatus.APPROVED,
                approver_id=requester_id,
                approver_role=requester_role,
                resolved_at=datetime.now(timezone.utc),
            )
        else:
            approval = DiscountApproval(
                store_id=store_id,
                order_id=order_id,
                requester_id=requester_id,
                requester_role=requester_role,
                requested_discount=discount_rate,
                original_amount_fen=original_amount_fen,
                discounted_amount_fen=int(original_amount_fen * discount_rate),
                reason=reason,
                status=ApprovalStatus.PENDING,
            )
            logger.info("折扣审批请求", approval_id=approval.approval_id,
                        discount=discount_rate, role=requester_role)
        self._approvals[approval.approval_id] = approval
        return approval

    def approve_discount(self, approval_id: str, approver_id: str, approver_role: str) -> DiscountApproval:
        """审批通过折扣"""
        approval = self._get_approval(approval_id)
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError("审批已处理")
        # 审批人权限检查
        check = self.check_permission(approver_role, approval.requested_discount)
        if not check["allowed"]:
            raise ValueError(f"审批人权限不足: {approver_role} 无法批准 {approval.requested_discount} 折")
        approval.status = ApprovalStatus.APPROVED
        approval.approver_id = approver_id
        approval.approver_role = approver_role
        approval.resolved_at = datetime.now(timezone.utc)
        logger.info("折扣审批通过", approval_id=approval_id, approver=approver_id)
        return approval

    def reject_discount(self, approval_id: str, approver_id: str, reason: str = "") -> DiscountApproval:
        """拒绝折扣"""
        approval = self._get_approval(approval_id)
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError("审批已处理")
        approval.status = ApprovalStatus.REJECTED
        approval.approver_id = approver_id
        approval.resolved_at = datetime.now(timezone.utc)
        return approval

    def _find_approver_role(self, discount_rate: float) -> Optional[str]:
        """找到能批准该折扣的最低角色"""
        # 按权限从小到大排
        for role, min_disc in sorted(self._config.items(), key=lambda x: x[1]):
            if discount_rate >= min_disc:
                return role
        return DiscountRole.HQ_ADMIN.value

    def _get_approval(self, approval_id: str) -> DiscountApproval:
        if approval_id not in self._approvals:
            raise ValueError(f"审批请求不存在: {approval_id}")
        return self._approvals[approval_id]
