"""经营快照时序模型 — BSC四维度日/周/月/季聚合

每行 = 一个门店在一个时间粒度下的完整经营画像。
daily由Celery定时聚合，weekly/monthly由daily再聚合。
"""

import enum
import uuid

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from .base import Base


class SnapshotPeriodType(str, enum.Enum):
    """快照周期类型"""

    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"


class OperationSnapshot(Base):
    """BSC四维度经营快照 — 门店运营数据时序聚合

    不使用TimestampMixin，有自己的aggregated_at字段。
    """

    __tablename__ = "operation_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    snapshot_date = Column(Date, nullable=False)
    period_type = Column(SAEnum(SnapshotPeriodType), nullable=False)

    # ── 财务维度（单位：分）──────────────────────────────────────
    revenue_fen = Column(BigInteger, default=0)
    cost_material_fen = Column(BigInteger, default=0)  # 食材成本
    cost_labor_fen = Column(BigInteger, default=0)  # 人力成本
    cost_rent_fen = Column(BigInteger, default=0)  # 租金
    cost_utility_fen = Column(BigInteger, default=0)  # 水电燃气
    cost_platform_fee_fen = Column(BigInteger, default=0)  # 平台佣金
    cost_other_fen = Column(BigInteger, default=0)  # 其他支出
    gross_profit_fen = Column(BigInteger, default=0)  # 毛利
    net_profit_fen = Column(BigInteger, default=0)  # 净利

    # ── 客户维度 ─────────────────────────────────────────────
    customer_count = Column(Integer, default=0)
    new_customer_count = Column(Integer, default=0)
    returning_customer_count = Column(Integer, default=0)
    avg_ticket_fen = Column(BigInteger, default=0)  # 客单价（分）
    table_turnover_rate = Column(Numeric(5, 2), nullable=True)  # 翻台率
    nps_score = Column(Numeric(4, 1), nullable=True)  # NPS 净推荐值
    complaint_count = Column(Integer, default=0)
    online_rating_avg = Column(Numeric(3, 1), nullable=True)  # 线上平均评分

    # ── 流程维度 ─────────────────────────────────────────────
    order_count = Column(Integer, default=0)
    dine_in_order_count = Column(Integer, default=0)
    takeout_order_count = Column(Integer, default=0)
    delivery_order_count = Column(Integer, default=0)
    avg_serve_time_sec = Column(Integer, nullable=True)  # 平均出餐时间（秒）
    waste_value_fen = Column(BigInteger, default=0)  # 损耗金额（分）
    waste_rate_pct = Column(Numeric(5, 2), nullable=True)  # 损耗率%
    procurement_accuracy_pct = Column(Numeric(5, 2), nullable=True)  # 采购准确率%

    # ── 学习维度 ─────────────────────────────────────────────
    employee_count = Column(Integer, default=0)
    turnover_count = Column(Integer, default=0)  # 离职人数
    training_hours = Column(Numeric(6, 1), default=0)  # 培训学时
    employee_satisfaction = Column(Numeric(4, 1), nullable=True)  # 员工满意度

    # ── 聚合元信息 ────────────────────────────────────────────
    data_completeness_pct = Column(Numeric(5, 2), default=100.00)  # 数据完整度%
    source_record_count = Column(Integer, default=0)  # 源记录数量
    aggregated_at = Column(DateTime(timezone=True), server_default=func.now())  # 聚合时间

    __table_args__ = (
        UniqueConstraint(
            "brand_id", "store_id", "snapshot_date", "period_type",
            name="uq_os_brand_store_date_period",
        ),
        Index("idx_os_store_period_date", "store_id", "period_type", snapshot_date.desc()),
        Index("idx_os_brand_period_date", "brand_id", "period_type", snapshot_date.desc()),
    )

    def to_summary_dict(self) -> dict:
        """返回关键指标的元版本（金额从分转元），供BFF/前端直接消费"""
        return {
            "store_id": self.store_id,
            "snapshot_date": str(self.snapshot_date) if self.snapshot_date else None,
            "period_type": self.period_type.value if self.period_type else None,
            # 财务（元）
            "revenue_yuan": round(self.revenue_fen / 100, 2) if self.revenue_fen else 0,
            "gross_profit_yuan": round(self.gross_profit_fen / 100, 2) if self.gross_profit_fen else 0,
            "net_profit_yuan": round(self.net_profit_fen / 100, 2) if self.net_profit_fen else 0,
            "cost_material_yuan": round(self.cost_material_fen / 100, 2) if self.cost_material_fen else 0,
            "cost_labor_yuan": round(self.cost_labor_fen / 100, 2) if self.cost_labor_fen else 0,
            "avg_ticket_yuan": round(self.avg_ticket_fen / 100, 2) if self.avg_ticket_fen else 0,
            # 客户
            "customer_count": self.customer_count or 0,
            "new_customer_count": self.new_customer_count or 0,
            "returning_customer_count": self.returning_customer_count or 0,
            "table_turnover_rate": float(self.table_turnover_rate) if self.table_turnover_rate else None,
            "nps_score": float(self.nps_score) if self.nps_score else None,
            "online_rating_avg": float(self.online_rating_avg) if self.online_rating_avg else None,
            # 流程
            "order_count": self.order_count or 0,
            "waste_value_yuan": round(self.waste_value_fen / 100, 2) if self.waste_value_fen else 0,
            "waste_rate_pct": float(self.waste_rate_pct) if self.waste_rate_pct else None,
            # 学习
            "employee_count": self.employee_count or 0,
            "turnover_count": self.turnover_count or 0,
            "training_hours": float(self.training_hours) if self.training_hours else 0,
            # 元信息
            "data_completeness_pct": float(self.data_completeness_pct) if self.data_completeness_pct else 100.0,
        }

    def __repr__(self):
        return (
            f"<OperationSnapshot(store='{self.store_id}', date='{self.snapshot_date}', "
            f"period='{self.period_type}', revenue_fen={self.revenue_fen})>"
        )
