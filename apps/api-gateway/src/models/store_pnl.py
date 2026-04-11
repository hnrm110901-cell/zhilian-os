"""门店损益表 + 盈亏平衡追踪 — 简化版阿米巴数据载体

设计理念（稻盛和夫简化版）：
- 店长只看5个数：营收/食材率/人力率/月累计利润/目标达成率
- 日报T+1自动生成，不需要财务手工
"""

import uuid

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from .base import Base, TimestampMixin


class StorePnl(Base, TimestampMixin):
    """门店日损益表 — 简化版阿米巴，T+1自动聚合"""

    __tablename__ = "store_pnl"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    biz_date = Column(Date, nullable=False, index=True)

    # ── 收入（分）──────────────────────────────────────────────
    revenue_fen = Column(BigInteger, default=0)  # 当日营收
    discount_fen = Column(BigInteger, default=0)  # 折扣/减免
    net_revenue_fen = Column(BigInteger, default=0)  # 实收 = 营收 - 折扣

    # ── 成本（分）──────────────────────────────────────────────
    cost_material_fen = Column(BigInteger, default=0)  # 食材成本
    cost_labor_fen = Column(BigInteger, default=0)  # 人力成本
    cost_rent_fen = Column(BigInteger, default=0)  # 租金（日均分摊）
    cost_utility_fen = Column(BigInteger, default=0)  # 水电燃气
    cost_platform_fee_fen = Column(BigInteger, default=0)  # 平台佣金
    cost_other_fen = Column(BigInteger, default=0)  # 其他支出

    # ── 利润（分）──────────────────────────────────────────────
    gross_profit_fen = Column(BigInteger, default=0)  # 毛利 = 实收 - 食材
    net_profit_fen = Column(BigInteger, default=0)  # 净利 = 实收 - 全部成本

    # ── 率（%）───────────────────────────────────────────────
    material_rate_pct = Column(Numeric(5, 2), nullable=True)  # 食材率 = 食材/实收
    labor_rate_pct = Column(Numeric(5, 2), nullable=True)  # 人力率 = 人力/实收
    gross_margin_pct = Column(Numeric(5, 2), nullable=True)  # 毛利率
    net_margin_pct = Column(Numeric(5, 2), nullable=True)  # 净利率

    # ── 月累计（分）─────────────────────────────────────────────
    mtd_revenue_fen = Column(BigInteger, default=0)  # 本月至今营收
    mtd_net_profit_fen = Column(BigInteger, default=0)  # 本月至今净利
    mtd_target_revenue_fen = Column(BigInteger, default=0)  # 本月营收目标
    mtd_achievement_rate_pct = Column(Numeric(5, 2), nullable=True)  # 目标达成率%

    # ── 运营指标 ─────────────────────────────────────────────
    order_count = Column(Integer, default=0)  # 当日单数
    customer_count = Column(Integer, default=0)  # 当日客数
    avg_ticket_fen = Column(BigInteger, default=0)  # 客单价（分）

    __table_args__ = (
        UniqueConstraint("brand_id", "store_id", "biz_date", name="uq_store_pnl_brand_store_date"),
        Index("idx_store_pnl_store_date", "store_id", biz_date.desc()),
        Index("idx_store_pnl_brand_date", "brand_id", biz_date.desc()),
    )

    @property
    def five_numbers_yuan(self) -> dict:
        """店长看的5个数字 — 金额从分转元

        1. 当日营收
        2. 食材率%
        3. 人力率%
        4. 月累计利润
        5. 目标达成率%
        """
        return {
            "revenue_yuan": round(self.revenue_fen / 100, 2) if self.revenue_fen else 0,
            "material_rate_pct": float(self.material_rate_pct) if self.material_rate_pct else 0,
            "labor_rate_pct": float(self.labor_rate_pct) if self.labor_rate_pct else 0,
            "mtd_net_profit_yuan": round(self.mtd_net_profit_fen / 100, 2) if self.mtd_net_profit_fen else 0,
            "mtd_achievement_rate_pct": float(self.mtd_achievement_rate_pct) if self.mtd_achievement_rate_pct else 0,
        }

    def __repr__(self):
        return (
            f"<StorePnl(store='{self.store_id}', date='{self.biz_date}', "
            f"revenue_fen={self.revenue_fen}, net_profit_fen={self.net_profit_fen})>"
        )


class BreakevenTracker(Base, TimestampMixin):
    """门店盈亏平衡追踪 — 月度盈亏平衡点监控"""

    __tablename__ = "breakeven_tracker"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_month = Column(Integer, nullable=False)  # 1-12

    # ── 固定成本（分/月）────────────────────────────────────────
    fixed_cost_rent_fen = Column(BigInteger, default=0)  # 租金
    fixed_cost_labor_fen = Column(BigInteger, default=0)  # 固定人力（底薪等）
    fixed_cost_depreciation_fen = Column(BigInteger, default=0)  # 设备折旧
    fixed_cost_other_fen = Column(BigInteger, default=0)  # 其他固定
    total_fixed_cost_fen = Column(BigInteger, default=0)  # 固定成本合计

    # ── 变动成本率 ────────────────────────────────────────────
    variable_cost_rate_pct = Column(Numeric(5, 2), nullable=True)  # 变动成本率（食材+变动人力+平台）

    # ── 盈亏平衡点 ────────────────────────────────────────────
    breakeven_revenue_fen = Column(BigInteger, default=0)  # 盈亏平衡日营收（分）
    breakeven_order_count = Column(Integer, nullable=True)  # 盈亏平衡日单数
    breakeven_customer_count = Column(Integer, nullable=True)  # 盈亏平衡日客数

    # ── 实际 vs 盈亏平衡 ──────────────────────────────────────
    actual_avg_daily_revenue_fen = Column(BigInteger, default=0)  # 本月实际日均营收
    safety_margin_pct = Column(Numeric(5, 2), nullable=True)  # 安全边际率% = (实际-盈亏平衡)/实际

    # ── 门店健康评分 ──────────────────────────────────────────
    store_model_score = Column(Numeric(5, 1), nullable=True)  # 综合评分 0~100
    days_above_breakeven = Column(Integer, default=0)  # 本月超盈亏平衡天数
    days_in_month = Column(Integer, default=0)  # 本月已过天数

    # ── 预测 ──────────────────────────────────────────────────
    predicted_eom_profit_fen = Column(BigInteger, nullable=True)  # 预测月末利润
    is_profitable = Column(Boolean, default=False)  # 本月是否盈利

    __table_args__ = (
        UniqueConstraint(
            "brand_id", "store_id", "fiscal_year", "fiscal_month",
            name="uq_breakeven_brand_store_year_month",
        ),
        Index("idx_breakeven_store_year_month", "store_id", "fiscal_year", "fiscal_month"),
    )

    @property
    def is_healthy(self) -> bool:
        """门店健康判定：综合评分 >= 60 为健康"""
        if self.store_model_score is None:
            return False
        return float(self.store_model_score) >= 60

    def __repr__(self):
        return (
            f"<BreakevenTracker(store='{self.store_id}', "
            f"{self.fiscal_year}-{self.fiscal_month:02d}, "
            f"breakeven_fen={self.breakeven_revenue_fen}, healthy={self.is_healthy})>"
        )
