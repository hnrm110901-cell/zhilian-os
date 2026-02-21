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

from ..services.open_api_platform import (
    OpenAPIPlatform,
    DeveloperTier,
    PluginCategory,
    PluginStatus
)
from ..services.industry_solutions import (
    IndustrySolutionsService,
    IndustryType,
    TemplateType
)
from ..services.supply_chain_integration import (
    SupplyChainIntegration,
    SupplierType
)
from ..services.internationalization import (
    InternationalizationService,
    Language,
    Currency
)
from ..database import get_db
from sqlalchemy.orm import Session


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
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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


@supply_chain_router.post("/quotes/request")
async def request_quotes(
    request: RequestQuotesRequest,
    db: Session = Depends(get_db)
):
    """Request quotes from suppliers"""
    try:
        service = SupplyChainIntegration(db)
        quotes = service.request_quotes(
            material_id=request.material_id,
            quantity=request.quantity,
            required_date=request.required_date,
            supplier_ids=request.supplier_ids
        )

        return {
            "success": True,
            "total_quotes": len(quotes),
            "quotes": [
                {
                    "quote_id": q.quote_id,
                    "supplier_id": q.supplier_id,
                    "unit_price": q.unit_price,
                    "total_price": q.total_price,
                    "delivery_date": q.delivery_date.isoformat()
                }
                for q in quotes
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@supply_chain_router.post("/quotes/compare")
async def compare_quotes(
    quote_ids: List[str],
    db: Session = Depends(get_db)
):
    """Compare quotes"""
    try:
        service = SupplyChainIntegration(db)
        comparison = service.compare_quotes(quote_ids)

        return {
            "success": True,
            **comparison
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
async def get_supported_languages(db: Session = Depends(get_db)):
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
async def get_supported_currencies(db: Session = Depends(get_db)):
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
    db: Session = Depends(get_db)
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
