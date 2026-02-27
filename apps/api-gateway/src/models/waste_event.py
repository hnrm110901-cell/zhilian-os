"""
损耗事件模型（PostgreSQL 主存储 + Neo4j 本体双写）

设计：
  - WasteEvent 是损耗五步推理的核心输入数据
  - PostgreSQL 存储：业务事实（发生时间、食材、数量、操作人）
  - Neo4j 存储：推理结论（根因、置信度、证据链）
  - 两层通过 event_id 关联

WasteEventType 枚举：
  COOKING_LOSS   - 烹饪过程损耗（出成率偏低）
  SPOILAGE       - 食材变质（超过保质期）
  OVER_PREP      - 过量备餐（备多了用不完）
  DROP_DAMAGE    - 操作失误（摔落/碎裂）
  QUALITY_REJECT - 质检不合格退回
  TRANSFER_LOSS  - 称重/分拣损耗
  UNKNOWN        - 未分类
"""

import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Numeric, Text, Boolean, DateTime,
    ForeignKey, Enum, Integer, Index, Float,
)
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class WasteEventType(str, enum.Enum):
    COOKING_LOSS   = "cooking_loss"
    SPOILAGE       = "spoilage"
    OVER_PREP      = "over_prep"
    DROP_DAMAGE    = "drop_damage"
    QUALITY_REJECT = "quality_reject"
    TRANSFER_LOSS  = "transfer_loss"
    UNKNOWN        = "unknown"


class WasteEventStatus(str, enum.Enum):
    PENDING   = "pending"     # 已记录，待推理
    ANALYZING = "analyzing"   # 推理中
    ANALYZED  = "analyzed"    # 推理完成
    VERIFIED  = "verified"    # 人工验证
    CLOSED    = "closed"      # 已关闭


class WasteEvent(Base, TimestampMixin):
    """
    损耗事件主档（关系型存储）

    一次损耗事件 = 某个门店 + 某道菜/某种食材 + 某个数量 + 某个时间点
    推理结论写回 root_cause / confidence / evidence（来自 WasteReasoningEngine）
    """
    __tablename__ = "waste_events"

    # 主键
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(50), unique=True, nullable=False)  # WE-XXXXXXXX，用于 Neo4j 关联

    # 门店
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False, index=True)

    # 事件类型与状态
    event_type = Column(Enum(WasteEventType), nullable=False, default=WasteEventType.UNKNOWN)
    status = Column(Enum(WasteEventStatus), nullable=False, default=WasteEventStatus.PENDING, index=True)

    # 关联菜品（可选：若是制作中损耗则关联菜品）
    dish_id = Column(UUID(as_uuid=True), ForeignKey("dishes.id"), nullable=True, index=True)

    # 关联食材（必填：损耗的具体食材）
    ingredient_id = Column(String(50), ForeignKey("inventory_items.id"), nullable=False, index=True)

    # 损耗数量
    quantity = Column(Numeric(10, 4), nullable=False)
    unit = Column(String(20), nullable=False)

    # 理论消耗（BOM 计算值，用于差异分析）
    theoretical_qty = Column(Numeric(10, 4), nullable=True)
    variance_qty = Column(Numeric(10, 4), nullable=True)     # actual - theoretical
    variance_pct = Column(Float, nullable=True)               # variance / theoretical

    # 发生时间（用户填写，可能早于创建时间）
    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    # 操作人（归责）
    reported_by = Column(String(100), nullable=True)         # 记录人（员工 ID）
    assigned_staff_id = Column(String(100), nullable=True)   # 疑似责任人

    # 推理结论（由 WasteReasoningEngine 回写）
    root_cause = Column(String(50), nullable=True)           # staff_error / food_quality / ...
    confidence = Column(Float, nullable=True)
    evidence = Column(JSON, nullable=True)                    # 推理证据链快照
    scores = Column(JSON, nullable=True)                      # 各维度评分

    # 处置
    action_taken = Column(Text, nullable=True)               # 实际处置措施
    wechat_action_id = Column(String(50), nullable=True)     # 关联企微 Action ID

    # 图片附件（可选）
    photo_urls = Column(JSON, nullable=True)

    # 备注
    notes = Column(Text, nullable=True)

    # 关联关系
    dish = relationship("Dish", foreign_keys=[dish_id])
    ingredient = relationship("InventoryItem", foreign_keys=[ingredient_id])

    __table_args__ = (
        Index("idx_waste_store_date", "store_id", "occurred_at"),
        Index("idx_waste_type_status", "event_type", "status"),
        Index("idx_waste_dish", "dish_id"),
        Index("idx_waste_ingredient", "ingredient_id"),
    )

    def __repr__(self):
        return (
            f"<WasteEvent(id={self.event_id}, store={self.store_id}, "
            f"qty={self.quantity}{self.unit}, cause={self.root_cause})>"
        )
