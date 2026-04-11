"""经营目标树 — OKR+MBO融合模型

支持集团→品牌→区域→门店级联目标分解，BSC四维度标记。
"""

import enum
import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class BscDimension(str, enum.Enum):
    """BSC平衡计分卡四维度"""

    financial = "financial"
    customer = "customer"
    process = "process"
    learning = "learning"


class ObjectiveLevel(str, enum.Enum):
    """目标层级"""

    company = "company"
    brand = "brand"
    region = "region"
    store = "store"


class PeriodType(str, enum.Enum):
    """周期类型"""

    annual = "annual"
    quarter = "quarter"
    month = "month"


class BusinessObjective(Base, TimestampMixin):
    """经营目标树 — 公司/品牌/区域/门店四级，支持BSC四维度"""

    __tablename__ = "business_objectives"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=True, index=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("business_objectives.id"), nullable=True)

    # 层级与周期
    level = Column(SAEnum(ObjectiveLevel), nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    period_type = Column(SAEnum(PeriodType), nullable=False)
    period_value = Column(Integer, nullable=False, default=0)  # 如Q1=1, M3=3, 年=0

    # 目标内容
    objective_name = Column(String(200), nullable=False)
    metric_code = Column(String(50), nullable=False)  # 关联指标编码
    target_value = Column(BigInteger, nullable=False)  # 目标值
    floor_value = Column(BigInteger, nullable=True)  # 保底值
    stretch_value = Column(BigInteger, nullable=True)  # 挑战值
    actual_value = Column(BigInteger, default=0)  # 实际达成值
    unit = Column(String(20), nullable=False, default="fen")  # fen/pct/count

    # BSC维度
    bsc_dimension = Column(SAEnum(BscDimension), nullable=False, default=BscDimension.financial)

    # 状态与归属
    status = Column(String(20), default="active")  # active/paused/completed/cancelled
    owner_id = Column(UUID(as_uuid=True), nullable=True)  # 负责人

    # 关系
    children = relationship("BusinessObjective", backref="parent", remote_side=[id])
    key_results = relationship(
        "ObjectiveKeyResult", back_populates="objective", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_bo_brand_store_period", "brand_id", "store_id", "fiscal_year", "period_type"),
        Index("idx_bo_parent", "parent_id", postgresql_where="parent_id IS NOT NULL"),
    )

    @property
    def achievement_rate(self) -> float:
        """目标达成率（%）"""
        if not self.target_value:
            return 0.0
        return round(self.actual_value / self.target_value * 100, 2)

    def __repr__(self):
        return (
            f"<BusinessObjective(id='{self.id}', name='{self.objective_name}', "
            f"level='{self.level}', achievement={self.achievement_rate}%)>"
        )


class ObjectiveKeyResult(Base, TimestampMixin):
    """OKR关键结果 — 带权重的可量化结果"""

    __tablename__ = "objective_key_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    objective_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_objectives.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    brand_id = Column(String(50), nullable=False, index=True)

    # KR内容
    kr_name = Column(String(200), nullable=False)
    metric_code = Column(String(50), nullable=False)
    target_value = Column(BigInteger, nullable=False)
    actual_value = Column(BigInteger, default=0)
    unit = Column(String(20), nullable=False, default="fen")
    weight = Column(Numeric(3, 2), default=1.00)  # 权重 0.00~1.00

    # 状态与归属
    status = Column(String(20), default="active")
    owner_id = Column(UUID(as_uuid=True), nullable=True)

    # 关系
    objective = relationship("BusinessObjective", back_populates="key_results")

    __table_args__ = (
        Index("idx_okr_objective", "objective_id"),
    )

    @property
    def achievement_rate(self) -> float:
        """KR达成率（%）"""
        if not self.target_value:
            return 0.0
        return round(self.actual_value / self.target_value * 100, 2)

    def __repr__(self):
        return (
            f"<ObjectiveKeyResult(id='{self.id}', kr='{self.kr_name}', "
            f"weight={self.weight}, achievement={self.achievement_rate}%)>"
        )
