"""
StoreDailyMetric — 门店日经营指标
存储某门店某一天的标准化经营指标，是日清日结和周复盘的数据基础。
"""
from sqlalchemy import Column, String, Integer, Boolean, Text, Date, JSON, SmallInteger
from sqlalchemy.dialects.postgresql import UUID
import uuid
from .base import Base, TimestampMixin


class StoreDailyMetric(Base, TimestampMixin):
    """门店日经营数据表"""
    __tablename__ = "store_daily_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 基础信息
    store_id = Column(String(64), nullable=False, index=True)
    store_code = Column(String(64))
    store_name = Column(String(128), nullable=False)
    region_id = Column(String(64))
    region_name = Column(String(128))
    biz_date = Column(Date, nullable=False, index=True)
    day_of_week = Column(SmallInteger)  # 1-7
    weather_code = Column(String(32))
    weather_text = Column(String(64))
    is_holiday = Column(Boolean, default=False, nullable=False)
    holiday_name = Column(String(64))
    business_status = Column(String(32), default="open", nullable=False)  # open/closed/partial_open

    # 销售类字段（金额单位：分）
    total_sales_amount = Column(Integer, default=0)       # 总销售额
    actual_receipts_amount = Column(Integer, default=0)   # 实收金额
    dine_in_sales_amount = Column(Integer, default=0)     # 堂食收入
    delivery_sales_amount = Column(Integer, default=0)    # 外卖收入
    food_sales_amount = Column(Integer, default=0)        # 菜品收入
    beverage_sales_amount = Column(Integer, default=0)    # 酒水收入
    other_sales_amount = Column(Integer, default=0)       # 其他收入
    order_count = Column(Integer, default=0)
    table_count = Column(Integer, default=0)
    guest_count = Column(Integer, default=0)
    avg_order_price = Column(Integer, default=0)          # 客单价（分）
    table_turnover_rate = Column(Integer, default=0)      # 翻台率×10000（存4位小数）

    # 成本类字段（金额单位：分）
    total_cost_amount = Column(Integer, default=0)
    food_cost_amount = Column(Integer, default=0)         # 菜品成本
    beverage_cost_amount = Column(Integer, default=0)     # 酒水成本
    other_cost_amount = Column(Integer, default=0)
    loss_cost_amount = Column(Integer, default=0)         # 报损成本
    staff_meal_cost_amount = Column(Integer, default=0)   # 员工餐成本
    gift_cost_amount = Column(Integer, default=0)         # 赠送成本
    tasting_cost_amount = Column(Integer, default=0)      # 试吃成本
    inbound_amount = Column(Integer, default=0)           # 当日入库金额
    issue_amount = Column(Integer, default=0)             # 当日领料金额
    consumed_cost_amount = Column(Integer, default=0)     # 当日耗用成本

    # 费用类字段（金额单位：分）
    labor_cost_amount = Column(Integer, default=0)        # 人工费
    rent_cost_amount = Column(Integer, default=0)         # 租金
    water_cost_amount = Column(Integer, default=0)        # 水费
    electricity_cost_amount = Column(Integer, default=0)  # 电费
    gas_cost_amount = Column(Integer, default=0)          # 燃气费
    platform_service_fee_amount = Column(Integer, default=0)  # 平台服务费
    material_cost_amount = Column(Integer, default=0)     # 物料消耗
    marketing_cost_amount = Column(Integer, default=0)    # 广告/营销费
    repair_cost_amount = Column(Integer, default=0)       # 修理费
    management_fee_amount = Column(Integer, default=0)    # 管理费
    other_expense_amount = Column(Integer, default=0)     # 其他费用

    # 优惠类字段（金额单位：分）
    total_discount_amount = Column(Integer, default=0)    # 总折扣金额
    platform_discount_amount = Column(Integer, default=0) # 平台活动折扣
    member_discount_amount = Column(Integer, default=0)   # 会员优惠
    manager_authorized_discount_amount = Column(Integer, default=0)  # 店长授权优惠
    complaint_compensation_amount = Column(Integer, default=0)       # 客诉补偿
    rounding_discount_amount = Column(Integer, default=0) # 抹零金额

    # 派生结果字段（金额：分；率：×10000 存整数，如 3300=33.00%）
    gross_profit_amount = Column(Integer, default=0)      # 毛利润
    gross_profit_rate = Column(Integer, default=0)        # 毛利率×10000
    net_profit_amount = Column(Integer, default=0)        # 净利润
    net_profit_rate = Column(Integer, default=0)          # 净利率×10000（可为负）
    food_cost_rate = Column(Integer, default=0)           # 菜品成本率×10000
    labor_cost_rate = Column(Integer, default=0)          # 人工率×10000
    discount_rate = Column(Integer, default=0)            # 折扣率×10000
    dine_in_sales_rate = Column(Integer, default=0)       # 堂食占比×10000
    delivery_sales_rate = Column(Integer, default=0)      # 外卖占比×10000

    # 人效字段
    front_staff_count = Column(Integer, default=0)
    kitchen_staff_count = Column(Integer, default=0)
    total_staff_count = Column(Integer, default=0)
    labor_hours = Column(Integer, default=0)              # 总工时×100
    sales_per_staff = Column(Integer, default=0)          # 人均销售（分）
    sales_per_labor_hour = Column(Integer, default=0)     # 工时效率（分）

    # 数据来源状态
    pos_source_status = Column(String(32))
    inventory_source_status = Column(String(32))
    attendance_source_status = Column(String(32))
    delivery_source_status = Column(String(32))
    data_version = Column(Integer, default=1, nullable=False)
    is_manual_adjusted = Column(Boolean, default=False, nullable=False)
    adjusted_by = Column(String(64))
    adjusted_at = Column(String(50))

    # 综合预警等级（green/yellow/red）
    warning_level = Column(String(16), default="green")

    def __repr__(self):
        return f"<StoreDailyMetric(store_id='{self.store_id}', biz_date='{self.biz_date}')>"
