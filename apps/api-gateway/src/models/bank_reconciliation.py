"""银行流水对账模型 — 银行流水记录 / 对账批次"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class BankStatement(Base, TimestampMixin):
    """银行流水记录（从银行账单导入）"""

    __tablename__ = "bank_statements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)

    # 银行信息
    bank_name = Column(String(50), nullable=False, index=True)  # 银行名称
    account_number = Column(String(30), nullable=False)  # 账号后4位(脱敏)

    # 交易信息
    transaction_date = Column(Date, nullable=False, index=True)
    transaction_type = Column(String(20), nullable=False)  # "credit"(收入) / "debit"(支出)
    amount_fen = Column(Integer, nullable=False)  # 金额(分)
    counterparty = Column(String(100), nullable=True)  # 对方户名
    reference_number = Column(String(50), nullable=True)  # 交易流水号
    description = Column(String(200), nullable=True)  # 摘要

    # 分类与匹配
    category = Column(String(30), nullable=True)  # sales/purchase/salary/rent/tax/other
    is_matched = Column(Boolean, nullable=False, default=False)
    matched_order_id = Column(String(100), nullable=True)  # 匹配的内部单据ID
    import_batch_id = Column(String(50), nullable=True, index=True)  # 导入批次

    def __repr__(self):
        return (
            f"<BankStatement(ref='{self.reference_number}', "
            f"bank='{self.bank_name}', amount={self.amount_fen}, "
            f"type='{self.transaction_type}')>"
        )


class BankReconciliationBatch(Base, TimestampMixin):
    """银行对账批次 — 每次执行对账生成一条"""

    __tablename__ = "bank_reconciliation_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    bank_name = Column(String(50), nullable=False)

    # 对账周期
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # 状态
    status = Column(String(20), nullable=False, default="pending")  # pending/processing/completed/error

    # 汇总
    total_credit_fen = Column(Integer, nullable=False, default=0)  # 收入合计(分)
    total_debit_fen = Column(Integer, nullable=False, default=0)  # 支出合计(分)
    matched_count = Column(Integer, nullable=False, default=0)
    unmatched_count = Column(Integer, nullable=False, default=0)

    # 余额对比
    bank_balance_fen = Column(Integer, nullable=True)  # 银行余额(分)
    system_balance_fen = Column(Integer, nullable=True)  # 系统余额(分)
    diff_fen = Column(Integer, nullable=False, default=0)  # 差异(分)

    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return (
            f"<BankReconciliationBatch(bank='{self.bank_name}', "
            f"period='{self.period_start}~{self.period_end}', "
            f"status='{self.status}')>"
        )
