"""
餐饮业务标准Schema
Restaurant Business Standard Schema

覆盖订单、菜品、人员、时间、金额五个核心维度
智链OS作为餐饮门店的神经系统，统一数据标准
"""
from pydantic import BaseModel, Field, PlainSerializer
from typing import Optional, List, Dict, Any, Annotated
from datetime import datetime
from enum import Enum
from decimal import Decimal

# Decimal that serializes to float in JSON (Pydantic v2 PlainSerializer pattern)
JsonDecimal = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


# ==================== 核心维度枚举 ====================


class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "pending"  # 待处理
    CONFIRMED = "confirmed"  # 已确认
    PREPARING = "preparing"  # 制作中
    READY = "ready"  # 已完成
    SERVED = "served"  # 已上菜
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


class OrderType(str, Enum):
    """订单类型"""
    DINE_IN = "dine_in"  # 堂食
    TAKEOUT = "takeout"  # 外带
    DELIVERY = "delivery"  # 外卖
    RESERVATION = "reservation"  # 预定


class DishCategory(str, Enum):
    """菜品分类"""
    APPETIZER = "appetizer"  # 开胃菜
    MAIN_COURSE = "main_course"  # 主菜
    SIDE_DISH = "side_dish"  # 配菜
    SOUP = "soup"  # 汤
    DESSERT = "dessert"  # 甜点
    BEVERAGE = "beverage"  # 饮料
    STAPLE = "staple"  # 主食


class StaffRole(str, Enum):
    """员工角色"""
    MANAGER = "manager"  # 店长
    CHEF = "chef"  # 厨师
    COOK = "cook"  # 配菜员
    WAITER = "waiter"  # 服务员
    CASHIER = "cashier"  # 收银员
    CLEANER = "cleaner"  # 清洁员


class ShiftType(str, Enum):
    """班次类型"""
    MORNING = "morning"  # 早班
    AFTERNOON = "afternoon"  # 中班
    EVENING = "evening"  # 晚班
    NIGHT = "night"  # 夜班


class PaymentMethod(str, Enum):
    """支付方式"""
    CASH = "cash"  # 现金
    CARD = "card"  # 刷卡
    WECHAT = "wechat"  # 微信
    ALIPAY = "alipay"  # 支付宝
    MEMBER = "member"  # 会员卡


# ==================== 维度1: 订单 (Order) ====================


class OrderItemSchema(BaseModel):
    """订单项标准Schema"""
    item_id: str = Field(..., description="订单项ID")
    dish_id: str = Field(..., description="菜品ID")
    dish_name: str = Field(..., description="菜品名称")
    dish_category: DishCategory = Field(..., description="菜品分类")
    quantity: int = Field(..., ge=1, description="数量")
    unit_price: JsonDecimal = Field(..., ge=0, description="单价")
    subtotal: JsonDecimal = Field(..., ge=0, description="小计")
    special_requirements: Optional[str] = Field(None, description="特殊要求")
    preparation_time: Optional[int] = Field(None, description="预计制作时间（分钟）")


class OrderSchema(BaseModel):
    """订单标准Schema"""
    # 基础信息
    order_id: str = Field(..., description="订单ID")
    order_number: str = Field(..., description="订单号")
    order_type: OrderType = Field(..., description="订单类型")
    order_status: OrderStatus = Field(..., description="订单状态")

    # 关联信息
    store_id: str = Field(..., description="门店ID")
    brand_id: Optional[str] = Field(None, description="品牌ID（多品牌隔离）")
    table_number: Optional[str] = Field(None, description="桌号")
    customer_id: Optional[str] = Field(None, description="客户ID")

    # 订单项
    items: List[OrderItemSchema] = Field(..., description="订单项列表")

    # 金额信息
    subtotal: JsonDecimal = Field(..., ge=0, description="小计")
    discount: JsonDecimal = Field(0, ge=0, description="折扣金额")
    service_charge: JsonDecimal = Field(0, ge=0, description="服务费")
    total: JsonDecimal = Field(..., ge=0, description="总金额")

    # 时间信息
    created_at: datetime = Field(..., description="创建时间")
    confirmed_at: Optional[datetime] = Field(None, description="确认时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")

    # 人员信息
    waiter_id: Optional[str] = Field(None, description="服务员ID")
    chef_id: Optional[str] = Field(None, description="厨师ID")
    cashier_id: Optional[str] = Field(None, description="收银员ID")

    # 备注
    notes: Optional[str] = Field(None, description="备注")


# ==================== 维度2: 菜品 (Dish) ====================


