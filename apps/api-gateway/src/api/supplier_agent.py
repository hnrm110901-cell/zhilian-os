"""
供应商管理 Agent — Phase 11 核心路由
路由前缀：/api/v1/supplier-agent

模块：
  供应商档案 CRUD
  物料目录管理
  报价管理
  合同管理
  收货记录
  比价分析（PriceComparisonAgent）
  供应商评级（SupplierRatingAgent）
  自动寻源（AutoSourcingAgent）
  合同风险扫描（ContractRiskAgent）
  供应链风险扫描（SupplyChainRiskAgent）
  驾驶舱汇总
"""
import uuid
from datetime import datetime, date
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User
from src.models.supplier_agent import (
    SupplierProfile, MaterialCatalog,
    SupplierQuote, SupplierContract, SupplierDelivery,
    PriceComparison, SupplierEvaluation, SourcingRecommendation,
    ContractAlert, SupplyRiskEvent, SupplierAgentLog,
    SupplierTierEnum, QuoteStatusEnum, ContractStatusEnum,
    DeliveryStatusEnum, RiskLevelEnum, AlertTypeEnum, SupplierAgentTypeEnum,
)
import sys
from pathlib import Path as _Path


def _load_supplier_agents():
    repo_root = _Path(__file__).resolve().parents[4]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from packages.agents.supplier.src.agent import (
        PriceComparisonAgent, SupplierRatingAgent, AutoSourcingAgent,
        ContractRiskAgent, SupplyChainRiskAgent,
    )
    return PriceComparisonAgent, SupplierRatingAgent, AutoSourcingAgent, ContractRiskAgent, SupplyChainRiskAgent


_PriceComparisonAgent, _SupplierRatingAgent, _AutoSourcingAgent, \
    _ContractRiskAgent, _SupplyChainRiskAgent = _load_supplier_agents()

router = APIRouter(prefix="/api/v1/supplier-agent", tags=["supplier-agent"])

_price_agent     = _PriceComparisonAgent()
_rating_agent    = _SupplierRatingAgent()
_sourcing_agent  = _AutoSourcingAgent()
_contract_agent  = _ContractRiskAgent()
_risk_agent      = _SupplyChainRiskAgent()


# ──────────── Schemas ─────────────────────────────────────────────────────────

class SupplierProfileCreateReq(BaseModel):
    supplier_id:       str
    brand_id:          str
    tier:              str = "approved"
    category_tags:     list[str] = []
    region_coverage:   list[str] = []
    min_order_yuan:    float = 0
    internal_notes:    Optional[str] = None


class SupplierProfileUpdateReq(BaseModel):
    tier:              Optional[str] = None
    certified:         Optional[bool] = None
    cert_expiry:       Optional[str] = None
    category_tags:     Optional[list[str]] = None
    min_order_yuan:    Optional[float] = None
    risk_flags:        Optional[list[str]] = None
    internal_notes:    Optional[str] = None


class MaterialCatalogCreateReq(BaseModel):
    brand_id:          str
    material_code:     str
    material_name:     str
    spec:              Optional[str] = None
    base_unit:         str = "kg"
    category:          Optional[str] = None
    benchmark_price_yuan: float = 0
    safety_stock_days: int = 3
    reorder_point_kg:  float = 0


class QuoteCreateReq(BaseModel):
    brand_id:          str
    supplier_id:       str
    material_id:       Optional[str] = None
    material_name:     str
    spec:              Optional[str] = None
    unit:              str = "kg"
    quantity:          float
    unit_price_yuan:   float
    valid_until:       Optional[str] = None
    delivery_days:     int = 3
    min_order_qty:     float = 0
    notes:             Optional[str] = None
    store_id:          Optional[str] = None


class ContractCreateReq(BaseModel):
    brand_id:          str
    supplier_id:       str
    contract_no:       str
    contract_name:     Optional[str] = None
    start_date:        str
    end_date:          str
    auto_renew:        bool = False
    renewal_notice_days: int = 30
    annual_value_yuan: float = 0
    payment_terms:     str = "net30"
    delivery_guarantee: bool = False
    price_lock_months: int = 0
    penalty_clause:    bool = False
    covered_categories: list[str] = []


