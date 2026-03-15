"""
离职结算单 — 最后工资 + 未休年假补偿 + 经济补偿金
Settlement Record for employee separation (resign/dismiss/expire/mutual).
"""
import enum
import uuid
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSON

from .base import Base, TimestampMixin


class SettlementStatus(str, enum.Enum):
    DRAFT = "draft"                      # 草稿（HR计算中）
    PENDING_APPROVAL = "pending_approval"  # 待审批
    APPROVED = "approved"                # 已批准
    PAID = "paid"                        # 已打款
    DISPUTED = "disputed"                # 有争议


class SeparationType(str, enum.Enum):
    RESIGN = "resign"      # 主动离职
    DISMISS = "dismiss"    # 辞退
    EXPIRE = "expire"      # 合同到期不续
    MUTUAL = "mutual"      # 协商解除


class CompensationType(str, enum.Enum):
    NONE = "none"          # 无补偿（主动离职）
    N = "n"                # N倍（合同到期不续 / 协商）
    N_PLUS_1 = "n_plus_1"  # N+1（未提前30天通知的辞退）
    TWO_N = "2n"           # 2N（违法解除）


class SettlementRecord(Base, TimestampMixin):
    """离职结算单"""
    __tablename__ = "settlement_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    brand_id = Column(String(50), nullable=False)
    employee_id = Column(String(50), nullable=False, index=True)
    employee_name = Column(String(100))

    # 离职信息
    separation_type = Column(String(30), nullable=False)   # resign/dismiss/expire/mutual
    last_work_date = Column(Date, nullable=False)
    separation_date = Column(Date, nullable=False)

    # ── 结算明细（全部单位：分） ──
    # 1. 最后月工资（按日折算）
    work_days_last_month = Column(Integer, default=0)
    last_month_salary_fen = Column(Integer, default=0)

    # 2. 未休年假补偿
    unused_annual_days = Column(Integer, default=0)
    annual_leave_compensation_fen = Column(Integer, default=0)
    annual_leave_calc_method = Column(String(20), default="legal")  # legal(3倍) / negotiate(1倍)

    # 3. 经济补偿金（N+1 / N / 2N）
    service_years = Column(Integer, default=0)       # 工龄年数（×10存储，含0.5年精度）
    compensation_months = Column(Integer, default=0)  # N值（×10存储）
    compensation_base_fen = Column(Integer, default=0)  # 月平均工资（前12个月）
    economic_compensation_fen = Column(Integer, default=0)
    compensation_type = Column(String(20), default="none")  # none/n/n_plus_1/2n

    # 4. 其他
    overtime_pay_fen = Column(Integer, default=0)       # 未结加班费
    bonus_fen = Column(Integer, default=0)              # 未发奖金
    deduction_fen = Column(Integer, default=0)          # 扣款（损坏/借支）
    deduction_detail = Column(Text, nullable=True)

    # 5. 汇总
    total_payable_fen = Column(Integer, default=0)      # 应付总额

    # 交接
    handover_items = Column(JSON, default=list)  # [{"item": "工牌", "returned": true}, ...]
    handover_completed = Column(Boolean, default=False)

    # 状态
    status = Column(String(20), default="draft")
    approval_instance_id = Column(UUID(as_uuid=True), nullable=True)

    # 打款
    paid_at = Column(DateTime, nullable=True)
    paid_by = Column(String(100), nullable=True)

    # 计算快照（审计用）
    calculation_snapshot = Column(JSON, nullable=True)

    remark = Column(Text, nullable=True)

    def __repr__(self):
        return (
            f"<SettlementRecord(employee='{self.employee_id}', "
            f"type='{self.separation_type}', total={self.total_payable_fen / 100:.2f}yuan)>"
        )
