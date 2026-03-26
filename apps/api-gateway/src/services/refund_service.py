"""
退款管理服务
支持全额/部分/单品退款，自动审批（<5000分），异常检测
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()

# 自动审批阈值（分）
AUTO_APPROVE_THRESHOLD_FEN = 5000


class RefundType(str, Enum):
    """退款类型"""
    FULL = "full"        # 整单退
    PARTIAL = "partial"  # 部分金额退
    ITEM = "item"        # 按菜品退


class RefundStatus(str, Enum):
    """退款状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSED = "processed"
    FAILED = "failed"


class RefundReason(str, Enum):
    """退款原因"""
    CUSTOMER_REQUEST = "customer_request"    # 顾客主动退
    FOOD_QUALITY = "food_quality"            # 菜品质量问题
    WRONG_ORDER = "wrong_order"              # 上错菜
    LONG_WAIT = "long_wait"                  # 等待时间过长
    DUPLICATE_PAY = "duplicate_pay"          # 重复支付
    PRICE_ERROR = "price_error"              # 价格错误
    OTHER = "other"


@dataclass
class RefundRequest:
    """退款请求"""
    refund_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str = ""
    order_id: str = ""
    refund_type: RefundType = RefundType.FULL
    reason: RefundReason = RefundReason.CUSTOMER_REQUEST
    reason_detail: str = ""
    # 原订单金额（分）
    original_amount_fen: int = 0
    # 退款金额（分）
    refund_amount_fen: int = 0
    # 退款菜品列表（仅 ITEM 类型使用）
    refund_items: List[Dict] = field(default_factory=list)
    status: RefundStatus = RefundStatus.PENDING
    operator_id: str = ""
    approver_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None
    reject_reason: str = ""

    @property
    def refund_amount_yuan(self) -> float:
        return round(self.refund_amount_fen / 100, 2)

    @property
    def original_amount_yuan(self) -> float:
        return round(self.original_amount_fen / 100, 2)


