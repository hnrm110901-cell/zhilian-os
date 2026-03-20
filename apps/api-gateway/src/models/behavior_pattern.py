"""
BehaviorPattern — 行为模型（越用越准）

从员工行为数据中挖掘的模式：
- 高绩效员工的行为特征
- 离职倾向的行为信号
- 服务质量关联的操作模式

org_scope 决定模型范围：品牌级(brand) or 全网级(global)
"""
import uuid
from sqlalchemy import Column, String, Float, Integer, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSON
from src.models.base import Base, TimestampMixin


class BehaviorPattern(Base, TimestampMixin):
    __tablename__ = "behavior_patterns"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 模式类型
    pattern_type = Column(String(50), nullable=False, index=True,
                          comment="模式类型: high_performer/churn_risk/service_quality/efficiency/safety")
    name = Column(String(200), comment="模式名称")
    description = Column(Text, comment="模式描述")

    # 特征向量
    feature_vector = Column(JSON, nullable=False, default=dict,
                            comment="特征向量 {feature_name: weight, ...}")
    feature_names = Column(JSON, default=list, comment="特征名称列表")

    # 模型效果
    outcome = Column(String(100), comment="预测结果标签")
    confidence = Column(Float, default=0.0, comment="模型置信度 0-1")
    precision_score = Column(Float, comment="精确率")
    recall_score = Column(Float, comment="召回率")

    # 训练数据
    sample_size = Column(Integer, default=0, comment="训练样本数")
    training_period_days = Column(Integer, comment="训练数据跨度(天)")
    last_trained_at = Column(DateTime, comment="最后训练时间")

    # 适用范围
    org_scope = Column(String(20), default="brand", index=True,
                       comment="范围: brand(品牌级)/global(全网)")
    brand_id = Column(String(50), nullable=True, index=True,
                      comment="品牌ID（org_scope=brand时）")
    applicable_positions = Column(JSON, default=list, comment="适用岗位")

    # 版本
    version = Column(Integer, default=1, comment="模型版本")
    is_active = Column(Boolean, default=True, index=True, comment="是否启用")
    superseded_by = Column(UUID(as_uuid=True), nullable=True, comment="被哪个新版本替代")

    def __repr__(self):
        return f"<BehaviorPattern {self.pattern_type} v{self.version} ({self.confidence:.2f})>"