class NutritionInfo(BaseModel):
    """营养信息"""
    calories: Optional[float] = Field(None, description="卡路里")
    protein: Optional[float] = Field(None, description="蛋白质(g)")
    fat: Optional[float] = Field(None, description="脂肪(g)")
    carbohydrate: Optional[float] = Field(None, description="碳水化合物(g)")


class IngredientSchema(BaseModel):
    """食材标准Schema"""
    ingredient_id: str = Field(..., description="食材ID")
    name: str = Field(..., description="食材名称")
    quantity: float = Field(..., ge=0, description="用量")
    unit: str = Field(..., description="单位")
    cost: JsonDecimal = Field(..., ge=0, description="成本")


class DishSchema(BaseModel):
    """菜品标准Schema"""
    # 基础信息
    dish_id: str = Field(..., description="菜品ID")
    name: str = Field(..., description="菜品名称")
    name_en: Optional[str] = Field(None, description="英文名称")
    category: DishCategory = Field(..., description="菜品分类")

    # 描述信息
    description: Optional[str] = Field(None, description="菜品描述")
    image_url: Optional[str] = Field(None, description="图片URL")
    tags: List[str] = Field(default_factory=list, description="标签")

    # 价格信息
    price: JsonDecimal = Field(..., ge=0, description="售价")
    cost: JsonDecimal = Field(..., ge=0, description="成本")
    profit_margin: float = Field(..., ge=0, le=1, description="利润率")

    # 制作信息
    preparation_time: int = Field(..., ge=0, description="制作时间（分钟）")
    ingredients: List[IngredientSchema] = Field(..., description="食材列表")
    recipe: Optional[str] = Field(None, description="制作方法")

    # 营养信息
    nutrition: Optional[NutritionInfo] = Field(None, description="营养信息")

    # 状态信息
    is_available: bool = Field(True, description="是否可售")
    is_recommended: bool = Field(False, description="是否推荐")
    popularity_score: float = Field(0, ge=0, le=100, description="受欢迎度")

    # 关联信息
    store_id: str = Field(..., description="门店ID")


# ==================== 维度3: 人员 (Staff) ====================


class ShiftSchema(BaseModel):
    """班次标准Schema"""
    shift_id: str = Field(..., description="班次ID")
    shift_type: ShiftType = Field(..., description="班次类型")
    start_time: datetime = Field(..., description="开始时间")
    end_time: datetime = Field(..., description="结束时间")
    break_duration: int = Field(0, ge=0, description="休息时长（分钟）")


class StaffSchema(BaseModel):
    """员工标准Schema"""
    # 基础信息
    staff_id: str = Field(..., description="员工ID")
    name: str = Field(..., description="姓名")
    role: StaffRole = Field(..., description="角色")
    phone: str = Field(..., description="手机号")
    email: Optional[str] = Field(None, description="邮箱")

    # 工作信息
    store_id: str = Field(..., description="门店ID")
    department: Optional[str] = Field(None, description="部门")
    hire_date: datetime = Field(..., description="入职日期")

    # 班次信息
    current_shift: Optional[ShiftSchema] = Field(None, description="当前班次")

    # 绩效信息
    performance_score: float = Field(0, ge=0, le=100, description="绩效评分")
    attendance_rate: float = Field(0, ge=0, le=1, description="出勤率")

    # 技能信息
    skills: List[str] = Field(default_factory=list, description="技能列表")
    certifications: List[str] = Field(default_factory=list, description="证书列表")

    # 状态信息
    is_active: bool = Field(True, description="是否在职")


# ==================== 维度4: 时间 (Time) ====================


class TimeSlotSchema(BaseModel):
    """时间段标准Schema"""
    slot_id: str = Field(..., description="时间段ID")
    date: datetime = Field(..., description="日期")
    start_time: datetime = Field(..., description="开始时间")
    end_time: datetime = Field(..., description="结束时间")
    duration_minutes: int = Field(..., ge=0, description="时长（分钟）")

    # 业务信息
    peak_hour: bool = Field(False, description="是否高峰期")
    expected_customers: Optional[int] = Field(None, description="预计客流")
    actual_customers: Optional[int] = Field(None, description="实际客流")

    # 关联信息
    store_id: str = Field(..., description="门店ID")


class BusinessHoursSchema(BaseModel):
    """营业时间标准Schema"""
    store_id: str = Field(..., description="门店ID")
    day_of_week: int = Field(..., ge=0, le=6, description="星期几（0=周一）")
    open_time: str = Field(..., description="开门时间（HH:MM）")
    close_time: str = Field(..., description="关门时间（HH:MM）")
    is_open: bool = Field(True, description="是否营业")
    break_start: Optional[str] = Field(None, description="休息开始时间")
    break_end: Optional[str] = Field(None, description="休息结束时间")


