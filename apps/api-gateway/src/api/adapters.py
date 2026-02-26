"""
API适配器集成接口
提供第三方系统数据同步功能
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import structlog

from ..services.adapter_integration_service import AdapterIntegrationService
from ..services.neural_system import neural_system

logger = structlog.get_logger()

router = APIRouter(prefix="/api/adapters", tags=["adapters"])

# 初始化集成服务
integration_service = AdapterIntegrationService(neural_system=neural_system)


# ==================== 请求模型 ====================


class OrderSyncRequest(BaseModel):
    """订单同步请求"""

    order_id: str
    store_id: str
    source_system: str  # tiancai, meituan


class DishSyncRequest(BaseModel):
    """菜品同步请求"""

    store_id: str
    source_system: str  # tiancai, meituan


class InventorySyncRequest(BaseModel):
    """库存同步请求"""

    item_id: str
    quantity: float
    target_system: str  # tiancai, meituan
    operation_type: Optional[int] = 1  # 1-入库 2-出库 3-盘点


class AdapterRegisterRequest(BaseModel):
    """适配器注册请求"""

    adapter_name: str  # tiancai, meituan, aoqiwei, pinzhi, yiding
    config: Dict[str, Any]


# ==================== 响应模型 ====================


class SyncResponse(BaseModel):
    """同步响应"""

    status: str
    message: str
    data: Optional[Dict[str, Any]] = None


# ==================== API端点 ====================


@router.post("/register", response_model=SyncResponse)
async def register_adapter(request: AdapterRegisterRequest):
    """
    注册API适配器

    Args:
        request: 适配器注册请求

    Returns:
        注册结果
    """
    try:
        adapter_name = request.adapter_name.lower()

        # 根据适配器名称创建实例
        if adapter_name == "tiancai":
            from packages.api_adapters.tiancai_shanglong.src import TiancaiShanglongAdapter

            adapter = TiancaiShanglongAdapter(request.config)
        elif adapter_name == "meituan":
            from packages.api_adapters.meituan_saas.src import MeituanSaasAdapter

            adapter = MeituanSaasAdapter(request.config)
        elif adapter_name == "aoqiwei":
            from packages.api_adapters.aoqiwei.src import AoqiweiAdapter

            adapter = AoqiweiAdapter(request.config)
        elif adapter_name == "pinzhi":
            from packages.api_adapters.pinzhi.src import PinzhiAdapter

            adapter = PinzhiAdapter(request.config)
        elif adapter_name == "yiding":
            from packages.api_adapters.yiding.src import YiDingAdapter

            adapter = YiDingAdapter(request.config)
        else:
            raise HTTPException(status_code=400, detail=f"不支持的适配器: {adapter_name}")

        # 注册适配器
        integration_service.register_adapter(adapter_name, adapter, request.config)

        logger.info("适配器注册成功", adapter_name=adapter_name)

        return SyncResponse(
            status="success",
            message=f"适配器 {adapter_name} 注册成功",
            data={"adapter_name": adapter_name},
        )

    except Exception as e:
        logger.error("适配器注册失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/order", response_model=SyncResponse)
async def sync_order(request: OrderSyncRequest):
    """
    同步订单

    Args:
        request: 订单同步请求

    Returns:
        同步结果
    """
    try:
        source_system = request.source_system.lower()

        if source_system == "tiancai":
            result = await integration_service.sync_order_from_tiancai(
                order_id=request.order_id,
                store_id=request.store_id,
            )
        elif source_system == "meituan":
            result = await integration_service.sync_order_from_meituan(
                order_id=request.order_id,
                store_id=request.store_id,
            )
        else:
            raise HTTPException(status_code=400, detail=f"不支持的来源系统: {source_system}")

        return SyncResponse(
            status="success",
            message="订单同步成功",
            data=result,
        )

    except Exception as e:
        logger.error("订单同步失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/dishes", response_model=SyncResponse)
async def sync_dishes(request: DishSyncRequest):
    """
    同步菜品

    Args:
        request: 菜品同步请求

    Returns:
        同步结果
    """
    try:
        source_system = request.source_system.lower()

        if source_system == "tiancai":
            result = await integration_service.sync_dishes_from_tiancai(
                store_id=request.store_id,
            )
        elif source_system == "meituan":
            result = await integration_service.sync_dishes_from_meituan(
                store_id=request.store_id,
            )
        else:
            raise HTTPException(status_code=400, detail=f"不支持的来源系统: {source_system}")

        return SyncResponse(
            status="success",
            message="菜品同步成功",
            data=result,
        )

    except Exception as e:
        logger.error("菜品同步失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/inventory", response_model=SyncResponse)
async def sync_inventory(request: InventorySyncRequest):
    """
    同步库存

    Args:
        request: 库存同步请求

    Returns:
        同步结果
    """
    try:
        target_system = request.target_system.lower()

        if target_system == "tiancai":
            result = await integration_service.sync_inventory_to_tiancai(
                material_id=request.item_id,
                quantity=request.quantity,
                operation_type=request.operation_type,
            )
        elif target_system == "meituan":
            result = await integration_service.sync_inventory_to_meituan(
                food_id=request.item_id,
                stock=int(request.quantity),
            )
        else:
            raise HTTPException(status_code=400, detail=f"不支持的目标系统: {target_system}")

        return SyncResponse(
            status="success",
            message="库存同步成功",
            data=result,
        )

    except Exception as e:
        logger.error("库存同步失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/all/{source_system}/{store_id}", response_model=SyncResponse)
async def sync_all(source_system: str, store_id: str):
    """
    全量同步

    Args:
        source_system: 来源系统 (tiancai, meituan)
        store_id: 门店ID

    Returns:
        同步结果
    """
    try:
        source_system = source_system.lower()

        if source_system == "tiancai":
            result = await integration_service.sync_all_from_tiancai(store_id=store_id)
        elif source_system == "meituan":
            result = await integration_service.sync_all_from_meituan(store_id=store_id)
        else:
            raise HTTPException(status_code=400, detail=f"不支持的来源系统: {source_system}")

        return SyncResponse(
            status="success",
            message="全量同步成功",
            data=result,
        )

    except Exception as e:
        logger.error("全量同步失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters", response_model=Dict[str, Any])
async def list_adapters():
    """
    列出已注册的适配器

    Returns:
        适配器列表
    """
    try:
        adapters = list(integration_service.adapters.keys())
        return {
            "status": "success",
            "adapters": adapters,
            "count": len(adapters),
        }

    except Exception as e:
        logger.error("获取适配器列表失败", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
