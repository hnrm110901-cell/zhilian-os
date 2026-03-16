"""
食材成本真相引擎 — 数据模型

核心表：
1. CostTruthDaily        — 门店日级成本真相快照
2. CostTruthDishDetail   — 菜品级差异明细
3. CostVarianceAttribution — 差异五因归因
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from src.models.base import Base


class VarianceSeverity(str, enum.Enum):
    ok = "ok"
    watch = "watch"  # 1-2pp 偏差，持续观察
    warning = "warning"  # 2-3pp 偏差，需要关注
    critical = "critical"  # >3pp 偏差，立即行动


class AttributionFactor(str, enum.Enum):
    """五因归因"""

    price_change = "price_change"  # 采购单价变动
    usage_overrun = "usage_overrun"  # 用量超标（BOM偏差）
    waste_loss = "waste_loss"  # 损耗（报损/变质/过期）
    yield_variance = "yield_variance"  # 出成率偏差（切配/烹饪）
    mix_shift = "mix_shift"  # 销售结构变化（高成本菜占比上升）


class CostTruthDaily(Base):
    """门店日级成本真相快照"""

    __tablename__ = "cost_truth_daily"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    truth_date = Column(Date, nullable=False, index=True)

    # 核心指标
    revenue_fen = Column(Integer, default=0)  # 当日营收（分）
    theoretical_cost_fen = Column(Integer, default=0)  # BOM理论成本（分）
    actual_cost_fen = Column(Integer, default=0)  # 实际用料成本（分）
    variance_fen = Column(Integer, default=0)  # 差异=实际-理论（分）

    theoretical_pct = Column(Float, default=0.0)  # 理论成本率%
    actual_pct = Column(Float, default=0.0)  # 实际成本率%
    variance_pct = Column(Float, default=0.0)  # 差异百分点

    # 分类
    severity = Column(SAEnum(VarianceSeverity), default=VarianceSeverity.ok)

    # 月度预测
    mtd_actual_pct = Column(Float, nullable=True)  # 本月至今实际成本率
    predicted_eom_pct = Column(Float, nullable=True)  # 预测月末成本率
    target_pct = Column(Float, default=32.0)  # 目标成本率

    # 元数据
    dish_count = Column(Integer, default=0)  # 当日售出菜品种数
    order_count = Column(Integer, default=0)  # 当日订单数
    top_variance_dish = Column(String(100))  # 差异最大的菜品名
    top_variance_yuan = Column(Float, default=0.0)  # 该菜品差异金额¥

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("store_id", "truth_date", name="uq_cost_truth_daily"),
        Index("ix_cost_truth_date_sev", "truth_date", "severity"),
    )


class CostTruthDishDetail(Base):
    """菜品级差异明细"""

    __tablename__ = "cost_truth_dish_detail"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    truth_daily_id = Column(UUID(as_uuid=True), ForeignKey("cost_truth_daily.id"), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)
    truth_date = Column(Date, nullable=False)

    dish_id = Column(String(50), nullable=False, index=True)
    dish_name = Column(String(100))
    sold_qty = Column(Integer, default=0)  # 当日售出份数

    theoretical_cost_fen = Column(Integer, default=0)  # 该菜品理论成本合计（分）
    actual_cost_fen = Column(Integer, default=0)  # 该菜品实际成本合计（分）
    variance_fen = Column(Integer, default=0)  # 差异（分）
    variance_pct = Column(Float, default=0.0)  # 差异率%

    # 前3大偏差食材
    top_ingredients = Column(JSON, default=list)
    # [{"name":"鲈鱼","theoretical_g":350,"actual_g":412,"variance_g":62,"cost_yuan":8.5}]

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("truth_daily_id", "dish_id", name="uq_cost_truth_dish"),)


class CostVarianceAttribution(Base):
    """差异五因归因"""

    __tablename__ = "cost_variance_attribution"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    truth_daily_id = Column(UUID(as_uuid=True), ForeignKey("cost_truth_daily.id"), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    truth_date = Column(Date, nullable=False)

    factor = Column(SAEnum(AttributionFactor), nullable=False)
    contribution_fen = Column(Integer, default=0)  # 该因素贡献的差异金额（分）
    contribution_pct = Column(Float, default=0.0)  # 占总差异的比例%
    description = Column(Text)  # 人可读描述
    action = Column(Text)  # 建议动作

    # 明细（JSON格式，因不同因素结构不同）
    detail = Column(JSON, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("truth_daily_id", "factor", name="uq_cost_attribution_factor"),)
