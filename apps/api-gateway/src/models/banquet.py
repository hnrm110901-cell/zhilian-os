"""
宴会管理 Agent — 数据模型
Phase 10（Banquet Intelligence System）

5层架构对应模型：
  L1 基础主数据：BanquetHall, BanquetHallType, BanquetType, SourceChannel
  L2 客户线索层：BanquetCustomer, BanquetLead, LeadFollowupRecord, BanquetQuote
  L3 订单资源层：BanquetOrder, BanquetHallBooking, MenuPackage, MenuPackageItem
  L4 执行收款层：ExecutionTemplate, ExecutionTask, ExecutionException,
                 BanquetPaymentRecord, BanquetContract
  L5 分析智能层：BanquetProfitSnapshot, BanquetKpiDaily,
                 BanquetAgentRule, BanquetAgentActionLog,
                 BanquetRevenueTarget
"""

import enum
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from src.models.base import Base, TimestampMixin

# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────


class BanquetHallType(str, enum.Enum):
    MAIN_HALL = "main_hall"  # 大厅
    VIP_ROOM = "vip_room"  # 包间
    GARDEN = "garden"  # 花园/露台
    OUTDOOR = "outdoor"  # 户外场地


class BanquetTypeEnum(str, enum.Enum):
    WEDDING = "wedding"  # 婚宴
    BIRTHDAY = "birthday"  # 寿宴/生日宴
    BUSINESS = "business"  # 商务宴
    FULL_MOON = "full_moon"  # 满月酒
    GRADUATION = "graduation"  # 升学宴
    ANNIVERSARY = "anniversary"  # 纪念日宴
    OTHER = "other"  # 其他


class LeadStageEnum(str, enum.Enum):
    NEW = "new"  # 新线索
    CONTACTED = "contacted"  # 已联系
    VISIT_SCHEDULED = "visit_scheduled"  # 预约看厅
    QUOTED = "quoted"  # 已报价
    WAITING_DECISION = "waiting_decision"  # 等待决策
    DEPOSIT_PENDING = "deposit_pending"  # 待付定金
    WON = "won"  # 成交
    LOST = "lost"  # 流失


class OrderStatusEnum(str, enum.Enum):
    DRAFT = "draft"  # 草稿
    CONFIRMED = "confirmed"  # 已确认
    PREPARING = "preparing"  # 准备中
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"  # 已完成
    SETTLED = "settled"  # 已结算
    CLOSED = "closed"  # 已关闭
    CANCELLED = "cancelled"  # 已取消


class DepositStatusEnum(str, enum.Enum):
    UNPAID = "unpaid"  # 未付
    PARTIAL = "partial"  # 部分付
    PAID = "paid"  # 已付


