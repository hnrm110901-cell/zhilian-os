"""
Member RFM Snapshots — 会员RFM画像快照
"""

import uuid

from sqlalchemy import Column, Date, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class MemberRfmSnapshot(Base, TimestampMixin):
    """RFM画像快照 — 每日/每周定时生成"""

    __tablename__ = "member_rfm_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(String(50), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)
    recency_days = Column(Integer, nullable=False)
    frequency_30d = Column(Integer, nullable=False)
    monetary_30d_fen = Column(Integer, nullable=False)
    r_score = Column(Integer, nullable=False)  # 1-5
    f_score = Column(Integer, nullable=False)  # 1-5
    m_score = Column(Integer, nullable=False)  # 1-5
    rfm_segment = Column(String(30), nullable=False)  # champion/loyal/at_risk/lost/...
    churn_risk_pct = Column(Numeric(5, 2))
    ltv_yuan = Column(Numeric(12, 2))
