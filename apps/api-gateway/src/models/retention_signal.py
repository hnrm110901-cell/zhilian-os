"""
RetentionSignal — 离职风险预测信号

基于 Assignment 维度的离职风险评估：
- risk_score: 0-100 离职概率
- risk_factors: 结构化风险因子（如考勤异常、绩效下降、薪资竞争力）
- intervention_status: 干预状态跟踪

HRAgent v2 (M3) 的 PredictionNode 产出此数据。
"""
import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSON
from src.models.base import Base, TimestampMixin


class RetentionSignal(Base, TimestampMixin):
    __tablename__ = "retention_signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 关联任职关系
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("assignments.id"), nullable=False, index=True,
                           comment="关联 Assignment")

    # 风险评估
    risk_score = Column(Integer, nullable=False, comment="离职风险分 0-100")
    risk_level = Column(String(20), comment="风险等级: low/medium/high/critical")
    risk_factors = Column(JSON, default=dict, comment="""
        风险因子: {
            attendance_anomaly: 0.3,     // 考勤异常指数
            performance_decline: 0.2,    // 绩效下降
            salary_competitiveness: -0.1,// 薪资竞争力（负=低于市场）
            tenure_risk: 0.15,           // 任期风险（新员工3月/老员工倦怠）
            team_friction: 0.1,          // 团队摩擦
            workload_pressure: 0.25      // 工作强度
        }
    """)

    # 干预跟踪
    intervention_status = Column(String(20), default="none",
                                  comment="干预状态: none/planned/in_progress/completed/ignored")
    intervention_plan = Column(JSON, nullable=True, comment="干预方案 {action, expected_effect, deadline}")
    intervened_by = Column(UUID(as_uuid=True), nullable=True, comment="干预人")
    intervened_at = Column(DateTime, comment="干预时间")

    # 预测模型信息
    model_version = Column(String(50), comment="使用的模型版本")
    computed_at = Column(DateTime, nullable=False, comment="计算时间")
    valid_until = Column(DateTime, comment="预测有效期")

    # 结果追踪
    actual_outcome = Column(String(20), comment="实际结果: stayed/resigned/terminated")
    outcome_date = Column(DateTime, comment="结果日期")
    prediction_accuracy = Column(Float, comment="预测准确度（事后校准）")

    def __repr__(self):
        return f"<RetentionSignal assignment={self.assignment_id} risk={self.risk_score}>"
