"""
日清日结 — DailyClosingReport 模型
每日自动对账汇总：营收、成本、毛利、支付/银行/发票对账状态、异常检测
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, Date, DateTime, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class DailyClosingReport(Base, TimestampMixin):
    """日结报告 — 每个门店每天一条"""

    __tablename__ = "daily_closing_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=True, index=True)  # NULL 表示品牌汇总

    # 日期
    closing_date = Column(Date, nullable=False, index=True)

    # 状态：pending / processing / completed / warning / error
    status = Column(String(20), nullable=False, default="pending")

    # ── 营收（单位：分）──────────────────────────────────────────────
    total_revenue_fen = Column(Integer, nullable=False, default=0)  # POS + 外卖 + 团购
    total_cost_fen = Column(Integer, nullable=False, default=0)  # 采购 + 损耗 + 人力
    gross_profit_fen = Column(Integer, nullable=False, default=0)  # 营收 - 成本

    # ── 对账状态 ──────────────────────────────────────────────────────
    payment_recon_status = Column(String(20), nullable=False, default="pending")  # matched / has_diff / pending
    bank_recon_status = Column(String(20), nullable=False, default="pending")
    invoice_status = Column(String(20), nullable=False, default="none")  # all_issued / partial / none

    # 三角对账匹配率（%）
    tri_recon_match_rate = Column(Numeric(5, 2), nullable=True)

    # ── 订单统计 ──────────────────────────────────────────────────────
    order_count = Column(Integer, nullable=False, default=0)
    avg_order_fen = Column(Integer, nullable=False, default=0)

    # ── 渠道明细 ──────────────────────────────────────────────────────
    # {dine_in: {revenue_fen, orders}, eleme: {...}, meituan: {...}, douyin: {...}}
    channel_breakdown = Column(JSON, nullable=False, default=dict)

    # ── 异常列表 ──────────────────────────────────────────────────────
    # [{type, description, amount_fen, severity}]
    anomalies = Column(JSON, nullable=True)

    # 完成时间
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_closing_brand_date", "brand_id", "closing_date"),
        Index("idx_closing_brand_status", "brand_id", "status"),
        Index("idx_closing_store_date", "store_id", "closing_date"),
    )

    def __repr__(self):
        return f"<DailyClosingReport(brand='{self.brand_id}', " f"date='{self.closing_date}', status='{self.status}')>"
