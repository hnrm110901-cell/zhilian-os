"""
员工指标记录模型（P2 绩效引擎）

每条记录代表某员工在某门店某周期某指标的实际值 + 目标值 + 达成率。
数据来源：PerformanceComputeService 从 orders / order_items / waste_events 聚合写入。
"""
import uuid
from sqlalchemy import Column, String, Date, Numeric, UniqueConstraint, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class EmployeeMetricRecord(Base, TimestampMixin):
    """员工绩效指标记录"""

    __tablename__ = "employee_metric_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 关联员工与门店
    employee_id = Column(String(50), ForeignKey("employees.id"), nullable=False, index=True)
    store_id    = Column(String(50), ForeignKey("stores.id"),    nullable=False, index=True)

    # 指标标识（与 DEFAULT_ROLE_CONFIG metrics[].id 对应）
    metric_id = Column(String(50), nullable=False)

    # 统计周期
    period_start = Column(Date, nullable=False)
    period_end   = Column(Date, nullable=False)

    # 指标值（分）
    value  = Column(Numeric(12, 4), nullable=True)
    target = Column(Numeric(12, 4), nullable=True)

    # 达成率 = value / target，范围 0.0000–2.0000（允许超额）
    achievement_rate = Column(Numeric(6, 4), nullable=True)

    # 数据来源标记，便于追溯
    data_source = Column(String(100), nullable=True)  # 'orders' / 'waste_events' / 'order_items'

    __table_args__ = (
        UniqueConstraint("employee_id", "metric_id", "period_start",
                         name="uq_emp_metric_period"),
        Index("idx_emp_metric_store_period", "store_id", "period_start"),
    )

    def __repr__(self):
        return (
            f"<EmployeeMetricRecord(emp={self.employee_id}, metric={self.metric_id}, "
            f"period={self.period_start}, value={self.value})>"
        )
