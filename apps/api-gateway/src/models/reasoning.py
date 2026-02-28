"""
L4 推理层 ORM 模型

ReasoningReport — 维度化推理报告（每日 × 维度 × 门店）

设计：
  - 每次对门店某维度执行推理后，将结论持久化为一条 ReasoningReport
  - 支持 upsert（同日同维度只保留最新一份）
  - 可追溯触发规则、证据链、同伴组百分位、KPI 快照
  - is_actioned 标记人工已处理（Human-in-the-Loop 闭环）
"""

import uuid
import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Date, Float, Index, String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from src.models.base import Base, TimestampMixin


class SeverityLevel(str, enum.Enum):
    P1 = "P1"   # 立即处理（置信度 ≥ 0.80）
    P2 = "P2"   # 本日内处理（置信度 ≥ 0.65）
    P3 = "P3"   # 本周内处理（置信度 ≥ 0.50）
    OK = "OK"   # 无显著异常


class ReasoningDimension(str, enum.Enum):
    WASTE       = "waste"
    EFFICIENCY  = "efficiency"
    QUALITY     = "quality"
    COST        = "cost"
    INVENTORY   = "inventory"
    CROSS_STORE = "cross_store"


class ReasoningReport(Base, TimestampMixin):
    """
    维度化推理报告

    每条记录描述「某门店在某日某维度的推理结论」，例如：
      store_id=STORE001 / report_date=2026-02-28 / dimension=waste /
      severity=P2 / root_cause=staff_error / confidence=0.73
    """
    __tablename__ = "reasoning_reports"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id    = Column(String(50),  nullable=False)
    report_date = Column(Date(),      nullable=False)
    dimension   = Column(String(30),  nullable=False)   # waste/efficiency/...
    severity    = Column(String(10),  nullable=False, default=SeverityLevel.OK.value)

    # 推理结论
    root_cause           = Column(String(100))
    confidence           = Column(Float())
    evidence_chain       = Column(JSONB())          # List[str]
    triggered_rule_codes = Column(JSONB())          # List[str]
    recommended_actions  = Column(JSONB())          # List[str]

    # 同伴组上下文（来自 L3 cross_store_metrics）
    peer_group      = Column(String(100))
    peer_context    = Column(JSONB())               # {"peer.p25": 0.05, "peer.p50": 0.08, ...}
    peer_percentile = Column(Float())               # 本店在组内百分位 (0-100)

    # KPI 快照（推理时的实际度量值）
    kpi_snapshot = Column(JSONB())                  # {"waste_rate": 0.15, ...}

    # 行动追踪（Human-in-the-Loop 闭环）
    is_actioned = Column(Boolean(), default=False)
    actioned_by = Column(String(100))
    actioned_at = Column(DateTime())

    __table_args__ = (
        UniqueConstraint(
            "store_id", "report_date", "dimension",
            name="uq_reasoning_report_store_date_dim",
        ),
        Index("idx_rr_store_date",  "store_id",    "report_date"),
        Index("idx_rr_severity",    "severity"),
        Index("idx_rr_dimension",   "dimension"),
        Index("idx_rr_report_date", "report_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<ReasoningReport("
            f"{self.store_id}/{self.dimension}/{self.report_date}: {self.severity}"
            f")>"
        )
