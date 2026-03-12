"""
AgentCollaborationOptimizer 数据模型
多Agent协同总线 — 冲突检测·优先级仲裁·全局优化
"""
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean, Numeric,
    DateTime, Enum as SAEnum, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from src.core.database import Base


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class ConflictTypeEnum(str, enum.Enum):
    resource_contention = "resource_contention"   # 同资源互斥（如：补货 vs 不买）
    financial_constraint = "financial_constraint"  # 财务约束冲突（如：现金流紧张）
    timing_conflict      = "timing_conflict"       # 时间窗口冲突（如：同时推送）
    priority_clash       = "priority_clash"        # 优先级争抢（多Agent同时抢 P0）
    contradictory_action = "contradictory_action"  # 动作互相矛盾（如：促销 vs 控成本）


class ConflictSeverityEnum(str, enum.Enum):
    low    = "low"
    medium = "medium"
    high   = "high"


class ArbitrationMethodEnum(str, enum.Enum):
    priority_wins       = "priority_wins"        # 优先级高的 Agent 胜出
    financial_first     = "financial_first"      # 财务约束优先
    revenue_first       = "revenue_first"        # 营收增长优先
    risk_first          = "risk_first"           # 风险防控优先
    manual_override     = "manual_override"      # 人工仲裁
    merge_recommendations = "merge_recommendations"  # 合并建议（双赢）


class ArbitrationStatusEnum(str, enum.Enum):
    pending   = "pending"
    resolved  = "resolved"
    escalated = "escalated"  # 升级人工处理


class OptimizationTypeEnum(str, enum.Enum):
    dedup        = "dedup"         # 去重（相同建议合并）
    reorder      = "reorder"       # 重排序（综合 ¥ 影响）
    bundle       = "bundle"        # 打包（互补建议合并一条）
    suppress     = "suppress"      # 抑制（低影响建议不推送）


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────

class AgentConflict(Base):
    """Agent 冲突记录"""
    __tablename__ = "agent_conflicts"

    id               = Column(String(36), primary_key=True)
    store_id         = Column(String(64), nullable=False, index=True)
    brand_id         = Column(String(64), nullable=True, index=True)

    # 冲突双方
    agent_a          = Column(String(64), nullable=False)   # 发起方
    agent_b          = Column(String(64), nullable=False)   # 冲突方
    recommendation_a_id = Column(String(36), nullable=True)  # agent_a 的建议 ID
    recommendation_b_id = Column(String(36), nullable=True)

    conflict_type    = Column(SAEnum(ConflictTypeEnum, name="conflict_type_enum"), nullable=False)
    severity         = Column(SAEnum(ConflictSeverityEnum, name="conflict_severity_enum"), nullable=False)
    description      = Column(Text, nullable=False)    # 冲突描述
    conflict_data    = Column(JSONB, nullable=True)    # 双方原始建议 JSON

    # 仲裁
    arbitration_status = Column(SAEnum(ArbitrationStatusEnum, name="arbitration_status_enum"),
                                default=ArbitrationStatusEnum.pending, nullable=False)
    arbitration_method = Column(SAEnum(ArbitrationMethodEnum, name="arbitration_method_enum"), nullable=True)
    winning_agent    = Column(String(64), nullable=True)   # 胜出方（None=合并）
    arbitration_note = Column(Text, nullable=True)
    impact_yuan_saved = Column(Numeric(14, 2), nullable=True)  # 仲裁节省的¥损失

    created_at       = Column(DateTime, default=datetime.utcnow)
    resolved_at      = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_conflict_store_created", "store_id", "created_at"),
        Index("idx_conflict_agents", "agent_a", "agent_b"),
    )


class GlobalOptimizationLog(Base):
    """全局优化日志 — 记录每次多Agent建议聚合优化的结果"""
    __tablename__ = "global_optimization_logs"

    id               = Column(String(36), primary_key=True)
    store_id         = Column(String(64), nullable=False, index=True)
    brand_id         = Column(String(64), nullable=True)

    # 优化前后对比
    input_count      = Column(Integer, nullable=False)      # 原始建议数量
    output_count     = Column(Integer, nullable=False)      # 优化后建议数量
    conflicts_detected = Column(Integer, default=0)
    dedup_count      = Column(Integer, default=0)           # 去重数量
    suppressed_count = Column(Integer, default=0)           # 抑制数量
    bundled_count    = Column(Integer, default=0)           # 打包数量

    # 影响
    total_impact_yuan_before = Column(Numeric(14, 2), nullable=True)
    total_impact_yuan_after  = Column(Numeric(14, 2), nullable=True)

    optimization_details = Column(JSONB, nullable=True)     # 每条操作记录
    ai_insight           = Column(Text, nullable=True)      # AI 总结

    created_at       = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_global_opt_store", "store_id", "created_at"),
    )


class AgentCollabSnapshot(Base):
    """协同快照 — 每日汇总协同总线效果"""
    __tablename__ = "agent_collab_snapshots"

    id                   = Column(String(36), primary_key=True)
    brand_id             = Column(String(64), nullable=False, index=True)
    snapshot_date        = Column(String(10), nullable=False)   # YYYY-MM-DD

    total_conflicts      = Column(Integer, default=0)
    resolved_conflicts   = Column(Integer, default=0)
    escalated_conflicts  = Column(Integer, default=0)
    avg_resolution_minutes = Column(Float, nullable=True)

    # 全局优化效果
    total_recommendations_before = Column(Integer, default=0)
    total_recommendations_after  = Column(Integer, default=0)
    dedup_rate_pct       = Column(Float, nullable=True)          # 去重率%
    conflict_rate_pct    = Column(Float, nullable=True)          # 冲突率%
    total_impact_gain_yuan = Column(Numeric(14, 2), nullable=True)  # 优化带来的额外¥收益

    # 最活跃冲突 Agent 对
    top_conflict_pair    = Column(String(128), nullable=True)    # "agent_a vs agent_b"

    created_at           = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_collab_snap_brand_date", "brand_id", "snapshot_date"),
    )
