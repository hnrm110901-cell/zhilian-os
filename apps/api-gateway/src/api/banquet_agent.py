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
    MenuPackage, ExecutionTask, ExecutionTemplate, ExecutionException, BanquetPaymentRecord,
    BanquetHallBooking, BanquetKpiDaily, BanquetQuote,
    BanquetContract, BanquetProfitSnapshot, LeadFollowupRecord,
    LeadStageEnum, OrderStatusEnum, BanquetTypeEnum,
    BanquetHallType, PaymentTypeEnum, DepositStatusEnum,
    TaskStatusEnum, TaskOwnerRoleEnum, BanquetAgentActionLog, BanquetRevenueTarget,
    BanquetOrderReview,
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
