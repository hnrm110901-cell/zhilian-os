"""
加盟商管理服务
加盟商注册、特许权使用费计算、KPI面板、暂停/终止
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


class FranchiseeStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"
    PENDING = "pending"  # 待审核


class FeeType(str, Enum):
    ROYALTY = "royalty"           # 特许权使用费（按营业额百分比）
    MANAGEMENT = "management"     # 管理费（固定）
    MARKETING = "marketing"       # 营销基金
    INITIAL = "initial"           # 加盟费（一次性）


@dataclass
class FranchiseFee:
    """加盟费用"""
    fee_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    franchisee_id: str = ""
    fee_type: FeeType = FeeType.ROYALTY
    period: str = ""         # "2026-03" 月度
    base_amount_fen: int = 0  # 基数（如营业额）
    rate: float = 0.0        # 费率
    amount_fen: int = 0      # 应付金额（分）
    paid: bool = False
    due_date: Optional[date] = None

    @property
    def amount_yuan(self) -> float:
        return round(self.amount_fen / 100, 2)

    @property
    def base_amount_yuan(self) -> float:
        return round(self.base_amount_fen / 100, 2)


@dataclass
class Franchisee:
    """加盟商"""
    franchisee_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    contact_person: str = ""
    phone: str = ""
    store_ids: List[str] = field(default_factory=list)  # 关联门店
    region: str = ""
    status: FranchiseeStatus = FranchiseeStatus.PENDING
    # 费率配置
    royalty_rate: float = 0.03      # 特许权使用费率（默认3%）
    management_fee_fen: int = 0     # 月管理费（分）
    marketing_rate: float = 0.01    # 营销基金费率（1%）
    initial_fee_fen: int = 0        # 加盟费（分）
    contract_start: Optional[date] = None
    contract_end: Optional[date] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class FranchiseService:
    """加盟商管理服务"""

    def __init__(self):
        self._franchisees: Dict[str, Franchisee] = {}
        self._fees: Dict[str, List[FranchiseFee]] = {}
        # 模拟门店营业额数据
        self._store_revenue: Dict[str, Dict[str, int]] = {}  # store_id -> {period: revenue_fen}

    def register(
        self,
        name: str,
        contact_person: str,
        phone: str,
        store_ids: Optional[List[str]] = None,
        region: str = "",
        royalty_rate: float = 0.03,
        management_fee_fen: int = 500000,  # 默认5000元/月
        marketing_rate: float = 0.01,
        initial_fee_fen: int = 10000000,   # 默认10万
        contract_start: Optional[date] = None,
        contract_end: Optional[date] = None,
    ) -> Franchisee:
        """注册加盟商"""
        franchisee = Franchisee(
            name=name,
            contact_person=contact_person,
            phone=phone,
            store_ids=store_ids or [],
            region=region,
            royalty_rate=royalty_rate,
            management_fee_fen=management_fee_fen,
            marketing_rate=marketing_rate,
            initial_fee_fen=initial_fee_fen,
            contract_start=contract_start or date.today(),
            contract_end=contract_end,
            status=FranchiseeStatus.ACTIVE,
        )
        self._franchisees[franchisee.franchisee_id] = franchisee
        self._fees[franchisee.franchisee_id] = []
        logger.info("注册加盟商", id=franchisee.franchisee_id, name=name, stores=len(franchisee.store_ids))
        return franchisee

    def set_store_revenue(self, store_id: str, period: str, revenue_fen: int) -> None:
        """设置门店营业额（供计算特许权使用费）"""
        if store_id not in self._store_revenue:
            self._store_revenue[store_id] = {}
        self._store_revenue[store_id][period] = revenue_fen

    def calculate_royalty(self, franchisee_id: str, period: str) -> List[FranchiseFee]:
        """
        计算某期的各项费用
        - 特许权使用费 = 总营业额 × royalty_rate
        - 管理费 = 固定金额
        - 营销基金 = 总营业额 × marketing_rate
        """
        f = self._get_franchisee(franchisee_id)
        if f.status != FranchiseeStatus.ACTIVE:
            raise ValueError(f"加盟商状态异常: {f.status.value}")

        # 计算总营业额
        total_revenue_fen = 0
        for sid in f.store_ids:
            rev = self._store_revenue.get(sid, {}).get(period, 0)
            total_revenue_fen += rev

        fees = []
        # 特许权使用费
        royalty_fen = int(total_revenue_fen * f.royalty_rate)
        fees.append(FranchiseFee(
            franchisee_id=franchisee_id,
            fee_type=FeeType.ROYALTY,
            period=period,
            base_amount_fen=total_revenue_fen,
            rate=f.royalty_rate,
            amount_fen=royalty_fen,
        ))
        # 管理费
        fees.append(FranchiseFee(
            franchisee_id=franchisee_id,
            fee_type=FeeType.MANAGEMENT,
            period=period,
            amount_fen=f.management_fee_fen,
        ))
        # 营销基金
        marketing_fen = int(total_revenue_fen * f.marketing_rate)
        fees.append(FranchiseFee(
            franchisee_id=franchisee_id,
            fee_type=FeeType.MARKETING,
            period=period,
            base_amount_fen=total_revenue_fen,
            rate=f.marketing_rate,
            amount_fen=marketing_fen,
        ))

        self._fees[franchisee_id].extend(fees)
        total_fen = sum(fee.amount_fen for fee in fees)
        logger.info("计算加盟费用", franchisee=f.name, period=period,
                     total_yuan=round(total_fen / 100, 2))
        return fees

    def get_kpi_dashboard(self, franchisee_id: str) -> Dict:
        """获取加盟商KPI面板"""
        f = self._get_franchisee(franchisee_id)

        # 汇总费用
        fees = self._fees.get(franchisee_id, [])
        total_fees_fen = sum(fee.amount_fen for fee in fees)
        paid_fen = sum(fee.amount_fen for fee in fees if fee.paid)
        unpaid_fen = total_fees_fen - paid_fen

        # 汇总营业额
        total_revenue_fen = 0
        for sid in f.store_ids:
            for period_rev in self._store_revenue.get(sid, {}).values():
                total_revenue_fen += period_rev

        return {
            "franchisee_id": franchisee_id,
            "name": f.name,
            "status": f.status.value,
            "store_count": len(f.store_ids),
            "total_revenue_fen": total_revenue_fen,
            "total_revenue_yuan": round(total_revenue_fen / 100, 2),
            "total_fees_fen": total_fees_fen,
            "total_fees_yuan": round(total_fees_fen / 100, 2),
            "paid_fen": paid_fen,
            "paid_yuan": round(paid_fen / 100, 2),
            "unpaid_fen": unpaid_fen,
            "unpaid_yuan": round(unpaid_fen / 100, 2),
            "contract_start": f.contract_start.isoformat() if f.contract_start else None,
            "contract_end": f.contract_end.isoformat() if f.contract_end else None,
        }

    def suspend(self, franchisee_id: str, reason: str = "") -> Franchisee:
        """暂停加盟商"""
        f = self._get_franchisee(franchisee_id)
        if f.status != FranchiseeStatus.ACTIVE:
            raise ValueError(f"加盟商状态不允许暂停: {f.status.value}")
        f.status = FranchiseeStatus.SUSPENDED
        logger.info("暂停加盟商", id=franchisee_id, name=f.name, reason=reason)
        return f

    def reactivate(self, franchisee_id: str) -> Franchisee:
        """恢复加盟商"""
        f = self._get_franchisee(franchisee_id)
        if f.status != FranchiseeStatus.SUSPENDED:
            raise ValueError("加盟商未暂停")
        f.status = FranchiseeStatus.ACTIVE
        return f

    def terminate(self, franchisee_id: str, reason: str = "") -> Franchisee:
        """终止加盟商"""
        f = self._get_franchisee(franchisee_id)
        if f.status == FranchiseeStatus.TERMINATED:
            raise ValueError("加盟商已终止")
        f.status = FranchiseeStatus.TERMINATED
        logger.info("终止加盟商", id=franchisee_id, name=f.name, reason=reason)
        return f

    def _get_franchisee(self, franchisee_id: str) -> Franchisee:
        if franchisee_id not in self._franchisees:
            raise ValueError(f"加盟商不存在: {franchisee_id}")
        return self._franchisees[franchisee_id]
