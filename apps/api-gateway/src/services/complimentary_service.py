"""
赠菜/试吃/招待审批管理服务

纯Python实现，不依赖数据库。
管理赠菜申请的创建、审批、预算控制和报表统计。
金额单位：分（fen）
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


class ComplimentaryReason(str, Enum):
    """赠菜原因"""
    COMPLAINT = "complaint"              # 客诉补偿
    VIP_MAINTAIN = "vip_maintain"        # VIP关系维护
    NEW_DISH_TASTING = "new_dish_tasting"  # 新品试吃
    STAFF_MEAL = "staff_meal"            # 员工餐
    MARKETING = "marketing"              # 营销活动
    MANAGER_DECISION = "manager_decision"  # 店长决定


class ApprovalStatus(str, Enum):
    """审批状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"


# 自动审批阈值：低于此金额（分）可自动通过
AUTO_APPROVE_THRESHOLD_FEN = 2000

# 自动审批的原因类型（无需人工审批）
AUTO_APPROVE_REASONS = {
    ComplimentaryReason.STAFF_MEAL,
}


@dataclass
class ComplimentaryRequest:
    """赠菜申请"""
    request_id: str
    order_id: str
    dish_id: str
    dish_name: str
    quantity: int
    cost_fen: int
    reason: ComplimentaryReason
    requester_id: str
    approver_id: Optional[str] = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    reject_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

    @property
    def total_cost_fen(self) -> int:
        """总成本（分）"""
        return self.cost_fen * self.quantity

    @property
    def total_cost_yuan(self) -> float:
        """总成本（元，保留2位小数）"""
        return round(self.total_cost_fen / 100, 2)


