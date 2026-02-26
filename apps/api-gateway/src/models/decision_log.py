"""
决策日志模型
用于记录AI Agent的决策建议、店长的实际决策和最终结果
支持Human-in-the-loop和联邦学习
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Enum as SQLEnum, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .base import Base


class DecisionType(str, enum.Enum):
    """决策类型"""
    REVENUE_ANOMALY = "revenue_anomaly"  # 营收异常
    INVENTORY_ALERT = "inventory_alert"  # 库存预警
    PURCHASE_SUGGESTION = "purchase_suggestion"  # 采购建议
    SCHEDULE_OPTIMIZATION = "schedule_optimization"  # 排班优化
    MENU_PRICING = "menu_pricing"  # 菜品定价
    ORDER_ANOMALY = "order_anomaly"  # 订单异常
    KPI_IMPROVEMENT = "kpi_improvement"  # KPI改进
    COST_OPTIMIZATION = "cost_optimization"  # 成本优化


class DecisionStatus(str, enum.Enum):
    """决策状态"""
    PENDING = "pending"  # 待审批
    APPROVED = "approved"  # 已批准
    REJECTED = "rejected"  # 已拒绝
    MODIFIED = "modified"  # 已修改
    EXECUTED = "executed"  # 已执行
    CANCELLED = "cancelled"  # 已取消


class DecisionOutcome(str, enum.Enum):
    """决策结果"""
    SUCCESS = "success"  # 成功
    FAILURE = "failure"  # 失败
    PARTIAL = "partial"  # 部分成功
    PENDING = "pending"  # 待评估


class DecisionLog(Base):
    """决策日志表"""
    __tablename__ = "decision_logs"

    id = Column(String(36), primary_key=True)

    # 决策基本信息
    decision_type = Column(SQLEnum(DecisionType, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True, comment="决策类型")
    agent_type = Column(String(50), nullable=False, index=True, comment="Agent类型")
    agent_method = Column(String(100), nullable=False, comment="Agent方法名")

    # 门店信息
    store_id = Column(String(36), ForeignKey("stores.id"), nullable=False, index=True, comment="门店ID")
    store = relationship("Store", backref="decision_logs")

    # AI建议
    ai_suggestion = Column(JSON, nullable=False, comment="AI建议内容")
    ai_confidence = Column(Float, comment="AI置信度 (0-1)")
    ai_reasoning = Column(Text, comment="AI推理过程")
    ai_alternatives = Column(JSON, comment="AI备选方案")

    # 店长决策
    manager_id = Column(String(36), ForeignKey("users.id"), index=True, comment="店长ID")
    manager_decision = Column(JSON, comment="店长实际决策")
    manager_feedback = Column(Text, comment="店长反馈意见")
    decision_status = Column(SQLEnum(DecisionStatus, values_callable=lambda x: [e.value for e in x]), default=DecisionStatus.PENDING, index=True, comment="决策状态")

    # 决策时间
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    approved_at = Column(DateTime, comment="批准时间")
    executed_at = Column(DateTime, comment="执行时间")

    # 执行结果
    outcome = Column(SQLEnum(DecisionOutcome, values_callable=lambda x: [e.value for e in x]), comment="决策结果")
    actual_result = Column(JSON, comment="实际结果数据")
    expected_result = Column(JSON, comment="预期结果数据")
    result_deviation = Column(Float, comment="结果偏差 (%)")

    # 业务指标
    business_impact = Column(JSON, comment="业务影响指标")
    cost_impact = Column(Numeric(12, 2), comment="成本影响 (元)")
    revenue_impact = Column(Numeric(12, 2), comment="营收影响 (元)")

    # 学习数据
    is_training_data = Column(Integer, default=0, comment="是否用于训练 (0=否, 1=是)")
    trust_score = Column(Float, comment="信任度评分 (0-100)")

    # 上下文信息
    context_data = Column(JSON, comment="决策上下文数据")
    rag_context = Column(JSON, comment="RAG检索上下文")

    # 审计信息
    approval_chain = Column(JSON, comment="审批链")
    notes = Column(Text, comment="备注")

    def __repr__(self):
        return f"<DecisionLog(id={self.id}, type={self.decision_type}, status={self.decision_status})>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "decision_type": self.decision_type.value if self.decision_type else None,
            "agent_type": self.agent_type,
            "agent_method": self.agent_method,
            "store_id": self.store_id,
            "ai_suggestion": self.ai_suggestion,
            "ai_confidence": self.ai_confidence,
            "ai_reasoning": self.ai_reasoning,
            "ai_alternatives": self.ai_alternatives,
            "manager_id": self.manager_id,
            "manager_decision": self.manager_decision,
            "manager_feedback": self.manager_feedback,
            "decision_status": self.decision_status.value if self.decision_status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "outcome": self.outcome.value if self.outcome else None,
            "actual_result": self.actual_result,
            "expected_result": self.expected_result,
            "result_deviation": self.result_deviation,
            "business_impact": self.business_impact,
            "cost_impact": self.cost_impact,
            "revenue_impact": self.revenue_impact,
            "is_training_data": self.is_training_data,
            "trust_score": self.trust_score,
            "context_data": self.context_data,
            "rag_context": self.rag_context,
            "approval_chain": self.approval_chain,
            "notes": self.notes
        }
