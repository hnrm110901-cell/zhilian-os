"""
Schedule Demand Models — 门店岗位编制需求配置
用于智能排班算法的需求侧输入：按日期类型+班次类型配置各岗位最低/最高人数。
"""
import uuid
from sqlalchemy import Column, String, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class StoreStaffingDemand(Base, TimestampMixin):
    """
    门店岗位编制需求配置。
    每条记录描述：某门店在某种日期类型（工作日/周五/周末/节假日）的
    某个班次（早/中/晚）中，某岗位需要的最少和最多人数。

    示例：
      store=S001, position=waiter, day_type=weekend, shift_type=morning
      min_count=3, max_count=5
    """
    __tablename__ = "store_staffing_demands"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), nullable=False, index=True)
    brand_id = Column(String(50), nullable=False)

    # 岗位：waiter/chef/cashier/host/manager/dishwasher
    position = Column(String(50), nullable=False)

    # 日期类型：weekday / friday / weekend / holiday
    day_type = Column(String(20), nullable=False)

    # 班次类型：morning / afternoon / evening
    shift_type = Column(String(20), nullable=False)

    # 人数范围
    min_count = Column(Integer, nullable=False, default=1)
    max_count = Column(Integer, nullable=False, default=3)

    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return (
            f"<StoreStaffingDemand(store='{self.store_id}', "
            f"position='{self.position}', day={self.day_type}, "
            f"shift={self.shift_type}, {self.min_count}~{self.max_count})>"
        )