class ComplimentaryService:
    """赠菜/试吃/招待审批管理"""

    def create_request(
        self,
        order_id: str,
        dish_id: str,
        dish_name: str,
        quantity: int,
        cost_fen: int,
        reason: ComplimentaryReason,
        requester_id: str,
    ) -> ComplimentaryRequest:
        """
        创建赠菜申请

        Args:
            order_id: 关联订单ID
            dish_id: 菜品ID
            dish_name: 菜品名称
            quantity: 数量
            cost_fen: 单份成本（分）
            reason: 赠菜原因
            requester_id: 申请人ID

        Returns:
            ComplimentaryRequest 申请对象
        """
        if quantity <= 0:
            raise ValueError("数量必须大于0")
        if cost_fen < 0:
            raise ValueError("成本不能为负数")

        request = ComplimentaryRequest(
            request_id=str(uuid.uuid4()),
            order_id=order_id,
            dish_id=dish_id,
            dish_name=dish_name,
            quantity=quantity,
            cost_fen=cost_fen,
            reason=reason,
            requester_id=requester_id,
        )

        logger.info(
            "complimentary_request_created",
            request_id=request.request_id,
            dish_name=dish_name,
            reason=reason.value,
            total_cost_fen=request.total_cost_fen,
        )

        return request

    def auto_approve_check(
        self,
        request: ComplimentaryRequest,
        daily_budget_fen: int,
        daily_used_fen: int,
    ) -> bool:
        """
        检查是否可以自动审批

        自动审批条件（满足任一即可）：
        1. 员工餐（STAFF_MEAL）且未超预算
        2. 单笔金额 < 2000分（20元）且未超预算

        Args:
            request: 赠菜申请
            daily_budget_fen: 每日赠菜预算（分）
            daily_used_fen: 当日已用预算（分）

        Returns:
            True 表示可以自动审批
        """
        remaining_budget = daily_budget_fen - daily_used_fen
        total_cost = request.total_cost_fen

        # 超预算不自动审批
        if total_cost > remaining_budget:
            logger.info(
                "auto_approve_rejected_over_budget",
                request_id=request.request_id,
                total_cost_fen=total_cost,
                remaining_budget_fen=remaining_budget,
            )
            return False

        # 员工餐自动通过
        if request.reason in AUTO_APPROVE_REASONS:
            request.status = ApprovalStatus.AUTO_APPROVED
            request.updated_at = datetime.utcnow()
            logger.info(
                "auto_approved_staff_meal",
                request_id=request.request_id,
            )
            return True

        # 小金额自动通过
        if total_cost < AUTO_APPROVE_THRESHOLD_FEN:
            request.status = ApprovalStatus.AUTO_APPROVED
            request.updated_at = datetime.utcnow()
            logger.info(
                "auto_approved_small_amount",
                request_id=request.request_id,
                total_cost_fen=total_cost,
            )
            return True

        return False

    def approve(
        self,
        request: ComplimentaryRequest,
        approver_id: str,
    ) -> ComplimentaryRequest:
        """
        审批通过

        Args:
            request: 赠菜申请
            approver_id: 审批人ID

        Returns:
            更新后的申请对象
        """
        if request.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"只能审批待处理的申请，当前状态: {request.status.value}"
            )

        request.status = ApprovalStatus.APPROVED
        request.approver_id = approver_id
        request.updated_at = datetime.utcnow()

        logger.info(
            "complimentary_request_approved",
            request_id=request.request_id,
            approver_id=approver_id,
        )

        return request

    def reject(
        self,
        request: ComplimentaryRequest,
        approver_id: str,
        reason: str,
    ) -> ComplimentaryRequest:
        """
        审批拒绝

        Args:
            request: 赠菜申请
            approver_id: 审批人ID
            reason: 拒绝原因

        Returns:
            更新后的申请对象
        """
        if request.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"只能拒绝待处理的申请，当前状态: {request.status.value}"
            )
        if not reason or not reason.strip():
            raise ValueError("拒绝原因不能为空")

        request.status = ApprovalStatus.REJECTED
        request.approver_id = approver_id
        request.reject_reason = reason.strip()
        request.updated_at = datetime.utcnow()

        logger.info(
            "complimentary_request_rejected",
            request_id=request.request_id,
            approver_id=approver_id,
            reason=reason,
        )

        return request

    def calculate_daily_complimentary(
        self,
        requests: List[ComplimentaryRequest],
        target_date: date,
    ) -> Dict:
        """
        计算指定日期的赠菜成本统计

        Args:
            requests: 所有赠菜申请列表
            target_date: 目标日期

        Returns:
            当日赠菜统计：总金额(分/元)、通过数量、各原因明细
        """
        # 筛选当日已通过的申请
        approved_statuses = {ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPROVED}
        daily_requests = [
            r for r in requests
            if r.created_at.date() == target_date
            and r.status in approved_statuses
        ]

        total_cost_fen = sum(r.total_cost_fen for r in daily_requests)

        # 按原因分类汇总
        by_reason: Dict[str, Dict] = {}
        for r in daily_requests:
            key = r.reason.value
            if key not in by_reason:
                by_reason[key] = {"count": 0, "total_cost_fen": 0}
            by_reason[key]["count"] += r.quantity
            by_reason[key]["total_cost_fen"] += r.total_cost_fen

        # 为每个原因添加元金额
        for entry in by_reason.values():
            entry["total_cost_yuan"] = round(entry["total_cost_fen"] / 100, 2)

        return {
            "date": target_date.isoformat(),
            "approved_count": len(daily_requests),
            "total_cost_fen": total_cost_fen,
            "total_cost_yuan": round(total_cost_fen / 100, 2),
            "by_reason": by_reason,
        }

    def get_complimentary_report(
        self,
        requests: List[ComplimentaryRequest],
        start_date: date,
        end_date: date,
    ) -> Dict:
        """
        赠菜报告（按原因分类 + 金额汇总）

        Args:
            requests: 所有赠菜申请列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            报告：总金额、按原因分类明细、按日期趋势
        """
        if start_date > end_date:
            raise ValueError("开始日期不能晚于结束日期")

        approved_statuses = {ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPROVED}
        filtered = [
            r for r in requests
            if start_date <= r.created_at.date() <= end_date
            and r.status in approved_statuses
        ]

        total_cost_fen = sum(r.total_cost_fen for r in filtered)

        # 按原因汇总
        by_reason: Dict[str, Dict] = {}
        for r in filtered:
            key = r.reason.value
            if key not in by_reason:
                by_reason[key] = {"count": 0, "total_cost_fen": 0, "dishes": []}
            by_reason[key]["count"] += r.quantity
            by_reason[key]["total_cost_fen"] += r.total_cost_fen
            by_reason[key]["dishes"].append(r.dish_name)

        for entry in by_reason.values():
            entry["total_cost_yuan"] = round(entry["total_cost_fen"] / 100, 2)
            entry["dishes"] = list(set(entry["dishes"]))

        # 按日期趋势
        daily_trend: Dict[str, int] = {}
        for r in filtered:
            day_key = r.created_at.date().isoformat()
            daily_trend[day_key] = daily_trend.get(day_key, 0) + r.total_cost_fen

        daily_trend_list = [
            {"date": k, "cost_fen": v, "cost_yuan": round(v / 100, 2)}
            for k, v in sorted(daily_trend.items())
        ]

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_requests": len(filtered),
            "total_cost_fen": total_cost_fen,
            "total_cost_yuan": round(total_cost_fen / 100, 2),
            "by_reason": by_reason,
            "daily_trend": daily_trend_list,
        }

    def check_budget_alert(
        self,
        daily_used_fen: int,
        daily_budget_fen: int,
    ) -> Optional[Dict]:
        """
        检查赠菜预算告警

        Args:
            daily_used_fen: 当日已用金额（分）
            daily_budget_fen: 每日预算（分）

        Returns:
            告警信息（超过80%预警，超过100%告警），None表示无告警
        """
        if daily_budget_fen <= 0:
            raise ValueError("每日预算必须大于0")

        usage_ratio = daily_used_fen / daily_budget_fen

        if usage_ratio >= 1.0:
            alert = {
                "level": "critical",
                "message": f"赠菜预算已超支！已用¥{daily_used_fen / 100:.2f}，"
                           f"预算¥{daily_budget_fen / 100:.2f}，"
                           f"超支¥{(daily_used_fen - daily_budget_fen) / 100:.2f}",
                "usage_ratio": round(usage_ratio, 4),
                "daily_used_fen": daily_used_fen,
                "daily_used_yuan": round(daily_used_fen / 100, 2),
                "daily_budget_fen": daily_budget_fen,
                "daily_budget_yuan": round(daily_budget_fen / 100, 2),
                "action": "立即停止赠菜，通知店长审批",
            }
            logger.warning("complimentary_budget_exceeded", **alert)
            return alert

        if usage_ratio >= 0.8:
            alert = {
                "level": "warning",
                "message": f"赠菜预算即将用完！已用¥{daily_used_fen / 100:.2f}，"
                           f"预算¥{daily_budget_fen / 100:.2f}，"
                           f"剩余¥{(daily_budget_fen - daily_used_fen) / 100:.2f}",
                "usage_ratio": round(usage_ratio, 4),
                "daily_used_fen": daily_used_fen,
                "daily_used_yuan": round(daily_used_fen / 100, 2),
                "daily_budget_fen": daily_budget_fen,
                "daily_budget_yuan": round(daily_budget_fen / 100, 2),
                "action": "控制赠菜频率，优先审批高价值客诉",
            }
            logger.warning("complimentary_budget_warning", **alert)
            return alert

        return None
