"""
宴会管理 Agent — Phase 9 核心路由
路由前缀：/api/v1/banquet-agent

与现有 banquet.py（吉日/BEO）并存，专注 CRM+线索+订单+Agent 能力。
"""
import uuid
from datetime import date as date_type, datetime
from typing import Optional
from fastapi import APIRouter, Body, Depends, Query, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.user import User
from src.models.banquet import (
    BanquetHall, BanquetCustomer, BanquetLead, BanquetOrder,
    MenuPackage, ExecutionTask, ExecutionTemplate, ExecutionException, BanquetPaymentRecord,
    BanquetHallBooking, BanquetKpiDaily, BanquetQuote,
    BanquetContract, BanquetProfitSnapshot, LeadFollowupRecord,
    LeadStageEnum, OrderStatusEnum, BanquetTypeEnum,
    BanquetHallType, PaymentTypeEnum, DepositStatusEnum,
    TaskStatusEnum, TaskOwnerRoleEnum, BanquetAgentActionLog, BanquetRevenueTarget,
    BanquetOrderReview, BanquetAgentTypeEnum,
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


class LostReq(BaseModel):
    lost_reason:    str
    followup_note:  Optional[str] = None


@router.patch("/stores/{store_id}/leads/{lead_id}/lost")
async def mark_lead_lost(
    store_id: str,
    lead_id: str,
    body: LostReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将线索标记为流失，记录流失原因"""
    result = await db.execute(
        select(BanquetLead).where(
            and_(BanquetLead.id == lead_id, BanquetLead.store_id == store_id)
        )
    )
    lead = result.scalars().first()
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")
    if lead.current_stage == LeadStageEnum.LOST:
        raise HTTPException(status_code=400, detail="线索已标记为流失")

    stage_before = lead.current_stage
    lead.current_stage = LeadStageEnum.LOST
    lead.lost_reason = body.lost_reason
    lead.last_followup_at = datetime.utcnow()

    record = LeadFollowupRecord(
        id=str(uuid.uuid4()),
        lead_id=lead_id,
        followup_type="other",
        content=body.followup_note or f"流失原因：{body.lost_reason}",
        stage_before=stage_before,
        stage_after=LeadStageEnum.LOST,
        created_by=str(current_user.id),
    )
    db.add(record)
    await db.commit()
    return {
        "lead_id": lead_id,
        "current_stage": "lost",
        "lost_reason": body.lost_reason,
    }


@router.get("/stores/{store_id}/leads/followup-due")
async def list_followup_due(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """返回今日到期 + 已逾期的跟进线索（排除 won/lost）"""
    from datetime import timedelta
    now = datetime.utcnow()
    tomorrow = now + timedelta(hours=24)
    stale_cutoff = now - timedelta(days=7)
    excluded = [LeadStageEnum.WON, LeadStageEnum.LOST]

    # due_today: next_followup_at is set and <= tomorrow
    result_due = await db.execute(
        select(BanquetLead).where(
            and_(
                BanquetLead.store_id == store_id,
                BanquetLead.current_stage.not_in(excluded),
                BanquetLead.next_followup_at.isnot(None),
                BanquetLead.next_followup_at <= tomorrow,
            )
        ).order_by(BanquetLead.next_followup_at)
    )
    due_leads = result_due.scalars().all()

    # stale: no recent followup and next_followup_at not set or already past stale_cutoff
    result_stale = await db.execute(
        select(BanquetLead).where(
            and_(
                BanquetLead.store_id == store_id,
                BanquetLead.current_stage.not_in(excluded),
                BanquetLead.last_followup_at < stale_cutoff,
                BanquetLead.next_followup_at.is_(None),
            )
        ).order_by(BanquetLead.last_followup_at)
    )
    stale_leads = result_stale.scalars().all()

    # merge, dedup by id
    seen = set()
    all_leads = []
    for lead in list(due_leads) + list(stale_leads):
        if lead.id not in seen:
            seen.add(lead.id)
            all_leads.append(lead)

    def _serialize(lead: BanquetLead, is_overdue: bool):
        return {
            "lead_id":           lead.id,
            "banquet_type":      lead.banquet_type.value if hasattr(lead.banquet_type, "value") else str(lead.banquet_type),
            "current_stage":     lead.current_stage.value,
            "expected_date":     lead.expected_date.isoformat() if lead.expected_date else None,
            "last_followup_at":  lead.last_followup_at.isoformat() if lead.last_followup_at else None,
            "next_followup_at":  lead.next_followup_at.isoformat() if lead.next_followup_at else None,
            "is_overdue":        is_overdue,
            "customer_id":       lead.customer_id,
        }

    due_ids = {l.id for l in due_leads}
    return {
        "due_today":  [_serialize(l, l.next_followup_at is not None and l.next_followup_at < now) for l in due_leads],
        "overdue":    [_serialize(l, True) for l in stale_leads if l.id not in due_ids],
        "total":      len(seen),
    }


# ────────── 分析看板 ──────────────────────────────────────────────────────────

_STAGE_LABELS = {
    "new":              "初步询价",
    "contacted":        "已联系",
    "visit_scheduled":  "预约看厅",
    "quoted":           "已报价",
    "waiting_decision": "等待决策",
    "deposit_pending":  "待付定金",
    "won":              "成交",
    "lost":             "流失",
}
_FUNNEL_STAGES = [
    "new", "contacted", "visit_scheduled", "quoted",
    "waiting_decision", "deposit_pending", "won",
]


@router.get("/stores/{store_id}/analytics/funnel")
async def get_conversion_funnel(
    store_id: str,
    month: Optional[str] = Query(None, description="YYYY-MM，默认当月"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """阶段转化漏斗：各阶段线索数 + 逐级转化率"""
    from datetime import timedelta
    if month:
        try:
            period_start = datetime.strptime(month, "%Y-%m").replace(day=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="month 格式应为 YYYY-MM")
    else:
        today = datetime.utcnow()
        period_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # next month start
    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1)

    # count leads created in period, grouped by stage (including LOST)
    result = await db.execute(
        select(BanquetLead.current_stage, func.count(BanquetLead.id)).where(
            and_(
                BanquetLead.store_id == store_id,
                BanquetLead.created_at >= period_start,
                BanquetLead.created_at < period_end,
            )
        ).group_by(BanquetLead.current_stage)
    )
    counts_raw = {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1]
                  for row in result.all()}

    total_leads = sum(counts_raw.values())
    won_count   = counts_raw.get("won", 0)
    lost_count  = counts_raw.get("lost", 0)

    # build funnel with conversion rates relative to previous stage
    stages = []
    prev_count = None
    for stage in _FUNNEL_STAGES:
        count = counts_raw.get(stage, 0)
        conversion_rate = round(count / prev_count, 4) if prev_count and prev_count > 0 else None
        stages.append({
            "stage":           stage,
            "label":           _STAGE_LABELS.get(stage, stage),
            "count":           count,
            "conversion_rate": conversion_rate,
        })
        prev_count = count

    return {
        "period":                   period_start.strftime("%Y-%m"),
        "stages":                   stages,
        "total_leads":              total_leads,
        "won_count":                won_count,
        "lost_count":               lost_count,
        "overall_conversion_rate":  round(won_count / total_leads, 4) if total_leads > 0 else 0.0,
    }


@router.get("/stores/{store_id}/analytics/revenue-forecast")
async def get_revenue_forecast(
    store_id: str,
    months: int = Query(3, ge=1, le=12, description="预测月数"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """未来 N 个月已确认订单的营收预测（按宴会日期归属月份）"""
    from datetime import timedelta
    today = datetime.utcnow().date()
    # start from current month
    start = today.replace(day=1)

    # end: start + months
    year, mo = start.year, start.month
    for _ in range(months):
        mo += 1
        if mo > 12:
            mo = 1
            year += 1
    end = date_type(year, mo, 1)

    result = await db.execute(
        select(BanquetOrder).where(
            and_(
                BanquetOrder.store_id == store_id,
                BanquetOrder.order_status.in_([
                    OrderStatusEnum.CONFIRMED,
                    OrderStatusEnum.PREPARING,
                    OrderStatusEnum.IN_PROGRESS,
                ]),
                BanquetOrder.banquet_date >= start,
                BanquetOrder.banquet_date < end,
            )
        )
    )
    orders = result.scalars().all()

    # bucket by month
    buckets: dict = {}
    for order in orders:
        key = order.banquet_date.strftime("%Y-%m")
        if key not in buckets:
            buckets[key] = {"month": key, "confirmed_revenue_yuan": 0.0, "order_count": 0}
        buckets[key]["confirmed_revenue_yuan"] += round(order.total_amount_fen / 100, 2)
        buckets[key]["order_count"] += 1

    # fill missing months with zeros
    forecast = []
    y, m = start.year, start.month
    for _ in range(months):
        key = f"{y:04d}-{m:02d}"
        forecast.append(buckets.get(key, {"month": key, "confirmed_revenue_yuan": 0.0, "order_count": 0}))
        m += 1
        if m > 12:
            m = 1
            y += 1

    return {"forecast": forecast}


@router.get("/stores/{store_id}/analytics/lost-analysis")
async def get_lost_analysis(
    store_id: str,
    month: Optional[str] = Query(None, description="YYYY-MM，默认当月"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """流失原因分析：按 lost_reason 分组统计"""
    if month:
        try:
            period_start = datetime.strptime(month, "%Y-%m").replace(day=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="month 格式应为 YYYY-MM")
    else:
        today = datetime.utcnow()
        period_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1)

    result = await db.execute(
        select(BanquetLead.lost_reason, func.count(BanquetLead.id)).where(
            and_(
                BanquetLead.store_id == store_id,
                BanquetLead.current_stage == LeadStageEnum.LOST,
                BanquetLead.created_at >= period_start,
                BanquetLead.created_at < period_end,
            )
        ).group_by(BanquetLead.lost_reason)
    )
    rows = result.all()
    total = sum(r[1] for r in rows)

    reasons = sorted(
        [
            {
                "reason":  r[0] or "未说明",
                "count":   r[1],
                "pct":     round(r[1] / total * 100, 1) if total > 0 else 0.0,
            }
            for r in rows
        ],
        key=lambda x: -x["count"],
    )
    return {
        "period":      period_start.strftime("%Y-%m"),
        "total_lost":  total,
        "reasons":     reasons,
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


# ────────── BEO / 应收账款 / KPI 同步 ─────────────────────────────────────────

@router.get("/stores/{store_id}/orders/{order_id}/beo")
async def get_order_beo(
    store_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """生成宴会执行单（BEO）：订单 + 任务（按角色分组）+ 厅房 + 套餐"""
    result = await db.execute(
        select(BanquetOrder).options(
            selectinload(BanquetOrder.tasks),
            selectinload(BanquetOrder.package),
            selectinload(BanquetOrder.bookings),
        ).where(
            and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
        )
    )
    order = result.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # group tasks by owner_role
    tasks_by_role: dict = {}
    for task in order.tasks:
        role = task.owner_role or "other"
        if role not in tasks_by_role:
            tasks_by_role[role] = []
        tasks_by_role[role].append({
            "task_id":   task.id,
            "task_name": task.task_name,
            "due_time":  task.due_time.isoformat() if task.due_time else None,
            "status":    task.task_status.value if hasattr(task.task_status, "value") else str(task.task_status),
        })

    # hall name from first booking
    hall_name = None
    if order.bookings:
        booking = order.bookings[0]
        hall_result = await db.execute(
            select(BanquetHall).where(BanquetHall.id == booking.hall_id)
        )
        hall = hall_result.scalars().first()
        hall_name = hall.name if hall else None

    package_name = order.package.name if order.package else None

    balance_fen = order.total_amount_fen - order.paid_fen

    return {
        "order_id":          order.id,
        "banquet_type":      order.banquet_type.value,
        "banquet_date":      order.banquet_date.isoformat(),
        "hall_name":         hall_name,
        "people_count":      order.people_count,
        "table_count":       order.table_count,
        "contact_name":      order.contact_name,
        "contact_phone":     order.contact_phone,
        "package_name":      package_name,
        "total_amount_yuan": round(order.total_amount_fen / 100, 2),
        "paid_yuan":         round(order.paid_fen / 100, 2),
        "balance_yuan":      round(balance_fen / 100, 2),
        "tasks_by_role":     tasks_by_role,
        "remark":            order.remark,
    }


@router.get("/stores/{store_id}/receivables")
async def get_receivables(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """应收账款：已确认且存在未收余款的订单"""
    from datetime import date as _date
    active_statuses = [
        OrderStatusEnum.CONFIRMED,
        OrderStatusEnum.PREPARING,
        OrderStatusEnum.IN_PROGRESS,
    ]
    result = await db.execute(
        select(BanquetOrder).where(
            and_(
                BanquetOrder.store_id == store_id,
                BanquetOrder.order_status.in_(active_statuses),
                BanquetOrder.total_amount_fen > BanquetOrder.paid_fen,
            )
        ).order_by(BanquetOrder.banquet_date)
    )
    orders = result.scalars().all()

    today = _date.today()
    items = []
    total_outstanding_fen = 0
    for o in orders:
        balance_fen = o.total_amount_fen - o.paid_fen
        total_outstanding_fen += balance_fen
        days_until = (o.banquet_date - today).days
        items.append({
            "order_id":          o.id,
            "banquet_type":      o.banquet_type.value,
            "banquet_date":      o.banquet_date.isoformat(),
            "contact_name":      o.contact_name,
            "total_amount_yuan": round(o.total_amount_fen / 100, 2),
            "paid_yuan":         round(o.paid_fen / 100, 2),
            "balance_yuan":      round(balance_fen / 100, 2),
            "deposit_status":    o.deposit_status.value,
            "days_until_event":  days_until,
        })

    return {
        "total_outstanding_yuan": round(total_outstanding_fen / 100, 2),
        "order_count":            len(items),
        "orders":                 items,
    }


@router.post("/stores/{store_id}/kpi/sync")
async def sync_kpi(
    store_id: str,
    sync_date: Optional[str] = Query(None, description="YYYY-MM-DD，默认今天"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """将当日宴会真实数据聚合写入 BanquetKpiDaily（upsert）"""
    from datetime import date as _date
    if sync_date:
        try:
            target_date = _date.fromisoformat(sync_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="date 格式应为 YYYY-MM-DD")
    else:
        target_date = _date.today()

    # order_count + revenue for target_date
    order_result = await db.execute(
        select(func.count(BanquetOrder.id), func.sum(BanquetOrder.total_amount_fen)).where(
            and_(
                BanquetOrder.store_id == store_id,
                BanquetOrder.banquet_date == target_date,
                BanquetOrder.order_status.in_([
                    OrderStatusEnum.CONFIRMED,
                    OrderStatusEnum.PREPARING,
                    OrderStatusEnum.IN_PROGRESS,
                    OrderStatusEnum.COMPLETED,
                    OrderStatusEnum.SETTLED,
                ]),
            )
        )
    )
    order_row = order_result.first()
    order_count = order_row[0] or 0
    revenue_fen = order_row[1] or 0

    # gross_profit from profit snapshots joined to orders on target_date
    from src.models.banquet import BanquetProfitSnapshot
    profit_result = await db.execute(
        select(func.sum(BanquetProfitSnapshot.gross_profit_fen)).join(
            BanquetOrder, BanquetProfitSnapshot.banquet_order_id == BanquetOrder.id
        ).where(
            and_(
                BanquetOrder.store_id == store_id,
                BanquetOrder.banquet_date == target_date,
            )
        )
    )
    gross_profit_fen = profit_result.scalar() or 0

    # lead_count: leads created in last 30 days
    from datetime import timedelta
    month_ago = datetime.utcnow() - timedelta(days=30)
    lead_result = await db.execute(
        select(func.count(BanquetLead.id)).where(
            and_(
                BanquetLead.store_id == store_id,
                BanquetLead.created_at >= month_ago,
            )
        )
    )
    lead_count = lead_result.scalar() or 0

    # conversion_rate: won / total (last 30 days)
    won_result = await db.execute(
        select(func.count(BanquetLead.id)).where(
            and_(
                BanquetLead.store_id == store_id,
                BanquetLead.created_at >= month_ago,
                BanquetLead.current_stage == LeadStageEnum.WON,
            )
        )
    )
    won_count = won_result.scalar() or 0
    conversion_rate_pct = round(won_count / lead_count * 100, 1) if lead_count > 0 else 0.0

    # upsert
    existing_result = await db.execute(
        select(BanquetKpiDaily).where(
            and_(BanquetKpiDaily.store_id == store_id, BanquetKpiDaily.stat_date == target_date)
        )
    )
    kpi = existing_result.scalars().first()
    if kpi:
        kpi.order_count          = order_count
        kpi.revenue_fen          = revenue_fen
        kpi.gross_profit_fen     = gross_profit_fen
        kpi.lead_count           = lead_count
        kpi.conversion_rate_pct  = conversion_rate_pct
    else:
        kpi = BanquetKpiDaily(
            id=str(uuid.uuid4()),
            store_id=store_id,
            stat_date=target_date,
            order_count=order_count,
            revenue_fen=revenue_fen,
            gross_profit_fen=gross_profit_fen,
            lead_count=lead_count,
            conversion_rate_pct=conversion_rate_pct,
        )
        db.add(kpi)
    await db.commit()

    return {
        "synced":               True,
        "date":                 target_date.isoformat(),
        "order_count":          order_count,
        "revenue_yuan":         round(revenue_fen / 100, 2),
        "gross_profit_yuan":    round(gross_profit_fen / 100, 2),
        "lead_count":           lead_count,
        "conversion_rate_pct":  conversion_rate_pct,
    }


# ────────── Phase 9 端点 ───────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/monthly-trend")
async def get_monthly_trend(
    store_id: str,
    months: int = Query(6, ge=1, le=24, description="返回最近 N 个月"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """近 N 月营收/订单数/毛利走势（按宴会日期聚合）"""
    from datetime import date as _date
    from dateutil.relativedelta import relativedelta  # type: ignore

    today = _date.today()
    # Build list of (year, month) from oldest → newest
    month_list = []
    for i in range(months - 1, -1, -1):
        d = today - relativedelta(months=i)
        month_list.append((d.year, d.month))

    # Revenue + order count per month
    revenue_rows = await db.execute(
        select(
            func.extract("year",  BanquetOrder.banquet_date).label("yr"),
            func.extract("month", BanquetOrder.banquet_date).label("mo"),
            func.count(BanquetOrder.id).label("cnt"),
            func.sum(BanquetOrder.total_amount_fen).label("rev"),
        ).where(
            and_(
                BanquetOrder.store_id == store_id,
                BanquetOrder.order_status.in_([
                    OrderStatusEnum.CONFIRMED,
                    OrderStatusEnum.PREPARING,
                    OrderStatusEnum.IN_PROGRESS,
                    OrderStatusEnum.COMPLETED,
                    OrderStatusEnum.SETTLED,
                ]),
            )
        ).group_by("yr", "mo")
    )
    rev_map: dict[tuple, tuple] = {}
    for row in revenue_rows.all():
        rev_map[(int(row.yr), int(row.mo))] = (int(row.cnt), int(row.rev or 0))

    # Gross profit per month via BanquetProfitSnapshot → BanquetOrder
    from src.models.banquet import BanquetProfitSnapshot as _BPS
    profit_rows = await db.execute(
        select(
            func.extract("year",  BanquetOrder.banquet_date).label("yr"),
            func.extract("month", BanquetOrder.banquet_date).label("mo"),
            func.sum(_BPS.gross_profit_fen).label("gp"),
        ).join(
            BanquetOrder, _BPS.banquet_order_id == BanquetOrder.id
        ).where(
            BanquetOrder.store_id == store_id,
        ).group_by("yr", "mo")
    )
    gp_map: dict[tuple, int] = {}
    for row in profit_rows.all():
        gp_map[(int(row.yr), int(row.mo))] = int(row.gp or 0)

    result = []
    for (yr, mo) in month_list:
        month_str = f"{yr:04d}-{mo:02d}"
        cnt, rev = rev_map.get((yr, mo), (0, 0))
        gp = gp_map.get((yr, mo), 0)
        result.append({
            "month":              month_str,
            "order_count":        cnt,
            "revenue_yuan":       round(rev / 100, 2),
            "gross_profit_yuan":  round(gp / 100, 2),
        })

    return {"months": result}


@router.get("/stores/{store_id}/packages/{pkg_id}/performance")
async def get_package_performance(
    store_id: str,
    pkg_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """套餐效益分析：使用次数 / 总营收 / 平均毛利率"""
    # Validate package exists
    pkg_result = await db.execute(
        select(MenuPackage).where(MenuPackage.id == pkg_id)
    )
    pkg = pkg_result.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="套餐不存在")

    # Usage count + total revenue
    usage_result = await db.execute(
        select(
            func.count(BanquetOrder.id).label("cnt"),
            func.sum(BanquetOrder.total_amount_fen).label("rev"),
            func.max(BanquetOrder.banquet_date).label("last_date"),
        ).where(
            and_(
                BanquetOrder.store_id == store_id,
                BanquetOrder.package_id == pkg_id,
                BanquetOrder.order_status.in_([
                    OrderStatusEnum.CONFIRMED,
                    OrderStatusEnum.PREPARING,
                    OrderStatusEnum.IN_PROGRESS,
                    OrderStatusEnum.COMPLETED,
                    OrderStatusEnum.SETTLED,
                ]),
            )
        )
    )
    usage_row = usage_result.first()
    usage_count = int(usage_row.cnt or 0)
    total_revenue_fen = int(usage_row.rev or 0)
    last_used_date = usage_row.last_date

    # Average gross margin from profit snapshots
    from src.models.banquet import BanquetProfitSnapshot as _BPS
    margin_result = await db.execute(
        select(func.avg(_BPS.gross_margin_pct)).join(
            BanquetOrder, _BPS.banquet_order_id == BanquetOrder.id
        ).where(
            and_(
                BanquetOrder.store_id == store_id,
                BanquetOrder.package_id == pkg_id,
            )
        )
    )
    avg_margin = margin_result.scalar()

    return {
        "package_id":          pkg_id,
        "package_name":        pkg.name,
        "usage_count":         usage_count,
        "total_revenue_yuan":  round(total_revenue_fen / 100, 2),
        "avg_gross_margin_pct": round(float(avg_margin), 1) if avg_margin else None,
        "last_used_date":      last_used_date.isoformat() if last_used_date else None,
    }


@router.get("/stores/{store_id}/tasks/upcoming")
async def get_upcoming_tasks(
    store_id: str,
    days: int = Query(7, ge=1, le=30, description="未来 N 天"),
    owner_role: Optional[str] = Query(None, description="kitchen/service/decor/purchase/manager"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """未来 N 天执行任务，按日期分组（SM 任务看板）"""
    from datetime import date as _date, timedelta as _td
    from src.models.banquet import TaskOwnerRoleEnum

    now = datetime.utcnow()
    end_dt = now + _td(days=days)

    stmt = (
        select(ExecutionTask, BanquetOrder.banquet_type)
        .join(BanquetOrder, ExecutionTask.banquet_order_id == BanquetOrder.id)
        .where(
            and_(
                BanquetOrder.store_id == store_id,
                ExecutionTask.due_time >= now,
                ExecutionTask.due_time <= end_dt,
            )
        )
        .order_by(ExecutionTask.due_time)
    )
    if owner_role:
        try:
            stmt = stmt.where(ExecutionTask.owner_role == TaskOwnerRoleEnum(owner_role))
        except ValueError:
            pass

    result = await db.execute(stmt)
    rows = result.all()

    # Group by date
    from collections import defaultdict
    date_groups: dict[str, list] = defaultdict(list)
    total_pending = 0
    total_done = 0

    for task, banquet_type in rows:
        date_str = task.due_time.date().isoformat() if task.due_time else "unknown"
        is_done = task.task_status.value in ("done", "verified")
        if is_done:
            total_done += 1
        else:
            total_pending += 1
        date_groups[date_str].append({
            "task_id":      task.id,
            "task_name":    task.task_name,
            "owner_role":   task.owner_role.value,
            "order_id":     task.banquet_order_id,
            "banquet_type": banquet_type.value if banquet_type else None,
            "due_time":     task.due_time.isoformat() if task.due_time else None,
            "status":       task.task_status.value,
        })

    days_list = [
        {"date": dt, "tasks": tasks}
        for dt, tasks in sorted(date_groups.items())
    ]

    return {
        "days":          days_list,
        "total_pending": total_pending,
        "total_done":    total_done,
    }


# ────────── Phase 10：搜索 · 月度目标 · 自定义任务 · 时间轴 ─────────────────────

@router.get("/stores/{store_id}/search")
async def search_banquet(
    store_id: str,
    q: str = Query(..., min_length=2, description="搜索关键词（客户姓名/电话/订单号）"),
    type: str = Query("all", description="all|lead|order"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """跨实体全文搜索：线索（客户姓名/电话）+ 订单（订单号/客户姓名/电话）"""
    leads_out = []
    orders_out = []
    like = f"%{q}%"

    if type in ("all", "lead"):
        stmt = (
            select(BanquetLead, BanquetCustomer)
            .join(BanquetCustomer, BanquetLead.customer_id == BanquetCustomer.id)
            .where(
                and_(
                    BanquetLead.store_id == store_id,
                    (BanquetCustomer.name.ilike(like)) |
                    (BanquetCustomer.phone.ilike(like)),
                )
            )
            .order_by(BanquetLead.created_at.desc())
            .limit(20)
        )
        rows = (await db.execute(stmt)).all()
        for lead, customer in rows:
            leads_out.append({
                "id":           lead.id,
                "type":         "lead",
                "customer_name": customer.name,
                "phone":        customer.phone,
                "banquet_type": lead.banquet_type.value if lead.banquet_type else None,
                "expected_date": lead.expected_date.isoformat() if lead.expected_date else None,
                "stage":        lead.stage.value,
            })

    if type in ("all", "order"):
        stmt = (
            select(BanquetOrder, BanquetCustomer)
            .join(BanquetCustomer, BanquetOrder.customer_id == BanquetCustomer.id)
            .where(
                and_(
                    BanquetOrder.store_id == store_id,
                    (BanquetCustomer.name.ilike(like)) |
                    (BanquetCustomer.phone.ilike(like)) |
                    (BanquetOrder.contact_name.ilike(like)) |
                    (BanquetOrder.contact_phone.ilike(like)),
                )
            )
            .order_by(BanquetOrder.created_at.desc())
            .limit(20)
        )
        rows = (await db.execute(stmt)).all()
        for order, customer in rows:
            orders_out.append({
                "id":            order.id,
                "type":          "order",
                "customer_name": customer.name,
                "banquet_type":  order.banquet_type.value if order.banquet_type else None,
                "banquet_date":  order.banquet_date.isoformat() if order.banquet_date else None,
                "total_amount_yuan": round(order.total_amount_fen / 100, 2),
                "status":        order.order_status.value,
            })

    return {"leads": leads_out, "orders": orders_out}


class _TargetBody(BaseModel):
    target_yuan: float = Field(..., gt=0, description="目标营收（元）")


@router.get("/stores/{store_id}/revenue-targets/{year}/{month}")
async def get_revenue_target(
    store_id: str,
    year: int,
    month: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """读取月度营收目标"""
    stmt = select(BanquetRevenueTarget).where(
        and_(
            BanquetRevenueTarget.store_id == store_id,
            BanquetRevenueTarget.year == year,
            BanquetRevenueTarget.month == month,
        )
    )
    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        return {"year": year, "month": month, "target_yuan": None, "target_fen": None}
    return {
        "year":         row.year,
        "month":        row.month,
        "target_yuan":  round(row.target_fen / 100, 2),
        "target_fen":   row.target_fen,
    }


@router.put("/stores/{store_id}/revenue-targets/{year}/{month}", status_code=200)
async def set_revenue_target(
    store_id: str,
    year: int,
    month: int,
    body: _TargetBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """设置/更新月度营收目标（upsert）"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    target_fen = int(body.target_yuan * 100)
    now = datetime.utcnow()
    stmt = (
        pg_insert(BanquetRevenueTarget)
        .values(
            id=str(uuid.uuid4()),
            store_id=store_id,
            year=year,
            month=month,
            target_fen=target_fen,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_revenue_target_store_ym",
            set_={"target_fen": target_fen, "updated_at": now},
        )
    )
    await db.execute(stmt)
    await db.commit()
    return {"year": year, "month": month, "target_yuan": body.target_yuan}


class _CustomTaskBody(BaseModel):
    task_name:  str = Field(..., min_length=1, max_length=200)
    owner_role: str = Field(..., description="kitchen/service/decor/purchase/manager")
    due_time:   str = Field(..., description="ISO datetime，如 2026-03-15T18:00:00")


@router.post("/stores/{store_id}/orders/{order_id}/tasks", status_code=201)
async def create_custom_task(
    store_id: str,
    order_id: str,
    body: _CustomTaskBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """在订单下创建自定义执行任务"""
    # Verify order belongs to store
    order_stmt = select(BanquetOrder).where(
        and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
    )
    order = (await db.execute(order_stmt)).scalars().first()
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    try:
        role_enum = TaskOwnerRoleEnum(body.owner_role)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"无效角色: {body.owner_role}")

    try:
        due_dt = datetime.fromisoformat(body.due_time.replace("Z", "+00:00"))
        if due_dt.tzinfo is not None:
            due_dt = due_dt.replace(tzinfo=None)
    except ValueError:
        raise HTTPException(status_code=422, detail="due_time 格式错误，请用 ISO 格式")

    task = ExecutionTask(
        id=str(uuid.uuid4()),
        banquet_order_id=order_id,
        task_name=body.task_name,
        task_type="custom",
        owner_role=role_enum,
        task_status=TaskStatusEnum.PENDING,
        due_time=due_dt,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return {
        "task_id":    task.id,
        "task_name":  task.task_name,
        "owner_role": task.owner_role.value,
        "status":     task.task_status.value,
        "due_time":   task.due_time.isoformat() if task.due_time else None,
    }


@router.get("/stores/{store_id}/orders/{order_id}/timeline")
async def get_order_timeline(
    store_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """订单事件时间轴：付款记录 + 已完成任务 + Agent 日志，按时间升序"""
    # Verify order
    order_stmt = select(BanquetOrder).where(
        and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
    )
    if (await db.execute(order_stmt)).scalars().first() is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    events = []

    # 1. Payment records
    pay_stmt = select(BanquetPaymentRecord).where(
        BanquetPaymentRecord.banquet_order_id == order_id
    ).order_by(BanquetPaymentRecord.created_at)
    for pay in (await db.execute(pay_stmt)).scalars().all():
        events.append({
            "time":       pay.created_at.isoformat(),
            "event_type": "payment",
            "title":      f"登记收款 ¥{round(pay.amount_fen / 100, 2):,.0f}",
            "detail":     pay.payment_method,
        })

    # 2. Completed tasks
    task_stmt = select(ExecutionTask).where(
        and_(
            ExecutionTask.banquet_order_id == order_id,
            ExecutionTask.task_status.in_([
                TaskStatusEnum.DONE, TaskStatusEnum.VERIFIED,
            ]),
        )
    ).order_by(ExecutionTask.updated_at)
    for task in (await db.execute(task_stmt)).scalars().all():
        events.append({
            "time":       (task.updated_at or task.created_at).isoformat(),
            "event_type": "task_done",
            "title":      f"任务完成：{task.task_name}",
            "detail":     task.owner_role.value if task.owner_role else None,
        })

    # 3. Agent action logs
    log_stmt = select(BanquetAgentActionLog).where(
        and_(
            BanquetAgentActionLog.related_object_type == "order",
            BanquetAgentActionLog.related_object_id == order_id,
        )
    ).order_by(BanquetAgentActionLog.created_at)
    for log in (await db.execute(log_stmt)).scalars().all():
        events.append({
            "time":       log.created_at.isoformat(),
            "event_type": "agent",
            "title":      log.action_type,
            "detail":     log.suggestion_text,
        })

    events.sort(key=lambda e: e["time"])
    return {"order_id": order_id, "events": events}


# ────────── Phase 11：任务模板管理 · 异常事件 · 快速创建线索 ─────────────────────

# ── 执行任务模板 ──────────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/templates")
async def list_templates(
    store_id: str,
    banquet_type: Optional[str] = Query(None, description="按宴会类型过滤"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """列出执行任务模板（仅返回 is_active=True）"""
    stmt = select(ExecutionTemplate).where(
        and_(ExecutionTemplate.store_id == store_id, ExecutionTemplate.is_active == True)
    )
    if banquet_type:
        try:
            stmt = stmt.where(ExecutionTemplate.banquet_type == BanquetTypeEnum(banquet_type))
        except ValueError:
            pass
    stmt = stmt.order_by(ExecutionTemplate.created_at.desc())
    templates = (await db.execute(stmt)).scalars().all()
    return [
        {
            "template_id":   t.id,
            "template_name": t.template_name,
            "banquet_type":  t.banquet_type.value if t.banquet_type else None,
            "task_count":    len(t.task_defs) if isinstance(t.task_defs, list) else 0,
            "version":       t.version,
            "is_active":     t.is_active,
        }
        for t in templates
    ]


class _TemplateBody(BaseModel):
    template_name: str = Field(..., min_length=1, max_length=200)
    banquet_type:  Optional[str] = Field(None, description="wedding/birthday/business/... 或留空=通用")
    task_defs:     list = Field(..., description="任务定义列表：[{task_name, owner_role, days_before}]")


@router.post("/stores/{store_id}/templates", status_code=201)
async def create_template(
    store_id: str,
    body: _TemplateBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """创建执行任务模板"""
    bt = None
    if body.banquet_type:
        try:
            bt = BanquetTypeEnum(body.banquet_type)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"无效宴会类型: {body.banquet_type}")

    tpl = ExecutionTemplate(
        id=str(uuid.uuid4()),
        store_id=store_id,
        template_name=body.template_name,
        banquet_type=bt,
        task_defs=body.task_defs,
        version=1,
        is_active=True,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return {
        "template_id":   tpl.id,
        "template_name": tpl.template_name,
        "banquet_type":  tpl.banquet_type.value if tpl.banquet_type else None,
        "task_count":    len(tpl.task_defs) if isinstance(tpl.task_defs, list) else 0,
    }


class _TemplatePatch(BaseModel):
    template_name: Optional[str] = None
    banquet_type:  Optional[str] = None
    task_defs:     Optional[list] = None
    is_active:     Optional[bool] = None


@router.patch("/stores/{store_id}/templates/{template_id}", status_code=200)
async def update_template(
    store_id: str,
    template_id: str,
    body: _TemplatePatch,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """更新执行任务模板"""
    stmt = select(ExecutionTemplate).where(
        and_(ExecutionTemplate.id == template_id, ExecutionTemplate.store_id == store_id)
    )
    tpl = (await db.execute(stmt)).scalars().first()
    if tpl is None:
        raise HTTPException(status_code=404, detail="模板不存在")

    if body.template_name is not None:
        tpl.template_name = body.template_name
    if body.banquet_type is not None:
        try:
            tpl.banquet_type = BanquetTypeEnum(body.banquet_type) if body.banquet_type else None
        except ValueError:
            raise HTTPException(status_code=422, detail=f"无效宴会类型: {body.banquet_type}")
    if body.task_defs is not None:
        tpl.task_defs = body.task_defs
        tpl.version = (tpl.version or 1) + 1
    if body.is_active is not None:
        tpl.is_active = body.is_active

    await db.commit()
    return {
        "template_id":   tpl.id,
        "template_name": tpl.template_name,
        "task_count":    len(tpl.task_defs) if isinstance(tpl.task_defs, list) else 0,
        "version":       tpl.version,
        "is_active":     tpl.is_active,
    }


@router.delete("/stores/{store_id}/templates/{template_id}", status_code=200)
async def deactivate_template(
    store_id: str,
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """软停用模板（is_active=False）"""
    stmt = select(ExecutionTemplate).where(
        and_(ExecutionTemplate.id == template_id, ExecutionTemplate.store_id == store_id)
    )
    tpl = (await db.execute(stmt)).scalars().first()
    if tpl is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    tpl.is_active = False
    await db.commit()
    return {"template_id": template_id, "is_active": False}


# ── 异常事件 ──────────────────────────────────────────────────────────────────

class _ExceptionBody(BaseModel):
    exception_type: str = Field(..., description="late/missing/quality/complaint")
    description:    str = Field(..., min_length=1)
    severity:       str = Field("medium", description="low/medium/high")


@router.post("/stores/{store_id}/orders/{order_id}/exceptions", status_code=201)
async def report_exception(
    store_id: str,
    order_id: str,
    body: _ExceptionBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上报执行异常事件"""
    order_stmt = select(BanquetOrder).where(
        and_(BanquetOrder.id == order_id, BanquetOrder.store_id == store_id)
    )
    if (await db.execute(order_stmt)).scalars().first() is None:
        raise HTTPException(status_code=404, detail="订单不存在")

    if body.exception_type not in ("late", "missing", "quality", "complaint"):
        raise HTTPException(status_code=422, detail=f"无效异常类型: {body.exception_type}")
    if body.severity not in ("low", "medium", "high"):
        raise HTTPException(status_code=422, detail=f"无效严重程度: {body.severity}")

    exc = ExecutionException(
        id=str(uuid.uuid4()),
        banquet_order_id=order_id,
        exception_type=body.exception_type,
        description=body.description,
        severity=body.severity,
        owner_user_id=current_user.id,
        status="open",
    )
    db.add(exc)
    await db.commit()
    await db.refresh(exc)
    return {
        "exception_id":  exc.id,
        "exception_type": exc.exception_type,
        "description":   exc.description,
        "severity":      exc.severity,
        "status":        exc.status,
        "created_at":    exc.created_at.isoformat() if exc.created_at else None,
    }


@router.get("/stores/{store_id}/exceptions")
async def list_exceptions(
    store_id: str,
    status: Optional[str] = Query(None, description="open|resolved"),
    order_id: Optional[str] = Query(None, description="按订单过滤"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """查看全店异常事件列表"""
    stmt = (
        select(ExecutionException, BanquetOrder.banquet_type)
        .join(BanquetOrder, ExecutionException.banquet_order_id == BanquetOrder.id)
        .where(BanquetOrder.store_id == store_id)
        .order_by(ExecutionException.created_at.desc())
    )
    if status in ("open", "resolved"):
        stmt = stmt.where(ExecutionException.status == status)
    if order_id:
        stmt = stmt.where(ExecutionException.banquet_order_id == order_id)

    rows = (await db.execute(stmt)).all()
    return [
        {
            "exception_id":  exc.id,
            "order_id":      exc.banquet_order_id,
            "banquet_type":  bt.value if bt else None,
            "exception_type": exc.exception_type,
            "description":   exc.description,
            "severity":      exc.severity,
            "status":        exc.status,
            "created_at":    exc.created_at.isoformat() if exc.created_at else None,
            "resolved_at":   exc.resolved_at.isoformat() if exc.resolved_at else None,
        }
        for exc, bt in rows
    ]


@router.patch("/stores/{store_id}/exceptions/{exception_id}/resolve", status_code=200)
async def resolve_exception(
    store_id: str,
    exception_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """解决异常事件"""
    stmt = (
        select(ExecutionException)
        .join(BanquetOrder, ExecutionException.banquet_order_id == BanquetOrder.id)
        .where(
            and_(
                ExecutionException.id == exception_id,
                BanquetOrder.store_id == store_id,
            )
        )
    )
    exc = (await db.execute(stmt)).scalars().first()
    if exc is None:
        raise HTTPException(status_code=404, detail="异常记录不存在")

    exc.status = "resolved"
    exc.resolved_at = datetime.utcnow()
    await db.commit()
    return {
        "exception_id": exc.id,
        "status":       exc.status,
        "resolved_at":  exc.resolved_at.isoformat(),
    }


# ── 快速创建客户 + 线索 ───────────────────────────────────────────────────────

class _CustomerLeadBody(BaseModel):
    customer_name:   str = Field(..., min_length=1, max_length=100)
    phone:           Optional[str] = Field(None, max_length=20)
    banquet_type:    str = Field(..., description="wedding/birthday/business/...")
    expected_date:   Optional[str] = Field(None, description="YYYY-MM-DD")
    expected_tables: Optional[int] = Field(None, ge=1)
    budget_yuan:     Optional[float] = Field(None, gt=0)
    remark:          Optional[str] = None


@router.post("/stores/{store_id}/customers-with-lead", status_code=201)
async def create_customer_with_lead(
    store_id: str,
    body: _CustomerLeadBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """原子创建客户+线索；同名同电话客户自动复用（幂等）"""
    # Validate banquet_type
    try:
        bt = BanquetTypeEnum(body.banquet_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"无效宴会类型: {body.banquet_type}")

    # Find or create customer
    customer: Optional[BanquetCustomer] = None
    if body.phone:
        cust_stmt = select(BanquetCustomer).where(
            and_(
                BanquetCustomer.store_id == store_id,
                BanquetCustomer.phone == body.phone,
            )
        )
        customer = (await db.execute(cust_stmt)).scalars().first()

    if customer is None:
        customer = BanquetCustomer(
            id=str(uuid.uuid4()),
            brand_id=getattr(current_user, "brand_id", store_id),
            store_id=store_id,
            name=body.customer_name,
            phone=body.phone or "",
        )
        db.add(customer)
        await db.flush()   # get customer.id

    # Parse expected_date
    exp_date = None
    if body.expected_date:
        try:
            from datetime import date as _date
            exp_date = _date.fromisoformat(body.expected_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="expected_date 格式错误，请用 YYYY-MM-DD")

    # Create lead
    lead = BanquetLead(
        id=str(uuid.uuid4()),
        customer_id=customer.id,
        store_id=store_id,
        banquet_type=bt,
        expected_date=exp_date,
        expected_people_count=(body.expected_tables * 10) if body.expected_tables else None,
        expected_budget_fen=int(body.budget_yuan * 100) if body.budget_yuan else None,
        current_stage=LeadStageEnum.NEW,
        owner_user_id=current_user.id,
    )
    db.add(lead)
    await db.flush()

    # Optional initial followup note
    if body.remark:
        note = LeadFollowupRecord(
            id=str(uuid.uuid4()),
            lead_id=lead.id,
            followup_type="remark",
            content=body.remark,
            created_by=current_user.id,
        )
        db.add(note)

    await db.commit()
    return {"customer_id": customer.id, "lead_id": lead.id}


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


# ═══════════════════════════════════════════════════════════════════════════
# Phase 12 — 复盘持久化 / 预警 / 跨店 / 跟进调度 / 异常统计
# ═══════════════════════════════════════════════════════════════════════════

from datetime import timedelta as _timedelta


# ── 复盘 Pydantic Schemas ────────────────────────────────────────────────────

class _ReviewRatingBody(BaseModel):
    rating: int = Field(..., ge=1, le=5)


# ── 1. POST /stores/{id}/orders/{order_id}/reviews ─────────────────────────

@router.post("/stores/{store_id}/orders/{order_id}/reviews", status_code=201)
async def create_or_refresh_review(
    store_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """触发 ReviewAgent 并持久化复盘结果（已有则覆盖）。"""
    # 确认订单存在
    order_res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.id == order_id,
            BanquetOrder.store_id == store_id,
        )
    )
    order = order_res.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.order_status not in (OrderStatusEnum.COMPLETED, OrderStatusEnum.SETTLED):
        raise HTTPException(status_code=400, detail="只有已完成/已结算订单才能复盘")

    # 调用 ReviewAgent（ephemeral，获取分析数据）
    review_agent = _ReviewAgent()
    ai_result = await review_agent.generate_review(order_id=order_id, db=db)

    # 统计逾期任务 & 异常
    task_res = await db.execute(
        select(func.count(ExecutionTask.id)).where(
            ExecutionTask.banquet_order_id == order_id,
            ExecutionTask.task_status == TaskStatusEnum.PENDING,
        )
    )
    overdue_count = task_res.scalar() or 0

    exc_res = await db.execute(
        select(func.count(ExecutionException.id)).where(
            ExecutionException.banquet_order_id == order_id,
        )
    )
    exc_count = exc_res.scalar() or 0

    # 利润快照
    snap_res = await db.execute(
        select(BanquetProfitSnapshot).where(
            BanquetProfitSnapshot.banquet_order_id == order_id
        )
    )
    snap = snap_res.scalars().first()
    revenue_yuan      = (snap.revenue_fen      / 100) if snap else None
    gross_profit_yuan = (snap.gross_profit_fen / 100) if snap else None
    gross_margin_pct  = snap.gross_margin_pct          if snap else None

    # 检查是否已有复盘记录
    existing_res = await db.execute(
        select(BanquetOrderReview).where(
            BanquetOrderReview.banquet_order_id == order_id
        )
    )
    review = existing_res.scalars().first()

    if review is None:
        review = BanquetOrderReview(
            id=str(uuid.uuid4()),
            banquet_order_id=order_id,
        )
        db.add(review)

    review.ai_score           = ai_result.get("ai_score")
    review.ai_summary         = ai_result.get("summary")
    review.improvement_tags   = ai_result.get("improvement_tags", [])
    review.revenue_yuan       = revenue_yuan
    review.gross_profit_yuan  = gross_profit_yuan
    review.gross_margin_pct   = gross_margin_pct
    review.overdue_task_count = overdue_count
    review.exception_count    = exc_count

    await db.commit()
    await db.refresh(review)

    return {
        "review_id":          review.id,
        "banquet_order_id":   review.banquet_order_id,
        "ai_score":           review.ai_score,
        "ai_summary":         review.ai_summary,
        "improvement_tags":   review.improvement_tags or [],
        "customer_rating":    review.customer_rating,
        "revenue_yuan":       review.revenue_yuan,
        "gross_profit_yuan":  review.gross_profit_yuan,
        "gross_margin_pct":   review.gross_margin_pct,
        "overdue_task_count": review.overdue_task_count,
        "exception_count":    review.exception_count,
        "created_at":         review.created_at.isoformat() if review.created_at else None,
    }


# ── 2. GET /stores/{id}/orders/{order_id}/reviews ──────────────────────────

@router.get("/stores/{store_id}/orders/{order_id}/reviews")
async def get_review(
    store_id: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """读取已持久化的复盘结果。"""
    res = await db.execute(
        select(BanquetOrderReview).where(
            BanquetOrderReview.banquet_order_id == order_id
        )
    )
    review = res.scalars().first()
    if not review:
        raise HTTPException(status_code=404, detail="尚无复盘记录，请先触发复盘")

    return {
        "review_id":          review.id,
        "banquet_order_id":   review.banquet_order_id,
        "ai_score":           review.ai_score,
        "ai_summary":         review.ai_summary,
        "improvement_tags":   review.improvement_tags or [],
        "customer_rating":    review.customer_rating,
        "revenue_yuan":       review.revenue_yuan,
        "gross_profit_yuan":  review.gross_profit_yuan,
        "gross_margin_pct":   review.gross_margin_pct,
        "overdue_task_count": review.overdue_task_count,
        "exception_count":    review.exception_count,
        "created_at":         review.created_at.isoformat() if review.created_at else None,
    }


# ── 3. PATCH /stores/{id}/orders/{order_id}/reviews/rating ─────────────────

@router.patch("/stores/{store_id}/orders/{order_id}/reviews/rating")
async def patch_review_rating(
    store_id: str,
    order_id: str,
    body: _ReviewRatingBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """客户提交 1–5 星评分，写入复盘记录。"""
    res = await db.execute(
        select(BanquetOrderReview).where(
            BanquetOrderReview.banquet_order_id == order_id
        )
    )
    review = res.scalars().first()
    if not review:
        raise HTTPException(status_code=404, detail="尚无复盘记录")

    review.customer_rating = body.rating
    await db.commit()

    return {"review_id": review.id, "customer_rating": review.customer_rating}


# ── 4. GET /stores/{id}/orders/at-risk ─────────────────────────────────────

@router.get("/stores/{store_id}/orders/at-risk")
async def list_at_risk_orders(
    store_id: str,
    days: int = Query(14, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """返回未来 days 天内存在风险信号的订单列表（逾期任务 / 余款未付 / 未处理异常）。"""
    from datetime import date as _date_cls
    today = _date_cls.today()
    deadline = today + _timedelta(days=days)

    # 未来 days 天内的 confirmed/preparing/in_progress 订单
    orders_res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.order_status.in_([
                OrderStatusEnum.CONFIRMED,
                OrderStatusEnum.PREPARING,
                OrderStatusEnum.IN_PROGRESS,
            ]),
            BanquetOrder.banquet_date.isnot(None),
            BanquetOrder.banquet_date >= today,
            BanquetOrder.banquet_date <= deadline,
        )
    )
    orders = orders_res.scalars().all()

    result = []
    for o in orders:
        risk_score = 0
        risk_reasons = []

        # 逾期任务
        task_res = await db.execute(
            select(func.count(ExecutionTask.id)).where(
                ExecutionTask.banquet_order_id == o.id,
                ExecutionTask.task_status == TaskStatusEnum.PENDING,
            )
        )
        overdue = task_res.scalar() or 0
        if overdue > 0:
            risk_score += 1
            risk_reasons.append(f"{overdue}项待执行任务")

        # 余款未付
        pay_res = await db.execute(
            select(func.sum(BanquetPaymentRecord.amount_fen)).where(
                BanquetPaymentRecord.banquet_order_id == o.id,
            )
        )
        paid_fen  = pay_res.scalar() or 0
        total_fen = o.total_amount_fen or 0
        if total_fen > 0 and paid_fen < total_fen:
            risk_score += 1
            balance_yuan = (total_fen - paid_fen) / 100
            risk_reasons.append(f"余款¥{balance_yuan:.0f}未付")

        # 未处理异常
        exc_res = await db.execute(
            select(func.count(ExecutionException.id)).where(
                ExecutionException.banquet_order_id == o.id,
                ExecutionException.status == "open",
            )
        )
        open_exc = exc_res.scalar() or 0
        if open_exc > 0:
            risk_score += 1
            risk_reasons.append(f"{open_exc}个未处理异常")

        if risk_score > 0:
            result.append({
                "order_id":     o.id,
                "banquet_date": str(o.banquet_date),
                "banquet_type": o.banquet_type.value if hasattr(o.banquet_type, "value") else o.banquet_type,
                "status":       o.order_status.value if hasattr(o.order_status, "value") else o.order_status,
                "risk_score":   risk_score,
                "risk_reasons": risk_reasons,
            })

    result.sort(key=lambda x: (-x["risk_score"], x["banquet_date"]))
    return result


# ── 5. GET /stores/{id}/analytics/review-summary ───────────────────────────

@router.get("/stores/{store_id}/analytics/review-summary")
async def get_review_summary(
    store_id: str,
    year:  int = Query(None),
    month: int = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """月度复盘汇总统计（平均 AI 分 / 平均客户评分 / 改进标签 TOP3）。"""
    from datetime import date as _date_cls
    today = _date_cls.today()
    y = year  or today.year
    m = month or today.month

    # 通过订单日期过滤当月
    reviews_res = await db.execute(
        select(BanquetOrderReview).join(
            BanquetOrder,
            BanquetOrderReview.banquet_order_id == BanquetOrder.id,
        ).where(
            BanquetOrder.store_id == store_id,
            func.extract("year",  BanquetOrder.banquet_date) == y,
            func.extract("month", BanquetOrder.banquet_date) == m,
        )
    )
    reviews = reviews_res.scalars().all()

    if not reviews:
        return {"store_id": store_id, "year": y, "month": m, "count": 0,
                "avg_ai_score": None, "avg_customer_rating": None, "top_improvement_tags": []}

    ai_scores = [r.ai_score for r in reviews if r.ai_score is not None]
    ratings   = [r.customer_rating for r in reviews if r.customer_rating is not None]

    # 统计 improvement_tags 频次
    tag_counter: dict[str, int] = {}
    for r in reviews:
        for tag in (r.improvement_tags or []):
            tag_counter[tag] = tag_counter.get(tag, 0) + 1
    top_tags = sorted(tag_counter.items(), key=lambda x: -x[1])[:3]

    return {
        "store_id":            store_id,
        "year":                y,
        "month":               m,
        "count":               len(reviews),
        "avg_ai_score":        round(sum(ai_scores) / len(ai_scores), 1) if ai_scores else None,
        "avg_customer_rating": round(sum(ratings)   / len(ratings),   1) if ratings   else None,
        "top_improvement_tags": [{"tag": t, "count": c} for t, c in top_tags],
    }


# ── 6. GET /multi-store/banquet-summary ────────────────────────────────────

@router.get("/multi-store/banquet-summary")
async def multi_store_banquet_summary(
    year:  int = Query(None),
    month: int = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """跨店宴会 KPI 汇总（按 brand_id 过滤）。仅限 HQ 角色。"""
    from datetime import date as _date_cls
    today = _date_cls.today()
    y = year  or today.year
    m = month or today.month

    # 查出当前品牌的所有 store_id
    brand_id = getattr(current_user, "brand_id", None)
    if not brand_id:
        raise HTTPException(status_code=403, detail="无跨店权限")

    from src.models.store import Store as _Store
    stores_res = await db.execute(
        select(_Store.id).where(_Store.brand_id == brand_id)
    )
    store_ids = [row[0] for row in stores_res.all()]
    if not store_ids:
        return []

    # 聚合 BanquetKpiDaily
    kpi_res = await db.execute(
        select(
            BanquetKpiDaily.store_id,
            func.sum(BanquetKpiDaily.revenue_fen).label("revenue_fen"),
            func.sum(BanquetKpiDaily.gross_profit_fen).label("profit_fen"),
            func.sum(BanquetKpiDaily.order_count).label("order_count"),
            func.sum(BanquetKpiDaily.lead_count).label("lead_count"),
            func.avg(BanquetKpiDaily.hall_utilization_pct).label("avg_utilization"),
        ).where(
            BanquetKpiDaily.store_id.in_(store_ids),
            func.extract("year",  BanquetKpiDaily.stat_date) == y,
            func.extract("month", BanquetKpiDaily.stat_date) == m,
        ).group_by(BanquetKpiDaily.store_id)
    )
    rows = kpi_res.all()

    result = []
    for row in rows:
        rev  = (row.revenue_fen or 0) / 100
        prof = (row.profit_fen  or 0) / 100
        result.append({
            "store_id":          row.store_id,
            "year":              y,
            "month":             m,
            "revenue_yuan":      rev,
            "gross_profit_yuan": prof,
            "gross_margin_pct":  round(prof / rev * 100, 1) if rev > 0 else 0,
            "order_count":       row.order_count or 0,
            "lead_count":        row.lead_count  or 0,
            "hall_utilization_pct": round(row.avg_utilization or 0, 1),
        })

    result.sort(key=lambda x: -x["revenue_yuan"])
    return result


# ── 7. POST /stores/{id}/agent/followup-dispatch ───────────────────────────

@router.post("/stores/{store_id}/agent/followup-dispatch", status_code=201)
async def followup_dispatch(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动触发跟进扫描，并将建议写入 BanquetAgentActionLog（可审批）。"""
    agent = _FollowupAgent()
    suggestions = await agent.scan_stale_leads(store_id=store_id, db=db)

    logs = []
    for s in suggestions:
        log = BanquetAgentActionLog(
            id=str(uuid.uuid4()),
            agent_type="followup",
            related_object_type="lead",
            related_object_id=s.get("lead_id", ""),
            rule_id=None,
            action_type="followup_suggestion",
            action_result=s,
            suggestion_text=s.get("suggestion", ""),
            is_human_approved=None,
        )
        db.add(log)
        logs.append({"log_id": log.id, "lead_id": s.get("lead_id"), "suggestion": s.get("suggestion")})

    await db.commit()
    return {"dispatched": len(logs), "items": logs}


# ── 8. GET /stores/{id}/analytics/exception-stats ─────────────────────────

@router.get("/stores/{store_id}/analytics/exception-stats")
async def get_exception_stats(
    store_id: str,
    year:  int = Query(None),
    month: int = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """异常统计：按类型/严重度分组，计算平均解决时长（小时）。"""
    from datetime import date as _date_cls
    today = _date_cls.today()
    y = year  or today.year
    m = month or today.month

    # 通过 join BanquetOrder 过滤 store & 月份
    exc_res = await db.execute(
        select(ExecutionException).join(
            BanquetOrder,
            ExecutionException.banquet_order_id == BanquetOrder.id,
        ).where(
            BanquetOrder.store_id == store_id,
            func.extract("year",  ExecutionException.created_at) == y,
            func.extract("month", ExecutionException.created_at) == m,
        )
    )
    exceptions = exc_res.scalars().all()

    by_type: dict[str, dict] = {}
    by_severity: dict[str, int] = {}
    resolution_hours: list[float] = []

    for e in exceptions:
        # by_type
        et = e.exception_type
        if et not in by_type:
            by_type[et] = {"count": 0, "resolved": 0}
        by_type[et]["count"] += 1
        if e.status == "resolved":
            by_type[et]["resolved"] += 1
            if e.resolved_at and e.created_at:
                diff = (e.resolved_at - e.created_at).total_seconds() / 3600
                resolution_hours.append(diff)

        # by_severity
        sev = e.severity
        by_severity[sev] = by_severity.get(sev, 0) + 1

    avg_resolution_hours = (
        round(sum(resolution_hours) / len(resolution_hours), 1)
        if resolution_hours else None
    )

    return {
        "store_id":              store_id,
        "year":                  y,
        "month":                 m,
        "total":                 len(exceptions),
        "by_type":               [{"type": k, **v} for k, v in by_type.items()],
        "by_severity":           [{"severity": k, "count": v} for k, v in by_severity.items()],
        "avg_resolution_hours":  avg_resolution_hours,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Phase 13 — 报价闭环 / 目标仪表盘 / 线索转化评分
# ═══════════════════════════════════════════════════════════════════════════

import calendar as _calendar
from datetime import date as _date_cls


# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class _QuotePatchBody(BaseModel):
    quoted_amount_yuan: Optional[float] = None
    valid_until:        Optional[str]   = None   # YYYY-MM-DD
    remark:             Optional[str]   = None


# ── helpers ──────────────────────────────────────────────────────────────────

def _quote_to_dict(q) -> dict:
    return {
        "quote_id":           q.id,
        "lead_id":            q.lead_id,
        "store_id":           q.store_id,
        "people_count":       q.people_count,
        "table_count":        q.table_count,
        "quoted_amount_yuan": q.quoted_amount_fen / 100,
        "valid_until":        str(q.valid_until) if q.valid_until else None,
        "is_accepted":        q.is_accepted,
        "is_expired":         bool(q.valid_until and q.valid_until < _date_cls.today()),
        "created_at":         q.created_at.isoformat() if q.created_at else None,
    }


def _compute_lead_score(lead) -> dict:
    """规则式线索转化评分（0–100）"""
    # stage_score (0–40)
    stage_map = {
        "new": 5, "contacted": 10, "visit_scheduled": 20,
        "quoted": 30, "waiting_decision": 35, "deposit_pending": 40,
        "won": 40, "lost": 0,
    }
    stage_val = lead.current_stage.value if hasattr(lead.current_stage, "value") else str(lead.current_stage)
    stage_score = stage_map.get(stage_val, 0)

    # budget_score (0–25)
    budget_yuan = (lead.expected_budget_fen / 100) if lead.expected_budget_fen else None
    if budget_yuan is None:
        budget_score = 0
    elif budget_yuan >= 80000:
        budget_score = 25
    elif budget_yuan >= 40000:
        budget_score = 20
    elif budget_yuan >= 20000:
        budget_score = 10
    else:
        budget_score = 5

    # recency_score (0–20)
    if lead.last_followup_at:
        days_since = (_date_cls.today() - lead.last_followup_at.date()).days
        if days_since <= 2:
            recency_score = 20
        elif days_since <= 7:
            recency_score = 15
        elif days_since <= 14:
            recency_score = 10
        elif days_since <= 30:
            recency_score = 5
        else:
            recency_score = 0
    else:
        recency_score = 0

    # completeness_score (0–15)
    completeness_score = (
        (5 if lead.expected_date else 0) +
        (5 if lead.expected_people_count else 0) +
        (5 if lead.expected_budget_fen else 0)
    )

    total = stage_score + budget_score + recency_score + completeness_score

    if total >= 75:
        grade = "A"
    elif total >= 50:
        grade = "B"
    elif total >= 25:
        grade = "C"
    else:
        grade = "D"

    return {
        "score": total,
        "grade": grade,
        "breakdown": {
            "stage_score":        stage_score,
            "budget_score":       budget_score,
            "recency_score":      recency_score,
            "completeness_score": completeness_score,
        },
    }


# ── 1. GET /stores/{id}/quotes ───────────────────────────────────────────────

@router.get("/stores/{store_id}/quotes")
async def list_store_quotes(
    store_id: str,
    status:   str = Query("all"),    # all / active / expired / accepted / declined
    page:     int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """全店报价列表（可按状态过滤）。"""
    today = _date_cls.today()
    q = select(BanquetQuote).where(BanquetQuote.store_id == store_id)

    if status == "accepted":
        q = q.where(BanquetQuote.is_accepted == True)
    elif status == "declined":
        q = q.where(
            BanquetQuote.is_accepted == False,
            BanquetQuote.valid_until < today,
        )
    elif status == "active":
        q = q.where(
            BanquetQuote.is_accepted == False,
            BanquetQuote.valid_until >= today,
        )
    elif status == "expired":
        q = q.where(
            BanquetQuote.is_accepted == False,
            BanquetQuote.valid_until < today,
        )

    q = q.order_by(BanquetQuote.created_at.desc())
    offset = (page - 1) * page_size

    count_res = await db.execute(select(func.count()).select_from(q.subquery()))
    total = count_res.scalar() or 0

    items_res = await db.execute(q.offset(offset).limit(page_size))
    items = items_res.scalars().all()

    return {
        "total":    total,
        "page":     page,
        "page_size": page_size,
        "items":    [_quote_to_dict(qr) for qr in items],
    }


# ── 2. GET /stores/{id}/leads/{lid}/quotes/{qid} ────────────────────────────

@router.get("/stores/{store_id}/leads/{lead_id}/quotes/{quote_id}")
async def get_single_quote(
    store_id: str,
    lead_id:  str,
    quote_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """读取单条报价详情。"""
    res = await db.execute(
        select(BanquetQuote).where(
            BanquetQuote.id == quote_id,
            BanquetQuote.lead_id == lead_id,
            BanquetQuote.store_id == store_id,
        )
    )
    q = res.scalars().first()
    if not q:
        raise HTTPException(status_code=404, detail="报价不存在")
    return _quote_to_dict(q)


# ── 3. PATCH /stores/{id}/leads/{lid}/quotes/{qid} ──────────────────────────

@router.patch("/stores/{store_id}/leads/{lead_id}/quotes/{quote_id}")
async def patch_quote(
    store_id: str,
    lead_id:  str,
    quote_id: str,
    body: _QuotePatchBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """更新报价金额 / 有效期。已接受的报价不可修改。"""
    res = await db.execute(
        select(BanquetQuote).where(
            BanquetQuote.id == quote_id,
            BanquetQuote.lead_id == lead_id,
            BanquetQuote.store_id == store_id,
        )
    )
    q = res.scalars().first()
    if not q:
        raise HTTPException(status_code=404, detail="报价不存在")
    if q.is_accepted:
        raise HTTPException(status_code=400, detail="已接受的报价不可修改")

    if body.quoted_amount_yuan is not None:
        q.quoted_amount_fen = int(body.quoted_amount_yuan * 100)
    if body.valid_until is not None:
        from datetime import datetime as _dt
        q.valid_until = _dt.strptime(body.valid_until, "%Y-%m-%d").date()

    await db.commit()
    return _quote_to_dict(q)


# ── 4. DELETE /stores/{id}/leads/{lid}/quotes/{qid} ─────────────────────────

@router.delete("/stores/{store_id}/leads/{lead_id}/quotes/{quote_id}",
               status_code=200)
async def delete_quote(
    store_id: str,
    lead_id:  str,
    quote_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """撤销报价（软删除：is_accepted=False，valid_until=今天）。"""
    res = await db.execute(
        select(BanquetQuote).where(
            BanquetQuote.id == quote_id,
            BanquetQuote.lead_id == lead_id,
            BanquetQuote.store_id == store_id,
        )
    )
    q = res.scalars().first()
    if not q:
        raise HTTPException(status_code=404, detail="报价不存在")
    if q.is_accepted:
        raise HTTPException(status_code=400, detail="已接受的报价不可撤销")

    q.valid_until = _date_cls.today()
    await db.commit()
    return {"quote_id": q.id, "revoked": True}


# ── 5. GET /stores/{id}/analytics/target-progress ───────────────────────────

@router.get("/stores/{store_id}/analytics/target-progress")
async def get_target_progress(
    store_id: str,
    year:  int = Query(None),
    month: int = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """月度营收目标达成率（target / actual / gap / daily_needed / on_track）。"""
    today = _date_cls.today()
    y = year  or today.year
    m = month or today.month

    # 目标
    target_res = await db.execute(
        select(BanquetRevenueTarget).where(
            BanquetRevenueTarget.store_id == store_id,
            BanquetRevenueTarget.year  == y,
            BanquetRevenueTarget.month == m,
        )
    )
    target = target_res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="当月尚未设置目标")

    target_yuan = target.target_fen / 100

    # 实际（从 BanquetKpiDaily 聚合）
    kpi_res = await db.execute(
        select(func.sum(BanquetKpiDaily.revenue_fen)).where(
            BanquetKpiDaily.store_id == store_id,
            func.extract("year",  BanquetKpiDaily.stat_date) == y,
            func.extract("month", BanquetKpiDaily.stat_date) == m,
        )
    )
    actual_yuan = (kpi_res.scalar() or 0) / 100

    days_in_month  = _calendar.monthrange(y, m)[1]
    days_elapsed   = today.day if (y == today.year and m == today.month) else days_in_month
    days_remaining = max(days_in_month - days_elapsed, 0)

    gap_yuan     = max(target_yuan - actual_yuan, 0)
    run_rate     = (actual_yuan / days_elapsed * days_in_month) if days_elapsed > 0 else 0
    daily_needed = (gap_yuan / days_remaining) if days_remaining > 0 else 0
    achievement  = round(actual_yuan / target_yuan * 100, 1) if target_yuan > 0 else 0
    on_track     = run_rate >= target_yuan

    return {
        "store_id":          store_id,
        "year":              y,
        "month":             m,
        "target_yuan":       target_yuan,
        "actual_yuan":       actual_yuan,
        "achievement_pct":   achievement,
        "gap_yuan":          gap_yuan,
        "run_rate_yuan":     round(run_rate, 2),
        "daily_needed_yuan": round(daily_needed, 2),
        "days_elapsed":      days_elapsed,
        "days_remaining":    days_remaining,
        "on_track":          on_track,
    }


# ── 6. GET /stores/{id}/analytics/target-trend ──────────────────────────────

@router.get("/stores/{store_id}/analytics/target-trend")
async def get_target_trend(
    store_id: str,
    months:   int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """近 N 个月目标 vs 实际折线数据。"""
    today = _date_cls.today()

    # 构造最近 N 个月的 (year, month) 列表
    month_list = []
    y, m = today.year, today.month
    for _ in range(months):
        month_list.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    month_list.reverse()

    # 批量查目标
    targets_res = await db.execute(
        select(BanquetRevenueTarget).where(
            BanquetRevenueTarget.store_id == store_id,
            BanquetRevenueTarget.year.in_([r[0] for r in month_list]),
            BanquetRevenueTarget.month.in_([r[1] for r in month_list]),
        )
    )
    target_map = {(t.year, t.month): t.target_fen / 100 for t in targets_res.scalars().all()}

    # 批量查实际
    kpi_res = await db.execute(
        select(
            func.extract("year",  BanquetKpiDaily.stat_date).label("y"),
            func.extract("month", BanquetKpiDaily.stat_date).label("m"),
            func.sum(BanquetKpiDaily.revenue_fen).label("revenue_fen"),
        ).where(
            BanquetKpiDaily.store_id == store_id,
        ).group_by("y", "m")
    )
    actual_map = {(int(r.y), int(r.m)): (r.revenue_fen or 0) / 100 for r in kpi_res.all()}

    result = []
    for (yr, mo) in month_list:
        result.append({
            "month":        f"{yr}-{mo:02d}",
            "target_yuan":  target_map.get((yr, mo), 0),
            "actual_yuan":  actual_map.get((yr, mo), 0),
        })

    return {"months": result}


# ── 7. POST /stores/{id}/agent/score-leads ──────────────────────────────────

@router.post("/stores/{store_id}/agent/score-leads", status_code=201)
async def score_leads(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量计算当前活跃线索转化评分，写入 BanquetAgentActionLog。"""
    # 查所有非 won/lost 线索
    leads_res = await db.execute(
        select(BanquetLead).where(
            BanquetLead.store_id == store_id,
            BanquetLead.current_stage.notin_([LeadStageEnum.WON, LeadStageEnum.LOST]),
        )
    )
    leads = leads_res.scalars().all()

    scored = []
    for lead in leads:
        result = _compute_lead_score(lead)
        log = BanquetAgentActionLog(
            id=str(uuid.uuid4()),
            agent_type="followup",
            related_object_type="lead",
            related_object_id=lead.id,
            rule_id=None,
            action_type="conversion_score",
            action_result=result,
            suggestion_text=f"线索评分 {result['score']} 分（{result['grade']}）",
            is_human_approved=None,
        )
        db.add(log)
        scored.append({"lead_id": lead.id, **result})

    await db.commit()
    return {"scored_count": len(scored), "items": scored}


# ── 8. GET /stores/{id}/leads/{lid}/score ───────────────────────────────────

@router.get("/stores/{store_id}/leads/{lead_id}/score")
async def get_lead_score(
    store_id: str,
    lead_id:  str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """读取线索最新转化评分（取 BanquetAgentActionLog 最新一条 conversion_score）。"""
    # 验证线索存在
    lead_res = await db.execute(
        select(BanquetLead).where(
            BanquetLead.id == lead_id,
            BanquetLead.store_id == store_id,
        )
    )
    lead = lead_res.scalars().first()
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")

    # 取最新一条 conversion_score log
    log_res = await db.execute(
        select(BanquetAgentActionLog).where(
            BanquetAgentActionLog.related_object_type == "lead",
            BanquetAgentActionLog.related_object_id   == lead_id,
            BanquetAgentActionLog.action_type         == "conversion_score",
        ).order_by(BanquetAgentActionLog.created_at.desc()).limit(1)
    )
    log = log_res.scalars().first()

    if log and log.action_result:
        return {
            "lead_id":    lead_id,
            "score":      log.action_result.get("score"),
            "grade":      log.action_result.get("grade"),
            "breakdown":  log.action_result.get("breakdown"),
            "scored_at":  log.created_at.isoformat() if log.created_at else None,
        }

    # 没有历史记录 → 实时计算（不持久化）
    result = _compute_lead_score(lead)
    return {
        "lead_id":    lead_id,
        "score":      result["score"],
        "grade":      result["grade"],
        "breakdown":  result["breakdown"],
        "scored_at":  None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 14 — 应收账款预警·跟进话术生成·厅房月历看板
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. GET /stores/{id}/analytics/receivables-aging ─────────────────────────

@router.get("/stores/{store_id}/analytics/receivables-aging")
async def get_receivables_aging(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """应收账款账龄分析（按逾期天数分桶）。

    逻辑：已确认/准备中/进行中的订单，paid_fen < total_amount_fen 视为有应收。
    账龄基准 = banquet_date（宴会日期过去后应收）。
    """
    from datetime import timedelta
    from src.models.banquet import OrderStatusEnum

    today = date_type.today()
    active_statuses = [
        OrderStatusEnum.CONFIRMED,
        OrderStatusEnum.PREPARING,
        OrderStatusEnum.IN_PROGRESS,
        OrderStatusEnum.COMPLETED,
    ]

    res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.order_status.in_(active_statuses),
            BanquetOrder.paid_fen < BanquetOrder.total_amount_fen,
            BanquetOrder.banquet_date < today,   # 宴会已过，仍有欠款
        )
    )
    orders = res.scalars().all()

    buckets = {"0_30": [], "31_60": [], "61_90": [], "over_90": []}
    totals  = {"0_30": 0,  "31_60": 0,  "61_90": 0,  "over_90": 0}

    for o in orders:
        days_overdue = (today - o.banquet_date).days
        balance_fen  = o.total_amount_fen - o.paid_fen
        bucket_key   = (
            "0_30"    if days_overdue <= 30  else
            "31_60"   if days_overdue <= 60  else
            "61_90"   if days_overdue <= 90  else
            "over_90"
        )
        buckets[bucket_key].append({
            "order_id":       o.id,
            "banquet_date":   o.banquet_date.isoformat(),
            "banquet_type":   o.banquet_type.value if hasattr(o.banquet_type, "value") else str(o.banquet_type),
            "total_yuan":     round(o.total_amount_fen / 100, 2),
            "paid_yuan":      round(o.paid_fen / 100, 2),
            "balance_yuan":   round(balance_fen / 100, 2),
            "days_overdue":   days_overdue,
            "contact_name":   o.contact_name,
        })
        totals[bucket_key] += balance_fen

    total_balance_fen = sum(totals.values())
    return {
        "store_id":           store_id,
        "as_of":              today.isoformat(),
        "total_balance_yuan": round(total_balance_fen / 100, 2),
        "buckets": {
            "0_30":    {"count": len(buckets["0_30"]),    "balance_yuan": round(totals["0_30"]    / 100, 2), "items": buckets["0_30"]},
            "31_60":   {"count": len(buckets["31_60"]),   "balance_yuan": round(totals["31_60"]   / 100, 2), "items": buckets["31_60"]},
            "61_90":   {"count": len(buckets["61_90"]),   "balance_yuan": round(totals["61_90"]   / 100, 2), "items": buckets["61_90"]},
            "over_90": {"count": len(buckets["over_90"]), "balance_yuan": round(totals["over_90"] / 100, 2), "items": buckets["over_90"]},
        },
    }


# ── 2. GET /stores/{id}/receivables/overdue ──────────────────────────────────

@router.get("/stores/{store_id}/receivables/overdue")
async def list_overdue_receivables(
    store_id: str,
    min_days: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """列出逾期 ≥ min_days 天、仍有欠款的订单。"""
    from datetime import timedelta
    from src.models.banquet import OrderStatusEnum

    today    = date_type.today()
    cutoff   = today - timedelta(days=min_days)
    active_s = [
        OrderStatusEnum.CONFIRMED,
        OrderStatusEnum.PREPARING,
        OrderStatusEnum.IN_PROGRESS,
        OrderStatusEnum.COMPLETED,
    ]

    res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.order_status.in_(active_s),
            BanquetOrder.paid_fen < BanquetOrder.total_amount_fen,
            BanquetOrder.banquet_date <= cutoff,
        ).order_by(BanquetOrder.banquet_date.asc())
    )
    orders = res.scalars().all()

    items = []
    for o in orders:
        days_overdue = (today - o.banquet_date).days
        items.append({
            "order_id":     o.id,
            "banquet_date": o.banquet_date.isoformat(),
            "banquet_type": o.banquet_type.value if hasattr(o.banquet_type, "value") else str(o.banquet_type),
            "total_yuan":   round(o.total_amount_fen / 100, 2),
            "paid_yuan":    round(o.paid_fen / 100, 2),
            "balance_yuan": round((o.total_amount_fen - o.paid_fen) / 100, 2),
            "days_overdue": days_overdue,
            "contact_name": o.contact_name,
            "contact_phone": o.contact_phone,
        })

    return {"store_id": store_id, "min_days": min_days, "total": len(items), "items": items}


# ── 3. POST /stores/{id}/leads/{lid}/followup-message ───────────────────────

# 5 stage-based templates
_FOLLOWUP_TEMPLATES = {
    "new": "您好 {name}，感谢您对我们{store}宴会服务的关注！我们专业的宴会团队随时为您提供个性化方案，请问您方便安排一次看厅体验吗？",
    "contacted": "您好 {name}，很高兴与您沟通！根据您的需求，我们已为您准备了{banquet_type}专属方案，可以约您来现场感受一下我们的环境和服务吗？",
    "visit_scheduled": "您好 {name}，期待您{date}的到来！届时我们将为您详细介绍{banquet_type}套餐，并可安排现场品鉴。如有任何问题请随时联系我们。",
    "quoted": "您好 {name}，已为您发送{banquet_type}报价方案，总额约¥{budget}。方案可根据需求灵活调整，不知您是否有其他疑虑？我们很乐意再为您详细解答。",
    "waiting_decision": "您好 {name}，我们诚邀您确认{banquet_type}预订方案。考虑到{date}前后档期较为紧张，建议尽早锁定。如有任何顾虑，欢迎随时沟通！",
    "deposit_pending": "您好 {name}，{banquet_type}档期已为您暂留，只需支付定金即可正式锁定。请问您方便在近期完成定金支付吗？",
}

class _FollowupMsgBody(BaseModel):
    custom_hint: Optional[str] = None   # 额外提示词（可选）

@router.post("/stores/{store_id}/leads/{lead_id}/followup-message")
async def generate_followup_message(
    store_id:  str,
    lead_id:   str,
    body:      _FollowupMsgBody = Body(default_factory=_FollowupMsgBody),
    db:        AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """基于线索阶段生成个性化跟进话术，并记录到 ActionLog。"""
    # 读取线索
    lead_res = await db.execute(
        select(BanquetLead).where(
            BanquetLead.id == lead_id,
            BanquetLead.store_id == store_id,
        )
    )
    lead = lead_res.scalars().first()
    if not lead:
        raise HTTPException(status_code=404, detail="线索不存在")

    # 读取客户
    cust_res = await db.execute(
        select(BanquetCustomer).where(BanquetCustomer.id == lead.customer_id)
    )
    customer = cust_res.scalars().first()

    stage   = lead.current_stage.value if hasattr(lead.current_stage, "value") else str(lead.current_stage)
    template = _FOLLOWUP_TEMPLATES.get(stage, _FOLLOWUP_TEMPLATES["new"])

    budget_str = ""
    if lead.expected_budget_fen:
        budget_str = f"{lead.expected_budget_fen // 100:,}"

    date_str = ""
    if lead.expected_date:
        date_str = lead.expected_date.strftime("%m月%d日")

    banquet_type_str = lead.banquet_type.value if hasattr(lead.banquet_type, "value") else str(lead.banquet_type or "")

    message = template.format(
        name=customer.customer_name if customer else "客户",
        store="智链酒楼",
        banquet_type=banquet_type_str,
        date=date_str or "预定日期",
        budget=budget_str or "待定",
    )

    if body.custom_hint:
        message = message.rstrip("！。") + f"。{body.custom_hint}"

    result = {
        "stage":    stage,
        "message":  message,
        "template": template,
    }

    log = BanquetAgentActionLog(
        id=str(__import__("uuid").uuid4()),
        agent_type=BanquetAgentTypeEnum.FOLLOWUP,
        action_type="followup_message",
        related_object_type="lead",
        related_object_id=lead_id,
        action_result=result,
        suggestion_text=message[:100],
        is_human_approved=None,
    )
    db.add(log)
    await db.commit()

    return {"lead_id": lead_id, **result}


# ── 4. GET /stores/{id}/leads/{lid}/followup-messages ───────────────────────

@router.get("/stores/{store_id}/leads/{lead_id}/followup-messages")
async def list_followup_messages(
    store_id: str,
    lead_id:  str,
    limit:    int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """读取线索历史跟进话术记录。"""
    res = await db.execute(
        select(BanquetAgentActionLog).where(
            BanquetAgentActionLog.related_object_type == "lead",
            BanquetAgentActionLog.related_object_id   == lead_id,
            BanquetAgentActionLog.action_type         == "followup_message",
        ).order_by(BanquetAgentActionLog.created_at.desc()).limit(limit)
    )
    logs = res.scalars().all()

    items = []
    for log in logs:
        r = log.action_result or {}
        items.append({
            "log_id":     log.id,
            "stage":      r.get("stage"),
            "message":    r.get("message"),
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })

    return {"lead_id": lead_id, "total": len(items), "items": items}


# ── 5. GET /stores/{id}/halls/monthly-schedule ──────────────────────────────

@router.get("/stores/{store_id}/halls/monthly-schedule")
async def get_halls_monthly_schedule(
    store_id: str,
    year:     int = Query(...),
    month:    int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """厅房月历看板：hall × day 占用矩阵。"""
    import calendar
    from datetime import timedelta

    first_day = date_type(year, month, 1)
    last_day  = date_type(year, month, calendar.monthrange(year, month)[1])

    # 获取所有厅房
    halls_res = await db.execute(
        select(BanquetHall).where(
            BanquetHall.store_id == store_id,
            BanquetHall.is_active == True,
        ).order_by(BanquetHall.name)
    )
    halls = halls_res.scalars().all()

    # 获取该月所有 bookings（含 order status）
    bookings_res = await db.execute(
        select(BanquetHallBooking, BanquetOrder).join(
            BanquetOrder, BanquetHallBooking.banquet_order_id == BanquetOrder.id
        ).where(
            BanquetHallBooking.hall_id.in_([h.id for h in halls]),
            BanquetHallBooking.slot_date >= first_day,
            BanquetHallBooking.slot_date <= last_day,
        )
    )
    booking_rows = bookings_res.all()

    # 构建 hall_id → {date_str → [slot_info]}
    hall_day_map: dict = {}
    for booking, order in booking_rows:
        hid  = booking.hall_id
        dstr = booking.slot_date.isoformat()
        if hid not in hall_day_map:
            hall_day_map[hid] = {}
        if dstr not in hall_day_map[hid]:
            hall_day_map[hid][dstr] = []
        hall_day_map[hid][dstr].append({
            "slot_name":    booking.slot_name,
            "is_locked":    booking.is_locked,
            "order_id":     order.id,
            "order_status": order.order_status.value if hasattr(order.order_status, "value") else str(order.order_status),
            "banquet_type": order.banquet_type.value if hasattr(order.banquet_type, "value") else str(order.banquet_type),
        })

    # 生成日期列表
    num_days = (last_day - first_day).days + 1
    dates = [(first_day + timedelta(days=i)).isoformat() for i in range(num_days)]

    halls_data = []
    for h in halls:
        day_cells = []
        for d in dates:
            slots = hall_day_map.get(h.id, {}).get(d, [])
            day_cells.append({
                "date":    d,
                "booked":  len(slots) > 0,
                "slots":   slots,
            })
        halls_data.append({
            "hall_id":    h.id,
            "hall_name":  h.name,
            "hall_type":  h.hall_type.value if hasattr(h.hall_type, "value") else str(h.hall_type),
            "max_tables": h.max_tables,
            "days":       day_cells,
        })

    return {
        "store_id": store_id,
        "year":     year,
        "month":    month,
        "dates":    dates,
        "halls":    halls_data,
    }


# ── 6. GET /stores/{id}/halls/{hall_id}/utilization ─────────────────────────

@router.get("/stores/{store_id}/halls/{hall_id}/utilization")
async def get_hall_utilization(
    store_id: str,
    hall_id:  str,
    year:     int = Query(...),
    month:    int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """单厅房月利用率统计。"""
    import calendar
    from datetime import timedelta

    # 验证厅房
    hall_res = await db.execute(
        select(BanquetHall).where(
            BanquetHall.id == hall_id,
            BanquetHall.store_id == store_id,
        )
    )
    hall = hall_res.scalars().first()
    if not hall:
        raise HTTPException(status_code=404, detail="厅房不存在")

    first_day = date_type(year, month, 1)
    last_day  = date_type(year, month, calendar.monthrange(year, month)[1])
    total_days = (last_day - first_day).days + 1

    bookings_res = await db.execute(
        select(BanquetHallBooking).where(
            BanquetHallBooking.hall_id == hall_id,
            BanquetHallBooking.slot_date >= first_day,
            BanquetHallBooking.slot_date <= last_day,
        )
    )
    bookings = bookings_res.scalars().all()

    booked_slots = len(bookings)
    # 每天理论可用 2 个时段（午/晚）
    total_slots  = total_days * 2
    utilization_pct = round(booked_slots / total_slots * 100, 1) if total_slots > 0 else 0.0

    # 按日统计
    day_map: dict = {}
    for b in bookings:
        dstr = b.slot_date.isoformat()
        day_map[dstr] = day_map.get(dstr, 0) + 1

    return {
        "hall_id":           hall_id,
        "hall_name":         hall.name,
        "year":              year,
        "month":             month,
        "total_days":        total_days,
        "booked_slots":      booked_slots,
        "total_slots":       total_slots,
        "utilization_pct":   utilization_pct,
        "booked_days":       len(day_map),
        "daily_breakdown":   [{"date": d, "slots": c} for d, c in sorted(day_map.items())],
    }


# ── 7. GET /stores/{id}/analytics/quote-stats ───────────────────────────────

@router.get("/stores/{store_id}/analytics/quote-stats")
async def get_quote_stats(
    store_id: str,
    year:     int  = Query(default=None),
    month:    int  = Query(default=None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """报价统计：接受率 + 按宴会类型分布。"""
    today = date_type.today()
    _year  = year  or today.year
    _month = month or today.month

    first_day = date_type(_year, _month, 1)
    import calendar as _cal
    last_day  = date_type(_year, _month, _cal.monthrange(_year, _month)[1])

    quotes_res = await db.execute(
        select(BanquetQuote, BanquetLead).join(
            BanquetLead, BanquetQuote.lead_id == BanquetLead.id
        ).where(
            BanquetQuote.store_id == store_id,
            BanquetQuote.created_at >= first_day,
            BanquetQuote.created_at <= last_day,
        )
    )
    rows = quotes_res.all()

    total        = len(rows)
    accepted     = sum(1 for q, _ in rows if q.is_accepted)
    acceptance_pct = round(accepted / total * 100, 1) if total > 0 else 0.0

    type_map: dict = {}
    for q, lead in rows:
        btype = lead.banquet_type.value if hasattr(lead.banquet_type, "value") else str(lead.banquet_type or "unknown")
        if btype not in type_map:
            type_map[btype] = {"total": 0, "accepted": 0, "total_amount_yuan": 0.0}
        type_map[btype]["total"] += 1
        type_map[btype]["total_amount_yuan"] += round(q.quoted_amount_fen / 100, 2)
        if q.is_accepted:
            type_map[btype]["accepted"] += 1

    type_distribution = [
        {
            "banquet_type": btype,
            "count": v["total"],
            "accepted": v["accepted"],
            "total_amount_yuan": round(v["total_amount_yuan"], 2),
        }
        for btype, v in sorted(type_map.items(), key=lambda x: -x[1]["total"])
    ]

    return {
        "store_id":         store_id,
        "year":             _year,
        "month":            _month,
        "total_quotes":     total,
        "accepted_quotes":  accepted,
        "acceptance_pct":   acceptance_pct,
        "type_distribution": type_distribution,
    }


# ── 8. GET /stores/{id}/contracts/pending-sign ──────────────────────────────

@router.get("/stores/{store_id}/contracts/pending-sign")
async def list_pending_sign_contracts(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """列出待签约（draft）合同，按宴会日期升序。"""
    res = await db.execute(
        select(BanquetContract, BanquetOrder).join(
            BanquetOrder, BanquetContract.banquet_order_id == BanquetOrder.id
        ).where(
            BanquetOrder.store_id == store_id,
            BanquetContract.contract_status == "draft",
        ).order_by(BanquetOrder.banquet_date.asc())
    )
    rows = res.all()

    items = []
    for contract, order in rows:
        items.append({
            "contract_id":    contract.id,
            "contract_no":    contract.contract_no,
            "order_id":       order.id,
            "banquet_date":   order.banquet_date.isoformat(),
            "banquet_type":   order.banquet_type.value if hasattr(order.banquet_type, "value") else str(order.banquet_type),
            "total_yuan":     round(order.total_amount_fen / 100, 2),
            "contact_name":   order.contact_name,
            "contact_phone":  order.contact_phone,
            "days_until":     (order.banquet_date - date_type.today()).days,
        })

    return {
        "store_id": store_id,
        "total":    len(items),
        "items":    items,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 15 — 服务品质看板·客户保留分析·智能排班建议
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. GET /stores/{id}/analytics/service-quality ───────────────────────────

@router.get("/stores/{store_id}/analytics/service-quality")
async def get_service_quality(
    store_id: str,
    month:    str = Query(default=None, description="YYYY-MM, default=current month"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """服务品质看板：任务完成率、平均延误、异常率（按宴会类型分解）。"""
    import calendar as _cal
    from datetime import timedelta

    today = date_type.today()
    _month = month or today.strftime("%Y-%m")
    y, m = int(_month[:4]), int(_month[5:7])
    first_day = date_type(y, m, 1)
    last_day  = date_type(y, m, _cal.monthrange(y, m)[1])

    # Orders in month
    orders_res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.banquet_date >= first_day,
            BanquetOrder.banquet_date <= last_day,
        )
    )
    orders = orders_res.scalars().all()
    order_ids = [o.id for o in orders]
    order_map = {o.id: o for o in orders}

    if not order_ids:
        return {
            "store_id": store_id, "month": _month,
            "task_completion_pct": 0.0, "avg_delay_hours": 0.0,
            "exception_rate_pct": 0.0, "order_count": 0,
            "by_banquet_type": [],
        }

    # Tasks for those orders
    tasks_res = await db.execute(
        select(ExecutionTask).where(ExecutionTask.banquet_order_id.in_(order_ids))
    )
    tasks = tasks_res.scalars().all()

    # Exceptions for those orders
    exc_res = await db.execute(
        select(ExecutionException).where(ExecutionException.banquet_order_id.in_(order_ids))
    )
    exceptions = exc_res.scalars().all()

    done_statuses = {TaskStatusEnum.DONE, TaskStatusEnum.VERIFIED, TaskStatusEnum.CLOSED}
    total_tasks = len(tasks)
    done_tasks  = sum(1 for t in tasks if t.task_status in done_statuses)
    completion_pct = round(done_tasks / total_tasks * 100, 1) if total_tasks > 0 else 0.0

    # Avg delay (hours): tasks completed after due_time
    delay_hours_list = []
    for t in tasks:
        if t.task_status in done_statuses and t.completed_at and t.due_time:
            diff = (t.completed_at - t.due_time).total_seconds() / 3600
            if diff > 0:
                delay_hours_list.append(diff)
    avg_delay = round(sum(delay_hours_list) / len(delay_hours_list), 1) if delay_hours_list else 0.0

    exception_rate = round(len(exceptions) / len(order_ids) * 100, 1)

    # By banquet type
    type_stats: dict = {}
    for o in orders:
        btype = o.banquet_type.value if hasattr(o.banquet_type, "value") else str(o.banquet_type)
        if btype not in type_stats:
            type_stats[btype] = {"task_count": 0, "done_count": 0, "exception_count": 0, "order_count": 0}
        type_stats[btype]["order_count"] += 1

    for t in tasks:
        o = order_map.get(t.banquet_order_id)
        if not o:
            continue
        btype = o.banquet_type.value if hasattr(o.banquet_type, "value") else str(o.banquet_type)
        type_stats[btype]["task_count"] += 1
        if t.task_status in done_statuses:
            type_stats[btype]["done_count"] += 1

    for e in exceptions:
        o = order_map.get(e.banquet_order_id)
        if not o:
            continue
        btype = o.banquet_type.value if hasattr(o.banquet_type, "value") else str(o.banquet_type)
        type_stats[btype]["exception_count"] += 1

    by_type = [
        {
            "banquet_type":     btype,
            "order_count":      v["order_count"],
            "task_count":       v["task_count"],
            "completion_pct":   round(v["done_count"] / v["task_count"] * 100, 1) if v["task_count"] > 0 else 0.0,
            "exception_count":  v["exception_count"],
        }
        for btype, v in sorted(type_stats.items())
    ]

    return {
        "store_id":            store_id,
        "month":               _month,
        "order_count":         len(order_ids),
        "task_completion_pct": completion_pct,
        "avg_delay_hours":     avg_delay,
        "exception_rate_pct":  exception_rate,
        "by_banquet_type":     by_type,
    }


# ── 2. GET /stores/{id}/analytics/booking-lead-time ─────────────────────────

@router.get("/stores/{store_id}/analytics/booking-lead-time")
async def get_booking_lead_time(
    store_id: str,
    months:   int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """预订提前量分布（<30d / 30-60d / 60-90d / >90d）及均值。"""
    from datetime import timedelta

    cutoff = date_type.today() - timedelta(days=months * 30)

    res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.banquet_date >= cutoff,
            BanquetOrder.order_status != OrderStatusEnum.CANCELLED,
        )
    )
    orders = res.scalars().all()

    if not orders:
        return {
            "store_id": store_id, "months": months, "total": 0,
            "avg_lead_time_days": 0,
            "buckets": {"under_30": 0, "d30_60": 0, "d60_90": 0, "over_90": 0},
        }

    buckets: dict = {"under_30": 0, "d30_60": 0, "d60_90": 0, "over_90": 0}
    lead_times = []

    for o in orders:
        created_date = o.created_at.date() if hasattr(o.created_at, "date") else o.created_at
        lead_days = (o.banquet_date - created_date).days
        if lead_days < 0:
            lead_days = 0
        lead_times.append(lead_days)
        if lead_days < 30:
            buckets["under_30"] += 1
        elif lead_days <= 60:
            buckets["d30_60"] += 1
        elif lead_days <= 90:
            buckets["d60_90"] += 1
        else:
            buckets["over_90"] += 1

    avg = round(sum(lead_times) / len(lead_times)) if lead_times else 0
    total = len(orders)
    bucket_pcts = {k: round(v / total * 100, 1) for k, v in buckets.items()}

    return {
        "store_id":           store_id,
        "months":             months,
        "total":              total,
        "avg_lead_time_days": avg,
        "buckets":            buckets,
        "bucket_pcts":        bucket_pcts,
    }


# ── 3. GET /stores/{id}/analytics/customer-retention ────────────────────────

@router.get("/stores/{store_id}/analytics/customer-retention")
async def get_customer_retention(
    store_id: str,
    months:   int = Query(12, ge=1, le=36),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """客户保留分析：复购率、客户终身价值均值、Top 复购客户。"""
    from datetime import timedelta

    cutoff = date_type.today() - timedelta(days=months * 30)

    res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.banquet_date >= cutoff,
            BanquetOrder.order_status.in_([
                OrderStatusEnum.COMPLETED,
                OrderStatusEnum.SETTLED if hasattr(OrderStatusEnum, "SETTLED") else OrderStatusEnum.COMPLETED,
            ]),
        )
    )
    orders = res.scalars().all()

    cust_map: dict = {}
    for o in orders:
        cid = o.customer_id
        if cid not in cust_map:
            cust_map[cid] = {"order_count": 0, "total_fen": 0}
        cust_map[cid]["order_count"] += 1
        cust_map[cid]["total_fen"] += o.total_amount_fen

    total_customers = len(cust_map)
    repeat_customers = sum(1 for v in cust_map.values() if v["order_count"] > 1)
    repeat_rate = round(repeat_customers / total_customers * 100, 1) if total_customers > 0 else 0.0

    all_values = [v["total_fen"] for v in cust_map.values()]
    avg_ltv_yuan = round(sum(all_values) / len(all_values) / 100, 2) if all_values else 0.0

    # Top 5 by order count then by value
    top_raw = sorted(cust_map.items(), key=lambda x: (-x[1]["order_count"], -x[1]["total_fen"]))[:5]

    # Fetch names for top customers
    top_ids = [cid for cid, _ in top_raw]
    names_map: dict = {}
    if top_ids:
        cust_res = await db.execute(
            select(BanquetCustomer).where(BanquetCustomer.id.in_(top_ids))
        )
        for c in cust_res.scalars().all():
            names_map[c.id] = c.customer_name

    top_customers = [
        {
            "customer_id":   cid,
            "name":          names_map.get(cid, "—"),
            "order_count":   v["order_count"],
            "total_yuan":    round(v["total_fen"] / 100, 2),
        }
        for cid, v in top_raw
    ]

    return {
        "store_id":            store_id,
        "months":              months,
        "total_customers":     total_customers,
        "repeat_customers":    repeat_customers,
        "repeat_rate_pct":     repeat_rate,
        "avg_ltv_yuan":        avg_ltv_yuan,
        "top_customers":       top_customers,
    }


# ── 4. POST /stores/{id}/orders/{oid}/staffing-plan ─────────────────────────

_STAFFING_RULES: dict = {
    "wedding":  {"kitchen": 0.15, "service": 0.30, "decor": 0.05, "manager": 0.03},
    "birthday": {"kitchen": 0.12, "service": 0.25, "decor": 0.03, "manager": 0.02},
    "business": {"kitchen": 0.10, "service": 0.20, "decor": 0.02, "manager": 0.04},
    "other":    {"kitchen": 0.10, "service": 0.20, "decor": 0.02, "manager": 0.02},
}
_MIN_STAFF = 1

def _compute_staffing(table_count: int, banquet_type: str) -> dict:
    btype = banquet_type.lower() if banquet_type else "other"
    rules = _STAFFING_RULES.get(btype, _STAFFING_RULES["other"])
    people = table_count * 10   # est. ~10 guests per table
    staffing = {}
    for role, factor in rules.items():
        staffing[role] = max(_MIN_STAFF, round(people * factor))
    staffing["total"] = sum(v for k, v in staffing.items() if k != "total")
    return staffing


@router.post("/stores/{store_id}/orders/{order_id}/staffing-plan")
async def create_staffing_plan(
    store_id:  str,
    order_id:  str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成并持久化排班建议（规则引擎：桌数×宴会类型）。"""
    order_res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.id == order_id,
            BanquetOrder.store_id == store_id,
        )
    )
    order = order_res.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    btype = order.banquet_type.value if hasattr(order.banquet_type, "value") else str(order.banquet_type)
    staffing = _compute_staffing(order.table_count, btype)

    result = {
        "order_id":     order_id,
        "banquet_type": btype,
        "table_count":  order.table_count,
        "staffing":     staffing,
    }

    log = BanquetAgentActionLog(
        id=str(__import__("uuid").uuid4()),
        agent_type=BanquetAgentTypeEnum.SCHEDULING,
        action_type="staffing_plan",
        related_object_type="order",
        related_object_id=order_id,
        action_result=result,
        suggestion_text=f"建议配置：{staffing.get('total', 0)} 人",
        is_human_approved=None,
    )
    db.add(log)
    await db.commit()

    return result


# ── 5. GET /stores/{id}/orders/{oid}/staffing-plan ───────────────────────────

@router.get("/stores/{store_id}/orders/{order_id}/staffing-plan")
async def get_staffing_plan(
    store_id:  str,
    order_id:  str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """读取最新排班建议（ActionLog），或实时计算。"""
    order_res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.id == order_id,
            BanquetOrder.store_id == store_id,
        )
    )
    order = order_res.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    log_res = await db.execute(
        select(BanquetAgentActionLog).where(
            BanquetAgentActionLog.related_object_type == "order",
            BanquetAgentActionLog.related_object_id   == order_id,
            BanquetAgentActionLog.action_type         == "staffing_plan",
        ).order_by(BanquetAgentActionLog.created_at.desc()).limit(1)
    )
    log = log_res.scalars().first()

    if log and log.action_result:
        return {**log.action_result, "generated_at": log.created_at.isoformat() if log.created_at else None}

    # Live calculation (no persist)
    btype = order.banquet_type.value if hasattr(order.banquet_type, "value") else str(order.banquet_type)
    staffing = _compute_staffing(order.table_count, btype)
    return {
        "order_id":     order_id,
        "banquet_type": btype,
        "table_count":  order.table_count,
        "staffing":     staffing,
        "generated_at": None,
    }


# ── 6. GET /stores/{id}/analytics/yield-by-hall ──────────────────────────────

@router.get("/stores/{store_id}/analytics/yield-by-hall")
async def get_yield_by_hall(
    store_id: str,
    year:     int = Query(default=None),
    month:    int = Query(default=None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """各厅房月收益：使用率 × 均单价，识别高/低效厅。"""
    import calendar as _cal

    today   = date_type.today()
    _year   = year  or today.year
    _month  = month or today.month
    first_day = date_type(_year, _month, 1)
    last_day  = date_type(_year, _month, _cal.monthrange(_year, _month)[1])
    total_days = (_last := (last_day - first_day).days + 1)
    total_slots = total_days * 2   # lunch + dinner

    halls_res = await db.execute(
        select(BanquetHall).where(
            BanquetHall.store_id == store_id,
            BanquetHall.is_active == True,
        )
    )
    halls = halls_res.scalars().all()
    if not halls:
        return {"store_id": store_id, "year": _year, "month": _month, "halls": []}

    hall_ids = [h.id for h in halls]

    bookings_res = await db.execute(
        select(BanquetHallBooking, BanquetOrder).join(
            BanquetOrder, BanquetHallBooking.banquet_order_id == BanquetOrder.id
        ).where(
            BanquetHallBooking.hall_id.in_(hall_ids),
            BanquetHallBooking.slot_date >= first_day,
            BanquetHallBooking.slot_date <= last_day,
        )
    )
    rows = bookings_res.all()

    hall_stats: dict = {h.id: {"booked_slots": 0, "revenue_fen": 0, "order_ids": set()} for h in halls}
    for booking, order in rows:
        hid = booking.hall_id
        if hid in hall_stats:
            hall_stats[hid]["booked_slots"] += 1
            if order.id not in hall_stats[hid]["order_ids"]:
                hall_stats[hid]["order_ids"].add(order.id)
                hall_stats[hid]["revenue_fen"] += order.total_amount_fen

    hall_map = {h.id: h for h in halls}
    result_halls = []
    for hid, stats in hall_stats.items():
        h = hall_map[hid]
        booked = stats["booked_slots"]
        revenue_yuan = round(stats["revenue_fen"] / 100, 2)
        utilization_pct = round(booked / total_slots * 100, 1) if total_slots > 0 else 0.0
        result_halls.append({
            "hall_id":         hid,
            "hall_name":       h.name,
            "hall_type":       h.hall_type.value if hasattr(h.hall_type, "value") else str(h.hall_type),
            "booked_slots":    booked,
            "total_slots":     total_slots,
            "utilization_pct": utilization_pct,
            "revenue_yuan":    revenue_yuan,
            "order_count":     len(stats["order_ids"]),
        })
    result_halls.sort(key=lambda x: -x["revenue_yuan"])

    return {"store_id": store_id, "year": _year, "month": _month, "halls": result_halls}


# ── 7. GET /stores/{id}/analytics/cancellation-analysis ─────────────────────

@router.get("/stores/{store_id}/analytics/cancellation-analysis")
async def get_cancellation_analysis(
    store_id: str,
    months:   int = Query(3, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """取消分析：数量、预估损失¥、按类型/提前量分桶。"""
    from datetime import timedelta

    cutoff = date_type.today() - timedelta(days=months * 30)

    res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.order_status == OrderStatusEnum.CANCELLED,
            BanquetOrder.created_at >= cutoff,
        )
    )
    orders = res.scalars().all()

    if not orders:
        return {
            "store_id": store_id, "months": months,
            "total": 0, "revenue_lost_yuan": 0.0,
            "by_banquet_type": [], "by_lead_time": {},
        }

    revenue_lost_fen = sum(o.total_amount_fen for o in orders)
    type_map: dict = {}
    lead_buckets: dict = {"urgent_7d": 0, "d7_30": 0, "over_30d": 0}

    for o in orders:
        btype = o.banquet_type.value if hasattr(o.banquet_type, "value") else str(o.banquet_type)
        type_map[btype] = type_map.get(btype, 0) + 1

        created_date = o.created_at.date() if hasattr(o.created_at, "date") else date_type.today()
        lead_days = (o.banquet_date - created_date).days
        if lead_days < 7:
            lead_buckets["urgent_7d"] += 1
        elif lead_days <= 30:
            lead_buckets["d7_30"] += 1
        else:
            lead_buckets["over_30d"] += 1

    by_type = [{"banquet_type": k, "count": v} for k, v in sorted(type_map.items(), key=lambda x: -x[1])]

    return {
        "store_id":          store_id,
        "months":            months,
        "total":             len(orders),
        "revenue_lost_yuan": round(revenue_lost_fen / 100, 2),
        "by_banquet_type":   by_type,
        "by_lead_time":      lead_buckets,
    }


# ── 8. GET /stores/{id}/analytics/peak-capacity ──────────────────────────────

@router.get("/stores/{store_id}/analytics/peak-capacity")
async def get_peak_capacity(
    store_id: str,
    months:   int = Query(3, ge=1, le=6),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """峰值容量：最忙日期、月利用率分布、溢价建议。"""
    import calendar as _cal
    from datetime import timedelta

    today = date_type.today()
    start = date_type(today.year, today.month, 1)

    halls_res = await db.execute(
        select(BanquetHall).where(
            BanquetHall.store_id == store_id,
            BanquetHall.is_active == True,
        )
    )
    halls = halls_res.scalars().all()
    hall_count = len(halls)

    if not hall_count:
        return {"store_id": store_id, "months": months,
                "busiest_days": [], "monthly_utilization": [],
                "surge_threshold_pct": 80, "premium_suggestion": "暂无厅房数据"}

    # Gather bookings for next `months` months
    end_month = start + timedelta(days=months * 31)
    end = date_type(end_month.year, end_month.month,
                    _cal.monthrange(end_month.year, end_month.month)[1])

    hall_ids = [h.id for h in halls]
    bookings_res = await db.execute(
        select(BanquetHallBooking).where(
            BanquetHallBooking.hall_id.in_(hall_ids),
            BanquetHallBooking.slot_date >= start,
            BanquetHallBooking.slot_date <= end,
        )
    )
    bookings = bookings_res.scalars().all()

    # Day-level count
    day_count: dict = {}
    month_count: dict = {}
    for b in bookings:
        dstr = b.slot_date.isoformat()
        day_count[dstr] = day_count.get(dstr, 0) + 1
        mkey = dstr[:7]
        month_count[mkey] = month_count.get(mkey, 0) + 1

    busiest_days = sorted(day_count.items(), key=lambda x: -x[1])[:5]

    # Monthly utilization
    monthly_util = []
    for i in range(months):
        mm = (start.month - 1 + i) % 12 + 1
        yy = start.year + (start.month - 1 + i) // 12
        days_in = _cal.monthrange(yy, mm)[1]
        total_slots = days_in * 2 * hall_count
        mkey = f"{yy:04d}-{mm:02d}"
        booked = month_count.get(mkey, 0)
        util_pct = round(booked / total_slots * 100, 1) if total_slots > 0 else 0.0
        monthly_util.append({
            "month": mkey,
            "booked_slots":     booked,
            "total_slots":      total_slots,
            "utilization_pct":  util_pct,
        })

    # Premium suggestion
    high_util_months = [r for r in monthly_util if r["utilization_pct"] >= 80]
    if high_util_months:
        months_str = "、".join(r["month"] for r in high_util_months)
        premium_suggestion = f"建议对 {months_str} 档期宴会加价 15–20%（利用率≥80%）"
    elif any(r["utilization_pct"] >= 60 for r in monthly_util):
        premium_suggestion = "当前利用率适中，可对吉日档期适当加价 5–10%"
    else:
        premium_suggestion = "当前档期充裕，建议推出早鸟优惠促进预订"

    return {
        "store_id":            store_id,
        "months":              months,
        "busiest_days":        [{"date": d, "booking_count": c} for d, c in busiest_days],
        "monthly_utilization": monthly_util,
        "surge_threshold_pct": 80,
        "premium_suggestion":  premium_suggestion,
    }


# ════════════════════════════════════════════════════════════════════════════════
# Phase 16 — 多店对标分析 · 客户赢回营销
# ════════════════════════════════════════════════════════════════════════════════

_ANNIVERSARY_TEMPLATES: dict[str, str] = {
    "wedding":  "尊敬的{name}，时光飞逝，您的婚宴周年纪念日即将到来！衷心感谢您当年选择我们共同见证这美好时刻。期待再次为您服务，如有宴会需求欢迎随时联系我们！",
    "birthday": "尊敬的{name}，您好！距您上次在我们这里举办生日宴已届一年。祝您生日快乐、万事如意，期待再次为您打造难忘的生日庆典！",
    "default":  "尊敬的{name}，您好！距您上次光临已届一年，感谢您对我们的信任。如有宴会、庆典需求，我们随时恭候，欢迎联系预约！",
}

_WIN_BACK_TEMPLATE = (
    "尊敬的{name}，好久不见！您上次在我们这里办宴会是{last_date}，至今已有{days}天。"
    "我们最近推出了全新套餐，期待能再次为您提供优质的宴会服务。如有需求欢迎随时联系，我们将为您提供专属优惠！"
)


# ── 1. 多店 KPI 对比 ─────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/brand-comparison")
async def get_brand_comparison(
    store_id: str,
    year:  int = Query(default=None),
    month: int = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: "User" = Depends(get_current_user),
):
    """品牌旗下所有门店宴会 KPI 对比（营收/订单数/转化率），标注本店排名。"""
    from datetime import timedelta
    from src.models.store import Store as _Store

    today = date_type.today()
    if not year:
        year = today.year
    if not month:
        month = today.month

    brand_id = getattr(_, "brand_id", None)
    if not brand_id:
        brand_id = store_id  # fallback: treat as single-store brand

    # Get all store IDs in brand
    stores_res = await db.execute(
        select(_Store.id, _Store.name).where(_Store.brand_id == brand_id)
    )
    stores = stores_res.all()
    if not stores:
        # Fallback to just the requested store
        stores = [(store_id, store_id)]

    store_map = {s[0]: s[1] for s in stores}
    store_ids = list(store_map.keys())

    # Aggregate per store for the given month
    first_day = date_type(year, month, 1)
    import calendar as _cal2
    last_day = date_type(year, month, _cal2.monthrange(year, month)[1])

    rows = []
    for sid in store_ids:
        # Revenue + order count from BanquetOrder
        orders_res = await db.execute(
            select(BanquetOrder).where(
                and_(
                    BanquetOrder.store_id == sid,
                    BanquetOrder.banquet_date >= first_day,
                    BanquetOrder.banquet_date <= last_day,
                    BanquetOrder.order_status.in_([
                        OrderStatusEnum.CONFIRMED,
                        OrderStatusEnum.COMPLETED,
                    ]),
                )
            )
        )
        orders = orders_res.scalars().all()

        # Leads (for conversion rate)
        leads_res = await db.execute(
            select(func.count(BanquetLead.id)).where(
                BanquetLead.store_id == sid
            )
        )
        lead_count = leads_res.scalar() or 0

        revenue = sum(o.total_amount_fen for o in orders) / 100
        order_count = len(orders)
        conversion_rate = round(order_count / lead_count * 100, 1) if lead_count > 0 else 0.0

        # Repeat rate: customers with >1 order
        from datetime import timedelta
        cutoff = date_type(year, month, 1) - timedelta(days=365)
        hist_res = await db.execute(
            select(BanquetOrder.customer_id, func.count(BanquetOrder.id).label("cnt")).where(
                and_(
                    BanquetOrder.store_id == sid,
                    BanquetOrder.banquet_date >= cutoff,
                    BanquetOrder.order_status.in_([
                        OrderStatusEnum.CONFIRMED,
                        OrderStatusEnum.COMPLETED,
                    ]),
                )
            ).group_by(BanquetOrder.customer_id)
        )
        hist = hist_res.all()
        total_c = len(hist)
        repeat_c = sum(1 for h in hist if h[1] > 1)
        repeat_rate = round(repeat_c / total_c * 100, 1) if total_c > 0 else 0.0

        rows.append({
            "store_id":       sid,
            "store_name":     store_map.get(sid, sid),
            "revenue_yuan":   revenue,
            "order_count":    order_count,
            "conversion_rate_pct": conversion_rate,
            "repeat_rate_pct":    repeat_rate,
            "is_self":        (sid == store_id),
        })

    # Sort by revenue desc, assign rank
    rows.sort(key=lambda r: -r["revenue_yuan"])
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    self_rank = next((r["rank"] for r in rows if r["is_self"]), None)

    # Brand averages
    n = len(rows)
    brand_avg = {
        "store_id":           "brand_avg",
        "store_name":         "品牌均值",
        "revenue_yuan":       round(sum(r["revenue_yuan"] for r in rows) / n, 2) if n else 0,
        "order_count":        round(sum(r["order_count"] for r in rows) / n, 1) if n else 0,
        "conversion_rate_pct": round(sum(r["conversion_rate_pct"] for r in rows) / n, 1) if n else 0,
        "repeat_rate_pct":    round(sum(r["repeat_rate_pct"] for r in rows) / n, 1) if n else 0,
        "is_self":            False,
        "rank":               None,
    }

    return {
        "year":        year,
        "month":       month,
        "total_stores": n,
        "self_rank":   self_rank,
        "stores":      rows,
        "brand_avg":   brand_avg,
    }


# ── 2. 单店 vs 品牌均值 Benchmark ────────────────────────────────────────────

@router.get("/stores/{store_id}/benchmark")
async def get_benchmark(
    store_id: str,
    year:  int = Query(default=None),
    month: int = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: "User" = Depends(get_current_user),
):
    """本店各 KPI 指标 vs 品牌均值的 delta 卡片（含排名）。"""
    comp = await get_brand_comparison(store_id=store_id, year=year, month=month, db=db, _=_)

    self_row = next((r for r in comp["stores"] if r["is_self"]), None)
    avg = comp["brand_avg"]
    total = comp["total_stores"]

    if not self_row:
        return {"year": comp["year"], "month": comp["month"], "metrics": [], "total_stores": total}

    metrics = []
    for key, label in [
        ("revenue_yuan",        "营收"),
        ("order_count",         "订单数"),
        ("conversion_rate_pct", "转化率"),
        ("repeat_rate_pct",     "复购率"),
    ]:
        store_val = self_row[key]
        avg_val   = avg[key]
        delta_pct = round((store_val - avg_val) / avg_val * 100, 1) if avg_val else 0.0
        status = "above" if delta_pct > 2 else ("below" if delta_pct < -2 else "on_par")
        metrics.append({
            "metric":      key,
            "label":       label,
            "store_value": store_val,
            "brand_avg":   avg_val,
            "delta_pct":   delta_pct,
            "status":      status,
            "rank":        self_row["rank"],
            "total_stores": total,
        })

    return {
        "year":        comp["year"],
        "month":       comp["month"],
        "self_rank":   comp["self_rank"],
        "total_stores": total,
        "metrics":     metrics,
    }


# ── 3. 周年/生日提醒 ─────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/customers/upcoming-anniversaries")
async def get_upcoming_anniversaries(
    store_id: str,
    days: int = Query(default=30),
    db: AsyncSession = Depends(get_db),
    _: "User" = Depends(get_current_user),
):
    """近 N 天内将至宴会周年/生日的老客户列表。"""
    from datetime import timedelta

    today = date_type.today()
    end   = today + timedelta(days=days)

    # Get all completed orders for the store, grouped by customer
    orders_res = await db.execute(
        select(BanquetOrder).where(
            and_(
                BanquetOrder.store_id == store_id,
                BanquetOrder.order_status.in_([
                    OrderStatusEnum.COMPLETED,
                ]),
            )
        ).order_by(BanquetOrder.banquet_date.desc())
    )
    orders = orders_res.scalars().all()

    # Find orders whose anniversary (same month+day) falls in [today, today+days]
    items = []
    seen_customers: set = set()
    for o in orders:
        if not o.banquet_date or not o.customer_id:
            continue
        if o.customer_id in seen_customers:
            continue
        bd = o.banquet_date
        # Compute this year's anniversary
        try:
            anniversary = date_type(today.year, bd.month, bd.day)
        except ValueError:
            continue  # Feb 29 on non-leap year
        if anniversary < today:
            # Check next year
            try:
                anniversary = date_type(today.year + 1, bd.month, bd.day)
            except ValueError:
                continue
        if today <= anniversary <= end:
            days_until = (anniversary - today).days
            seen_customers.add(o.customer_id)

            # Load customer name
            cust_res = await db.execute(
                select(BanquetCustomer).where(BanquetCustomer.id == o.customer_id)
            )
            cust = cust_res.scalars().first()

            items.append({
                "customer_id":        o.customer_id,
                "name":               cust.customer_name if cust else "客户",
                "phone":              cust.phone if cust else None,
                "last_banquet_type":  o.banquet_type.value if hasattr(o.banquet_type, "value") else str(o.banquet_type),
                "last_banquet_date":  bd.isoformat(),
                "anniversary_date":   anniversary.isoformat(),
                "days_until":         days_until,
            })

    items.sort(key=lambda x: x["days_until"])
    return {"total": len(items), "items": items, "days": days}


# ── 4. 赢回候选客户 ──────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/customers/win-back-candidates")
async def get_win_back_candidates(
    store_id: str,
    months: int = Query(default=12),
    db: AsyncSession = Depends(get_db),
    _: "User" = Depends(get_current_user),
):
    """N 个月以上未复购的老客户列表（至少有 1 笔历史订单）。"""
    from datetime import timedelta

    today   = date_type.today()
    cutoff  = today - timedelta(days=months * 30)

    # Get all customers who have at least one order
    orders_res = await db.execute(
        select(BanquetOrder).where(
            and_(
                BanquetOrder.store_id == store_id,
                BanquetOrder.order_status.in_([
                    OrderStatusEnum.COMPLETED,
                    OrderStatusEnum.CONFIRMED,
                ]),
            )
        ).order_by(BanquetOrder.banquet_date.desc())
    )
    orders = orders_res.scalars().all()

    # Group by customer: find last order date
    from collections import defaultdict
    cust_orders: dict = defaultdict(list)
    for o in orders:
        if o.customer_id:
            cust_orders[o.customer_id].append(o)

    candidates = []
    for cid, c_orders in cust_orders.items():
        last_order = max(c_orders, key=lambda o: o.banquet_date)
        if last_order.banquet_date >= cutoff:
            continue  # Active customer, skip
        days_since = (today - last_order.banquet_date).days
        total_yuan = sum(o.total_amount_fen for o in c_orders) / 100

        cust_res = await db.execute(
            select(BanquetCustomer).where(BanquetCustomer.id == cid)
        )
        cust = cust_res.scalars().first()

        candidates.append({
            "customer_id":    cid,
            "name":           cust.customer_name if cust else "客户",
            "phone":          cust.phone if cust else None,
            "last_order_date": last_order.banquet_date.isoformat(),
            "days_since":     days_since,
            "total_orders":   len(c_orders),
            "total_yuan":     total_yuan,
        })

    candidates.sort(key=lambda x: x["days_since"])
    return {"total": len(candidates), "items": candidates, "months": months}


# ── 5. 生成周年话术 ──────────────────────────────────────────────────────────

class _OutreachBody(BaseModel):
    channel: str = Field(default="wechat")

@router.post("/stores/{store_id}/customers/{customer_id}/anniversary-message")
async def generate_anniversary_message(
    store_id:    str,
    customer_id: str,
    body: _OutreachBody = Body(default_factory=_OutreachBody),
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
):
    """生成宴会周年/生日触达话术并记录到 ActionLog。"""
    cust_res = await db.execute(
        select(BanquetCustomer).where(BanquetCustomer.id == customer_id)
    )
    cust = cust_res.scalars().first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Get last order for type info
    ord_res = await db.execute(
        select(BanquetOrder).where(
            and_(
                BanquetOrder.customer_id == customer_id,
                BanquetOrder.store_id == store_id,
                BanquetOrder.order_status == OrderStatusEnum.COMPLETED,
            )
        ).order_by(BanquetOrder.banquet_date.desc())
    )
    last_order = ord_res.scalars().first()

    btype = "default"
    if last_order and hasattr(last_order.banquet_type, "value"):
        btype = last_order.banquet_type.value
    template = _ANNIVERSARY_TEMPLATES.get(btype, _ANNIVERSARY_TEMPLATES["default"])
    message  = template.format(name=cust.customer_name)

    result = {
        "customer_id":   customer_id,
        "customer_name": cust.customer_name,
        "outreach_type": "anniversary",
        "channel":       body.channel,
        "message":       message,
    }

    log = BanquetAgentActionLog(
        id=str(uuid.uuid4()),
        agent_type=BanquetAgentTypeEnum.FOLLOWUP,
        action_type="anniversary_message",
        related_object_type="customer",
        related_object_id=customer_id,
        action_result=result,
    )
    db.add(log)
    await db.commit()
    return result


# ── 6. 生成赢回话术 ──────────────────────────────────────────────────────────

@router.post("/stores/{store_id}/customers/{customer_id}/win-back-message")
async def generate_win_back_message(
    store_id:    str,
    customer_id: str,
    body: _OutreachBody = Body(default_factory=_OutreachBody),
    db: AsyncSession = Depends(get_db),
    current_user: "User" = Depends(get_current_user),
):
    """生成客户赢回话术并记录到 ActionLog。"""
    cust_res = await db.execute(
        select(BanquetCustomer).where(BanquetCustomer.id == customer_id)
    )
    cust = cust_res.scalars().first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    ord_res = await db.execute(
        select(BanquetOrder).where(
            and_(
                BanquetOrder.customer_id == customer_id,
                BanquetOrder.store_id == store_id,
            )
        ).order_by(BanquetOrder.banquet_date.desc())
    )
    last_order = ord_res.scalars().first()

    from datetime import timedelta
    today = date_type.today()
    if last_order and last_order.banquet_date:
        days_since = (today - last_order.banquet_date).days
        last_date  = last_order.banquet_date.strftime("%Y年%m月%d日")
    else:
        days_since = 0
        last_date  = "不久前"

    message = _WIN_BACK_TEMPLATE.format(
        name=cust.customer_name,
        last_date=last_date,
        days=days_since,
    )

    result = {
        "customer_id":   customer_id,
        "customer_name": cust.customer_name,
        "outreach_type": "win_back",
        "channel":       body.channel,
        "message":       message,
        "days_since":    days_since,
    }

    log = BanquetAgentActionLog(
        id=str(uuid.uuid4()),
        agent_type=BanquetAgentTypeEnum.FOLLOWUP,
        action_type="win_back_message",
        related_object_type="customer",
        related_object_id=customer_id,
        action_result=result,
    )
    db.add(log)
    await db.commit()
    return result


# ── 7. 客户触达历史 ──────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/customers/{customer_id}/outreach-history")
async def get_outreach_history(
    store_id:    str,
    customer_id: str,
    limit: int = Query(default=20),
    db: AsyncSession = Depends(get_db),
    _: "User" = Depends(get_current_user),
):
    """客户所有触达记录（followup / anniversary / win_back）。"""
    logs_res = await db.execute(
        select(BanquetAgentActionLog).where(
            and_(
                BanquetAgentActionLog.related_object_type == "customer",
                BanquetAgentActionLog.related_object_id   == customer_id,
                BanquetAgentActionLog.action_type.in_([
                    "followup_message",
                    "anniversary_message",
                    "win_back_message",
                ]),
            )
        ).order_by(BanquetAgentActionLog.created_at.desc()).limit(limit)
    )
    logs = logs_res.scalars().all()

    items = []
    for log in logs:
        result = log.action_result or {}
        items.append({
            "log_id":       log.id,
            "action_type":  log.action_type,
            "outreach_type": result.get("outreach_type", log.action_type),
            "channel":      result.get("channel"),
            "message":      result.get("message"),
            "created_at":   log.created_at.isoformat() if log.created_at else None,
        })

    return {"total": len(items), "items": items}


# ── 8. 月度执行摘要 ──────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/executive-summary")
async def get_executive_summary(
    store_id: str,
    year:  int = Query(default=None),
    month: int = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: "User" = Depends(get_current_user),
):
    """月度经营执行摘要：10 个核心指标 + 亮点/风险规则文字。"""
    import calendar as _cal3
    from datetime import timedelta

    today = date_type.today()
    if not year:
        year = today.year
    if not month:
        month = today.month

    first_day = date_type(year, month, 1)
    last_day  = date_type(year, month, _cal3.monthrange(year, month)[1])

    # All orders for month
    orders_res = await db.execute(
        select(BanquetOrder).where(
            and_(
                BanquetOrder.store_id == store_id,
                BanquetOrder.banquet_date >= first_day,
                BanquetOrder.banquet_date <= last_day,
            )
        )
    )
    orders = orders_res.scalars().all()

    active   = [o for o in orders if o.order_status in (OrderStatusEnum.CONFIRMED, OrderStatusEnum.COMPLETED)]
    cancelled= [o for o in orders if o.order_status == OrderStatusEnum.CANCELLED]

    revenue_yuan      = sum(o.total_amount_fen for o in active) / 100
    order_count       = len(active)
    avg_order_yuan    = round(revenue_yuan / order_count, 2) if order_count else 0.0
    cancel_count      = len(cancelled)
    cancel_rate_pct   = round(cancel_count / len(orders) * 100, 1) if orders else 0.0

    # Revenue lost
    revenue_lost_yuan = sum(o.total_amount_fen for o in cancelled) / 100

    # Leads for conversion
    leads_res = await db.execute(
        select(func.count(BanquetLead.id)).where(BanquetLead.store_id == store_id)
    )
    lead_count      = leads_res.scalar() or 0
    conversion_rate = round(order_count / lead_count * 100, 1) if lead_count > 0 else 0.0

    # Tasks
    from datetime import timedelta
    tasks_res = await db.execute(
        select(ExecutionTask).where(
            and_(
                ExecutionTask.banquet_order_id.in_([o.id for o in active]) if active else False,
            )
        )
    )
    tasks = tasks_res.scalars().all() if active else []
    done_tasks  = [t for t in tasks if t.task_status == TaskStatusEnum.DONE]
    task_compl  = round(len(done_tasks) / len(tasks) * 100, 1) if tasks else 0.0

    # Exceptions
    exc_res = await db.execute(
        select(ExecutionException).where(
            ExecutionException.banquet_order_id.in_([o.id for o in active]) if active else False,
        )
    )
    exceptions = exc_res.scalars().all() if active else []
    exc_rate = round(len(exceptions) / order_count * 100, 1) if order_count else 0.0

    # Repeat rate (customers with >1 order in last year)
    cutoff = first_day - timedelta(days=365)
    hist_res = await db.execute(
        select(BanquetOrder.customer_id, func.count(BanquetOrder.id).label("cnt")).where(
            and_(
                BanquetOrder.store_id == store_id,
                BanquetOrder.banquet_date >= cutoff,
                BanquetOrder.order_status.in_([
                    OrderStatusEnum.CONFIRMED,
                    OrderStatusEnum.COMPLETED,
                ]),
            )
        ).group_by(BanquetOrder.customer_id)
    )
    hist = hist_res.all()
    total_c  = len(hist)
    repeat_c = sum(1 for h in hist if h[1] > 1)
    repeat_rate = round(repeat_c / total_c * 100, 1) if total_c > 0 else 0.0

    # Revenue target achievement
    target_res = await db.execute(
        select(BanquetRevenueTarget).where(
            and_(
                BanquetRevenueTarget.store_id == store_id,
                BanquetRevenueTarget.year  == year,
                BanquetRevenueTarget.month == month,
            )
        )
    )
    target = target_res.scalars().first()
    target_yuan = target.target_amount_fen / 100 if target and target.target_amount_fen else None
    achievement_pct = round(revenue_yuan / target_yuan * 100, 1) if target_yuan else None

    metrics = {
        "revenue_yuan":          revenue_yuan,
        "order_count":           order_count,
        "avg_order_yuan":        avg_order_yuan,
        "conversion_rate_pct":   conversion_rate,
        "task_completion_pct":   task_compl,
        "exception_rate_pct":    exc_rate,
        "repeat_rate_pct":       repeat_rate,
        "cancellation_rate_pct": cancel_rate_pct,
        "revenue_lost_yuan":     revenue_lost_yuan,
        "target_achievement_pct": achievement_pct,
    }

    # Rule-based highlights & risks
    highlights = []
    risks      = []

    if order_count > 0:
        highlights.append(f"本月共 {order_count} 单宴会，营收 ¥{revenue_yuan:,.0f}")
    if repeat_rate >= 30:
        highlights.append(f"客户复购率 {repeat_rate}%，留存表现优秀")
    if task_compl >= 90:
        highlights.append(f"任务完成率 {task_compl}%，执行团队表现出色")
    if achievement_pct and achievement_pct >= 100:
        highlights.append(f"月度目标达成率 {achievement_pct}%，超额完成！")

    if cancel_rate_pct > 15:
        risks.append(f"取消率 {cancel_rate_pct}% 偏高（损失 ¥{revenue_lost_yuan:,.0f}），建议加强签约跟进")
    if exc_rate > 10:
        risks.append(f"异常率 {exc_rate}%，建议复盘服务流程")
    if conversion_rate < 20 and lead_count > 0:
        risks.append(f"线索转化率仅 {conversion_rate}%，建议强化跟进话术")
    if achievement_pct and achievement_pct < 80:
        risks.append(f"目标达成率 {achievement_pct}%，距目标仍有差距")

    return {
        "year":       year,
        "month":      month,
        "store_id":   store_id,
        "metrics":    metrics,
        "highlights": highlights[:3],
        "risks":      risks[:3],
    }


# ════════════════════════════════════════════════════════════════════════════
# Phase 17 — 套餐毛利分析 · 季节性规律 · 智能运营提醒
# ════════════════════════════════════════════════════════════════════════════

# ── 1. 套餐毛利排行 ────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/menu-packages/profitability")
async def get_menu_profitability(
    store_id: str,
    year:  int = Query(default=0),
    month: int = Query(default=0),
    db:    AsyncSession = Depends(get_db),
    _:     User         = Depends(get_current_user),
):
    """套餐毛利排行：理论毛利率（from MenuPackage）× 实际毛利率（from ProfitSnapshot）"""
    from datetime import timedelta

    # 查有效套餐
    pkgs_res = await db.execute(
        select(MenuPackage).where(
            MenuPackage.store_id == store_id,
            MenuPackage.is_active.is_(True),
        )
    )
    pkgs = pkgs_res.scalars().all()
    if not pkgs:
        return {"store_id": store_id, "packages": []}

    # 查利润快照（通过 BanquetOrder 关联 store_id + banquet_type）
    snap_q = (
        select(BanquetProfitSnapshot, BanquetOrder.banquet_type)
        .join(BanquetOrder, BanquetProfitSnapshot.banquet_order_id == BanquetOrder.id)
        .where(BanquetOrder.store_id == store_id)
    )
    if year and month:
        start = date_type(year, month, 1)
        end_month = month + 1 if month < 12 else 1
        end_year  = year if month < 12 else year + 1
        end   = date_type(end_year, end_month, 1)
        snap_q = snap_q.where(
            BanquetOrder.banquet_date >= start,
            BanquetOrder.banquet_date <  end,
        )
    snaps_res = await db.execute(snap_q)
    snap_rows = snaps_res.all()

    # 按 banquet_type 聚合快照
    snap_by_type: dict = {}
    for row in snap_rows:
        s  = row[0]
        bt = row[1]
        key = bt.value if hasattr(bt, "value") else str(bt)
        if key not in snap_by_type:
            snap_by_type[key] = {"revenue": 0, "cost": 0}
        rev = getattr(s, "revenue_fen", 0) or 0
        cost = (
            (getattr(s, "ingredient_cost_fen", 0) or 0)
            + (getattr(s, "labor_cost_fen",     0) or 0)
            + (getattr(s, "material_cost_fen",  0) or 0)
            + (getattr(s, "other_cost_fen",     0) or 0)
        )
        snap_by_type[key]["revenue"] += rev
        snap_by_type[key]["cost"]    += cost

    # 查订单数量
    order_q = select(
        BanquetOrder.banquet_type,
        func.count(BanquetOrder.id).label("cnt"),
    ).where(
        BanquetOrder.store_id == store_id,
        BanquetOrder.order_status.in_([OrderStatusEnum.CONFIRMED, OrderStatusEnum.COMPLETED]),
    ).group_by(BanquetOrder.banquet_type)
    order_res = await db.execute(order_q)
    order_cnt_by_type = {
        (r[0].value if hasattr(r[0], "value") else str(r[0])): r[1]
        for r in order_res.all()
    }

    rows = []
    for pkg in pkgs:
        price_fen = getattr(pkg, "suggested_price_fen", 0) or 0
        cost_fen  = getattr(pkg, "cost_fen", 0) or 0
        theo_margin = round((price_fen - cost_fen) / price_fen * 100, 1) if price_fen else None

        bt = getattr(pkg, "banquet_type", None)
        bt_key = bt.value if hasattr(bt, "value") else str(bt)
        snap = snap_by_type.get(bt_key)
        actual_margin: float | None = None
        if snap and snap["revenue"] > 0:
            actual_margin = round((snap["revenue"] - snap["cost"]) / snap["revenue"] * 100, 1)

        rows.append({
            "pkg_id":               str(pkg.id),
            "name":                 pkg.name,
            "banquet_type":         bt_key,
            "suggested_price_yuan": round(price_fen / 100, 2),
            "cost_yuan":            round(cost_fen  / 100, 2),
            "theoretical_margin_pct": theo_margin,
            "actual_margin_pct":    actual_margin,
            "order_count":          order_cnt_by_type.get(bt_key, 0),
        })

    rows.sort(key=lambda r: (r["actual_margin_pct"] or r["theoretical_margin_pct"] or 0), reverse=True)
    return {"store_id": store_id, "packages": rows}


# ── 2. 单套餐毛利明细 ──────────────────────────────────────────────────────

@router.get("/stores/{store_id}/menu-packages/{pkg_id}/margin-detail")
async def get_menu_package_detail(
    store_id: str,
    pkg_id:   str,
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """单套餐明细：菜品列表 + 近6月毛利率趋势"""
    from datetime import timedelta
    from src.models.banquet import MenuPackageItem

    pkg_res = await db.execute(
        select(MenuPackage).where(MenuPackage.id == pkg_id, MenuPackage.store_id == store_id)
    )
    pkg = pkg_res.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="套餐不存在")

    items_res = await db.execute(
        select(MenuPackageItem).where(MenuPackageItem.menu_package_id == pkg_id)
    )
    items = items_res.scalars().all()

    # 近6个月趋势
    today = date_type.today()
    bt = getattr(pkg, "banquet_type", None)
    bt_key = bt.value if hasattr(bt, "value") else str(bt)
    trend = []
    for i in range(5, -1, -1):
        m = (today.month - i - 1) % 12 + 1
        y = today.year - ((today.month - i - 1) // 12 + (1 if (today.month - i - 1) < 0 else 0))
        start = date_type(y, m, 1)
        end_m = m + 1 if m < 12 else 1
        end_y = y if m < 12 else y + 1
        end   = date_type(end_y, end_m, 1)
        snaps_res = await db.execute(
            select(BanquetProfitSnapshot)
            .join(BanquetOrder, BanquetProfitSnapshot.banquet_order_id == BanquetOrder.id)
            .where(
                BanquetOrder.store_id    == store_id,
                BanquetOrder.banquet_date >= start,
                BanquetOrder.banquet_date <  end,
            )
        )
        snaps = snaps_res.scalars().all()
        rev  = sum((getattr(s, "revenue_fen", 0) or 0) for s in snaps)
        cost = sum((
            (getattr(s, "ingredient_cost_fen", 0) or 0)
            + (getattr(s, "labor_cost_fen",     0) or 0)
            + (getattr(s, "material_cost_fen",  0) or 0)
            + (getattr(s, "other_cost_fen",     0) or 0)
        ) for s in snaps)
        margin = round((rev - cost) / rev * 100, 1) if rev > 0 else None
        trend.append({"month": f"{y:04d}-{m:02d}", "margin_pct": margin})

    return {
        "pkg": {
            "id":                   str(pkg.id),
            "name":                 pkg.name,
            "banquet_type":         bt_key,
            "suggested_price_yuan": round((getattr(pkg, "suggested_price_fen", 0) or 0) / 100, 2),
            "cost_yuan":            round((getattr(pkg, "cost_fen", 0) or 0) / 100, 2),
        },
        "items": [
            {
                "dish_name":     item.dish_name,
                "quantity":      item.quantity,
                "item_type":     item.item_type,
                "replace_group": item.replace_group,
            }
            for item in items
        ],
        "margin_trend": trend,
    }


# ── 3. 季节性规律 ──────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/seasonal-patterns")
async def get_seasonal_patterns(
    store_id: str,
    years:    int = Query(default=2),
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """月度/周几峰谷规律（过去 N 年历史订单）"""
    from datetime import timedelta

    cutoff = date_type.today() - timedelta(days=years * 365)
    orders_res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.order_status.in_([OrderStatusEnum.CONFIRMED, OrderStatusEnum.COMPLETED]),
            BanquetOrder.banquet_date >= cutoff,
        )
    )
    orders = orders_res.scalars().all()

    monthly_orders:  dict[int, int]   = {m: 0 for m in range(1, 13)}
    monthly_revenue: dict[int, float] = {m: 0.0 for m in range(1, 13)}
    weekly_orders:   dict[int, int]   = {d: 0 for d in range(7)}

    for o in orders:
        bd = o.banquet_date
        monthly_orders[bd.month]  += 1
        monthly_revenue[bd.month] += (o.total_amount_fen or 0) / 100
        weekly_orders[bd.weekday()] += 1

    total_months = max(years * 12, 1)
    avg_monthly  = sum(monthly_orders.values()) / 12

    monthly = []
    for m in range(1, 13):
        cnt = monthly_orders[m]
        rev = monthly_revenue[m]
        monthly.append({
            "month":            m,
            "avg_orders":       round(cnt / years, 1),
            "avg_revenue_yuan": round(rev / years, 2),
            "is_peak":          avg_monthly > 0 and cnt > avg_monthly * 1.2,
            "is_low":           cnt < avg_monthly * 0.8,
        })

    total_weekly = sum(weekly_orders.values()) or 1
    weekday_labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekly = [
        {
            "weekday":      d,
            "label":        weekday_labels[d],
            "avg_orders":   round(weekly_orders[d] / years, 1),
            "relative_pct": round(weekly_orders[d] / total_weekly * 100, 1),
        }
        for d in range(7)
    ]

    return {"store_id": store_id, "monthly": monthly, "weekly": weekly}


# ── 4. 宴会类型同期对比 ────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/banquet-type-trends")
async def get_banquet_type_trends(
    store_id: str,
    year:     int = Query(default=0),
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """当年 vs 去年同期宴会类型订单量/营收对比"""
    this_year = year or date_type.today().year
    last_year = this_year - 1

    async def _fetch_year(y: int):
        start = date_type(y, 1, 1)
        end   = date_type(y, 12, 31)
        res = await db.execute(
            select(BanquetOrder).where(
                BanquetOrder.store_id == store_id,
                BanquetOrder.order_status.in_([OrderStatusEnum.CONFIRMED, OrderStatusEnum.COMPLETED]),
                BanquetOrder.banquet_date.between(start, end),
            )
        )
        return res.scalars().all()

    this_orders, last_orders = await _fetch_year(this_year), await _fetch_year(last_year)

    def _aggregate(orders):
        """按 banquet_type × month 聚合"""
        agg: dict = {}
        for o in orders:
            bt = o.banquet_type.value if hasattr(o.banquet_type, "value") else str(o.banquet_type)
            m  = o.banquet_date.month
            if bt not in agg:
                agg[bt] = {mo: {"orders": 0, "revenue_yuan": 0.0} for mo in range(1, 13)}
            agg[bt][m]["orders"]       += 1
            agg[bt][m]["revenue_yuan"] += (o.total_amount_fen or 0) / 100
        return agg

    this_agg = _aggregate(this_orders)
    last_agg = _aggregate(last_orders)

    all_types = sorted(set(list(this_agg.keys()) + list(last_agg.keys())))
    bt_labels = {
        "wedding": "婚宴", "birthday": "寿宴", "business": "商务宴", "full_month": "满月宴",
        "graduation": "升学宴", "other": "其他",
    }

    result = []
    for bt in all_types:
        this_by_month = [
            {"month": m, **this_agg.get(bt, {}).get(m, {"orders": 0, "revenue_yuan": 0.0})}
            for m in range(1, 13)
        ]
        last_by_month = [
            {"month": m, **last_agg.get(bt, {}).get(m, {"orders": 0, "revenue_yuan": 0.0})}
            for m in range(1, 13)
        ]
        this_total = sum(r["orders"] for r in this_by_month)
        last_total = sum(r["orders"] for r in last_by_month)
        yoy_growth = round((this_total - last_total) / last_total * 100, 1) if last_total else None

        result.append({
            "type":           bt,
            "label":          bt_labels.get(bt, bt),
            "this_year":      this_by_month,
            "last_year":      last_by_month,
            "yoy_growth_pct": yoy_growth,
        })

    return {"store_id": store_id, "year": this_year, "types": result}


# ── 5. 当日运营简报 ────────────────────────────────────────────────────────

async def _build_daily_brief(store_id: str, days: int, db: AsyncSession) -> dict:
    """共用逻辑：汇总未来 days 天宴会的待办事项"""
    from datetime import timedelta

    today = date_type.today()
    end   = today + timedelta(days=days)

    orders_res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.order_status.in_([OrderStatusEnum.CONFIRMED, OrderStatusEnum.COMPLETED]),
            BanquetOrder.banquet_date.between(today, end),
        )
    )
    orders = orders_res.scalars().all()

    alerts = []
    for o in orders:
        # 待完成任务
        tasks_res = await db.execute(
            select(ExecutionTask).where(
                ExecutionTask.banquet_order_id == o.id,
                ExecutionTask.task_status.in_([TaskStatusEnum.PENDING, TaskStatusEnum.IN_PROGRESS]),
            )
        )
        pending_tasks = len(tasks_res.scalars().all())

        # 未收款
        paid        = getattr(o, "paid_fen", 0) or 0
        total       = getattr(o, "total_amount_fen", 0) or 0
        unpaid_yuan = round((total - paid) / 100, 2) if total > paid else 0.0

        # 未处理异常
        exc_res = await db.execute(
            select(ExecutionException).where(ExecutionException.banquet_order_id == o.id)
        )
        open_exceptions = len(exc_res.scalars().all())

        # 风险级别
        days_until = (o.banquet_date - today).days
        risk_level = "ok"
        if pending_tasks > 3 or (unpaid_yuan > 0 and total > 0 and paid / total < 0.5) \
                or (days_until <= 3 and paid == 0 and total > 0):
            risk_level = "high"
        elif pending_tasks > 0 or unpaid_yuan > 0 or open_exceptions > 0:
            risk_level = "medium"

        bt = o.banquet_type.value if hasattr(o.banquet_type, "value") else str(o.banquet_type)
        alerts.append({
            "order_id":       str(o.id),
            "banquet_date":   str(o.banquet_date),
            "banquet_type":   bt,
            "days_until":     days_until,
            "risk_level":     risk_level,
            "pending_tasks":  pending_tasks,
            "unpaid_yuan":    unpaid_yuan,
            "open_exceptions": open_exceptions,
        })

    alerts.sort(key=lambda a: {"high": 0, "medium": 1, "ok": 2}[a["risk_level"]])

    today_count = sum(1 for a in alerts if a["days_until"] == 0)
    return {
        "store_id":        store_id,
        "today_banquets":  today_count,
        "next_n_banquets": len(alerts),
        "days":            days,
        "alerts":          alerts,
    }


@router.get("/stores/{store_id}/operations/daily-brief")
async def get_daily_brief(
    store_id: str,
    days:     int = Query(default=7),
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """当日运营简报：未来 N 天宴会的待办/未收/异常汇总"""
    return await _build_daily_brief(store_id, days, db)


# ── 6. 未来风险预警 ────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/operations/upcoming-alerts")
async def get_upcoming_alerts(
    store_id: str,
    days:     int = Query(default=14),
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """未来 N 天宴会风险预警（仅返回 high/medium）"""
    brief = await _build_daily_brief(store_id, days, db)
    high_medium = [a for a in brief["alerts"] if a["risk_level"] in ("high", "medium")]
    return {
        "store_id":     store_id,
        "days":         days,
        "total_alerts": len(high_medium),
        "high":         sum(1 for a in high_medium if a["risk_level"] == "high"),
        "medium":       sum(1 for a in high_medium if a["risk_level"] == "medium"),
        "alerts":       high_medium,
    }


# ── 7. 推送当日简报 ────────────────────────────────────────────────────────

@router.post("/stores/{store_id}/operations/daily-brief/push")
async def push_daily_brief(
    store_id:     str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """将当日简报写入 ActionLog，模拟推送"""
    brief = await _build_daily_brief(store_id, 7, db)

    log = BanquetAgentActionLog(
        agent_type          = BanquetAgentTypeEnum.FOLLOWUP,
        related_object_type = "store",
        related_object_id   = store_id,
        action_type         = "daily_brief",
        action_result       = brief,
        suggestion_text     = f"今日宴会 {brief['today_banquets']} 场，{brief['days']} 天内预警 {len(brief['alerts'])} 条",
        is_human_approved   = False,
    )
    db.add(log)
    await db.commit()

    return {
        "pushed_at":   datetime.utcnow().isoformat(),
        "alert_count": len(brief["alerts"]),
        "high_count":  sum(1 for a in brief["alerts"] if a["risk_level"] == "high"),
    }


# ── 8. 营收预测 ────────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/revenue-forecast")
async def get_revenue_forecast(
    store_id:      str,
    months_ahead:  int = Query(default=1),
    db:            AsyncSession = Depends(get_db),
    _:             User         = Depends(get_current_user),
):
    """基于历史季节性的未来月营收预测"""
    from datetime import timedelta

    today      = date_type.today()
    target_m   = (today.month + months_ahead - 1) % 12 + 1
    target_y   = today.year + (today.month + months_ahead - 1) // 12

    # 已确认订单（下限）
    t_start = date_type(target_y, target_m, 1)
    t_end_m = target_m + 1 if target_m < 12 else 1
    t_end_y = target_y  if target_m < 12 else target_y + 1
    t_end   = date_type(t_end_y, t_end_m, 1)

    confirmed_res = await db.execute(
        select(func.sum(BanquetOrder.total_amount_fen)).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.order_status == OrderStatusEnum.CONFIRMED,
            BanquetOrder.banquet_date >= t_start,
            BanquetOrder.banquet_date <  t_end,
        )
    )
    confirmed_fen = confirmed_res.scalar() or 0

    # 历史同月均值（过去2年）
    hist_totals = []
    for delta_y in range(1, 3):
        hy    = target_y - delta_y
        start = date_type(hy, target_m, 1)
        hend_m = target_m + 1 if target_m < 12 else 1
        hend_y = hy if target_m < 12 else hy + 1
        hend  = date_type(hend_y, hend_m, 1)
        hist_res = await db.execute(
            select(func.sum(BanquetOrder.total_amount_fen)).where(
                BanquetOrder.store_id == store_id,
                BanquetOrder.order_status.in_([OrderStatusEnum.CONFIRMED, OrderStatusEnum.COMPLETED]),
                BanquetOrder.banquet_date >= start,
                BanquetOrder.banquet_date <  hend,
            )
        )
        hist_totals.append(hist_res.scalar() or 0)

    base_fen     = int(sum(hist_totals) / len(hist_totals)) if hist_totals else 0
    forecast_fen = max(base_fen, confirmed_fen)

    return {
        "store_id":              store_id,
        "target_month":          f"{target_y:04d}-{target_m:02d}",
        "base_revenue_yuan":     round(base_fen     / 100, 2),
        "confirmed_revenue_yuan": round(confirmed_fen / 100, 2),
        "forecast_yuan":         round(forecast_fen  / 100, 2),
    }


# ════════════════════════════════════════════════════════════════════════════
# Phase 18 — 合同履约追踪 · 智能定价 · 评价闭环
# ════════════════════════════════════════════════════════════════════════════

# ── 1. 合同履约状态总览 ────────────────────────────────────────────────────

@router.get("/stores/{store_id}/contracts/compliance")
async def get_contract_compliance(
    store_id: str,
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """合同履约状态总览：未签 / 定金逾期 / 尾款逾期"""
    from datetime import timedelta

    today = date_type.today()
    warn_horizon = today + timedelta(days=30)  # 30天内宴会未签 → 警告

    orders_res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.order_status.in_([OrderStatusEnum.CONFIRMED, OrderStatusEnum.COMPLETED]),
        )
    )
    orders = orders_res.scalars().all()

    # 批量拉合同
    oids = [o.id for o in orders]
    contracts_by_oid: dict = {}
    if oids:
        ct_res = await db.execute(
            select(BanquetContract).where(BanquetContract.banquet_order_id.in_(oids))
        )
        for c in ct_res.scalars().all():
            contracts_by_oid[c.banquet_order_id] = c

    unsigned    = []
    deposit_due = []
    final_due   = []

    for o in orders:
        ct = contracts_by_oid.get(o.id)
        bt = o.banquet_type.value if hasattr(o.banquet_type, "value") else str(o.banquet_type)
        row = {
            "order_id":    str(o.id),
            "banquet_date": str(o.banquet_date),
            "banquet_type": bt,
            "contact_name": o.contact_name,
        }

        # 1) 未签合同：30天内宴会且合同不存在或未签
        if o.banquet_date <= warn_horizon:
            if ct is None or ct.contract_status != "signed":
                days_until = (o.banquet_date - today).days
                unsigned.append({**row, "days_until": days_until, "has_contract": ct is not None})

        # 2) 定金逾期：已确认但 deposit_status 仍 UNPAID 且距宴会 <= 14 天
        deposit_st = getattr(o, "deposit_status", None)
        ds_val = deposit_st.value if hasattr(deposit_st, "value") else str(deposit_st)
        total_fen = o.total_amount_fen or 0
        paid_fen  = o.paid_fen or 0
        deposit_fen = getattr(o, "deposit_fen", 0) or 0
        days_until = (o.banquet_date - today).days
        if ds_val == "unpaid" and 0 <= days_until <= 14:
            deposit_due.append({
                **row,
                "days_until":       days_until,
                "deposit_yuan":     round(deposit_fen / 100, 2),
                "contact_phone":    o.contact_phone,
            })

        # 3) 尾款逾期：宴会已过 且 paid_fen < total_amount_fen
        if o.banquet_date < today and paid_fen < total_fen:
            overdue_yuan = round((total_fen - paid_fen) / 100, 2)
            days_overdue = (today - o.banquet_date).days
            final_due.append({
                **row,
                "days_overdue":  days_overdue,
                "overdue_yuan":  overdue_yuan,
                "contact_phone": o.contact_phone,
            })

    unsigned.sort(key=lambda x: x["days_until"])
    deposit_due.sort(key=lambda x: x["days_until"])
    final_due.sort(key=lambda x: x["days_overdue"], reverse=True)

    return {
        "store_id":     store_id,
        "total_orders": len(orders),
        "unsigned": {
            "count": len(unsigned),
            "orders": unsigned[:20],
        },
        "deposit_due": {
            "count": len(deposit_due),
            "total_overdue_yuan": sum(r["deposit_yuan"] for r in deposit_due),
            "orders": deposit_due[:20],
        },
        "final_due": {
            "count": len(final_due),
            "total_overdue_yuan": sum(r["overdue_yuan"] for r in final_due),
            "orders": final_due[:20],
        },
    }


# ── 2. 逾期定金预警列表 ────────────────────────────────────────────────────

@router.get("/stores/{store_id}/contracts/overdue-deposits")
async def get_overdue_deposits(
    store_id:     str,
    days_overdue: int = Query(default=0),
    db:           AsyncSession = Depends(get_db),
    _:            User         = Depends(get_current_user),
):
    """定金逾期预警：deposit_status=unpaid 且 banquet_date 即将到来"""
    from datetime import timedelta

    today     = date_type.today()
    threshold = today + timedelta(days=max(0, 30 - days_overdue))

    orders_res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.order_status == OrderStatusEnum.CONFIRMED,
            BanquetOrder.deposit_status == DepositStatusEnum.UNPAID,
            BanquetOrder.banquet_date <= threshold,
        )
    )
    orders = orders_res.scalars().all()

    items = []
    for o in orders:
        deposit_fen = getattr(o, "deposit_fen", 0) or 0
        days_until = (o.banquet_date - today).days
        bt = o.banquet_type.value if hasattr(o.banquet_type, "value") else str(o.banquet_type)
        items.append({
            "order_id":          str(o.id),
            "banquet_date":      str(o.banquet_date),
            "banquet_type":      bt,
            "contact_name":      o.contact_name,
            "contact_phone":     o.contact_phone,
            "days_until":        days_until,
            "deposit_yuan":      round(deposit_fen / 100, 2),
        })

    items.sort(key=lambda x: x["days_until"])
    return {"store_id": store_id, "total": len(items), "items": items}


# ── 3. 智能定价建议 ────────────────────────────────────────────────────────

@router.post("/stores/{store_id}/orders/{order_id}/pricing-recommendation")
async def get_pricing_recommendation(
    store_id: str,
    order_id: str,
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """基于历史同类订单的分位数定价建议（纯规则，不调 LLM）"""
    from datetime import timedelta

    order_res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.id == order_id,
            BanquetOrder.store_id == store_id,
        )
    )
    order = order_res.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    banquet_date  = order.banquet_date
    banquet_type  = order.banquet_type
    table_count   = order.table_count or 1

    # 查历史同类确认/完成订单（近2年，±30天内日期）
    two_years_ago = banquet_date - timedelta(days=730)
    hist_res = await db.execute(
        select(BanquetOrder).where(
            BanquetOrder.store_id == store_id,
            BanquetOrder.banquet_type == banquet_type,
            BanquetOrder.order_status.in_([OrderStatusEnum.CONFIRMED, OrderStatusEnum.COMPLETED]),
            BanquetOrder.banquet_date >= two_years_ago,
            BanquetOrder.id != order_id,
            BanquetOrder.table_count > 0,
            BanquetOrder.total_amount_fen > 0,
        )
    )
    hist = hist_res.scalars().all()

    # 吉日加成（查 BanquetKpiDaily 的 is_auspicious 标记）
    auspicious_res = await db.execute(
        select(BanquetKpiDaily).where(
            BanquetKpiDaily.store_id == store_id,
            BanquetKpiDaily.stat_date == banquet_date,
        )
    )
    kpi_day = auspicious_res.scalars().first()
    # BanquetKpiDaily 没有 is_auspicious 字段，用月份判断粗代理（3/5/6/9/10 为旺季）
    peak_months = {3, 5, 6, 9, 10}
    is_peak = banquet_date.month in peak_months
    # 周末溢价
    is_weekend = banquet_date.weekday() >= 5

    premium_mult = 1.0
    if is_peak:    premium_mult += 0.03
    if is_weekend: premium_mult += 0.05

    bt_label = banquet_type.value if hasattr(banquet_type, "value") else str(banquet_type)

    if len(hist) < 5:
        # 样本不足 → 用 MenuPackage 理论定价
        pkg_res = await db.execute(
            select(MenuPackage).where(
                MenuPackage.store_id == store_id,
                MenuPackage.banquet_type == banquet_type,
                MenuPackage.is_active.is_(True),
            )
        )
        pkgs = pkg_res.scalars().all()
        if pkgs:
            avg_price = sum((p.suggested_price_fen or 0) for p in pkgs) / len(pkgs)
        else:
            avg_price = 80000  # 默认 800元/桌 × 100

        base_per_table = avg_price
        tiers = [
            {"tier": "economy",  "price_per_table_yuan": round(base_per_table * 0.85 / 100, 0), "total_yuan": round(base_per_table * 0.85 / 100 * table_count, 0), "conversion_rate_pct": None},
            {"tier": "standard", "price_per_table_yuan": round(base_per_table / 100, 0),          "total_yuan": round(base_per_table / 100 * table_count, 0),          "conversion_rate_pct": None},
            {"tier": "premium",  "price_per_table_yuan": round(base_per_table * 1.2 / 100, 0),  "total_yuan": round(base_per_table * 1.2 / 100 * table_count, 0),  "conversion_rate_pct": None},
        ]
        return {
            "order_id": order_id, "banquet_type": bt_label,
            "table_count": table_count, "banquet_date": str(banquet_date),
            "is_peak": is_peak, "is_weekend": is_weekend,
            "sample_count": len(hist),
            "tiers": tiers,
            "recommendation": "standard",
            "reason": f"历史样本不足（{len(hist)} 条），基于套餐定价估算",
        }

    # 计算每桌单价分位数
    prices_per_table = sorted((o.total_amount_fen / o.table_count) for o in hist if o.table_count > 0)
    n = len(prices_per_table)
    p25 = prices_per_table[max(0, int(n * 0.25) - 1)]
    p50 = prices_per_table[max(0, int(n * 0.50) - 1)]
    p75 = prices_per_table[max(0, int(n * 0.75) - 1)]

    p25 *= premium_mult
    p50 *= premium_mult
    p75 *= premium_mult

    def _conv_rate(threshold_fen: float) -> float:
        above = sum(1 for o in hist if (o.total_amount_fen / o.table_count) >= threshold_fen)
        return round(above / len(hist) * 100, 1)

    tiers = [
        {"tier": "economy",  "price_per_table_yuan": round(p25 / 100, 0), "total_yuan": round(p25 / 100 * table_count, 0), "conversion_rate_pct": _conv_rate(p25)},
        {"tier": "standard", "price_per_table_yuan": round(p50 / 100, 0), "total_yuan": round(p50 / 100 * table_count, 0), "conversion_rate_pct": _conv_rate(p50)},
        {"tier": "premium",  "price_per_table_yuan": round(p75 / 100, 0), "total_yuan": round(p75 / 100 * table_count, 0), "conversion_rate_pct": _conv_rate(p75)},
    ]

    recommendation = "standard"
    reason = f"基于 {len(hist)} 条历史同类订单"
    if is_peak:    reason += "，旺季月份（+3%）"
    if is_weekend: reason += "，周末（+5%）"

    return {
        "order_id": order_id, "banquet_type": bt_label,
        "table_count": table_count, "banquet_date": str(banquet_date),
        "is_peak": is_peak, "is_weekend": is_weekend,
        "sample_count": len(hist),
        "tiers": tiers,
        "recommendation": recommendation,
        "reason": reason,
    }


# ── 4. 价格段成交率分析 ────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/pricing-analysis")
async def get_pricing_analysis(
    store_id:     str,
    banquet_type: Optional[str] = Query(default=None),
    db:           AsyncSession  = Depends(get_db),
    _:            User          = Depends(get_current_user),
):
    """价格段（元/桌）成交率分析"""
    # 线索（预算）
    lead_q = select(BanquetLead).where(
        BanquetLead.store_id == store_id,
        BanquetLead.expected_budget_fen > 0,
    )
    if banquet_type:
        try:
            lead_q = lead_q.where(BanquetLead.banquet_type == BanquetTypeEnum(banquet_type))
        except ValueError:
            pass
    leads_res = await db.execute(lead_q)
    leads = leads_res.scalars().all()

    # 已转化订单
    order_q = select(BanquetOrder).where(
        BanquetOrder.store_id == store_id,
        BanquetOrder.order_status.in_([OrderStatusEnum.CONFIRMED, OrderStatusEnum.COMPLETED]),
        BanquetOrder.total_amount_fen > 0,
        BanquetOrder.table_count > 0,
    )
    if banquet_type:
        try:
            order_q = order_q.where(BanquetOrder.banquet_type == BanquetTypeEnum(banquet_type))
        except ValueError:
            pass
    orders_res = await db.execute(order_q)
    orders = orders_res.scalars().all()

    # 价格段：按线索预算/桌分桶（estimated_people / 10 as proxy tables）
    buckets = [
        {"range": "<500元/桌",    "min": 0,    "max": 50000},
        {"range": "500-800元/桌", "min": 50000, "max": 80000},
        {"range": "800-1200元/桌","min": 80000, "max": 120000},
        {"range": ">1200元/桌",   "min": 120000,"max": 9999999},
    ]

    # 以线索预算÷预计桌数（人数/10）作为每桌预算
    def _lead_per_table(lead) -> float:
        people = (lead.expected_people_count or 100)
        tables = max(people // 10, 1)
        return (lead.expected_budget_fen or 0) / tables

    def _order_per_table(order) -> float:
        return order.total_amount_fen / (order.table_count or 1)

    result = []
    for b in buckets:
        lc = sum(1 for l in leads  if b["min"] <= _lead_per_table(l)  < b["max"])
        oc = sum(1 for o in orders if b["min"] <= _order_per_table(o) < b["max"])
        rev = sum(o.total_amount_fen for o in orders if b["min"] <= _order_per_table(o) < b["max"])
        conv = round(oc / lc * 100, 1) if lc > 0 else None
        avg_rev = round(rev / oc / 100, 0) if oc > 0 else None
        result.append({
            "range":               b["range"],
            "lead_count":          lc,
            "order_count":         oc,
            "conversion_rate_pct": conv,
            "avg_revenue_yuan":    avg_rev,
        })

    return {"store_id": store_id, "buckets": result}


# ── 5. 评价汇总 ────────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/reviews/summary")
async def get_reviews_summary(
    store_id: str,
    months:   int = Query(default=3),
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """宴后评价汇总：均分、评分分布、月度趋势、类型分布"""
    from datetime import timedelta

    cutoff = date_type.today() - timedelta(days=months * 30)

    reviews_res = await db.execute(
        select(BanquetOrderReview, BanquetOrder.banquet_date, BanquetOrder.banquet_type)
        .join(BanquetOrder, BanquetOrderReview.banquet_order_id == BanquetOrder.id)
        .where(
            BanquetOrder.store_id == store_id,
            BanquetOrderReview.customer_rating.isnot(None),
            BanquetOrder.banquet_date >= cutoff,
        )
    )
    rows = reviews_res.all()

    if not rows:
        return {
            "store_id": store_id, "total": 0, "avg_score": None,
            "score_distribution": {str(i): 0 for i in range(1, 6)},
            "monthly_trend": [], "by_banquet_type": [],
        }

    dist: dict[str, int] = {str(i): 0 for i in range(1, 6)}
    monthly: dict[str, list] = {}
    by_type: dict[str, list] = {}

    for rev, bd, bt in rows:
        score = rev.customer_rating
        dist[str(score)] = dist.get(str(score), 0) + 1
        m_key = f"{bd.year:04d}-{bd.month:02d}"
        monthly.setdefault(m_key, []).append(score)
        bt_key = bt.value if hasattr(bt, "value") else str(bt)
        by_type.setdefault(bt_key, []).append(score)

    all_scores = [r[0].customer_rating for r in rows]
    avg = round(sum(all_scores) / len(all_scores), 2)

    trend = sorted([
        {"month": m, "avg_score": round(sum(v) / len(v), 2), "count": len(v)}
        for m, v in monthly.items()
    ], key=lambda x: x["month"])

    by_type_list = [
        {"banquet_type": t, "avg_score": round(sum(v) / len(v), 2), "count": len(v)}
        for t, v in by_type.items()
    ]

    return {
        "store_id":           store_id,
        "total":              len(rows),
        "avg_score":          avg,
        "score_distribution": dist,
        "monthly_trend":      trend,
        "by_banquet_type":    by_type_list,
    }


# ── 6. 低分预警 ────────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/reviews/low-score-alerts")
async def get_low_score_alerts(
    store_id:  str,
    threshold: int = Query(default=3),
    db:        AsyncSession = Depends(get_db),
    _:         User         = Depends(get_current_user),
):
    """低分评价预警列表（customer_rating <= threshold，近90天）"""
    from datetime import timedelta

    cutoff = date_type.today() - timedelta(days=90)

    res = await db.execute(
        select(BanquetOrderReview, BanquetOrder)
        .join(BanquetOrder, BanquetOrderReview.banquet_order_id == BanquetOrder.id)
        .where(
            BanquetOrder.store_id == store_id,
            BanquetOrderReview.customer_rating.isnot(None),
            BanquetOrderReview.customer_rating <= threshold,
            BanquetOrder.banquet_date >= cutoff,
        )
        .order_by(BanquetOrderReview.created_at.desc())
    )
    rows = res.all()

    items = []
    for rev, order in rows:
        bt = order.banquet_type.value if hasattr(order.banquet_type, "value") else str(order.banquet_type)
        items.append({
            "review_id":    str(rev.id),
            "order_id":     str(order.id),
            "score":        rev.customer_rating,
            "banquet_date": str(order.banquet_date),
            "banquet_type": bt,
            "contact_name": order.contact_name,
            "ai_summary":   rev.ai_summary,
            "tags":         rev.improvement_tags or [],
            "created_at":   rev.created_at.isoformat() if rev.created_at else None,
        })

    return {"store_id": store_id, "total": len(items), "threshold": threshold, "items": items}


# ── 7. 线索来源 ROI ────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/lead-source-roi")
async def get_lead_source_roi(
    store_id: str,
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """线索来源（source_channel）转化率与营收归因"""
    leads_res = await db.execute(
        select(BanquetLead).where(BanquetLead.store_id == store_id)
    )
    leads = leads_res.scalars().all()

    if not leads:
        return {"store_id": store_id, "sources": []}

    # 已转化线索 → 查对应订单金额
    converted = [l for l in leads if l.converted_order_id]
    conv_oids  = [l.converted_order_id for l in converted]
    orders_by_id: dict = {}
    if conv_oids:
        ord_res = await db.execute(
            select(BanquetOrder).where(BanquetOrder.id.in_(conv_oids))
        )
        for o in ord_res.scalars().all():
            orders_by_id[str(o.id)] = o

    # 按 source_channel 聚合（None → "其他"）
    by_source: dict = {}
    for lead in leads:
        src = lead.source_channel or "其他"
        if src not in by_source:
            by_source[src] = {"leads": [], "revenue_fen": 0, "converted": 0}
        by_source[src]["leads"].append(lead)

    for lead in converted:
        src = lead.source_channel or "其他"
        ord = orders_by_id.get(str(lead.converted_order_id))
        by_source[src]["converted"]   += 1
        by_source[src]["revenue_fen"] += (ord.total_amount_fen if ord else 0)

    sources = []
    for src, data in sorted(by_source.items(), key=lambda x: -x[1]["revenue_fen"]):
        lc  = len(data["leads"])
        conv = data["converted"]
        rev_fen = data["revenue_fen"]
        sources.append({
            "source":                src,
            "lead_count":            lc,
            "converted":             conv,
            "conversion_rate_pct":   round(conv / lc * 100, 1) if lc else 0.0,
            "revenue_yuan":          round(rev_fen / 100, 2),
            "revenue_per_lead_yuan": round(rev_fen / lc / 100, 2) if lc else 0.0,
        })

    return {"store_id": store_id, "sources": sources}


# ── 8. 厅房利用率预测 ────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/hall-utilization-forecast")
async def get_hall_utilization_forecast(
    store_id: str,
    days:     int = Query(default=30),
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """未来 N 天厅房利用率预测（每日）"""
    from datetime import timedelta

    today = date_type.today()
    end   = today + timedelta(days=days)

    # 查有效厅房数量（作为每日可用 slot 基准）
    halls_res = await db.execute(
        select(BanquetHall).where(
            BanquetHall.store_id == store_id,
            BanquetHall.is_active.is_(True),
        )
    )
    halls = halls_res.scalars().all()
    hall_count = max(len(halls), 1)
    slots_per_day = hall_count * 2  # 每个厅每天2个时段（午/晚）

    # 未来预订
    future_res = await db.execute(
        select(BanquetHallBooking).where(
            BanquetHallBooking.slot_date >= today,
            BanquetHallBooking.slot_date <= end,
            BanquetHallBooking.hall_id.in_([h.id for h in halls]),
        )
    )
    future_bookings = future_res.scalars().all()

    # 历史同期（去年同期 ±15天）
    last_year_start = today - timedelta(days=365 - 15)
    last_year_end   = end   - timedelta(days=365 - 15)
    hist_res = await db.execute(
        select(BanquetHallBooking).where(
            BanquetHallBooking.slot_date >= last_year_start,
            BanquetHallBooking.slot_date <= last_year_end,
            BanquetHallBooking.hall_id.in_([h.id for h in halls]),
        )
    )
    hist_bookings = hist_res.scalars().all()

    # 按日期分组
    future_by_date: dict[str, int] = {}
    for bk in future_bookings:
        k = str(bk.slot_date)
        future_by_date[k] = future_by_date.get(k, 0) + 1

    hist_by_offset: dict[int, int] = {}
    for bk in hist_bookings:
        # offset = days from today
        offset = (bk.slot_date - (today - timedelta(days=365 - 15))).days
        hist_by_offset[offset] = hist_by_offset.get(offset, 0) + 1

    daily = []
    for i in range(days):
        d = today + timedelta(days=i)
        d_str = str(d)
        booked   = future_by_date.get(d_str, 0)
        hist_bk  = hist_by_offset.get(i, 0)
        util_pct  = round(booked  / slots_per_day * 100, 1)
        hist_pct  = round(hist_bk / slots_per_day * 100, 1)
        status = "overbooked" if util_pct >= 100 else ("underbooked" if util_pct < 30 else "normal")
        daily.append({
            "date":           d_str,
            "booked":         booked,
            "capacity":       slots_per_day,
            "utilization_pct": util_pct,
            "hist_avg_pct":   hist_pct,
            "status":         status,
        })

    avg_util = round(sum(d["utilization_pct"] for d in daily) / days, 1) if daily else 0.0
    return {
        "store_id":   store_id,
        "halls":      hall_count,
        "days":       days,
        "daily":      daily,
        "summary": {
            "avg_utilization_pct": avg_util,
            "overbooked_days":     sum(1 for d in daily if d["status"] == "overbooked"),
            "underbooked_days":    sum(1 for d in daily if d["status"] == "underbooked"),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 19 — 宴后闭环 · 成本穿透 · 运营健康
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. 成本穿透分析 ─────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/cost-breakdown")
async def get_cost_breakdown(
    store_id: str,
    year:  int = 0,
    month: int = 0,
    db:    AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """按宴会类型拆解成本（原料/人工/其他）vs 毛利"""
    from datetime import timedelta
    from src.models.banquet import (
        BanquetProfitSnapshot, BanquetOrder, BanquetTypeEnum,
        OrderStatusEnum,
    )

    q = (
        select(
            BanquetOrder.banquet_type,
            func.sum(BanquetProfitSnapshot.revenue_fen).label("rev"),
            func.sum(BanquetProfitSnapshot.ingredient_cost_fen).label("ingredient"),
            func.sum(BanquetProfitSnapshot.labor_cost_fen).label("labor"),
            func.sum(BanquetProfitSnapshot.material_cost_fen).label("material"),
            func.sum(BanquetProfitSnapshot.other_cost_fen).label("other"),
            func.sum(BanquetProfitSnapshot.gross_profit_fen).label("profit"),
            func.count(BanquetOrder.id).label("cnt"),
        )
        .join(BanquetOrder, BanquetProfitSnapshot.banquet_order_id == BanquetOrder.id)
        .where(BanquetOrder.store_id == store_id)
        .where(BanquetOrder.order_status == OrderStatusEnum.COMPLETED)
        .group_by(BanquetOrder.banquet_type)
    )
    if year > 0:
        q = q.where(func.extract("year", BanquetOrder.banquet_date) == year)
    if month > 0:
        q = q.where(func.extract("month", BanquetOrder.banquet_date) == month)

    rows = (await db.execute(q)).all()

    result = []
    for r in rows:
        rev = r.rev or 0
        total_cost = (r.ingredient or 0) + (r.labor or 0) + (r.material or 0) + (r.other or 0)
        result.append({
            "banquet_type":        r.banquet_type.value if hasattr(r.banquet_type, "value") else str(r.banquet_type),
            "event_count":         r.cnt or 0,
            "revenue_yuan":        round((rev) / 100, 2),
            "ingredient_cost_yuan": round((r.ingredient or 0) / 100, 2),
            "labor_cost_yuan":     round((r.labor or 0) / 100, 2),
            "material_cost_yuan":  round((r.material or 0) / 100, 2),
            "other_cost_yuan":     round((r.other or 0) / 100, 2),
            "total_cost_yuan":     round(total_cost / 100, 2),
            "gross_profit_yuan":   round((r.profit or 0) / 100, 2),
            "gross_margin_pct":    round((r.profit or 0) / rev * 100, 1) if rev > 0 else None,
        })

    result.sort(key=lambda x: x["revenue_yuan"], reverse=True)
    return {
        "store_id":     store_id,
        "year":         year,
        "month":        month,
        "by_type":      result,
        "total_revenue_yuan":      round(sum(x["revenue_yuan"] for x in result), 2),
        "total_gross_profit_yuan": round(sum(x["gross_profit_yuan"] for x in result), 2),
    }


# ── 2. 单场宴后复盘 ──────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/orders/{order_id}/post-event-summary")
async def get_post_event_summary(
    store_id: str,
    order_id: str,
    db:       AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """单场宴会宴后复盘：计划 vs 实际、任务完成率、评价得分"""
    from src.models.banquet import (
        BanquetOrder, BanquetProfitSnapshot, BanquetOrderReview,
        ExecutionTask, TaskStatusEnum, OrderStatusEnum,
    )

    res = await db.execute(
        select(BanquetOrder)
        .where(BanquetOrder.id == order_id)
        .where(BanquetOrder.store_id == store_id)
    )
    order = res.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="order not found")

    # profit snapshot
    snap_res = await db.execute(
        select(BanquetProfitSnapshot)
        .where(BanquetProfitSnapshot.banquet_order_id == order_id)
    )
    snap = snap_res.scalars().first()

    # tasks
    task_res = await db.execute(
        select(ExecutionTask).where(ExecutionTask.banquet_order_id == order_id)
    )
    tasks = task_res.scalars().all()
    total_tasks = len(tasks)
    done_tasks  = sum(1 for t in tasks if t.task_status == TaskStatusEnum.DONE)

    # review
    rev_res = await db.execute(
        select(BanquetOrderReview)
        .where(BanquetOrderReview.banquet_order_id == order_id)
    )
    review = rev_res.scalars().first()

    total_fen  = order.total_amount_fen or 0
    paid_fen   = order.paid_fen or 0
    unpaid_fen = max(0, total_fen - paid_fen)

    return {
        "order_id":        order_id,
        "store_id":        store_id,
        "banquet_date":    str(order.banquet_date),
        "banquet_type":    order.banquet_type.value if hasattr(order.banquet_type, "value") else str(order.banquet_type),
        "order_status":    order.order_status.value if hasattr(order.order_status, "value") else str(order.order_status),
        "planned_tables":  order.table_count,
        "planned_people":  order.people_count,
        "financials": {
            "total_yuan":          round(total_fen / 100, 2),
            "paid_yuan":           round(paid_fen / 100, 2),
            "unpaid_yuan":         round(unpaid_fen / 100, 2),
            "revenue_yuan":        round((snap.revenue_fen or 0) / 100, 2) if snap else None,
            "gross_profit_yuan":   round((snap.gross_profit_fen or 0) / 100, 2) if snap else None,
            "gross_margin_pct":    snap.gross_margin_pct if snap else None,
            "ingredient_cost_yuan": round((snap.ingredient_cost_fen or 0) / 100, 2) if snap else None,
            "labor_cost_yuan":     round((snap.labor_cost_fen or 0) / 100, 2) if snap else None,
        },
        "tasks": {
            "total":       total_tasks,
            "done":        done_tasks,
            "completion_rate_pct": round(done_tasks / total_tasks * 100, 1) if total_tasks else None,
        },
        "review": {
            "customer_rating": review.customer_rating if review else None,
            "ai_score":        review.ai_score if review else None,
            "ai_summary":      review.ai_summary if review else None,
        } if review else None,
    }


# ── 3. 场次绩效排行 ─────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/event-performance-ranking")
async def get_event_performance_ranking(
    store_id:  str,
    sort_by:   str = "margin",    # margin | rating
    top_n:     int = 10,
    btype:     str = "",
    months:    int = 6,
    db:        AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """场次绩效排行：按毛利率或评分 Top-N"""
    from datetime import timedelta
    from src.models.banquet import (
        BanquetOrder, BanquetProfitSnapshot, BanquetOrderReview,
        BanquetTypeEnum, OrderStatusEnum,
    )

    cutoff = date_type.today() - timedelta(days=months * 30)
    q = (
        select(
            BanquetOrder,
            BanquetProfitSnapshot.gross_margin_pct,
            BanquetProfitSnapshot.gross_profit_fen,
            BanquetOrderReview.customer_rating,
        )
        .outerjoin(BanquetProfitSnapshot, BanquetProfitSnapshot.banquet_order_id == BanquetOrder.id)
        .outerjoin(BanquetOrderReview, BanquetOrderReview.banquet_order_id == BanquetOrder.id)
        .where(BanquetOrder.store_id == store_id)
        .where(BanquetOrder.order_status == OrderStatusEnum.COMPLETED)
        .where(BanquetOrder.banquet_date >= cutoff)
    )
    if btype:
        try:
            q = q.where(BanquetOrder.banquet_type == BanquetTypeEnum(btype))
        except ValueError:
            pass

    rows = (await db.execute(q)).all()

    events = []
    for order, margin_pct, profit_fen, rating in rows:
        events.append({
            "order_id":          order.id,
            "banquet_date":      str(order.banquet_date),
            "banquet_type":      order.banquet_type.value if hasattr(order.banquet_type, "value") else str(order.banquet_type),
            "contact_name":      order.contact_name,
            "total_yuan":        round((order.total_amount_fen or 0) / 100, 2),
            "gross_margin_pct":  margin_pct,
            "gross_profit_yuan": round((profit_fen or 0) / 100, 2),
            "customer_rating":   rating,
        })

    if sort_by == "rating":
        events.sort(key=lambda x: (x["customer_rating"] or 0), reverse=True)
    else:
        events.sort(key=lambda x: (x["gross_margin_pct"] or 0), reverse=True)

    return {
        "store_id": store_id,
        "sort_by":  sort_by,
        "months":   months,
        "total":    len(events),
        "ranking":  events[:top_n],
    }


# ── 4. 智能催款话术 ─────────────────────────────────────────────────────────

@router.post("/stores/{store_id}/collections/generate-message")
async def generate_collection_message(
    store_id:  str,
    order_id:  str = Body(..., embed=True),
    db:        AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """针对逾期尾款订单生成催款话术，写入 ActionLog"""
    from src.models.banquet import BanquetOrder, BanquetAgentActionLog, OrderStatusEnum

    res = await db.execute(
        select(BanquetOrder)
        .where(BanquetOrder.id == order_id)
        .where(BanquetOrder.store_id == store_id)
    )
    order = res.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="order not found")

    unpaid_fen = max(0, (order.total_amount_fen or 0) - (order.paid_fen or 0))
    unpaid_yuan = round(unpaid_fen / 100, 2)
    contact = order.contact_name or "尊敬的客户"
    banquet_date_str = str(order.banquet_date) if order.banquet_date else "贵宴"
    btype_label = {
        "wedding": "婚宴", "birthday": "寿宴", "full_moon": "满月宴",
        "corporate": "商务宴", "other": "宴会",
    }.get(order.banquet_type.value if hasattr(order.banquet_type, "value") else str(order.banquet_type), "宴会")

    message = (
        f"您好，{contact}！感谢您选择我们为您的{btype_label}服务（{banquet_date_str}）。"
        f"根据合同约定，您还有尾款 ¥{unpaid_yuan:,.2f} 待结清。"
        f"请于近日安排付款，如有疑问请随时联系我们，期待与您保持良好合作！"
    )

    log = BanquetAgentActionLog(
        id=str(__import__("uuid").uuid4()),
        agent_type="collection",
        related_object_type="banquet_order",
        related_object_id=order_id,
        action_type="collection_message",
        action_result="generated",
        suggestion_text=message,
        is_human_approved=False,
    )
    db.add(log)
    await db.commit()

    return {
        "order_id":    order_id,
        "contact":     contact,
        "unpaid_yuan": unpaid_yuan,
        "message":     message,
        "log_id":      log.id,
    }


# ── 5. 应收账款账龄分析 ─────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/payment-aging")
async def get_payment_aging(
    store_id: str,
    db:       AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """应收账款账龄分析：0-7 / 8-30 / 31-60 / 60+ 天四段"""
    from datetime import timedelta
    from src.models.banquet import BanquetOrder, OrderStatusEnum, DepositStatusEnum

    today = date_type.today()
    res = await db.execute(
        select(BanquetOrder)
        .where(BanquetOrder.store_id == store_id)
        .where(BanquetOrder.order_status.in_([OrderStatusEnum.CONFIRMED, OrderStatusEnum.COMPLETED]))
        .where(BanquetOrder.banquet_date < today)  # 已过日期
    )
    orders = res.scalars().all()

    buckets = {
        "0_7":   {"label": "0-7天",  "count": 0, "amount_yuan": 0.0},
        "8_30":  {"label": "8-30天", "count": 0, "amount_yuan": 0.0},
        "31_60": {"label": "31-60天","count": 0, "amount_yuan": 0.0},
        "60p":   {"label": "60天+",  "count": 0, "amount_yuan": 0.0},
    }

    total_overdue_yuan = 0.0
    for o in orders:
        unpaid_fen = max(0, (o.total_amount_fen or 0) - (o.paid_fen or 0))
        if unpaid_fen <= 0:
            continue
        days_past = (today - o.banquet_date).days
        unpaid_yuan = round(unpaid_fen / 100, 2)
        total_overdue_yuan += unpaid_yuan
        if days_past <= 7:
            b = "0_7"
        elif days_past <= 30:
            b = "8_30"
        elif days_past <= 60:
            b = "31_60"
        else:
            b = "60p"
        buckets[b]["count"]       += 1
        buckets[b]["amount_yuan"] += unpaid_yuan

    for bk in buckets.values():
        bk["amount_yuan"] = round(bk["amount_yuan"], 2)

    return {
        "store_id":           store_id,
        "total_overdue_yuan": round(total_overdue_yuan, 2),
        "buckets":            list(buckets.values()),
    }


# ── 6. 季度经营摘要 ─────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/reports/quarterly-summary")
async def get_quarterly_summary(
    store_id: str,
    year:     int = 0,
    quarter:  int = 0,  # 1-4
    db:       AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """季度经营摘要：KPI 一览"""
    from datetime import timedelta
    from src.models.banquet import (
        BanquetOrder, BanquetProfitSnapshot, BanquetOrderReview,
        BanquetContract, BanquetLead, OrderStatusEnum, LeadStageEnum,
    )

    today = date_type.today()
    if year <= 0:
        year = today.year
    if quarter <= 0:
        quarter = (today.month - 1) // 3 + 1

    q_start_month = (quarter - 1) * 3 + 1
    q_end_month   = q_start_month + 2

    from datetime import date as _date
    import calendar
    _, last_day = calendar.monthrange(year, q_end_month)
    period_start = _date(year, q_start_month, 1)
    period_end   = _date(year, q_end_month, last_day)

    # orders in quarter
    res = await db.execute(
        select(BanquetOrder)
        .where(BanquetOrder.store_id == store_id)
        .where(BanquetOrder.banquet_date >= period_start)
        .where(BanquetOrder.banquet_date <= period_end)
    )
    orders = res.scalars().all()
    order_ids = [o.id for o in orders]

    total_orders    = len(orders)
    confirmed_count = sum(1 for o in orders if o.order_status.value in ("confirmed", "completed") if hasattr(o.order_status, "value"))
    total_rev_fen   = sum(o.total_amount_fen or 0 for o in orders)
    total_paid_fen  = sum(o.paid_fen or 0 for o in orders)

    # snapshots for completed orders
    avg_margin = None
    if order_ids:
        snap_res = await db.execute(
            select(func.avg(BanquetProfitSnapshot.gross_margin_pct))
            .join(BanquetOrder, BanquetProfitSnapshot.banquet_order_id == BanquetOrder.id)
            .where(BanquetOrder.store_id == store_id)
            .where(BanquetOrder.banquet_date >= period_start)
            .where(BanquetOrder.banquet_date <= period_end)
        )
        avg_margin = snap_res.scalar()

    # reviews
    avg_rating = None
    if order_ids:
        rev_res = await db.execute(
            select(func.avg(BanquetOrderReview.customer_rating))
            .where(BanquetOrderReview.banquet_order_id.in_(order_ids))
        )
        avg_rating = rev_res.scalar()

    # unsigned contracts
    unsigned_count = 0
    if order_ids:
        ct_res = await db.execute(
            select(BanquetContract)
            .where(BanquetContract.banquet_order_id.in_(order_ids))
            .where(BanquetContract.contract_status != "signed")
        )
        unsigned_count = len(ct_res.scalars().all())

    # leads created in quarter (by created_at proxy: banquet_date in range from leads)
    lead_res = await db.execute(
        select(func.count(BanquetLead.id))
        .where(BanquetLead.store_id == store_id)
        .where(BanquetLead.expected_date >= period_start)
        .where(BanquetLead.expected_date <= period_end)
    )
    lead_count = lead_res.scalar() or 0

    return {
        "store_id":    store_id,
        "year":        year,
        "quarter":     quarter,
        "period":      {"start": str(period_start), "end": str(period_end)},
        "total_orders":          total_orders,
        "confirmed_orders":      confirmed_count,
        "total_revenue_yuan":    round(total_rev_fen / 100, 2),
        "total_paid_yuan":       round(total_paid_fen / 100, 2),
        "avg_gross_margin_pct":  round(avg_margin, 1) if avg_margin is not None else None,
        "avg_customer_rating":   round(avg_rating, 2) if avg_rating is not None else None,
        "unsigned_contracts":    unsigned_count,
        "lead_count":            lead_count,
    }


# ── 7. 运营健康评分 ─────────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/operations-health-score")
async def get_operations_health_score(
    store_id: str,
    months:   int = 3,
    db:       AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """运营健康评分（0-100）= 合同合规 20 + 收款及时 20 + 评价均分 20 + 利用率 20 + 转化率 20"""
    from datetime import timedelta
    from src.models.banquet import (
        BanquetOrder, BanquetContract, BanquetOrderReview,
        BanquetHallBooking, BanquetHall, BanquetLead,
        OrderStatusEnum, DepositStatusEnum, LeadStageEnum,
    )

    cutoff = date_type.today() - timedelta(days=months * 30)

    # ── Dim 1: 合同合规率 (有合同且已签 / 全部订单)
    ord_res = await db.execute(
        select(BanquetOrder)
        .where(BanquetOrder.store_id == store_id)
        .where(BanquetOrder.banquet_date >= cutoff)
        .where(BanquetOrder.order_status.in_([OrderStatusEnum.CONFIRMED, OrderStatusEnum.COMPLETED]))
    )
    orders = ord_res.scalars().all()
    total_ord = len(orders)
    order_ids = [o.id for o in orders]

    signed_ct = 0
    if order_ids:
        ct_res = await db.execute(
            select(func.count(BanquetContract.id))
            .where(BanquetContract.banquet_order_id.in_(order_ids))
            .where(BanquetContract.contract_status == "signed")
        )
        signed_ct = ct_res.scalar() or 0

    contract_score = round(signed_ct / total_ord * 20, 1) if total_ord > 0 else 0.0

    # ── Dim 2: 收款及时率 (已完成且全额收款 / 已完成)
    completed = [o for o in orders if o.order_status == OrderStatusEnum.COMPLETED]
    paid_full  = sum(1 for o in completed if (o.paid_fen or 0) >= (o.total_amount_fen or 1))
    payment_score = round(paid_full / len(completed) * 20, 1) if completed else 0.0

    # ── Dim 3: 评价均分 (avg_rating / 5 * 20)
    avg_rating = None
    if order_ids:
        rv_res = await db.execute(
            select(func.avg(BanquetOrderReview.customer_rating))
            .where(BanquetOrderReview.banquet_order_id.in_(order_ids))
        )
        avg_rating = rv_res.scalar()
    review_score = round((avg_rating or 0) / 5 * 20, 1)

    # ── Dim 4: 厅房利用率 (实际预订 / 理论总容量，上限100%)
    hall_res = await db.execute(
        select(BanquetHall).where(BanquetHall.store_id == store_id).where(BanquetHall.is_active == True)
    )
    halls = hall_res.scalars().all()
    hall_count = len(halls)
    slots_per_day = hall_count * 2  # lunch + dinner
    total_days = months * 30
    total_capacity = slots_per_day * total_days

    bk_res = await db.execute(
        select(func.count(BanquetHallBooking.id))
        .where(BanquetHallBooking.hall_id.in_([h.id for h in halls]))
        .where(BanquetHallBooking.slot_date >= cutoff)
    )
    booked_slots = bk_res.scalar() or 0
    util_ratio = min(booked_slots / total_capacity, 1.0) if total_capacity > 0 else 0.0
    util_score = round(util_ratio * 20, 1)

    # ── Dim 5: 线索转化率 (WON leads / total leads)
    lead_total_res = await db.execute(
        select(func.count(BanquetLead.id)).where(BanquetLead.store_id == store_id)
    )
    lead_total = lead_total_res.scalar() or 0
    lead_won_res = await db.execute(
        select(func.count(BanquetLead.id))
        .where(BanquetLead.store_id == store_id)
        .where(BanquetLead.current_stage == LeadStageEnum.WON)
    )
    lead_won = lead_won_res.scalar() or 0
    conv_rate = lead_won / lead_total if lead_total > 0 else 0.0
    # 目标 30% 转化率为满分
    conv_score = round(min(conv_rate / 0.30, 1.0) * 20, 1)

    total_score = round(contract_score + payment_score + review_score + util_score + conv_score, 1)

    return {
        "store_id":    store_id,
        "months":      months,
        "total_score": total_score,
        "grade":       "A" if total_score >= 80 else ("B" if total_score >= 60 else "C"),
        "dimensions": [
            {"name": "合同合规率", "score": contract_score, "max": 20,
             "detail": f"{signed_ct}/{total_ord} 已签"},
            {"name": "收款及时率", "score": payment_score, "max": 20,
             "detail": f"{paid_full}/{len(completed)} 已结清"},
            {"name": "客户评价",   "score": review_score,  "max": 20,
             "detail": f"均分 {round(avg_rating, 1) if avg_rating else 'N/A'}"},
            {"name": "厅房利用率", "score": util_score,    "max": 20,
             "detail": f"{round(util_ratio * 100, 1)}%"},
            {"name": "线索转化率", "score": conv_score,    "max": 20,
             "detail": f"{lead_won}/{lead_total}"},
        ],
    }


# ── 8. 月度基准折线数据 ──────────────────────────────────────────────────────

@router.get("/stores/{store_id}/analytics/monthly-benchmark")
async def get_monthly_benchmark(
    store_id: str,
    months:   int = 12,
    db:       AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """自身各月份连续数据（收入/毛利/场次），用于趋势折线图"""
    from datetime import timedelta
    from src.models.banquet import (
        BanquetOrder, BanquetProfitSnapshot, OrderStatusEnum,
    )

    cutoff = date_type.today().replace(day=1)
    # go back (months-1) full months
    for _ in range(months - 1):
        first = cutoff.replace(day=1)
        cutoff = (first - timedelta(days=1)).replace(day=1)

    q = (
        select(
            func.extract("year",  BanquetOrder.banquet_date).label("yr"),
            func.extract("month", BanquetOrder.banquet_date).label("mo"),
            func.count(BanquetOrder.id).label("cnt"),
            func.sum(BanquetOrder.total_amount_fen).label("rev_fen"),
            func.sum(BanquetProfitSnapshot.gross_profit_fen).label("profit_fen"),
        )
        .outerjoin(BanquetProfitSnapshot, BanquetProfitSnapshot.banquet_order_id == BanquetOrder.id)
        .where(BanquetOrder.store_id == store_id)
        .where(BanquetOrder.order_status.in_([OrderStatusEnum.CONFIRMED, OrderStatusEnum.COMPLETED]))
        .where(BanquetOrder.banquet_date >= cutoff)
        .group_by("yr", "mo")
        .order_by("yr", "mo")
    )
    rows = (await db.execute(q)).all()

    data = []
    for r in rows:
        data.append({
            "year":              int(r.yr),
            "month":             int(r.mo),
            "label":             f"{int(r.yr)}-{int(r.mo):02d}",
            "event_count":       r.cnt or 0,
            "revenue_yuan":      round((r.rev_fen or 0) / 100, 2),
            "gross_profit_yuan": round((r.profit_fen or 0) / 100, 2),
        })

    return {
        "store_id": store_id,
        "months":   months,
        "data":     data,
    }
