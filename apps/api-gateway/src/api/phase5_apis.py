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
    SupplierType
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


class CreateOrderRequest(BaseModel):
    store_id: str
    supplier_id: str
    items: List[dict]
    expected_delivery: datetime
    created_by: Optional[str] = None
    notes: Optional[str] = None


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