# ==================== 维度5: 金额 (Amount) ====================


class TransactionSchema(BaseModel):
    """交易标准Schema"""
    # 基础信息
    transaction_id: str = Field(..., description="交易ID")
    transaction_number: str = Field(..., description="交易号")
    transaction_type: str = Field(..., description="交易类型")

    # 金额信息
    amount: JsonDecimal = Field(..., description="金额")
    currency: str = Field("CNY", description="货币")

    # 支付信息
    payment_method: PaymentMethod = Field(..., description="支付方式")
    payment_status: str = Field(..., description="支付状态")

    # 关联信息
    order_id: Optional[str] = Field(None, description="订单ID")
    customer_id: Optional[str] = Field(None, description="客户ID")
    store_id: str = Field(..., description="门店ID")

    # 时间信息
    created_at: datetime = Field(..., description="创建时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")

    # 操作人员
    operator_id: Optional[str] = Field(None, description="操作员ID")

    # 备注
    notes: Optional[str] = Field(None, description="备注")


class FinancialSummarySchema(BaseModel):
    """财务汇总标准Schema"""
    # 时间范围
    period_start: datetime = Field(..., description="开始时间")
    period_end: datetime = Field(..., description="结束时间")

    # 收入
    total_revenue: JsonDecimal = Field(..., ge=0, description="总收入")
    dine_in_revenue: JsonDecimal = Field(0, ge=0, description="堂食收入")
    takeout_revenue: JsonDecimal = Field(0, ge=0, description="外带收入")
    delivery_revenue: JsonDecimal = Field(0, ge=0, description="外卖收入")

    # 成本
    total_cost: JsonDecimal = Field(..., ge=0, description="总成本")
    food_cost: JsonDecimal = Field(0, ge=0, description="食材成本")
    labor_cost: JsonDecimal = Field(0, ge=0, description="人工成本")
    overhead_cost: JsonDecimal = Field(0, ge=0, description="运营成本")

    # 利润
    gross_profit: JsonDecimal = Field(..., description="毛利润")
    net_profit: JsonDecimal = Field(..., description="净利润")
    profit_margin: float = Field(..., ge=-1, le=1, description="利润率")

    # 统计
    order_count: int = Field(..., ge=0, description="订单数")
    customer_count: int = Field(..., ge=0, description="客户数")
    average_order_value: JsonDecimal = Field(..., ge=0, description="客单价")

    # 关联信息
    store_id: str = Field(..., description="门店ID")


# ==================== 员工操作 (StaffAction) ====================


class StaffAction(BaseModel):
    """员工操作记录标准Schema（用于可信执行层审计）"""
    action_type: str = Field(..., description="操作类型（如 discount_apply, shift_report, stock_alert）")
    brand_id: str = Field(..., description="品牌ID")
    store_id: str = Field(..., description="门店ID")
    operator_id: str = Field(..., description="操作人员ID")
    amount: Optional[JsonDecimal] = Field(None, ge=0, description="涉及金额（如折扣金额）")
    reason: Optional[str] = Field(None, description="操作原因")
    approved_by: Optional[str] = Field(None, description="审批人员ID")
    created_at: datetime = Field(..., description="操作时间")


# ==================== 神经系统事件 (Neural System Event) ====================


class NeuralEventSchema(BaseModel):
    """神经系统事件标准Schema

    智链OS作为餐饮门店的神经系统，所有业务事件都通过此Schema传递
    """
    # 事件基础信息
    event_id: str = Field(..., description="事件ID")
    event_type: str = Field(..., description="事件类型")
    event_source: str = Field(..., description="事件来源")

    # 时间戳
    timestamp: datetime = Field(..., description="事件时间")

    # 关联维度
    order_id: Optional[str] = Field(None, description="订单ID")
    dish_id: Optional[str] = Field(None, description="菜品ID")
    staff_id: Optional[str] = Field(None, description="员工ID")
    store_id: str = Field(..., description="门店ID")

    # 事件数据
    data: Dict[str, Any] = Field(..., description="事件数据")

    # 向量嵌入（用于语义搜索）
    embedding: Optional[List[float]] = Field(None, description="向量嵌入")

    # 优先级
    priority: int = Field(0, ge=0, le=10, description="优先级")

    # 处理状态
    processed: bool = Field(False, description="是否已处理")
