"""
Quality Inspection Model
菜品质量检测记录
"""
import enum
import uuid
from sqlalchemy import Column, String, Integer, Float, Text, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class InspectionStatus(str, enum.Enum):
    PASS    = "pass"     # 合格
    FAIL    = "fail"     # 不合格
    REVIEW  = "review"   # 人工复核


class QualityInspection(Base, TimestampMixin):
    """菜品质量检测记录"""

    __tablename__ = "quality_inspections"

    id       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    dish_id  = Column(String(50), index=True)          # 可选，关联菜品
    dish_name = Column(String(100), nullable=False)

    # 图像
    image_url    = Column(Text)                        # 存储路径或 URL
    image_source = Column(String(20), default="upload")  # upload / camera

    # 检测结果
    quality_score = Column(Float, nullable=False)      # 0-100
    status        = Column(Enum(InspectionStatus), nullable=False, index=True)
    issues        = Column(JSON, default=list)          # 问题列表 [{type, description, severity}]
    suggestions   = Column(JSON, default=list)          # 改进建议

    # LLM 原始输出
    llm_reasoning = Column(Text)

    # 元数据
    inspector     = Column(String(50), default="quality_agent")  # agent / staff_id
    pass_threshold = Column(Float, default=75.0)       # 合格分数线

    def __repr__(self):
        return f"<QualityInspection(dish='{self.dish_name}', score={self.quality_score}, status='{self.status}')>"
