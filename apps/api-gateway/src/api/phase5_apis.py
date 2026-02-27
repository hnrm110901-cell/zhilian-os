"""
Phase 5 API Endpoints
生态扩展期API端点

Consolidated API endpoints for:
- Open API Platform
- Industry Solutions
- Supply Chain Integration
- Internationalization
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from src.services.open_api_platform import (
    OpenAPIPlatform,
    DeveloperTier,
    PluginCategory,
    PluginStatus
)
from src.services.industry_solutions import (
    IndustrySolutionsService,
    IndustryType,
    TemplateType
)
from src.services.supply_chain_integration import (
    SupplyChainIntegration,
)
from src.services.internationalization import (
    InternationalizationService,
    Language,
    Currency
)
from src.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession


# ==================== Open API Platform ====================
platform_router = APIRouter(prefix="/api/v1/platform", tags=["open_platform"])


class DeveloperTierEnum(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class PluginCategoryEnum(str, Enum):
    ANALYTICS = "analytics"
    MARKETING = "marketing"
    OPERATIONS = "operations"
    FINANCE = "finance"
    INTEGRATION = "integration"
    AI = "ai"


class RegisterDeveloperRequest(BaseModel):
    name: str
    email: str
    company: Optional[str] = None
    tier: DeveloperTierEnum = DeveloperTierEnum.FREE


class SubmitPluginRequest(BaseModel):
    developer_id: str
    name: str
    description: str
    category: PluginCategoryEnum
    version: str
    price: float
    webhook_url: Optional[str] = None


@platform_router.post("/developer/register")
async def register_developer(
    request: RegisterDeveloperRequest,
    db: AsyncSession = Depends(get_db)
):
    """Register new developer"""
    try:
        platform = OpenAPIPlatform(db)
        developer = platform.register_developer(
            name=request.name,
            email=request.email,
            company=request.company,
            tier=DeveloperTier(request.tier.value)
        )

        return {
            "success": True,
            "developer_id": developer.developer_id,
            "api_key": developer.api_key,
            "api_secret": developer.api_secret,
            "rate_limit": developer.rate_limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@platform_router.post("/plugin/submit")
async def submit_plugin(
    request: SubmitPluginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Submit plugin for review"""
    try:
        platform = OpenAPIPlatform(db)
        plugin = platform.submit_plugin(
            developer_id=request.developer_id,
            name=request.name,
            description=request.description,
            category=PluginCategory(request.category.value),
            version=request.version,
            price=request.price,
            webhook_url=request.webhook_url
        )

        return {
            "success": True,
            "plugin_id": plugin.plugin_id,
            "status": plugin.status.value,
            "revenue_share": plugin.revenue_share
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@platform_router.get("/marketplace")
async def get_marketplace_plugins(
    category: Optional[PluginCategoryEnum] = None,
    sort_by: str = "installs",
    db: AsyncSession = Depends(get_db)
):
    """Get marketplace plugins"""
    try:
        platform = OpenAPIPlatform(db)
        cat = PluginCategory(category.value) if category else None
        plugins = platform.get_marketplace_plugins(category=cat, sort_by=sort_by)

        return {
            "success": True,
            "total": len(plugins),
            "plugins": [
                {
                    "plugin_id": p.plugin_id,
                    "name": p.name,
                    "description": p.description,
                    "category": p.category.value,
                    "price": p.price,
                    "installs": p.installs,
                    "rating": p.rating
                }
                for p in plugins
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Industry Solutions ====================
industry_router = APIRouter(prefix="/api/v1/industry", tags=["industry_solutions"])


class IndustryTypeEnum(str, Enum):
    HOTPOT = "hotpot"
    BBQ = "bbq"
    FAST_FOOD = "fast_food"
    FINE_DINING = "fine_dining"
    CAFE = "cafe"
    BAKERY = "bakery"
    TEA_SHOP = "tea_shop"
    NOODLES = "noodles"


@industry_router.get("/solution/{industry_type}")
async def get_industry_solution(
    industry_type: IndustryTypeEnum,
    db: AsyncSession = Depends(get_db)
):
    """Get industry solution"""
    try:
        service = IndustrySolutionsService(db)
        solution = service.get_solution(IndustryType(industry_type.value))

        if not solution:
            raise HTTPException(status_code=404, detail="Solution not found")

        return {
            "success": True,
            "solution": {
                "solution_id": solution.solution_id,
                "industry_type": solution.industry_type.value,
                "name": solution.name,
                "description": solution.description,
                "templates_count": len(solution.templates),
                "best_practices_count": len(solution.best_practices),
                "kpi_benchmarks": solution.kpi_benchmarks
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@industry_router.post("/apply")
async def apply_industry_solution(
    store_id: str,
    industry_type: IndustryTypeEnum,
    db: AsyncSession = Depends(get_db)
):
    """Apply industry solution to store"""
    try:
        service = IndustrySolutionsService(db)
        result = service.apply_solution(
            store_id=store_id,
            industry_type=IndustryType(industry_type.value)
        )

        return {
            "success": True,
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Supply Chain ====================
supply_chain_router = APIRouter(prefix="/api/v1/supply-chain", tags=["supply_chain"])


class RequestQuotesRequest(BaseModel):
    material_id: str
    quantity: float
    required_date: datetime
    supplier_ids: Optional[List[str]] = None


class CompareQuotesRequest(BaseModel):
    quotes: List[dict]


class RegisterSupplierRequest(BaseModel):
    name: str
    category: str = "food"
    contact_person: str = ""
    phone: str = ""
    email: Optional[str] = None
    address: Optional[str] = None
    payment_terms: str = "net30"
    delivery_time: int = 3
    notes: Optional[str] = None


class CreateOrderRequest(BaseModel):
    store_id: str
    supplier_id: str
    items: List[dict]
    expected_delivery: datetime
    created_by: Optional[str] = None
    notes: Optional[str] = None


class UpdateOrderStatusRequest(BaseModel):
    status: str


@supply_chain_router.get("/suppliers")
async def list_suppliers(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """获取供应商列表"""
    try:
        service = SupplyChainIntegration(db)
        suppliers = await service.get_suppliers(category=category)
        return {
            "success": True,
            "suppliers": [
                {
                    "id": s.id, "name": s.name, "code": s.code,
                    "category": s.category, "contact_person": s.contact_person,
                    "phone": s.phone, "rating": s.rating,
                    "payment_terms": s.payment_terms, "delivery_time": s.delivery_time,
                    "status": s.status,
                }
                for s in suppliers
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@supply_chain_router.post("/suppliers")
async def register_supplier(
    request: RegisterSupplierRequest,
    db: AsyncSession = Depends(get_db)
):
    """注册供应商"""
    try:
        service = SupplyChainIntegration(db)
        supplier = await service.register_supplier(
            name=request.name,
            category=request.category,
            contact_person=request.contact_person,
            phone=request.phone,
            email=request.email,
            address=request.address,
            payment_terms=request.payment_terms,
            delivery_time=request.delivery_time,
            notes=request.notes,
        )
        return {\"success\": True, \"supplier_id\": supplier.id, \"code\": supplier.code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateSupplierRequest(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    payment_terms: Optional[str] = None
    delivery_time: Optional[int] = None
    notes: Optional[str] = None


class EvaluateSupplierRequest(BaseModel):
    quality_score: float = Field(..., ge=0, le=5, description="质量评分 0-5")
    delivery_score: float = Field(..., ge=0, le=5, description="准时交货评分 0-5")
    price_score: float = Field(..., ge=0, le=5, description="价格竞争力评分 0-5")
    comment: Optional[str] = None


@supply_chain_router.patch("/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: str,
    request: UpdateSupplierRequest,
    db: AsyncSession = Depends(get_db),
):
    """更新供应商信息"""
    from src.models.supply_chain import Supplier
    from sqlalchemy import select
    try:
        result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
        supplier = result.scalar_one_or_none()
        if not supplier:
            raise HTTPException(status_code=404, detail="供应商不存在")
        for field, value in request.model_dump(exclude_none=True).items():
            setattr(supplier, field, value)
        await db.commit()
        await db.refresh(supplier)
        return {"success": True, "supplier_id": supplier.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@supply_chain_router.delete("/suppliers/{supplier_id}")
async def deactivate_supplier(
    supplier_id: str,
    db: AsyncSession = Depends(get_db),
):
    """停用供应商（软删除）"""
    from src.models.supply_chain import Supplier
    from sqlalchemy import select
    try:
        result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
        supplier = result.scalar_one_or_none()
        if not supplier:
            raise HTTPException(status_code=404, detail="供应商不存在")
        supplier.status = "inactive"
        await db.commit()
        return {"success": True, "message": "供应商已停用"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@supply_chain_router.post("/suppliers/{supplier_id}/evaluate")
async def evaluate_supplier(
    supplier_id: str,
    request: EvaluateSupplierRequest,
    db: AsyncSession = Depends(get_db),
):
    """评价供应商，更新综合评分"""
    from src.models.supply_chain import Supplier
    from sqlalchemy import select
    try:
        result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
        supplier = result.scalar_one_or_none()
        if not supplier:
            raise HTTPException(status_code=404, detail="供应商不存在")
        # 综合评分：三项加权平均
        new_rating = round((request.quality_score + request.delivery_score + request.price_score) / 3, 2)
        # 与历史评分做滑动平均（若已有评分）
        if supplier.rating:
            supplier.rating = round((float(supplier.rating) + new_rating) / 2, 2)
        else:
            supplier.rating = new_rating
        await db.commit()
        return {
            "success": True,
            "supplier_id": supplier_id,
            "new_rating": new_rating,
            "overall_rating": float(supplier.rating),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@supply_chain_router.get("/suppliers/{supplier_id}/performance")
async def get_supplier_performance_api(
    supplier_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取供应商历史绩效"""
    try:
        service = SupplyChainIntegration(db)
        perf = await service.get_supplier_performance(supplier_id)
        return {"success": True, "performance": perf}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@supply_chain_router.post("/quotes/request")
async def request_quotes(
    request: RequestQuotesRequest,
    db: AsyncSession = Depends(get_db)
):
    """向供应商询价"""
    try:
        service = SupplyChainIntegration(db)
        quotes = await service.request_quotes(
            material_id=request.material_id,
            quantity=request.quantity,
            required_date=request.required_date,
            supplier_ids=request.supplier_ids,
        )
        return {"success": True, "total_quotes": len(quotes), "quotes": quotes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@supply_chain_router.post("/quotes/compare")
async def compare_quotes(
    request: CompareQuotesRequest,
    db: AsyncSession = Depends(get_db)
):
    """比较报价"""
    try:
        service = SupplyChainIntegration(db)
        comparison = service.compare_quotes(request.quotes)
        return {"success": True, **comparison}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@supply_chain_router.post("/orders")
async def create_order(
    request: CreateOrderRequest,
    db: AsyncSession = Depends(get_db)
):
    """创建采购订单"""
    try:
        service = SupplyChainIntegration(db)
        order = await service.create_purchase_order(
            store_id=request.store_id,
            supplier_id=request.supplier_id,
            items=request.items,
            expected_delivery=request.expected_delivery,
            created_by=request.created_by,
            notes=request.notes,
        )
        return {"success": True, "order_id": order.id, "order_number": order.order_number, "status": order.status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@supply_chain_router.get("/orders")
async def list_orders(
    store_id: Optional[str] = None,
    supplier_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """查询采购订单"""
    try:
        service = SupplyChainIntegration(db)
        orders = await service.get_purchase_orders(store_id=store_id, supplier_id=supplier_id, status=status)
        return {
            "success": True,
            "orders": [
                {
                    "id": o.id, "order_number": o.order_number,
                    "supplier_id": o.supplier_id, "store_id": o.store_id,
                    "status": o.status, "total_amount": o.total_amount / 100,
                    "expected_delivery": o.expected_delivery.isoformat() if o.expected_delivery else None,
                    "created_at": o.created_at.isoformat(),
                }
                for o in orders
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@supply_chain_router.patch("/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    request: UpdateOrderStatusRequest,
    db: AsyncSession = Depends(get_db)
):
    """更新订单状态"""
    try:
        service = SupplyChainIntegration(db)
        order = await service.update_order_status(order_id=order_id, status=request.status)
        return {"success": True, "order_id": order.id, "status": order.status}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Internationalization ====================
i18n_router = APIRouter(prefix="/api/v1/i18n", tags=["internationalization"])


class LanguageEnum(str, Enum):
    ZH_CN = "zh_CN"
    ZH_TW = "zh_TW"
    EN_US = "en_US"
    EN_GB = "en_GB"
    JA_JP = "ja_JP"
    KO_KR = "ko_KR"
    TH_TH = "th_TH"
    VI_VN = "vi_VN"


class CurrencyEnum(str, Enum):
    CNY = "CNY"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    KRW = "KRW"
    THB = "THB"
    VND = "VND"


@i18n_router.get("/languages")
async def get_supported_languages(db: AsyncSession = Depends(get_db)):
    """Get supported languages"""
    try:
        service = InternationalizationService(db)
        languages = service.get_supported_languages()

        return {
            "success": True,
            "languages": languages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@i18n_router.get("/currencies")
async def get_supported_currencies(db: AsyncSession = Depends(get_db)):
    """Get supported currencies"""
    try:
        service = InternationalizationService(db)
        currencies = service.get_supported_currencies()

        return {
            "success": True,
            "currencies": currencies
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@i18n_router.post("/currency/convert")
async def convert_currency(
    amount: float,
    from_currency: CurrencyEnum,
    to_currency: CurrencyEnum,
    db: AsyncSession = Depends(get_db)
):
    """Convert currency"""
    try:
        service = InternationalizationService(db)
        converted = service.convert_currency(
            amount=amount,
            from_currency=Currency(from_currency.value),
            to_currency=Currency(to_currency.value)
        )

        return {
            "success": True,
            "original_amount": amount,
            "original_currency": from_currency.value,
            "converted_amount": converted,
            "converted_currency": to_currency.value
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Export all routers
__all__ = ["platform_router", "industry_router", "supply_chain_router", "i18n_router"]
