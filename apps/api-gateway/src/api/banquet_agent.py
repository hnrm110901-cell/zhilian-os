"""
宴会管理 Agent — Phase 9 核心路由
路由前缀：/api/v1/banquet-agent

与现有 banquet.py（吉日/BEO）并存，专注 CRM+线索+订单+Agent 能力。
"""
import uuid
from datetime import date as date_type, datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.user import User
from src.models.banquet import (
    BanquetHall, BanquetCustomer, BanquetLead, BanquetOrder,
    MenuPackage, ExecutionTask, BanquetPaymentRecord,
    BanquetHallBooking, BanquetKpiDaily, BanquetQuote,
    BanquetContract, BanquetProfitSnapshot, LeadFollowupRecord,
    LeadStageEnum, OrderStatusEnum, BanquetTypeEnum,
    BanquetHallType, PaymentTypeEnum, DepositStatusEnum,
    TaskStatusEnum,
)
import sys
from pathlib import Path as _Path

def _load_banquet_agents():
    """懒加载 Banquet Agent（与 workforce_auto_schedule_service 同一模式）"""
    repo_root = _Path(__file__).resolve().parents[4]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from packages.agents.banquet.src.agent import (
        FollowupAgent, QuotationAgent, SchedulingAgent,
        ExecutionAgent, ReviewAgent,
    )
    return FollowupAgent, QuotationAgent, SchedulingAgent, ExecutionAgent, ReviewAgent

_FollowupAgent, _QuotationAgent, _SchedulingAgent, _ExecutionAgent, _ReviewAgent = _load_banquet_agents()

router = APIRouter(prefix="/api/v1/banquet-agent", tags=["banquet-agent"])

_LEAD_STAGE_LABELS: dict[str, str] = {
    "new":              "初步询价",
    "contacted":        "已联系",
    "visit_scheduled":  "预约看厅",
    "quoted":           "意向确认",
    "waiting_decision": "等待决策",
    "deposit_pending":  "锁台",
    "won":              "已签约",
    "lost":             "已流失",
}

_followup   = _FollowupAgent()
_quotation  = _QuotationAgent()
_scheduling = _SchedulingAgent()
_execution  = _ExecutionAgent()
_review     = _ReviewAgent()


# ────────── Schemas ──────────────────────────────────────────────────────────

class HallCreateReq(BaseModel):
    name: str
    hall_type: BanquetHallType
    max_tables: int = Field(ge=1, default=1)
    max_people: int = Field(ge=1)
    min_spend_yuan: float = Field(ge=0, default=0)
    floor_area_m2: Optional[float] = None
    description: Optional[str] = None


class CustomerCreateReq(BaseModel):
    name: str
    phone: str
    wechat_id: Optional[str] = None
    customer_type: Optional[str] = None
    company_name: Optional[str] = None
    source: Optional[str] = None
    remark: Optional[str] = None


class LeadCreateReq(BaseModel):
    customer_id: str
    banquet_type: BanquetTypeEnum
    expected_date: Optional[date_type] = None
    expected_people_count: Optional[int] = None
    expected_budget_yuan: Optional[float] = None
    preferred_hall_type: Optional[BanquetHallType] = None
    source_channel: Optional[str] = None
    owner_user_id: Optional[str] = None


class LeadStageUpdateReq(BaseModel):
    stage: LeadStageEnum
    followup_content: Optional[str] = None   # legacy field name
    followup_note:    Optional[str] = None   # Phase 2 frontend field name
    next_followup_days: Optional[int] = Field(None, ge=1, le=30)


class OrderCreateReq(BaseModel):
    lead_id: Optional[str] = None
    customer_id: str
    banquet_type: BanquetTypeEnum
    banquet_date: date_type
    people_count: int = Field(ge=1)
    table_count: int = Field(ge=1)
    package_id: Optional[str] = None
    total_amount_yuan: float = Field(ge=0)
    deposit_yuan: float = Field(ge=0, default=0)
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    hall_id: Optional[str] = None
    slot_name: str = "all_day"
    remark: Optional[str] = None


class PaymentReq(BaseModel):
    payment_type: PaymentTypeEnum = PaymentTypeEnum.BALANCE   # default: 尾款
    amount_yuan: float = Field(gt=0)
    payment_method: Optional[str] = None
    receipt_no: Optional[str] = None


