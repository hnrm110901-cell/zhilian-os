"""
Daily Report Model
营业日报模型
"""
from sqlalchemy import Column, String, Integer, Float, Text, Date, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import date

from .base import Base, TimestampMixin


class DailyReport(Base, TimestampMixin):
    """营业日报模型"""

    __tablename__ = "daily_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 基本信息
    store_id = Column(String(50), nullable=False, index=True)
    report_date = Column(Date, nullable=False, index=True)  # 报告日期

    # 营收数据
    total_revenue = Column(Integer, default=0)  # 总营收（分）
    order_count = Column(Integer, default=0)  # 订单数
    customer_count = Column(Integer, default=0)  # 客流量
    avg_order_value = Column(Integer, default=0)  # 客单价（分）

    # 环比数据
    revenue_change_rate = Column(Float, default=0.0)  # 营收环比（%）
    order_change_rate = Column(Float, default=0.0)  # 订单环比（%）
    customer_change_rate = Column(Float, default=0.0)  # 客流环比（%）

    # 运营数据
    inventory_alert_count = Column(Integer, default=0)  # 库存预警数
    task_completion_rate = Column(Float, default=0.0)  # 任务完成率（%）
    service_issue_count = Column(Integer, default=0)  # 服务问题数

    # 详细数据（JSON格式）
    top_dishes = Column(JSON)  # 热销菜品
    peak_hours = Column(JSON)  # 高峰时段
    payment_methods = Column(JSON)  # 支付方式分布

    # 报告内容
    summary = Column(Text)  # 报告摘要
    highlights = Column(JSON)  # 亮点数据
    alerts = Column(JSON)  # 预警信息

    # 推送状态
    is_sent = Column(String(10), default="false")  # 是否已推送
    sent_at = Column(String(50))  # 推送时间

    def __repr__(self):
        return f"<DailyReport(store_id='{self.store_id}', date='{self.report_date}')>"
