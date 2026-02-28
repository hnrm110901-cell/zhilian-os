"""
L2 融合层 — IngredientMapping ORM 模型

规范ID注册中心（Canonical Entity Registry）
每条记录代表一个经过多源融合后确定的"食材原型"。
"""
import uuid
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Float, Boolean, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

from .base import Base


class FusionMethod(str, enum.Enum):
    EXACT_ID    = "exact_id"       # 直接命中 external_id
    EXACT_NAME  = "exact_name"     # 规范名完全匹配
    FUZZY_NAME  = "fuzzy_name"     # 字符 bigram Jaccard 模糊匹配
    MANUAL      = "manual_merge"   # 人工合并
    NEW         = "new_canonical"  # 未匹配，新建规范条目


class IngredientMapping(Base):
    """
    食材规范ID注册中心

    示例：
      canonical_id   = "ING-SEAFOOD-CAOY-001"
      canonical_name = "草鱼片"
      aliases        = ["草鱼", "Grass Carp Slice", "草鱼-1"]
      external_ids   = {"pinzhi": "12345", "meituan": "F789",
                        "tiancai": "M456", "supplier_sku": "SKU-0091"}
      source_costs   = {
          "supplier_invoice": {"cost_fen": 3800, "confidence": 0.95,
                               "updated_at": "2026-02-28T10:00:00"},
          "pinzhi":           {"cost_fen": 3500, "confidence": 0.85,
                               "updated_at": "2026-02-28T09:00:00"},
      }
      canonical_cost_fen = 3710     # 加权均值
      fusion_confidence  = 0.92
    """

    __tablename__ = "ingredient_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── 规范标识 ────────────────────────────────────────────────────────────
    canonical_id   = Column(String(50), nullable=False, unique=True, index=True)
    canonical_name = Column(String(200), nullable=False)
    aliases        = Column(ARRAY(Text), nullable=False, default=list)

    # ── 语义属性 ────────────────────────────────────────────────────────────
    category = Column(String(50))   # meat / seafood / vegetable / dry_goods ...
    unit     = Column(String(20))   # kg / piece / bottle / ml ...

    # ── 多源映射 ────────────────────────────────────────────────────────────
    # {"pinzhi": "123", "meituan": "F789", "tiancai": "M456"}
    external_ids = Column(JSONB, nullable=False, default=dict)

    # ── 多源成本快照 ────────────────────────────────────────────────────────
    # {"supplier_invoice": {"cost_fen": 3800, "confidence": 0.95, "updated_at": "..."}}
    source_costs       = Column(JSONB, nullable=False, default=dict)
    canonical_cost_fen = Column(Integer)   # 加权规范成本（分）

    # ── 融合元数据 ──────────────────────────────────────────────────────────
    fusion_confidence = Column(Float, nullable=False, default=1.0)
    fusion_method     = Column(String(50))   # FusionMethod value
    conflict_flag     = Column(Boolean, nullable=False, default=False)

    # 若本条目由多个 canonical_id 合并而来
    merge_of = Column(ARRAY(String(50)), nullable=False, default=list)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FusionAuditLog(Base):
    """
    融合决策不可变审计日志

    每次 resolve_or_create / merge / conflict 操作均追加一条。
    """

    __tablename__ = "fusion_audit_log"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String(50), nullable=False)   # ingredient / dish / store
    canonical_id = Column(String(50), index=True)
    action       = Column(String(50), nullable=False)
    # create_canonical / alias_to_existing / merge / conflict_detected /
    # manual_override / cost_update / split

    source_system      = Column(String(50), index=True)
    raw_external_id    = Column(String(200))
    raw_name           = Column(String(200))
    matched_canonical_id = Column(String(50))   # alias 时命中的规范 ID
    confidence         = Column(Float)
    fusion_method      = Column(String(50))
    evidence           = Column(JSONB)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_by = Column(String(100))
