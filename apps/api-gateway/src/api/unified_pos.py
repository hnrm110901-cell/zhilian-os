"""
统一 POS 收银 API — 平替天财商龙的完整收银接口

路由前缀: /api/v1/pos
覆盖: 开单/点菜/加菜/退菜/结账/厨打/KDS/多端点单/影子同步
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/pos", tags=["unified-pos"])


# ── Request/Response Models ──────────────────────────────────────────────────

class OrderItemRequest(BaseModel):
    """点菜请求项"""
    dish_id: str = Field(..., description="菜品ID")
    dish_name: str = Field(..., description="菜品名称")
    quantity: int = Field(1, ge=1, description="数量")
    pricing_mode: str = Field("fixed", description="计价模式: fixed/by_weight/market/by_count/package")
    unit_price_fen: int = Field(0, ge=0, description="单价(分)")
    spec_id: Optional[str] = Field(None, description="规格ID")
    spec_name: Optional[str] = Field(None, description="规格名称")
    weight_g: Optional[float] = Field(None, description="重量(克), 海鲜称重时必填")
    market_price_fen: Optional[int] = Field(None, description="时价(分), 海鲜时价时必填")
    cooking_method: Optional[str] = Field(None, description="做法: 清蒸/红烧/白灼/椒盐...")
    notes: Optional[str] = Field(None, description="备注: 少盐/不要辣/...")
    kitchen_station: Optional[str] = Field(None, description="厨房工位")
    is_gift: bool = Field(False, description="是否赠品")


class CreateOrderRequest(BaseModel):
    """开单请求"""
    table_code: str = Field(..., description="桌号")
    party_size: int = Field(1, ge=1, description="就餐人数")
    items: List[OrderItemRequest] = Field(..., min_length=1, description="菜品列表")
    scene: str = Field("dine_in", description="场景: dine_in/takeaway/self_pickup/outdoor/banquet/set_meal/delivery")
    device_type: str = Field("pos_terminal", description="设备: mini_program/mobile/tablet/tv/touch_screen/pos_terminal")
    waiter_id: Optional[str] = Field(None, description="服务员ID")
    member_id: Optional[str] = Field(None, description="会员ID")
    reservation_id: Optional[str] = Field(None, description="预定ID")


class AddItemsRequest(BaseModel):
    """加菜请求"""
    items: List[OrderItemRequest] = Field(..., min_length=1)
    device_type: str = Field("pos_terminal")


class VoidItemRequest(BaseModel):
    """退菜请求"""
    item_id: str = Field(..., description="菜品明细ID")
    reason: str = Field(..., description="退菜原因")
    operator_id: str = Field(..., description="操作员ID")


class CouponRequest(BaseModel):
    """优惠券请求"""
    coupon_code: str = Field(..., description="券码")
    platform: str = Field("meituan", description="平台: meituan/douyin/dianping/weishenghuo/self")
    coupon_value_fen: int = Field(0, ge=0, description="券面值(分)")
    coupon_type: str = Field("voucher", description="类型: discount/voucher/package")
    min_order_fen: int = Field(0, ge=0, description="最低消费(分)")


class PaymentRequest(BaseModel):
    """支付项"""
    method: str = Field(..., description="支付方式: cash/wechat/alipay/member_balance/member_points/bank_card/coupon/credit")
    amount_fen: int = Field(..., ge=0, description="支付金额(分)")
    reference: str = Field("", description="支付参考号")


class SettleRequest(BaseModel):
    """结账请求"""
    payments: List[PaymentRequest] = Field(..., min_length=1, description="支付列表(支持混合支付)")


class KitchenDispatchRequest(BaseModel):
    """厨打分单请求"""
    priority: int = Field(0, ge=0, le=2, description="优先级: 0=普通, 1=加急, 2=VIP")


# ── KDS 相关 ─────────────────────────────────────────────────────────────────

class RegisterDeviceRequest(BaseModel):
    """注册KDS设备"""
    device_id: str
    device_name: str
    device_type: str = Field(..., description="kds_screen/printer/runner/expeditor")
    station: Optional[str] = Field(None, description="工位: hot_wok/steamer/deep_fry/cold_dish/seafood/...")
    ip_address: str = ""


class UpdateTicketRequest(BaseModel):
    """更新厨打票状态"""
    status: str = Field(..., description="queued/received/cooking/plating/ready/served/returned/cancelled")
    operator_id: Optional[str] = None


# ── 多端点单 ─────────────────────────────────────────────────────────────────

class RegisterSessionRequest(BaseModel):
    """设备会话注册"""
    device_id: str
    device_type: str = Field(..., description="mini_program/mobile/tablet/tv/touch_screen/pos_terminal")
    device_role: str = Field("customer_self", description="customer_self/waiter/cashier/kitchen/manager/display")
    table_code: Optional[str] = None
    employee_id: Optional[str] = None


class CartItemRequest(BaseModel):
    """购物车添加项"""
    dish_id: str
    dish_name: str
    quantity: int = 1
    unit_price_fen: int = 0
    spec_id: Optional[str] = None
    notes: Optional[str] = None
    expected_version: Optional[int] = None


# ═══════════════════════════════════════════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════════════════════════════════════════


# ── 1. 开单/点菜 ─────────────────────────────────────────────────────────────

@router.post("/orders", summary="开单（支持所有场景+海鲜称重+套餐）")
async def create_order(req: CreateOrderRequest) -> Dict[str, Any]:
    """
    创建订单。

    支持场景：堂食/外卖/自提/外摆/宴会/套餐/配送
    支持海鲜：称重(by_weight)/时价(market)/按只(by_count)
    支持设备：小程序/手机/平板/电视/触摸屏/POS终端
    """
    from services.unified_pos_engine import (
        UnifiedPOSEngine, OrderItemSpec, PricingMode, ConsumptionScene, DeviceType,
    )

    engine = UnifiedPOSEngine(store_id="default", brand_id="default")

    items = []
    for item_req in req.items:
        items.append(OrderItemSpec(
            dish_id=item_req.dish_id,
            dish_name=item_req.dish_name,
            pricing_mode=PricingMode(item_req.pricing_mode),
            quantity=item_req.quantity,
            unit_price_fen=item_req.unit_price_fen,
            spec_id=item_req.spec_id,
            spec_name=item_req.spec_name,
            weight_g=item_req.weight_g,
            market_price_fen=item_req.market_price_fen,
            cooking_method=item_req.cooking_method,
            notes=item_req.notes,
            is_gift=item_req.is_gift,
        ))

    order = await engine.create_order(
        table_code=req.table_code,
        party_size=req.party_size,
        items=items,
        scene=ConsumptionScene(req.scene),
        device_type=DeviceType(req.device_type),
        waiter_id=req.waiter_id,
        member_id=req.member_id,
        reservation_id=req.reservation_id,
    )
    return {"success": True, "data": order}


@router.post("/orders/{order_id}/items", summary="加菜")
async def add_items(order_id: str, req: AddItemsRequest) -> Dict[str, Any]:
    """追加点菜（加菜）"""
    from services.unified_pos_engine import (
        UnifiedPOSEngine, OrderItemSpec, PricingMode, DeviceType,
    )

    engine = UnifiedPOSEngine(store_id="default", brand_id="default")
    items = [
        OrderItemSpec(
            dish_id=i.dish_id,
            dish_name=i.dish_name,
            pricing_mode=PricingMode(i.pricing_mode),
            quantity=i.quantity,
            unit_price_fen=i.unit_price_fen,
            notes=i.notes,
        )
        for i in req.items
    ]

    try:
        result = await engine.add_items(order_id, items, DeviceType(req.device_type))
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/orders/{order_id}/items/{item_id}", summary="退菜")
async def void_item(order_id: str, item_id: str, req: VoidItemRequest) -> Dict[str, Any]:
    """退菜"""
    from services.unified_pos_engine import UnifiedPOSEngine

    engine = UnifiedPOSEngine(store_id="default", brand_id="default")
    try:
        result = await engine.void_item(order_id, item_id, req.reason, req.operator_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 2. 优惠券 ────────────────────────────────────────────────────────────────

@router.post("/orders/{order_id}/coupons", summary="应用优惠券（美团/抖音/大众点评/微生活）")
async def apply_coupon(order_id: str, req: CouponRequest) -> Dict[str, Any]:
    """验证并应用平台优惠券"""
    from services.unified_pos_engine import UnifiedPOSEngine, CouponApplication

    engine = UnifiedPOSEngine(store_id="default", brand_id="default")
    coupon = CouponApplication(
        coupon_code=req.coupon_code,
        platform=req.platform,
        coupon_value_fen=req.coupon_value_fen,
        coupon_type=req.coupon_type,
        min_order_fen=req.min_order_fen,
    )
    try:
        result = await engine.apply_coupon(order_id, coupon)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 3. 结账 ──────────────────────────────────────────────────────────────────

@router.post("/orders/{order_id}/settle", summary="结账（支持混合支付+会员余额+积分+券）")
async def settle_order(order_id: str, req: SettleRequest) -> Dict[str, Any]:
    """
    结账。支持混合支付：
    - 微信/支付宝/现金/银行卡
    - 会员余额/积分抵扣
    - 挂账（企业/协议单位）
    """
    from services.unified_pos_engine import UnifiedPOSEngine, PaymentEntry, PaymentMethod

    engine = UnifiedPOSEngine(store_id="default", brand_id="default")
    payments = [
        PaymentEntry(
            method=PaymentMethod(p.method),
            amount_fen=p.amount_fen,
            reference=p.reference,
        )
        for p in req.payments
    ]
    try:
        result = await engine.settle(order_id, payments)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 4. 厨打/KDS ──────────────────────────────────────────────────────────────

@router.post("/orders/{order_id}/kitchen", summary="下发厨打（按工位自动拆分）")
async def dispatch_kitchen(order_id: str, req: KitchenDispatchRequest) -> Dict[str, Any]:
    """下发厨打单到 KDS/打印机"""
    from services.unified_pos_engine import UnifiedPOSEngine

    engine = UnifiedPOSEngine(store_id="default", brand_id="default")
    try:
        tickets = await engine.dispatch_to_kitchen(order_id, req.priority)
        return {"success": True, "data": {"tickets": tickets}}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/kds/expeditor", summary="催菜员汇总视图（所有工位）")
async def get_expeditor_view(store_id: str = "default") -> Dict[str, Any]:
    """获取催菜员汇总视图"""
    from services.kds_protocol_service import KDSProtocolService

    kds = KDSProtocolService(store_id)
    return {"success": True, "data": kds.get_expeditor_view()}


@router.get("/kds/station/{station}", summary="获取工位队列")
async def get_station_queue(station: str, store_id: str = "default") -> Dict[str, Any]:
    """获取指定工位的出餐队列"""
    from services.kds_protocol_service import KDSProtocolService, StationCategory

    kds = KDSProtocolService(store_id)
    try:
        queue = kds.get_station_queue(StationCategory(station))
        return {"success": True, "data": {"station": station, "queue": queue}}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效工位: {station}")


@router.post("/kds/tickets/{ticket_id}/status", summary="更新厨打票状态")
async def update_ticket_status(
    ticket_id: str,
    req: UpdateTicketRequest,
    store_id: str = "default",
) -> Dict[str, Any]:
    """更新厨打票状态（KDS 大屏操作）"""
    from services.kds_protocol_service import KDSProtocolService, TicketStatus

    kds = KDSProtocolService(store_id)
    try:
        result = kds.update_ticket_status(ticket_id, TicketStatus(req.status), req.operator_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"厨打票不存在: {ticket_id}")
        return {"success": True, "data": result}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效状态: {req.status}")


@router.post("/kds/orders/{order_id}/rush", summary="催菜")
async def rush_order(order_id: str, store_id: str = "default") -> Dict[str, Any]:
    """催菜（提升优先级）"""
    from services.kds_protocol_service import KDSProtocolService

    kds = KDSProtocolService(store_id)
    result = kds.rush_order(order_id)
    return {"success": True, "data": {"rushed_tickets": result}}


@router.get("/kds/orders/{order_id}/status", summary="订单厨房进度")
async def get_kitchen_status(order_id: str, store_id: str = "default") -> Dict[str, Any]:
    """获取订单的厨房出餐进度"""
    from services.kds_protocol_service import KDSProtocolService

    kds = KDSProtocolService(store_id)
    return {"success": True, "data": kds.get_order_kitchen_status(order_id)}


@router.post("/kds/devices", summary="注册 KDS 设备/打印机")
async def register_kds_device(req: RegisterDeviceRequest, store_id: str = "default") -> Dict[str, Any]:
    """注册 KDS 显示屏或厨房打印机"""
    from services.kds_protocol_service import KDSProtocolService, KDSDeviceType, StationCategory

    kds = KDSProtocolService(store_id)
    device = kds.register_device(
        device_id=req.device_id,
        device_name=req.device_name,
        device_type=KDSDeviceType(req.device_type),
        station=StationCategory(req.station) if req.station else None,
        ip_address=req.ip_address,
    )
    return {"success": True, "data": device.to_dict()}


# ── 5. 多端点单 ──────────────────────────────────────────────────────────────

@router.post("/devices/sessions", summary="设备会话注册")
async def register_device_session(req: RegisterSessionRequest, store_id: str = "default") -> Dict[str, Any]:
    """注册点单设备并创建会话"""
    from services.multi_device_ordering_gateway import (
        MultiDeviceOrderingGateway, DeviceType, DeviceRole,
    )

    gateway = MultiDeviceOrderingGateway(store_id)
    session = gateway.register_device(
        device_id=req.device_id,
        device_type=DeviceType(req.device_type),
        device_role=DeviceRole(req.device_role),
        table_code=req.table_code,
        employee_id=req.employee_id,
    )
    return {"success": True, "data": session.to_dict()}


@router.post("/cart/{table_code}/items", summary="添加到共享购物车")
async def add_to_cart(
    table_code: str,
    req: CartItemRequest,
    session_id: str = Query(..., description="设备会话ID"),
    store_id: str = "default",
) -> Dict[str, Any]:
    """
    添加菜品到共享购物车（同桌多设备共享）。

    支持乐观锁：传 expected_version 检查冲突。
    """
    from services.multi_device_ordering_gateway import MultiDeviceOrderingGateway

    gateway = MultiDeviceOrderingGateway(store_id)
    result = gateway.add_to_cart(
        session_id=session_id,
        table_code=table_code,
        item={
            "dish_id": req.dish_id,
            "dish_name": req.dish_name,
            "quantity": req.quantity,
            "unit_price_fen": req.unit_price_fen,
            "spec_id": req.spec_id,
            "notes": req.notes,
        },
        expected_version=req.expected_version,
    )
    return result


@router.get("/cart/{table_code}", summary="获取共享购物车")
async def get_cart(table_code: str, store_id: str = "default") -> Dict[str, Any]:
    """获取桌台共享购物车"""
    from services.multi_device_ordering_gateway import MultiDeviceOrderingGateway

    gateway = MultiDeviceOrderingGateway(store_id)
    return {"success": True, "data": gateway.get_cart(table_code)}


@router.get("/devices/gateway-status", summary="多端网关状态")
async def get_gateway_status(store_id: str = "default") -> Dict[str, Any]:
    """获取多端点单网关状态"""
    from services.multi_device_ordering_gateway import MultiDeviceOrderingGateway

    gateway = MultiDeviceOrderingGateway(store_id)
    return {"success": True, "data": gateway.get_gateway_status()}


# ── 6. 影子同步 ──────────────────────────────────────────────────────────────

@router.get("/shadow/report/{date}", summary="影子同步每日对账报告")
async def get_shadow_report(date: str, store_id: str = "default") -> Dict[str, Any]:
    """获取影子同步一致性报告"""
    from services.shadow_sync_service import ShadowSyncService

    sync = ShadowSyncService(store_id, "default")
    return {"success": True, "data": sync.generate_daily_report(date)}


@router.get("/shadow/readiness", summary="切换就绪度评估")
async def get_cutover_readiness(store_id: str = "default") -> Dict[str, Any]:
    """评估是否可以从天财商龙切换到屯象OS"""
    from services.shadow_sync_service import ShadowSyncService

    sync = ShadowSyncService(store_id, "default")
    return {"success": True, "data": sync.get_cutover_readiness()}


@router.post("/shadow/sync-menu", summary="同步菜单变更（天财→屯象）")
async def sync_menu(store_id: str = "default") -> Dict[str, Any]:
    """从天财商龙同步最新菜单"""
    from services.shadow_sync_service import ShadowSyncService

    sync = ShadowSyncService(store_id, "default")
    return {"success": True, "data": await sync.sync_menu_changes()}


@router.post("/shadow/sync-tables", summary="同步桌台状态（天财→屯象）")
async def sync_tables(store_id: str = "default") -> Dict[str, Any]:
    """从天财商龙同步桌台状态"""
    from services.shadow_sync_service import ShadowSyncService

    sync = ShadowSyncService(store_id, "default")
    return {"success": True, "data": await sync.sync_table_status()}