class RefundService:
    """退款管理服务"""

    def __init__(self):
        self._refunds: Dict[str, RefundRequest] = {}
        # store_id -> 每日退款统计缓存
        self._daily_stats_cache: Dict[str, Dict] = {}

    def create_refund_request(
        self,
        store_id: str,
        order_id: str,
        refund_type: RefundType,
        reason: RefundReason,
        original_amount_fen: int,
        refund_amount_fen: int,
        operator_id: str = "",
        reason_detail: str = "",
        refund_items: Optional[List[Dict]] = None,
    ) -> RefundRequest:
        """
        创建退款请求
        自动检查是否可自动审批（<5000分自动通过）
        """
        if refund_amount_fen <= 0:
            raise ValueError("退款金额必须大于0")
        if refund_amount_fen > original_amount_fen:
            raise ValueError("退款金额不能超过原订单金额")

        req = RefundRequest(
            store_id=store_id,
            order_id=order_id,
            refund_type=refund_type,
            reason=reason,
            reason_detail=reason_detail,
            original_amount_fen=original_amount_fen,
            refund_amount_fen=refund_amount_fen,
            refund_items=refund_items or [],
            operator_id=operator_id,
        )

        # 自动审批判断
        if self.auto_approve_check(req):
            req.status = RefundStatus.APPROVED
            req.approver_id = "SYSTEM_AUTO"
            logger.info("退款自动审批通过", refund_id=req.refund_id,
                        amount_yuan=req.refund_amount_yuan)
        else:
            logger.info("退款需人工审批", refund_id=req.refund_id,
                        amount_yuan=req.refund_amount_yuan)

        self._refunds[req.refund_id] = req
        return req

    def auto_approve_check(self, req: RefundRequest) -> bool:
        """
        自动审批检查
        规则：退款金额 < 5000分(50元) 自动通过
        """
        return req.refund_amount_fen < AUTO_APPROVE_THRESHOLD_FEN

    def approve(self, refund_id: str, approver_id: str) -> RefundRequest:
        """审批通过"""
        req = self._get_refund(refund_id)
        if req.status != RefundStatus.PENDING:
            raise ValueError(f"退款状态不允许审批: {req.status.value}")
        req.status = RefundStatus.APPROVED
        req.approver_id = approver_id
        logger.info("退款审批通过", refund_id=refund_id, approver=approver_id)
        return req

    def reject(self, refund_id: str, approver_id: str, reject_reason: str = "") -> RefundRequest:
        """审批拒绝"""
        req = self._get_refund(refund_id)
        if req.status != RefundStatus.PENDING:
            raise ValueError(f"退款状态不允许拒绝: {req.status.value}")
        req.status = RefundStatus.REJECTED
        req.approver_id = approver_id
        req.reject_reason = reject_reason
        logger.info("退款审批拒绝", refund_id=refund_id, reason=reject_reason)
        return req

    def process_refund(self, refund_id: str) -> RefundRequest:
        """
        执行退款（模拟退回资金）
        仅已审批的退款可执行
        """
        req = self._get_refund(refund_id)
        if req.status != RefundStatus.APPROVED:
            raise ValueError(f"退款未审批，无法执行: {req.status.value}")
        req.status = RefundStatus.PROCESSED
        req.processed_at = datetime.now(timezone.utc)
        logger.info("退款已处理", refund_id=refund_id, amount_yuan=req.refund_amount_yuan)
        return req

    def calculate_partial(
        self,
        original_amount_fen: int,
        items: List[Dict],
    ) -> Dict:
        """
        计算部分退款金额
        items: [{"name": "菜名", "price_fen": 3000, "qty": 1}, ...]
        """
        refund_fen = sum(item["price_fen"] * item.get("qty", 1) for item in items)
        if refund_fen > original_amount_fen:
            refund_fen = original_amount_fen
        return {
            "original_amount_fen": original_amount_fen,
            "original_amount_yuan": round(original_amount_fen / 100, 2),
            "refund_amount_fen": refund_fen,
            "refund_amount_yuan": round(refund_fen / 100, 2),
            "remaining_fen": original_amount_fen - refund_fen,
            "remaining_yuan": round((original_amount_fen - refund_fen) / 100, 2),
            "items": items,
        }

    def get_daily_stats(self, store_id: str, date: Optional[datetime] = None) -> Dict:
        """获取门店当日退款统计"""
        target_date = (date or datetime.now(timezone.utc)).date()
        refunds = [
            r for r in self._refunds.values()
            if r.store_id == store_id and r.created_at.date() == target_date
        ]
        total_fen = sum(r.refund_amount_fen for r in refunds if r.status == RefundStatus.PROCESSED)
        return {
            "store_id": store_id,
            "date": target_date.isoformat(),
            "total_refund_count": len(refunds),
            "processed_count": len([r for r in refunds if r.status == RefundStatus.PROCESSED]),
            "pending_count": len([r for r in refunds if r.status == RefundStatus.PENDING]),
            "rejected_count": len([r for r in refunds if r.status == RefundStatus.REJECTED]),
            "total_refund_fen": total_fen,
            "total_refund_yuan": round(total_fen / 100, 2),
            "by_reason": self._group_by_reason(refunds),
        }

    def check_anomaly(self, store_id: str, threshold_count: int = 10, threshold_fen: int = 500000) -> Dict:
        """
        异常检测：当日退款次数或金额超阈值告警
        threshold_fen: 默认5000元
        """
        stats = self.get_daily_stats(store_id)
        anomalies = []
        if stats["total_refund_count"] >= threshold_count:
            anomalies.append({
                "type": "退款次数过多",
                "value": stats["total_refund_count"],
                "threshold": threshold_count,
            })
        if stats["total_refund_fen"] >= threshold_fen:
            anomalies.append({
                "type": "退款金额过高",
                "value_fen": stats["total_refund_fen"],
                "value_yuan": stats["total_refund_yuan"],
                "threshold_fen": threshold_fen,
                "threshold_yuan": round(threshold_fen / 100, 2),
            })
        result = {
            "store_id": store_id,
            "has_anomaly": len(anomalies) > 0,
            "anomalies": anomalies,
            "stats": stats,
        }
        if anomalies:
            logger.warning("退款异常检测告警", store_id=store_id, anomalies=anomalies)
        return result

    def _get_refund(self, refund_id: str) -> RefundRequest:
        if refund_id not in self._refunds:
            raise ValueError(f"退款请求不存在: {refund_id}")
        return self._refunds[refund_id]

    @staticmethod
    def _group_by_reason(refunds: List[RefundRequest]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for r in refunds:
            key = r.reason.value
            result[key] = result.get(key, 0) + 1
        return result
