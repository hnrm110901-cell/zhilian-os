"""
DataQualityCheckRecord — 数据质量校验记录表
保证经营数据清晰准确。
"""
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid
from .base import Base, TimestampMixin


class DataQualityCheckRecord(Base, TimestampMixin):
    """数据质量校验记录表"""
    __tablename__ = "data_quality_check_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(64), nullable=False, index=True)
    biz_date = Column(String(10), nullable=False, index=True)
    check_type = Column(String(64), nullable=False)         # 校验类型
    check_code = Column(String(64), nullable=False)         # 校验编码
    check_name = Column(String(128), nullable=False)
    check_result = Column(String(16), nullable=False)       # pass/warn/fail
    expected_value = Column(String(128))
    actual_value = Column(String(128))
    error_message = Column(Text)
    source_system = Column(String(64))
    # 处理状态：pending/resolved/ignored
    resolved_status = Column(String(32), default="pending", nullable=False)
    resolved_by = Column(String(64))
    resolved_at = Column(DateTime)

    def __repr__(self):
        return f"<DataQualityCheckRecord(store_id='{self.store_id}', check='{self.check_code}', result='{self.check_result}')>"
