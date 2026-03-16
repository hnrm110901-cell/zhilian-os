"""
Onboarding Engine ORM Models
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from .base import Base


class OnboardingTask(Base):
    """每个 store 每个 step 的进度追踪（connect/import/build/diagnose/complete）"""

    __tablename__ = "onboarding_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    step = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    total_records = Column(Integer, nullable=False, default=0)
    imported_records = Column(Integer, nullable=False, default=0)
    failed_records = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    extra = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (Index("ix_onboarding_tasks_store_step", "store_id", "step"),)


class OnboardingImport(Base):
    """每个 store + data_type 的导入状态（唯一约束：store_id + data_type）"""

    __tablename__ = "onboarding_imports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    data_type = Column(String(10), nullable=False)  # D01-D10
    status = Column(String(20), nullable=False, default="pending")  # pending/previewed/imported
    row_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    column_mapping = Column(JSONB, nullable=True)
    imported_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class OnboardingRawData(Base):
    """原始导入行数据（JSONB），供后续 Pipeline 处理后分发到业务表"""

    __tablename__ = "onboarding_raw_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    data_type = Column(String(10), nullable=False)
    row_index = Column(Integer, nullable=False)
    row_data = Column(JSONB, nullable=False)
    is_valid = Column(Boolean, nullable=False, default=True)
    error_msg = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("ix_onboarding_raw_store_dtype", "store_id", "data_type"),)
