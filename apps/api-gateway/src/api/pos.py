"""
POS API
品智收银系统API端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import date
import structlog

from ..services.pos_service import pos_service
from ..core.auth import get_current_user, require_permissions
from ..models.user import User

logger = structlog.get_logger()

router = APIRouter()


# ==================== Request/Response Models ====================


class StoreInfo(BaseModel):
    """门店信息"""

    ognid: int
    ognno: str
    ognname: str
    ognaddress: Optional[str] = None
    ogntel: Optional[str] = None
    brandid: Optional[int] = None
    brandname: Optional[str] = None


class DishCategory(BaseModel):
    """菜品类别"""

    rcId: int
    rcNO: str
    rcNAME: str
    fatherId: int
    status: int


class Dish(BaseModel):
    """菜品信息"""

    dishesId: int
    dishesCode: str
    dishesName: str
    dishPrice: float
    rcId: int
    status: int
    unit: Optional[str] = None
    isRecommend: Optional[int] = None


class Table(BaseModel):
    """桌台信息"""

    tableId: int
    tableName: str
    blId: int
    blName: str


class Employee(BaseModel):
    """员工信息"""

    epId: int
    epNo: str
    epName: str
    pgId: int
    pgName: str
    status: int


class Order(BaseModel):
    """订单信息"""

    billId: str
    billNo: str
    orderSource: int
    tableNo: str
    people: int
    openTime: str
    payTime: Optional[str] = None
    billPriceTotal: int  # 单位：分
    realPrice: int  # 单位：分
    billStatus: int
    vipName: Optional[str] = None


class OrderQueryResponse(BaseModel):
    """订单查询响应"""

    orders: List[Order]
    page: int
    page_size: int
    total: int


class PayType(BaseModel):
    """支付方式"""

    id: int
    name: str
    category: int


class ConnectionTestResponse(BaseModel):
    """连接测试响应"""

    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
    stores_count: Optional[int] = None


# ==================== API Endpoints ====================


@router.get("/stores", response_model=List[StoreInfo], summary="获取门店信息")
async def get_stores(
    ognid: Optional[str] = Query(None, description="门店ID，不传则返回所有门店"),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["pos:read"])),
):
    """
    获取门店信息

    需要权限: pos:read
    """
    try:
        stores = await pos_service.get_stores(ognid)
        return stores
    except Exception as e:
        logger.error("获取门店信息失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取门店信息失败: {str(e)}")


@router.get(
    "/dish-categories", response_model=List[DishCategory], summary="获取菜品类别"
)
async def get_dish_categories(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["pos:read"])),
):
    """
    获取菜品类别

    需要权限: pos:read
    """
    try:
        categories = await pos_service.get_dish_categories()
        return categories
    except Exception as e:
        logger.error("获取菜品类别失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取菜品类别失败: {str(e)}")


@router.get("/dishes", response_model=List[Dish], summary="获取菜品信息")
async def get_dishes(
    updatetime: int = Query(0, description="同步时间戳，传0拉取所有"),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["pos:read"])),
):
    """
    获取菜品信息

    需要权限: pos:read
    """
    try:
        dishes = await pos_service.get_dishes(updatetime)
        return dishes
    except Exception as e:
        logger.error("获取菜品信息失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取菜品信息失败: {str(e)}")


@router.get("/tables", response_model=List[Table], summary="获取桌台信息")
async def get_tables(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["pos:read"])),
):
    """
    获取桌台信息

    需要权限: pos:read
    """
    try:
        tables = await pos_service.get_tables()
        return tables
    except Exception as e:
        logger.error("获取桌台信息失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取桌台信息失败: {str(e)}")


@router.get("/employees", response_model=List[Employee], summary="获取员工信息")
async def get_employees(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["pos:read"])),
):
    """
    获取员工信息

    需要权限: pos:read
    """
    try:
        employees = await pos_service.get_employees()
        return employees
    except Exception as e:
        logger.error("获取员工信息失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取员工信息失败: {str(e)}")


@router.get("/orders", response_model=OrderQueryResponse, summary="查询订单")
async def query_orders(
    ognid: Optional[str] = Query(None, description="门店ID"),
    begin_date: Optional[str] = Query(None, description="开始日期（yyyy-MM-dd）"),
    end_date: Optional[str] = Query(None, description="结束日期（yyyy-MM-dd）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["pos:read"])),
):
    """
    查询订单

    需要权限: pos:read
    """
    try:
        result = await pos_service.query_orders(
            ognid=ognid,
            begin_date=begin_date,
            end_date=end_date,
            page_index=page,
            page_size=page_size,
        )
        return result
    except Exception as e:
        logger.error("查询订单失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"查询订单失败: {str(e)}")


@router.get("/order-summary", summary="查询门店收入汇总")
async def query_order_summary(
    ognid: str = Query(..., description="门店ID"),
    business_date: str = Query(..., description="营业日（yyyy-MM-dd）"),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["pos:read"])),
):
    """
    查询门店收入汇总

    需要权限: pos:read
    """
    try:
        summary = await pos_service.query_order_summary(ognid, business_date)
        return summary
    except Exception as e:
        logger.error("查询收入汇总失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"查询收入汇总失败: {str(e)}")


@router.get("/pay-types", response_model=List[PayType], summary="获取支付方式")
async def get_pay_types(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["pos:read"])),
):
    """
    获取支付方式

    需要权限: pos:read
    """
    try:
        pay_types = await pos_service.get_pay_types()
        return pay_types
    except Exception as e:
        logger.error("获取支付方式失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"获取支付方式失败: {str(e)}")


@router.get(
    "/test-connection",
    response_model=ConnectionTestResponse,
    summary="测试POS系统连接",
)
async def test_connection(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["system:config"])),
):
    """
    测试POS系统连接

    需要权限: system:config
    """
    try:
        result = await pos_service.test_connection()
        return result
    except Exception as e:
        logger.error("测试连接失败", error=str(e))
        return ConnectionTestResponse(success=False, error=str(e))
