"""
决策飞轮记录模型 — Palantir闭环核心
记录每个AI决策建议的完整生命周期：
建议 → 用户响应 → 执行 → 效果追踪 → 模型校准
"""
from __future__ import annotations

import uuid
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, Date, Index
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.sql import func

from src.models.base import Base, TimestampMixin


class DecisionRecord(Base, TimestampMixin):
    """AI决策记录 — 飞轮核心数据表"""
    __tablename__ = "decision_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    store_id = Column(String(50), nullable=False, index=True)

    # ── 决策来源 ──
    decision_type = Column(String(50), nullable=False, index=True)
    # Types: turnover_risk, schedule_optimize, salary_adjust, growth_plan,
    #        compliance_alert, staffing_demand, training_recommend
    module = Column(String(50), nullable=False)  # hr_ai, schedule, payroll, training
    source = Column(String(20), nullable=False, default="ai")  # ai, rules, ai+rules

    # ── 决策目标 ──
    target_type = Column(String(30), nullable=False)  # employee, store, department, position
    target_id = Column(String(100), nullable=True)  # employee_id, store_id, etc.
    target_name = Column(String(100), nullable=True)

    # ── AI建议内容 ──
    recommendation = Column(Text, nullable=False)  # 建议动作描述
    risk_score = Column(Integer, nullable=True)  # 关联风险分 0-100
    confidence = Column(Float, nullable=True)  # AI置信度 0.0-1.0
    predicted_impact_fen = Column(Integer, nullable=True)  # 预测影响（分）
    ai_analysis = Column(Text, nullable=True)  # AI分析文本
    context_snapshot = Column(JSON, nullable=True)  # 决策时的上下文快照

    # ── 用户响应 ──
    user_action = Column(String(20), nullable=True)
    # accept: 采纳执行 | reject: 拒绝 | modify: 修改后执行 | ignore: 未响应 | defer: 延后处理
    user_id = Column(String(50), nullable=True)  # 操作人
    user_action_at = Column(DateTime, nullable=True)
    user_note = Column(Text, nullable=True)  # 用户备注/拒绝原因
    modified_action = Column(Text, nullable=True)  # 修改后的执行动作

    # ── 执行追踪 ──
    executed = Column(Boolean, default=False)
    executed_at = Column(DateTime, nullable=True)
    execution_detail = Column(JSON, nullable=True)  # 执行结果详情

    # ── 效果追踪（30/60/90天） ──
    review_30d_at = Column(DateTime, nullable=True)
    review_30d_result = Column(JSON, nullable=True)
    # {actual_impact_fen, target_status, metric_changes: {attendance_rate, performance_score, ...}}

    review_60d_at = Column(DateTime, nullable=True)
    review_60d_result = Column(JSON, nullable=True)

    review_90d_at = Column(DateTime, nullable=True)
    review_90d_result = Column(JSON, nullable=True)

    # ── 校准 ──
    actual_impact_fen = Column(Integer, nullable=True)  # 实际影响（分）
    deviation_pct = Column(Float, nullable=True)  # 预测vs实际偏差百分比
    calibration_note = Column(Text, nullable=True)  # 校准分析
    model_version = Column(String(50), nullable=True)  # AI模型版本

    # ── 状态 ──
    status = Column(String(20), nullable=False, default="pending")
    # pending → actioned → tracking → reviewed → calibrated

    __table_args__ = (
        Index("idx_dr_store_type_status", "store_id", "decision_type", "status"),
        Index("idx_dr_target", "target_type", "target_id"),
        Index("idx_dr_created", "created_at"),
        Index("idx_dr_review_due", "status", "executed_at"),  # for finding records due for review
    )
