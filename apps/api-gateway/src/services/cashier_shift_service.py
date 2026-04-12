"""
收银员交接班服务
管理收银员换班时的现金清点、差异计算、交接单生成
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class ShiftStatus(str, Enum):
    """交接班状态"""
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    AUDITED = "audited"


@dataclass
class CashDrawerCount:
    """现金面额清点"""
    # 各面额张数
    yuan_100: int = 0
    yuan_50: int = 0
    yuan_20: int = 0
    yuan_10: int = 0
    yuan_5: int = 0
    yuan_1: int = 0
    jiao_5: int = 0  # 5角
    jiao_1: int = 0  # 1角

    @property
    def total_fen(self) -> int:
        """清点总额（分）"""
        return (
            self.yuan_100 * 10000
            + self.yuan_50 * 5000
            + self.yuan_20 * 2000
            + self.yuan_10 * 1000
            + self.yuan_5 * 500
            + self.yuan_1 * 100
            + self.jiao_5 * 50
            + self.jiao_1 * 10
        )

    @property
    def total_yuan(self) -> float:
        """清点总额（元）"""
        return round(self.total_fen / 100, 2)


@dataclass
class CashierShift:
    """收银员班次"""
    shift_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str = ""
    cashier_id: str = ""
    cashier_name: str = ""
    register_id: str = ""  # 收银台编号
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None
    status: ShiftStatus = ShiftStatus.OPEN
    # 系统记录的现金交易总额（分）
    system_cash_fen: int = 0
    # 开班备用金（分）
    opening_float_fen: int = 0
    # 清点结果
    drawer_count: Optional[CashDrawerCount] = None
    # 差异（分）：正=长款，负=短款
    variance_fen: int = 0
    notes: str = ""


@dataclass
class ShiftSummary:
    """班次汇总"""
    shift_id: str = ""
    cashier_name: str = ""
    store_id: str = ""
    duration_minutes: int = 0
    # 各支付方式汇总（分）
    cash_total_fen: int = 0
    wechat_total_fen: int = 0
    alipay_total_fen: int = 0
    card_total_fen: int = 0
    other_total_fen: int = 0
    order_count: int = 0
    refund_count: int = 0
    refund_total_fen: int = 0
    # 差异
    variance_fen: int = 0
    variance_yuan: float = 0.0
    variance_type: str = ""  # "长款" / "短款" / "无差异"


class CashierShiftService:
    """收银员交接班服务"""

    def __init__(self):
        # 内存存储：shift_id -> CashierShift
        self._shifts: Dict[str, CashierShift] = {}
        # 班次交易记录：shift_id -> [{"type": "cash"/"wechat"/..., "amount_fen": int}]
        self._transactions: Dict[str, List[Dict]] = {}

    def open_shift(
        self,
        store_id: str,
        cashier_id: str,
        cashier_name: str,
        register_id: str,
        opening_float_fen: int = 0,
    ) -> CashierShift:
        """
        开班
        :param opening_float_fen: 备用金（分）
        """
        shift = CashierShift(
            store_id=store_id,
            cashier_id=cashier_id,
            cashier_name=cashier_name,
            register_id=register_id,
            open_time=datetime.now(timezone.utc),
            status=ShiftStatus.OPEN,
            opening_float_fen=opening_float_fen,
        )
        self._shifts[shift.shift_id] = shift
        self._transactions[shift.shift_id] = []
        logger.info("收银员开班", shift_id=shift.shift_id, cashier=cashier_name, register=register_id)
        return shift

    def record_transaction(self, shift_id: str, payment_type: str, amount_fen: int) -> bool:
        """记录一笔交易到当前班次"""
        if shift_id not in self._shifts:
            return False
        shift = self._shifts[shift_id]
        if shift.status != ShiftStatus.OPEN:
            return False
        self._transactions[shift_id].append({"type": payment_type, "amount_fen": amount_fen})
        if payment_type == "cash":
            shift.system_cash_fen += amount_fen
        return True

    def close_shift(self, shift_id: str, drawer_count: CashDrawerCount, notes: str = "") -> CashierShift:
        """
        关班并清点现金
        差异 = 清点现金 - (系统现金 + 备用金)
        正值=长款，负值=短款
        """
        if shift_id not in self._shifts:
            raise ValueError(f"班次不存在: {shift_id}")
        shift = self._shifts[shift_id]
        if shift.status != ShiftStatus.OPEN:
            raise ValueError(f"班次状态不允许关班: {shift.status}")

        shift.close_time = datetime.now(timezone.utc)
        shift.status = ShiftStatus.CLOSED
        shift.drawer_count = drawer_count
        shift.notes = notes
        shift.variance_fen = self.calculate_variance(shift)

        logger.info(
            "收银员关班",
            shift_id=shift_id,
            variance_fen=shift.variance_fen,
            variance_yuan=round(shift.variance_fen / 100, 2),
        )
        return shift

    def calculate_variance(self, shift: CashierShift) -> int:
        """
        计算差异（分）
        差异 = 清点现金 - (系统现金 + 备用金)
        """
        if shift.drawer_count is None:
            return 0
        counted = shift.drawer_count.total_fen
        expected = shift.system_cash_fen + shift.opening_float_fen
        return counted - expected

    def get_shift_summary(self, shift_id: str) -> ShiftSummary:
        """获取班次汇总"""
        if shift_id not in self._shifts:
            raise ValueError(f"班次不存在: {shift_id}")
        shift = self._shifts[shift_id]
        txns = self._transactions.get(shift_id, [])

        # 按支付方式汇总
        cash_total = sum(t["amount_fen"] for t in txns if t["type"] == "cash")
        wechat_total = sum(t["amount_fen"] for t in txns if t["type"] == "wechat")
        alipay_total = sum(t["amount_fen"] for t in txns if t["type"] == "alipay")
        card_total = sum(t["amount_fen"] for t in txns if t["type"] == "card")
        other_total = sum(t["amount_fen"] for t in txns if t["type"] not in ("cash", "wechat", "alipay", "card"))
        refund_txns = [t for t in txns if t["amount_fen"] < 0]

        # 计算时长
        duration = 0
        if shift.open_time and shift.close_time:
            duration = int((shift.close_time - shift.open_time).total_seconds() / 60)

        variance_fen = shift.variance_fen
        if variance_fen > 0:
            vtype = "长款"
        elif variance_fen < 0:
            vtype = "短款"
        else:
            vtype = "无差异"

        return ShiftSummary(
            shift_id=shift_id,
            cashier_name=shift.cashier_name,
            store_id=shift.store_id,
            duration_minutes=duration,
            cash_total_fen=cash_total,
            wechat_total_fen=wechat_total,
            alipay_total_fen=alipay_total,
            card_total_fen=card_total,
            other_total_fen=other_total,
            order_count=len([t for t in txns if t["amount_fen"] > 0]),
            refund_count=len(refund_txns),
            refund_total_fen=sum(t["amount_fen"] for t in refund_txns),
            variance_fen=variance_fen,
            variance_yuan=round(variance_fen / 100, 2),
            variance_type=vtype,
        )

    def audit_shift(self, shift_id: str, auditor_id: str, approved: bool, comment: str = "") -> CashierShift:
        """审核班次（主管审核长短款）"""
        if shift_id not in self._shifts:
            raise ValueError(f"班次不存在: {shift_id}")
        shift = self._shifts[shift_id]
        if shift.status != ShiftStatus.CLOSED:
            raise ValueError("只有已关班的班次才能审核")
        shift.status = ShiftStatus.AUDITED
        logger.info("班次审核", shift_id=shift_id, auditor=auditor_id, approved=approved, comment=comment)
        return shift

    def generate_handover_receipt(self, shift_id: str) -> Dict:
        """生成交接单（可打印）"""
        summary = self.get_shift_summary(shift_id)
        shift = self._shifts[shift_id]
        count = shift.drawer_count

        receipt = {
            "title": "收银交接单",
            "shift_id": shift_id,
            "store_id": shift.store_id,
            "cashier": shift.cashier_name,
            "register": shift.register_id,
            "open_time": shift.open_time.isoformat() if shift.open_time else "",
            "close_time": shift.close_time.isoformat() if shift.close_time else "",
            "duration_minutes": summary.duration_minutes,
            "opening_float_yuan": round(shift.opening_float_fen / 100, 2),
            "denomination_count": {
                "100元": count.yuan_100 if count else 0,
                "50元": count.yuan_50 if count else 0,
                "20元": count.yuan_20 if count else 0,
                "10元": count.yuan_10 if count else 0,
                "5元": count.yuan_5 if count else 0,
                "1元": count.yuan_1 if count else 0,
                "5角": count.jiao_5 if count else 0,
                "1角": count.jiao_1 if count else 0,
            },
            "counted_cash_yuan": count.total_yuan if count else 0,
            "system_cash_yuan": round(shift.system_cash_fen / 100, 2),
            "variance_yuan": summary.variance_yuan,
            "variance_type": summary.variance_type,
            "payment_summary": {
                "现金": round(summary.cash_total_fen / 100, 2),
                "微信": round(summary.wechat_total_fen / 100, 2),
                "支付宝": round(summary.alipay_total_fen / 100, 2),
                "银行卡": round(summary.card_total_fen / 100, 2),
                "其他": round(summary.other_total_fen / 100, 2),
            },
            "order_count": summary.order_count,
            "refund_count": summary.refund_count,
            "refund_total_yuan": round(summary.refund_total_fen / 100, 2),
            "notes": shift.notes,
        }
        return receipt
