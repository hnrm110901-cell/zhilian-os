"""
EmployeeGrowthTrace — 员工成长溯源时间轴
记录员工完整职业发展历程，支持里程碑标记与KPI快照。
"""
from sqlalchemy import Column, String, Integer, Boolean, Text, Date, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from .base import Base, TimestampMixin


class EmployeeGrowthTrace(Base, TimestampMixin):
    """员工成长溯源时间轴表"""
    __tablename__ = "employee_growth_traces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 员工信息
    employee_id = Column(String(64), nullable=False, index=True)
    employee_name = Column(String(128))
    store_id = Column(String(64), index=True)

    # 事件类型：hire/transfer/promote/train_complete/assess/reward/penalty/resign/job_change
    trace_type = Column(String(32), nullable=False, index=True)
    trace_date = Column(Date, nullable=False, index=True)

    # 事件内容
    event_title = Column(String(256), nullable=False)
    event_detail = Column(Text)

    # 岗位变更（可选）
    from_job_code = Column(String(64))   # 变更前岗位
    from_job_name = Column(String(128))
    to_job_code = Column(String(64))     # 变更后岗位
    to_job_name = Column(String(128))

    # 评估数据
    kpi_snapshot = Column(JSON)           # 事件发生时KPI快照 {metric: value}
    assessment_score = Column(Integer)    # 考核分数（可选）
    assessor_id = Column(String(64))      # 评估人

    # 附件和标记
    attachments = Column(JSON)            # 附件列表
    is_milestone = Column(Boolean, default=False)   # 里程碑节点（晋升/转正等）

    created_by = Column(String(64))

    def __repr__(self):
        return f"<EmployeeGrowthTrace(employee_id='{self.employee_id}', trace_type='{self.trace_type}', trace_date={self.trace_date})>"