class TaskStatusEnum(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    VERIFIED = "verified"
    OVERDUE = "overdue"
    CLOSED = "closed"


class TaskOwnerRoleEnum(str, enum.Enum):
    KITCHEN = "kitchen"  # 厨房
    SERVICE = "service"  # 服务
    DECOR = "decor"  # 布置
    PURCHASE = "purchase"  # 采购
    MANAGER = "manager"  # 店长


class PaymentTypeEnum(str, enum.Enum):
    DEPOSIT = "deposit"  # 定金
    BALANCE = "balance"  # 尾款
    EXTRA = "extra"  # 追加消费


class BanquetAgentTypeEnum(str, enum.Enum):
    FOLLOWUP = "followup"  # 跟进提醒
    QUOTATION = "quotation"  # 自动报价
    SCHEDULING = "scheduling"  # 排期推荐
    EXECUTION = "execution"  # 执行任务
    REVIEW = "review"  # 复盘


# ─────────────────────────────────────────────
# L1 — 基础主数据
# ─────────────────────────────────────────────


class BanquetHall(Base, TimestampMixin):
    """宴会厅/包间主数据"""

    __tablename__ = "banquet_halls"

    id = Column(String(36), primary_key=True)
    store_id = Column(String(36), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    hall_type = Column(SAEnum(BanquetHallType), nullable=False)
    max_tables = Column(Integer, nullable=False, default=1)
    max_people = Column(Integer, nullable=False)
    min_spend_fen = Column(Integer, nullable=False, default=0)  # 最低消费（分）
    floor_area_m2 = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    bookings = relationship("BanquetHallBooking", back_populates="hall")

    __table_args__ = (Index("ix_banquet_halls_store_active", "store_id", "is_active"),)


# ─────────────────────────────────────────────
# L2 — 客户与线索层
# ─────────────────────────────────────────────


class BanquetCustomer(Base, TimestampMixin):
    """宴会客户（独立于散客会员体系，聚焦宴会CRM）"""

    __tablename__ = "banquet_customers"

    id = Column(String(36), primary_key=True)
    brand_id = Column(String(36), nullable=False, index=True)
    store_id = Column(String(36), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    wechat_id = Column(String(100), nullable=True)
    customer_type = Column(String(50), nullable=True)  # 个人/企业
    company_name = Column(String(200), nullable=True)
    source = Column(String(50), nullable=True)  # 来源渠道
    tags = Column(JSON, nullable=True)  # 标签列表
    vip_level = Column(Integer, nullable=False, default=0)
    total_banquet_count = Column(Integer, nullable=False, default=0)
    total_banquet_amount_fen = Column(Integer, nullable=False, default=0)  # 累计消费（分）
    remark = Column(Text, nullable=True)

    leads = relationship("BanquetLead", back_populates="customer")
    orders = relationship("BanquetOrder", back_populates="customer")

    __table_args__ = (Index("ix_banquet_customers_brand_phone", "brand_id", "phone"),)


class BanquetLead(Base, TimestampMixin):
    """宴会线索（销售漏斗核心对象）"""

    __tablename__ = "banquet_leads"

    id = Column(String(36), primary_key=True)
    customer_id = Column(String(36), ForeignKey("banquet_customers.id"), nullable=False)
    store_id = Column(String(36), nullable=False, index=True)
    banquet_type = Column(SAEnum(BanquetTypeEnum), nullable=False)
    expected_date = Column(Date, nullable=True)
    expected_people_count = Column(Integer, nullable=True)
    expected_budget_fen = Column(Integer, nullable=True)  # 预算（分）
    preferred_hall_type = Column(SAEnum(BanquetHallType), nullable=True)
    source_channel = Column(String(50), nullable=True)
    current_stage = Column(SAEnum(LeadStageEnum), nullable=False, default=LeadStageEnum.NEW)
    owner_user_id = Column(String(36), nullable=True)
    last_followup_at = Column(DateTime, nullable=True)
    next_followup_at = Column(DateTime, nullable=True)
    lost_reason = Column(String(200), nullable=True)
    converted_order_id = Column(String(36), nullable=True)

    customer = relationship("BanquetCustomer", back_populates="leads")
    followups = relationship("LeadFollowupRecord", back_populates="lead", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_banquet_leads_store_stage", "store_id", "current_stage"),
        Index("ix_banquet_leads_owner", "owner_user_id"),
    )


class LeadFollowupRecord(Base, TimestampMixin):
    """线索跟进记录"""

    __tablename__ = "lead_followup_records"

    id = Column(String(36), primary_key=True)
    lead_id = Column(String(36), ForeignKey("banquet_leads.id"), nullable=False)
    followup_type = Column(String(50), nullable=False)  # call/visit/wechat/email
    content = Column(Text, nullable=False)
    stage_before = Column(SAEnum(LeadStageEnum), nullable=True)
    stage_after = Column(SAEnum(LeadStageEnum), nullable=True)
    next_followup_at = Column(DateTime, nullable=True)
    created_by = Column(String(36), nullable=False)

    lead = relationship("BanquetLead", back_populates="followups")


class BanquetQuote(Base, TimestampMixin):
    """宴会报价单"""

    __tablename__ = "banquet_quotes"

    id = Column(String(36), primary_key=True)
    lead_id = Column(String(36), ForeignKey("banquet_leads.id"), nullable=False)
    store_id = Column(String(36), nullable=False, index=True)
    package_id = Column(String(36), nullable=True)  # 基础套餐（可为空=自定义）
    people_count = Column(Integer, nullable=False)
    table_count = Column(Integer, nullable=False)
    quoted_amount_fen = Column(Integer, nullable=False)  # 报价总额（分）
    menu_snapshot = Column(JSON, nullable=True)  # 菜单快照
    valid_until = Column(Date, nullable=True)
    is_accepted = Column(Boolean, nullable=False, default=False)
    created_by = Column(String(36), nullable=False)


# ─────────────────────────────────────────────
# L3 — 订单与资源层
# ─────────────────────────────────────────────


class MenuPackage(Base, TimestampMixin):
    """宴会套餐"""

    __tablename__ = "banquet_menu_packages"

    id = Column(String(36), primary_key=True)
    store_id = Column(String(36), nullable=False, index=True)
    banquet_type = Column(SAEnum(BanquetTypeEnum), nullable=True)
    name = Column(String(200), nullable=False)
    suggested_price_fen = Column(Integer, nullable=False)  # 建议售价（分）
    cost_fen = Column(Integer, nullable=True)  # 估算成本（分）
    target_people_min = Column(Integer, nullable=False, default=1)
    target_people_max = Column(Integer, nullable=False, default=999)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    items = relationship("MenuPackageItem", back_populates="package", cascade="all, delete-orphan")
    orders = relationship("BanquetOrder", back_populates="package")


class MenuPackageItem(Base, TimestampMixin):
    """套餐菜品明细"""

    __tablename__ = "banquet_menu_package_items"

    id = Column(String(36), primary_key=True)
    package_id = Column(String(36), ForeignKey("banquet_menu_packages.id"), nullable=False)
    dish_id = Column(String(36), nullable=True)  # 关联菜品（可为自定义菜）
    dish_name = Column(String(200), nullable=False)  # 冗余存名，菜品变更不影响历史
    item_type = Column(String(50), nullable=False, default="standard")  # standard/optional
    quantity = Column(Integer, nullable=False, default=1)
    replace_group = Column(String(50), nullable=True)  # 同组可替换

    package = relationship("MenuPackage", back_populates="items")


class BanquetOrder(Base, TimestampMixin):
    """宴会订单（核心业务对象）"""

    __tablename__ = "banquet_orders"

    id = Column(String(36), primary_key=True)
    lead_id = Column(String(36), ForeignKey("banquet_leads.id"), nullable=True)
    customer_id = Column(String(36), ForeignKey("banquet_customers.id"), nullable=False)
    store_id = Column(String(36), nullable=False, index=True)
    banquet_type = Column(SAEnum(BanquetTypeEnum), nullable=False)
    banquet_date = Column(Date, nullable=False)
    people_count = Column(Integer, nullable=False)
    table_count = Column(Integer, nullable=False)
    package_id = Column(String(36), ForeignKey("banquet_menu_packages.id"), nullable=True)
    menu_snapshot = Column(JSON, nullable=True)  # 菜单最终快照
    order_status = Column(SAEnum(OrderStatusEnum), nullable=False, default=OrderStatusEnum.DRAFT)
    deposit_status = Column(SAEnum(DepositStatusEnum), nullable=False, default=DepositStatusEnum.UNPAID)
    total_amount_fen = Column(Integer, nullable=False, default=0)  # 合同总额（分）
    deposit_fen = Column(Integer, nullable=False, default=0)  # 定金（分）
    paid_fen = Column(Integer, nullable=False, default=0)  # 已付总额（分）
    contact_name = Column(String(100), nullable=True)
    contact_phone = Column(String(20), nullable=True)
    remark = Column(Text, nullable=True)
    owner_user_id = Column(String(36), nullable=True)

    customer = relationship("BanquetCustomer", back_populates="orders")
    package = relationship("MenuPackage", back_populates="orders")
    bookings = relationship("BanquetHallBooking", back_populates="order", cascade="all, delete-orphan")
    tasks = relationship("ExecutionTask", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("BanquetPaymentRecord", back_populates="order", cascade="all, delete-orphan")
    contract = relationship("BanquetContract", back_populates="order", uselist=False)

    __table_args__ = (
        Index("ix_banquet_orders_store_date", "store_id", "banquet_date"),
        Index("ix_banquet_orders_store_status", "store_id", "order_status"),
    )


class BanquetHallBooking(Base, TimestampMixin):
    """宴会厅档期占用（防冲突核心表）"""

    __tablename__ = "banquet_hall_bookings"

    id = Column(String(36), primary_key=True)
    hall_id = Column(String(36), ForeignKey("banquet_halls.id"), nullable=False)
    banquet_order_id = Column(String(36), ForeignKey("banquet_orders.id"), nullable=False)
    slot_date = Column(Date, nullable=False)
    slot_name = Column(String(50), nullable=False)  # lunch/dinner/all_day
    start_time = Column(String(10), nullable=True)  # HH:MM
    end_time = Column(String(10), nullable=True)
    is_locked = Column(Boolean, nullable=False, default=True)

    hall = relationship("BanquetHall", back_populates="bookings")
    order = relationship("BanquetOrder", back_populates="bookings")

    __table_args__ = (
        UniqueConstraint("hall_id", "slot_date", "slot_name", name="uq_hall_booking_slot"),
        Index("ix_hall_bookings_date", "slot_date"),
    )


# ─────────────────────────────────────────────
# L4 — 执行与收款层
# ─────────────────────────────────────────────


class ExecutionTemplate(Base, TimestampMixin):
    """宴会执行任务模板"""

    __tablename__ = "banquet_execution_templates"

    id = Column(String(36), primary_key=True)
    store_id = Column(String(36), nullable=False, index=True)
    template_name = Column(String(200), nullable=False)
    banquet_type = Column(SAEnum(BanquetTypeEnum), nullable=True)  # None=通用
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    task_defs = Column(JSON, nullable=False)  # 任务定义列表（提前多少天、责任角色等）


class ExecutionTask(Base, TimestampMixin):
    """宴会执行任务（由模板自动生成）"""

    __tablename__ = "banquet_execution_tasks"

    id = Column(String(36), primary_key=True)
    banquet_order_id = Column(String(36), ForeignKey("banquet_orders.id"), nullable=False)
    template_id = Column(String(36), ForeignKey("banquet_execution_templates.id"), nullable=True)
    task_type = Column(String(50), nullable=False)
    task_name = Column(String(200), nullable=False)
    owner_role = Column(SAEnum(TaskOwnerRoleEnum), nullable=False)
    owner_user_id = Column(String(36), nullable=True)
    due_time = Column(DateTime, nullable=False)
    task_status = Column(SAEnum(TaskStatusEnum), nullable=False, default=TaskStatusEnum.PENDING)
    completed_at = Column(DateTime, nullable=True)
    remark = Column(Text, nullable=True)

    order = relationship("BanquetOrder", back_populates="tasks")

    __table_args__ = (
        Index("ix_exec_tasks_order", "banquet_order_id"),
        Index("ix_exec_tasks_status_due", "task_status", "due_time"),
    )


class ExecutionException(Base, TimestampMixin):
    """宴会执行异常事件"""

    __tablename__ = "banquet_execution_exceptions"

    id = Column(String(36), primary_key=True)
    banquet_order_id = Column(String(36), ForeignKey("banquet_orders.id"), nullable=False)
    task_id = Column(String(36), ForeignKey("banquet_execution_tasks.id"), nullable=True)
    exception_type = Column(String(50), nullable=False)  # late/missing/quality/complaint
    description = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False, default="medium")  # low/medium/high
    owner_user_id = Column(String(36), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="open")  # open/resolved


class BanquetPaymentRecord(Base, TimestampMixin):
    """宴会收款记录"""

    __tablename__ = "banquet_payment_records"

    id = Column(String(36), primary_key=True)
    banquet_order_id = Column(String(36), ForeignKey("banquet_orders.id"), nullable=False)
    payment_type = Column(SAEnum(PaymentTypeEnum), nullable=False)
    amount_fen = Column(Integer, nullable=False)  # 金额（分）
    paid_at = Column(DateTime, nullable=False)
    payment_method = Column(String(50), nullable=True)  # cash/wechat/alipay/pos
    receipt_no = Column(String(100), nullable=True)
    created_by = Column(String(36), nullable=False)

    order = relationship("BanquetOrder", back_populates="payments")


class BanquetContract(Base, TimestampMixin):
    """宴会合同"""

    __tablename__ = "banquet_contracts"

    id = Column(String(36), primary_key=True)
    banquet_order_id = Column(String(36), ForeignKey("banquet_orders.id"), nullable=False, unique=True)
    contract_no = Column(String(100), nullable=False, unique=True)
    file_url = Column(String(500), nullable=True)
    contract_status = Column(String(20), nullable=False, default="draft")  # draft/signed/void
    signed_at = Column(DateTime, nullable=True)
    signed_by = Column(String(36), nullable=True)

    order = relationship("BanquetOrder", back_populates="contract")


# ─────────────────────────────────────────────
# L5 — 分析、快照与 Agent 层
# ─────────────────────────────────────────────


class BanquetProfitSnapshot(Base, TimestampMixin):
    """宴会利润快照（宴会完成后计算）"""

    __tablename__ = "banquet_profit_snapshots"

    id = Column(String(36), primary_key=True)
    banquet_order_id = Column(String(36), ForeignKey("banquet_orders.id"), nullable=False, unique=True)
    revenue_fen = Column(Integer, nullable=False, default=0)
    ingredient_cost_fen = Column(Integer, nullable=False, default=0)
    labor_cost_fen = Column(Integer, nullable=False, default=0)
    material_cost_fen = Column(Integer, nullable=False, default=0)
    other_cost_fen = Column(Integer, nullable=False, default=0)
    gross_profit_fen = Column(Integer, nullable=False, default=0)
    gross_margin_pct = Column(Float, nullable=False, default=0.0)


class BanquetKpiDaily(Base, TimestampMixin):
    """宴会KPI日报（分析聚合）"""

    __tablename__ = "banquet_kpi_daily"

    id = Column(String(36), primary_key=True)
    store_id = Column(String(36), nullable=False, index=True)
    stat_date = Column(Date, nullable=False)
    lead_count = Column(Integer, nullable=False, default=0)
    order_count = Column(Integer, nullable=False, default=0)
    revenue_fen = Column(Integer, nullable=False, default=0)
    gross_profit_fen = Column(Integer, nullable=False, default=0)
    hall_utilization_pct = Column(Float, nullable=False, default=0.0)
    conversion_rate_pct = Column(Float, nullable=False, default=0.0)

    __table_args__ = (UniqueConstraint("store_id", "stat_date", name="uq_banquet_kpi_store_date"),)


class BanquetAgentRule(Base, TimestampMixin):
    """宴会 Agent 规则定义"""

    __tablename__ = "banquet_agent_rules"

    id = Column(String(36), primary_key=True)
    store_id = Column(String(36), nullable=True)  # None=全局规则
    agent_type = Column(SAEnum(BanquetAgentTypeEnum), nullable=False)
    rule_name = Column(String(200), nullable=False)
    trigger_event = Column(String(100), nullable=False)
    rule_expression = Column(JSON, nullable=False)  # 规则条件（JSON格式）
    action_template = Column(JSON, nullable=False)  # 动作模板
    is_active = Column(Boolean, nullable=False, default=True)


class BanquetAgentActionLog(Base, TimestampMixin):
    """宴会 Agent 执行日志"""

    __tablename__ = "banquet_agent_action_logs"

    id = Column(String(36), primary_key=True)
    agent_type = Column(SAEnum(BanquetAgentTypeEnum), nullable=False)
    related_object_type = Column(String(50), nullable=False)  # lead/order/task
    related_object_id = Column(String(36), nullable=False)
    rule_id = Column(String(36), nullable=True)
    action_type = Column(String(100), nullable=False)
    action_result = Column(JSON, nullable=True)
    suggestion_text = Column(Text, nullable=True)
    is_human_approved = Column(Boolean, nullable=True)  # None=未审批

    __table_args__ = (Index("ix_banquet_agent_log_obj", "related_object_type", "related_object_id"),)


class BanquetRevenueTarget(Base, TimestampMixin):
    """宴会月度营收目标"""

    __tablename__ = "banquet_revenue_targets"

    id = Column(String(36), primary_key=True)
    store_id = Column(String(36), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)  # 1–12
    target_fen = Column(Integer, nullable=False)  # 目标营收（分）

    __table_args__ = (UniqueConstraint("store_id", "year", "month", name="uq_revenue_target_store_ym"),)


class BanquetOrderReview(Base, TimestampMixin):
    """宴会订单复盘（AI生成 + 客户评分）"""

    __tablename__ = "banquet_order_reviews"

    id = Column(String(36), primary_key=True)
    banquet_order_id = Column(String(36), ForeignKey("banquet_orders.id"), nullable=False, unique=True, index=True)
    customer_rating = Column(Integer, nullable=True)  # 1–5 星
    ai_score = Column(Float, nullable=True)  # 0–100
    ai_summary = Column(Text, nullable=True)
    improvement_tags = Column(JSON, nullable=True)  # ["延误", "菜量不足", ...]
    revenue_yuan = Column(Float, nullable=True)
    gross_profit_yuan = Column(Float, nullable=True)
    gross_margin_pct = Column(Float, nullable=True)
    overdue_task_count = Column(Integer, nullable=False, default=0)
    exception_count = Column(Integer, nullable=False, default=0)

    order = relationship("BanquetOrder", backref="review", uselist=False)
