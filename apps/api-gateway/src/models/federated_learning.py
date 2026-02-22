"""
联邦学习数据模型
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .base import Base


class RoundStatus(str, enum.Enum):
    INITIALIZED = "initialized"
    COLLECTING = "collecting"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"


class FLTrainingRound(Base):
    """联邦学习训练轮次表"""
    __tablename__ = "fl_training_rounds"

    id = Column(String(36), primary_key=True)
    model_type = Column(String(50), nullable=False, index=True)
    status = Column(SQLEnum(RoundStatus), default=RoundStatus.INITIALIZED, index=True)
    config = Column(JSON, comment="训练配置")
    global_model_parameters = Column(JSON, comment="聚合后的全局模型参数")
    aggregation_method = Column(String(50))
    num_participating_stores = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)

    uploads = relationship("FLModelUpload", back_populates="round")


class FLModelUpload(Base):
    """门店上传的本地模型参数表"""
    __tablename__ = "fl_model_uploads"

    id = Column(String(36), primary_key=True)
    round_id = Column(String(36), ForeignKey("fl_training_rounds.id"), nullable=False, index=True)
    store_id = Column(String(36), ForeignKey("stores.id"), nullable=False, index=True)
    model_parameters = Column(JSON, comment="模型参数（序列化后）")
    training_metrics = Column(JSON, comment="训练指标")
    training_samples = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    round = relationship("FLTrainingRound", back_populates="uploads")
    store = relationship("Store", backref="fl_uploads")