class DeliveryCreateReq(BaseModel):
    brand_id:          str
    store_id:          str
    supplier_id:       str
    purchase_order_id: Optional[str] = None
    promised_date:     str
    ordered_qty:       float
    received_qty:      float = 0
    rejected_qty:      float = 0
    reject_reason:     Optional[str] = None
    quality_score:     Optional[float] = None
    freshness_ok:      Optional[bool] = None
    notes:             Optional[str] = None


class PriceCompareReq(BaseModel):
    brand_id:    str
    material_id: str
    required_qty: float
    store_id:    Optional[str] = None


class RatingReq(BaseModel):
    brand_id:       str
    supplier_id:    str
    eval_period:    str          # "2026-03"
    service_score:  Optional[float] = None


class SourcingReq(BaseModel):
    brand_id:       str
    material_id:    str
    required_qty:   float
    needed_by_date: str          # "2026-03-20"
    store_id:       Optional[str] = None
    trigger:        str = "manual"


class AlertResolveReq(BaseModel):
    resolved_by: str
    note:        Optional[str] = None


# ──────────── 供应商档案 ──────────────────────────────────────────────────────

@router.post("/profiles", summary="创建供应商档案")
async def create_profile(
    req: SupplierProfileCreateReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = SupplierProfile(
        id=str(uuid.uuid4()),
        supplier_id=req.supplier_id,
        brand_id=req.brand_id,
        tier=SupplierTierEnum(req.tier),
        category_tags=req.category_tags,
        region_coverage=req.region_coverage,
        min_order_yuan=Decimal(str(req.min_order_yuan)),
        internal_notes=req.internal_notes,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return {"id": profile.id, "supplier_id": profile.supplier_id, "tier": profile.tier}


@router.get("/profiles", summary="查询供应商档案列表")
async def list_profiles(
    brand_id: str = Query(...),
    tier: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(SupplierProfile).where(SupplierProfile.brand_id == brand_id)
    if tier:
        q = q.where(SupplierProfile.tier == SupplierTierEnum(tier))
    q = q.order_by(desc(SupplierProfile.composite_score))
    result = await db.execute(q)
    profiles = result.scalars().all()
    return {
        "items": [
            {
                "id": p.id,
                "supplier_id": p.supplier_id,
                "tier": p.tier,
                "composite_score": p.composite_score,
                "price_score": p.price_score,
                "quality_score": p.quality_score,
                "delivery_score": p.delivery_score,
                "service_score": p.service_score,
                "risk_flags": p.risk_flags,
                "last_rated_at": str(p.last_rated_at) if p.last_rated_at else None,
            }
            for p in profiles
        ],
        "total": len(profiles),
    }


@router.patch("/profiles/{profile_id}", summary="更新供应商档案")
async def update_profile(
    profile_id: str,
    req: SupplierProfileUpdateReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(SupplierProfile).where(SupplierProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="供应商档案不存在")
    if req.tier is not None:
        profile.tier = SupplierTierEnum(req.tier)
    if req.certified is not None:
        profile.certified = req.certified
    if req.category_tags is not None:
        profile.category_tags = req.category_tags
    if req.min_order_yuan is not None:
        profile.min_order_yuan = Decimal(str(req.min_order_yuan))
    if req.risk_flags is not None:
        profile.risk_flags = req.risk_flags
    if req.internal_notes is not None:
        profile.internal_notes = req.internal_notes
    await db.commit()
    return {"id": profile_id, "updated": True}


# ──────────── 物料目录 ────────────────────────────────────────────────────────

@router.post("/materials", summary="创建物料目录")
async def create_material(
    req: MaterialCatalogCreateReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    material = MaterialCatalog(
        id=str(uuid.uuid4()),
        brand_id=req.brand_id,
        material_code=req.material_code,
        material_name=req.material_name,
        spec=req.spec,
        base_unit=req.base_unit,
        category=req.category,
        benchmark_price_yuan=Decimal(str(req.benchmark_price_yuan)),
        latest_price_yuan=Decimal(str(req.benchmark_price_yuan)),
        safety_stock_days=req.safety_stock_days,
        reorder_point_kg=req.reorder_point_kg,
        is_active=True,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)
    return {"id": material.id, "material_name": material.material_name}


@router.get("/materials", summary="查询物料目录")
async def list_materials(
    brand_id: str = Query(...),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(MaterialCatalog).where(
        and_(MaterialCatalog.brand_id == brand_id, MaterialCatalog.is_active == True)
    )
    if category:
        q = q.where(MaterialCatalog.category == category)
    result = await db.execute(q.order_by(MaterialCatalog.category, MaterialCatalog.material_name))
    materials = result.scalars().all()
    return {
        "items": [
            {
                "id": m.id,
                "material_code": m.material_code,
                "material_name": m.material_name,
                "category": m.category,
                "base_unit": m.base_unit,
                "benchmark_price_yuan": float(m.benchmark_price_yuan or 0),
                "latest_price_yuan": float(m.latest_price_yuan or 0),
                "preferred_supplier_id": m.preferred_supplier_id,
                "safety_stock_days": m.safety_stock_days,
            }
            for m in materials
        ],
        "total": len(materials),
    }


# ──────────── 报价管理 ────────────────────────────────────────────────────────

@router.post("/quotes", summary="提交供应商报价")
async def create_quote(
    req: QuoteCreateReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    valid_until = date.fromisoformat(req.valid_until) if req.valid_until else None
    total = round(req.unit_price_yuan * req.quantity, 2)
    quote = SupplierQuote(
        id=str(uuid.uuid4()),
        brand_id=req.brand_id,
        store_id=req.store_id,
        supplier_id=req.supplier_id,
        material_id=req.material_id,
        material_name=req.material_name,
        spec=req.spec,
        unit=req.unit,
        quantity=req.quantity,
        unit_price_yuan=Decimal(str(req.unit_price_yuan)),
        total_yuan=Decimal(str(total)),
        valid_until=valid_until,
        status=QuoteStatusEnum.SUBMITTED,
        delivery_days=req.delivery_days,
        min_order_qty=req.min_order_qty,
        notes=req.notes,
    )
    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    return {"id": quote.id, "total_yuan": total, "status": QuoteStatusEnum.SUBMITTED}


@router.get("/quotes", summary="查询报价列表")
async def list_quotes(
    brand_id: str = Query(...),
    material_id: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(SupplierQuote).where(SupplierQuote.brand_id == brand_id)
    if material_id:
        q = q.where(SupplierQuote.material_id == material_id)
    if supplier_id:
        q = q.where(SupplierQuote.supplier_id == supplier_id)
    q = q.order_by(desc(SupplierQuote.created_at))
    result = await db.execute(q.limit(100))
    quotes = result.scalars().all()
    return {
        "items": [
            {
                "id": qt.id,
                "supplier_id": qt.supplier_id,
                "material_name": qt.material_name,
                "unit_price_yuan": float(qt.unit_price_yuan),
                "quantity": qt.quantity,
                "total_yuan": float(qt.total_yuan or 0),
                "valid_until": str(qt.valid_until) if qt.valid_until else None,
                "delivery_days": qt.delivery_days,
                "status": qt.status,
                "rank_in_comparison": qt.rank_in_comparison,
            }
            for qt in quotes
        ],
        "total": len(quotes),
    }


# ──────────── 合同管理 ────────────────────────────────────────────────────────

@router.post("/contracts", summary="创建供应商合同")
async def create_contract(
    req: ContractCreateReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = SupplierContract(
        id=str(uuid.uuid4()),
        brand_id=req.brand_id,
        supplier_id=req.supplier_id,
        contract_no=req.contract_no,
        contract_name=req.contract_name,
        start_date=date.fromisoformat(req.start_date),
        end_date=date.fromisoformat(req.end_date),
        auto_renew=req.auto_renew,
        renewal_notice_days=req.renewal_notice_days,
        status=ContractStatusEnum.DRAFT,
        annual_value_yuan=Decimal(str(req.annual_value_yuan)),
        payment_terms=req.payment_terms,
        delivery_guarantee=req.delivery_guarantee,
        price_lock_months=req.price_lock_months,
        penalty_clause=req.penalty_clause,
        covered_categories=req.covered_categories,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return {"id": contract.id, "contract_no": contract.contract_no, "status": ContractStatusEnum.DRAFT}


@router.get("/contracts", summary="查询合同列表")
async def list_contracts(
    brand_id: str = Query(...),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(SupplierContract).where(SupplierContract.brand_id == brand_id)
    if status:
        q = q.where(SupplierContract.status == ContractStatusEnum(status))
    q = q.order_by(SupplierContract.end_date)
    result = await db.execute(q)
    contracts = result.scalars().all()
    today = date.today()
    return {
        "items": [
            {
                "id": c.id,
                "contract_no": c.contract_no,
                "contract_name": c.contract_name,
                "supplier_id": c.supplier_id,
                "start_date": str(c.start_date),
                "end_date": str(c.end_date),
                "days_to_expiry": (c.end_date - today).days,
                "status": c.status,
                "annual_value_yuan": float(c.annual_value_yuan or 0),
                "auto_renew": c.auto_renew,
            }
            for c in contracts
        ],
        "total": len(contracts),
    }


@router.patch("/contracts/{contract_id}/activate", summary="激活合同")
async def activate_contract(
    contract_id: str,
    signed_by: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(SupplierContract).where(SupplierContract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    contract.status = ContractStatusEnum.ACTIVE
    contract.signed_by = signed_by
    contract.signed_at = datetime.utcnow()
    await db.commit()
    return {"id": contract_id, "status": ContractStatusEnum.ACTIVE}


# ──────────── 收货记录 ────────────────────────────────────────────────────────

@router.post("/deliveries", summary="记录收货")
async def create_delivery(
    req: DeliveryCreateReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    promised_date = date.fromisoformat(req.promised_date)
    actual_date = date.today()
    delay_days = (actual_date - promised_date).days

    status = DeliveryStatusEnum.DELIVERED
    if req.rejected_qty > 0 and req.rejected_qty >= req.ordered_qty:
        status = DeliveryStatusEnum.REJECTED
    elif req.received_qty < req.ordered_qty:
        status = DeliveryStatusEnum.PARTIAL

    delivery = SupplierDelivery(
        id=str(uuid.uuid4()),
        brand_id=req.brand_id,
        store_id=req.store_id,
        supplier_id=req.supplier_id,
        purchase_order_id=req.purchase_order_id,
        promised_date=promised_date,
        actual_date=actual_date,
        delay_days=delay_days,
        status=status,
        ordered_qty=req.ordered_qty,
        received_qty=req.received_qty,
        rejected_qty=req.rejected_qty,
        reject_reason=req.reject_reason,
        quality_score=req.quality_score,
        freshness_ok=req.freshness_ok,
        notes=req.notes,
        inspector_id=str(current_user.id) if hasattr(current_user, "id") else None,
    )
    db.add(delivery)
    await db.commit()
    await db.refresh(delivery)
    return {
        "id": delivery.id,
        "status": status,
        "delay_days": delay_days,
        "reject_rate": round(req.rejected_qty / max(req.ordered_qty, 1), 4),
    }


# ──────────── Agent 接口 ──────────────────────────────────────────────────────

@router.post("/agents/price-compare", summary="[Agent] 多供应商比价")
async def agent_price_compare(
    req: PriceCompareReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """比价引擎：汇总多供应商报价，推荐最优采购方案（含¥节省估算）"""
    result = await _price_agent.compare(
        brand_id=req.brand_id,
        material_id=req.material_id,
        required_qty=req.required_qty,
        db=db,
        store_id=req.store_id,
        save=True,
    )
    return result


@router.post("/agents/rate-supplier", summary="[Agent] 供应商综合评级")
async def agent_rate_supplier(
    req: RatingReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """供应商评级：四维度综合评分，生成分级建议"""
    result = await _rating_agent.evaluate(
        brand_id=req.brand_id,
        supplier_id=req.supplier_id,
        eval_period=req.eval_period,
        db=db,
        service_score=req.service_score,
        save=True,
    )
    return result


@router.post("/agents/auto-source", summary="[Agent] 自动寻源")
async def agent_auto_source(
    req: SourcingReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """自动寻源：BOM驱动匹配最优供应商，生成采购建议"""
    needed_by = date.fromisoformat(req.needed_by_date)
    result = await _sourcing_agent.source(
        brand_id=req.brand_id,
        material_id=req.material_id,
        required_qty=req.required_qty,
        needed_by_date=needed_by,
        db=db,
        store_id=req.store_id,
        trigger=req.trigger,
        save=True,
    )
    return result


@router.post("/agents/scan-contract-risk", summary="[Agent] 合同风险扫描")
async def agent_scan_contract_risk(
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """扫描即将到期合同，生成三级预警"""
    result = await _contract_agent.scan(brand_id=brand_id, db=db, save=True)
    return result


@router.post("/agents/scan-supply-risk", summary="[Agent] 供应链风险扫描")
async def agent_scan_supply_risk(
    brand_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """扫描供应链风险（单一来源/连续延误/价格波动）"""
    result = await _risk_agent.scan(brand_id=brand_id, db=db, store_id=store_id, save=True)
    return result


# ──────────── 预警管理 ────────────────────────────────────────────────────────

@router.get("/alerts", summary="查询供应商预警列表")
async def list_alerts(
    brand_id: str = Query(...),
    is_resolved: bool = Query(False),
    risk_level: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 合同预警
    cq = select(ContractAlert).where(
        and_(ContractAlert.brand_id == brand_id, ContractAlert.is_resolved == is_resolved)
    )
    if risk_level:
        cq = cq.where(ContractAlert.risk_level == RiskLevelEnum(risk_level))
    c_result = await db.execute(cq.order_by(desc(ContractAlert.created_at)).limit(50))
    contract_alerts = c_result.scalars().all()

    # 供应链风险
    rq = select(SupplyRiskEvent).where(
        and_(SupplyRiskEvent.brand_id == brand_id, SupplyRiskEvent.is_resolved == is_resolved)
    )
    if risk_level:
        rq = rq.where(SupplyRiskEvent.risk_level == RiskLevelEnum(risk_level))
    r_result = await db.execute(rq.order_by(desc(SupplyRiskEvent.created_at)).limit(50))
    supply_risks = r_result.scalars().all()

    return {
        "contract_alerts": [
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "risk_level": a.risk_level,
                "title": a.title,
                "days_to_expiry": a.days_to_expiry,
                "financial_impact_yuan": float(a.financial_impact_yuan or 0),
                "recommended_action": a.recommended_action,
                "created_at": str(a.created_at),
            }
            for a in contract_alerts
        ],
        "supply_risks": [
            {
                "id": r.id,
                "alert_type": r.alert_type,
                "risk_level": r.risk_level,
                "title": r.title,
                "probability": r.probability,
                "financial_impact_yuan": float(r.financial_impact_yuan or 0),
                "mitigation_plan": r.mitigation_plan,
                "created_at": str(r.created_at),
            }
            for r in supply_risks
        ],
        "total_unresolved": len(contract_alerts) + len(supply_risks),
    }


@router.patch("/alerts/contract/{alert_id}/resolve", summary="标记合同预警已处理")
async def resolve_contract_alert(
    alert_id: str,
    req: AlertResolveReq,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ContractAlert).where(ContractAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="预警不存在")
    alert.is_resolved = True
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by = req.resolved_by
    await db.commit()
    return {"id": alert_id, "resolved": True}


# ──────────── 寻源推荐管理 ───────────────────────────────────────────────────

@router.get("/sourcing-recommendations", summary="查询寻源推荐列表")
async def list_sourcing_recommendations(
    brand_id: str = Query(...),
    status: str = Query("pending"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(SourcingRecommendation).where(
        and_(SourcingRecommendation.brand_id == brand_id,
             SourcingRecommendation.status == status)
    ).order_by(desc(SourcingRecommendation.created_at)).limit(50)
    result = await db.execute(q)
    recs = result.scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "material_name": r.material_name,
                "required_qty": r.required_qty,
                "needed_by_date": str(r.needed_by_date) if r.needed_by_date else None,
                "recommended_supplier_id": r.recommended_supplier_id,
                "recommended_price_yuan": float(r.recommended_price_yuan or 0),
                "estimated_total_yuan": float(r.estimated_total_yuan or 0),
                "estimated_saving_yuan": float(r.estimated_saving_yuan or 0),
                "sourcing_strategy": r.sourcing_strategy,
                "confidence": r.confidence,
                "status": r.status,
            }
            for r in recs
        ],
        "total": len(recs),
    }


@router.patch("/sourcing-recommendations/{rec_id}/accept", summary="接受寻源推荐")
async def accept_sourcing_recommendation(
    rec_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(SourcingRecommendation).where(SourcingRecommendation.id == rec_id))
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="寻源推荐不存在")
    rec.status = "accepted"
    rec.accepted_by = str(current_user.id) if hasattr(current_user, "id") else "unknown"
    rec.accepted_at = datetime.utcnow()
    await db.commit()
    return {"id": rec_id, "status": "accepted"}


# ──────────── 驾驶舱 ─────────────────────────────────────────────────────────

@router.get("/dashboard", summary="供应商管理驾驶舱")
async def get_dashboard(
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """供应商管理综合看板：供应商分级、活跃合同、待处理预警、寻源推荐汇总"""
    today = date.today()

    # 供应商分级分布
    tier_result = await db.execute(
        select(SupplierProfile.tier, func.count(SupplierProfile.id))
        .where(SupplierProfile.brand_id == brand_id)
        .group_by(SupplierProfile.tier)
    )
    tier_dist = {row[0]: row[1] for row in tier_result.fetchall()}

    # 活跃合同数 & 即将到期（30天内）
    contract_result = await db.execute(
        select(func.count(SupplierContract.id)).where(
            and_(SupplierContract.brand_id == brand_id,
                 SupplierContract.status == ContractStatusEnum.ACTIVE)
        )
    )
    active_contracts = contract_result.scalar() or 0

    expiring_result = await db.execute(
        select(func.count(SupplierContract.id)).where(
            and_(SupplierContract.brand_id == brand_id,
                 SupplierContract.status.in_([ContractStatusEnum.ACTIVE, ContractStatusEnum.EXPIRING]),
                 SupplierContract.end_date <= today.replace(day=today.day + 30)
                 if today.day <= 1 else SupplierContract.end_date <= date(today.year, today.month, today.day + 30)
                 if today.day + 30 <= 28 else SupplierContract.end_date >= today)
        )
    )

    # 未处理预警数
    unresolved_contract_result = await db.execute(
        select(func.count(ContractAlert.id)).where(
            and_(ContractAlert.brand_id == brand_id, ContractAlert.is_resolved == False)
        )
    )
    unresolved_supply_result = await db.execute(
        select(func.count(SupplyRiskEvent.id)).where(
            and_(SupplyRiskEvent.brand_id == brand_id, SupplyRiskEvent.is_resolved == False)
        )
    )

    # 待处理寻源推荐
    pending_sourcing_result = await db.execute(
        select(func.count(SourcingRecommendation.id)).where(
            and_(SourcingRecommendation.brand_id == brand_id,
                 SourcingRecommendation.status == "pending")
        )
    )

    # 本月累计节省¥
    saving_result = await db.execute(
        select(func.sum(PriceComparison.estimated_saving_yuan)).where(
            and_(PriceComparison.brand_id == brand_id,
                 PriceComparison.comparison_date >= date(today.year, today.month, 1))
        )
    )
    monthly_saving = float(saving_result.scalar() or 0)

    return {
        "supplier_tier_distribution": {
            "strategic": tier_dist.get(SupplierTierEnum.STRATEGIC, 0),
            "preferred": tier_dist.get(SupplierTierEnum.PREFERRED, 0),
            "approved": tier_dist.get(SupplierTierEnum.APPROVED, 0),
            "probation": tier_dist.get(SupplierTierEnum.PROBATION, 0),
        },
        "active_contracts": active_contracts,
        "unresolved_alerts": (unresolved_contract_result.scalar() or 0) + (unresolved_supply_result.scalar() or 0),
        "pending_sourcing_recommendations": pending_sourcing_result.scalar() or 0,
        "monthly_estimated_saving_yuan": monthly_saving,
        "data_as_of": str(today),
    }
