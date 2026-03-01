"""
L3 跨店知识聚合 ORM 模型

CrossStoreMetric   — 日维度物化指标（物化缓存，加速跨店对比查询）
StoreSimilarityCache — 门店两两相似度（每日重算）
StorePeerGroup     — 同伴组（tier + region 定义）
"""
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Column, String, Float, Boolean, Integer,
    Date, DateTime, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY

from .base import Base


class CrossStoreMetric(Base):
    """
    日维度物化指标

    每条记录 = 某门店在某日某指标的实际值 + 同伴组百分位。

    支持指标 metric_name：
      waste_rate        食材损耗率（损耗量/采购量）
      cost_ratio        食材成本率（食材成本/营业额）
      bom_compliance    BOM 配方合规率（实际用量/标准用量）
      labor_ratio       人力成本率
      revenue_per_seat  每座位日均营业额（元）
      menu_coverage     全品牌菜单覆盖率（%）
    """

    __tablename__ = "cross_store_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    store_id    = Column(String(50),  nullable=False, index=True)
    metric_date = Column(Date,         nullable=False)
    metric_name = Column(String(50),   nullable=False)
    value       = Column(Float,         nullable=False)

    # 同伴组
    peer_group   = Column(String(100))   # "standard_华东"
    peer_count   = Column(Integer)
    peer_p25     = Column(Float)
    peer_p50     = Column(Float)
    peer_p75     = Column(Float)
    peer_p90     = Column(Float)

    percentile_in_peer = Column(Float)   # 本店在组内百分位 (0–100)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("store_id", "metric_date", "metric_name",
                         name="uq_cross_store_metric"),
        Index("ix_csm_store_date",  "store_id",    "metric_date"),
        Index("ix_csm_metric_date", "metric_name", "metric_date"),
    )


class StoreSimilarityCache(Base):
    """
    门店两两相似度缓存

    相似度得分 = 0.40×菜单Jaccard + 0.20×区域匹配 + 0.20×层级匹配 + 0.20×容量比率

    store_a_id < store_b_id（字典序）确保唯一性。
    """

    __tablename__ = "store_similarity_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    store_a_id       = Column(String(50), nullable=False)
    store_b_id       = Column(String(50), nullable=False)
    similarity_score = Column(Float,      nullable=False)  # 0.0 – 1.0

    # 分量（可解释性）
    menu_overlap    = Column(Float)    # 菜单名称 Jaccard
    region_match    = Column(Boolean)
    tier_match      = Column(Boolean)
    capacity_ratio  = Column(Float)    # min(seats)/max(seats)

    computed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("store_a_id", "store_b_id", name="uq_store_similarity"),
        Index("ix_ssc_store_a", "store_a_id"),
        Index("ix_ssc_score",   "similarity_score"),
    )


class StorePeerGroup(Base):
    """
    门店同伴组

    group_key = "{tier}_{region}"，例如 "standard_华东"、"premium_上海"。
    store_ids 为当前属于该组的门店 ID 列表（动态更新）。
    """

    __tablename__ = "store_peer_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    group_key   = Column(String(100), nullable=False, unique=True)
    tier        = Column(String(30))
    region      = Column(String(50))
    store_ids   = Column(ARRAY(String(50)), nullable=False, default=list)
    store_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_spg_tier_region", "tier", "region"),
    )