# ────────── 宴会厅 ────────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/halls")
async def list_halls(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """查询门店宴会厅列表"""
    result = await db.execute(
        select(BanquetHall).where(
            and_(BanquetHall.store_id == store_id, BanquetHall.is_active == True)
        )
    )
    halls = result.scalars().all()
    return {
        "store_id": store_id,
        "total": len(halls),
        "items": [
            {
                "id": h.id, "name": h.name, "hall_type": h.hall_type.value,
                "max_tables": h.max_tables, "max_people": h.max_people,
                "min_spend_yuan": h.min_spend_fen / 100,
            }
            for h in halls
        ],
    }


@router.post("/stores/{store_id}/halls", status_code=status.HTTP_201_CREATED)
async def create_hall(
    store_id: str,
    body: HallCreateReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    hall = BanquetHall(
        id=str(uuid.uuid4()),
        store_id=store_id,
        name=body.name,
        hall_type=body.hall_type,
        max_tables=body.max_tables,
        max_people=body.max_people,
        min_spend_fen=int(body.min_spend_yuan * 100),
        floor_area_m2=body.floor_area_m2,
        description=body.description,
    )
    db.add(hall)
    await db.commit()
    return {"id": hall.id, "name": hall.name}


# ────────── 宴会客户 CRM ──────────────────────────────────────────────────────

@router.get("/stores/{store_id}/customers")
async def list_customers(
    store_id: str,
    q: Optional[str] = Query(None, description="搜索姓名/手机"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(BanquetCustomer).where(BanquetCustomer.store_id == store_id)
    if q:
        stmt = stmt.where(
            BanquetCustomer.name.ilike(f"%{q}%") |
            BanquetCustomer.phone.contains(q)
        )
    result = await db.execute(stmt.order_by(BanquetCustomer.total_banquet_amount_fen.desc()))
    customers = result.scalars().all()
    return {
        "store_id": store_id,
        "total": len(customers),
        "items": [
            {
                "id": c.id, "name": c.name, "phone": c.phone,
                "vip_level": c.vip_level,
                "total_banquet_count": c.total_banquet_count,
                "total_banquet_amount_yuan": c.total_banquet_amount_fen / 100,
                "source": c.source,
            }
            for c in customers
        ],
    }


@router.post("/stores/{store_id}/customers", status_code=status.HTTP_201_CREATED)
async def create_customer(
    store_id: str,
    body: CustomerCreateReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = await db.execute(
        select(BanquetCustomer).where(
            and_(BanquetCustomer.store_id == store_id, BanquetCustomer.phone == body.phone)
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="该手机号客户已存在")
    brand_id = getattr(current_user, "brand_id", store_id)
    customer = BanquetCustomer(
        id=str(uuid.uuid4()),
        brand_id=brand_id,
        store_id=store_id,
        name=body.name,
        phone=body.phone,
        wechat_id=body.wechat_id,
        customer_type=body.customer_type,
        company_name=body.company_name,
        source=body.source,
        remark=body.remark,
    )
    db.add(customer)
    await db.commit()
    return {"id": customer.id, "name": customer.name}


@router.get("/stores/{store_id}/customers/{customer_id}")
async def get_customer_detail(
    store_id: str,
    customer_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """客户详情：基本信息 + 全部线索 + 全部订单"""
    result = await db.execute(
        select(BanquetCustomer).where(
            and_(BanquetCustomer.id == customer_id, BanquetCustomer.store_id == store_id)
        )
    )
    customer = result.scalars().first()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    leads_result = await db.execute(
        select(BanquetLead)
        .where(BanquetLead.customer_id == customer_id)
        .order_by(BanquetLead.created_at.desc())
    )
    leads = leads_result.scalars().all()

    orders_result = await db.execute(
        select(BanquetOrder)
        .where(BanquetOrder.customer_id == customer_id)
        .order_by(BanquetOrder.banquet_date.desc())
    )
    orders = orders_result.scalars().all()

    return {
        "customer": {
            "id":                        customer.id,
            "name":                      customer.name,
            "phone":                     customer.phone,
            "wechat_id":                 customer.wechat_id,
            "customer_type":             customer.customer_type,
            "company_name":              customer.company_name,
            "vip_level":                 customer.vip_level,
            "total_banquet_count":       customer.total_banquet_count,
            "total_banquet_amount_yuan": customer.total_banquet_amount_fen / 100,
            "source":                    customer.source,
            "tags":                      customer.tags,
            "remark":                    customer.remark,
        },
        "leads": [
            {
                "lead_id":       l.id,
                "banquet_type":  l.banquet_type.value,
                "expected_date": l.expected_date.isoformat() if l.expected_date else None,
                "current_stage": l.current_stage.value,
                "stage_label":   _LEAD_STAGE_LABELS.get(l.current_stage.value, l.current_stage.value),
                "converted_order_id": l.converted_order_id,
            }
            for l in leads
        ],
        "orders": [
            {
                "order_id":          o.id,
                "banquet_type":      o.banquet_type.value,
                "banquet_date":      o.banquet_date.isoformat() if o.banquet_date else None,
                "order_status":      o.order_status.value,
                "total_amount_yuan": o.total_amount_fen / 100,
            }
            for o in orders
        ],
    }


# ────────── 宴会线索 ──────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/leads")
async def list_leads(
    store_id: str,
    stage: Optional[str] = Query(None),
    owner_user_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = (
        select(BanquetLead)
        .options(selectinload(BanquetLead.customer))
        .where(BanquetLead.store_id == store_id)
    )
    if stage:
        try:
            stmt = stmt.where(BanquetLead.current_stage == LeadStageEnum(stage))
        except ValueError:
            pass  # 无效阶段值 → 忽略过滤，返回全部
    if owner_user_id:
        stmt = stmt.where(BanquetLead.owner_user_id == owner_user_id)
    result = await db.execute(stmt.order_by(BanquetLead.created_at.desc()))
    leads = result.scalars().all()
    return {
        "total": len(leads),
        "items": [
            {
                # Phase 2 frontend fields
                "banquet_id":    l.id,
                "banquet_type":  l.banquet_type.value,
                "expected_date": str(l.expected_date) if l.expected_date else None,
                "contact_name":  l.customer.name if l.customer else None,
                "budget_yuan":   (l.expected_budget_fen or 0) / 100,
                "stage":         l.current_stage.value,
                "stage_label":   _LEAD_STAGE_LABELS.get(l.current_stage.value, l.current_stage.value),
                # Legacy fields (backward compat)
                "id":                   l.id,
                "expected_people_count": l.expected_people_count,
                "expected_budget_yuan":  (l.expected_budget_fen or 0) / 100,
                "current_stage":         l.current_stage.value,
                "owner_user_id":         l.owner_user_id,
                "last_followup_at":      l.last_followup_at.isoformat() if l.last_followup_at else None,
            }
            for l in leads
        ],
    }


@router.post("/stores/{store_id}/leads", status_code=status.HTTP_201_CREATED)
async def create_lead(
    store_id: str,
    body: LeadCreateReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    lead = BanquetLead(
        id=str(uuid.uuid4()),
        store_id=store_id,
        customer_id=body.customer_id,
        banquet_type=body.banquet_type,
        current_stage=LeadStageEnum.NEW,
        expected_date=body.expected_date,
        expected_people_count=body.expected_people_count,
        expected_budget_fen=int(body.expected_budget_yuan * 100) if body.expected_budget_yuan else None,
        preferred_hall_type=body.preferred_hall_type,
        source_channel=body.source_channel,
        owner_user_id=body.owner_user_id,
        last_followup_at=datetime.utcnow(),
    )
    db.add(lead)
    await db.commit()
    return {"id": lead.id, "current_stage": lead.current_stage.value}


@router.patch("/stores/{store_id}/leads/{lead_id}/stage")
async def update_lead_stage(
    store_id: str,
    lead_id: str,
    body: LeadStageUpdateReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """推进线索阶段 + 记录跟进内容（LeadFollowupRecord）"""
    result = await db.execute(
        select(BanquetLead).where(
            and_(BanquetLead.id == lead_id, BanquetLead.store_id == store_id)
        )
    )
    lead = result.scalars().first()
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")

    stage_before = lead.current_stage   # 变更前阶段，在 mutation 前保存
    lead.current_stage = body.stage
    lead.last_followup_at = datetime.utcnow()

    next_followup_at = None
    if body.next_followup_days:
        from datetime import timedelta
        next_followup_at = datetime.utcnow() + timedelta(days=body.next_followup_days)

    note_content = body.followup_content or body.followup_note or "（无跟进内容）"

    from src.models.banquet import LeadFollowupRecord
    record = LeadFollowupRecord(
        id=str(uuid.uuid4()),
        lead_id=lead_id,
        followup_type="wechat",          # 默认类型；后续可在 body 中扩展
        content=note_content,
        stage_before=stage_before,
        stage_after=body.stage,
        next_followup_at=next_followup_at,
        created_by=str(current_user.id),
    )
    db.add(record)
    await db.commit()
    return {
        "lead_id": lead_id,
        "stage_before": stage_before.value,
        "new_stage": lead.current_stage.value,
        "last_followup_at": lead.last_followup_at.isoformat(),
        "next_followup_at": next_followup_at.isoformat() if next_followup_at else None,
    }


# ────────── 宴会订单 ──────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/orders")
async def list_orders(
    store_id: str,
    status: Optional[str] = Query(None, description="订单状态（Phase 2 前端参数名）"),
    order_status: Optional[str] = Query(None, description="订单状态（旧参数名，兼容保留）"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(BanquetOrder).where(BanquetOrder.store_id == store_id)
    effective_status = status or order_status
    if effective_status:
        try:
            stmt = stmt.where(BanquetOrder.order_status == OrderStatusEnum(effective_status))
        except ValueError:
            pass  # 无效状态值 → 忽略过滤，返回全部
    if date_from:
        stmt = stmt.where(BanquetOrder.banquet_date >= date_from)
    if date_to:
        stmt = stmt.where(BanquetOrder.banquet_date <= date_to)
    result = await db.execute(stmt.order_by(BanquetOrder.banquet_date))
    orders = result.scalars().all()
    return {
        "total": len(orders),
        "items": [
            {
                # Phase 2 frontend fields
                "banquet_id":   o.id,
                "banquet_type": o.banquet_type.value,
                "banquet_date": str(o.banquet_date),
                "table_count":  o.table_count,
                "amount_yuan":  o.total_amount_fen / 100,
                "status":       o.order_status.value,
                # Legacy fields (backward compat)
                "id":                 o.id,
                "people_count":       o.people_count,
                "order_status":       o.order_status.value,
                "deposit_status":     o.deposit_status.value,
                "total_amount_yuan":  o.total_amount_fen / 100,
                "paid_yuan":          o.paid_fen / 100,
                "balance_yuan":       (o.total_amount_fen - o.paid_fen) / 100,
            }
            for o in orders
        ],
    }


@router.post("/stores/{store_id}/orders", status_code=status.HTTP_201_CREATED)
async def create_order(
    store_id: str,
    body: OrderCreateReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    order = BanquetOrder(
        id=str(uuid.uuid4()),
        lead_id=body.lead_id,
        customer_id=body.customer_id,
        store_id=store_id,
        banquet_type=body.banquet_type,
        banquet_date=body.banquet_date,
        people_count=body.people_count,
        table_count=body.table_count,
        package_id=body.package_id,
        order_status=OrderStatusEnum.DRAFT,
        total_amount_fen=int(body.total_amount_yuan * 100),
        deposit_fen=int(body.deposit_yuan * 100) if body.deposit_yuan else 0,
        contact_name=body.contact_name,
        contact_phone=body.contact_phone,
        remark=body.remark,
    )
    db.add(order)
    await db.commit()
    return {"id": order.id, "order_status": order.order_status.value}


@router.post("/stores/{store_id}/orders/{order_id}/confirm")
async def confirm_order(
    store_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """确认订单 → ExecutionAgent 自动生成执行任务"""
    result = await db.execute(
        select(BanquetOrder).where(
            and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
        )
    )
    order = result.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.order_status != OrderStatusEnum.DRAFT:
        raise HTTPException(status_code=400, detail=f"当前状态 {order.order_status.value} 不可确认")

    order.order_status = OrderStatusEnum.CONFIRMED
    await db.commit()
    tasks = await _execution.generate_tasks_for_order(order=order, db=db)
    return {
        "order_id": order_id,
        "order_status": order.order_status.value,
        "tasks_generated": len(tasks),
        "message": f"订单已确认，自动生成 {len(tasks)} 个执行任务。",
    }


@router.post("/stores/{store_id}/orders/{order_id}/payment")
async def add_payment(
    store_id: str,
    order_id: str,
    body: PaymentReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """收款登记"""
    result = await db.execute(
        select(BanquetOrder).where(
            and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
        )
    )
    order = result.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    payment = BanquetPaymentRecord(
        id=str(uuid.uuid4()),
        banquet_order_id=order_id,
        payment_type=body.payment_type,
        amount_fen=int(body.amount_yuan * 100),
        paid_at=datetime.utcnow(),
        payment_method=body.payment_method,
        receipt_no=body.receipt_no,
        created_by=str(current_user.id),
    )
    db.add(payment)
    order.paid_fen += payment.amount_fen
    # 更新定金状态
    if order.paid_fen >= order.deposit_fen:
        order.deposit_status = DepositStatusEnum.PAID
    elif order.paid_fen > 0:
        order.deposit_status = DepositStatusEnum.PARTIAL
    await db.commit()
    return {
        "payment_id": payment.id,
        "paid_yuan": order.paid_fen / 100,
        "balance_yuan": (order.total_amount_fen - order.paid_fen) / 100,
        "deposit_status": order.deposit_status.value,
    }


# ────────── 订单详情 ──────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/orders/{order_id}")
async def get_order_detail(
    store_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """订单详情：基本信息 + 执行任务 + 付款记录"""
    result = await db.execute(
        select(BanquetOrder)
        .options(
            selectinload(BanquetOrder.tasks),
            selectinload(BanquetOrder.payments),
            selectinload(BanquetOrder.bookings).selectinload(BanquetHallBooking.hall),
            selectinload(BanquetOrder.customer),
        )
        .where(and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id))
    )
    order = result.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    tasks_data = [
        {
            "task_id":    t.id,
            "task_name":  t.task_name,
            "task_type":  t.task_type,
            "owner_role": t.owner_role.value,
            "due_time":   t.due_time.isoformat() if t.due_time else None,
            "status":     t.task_status.value,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "remark":     t.remark,
        }
        for t in sorted(order.tasks, key=lambda x: x.due_time)
    ]
    payments_data = [
        {
            "payment_id":     p.id,
            "payment_type":   p.payment_type.value,
            "amount_yuan":    p.amount_fen / 100,
            "payment_method": p.payment_method,
            "paid_at":        p.paid_at.isoformat() if p.paid_at else None,
            "receipt_no":     p.receipt_no,
        }
        for p in sorted(order.payments, key=lambda x: x.paid_at)
    ]
    booking = order.bookings[0] if order.bookings else None

    tasks_done  = sum(1 for t in order.tasks if t.task_status == TaskStatusEnum.DONE)
    tasks_total = len(order.tasks)

    return {
        "order_id":          order.id,
        "store_id":          order.store_id,
        "banquet_type":      order.banquet_type.value,
        "banquet_date":      order.banquet_date.isoformat(),
        "people_count":      order.people_count,
        "table_count":       order.table_count,
        "contact_name":      order.contact_name or (order.customer.name if order.customer else None),
        "contact_phone":     order.contact_phone or (order.customer.phone if order.customer else None),
        "status":            order.order_status.value,
        "deposit_status":    order.deposit_status.value,
        "total_amount_yuan": order.total_amount_fen / 100,
        "paid_yuan":         order.paid_fen / 100,
        "balance_yuan":      (order.total_amount_fen - order.paid_fen) / 100,
        "hall_name":         booking.hall.name if booking and booking.hall else None,
        "slot_name":         booking.slot_name if booking else None,
        "remark":            order.remark,
        "tasks":             tasks_data,
        "tasks_done":        tasks_done,
        "tasks_total":       tasks_total,
        "payments":          payments_data,
    }


# ────────── 执行任务 ──────────────────────────────────────────────────────────

class TaskUpdateReq(BaseModel):
    status: TaskStatusEnum
    remark: Optional[str] = None


@router.get("/stores/{store_id}/orders/{order_id}/tasks")
async def list_order_tasks(
    store_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """订单执行任务列表"""
    # verify order belongs to store
    order_result = await db.execute(
        select(BanquetOrder.id).where(
            and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
        )
    )
    if not order_result.first():
        raise HTTPException(status_code=404, detail="订单不存在")

    result = await db.execute(
        select(ExecutionTask)
        .where(ExecutionTask.banquet_order_id == order_id)
        .order_by(ExecutionTask.due_time)
    )
    tasks = result.scalars().all()
    return [
        {
            "task_id":    t.id,
            "task_name":  t.task_name,
            "task_type":  t.task_type,
            "owner_role": t.owner_role.value,
            "due_time":   t.due_time.isoformat() if t.due_time else None,
            "status":     t.task_status.value,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "remark":     t.remark,
        }
        for t in tasks
    ]


@router.patch("/stores/{store_id}/orders/{order_id}/tasks/{task_id}")
async def update_task_status(
    store_id: str,
    order_id: str,
    task_id: str,
    body: TaskUpdateReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """更新任务状态（完成/重开等）"""
    # join-verify task belongs to this store's order
    result = await db.execute(
        select(ExecutionTask)
        .join(BanquetOrder, ExecutionTask.banquet_order_id == BanquetOrder.id)
        .where(
            and_(
                ExecutionTask.id == task_id,
                BanquetOrder.id == order_id,
                BanquetOrder.store_id == store_id,
            )
        )
    )
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task.task_status = body.status
    if body.status == TaskStatusEnum.DONE and not task.completed_at:
        task.completed_at = datetime.utcnow()
    elif body.status != TaskStatusEnum.DONE:
        task.completed_at = None
    if body.remark is not None:
        task.remark = body.remark
    await db.commit()
    return {"task_id": task_id, "status": task.task_status.value}


@router.post("/stores/{store_id}/orders/{order_id}/tasks/generate", status_code=201)
async def generate_order_tasks(
    store_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """从模板为订单批量生成执行任务（ExecutionAgent）"""
    result = await db.execute(
        select(BanquetOrder).where(
            and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
        )
    )
    order = result.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    tasks = await _execution.generate_tasks_for_order(order=order, db=db)
    return {"order_id": order_id, "tasks_generated": len(tasks)}


@router.get("/stores/{store_id}/tasks")
async def list_store_tasks(
    store_id: str,
    status: Optional[str] = Query(None, description="pending/in_progress/done/overdue"),
    owner_role: Optional[str] = Query(None, description="kitchen/service/decor/purchase/manager"),
    due_date: Optional[str] = Query(None, description="YYYY-MM-DD，筛选截止日当天"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """跨订单执行任务视图（SM 任务清单）"""
    stmt = (
        select(ExecutionTask, BanquetOrder.banquet_date, BanquetOrder.banquet_type)
        .join(BanquetOrder, ExecutionTask.banquet_order_id == BanquetOrder.id)
        .where(BanquetOrder.store_id == store_id)
    )
    if status:
        try:
            stmt = stmt.where(ExecutionTask.task_status == TaskStatusEnum(status))
        except ValueError:
            pass
    if owner_role:
        from src.models.banquet import TaskOwnerRoleEnum
        try:
            stmt = stmt.where(ExecutionTask.owner_role == TaskOwnerRoleEnum(owner_role))
        except ValueError:
            pass
    if due_date:
        from datetime import date as _date
        try:
            d = _date.fromisoformat(due_date)
            stmt = stmt.where(func.date(ExecutionTask.due_time) == d)
        except ValueError:
            pass

    stmt = stmt.order_by(ExecutionTask.due_time)
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "task_id":       t.id,
            "task_name":     t.task_name,
            "task_type":     t.task_type,
            "owner_role":    t.owner_role.value,
            "due_time":      t.due_time.isoformat() if t.due_time else None,
            "status":        t.task_status.value,
            "completed_at":  t.completed_at.isoformat() if t.completed_at else None,
            "order_id":      t.banquet_order_id,
            "banquet_date":  banquet_date.isoformat() if banquet_date else None,
            "banquet_type":  banquet_type.value if banquet_type else None,
        }
        for t, banquet_date, banquet_type in rows
    ]


# ────────── 报价单 ────────────────────────────────────────────────────────────

class QuoteCreateReq(BaseModel):
    people_count: int = Field(ge=1)
    table_count: int = Field(ge=1)
    quoted_amount_yuan: float = Field(gt=0)
    package_id: Optional[str] = None
    valid_days: int = Field(default=7, ge=1, le=90)
    menu_snapshot: Optional[dict] = None


@router.get("/stores/{store_id}/leads/{lead_id}/quotes")
async def list_lead_quotes(
    store_id: str,
    lead_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """线索报价单列表"""
    # verify lead belongs to store
    lead_result = await db.execute(
        select(BanquetLead.id).where(
            and_(BanquetLead.id == lead_id, BanquetLead.store_id == store_id)
        )
    )
    if not lead_result.first():
        raise HTTPException(status_code=404, detail="线索不存在")

    result = await db.execute(
        select(BanquetQuote)
        .where(BanquetQuote.lead_id == lead_id)
        .order_by(BanquetQuote.created_at.desc())
    )
    quotes = result.scalars().all()
    return [
        {
            "quote_id":           q.id,
            "people_count":       q.people_count,
            "table_count":        q.table_count,
            "quoted_amount_yuan": q.quoted_amount_fen / 100,
            "valid_until":        q.valid_until.isoformat() if q.valid_until else None,
            "is_accepted":        q.is_accepted,
            "package_id":         q.package_id,
            "created_at":         q.created_at.isoformat() if q.created_at else None,
        }
        for q in quotes
    ]


@router.post("/stores/{store_id}/leads/{lead_id}/quotes", status_code=201)
async def create_lead_quote(
    store_id: str,
    lead_id: str,
    body: QuoteCreateReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建报价单"""
    lead_result = await db.execute(
        select(BanquetLead.id).where(
            and_(BanquetLead.id == lead_id, BanquetLead.store_id == store_id)
        )
    )
    if not lead_result.first():
        raise HTTPException(status_code=404, detail="线索不存在")

    from datetime import date as _date, timedelta
    valid_until = _date.today() + timedelta(days=body.valid_days)

    quote = BanquetQuote(
        id=str(uuid.uuid4()),
        lead_id=lead_id,
        store_id=store_id,
        package_id=body.package_id,
        people_count=body.people_count,
        table_count=body.table_count,
        quoted_amount_fen=int(body.quoted_amount_yuan * 100),
        menu_snapshot=body.menu_snapshot,
        valid_until=valid_until,
        is_accepted=False,
        created_by=str(current_user.id),
    )
    db.add(quote)
    await db.commit()
    return {
        "quote_id":           quote.id,
        "quoted_amount_yuan": body.quoted_amount_yuan,
        "valid_until":        valid_until.isoformat(),
    }


# ────────── 线索详情 ──────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/leads/{lead_id}")
async def get_lead_detail(
    store_id: str,
    lead_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """线索详情：客户信息 + 跟进时间线 + 报价列表"""
    result = await db.execute(
        select(BanquetLead)
        .options(
            selectinload(BanquetLead.customer),
            selectinload(BanquetLead.followups),
        )
        .where(and_(BanquetLead.id == lead_id, BanquetLead.store_id == store_id))
    )
    lead = result.scalars().first()
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")

    quotes_result = await db.execute(
        select(BanquetQuote)
        .where(BanquetQuote.lead_id == lead_id)
        .order_by(BanquetQuote.created_at.desc())
    )
    quotes = quotes_result.scalars().all()

    followups_data = [
        {
            "followup_id":    f.id,
            "followup_type":  f.followup_type,
            "content":        f.content,
            "stage_before":   f.stage_before.value if f.stage_before else None,
            "stage_after":    f.stage_after.value if f.stage_after else None,
            "next_followup_at": f.next_followup_at.isoformat() if f.next_followup_at else None,
            "created_at":     f.created_at.isoformat() if f.created_at else None,
        }
        for f in sorted(lead.followups, key=lambda x: x.created_at or datetime.min, reverse=True)
    ]
    quotes_data = [
        {
            "quote_id":           q.id,
            "people_count":       q.people_count,
            "table_count":        q.table_count,
            "quoted_amount_yuan": q.quoted_amount_fen / 100,
            "valid_until":        q.valid_until.isoformat() if q.valid_until else None,
            "is_accepted":        q.is_accepted,
            "package_id":         q.package_id,
            "created_at":         q.created_at.isoformat() if q.created_at else None,
        }
        for q in quotes
    ]

    return {
        "lead_id":       lead.id,
        "store_id":      lead.store_id,
        "banquet_type":  lead.banquet_type.value,
        "expected_date": lead.expected_date.isoformat() if lead.expected_date else None,
        "expected_people_count": lead.expected_people_count,
        "expected_budget_yuan":  (lead.expected_budget_fen or 0) / 100,
        "preferred_hall_type":   lead.preferred_hall_type.value if lead.preferred_hall_type else None,
        "source_channel":        lead.source_channel,
        "current_stage":         lead.current_stage.value,
        "stage_label":           _LEAD_STAGE_LABELS.get(lead.current_stage.value, lead.current_stage.value),
        "owner_user_id":         lead.owner_user_id,
        "last_followup_at":      lead.last_followup_at.isoformat() if lead.last_followup_at else None,
        "converted_order_id":    lead.converted_order_id,
        "contact_name":          lead.customer.name if lead.customer else None,
        "contact_phone":         lead.customer.phone if lead.customer else None,
        "followups":             followups_data,
        "quotes":                quotes_data,
    }


# ────────── 报价接受 ──────────────────────────────────────────────────────────

@router.patch("/stores/{store_id}/leads/{lead_id}/quotes/{quote_id}/accept")
async def accept_quote(
    store_id: str,
    lead_id: str,
    quote_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """接受报价单（is_accepted=True）"""
    result = await db.execute(
        select(BanquetQuote)
        .where(and_(BanquetQuote.id == quote_id, BanquetQuote.lead_id == lead_id))
    )
    quote = result.scalars().first()
    if not quote:
        raise HTTPException(status_code=404, detail="报价单不存在")
    if quote.store_id != store_id:
        raise HTTPException(status_code=403, detail="无权操作")

    quote.is_accepted = True
    await db.commit()
    return {
        "quote_id":   quote_id,
        "is_accepted": True,
        "lead_id":    lead_id,
    }


# ────────── 合同管理 ──────────────────────────────────────────────────────────

class ContractSignReq(BaseModel):
    signed_by: Optional[str] = None
    file_url: Optional[str] = None


@router.get("/stores/{store_id}/orders/{order_id}/contract")
async def get_contract(
    store_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """查询订单合同"""
    # verify order belongs to store
    order_result = await db.execute(
        select(BanquetOrder.id).where(
            and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
        )
    )
    if not order_result.first():
        raise HTTPException(status_code=404, detail="订单不存在")

    result = await db.execute(
        select(BanquetContract).where(BanquetContract.banquet_order_id == order_id)
    )
    contract = result.scalars().first()
    if not contract:
        return {"contract": None, "order_id": order_id}

    return {
        "contract": {
            "contract_id":      contract.id,
            "contract_no":      contract.contract_no,
            "contract_status":  contract.contract_status,
            "file_url":         contract.file_url,
            "signed_at":        contract.signed_at.isoformat() if contract.signed_at else None,
            "signed_by":        contract.signed_by,
        },
        "order_id": order_id,
    }


@router.post("/stores/{store_id}/orders/{order_id}/contract", status_code=201)
async def create_contract(
    store_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """为订单创建合同（自动生成合同号，初始状态 draft）"""
    order_result = await db.execute(
        select(BanquetOrder).where(
            and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
        )
    )
    order = order_result.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # idempotent: return existing contract if already created
    existing = await db.execute(
        select(BanquetContract).where(BanquetContract.banquet_order_id == order_id)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="合同已存在")

    contract_no = f"BQ-{store_id}-{datetime.utcnow().strftime('%Y%m%d')}-{order_id[:6].upper()}"
    contract = BanquetContract(
        id=str(uuid.uuid4()),
        banquet_order_id=order_id,
        contract_no=contract_no,
        contract_status="draft",
    )
    db.add(contract)
    await db.commit()
    return {
        "contract_id":     contract.id,
        "contract_no":     contract_no,
        "contract_status": "draft",
    }


@router.patch("/stores/{store_id}/orders/{order_id}/contract/sign")
async def sign_contract(
    store_id: str,
    order_id: str,
    body: ContractSignReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """签约（draft → signed）"""
    order_result = await db.execute(
        select(BanquetOrder.id).where(
            and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
        )
    )
    if not order_result.first():
        raise HTTPException(status_code=404, detail="订单不存在")

    result = await db.execute(
        select(BanquetContract).where(BanquetContract.banquet_order_id == order_id)
    )
    contract = result.scalars().first()
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在，请先创建合同")
    if contract.contract_status == "signed":
        raise HTTPException(status_code=400, detail="合同已签约")

    contract.contract_status = "signed"
    contract.signed_at = datetime.utcnow()
    contract.signed_by = body.signed_by or str(current_user.id)
    if body.file_url:
        contract.file_url = body.file_url
    await db.commit()
    return {
        "contract_id":     contract.id,
        "contract_no":     contract.contract_no,
        "contract_status": "signed",
        "signed_at":       contract.signed_at.isoformat(),
    }


# ────────── 利润快照 ──────────────────────────────────────────────────────────

class ProfitSnapshotReq(BaseModel):
    revenue_yuan:         float = Field(ge=0)
    ingredient_cost_yuan: float = Field(ge=0, default=0)
    labor_cost_yuan:      float = Field(ge=0, default=0)
    material_cost_yuan:   float = Field(ge=0, default=0)
    other_cost_yuan:      float = Field(ge=0, default=0)


@router.get("/stores/{store_id}/profit-snapshots")
async def list_profit_snapshots(
    store_id: str,
    month: Optional[str] = Query(None, description="YYYY-MM，过滤宴会月份"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """门店利润快照列表（含订单基本信息）"""
    stmt = (
        select(BanquetProfitSnapshot, BanquetOrder.banquet_date, BanquetOrder.banquet_type)
        .join(BanquetOrder, BanquetProfitSnapshot.banquet_order_id == BanquetOrder.id)
        .where(BanquetOrder.store_id == store_id)
    )
    if month:
        try:
            y, m = map(int, month.split("-"))
            stmt = stmt.where(
                and_(
                    func.extract("year",  BanquetOrder.banquet_date) == y,
                    func.extract("month", BanquetOrder.banquet_date) == m,
                )
            )
        except (ValueError, AttributeError):
            pass

    stmt = stmt.order_by(BanquetOrder.banquet_date.desc())
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "snapshot_id":            snap.id,
            "order_id":               snap.banquet_order_id,
            "banquet_date":           banquet_date.isoformat() if banquet_date else None,
            "banquet_type":           banquet_type.value if banquet_type else None,
            "revenue_yuan":           snap.revenue_fen / 100,
            "ingredient_cost_yuan":   snap.ingredient_cost_fen / 100,
            "labor_cost_yuan":        snap.labor_cost_fen / 100,
            "material_cost_yuan":     snap.material_cost_fen / 100,
            "other_cost_yuan":        snap.other_cost_fen / 100,
            "gross_profit_yuan":      snap.gross_profit_fen / 100,
            "gross_margin_pct":       snap.gross_margin_pct,
        }
        for snap, banquet_date, banquet_type in rows
    ]


@router.post("/stores/{store_id}/orders/{order_id}/profit-snapshot", status_code=201)
async def create_profit_snapshot(
    store_id: str,
    order_id: str,
    body: ProfitSnapshotReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """录入/更新订单利润快照"""
    order_result = await db.execute(
        select(BanquetOrder.id).where(
            and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
        )
    )
    if not order_result.first():
        raise HTTPException(status_code=404, detail="订单不存在")

    revenue_fen         = int(body.revenue_yuan * 100)
    ingredient_cost_fen = int(body.ingredient_cost_yuan * 100)
    labor_cost_fen      = int(body.labor_cost_yuan * 100)
    material_cost_fen   = int(body.material_cost_yuan * 100)
    other_cost_fen      = int(body.other_cost_yuan * 100)
    total_cost_fen      = ingredient_cost_fen + labor_cost_fen + material_cost_fen + other_cost_fen
    gross_profit_fen    = revenue_fen - total_cost_fen
    gross_margin_pct    = round(gross_profit_fen / revenue_fen * 100, 1) if revenue_fen > 0 else 0.0

    # upsert: update if exists, create otherwise
    existing_result = await db.execute(
        select(BanquetProfitSnapshot).where(BanquetProfitSnapshot.banquet_order_id == order_id)
    )
    snap = existing_result.scalars().first()
    if snap:
        snap.revenue_fen         = revenue_fen
        snap.ingredient_cost_fen = ingredient_cost_fen
        snap.labor_cost_fen      = labor_cost_fen
        snap.material_cost_fen   = material_cost_fen
        snap.other_cost_fen      = other_cost_fen
        snap.gross_profit_fen    = gross_profit_fen
        snap.gross_margin_pct    = gross_margin_pct
    else:
        snap = BanquetProfitSnapshot(
            id=str(uuid.uuid4()),
            banquet_order_id=order_id,
            revenue_fen=revenue_fen,
            ingredient_cost_fen=ingredient_cost_fen,
            labor_cost_fen=labor_cost_fen,
            material_cost_fen=material_cost_fen,
            other_cost_fen=other_cost_fen,
            gross_profit_fen=gross_profit_fen,
            gross_margin_pct=gross_margin_pct,
        )
        db.add(snap)

    await db.commit()
    return {
        "snapshot_id":       snap.id,
        "order_id":          order_id,
        "revenue_yuan":      body.revenue_yuan,
        "gross_profit_yuan": gross_profit_fen / 100,
        "gross_margin_pct":  gross_margin_pct,
    }


# ────────── 厅房管理 ──────────────────────────────────────────────────────────

class HallCreateReq(BaseModel):
    name: str
    hall_type: str
    max_tables: int = 1
    max_people: int
    min_spend_yuan: float = 0
    floor_area_m2: Optional[float] = None
    description: Optional[str] = None


class HallUpdateReq(BaseModel):
    name: Optional[str] = None
    hall_type: Optional[str] = None
    max_tables: Optional[int] = None
    max_people: Optional[int] = None
    min_spend_yuan: Optional[float] = None
    floor_area_m2: Optional[float] = None
    description: Optional[str] = None


@router.get("/stores/{store_id}/halls")
async def list_halls(
    store_id: str,
    active_only: bool = Query(True, description="仅返回在用厅房"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """厅房列表"""
    stmt = select(BanquetHall).where(BanquetHall.store_id == store_id)
    if active_only:
        stmt = stmt.where(BanquetHall.is_active == True)
    stmt = stmt.order_by(BanquetHall.name)
    result = await db.execute(stmt)
    halls = result.scalars().all()
    return [
        {
            "hall_id":        h.id,
            "name":           h.name,
            "hall_type":      h.hall_type.value if h.hall_type else None,
            "max_tables":     h.max_tables,
            "max_people":     h.max_people,
            "min_spend_yuan": h.min_spend_fen / 100,
            "floor_area_m2":  h.floor_area_m2,
            "description":    h.description,
            "is_active":      h.is_active,
        }
        for h in halls
    ]


@router.post("/stores/{store_id}/halls", status_code=201)
async def create_hall(
    store_id: str,
    body: HallCreateReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """创建厅房"""
    try:
        hall_type_enum = BanquetHallType(body.hall_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的厅房类型：{body.hall_type}")

    hall = BanquetHall(
        id=str(uuid.uuid4()),
        store_id=store_id,
        name=body.name,
        hall_type=hall_type_enum,
        max_tables=body.max_tables,
        max_people=body.max_people,
        min_spend_fen=int(body.min_spend_yuan * 100),
        floor_area_m2=body.floor_area_m2,
        description=body.description,
        is_active=True,
    )
    db.add(hall)
    await db.commit()
    return {"hall_id": hall.id, "name": hall.name, "is_active": True}


@router.patch("/stores/{store_id}/halls/{hall_id}")
async def update_hall(
    store_id: str,
    hall_id: str,
    body: HallUpdateReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """编辑厅房信息"""
    result = await db.execute(
        select(BanquetHall).where(
            and_(BanquetHall.id == hall_id, BanquetHall.store_id == store_id)
        )
    )
    hall = result.scalars().first()
    if not hall:
        raise HTTPException(status_code=404, detail="厅房不存在")

    if body.name is not None:
        hall.name = body.name
    if body.hall_type is not None:
        try:
            hall.hall_type = BanquetHallType(body.hall_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的厅房类型：{body.hall_type}")
    if body.max_tables is not None:
        hall.max_tables = body.max_tables
    if body.max_people is not None:
        hall.max_people = body.max_people
    if body.min_spend_yuan is not None:
        hall.min_spend_fen = int(body.min_spend_yuan * 100)
    if body.floor_area_m2 is not None:
        hall.floor_area_m2 = body.floor_area_m2
    if body.description is not None:
        hall.description = body.description

    await db.commit()
    return {"hall_id": hall_id, "updated": True}


@router.delete("/stores/{store_id}/halls/{hall_id}", status_code=200)
async def deactivate_hall(
    store_id: str,
    hall_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """停用厅房（软删除）"""
    result = await db.execute(
        select(BanquetHall).where(
            and_(BanquetHall.id == hall_id, BanquetHall.store_id == store_id)
        )
    )
    hall = result.scalars().first()
    if not hall:
        raise HTTPException(status_code=404, detail="厅房不存在")

    hall.is_active = False
    await db.commit()
    return {"hall_id": hall_id, "is_active": False}


# ────────── 套餐管理 ──────────────────────────────────────────────────────────

class PackageCreateReq(BaseModel):
    name: str
    banquet_type: Optional[str] = None
    suggested_price_yuan: float = Field(ge=0)
    cost_yuan: Optional[float] = None
    target_people_min: int = 1
    target_people_max: int = 999
    description: Optional[str] = None


class PackageUpdateReq(BaseModel):
    name: Optional[str] = None
    banquet_type: Optional[str] = None
    suggested_price_yuan: Optional[float] = None
    cost_yuan: Optional[float] = None
    target_people_min: Optional[int] = None
    target_people_max: Optional[int] = None
    description: Optional[str] = None


@router.get("/stores/{store_id}/packages")
async def list_packages(
    store_id: str,
    active_only: bool = Query(True, description="仅返回上架套餐"),
    banquet_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """套餐列表"""
    stmt = select(MenuPackage).where(MenuPackage.store_id == store_id)
    if active_only:
        stmt = stmt.where(MenuPackage.is_active == True)
    if banquet_type:
        try:
            stmt = stmt.where(MenuPackage.banquet_type == BanquetTypeEnum(banquet_type))
        except ValueError:
            pass
    stmt = stmt.order_by(MenuPackage.suggested_price_fen)
    result = await db.execute(stmt)
    pkgs = result.scalars().all()
    return [
        {
            "package_id":           p.id,
            "name":                 p.name,
            "banquet_type":         p.banquet_type.value if p.banquet_type else None,
            "suggested_price_yuan": p.suggested_price_fen / 100,
            "cost_yuan":            p.cost_fen / 100 if p.cost_fen is not None else None,
            "gross_margin_pct":     round(
                (1 - p.cost_fen / p.suggested_price_fen) * 100, 1
            ) if p.cost_fen and p.suggested_price_fen else None,
            "target_people_min":    p.target_people_min,
            "target_people_max":    p.target_people_max,
            "description":          p.description,
            "is_active":            p.is_active,
        }
        for p in pkgs
    ]


@router.post("/stores/{store_id}/packages", status_code=201)
async def create_package(
    store_id: str,
    body: PackageCreateReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """创建套餐"""
    banquet_type_enum = None
    if body.banquet_type:
        try:
            banquet_type_enum = BanquetTypeEnum(body.banquet_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的宴会类型：{body.banquet_type}")

    pkg = MenuPackage(
        id=str(uuid.uuid4()),
        store_id=store_id,
        banquet_type=banquet_type_enum,
        name=body.name,
        suggested_price_fen=int(body.suggested_price_yuan * 100),
        cost_fen=int(body.cost_yuan * 100) if body.cost_yuan is not None else None,
        target_people_min=body.target_people_min,
        target_people_max=body.target_people_max,
        description=body.description,
        is_active=True,
    )
    db.add(pkg)
    await db.commit()
    return {"package_id": pkg.id, "name": pkg.name, "is_active": True}


@router.patch("/stores/{store_id}/packages/{pkg_id}")
async def update_package(
    store_id: str,
    pkg_id: str,
    body: PackageUpdateReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """编辑套餐信息"""
    result = await db.execute(
        select(MenuPackage).where(
            and_(MenuPackage.id == pkg_id, MenuPackage.store_id == store_id)
        )
    )
    pkg = result.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="套餐不存在")

    if body.name is not None:
        pkg.name = body.name
    if body.banquet_type is not None:
        try:
            pkg.banquet_type = BanquetTypeEnum(body.banquet_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的宴会类型：{body.banquet_type}")
    if body.suggested_price_yuan is not None:
        pkg.suggested_price_fen = int(body.suggested_price_yuan * 100)
    if body.cost_yuan is not None:
        pkg.cost_fen = int(body.cost_yuan * 100)
    if body.target_people_min is not None:
        pkg.target_people_min = body.target_people_min
    if body.target_people_max is not None:
        pkg.target_people_max = body.target_people_max
    if body.description is not None:
        pkg.description = body.description

    await db.commit()
    return {"package_id": pkg_id, "updated": True}


@router.delete("/stores/{store_id}/packages/{pkg_id}", status_code=200)
async def deactivate_package(
    store_id: str,
    pkg_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """下架套餐（软删除）"""
    result = await db.execute(
        select(MenuPackage).where(
            and_(MenuPackage.id == pkg_id, MenuPackage.store_id == store_id)
        )
    )
    pkg = result.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="套餐不存在")

    pkg.is_active = False
    await db.commit()
    return {"package_id": pkg_id, "is_active": False}


# ────────── 结算闭环 ──────────────────────────────────────────────────────────

class SettleOrderReq(BaseModel):
    revenue_yuan: float = Field(ge=0)
    ingredient_cost_yuan: float = Field(ge=0, default=0)
    labor_cost_yuan: float = Field(ge=0, default=0)
    other_cost_yuan: float = Field(ge=0, default=0)


@router.post("/stores/{store_id}/orders/{order_id}/settle", status_code=200)
async def settle_order(
    store_id: str,
    order_id: str,
    body: SettleOrderReq,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """结算宴会订单（completed → settled），同步写入利润快照"""
    result = await db.execute(
        select(BanquetOrder).where(
            and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
        )
    )
    order = result.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.order_status != OrderStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"只有已完成的订单才能结算，当前状态：{order.order_status.value}",
        )

    # 更新订单状态
    order.order_status = OrderStatusEnum.SETTLED

    # upsert 利润快照
    revenue_fen         = int(body.revenue_yuan * 100)
    ingredient_cost_fen = int(body.ingredient_cost_yuan * 100)
    labor_cost_fen      = int(body.labor_cost_yuan * 100)
    other_cost_fen      = int(body.other_cost_yuan * 100)
    total_cost_fen      = ingredient_cost_fen + labor_cost_fen + other_cost_fen
    gross_profit_fen    = revenue_fen - total_cost_fen
    gross_margin_pct    = round(gross_profit_fen / revenue_fen * 100, 1) if revenue_fen > 0 else 0.0

    snap_result = await db.execute(
        select(BanquetProfitSnapshot).where(BanquetProfitSnapshot.banquet_order_id == order_id)
    )
    snap = snap_result.scalars().first()
    if snap:
        snap.revenue_fen         = revenue_fen
        snap.ingredient_cost_fen = ingredient_cost_fen
        snap.labor_cost_fen      = labor_cost_fen
        snap.other_cost_fen      = other_cost_fen
        snap.gross_profit_fen    = gross_profit_fen
        snap.gross_margin_pct    = gross_margin_pct
    else:
        snap = BanquetProfitSnapshot(
            id=str(uuid.uuid4()),
            banquet_order_id=order_id,
            revenue_fen=revenue_fen,
            ingredient_cost_fen=ingredient_cost_fen,
            labor_cost_fen=labor_cost_fen,
            material_cost_fen=0,
            other_cost_fen=other_cost_fen,
            gross_profit_fen=gross_profit_fen,
            gross_margin_pct=gross_margin_pct,
        )
        db.add(snap)

    await db.commit()
    return {
        "order_id":          order_id,
        "status":            "settled",
        "snapshot_id":       snap.id,
        "gross_profit_yuan": gross_profit_fen / 100,
        "gross_margin_pct":  gross_margin_pct,
    }


# ────────── 推送通知 ──────────────────────────────────────────────────────────

@router.post("/stores/{store_id}/push/scan", status_code=200)
async def push_scan(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """扫描并推送：D-7/D-1 宴会提醒、逾期任务告警、停滞线索提醒"""
    from datetime import timedelta
    import json

    now = datetime.utcnow()
    today = now.date()
    d1 = today + timedelta(days=1)
    d7 = today + timedelta(days=7)

    details = []

    # D-1 / D-7 宴会提醒
    for target_date, label in [(d1, "D-1"), (d7, "D-7")]:
        upcoming = await db.execute(
            select(BanquetOrder).where(
                and_(
                    BanquetOrder.store_id == store_id,
                    BanquetOrder.banquet_date == target_date,
                    BanquetOrder.order_status == OrderStatusEnum.CONFIRMED,
                )
            )
        )
        for order in upcoming.scalars().all():
            details.append({
                "type":      "banquet_reminder",
                "target_id": order.id,
                "label":     label,
                "content":   f"【{label}提醒】{order.banquet_type.value} 宴会将于 {target_date} 举行，请做好准备。",
                "status":    "sent",
            })

    # 逾期任务告警
    overdue_result = await db.execute(
        select(ExecutionTask).join(
            BanquetOrder, ExecutionTask.banquet_order_id == BanquetOrder.id
        ).where(
            and_(
                BanquetOrder.store_id == store_id,
                ExecutionTask.due_time < now,
                ExecutionTask.task_status.notin_([
                    TaskStatusEnum.DONE, TaskStatusEnum.VERIFIED, TaskStatusEnum.CLOSED,
                ]),
            )
        ).limit(20)
    )
    for task in overdue_result.scalars().all():
        details.append({
            "type":      "task_overdue",
            "target_id": task.id,
            "label":     "逾期告警",
            "content":   f"【任务逾期】{task.task_name} 已逾期，请及时处理。",
            "status":    "sent",
        })

    # 停滞线索提醒（7天未跟进）
    stale_cutoff = now - timedelta(days=7)
    stale_result = await db.execute(
        select(BanquetLead).where(
            and_(
                BanquetLead.store_id == store_id,
                BanquetLead.current_stage.notin_([
                    LeadStageEnum.WON, LeadStageEnum.LOST,
                ]),
                BanquetLead.last_followup_at < stale_cutoff,
            )
        ).limit(20)
    )
    for lead in stale_result.scalars().all():
        details.append({
            "type":      "lead_stale",
            "target_id": lead.id,
            "label":     "线索停滞",
            "content":   f"【线索停滞】{lead.banquet_type.value} 线索已超7天未跟进，请尽快联系客户。",
            "status":    "sent",
        })

    # 写入 Redis 推送日志
    try:
        from src.core.dependencies import get_redis
        redis = await get_redis()
        log_key = f"banquet:push_log:{store_id}"
        existing_raw = await redis.get(log_key)
        existing = json.loads(existing_raw) if existing_raw else []
        new_records = [
            {
                "record_id": str(uuid.uuid4()),
                "push_type": d["type"],
                "target_id": d["target_id"],
                "content":   d["content"],
                "status":    d["status"],
                "sent_at":   now.isoformat(),
            }
            for d in details
        ]
        combined = (new_records + existing)[:200]   # cap at 200 records
        await redis.setex(log_key, 30 * 24 * 3600, json.dumps(combined))
    except Exception:
        pass   # push log is best-effort

    return {
        "sent":    len(details),
        "skipped": 0,
        "details": details,
    }


@router.get("/stores/{store_id}/push/records")
async def list_push_records(
    store_id: str,
    _: User = Depends(get_current_user),
):
    """推送记录列表（最近30天，读 Redis）"""
    import json
    try:
        from src.core.dependencies import get_redis
        redis = await get_redis()
        raw = await redis.get(f"banquet:push_log:{store_id}")
        records = json.loads(raw) if raw else []
    except Exception:
        records = []
    return {"records": records, "total": len(records)}


# ────────── Agent 接口 ────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/agent/followup-scan")
async def agent_followup_scan(
    store_id: str,
    dry_run: bool = Query(True, description="true=仅扫描不写库"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """跟进提醒 Agent：扫描停滞线索 → 企微提醒文本"""
    results = await _followup.scan_stale_leads(store_id=store_id, db=db, dry_run=dry_run)
    return {"store_id": store_id, "dry_run": dry_run, "stale_lead_count": len(results), "items": results}


@router.get("/stores/{store_id}/agent/quote-recommend")
async def agent_quote_recommend(
    store_id: str,
    people_count: int = Query(..., ge=1),
    budget_yuan: float = Query(..., gt=0),
    banquet_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """报价推荐 Agent：按人数+预算推荐套餐（含¥毛利估算）"""
    return await _quotation.recommend_packages(
        store_id=store_id,
        people_count=people_count,
        budget_fen=int(budget_yuan * 100),
        banquet_type=banquet_type,
        db=db,
    )


@router.get("/stores/{store_id}/agent/hall-recommend")
async def agent_hall_recommend(
    store_id: str,
    target_date: str = Query(..., description="YYYY-MM-DD"),
    slot_name: str = Query("all_day", description="lunch/dinner/all_day"),
    people_count: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """排期推荐 Agent：查可用厅房，排除冲突档期"""
    from datetime import date
    d = date.fromisoformat(target_date)
    return await _scheduling.recommend_halls(
        store_id=store_id, target_date=d, slot_name=slot_name, people_count=people_count, db=db
    )


@router.post("/stores/{store_id}/orders/{order_id}/review")
async def agent_generate_review(
    store_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """复盘 Agent：宴会完成后自动生成复盘草稿（含¥收入/利润分析）"""
    result = await db.execute(
        select(BanquetOrder).where(
            and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
        )
    )
    order = result.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.order_status not in {OrderStatusEnum.COMPLETED, OrderStatusEnum.SETTLED}:
        raise HTTPException(status_code=400, detail="订单尚未完成")
    return await _review.generate_review(order=order, db=db)


# ────────── 驾驶舱 ────────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/dashboard")
async def banquet_dashboard(
    store_id: str,
    year:  Optional[int] = Query(None, description="年份（整数，与 month 整数配合使用）"),
    month: Optional[str] = Query(None, description="月份：可为整数 '3' 或 YYYY-MM 字符串 '2026-03'"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """宴会经营驾驶舱：本月收入/订单数/转化率/档期利用率"""
    from datetime import date as _date
    # 解析年月：支持 ?year=2026&month=3 和 ?month=2026-03 两种形式
    if month and "-" in str(month):
        y, m = map(int, month.split("-"))
    elif year and month:
        y, m = year, int(month)
    elif month:
        today = _date.today()
        y, m = today.year, int(month)
    else:
        today = _date.today()
        y, m = today.year, today.month

    # KPI 日报聚合
    kpi_result = await db.execute(
        select(
            func.sum(BanquetKpiDaily.revenue_fen).label("revenue_fen"),
            func.sum(BanquetKpiDaily.gross_profit_fen).label("profit_fen"),
            func.sum(BanquetKpiDaily.order_count).label("order_count"),
            func.sum(BanquetKpiDaily.lead_count).label("lead_count"),
            func.avg(BanquetKpiDaily.hall_utilization_pct).label("avg_utilization"),
        ).where(
            and_(
                BanquetKpiDaily.store_id == store_id,
                func.extract("year", BanquetKpiDaily.stat_date) == y,
                func.extract("month", BanquetKpiDaily.stat_date) == m,
            )
        )
    )
    row = kpi_result.first()
    revenue_yuan = (row.revenue_fen or 0) / 100
    profit_yuan  = (row.profit_fen  or 0) / 100
    order_count  = row.order_count  or 0
    lead_count   = row.lead_count   or 0
    utilization  = round(row.avg_utilization or 0, 1)
    conversion   = round(order_count / lead_count * 100, 1) if lead_count > 0 else 0

    return {
        "store_id": store_id,
        "year": y,
        "month": m,
        # Phase 2 frontend fields (DashboardData interface)
        "revenue_yuan":     revenue_yuan,
        "gross_margin_pct": round(profit_yuan / revenue_yuan * 100, 1) if revenue_yuan > 0 else 0,
        "order_count":      order_count,
        "conversion_rate":  conversion,       # alias: conversion_rate_pct
        "room_utilization": utilization,      # alias: hall_utilization_pct
        # Legacy / additional fields
        "gross_profit_yuan":   profit_yuan,
        "lead_count":          lead_count,
        "conversion_rate_pct": conversion,
        "hall_utilization_pct": utilization,
        "summary": (
            f"{y}年{m}月宴会收入¥{revenue_yuan:.0f}，"
            f"毛利¥{profit_yuan:.0f}，"
            f"转化率{conversion}%，档期利用率{utilization}%。"
        ),
    }
