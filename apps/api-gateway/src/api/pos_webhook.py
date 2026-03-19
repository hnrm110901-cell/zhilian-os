"""
Webhook POS 适配器
支持美团收银、客如云、微信收款码等通过 Webhook 推送订单的 POS 系统

接入方式：
  1. 在 POS 系统后台配置 Webhook URL：
     POST /api/v1/pos-webhook/{store_id}/order
  2. 配置签名密钥（可选）：env WEBHOOK_POS_SECRET
  3. 系统自动将推送的订单写入 orders 表

支持的 POS 格式（通过 source 字段区分）：
  - meituan   美团收银
  - keruyun   客如云
  - pinzhi    品智收银（专用端点 /{store_id}/pinzhi-order + MD5 签名）
  - generic   通用格式（自定义字段映射）
"""

import hashlib
import hmac
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from src.core.database import get_db_session
from src.models.order import Order, OrderItem, OrderStatus

# 品智签名验证需要 token
PINZHI_WEBHOOK_TOKEN = os.getenv("PINZHI_WEBHOOK_TOKEN", "")

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/pos-webhook", tags=["pos_webhook"])

WEBHOOK_SECRET = os.getenv("WEBHOOK_POS_SECRET", "")

# 延迟初始化（lazy），避免模块导入时产生循环依赖；测试可通过 patch 此名称替换
identity_resolution_service = None


# ── Pydantic 入参模型 ──────────────────────────────────────────


class WebhookOrderItem(BaseModel):
    item_id: str = ""
    item_name: str
    quantity: int = 1
    unit_price: int  # 分
    subtotal: int  # 分
    notes: Optional[str] = None


class WebhookOrderPayload(BaseModel):
    """通用 Webhook 订单格式（各 POS 字段映射后统一为此结构）"""

    source: str = "generic"  # meituan | keruyun | generic
    external_order_id: str  # POS 系统内部订单号
    table_number: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    status: str = "completed"  # POS 推送时通常已完成
    total_amount: int  # 分
    discount_amount: int = 0  # 分
    final_amount: int  # 分
    order_time: Optional[str] = None  # ISO8601，缺省用当前时间
    items: List[WebhookOrderItem] = []
    notes: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None  # 原始 payload 存档


# ── 签名验证 ───────────────────────────────────────────────────


def _verify_signature(body: bytes, signature: Optional[str]) -> bool:
    """HMAC-SHA256 签名验证，未配置 secret 时跳过"""
    if not WEBHOOK_SECRET:
        return True
    if not signature:
        return False
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


# ── 各 POS 格式归一化 ──────────────────────────────────────────


def _normalize_meituan(raw: Dict[str, Any]) -> WebhookOrderPayload:
    """美团收银 Webhook 字段映射"""
    items = [
        WebhookOrderItem(
            item_id=str(d.get("skuId", "")),
            item_name=d.get("skuName", ""),
            quantity=int(d.get("num", 1)),
            unit_price=int(float(d.get("price", 0)) * 100),
            subtotal=int(float(d.get("amount", 0)) * 100),
        )
        for d in raw.get("detailList", [])
    ]
    return WebhookOrderPayload(
        source="meituan",
        external_order_id=str(raw.get("orderId", "")),
        table_number=str(raw.get("tableCode", "")),
        customer_name=raw.get("userName"),
        customer_phone=raw.get("userPhone"),
        status="completed",
        total_amount=int(float(raw.get("totalPrice", 0)) * 100),
        discount_amount=int(float(raw.get("discountPrice", 0)) * 100),
        final_amount=int(float(raw.get("payPrice", 0)) * 100),
        order_time=raw.get("createTime"),
        items=items,
        raw=raw,
    )


def _normalize_keruyun(raw: Dict[str, Any]) -> WebhookOrderPayload:
    """客如云 Webhook 字段映射"""
    items = [
        WebhookOrderItem(
            item_id=str(d.get("dishId", "")),
            item_name=d.get("dishName", ""),
            quantity=int(d.get("num", 1)),
            unit_price=int(float(d.get("price", 0)) * 100),
            subtotal=int(float(d.get("totalPrice", 0)) * 100),
        )
        for d in raw.get("orderDetails", [])
    ]
    return WebhookOrderPayload(
        source="keruyun",
        external_order_id=str(raw.get("orderNo", "")),
        table_number=raw.get("tableNo"),
        customer_name=raw.get("memberName"),
        customer_phone=raw.get("memberPhone"),
        status="completed",
        total_amount=int(float(raw.get("totalAmount", 0)) * 100),
        discount_amount=int(float(raw.get("discountAmount", 0)) * 100),
        final_amount=int(float(raw.get("payAmount", 0)) * 100),
        order_time=raw.get("createTime"),
        items=items,
        raw=raw,
    )


def _normalize_pinzhi(raw: Dict[str, Any]) -> WebhookOrderPayload:
    """
    品智 POS Webhook 字段映射

    品智原始字段（参考 queryOrderListV2.do / Webhook 推送）：
      billId, billNo, orderSource, tableNo, openTime, payTime,
      dishPriceTotal, specialOfferPrice, realPrice, billStatus,
      dishList[{dishId, dishName, dishPrice, dishNum}]
    金额单位：分（整数）
    """
    items = [
        WebhookOrderItem(
            item_id=str(d.get("dishId", "")),
            item_name=d.get("dishName", ""),
            quantity=int(d.get("dishNum", d.get("quantity", 1))),
            unit_price=int(d.get("dishPrice", d.get("price", 0))),
            subtotal=int(d.get("dishPrice", d.get("price", 0)))
            * int(d.get("dishNum", d.get("quantity", 1))),
        )
        for d in raw.get("dishList", [])
    ]

    # billStatus: 1=已结账 0=未结账 2=已退单
    bill_status = raw.get("billStatus", 0)
    status_map = {1: "completed", 0: "pending", 2: "cancelled"}
    status = status_map.get(bill_status, "pending")

    return WebhookOrderPayload(
        source="pinzhi",
        external_order_id=str(raw.get("billId", raw.get("billNo", ""))),
        table_number=raw.get("tableNo"),
        customer_name=raw.get("vipCard"),  # 品智用 vipCard 标识客户
        customer_phone=None,
        status=status,
        total_amount=int(raw.get("dishPriceTotal", 0)),
        discount_amount=int(raw.get("specialOfferPrice", 0)),
        final_amount=int(raw.get("realPrice", 0)),
        order_time=raw.get("payTime") or raw.get("openTime"),
        items=items,
        notes=raw.get("remark"),
        raw=raw,
    )


def _pinzhi_generate_sign(token: str, params: Dict[str, Any]) -> str:
    """
    品智 MD5 签名算法（内联实现，避免跨包导入问题）。
    规则：参数按 key ASCII 升序拼接（排除 sign/pageIndex/pageSize），
    末尾加 &token=xxx，整体 MD5 取 32 位小写 hex。
    """
    filtered = {
        k: v
        for k, v in params.items()
        if k not in ("sign", "pageIndex", "pageSize") and v is not None
    }
    ordered = sorted(filtered.items())
    param_str = "&".join(f"{k}={v}" for k, v in ordered)
    param_str += f"&token={token}"
    return hashlib.md5(param_str.encode("utf-8")).hexdigest()


def _verify_pinzhi_signature(raw: Dict[str, Any]) -> bool:
    """
    验证品智 Webhook 推送签名（MD5）。
    品智签名规则：参数按 key ASCII 升序拼接 + token，MD5 取 hex。
    未配置 PINZHI_WEBHOOK_TOKEN 时跳过验证。
    """
    if not PINZHI_WEBHOOK_TOKEN:
        return True
    sign = raw.get("sign", "")
    if not sign:
        return False
    expected = _pinzhi_generate_sign(PINZHI_WEBHOOK_TOKEN, raw)
    return expected == sign


NORMALIZERS = {
    "meituan": _normalize_meituan,
    "keruyun": _normalize_keruyun,
    "pinzhi": _normalize_pinzhi,
}


# ── 识客 ───────────────────────────────────────────────────────


async def _handle_member_check_in(
    store_id: str,
    customer_phone: Optional[str],
) -> Optional["uuid.UUID"]:
    """POS开单时自动识客：resolve phone → 创建 MemberCheckIn 记录。
    自行管理 DB session（与 _upsert_order 模式一致，使用 get_db_session）。
    """
    if not customer_phone:
        return None
    try:
        # 延迟导入，避免循环依赖；同时允许测试通过模块属性 patch
        global identity_resolution_service
        if identity_resolution_service is None:
            from src.services.identity_resolution_service import (
                identity_resolution_service as _irs,
            )
            identity_resolution_service = _irs
        from src.models.member_check_in import MemberCheckIn
        from src.models.store import Store

        async with get_db_session() as session:
            store = await session.get(Store, store_id)
            brand_id = store.brand_id if store else ""

            consumer_id = await identity_resolution_service.resolve(
                session, customer_phone.strip(),
                store_id=store_id,
                source="pos_webhook",
            )
            check_in = MemberCheckIn(
                store_id=store_id,
                brand_id=brand_id,
                consumer_id=consumer_id,
                trigger_type="pos_webhook",
            )
            session.add(check_in)
            await session.commit()
            logger.info("POS识客事件已创建", store_id=store_id, consumer_id=str(consumer_id))
            return consumer_id
    except Exception as exc:
        logger.warning("POS识客失败，不影响订单处理", error=str(exc))
        return None


# ── 写库 ───────────────────────────────────────────────────────


async def _upsert_order(store_id: str, payload: WebhookOrderPayload) -> str:
    """将归一化订单写入 orders 表（幂等：同一 external_order_id 不重复写）"""
    order_id = f"POS_{payload.source.upper()}_{payload.external_order_id}"

    async with get_db_session() as session:
        from sqlalchemy import select

        existing = await session.execute(select(Order).where(Order.id == order_id))
        if existing.scalar_one_or_none():
            logger.info("POS 订单已存在，跳过", order_id=order_id)
            return order_id

        order_time = datetime.fromisoformat(payload.order_time) if payload.order_time else datetime.utcnow()

        order = Order(
            id=order_id,
            store_id=store_id,
            table_number=payload.table_number,
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            status=OrderStatus.COMPLETED.value,
            total_amount=payload.total_amount,
            discount_amount=payload.discount_amount,
            final_amount=payload.final_amount,
            order_time=order_time,
            completed_at=order_time,
            sales_channel=payload.source,  # 统一 source 标记：pinzhi/meituan/keruyun/generic
            notes=payload.notes,
            order_metadata={
                "source": payload.source,
                "external_order_id": payload.external_order_id,
                "raw": payload.raw,
            },
        )
        session.add(order)

        for item in payload.items:
            session.add(
                OrderItem(
                    order_id=order_id,
                    item_id=item.item_id or item.item_name,
                    item_name=item.item_name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    subtotal=item.subtotal,
                    notes=item.notes,
                )
            )

        await session.commit()
        logger.info("POS 订单写入成功", order_id=order_id, store_id=store_id)

    # 识客：如果订单含手机号，自动创建识客事件（独立session，不影响订单事务）
    if payload.customer_phone:
        await _handle_member_check_in(store_id=store_id, customer_phone=payload.customer_phone)

    return order_id


# ── API 端点 ───────────────────────────────────────────────────


@router.post("/{store_id}/order")
async def receive_pos_order(
    store_id: str,
    request: Request,
    x_pos_source: Optional[str] = Header(default="generic"),
    x_pos_signature: Optional[str] = Header(default=None),
):
    """
    接收 POS Webhook 推送的订单

    Headers:
      X-Pos-Source: meituan | keruyun | generic
      X-Pos-Signature: sha256=<hmac>  （配置 WEBHOOK_POS_SECRET 后必须携带）
    """
    body = await request.body()

    if not _verify_signature(body, x_pos_signature):
        raise HTTPException(status_code=401, detail="签名验证失败")

    raw = await request.json()
    source = (x_pos_source or "generic").lower()

    if source in NORMALIZERS:
        payload = NORMALIZERS[source](raw)
    else:
        # generic：直接用通用格式解析
        try:
            payload = WebhookOrderPayload(**raw, source="generic", raw=raw)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Payload 解析失败: {e}")

    order_id = await _upsert_order(store_id, payload)
    return {"success": True, "order_id": order_id, "source": source}


@router.post("/{store_id}/pinzhi-order")
async def receive_pinzhi_order(
    store_id: str,
    request: Request,
):
    """
    品智 POS 专用 Webhook 端点

    品智 POS 推送订单到此端点，使用品智自有的 MD5 签名验证。
    配置方式：在品智后台设置 Webhook URL 为
      POST {base}/api/v1/pos-webhook/{store_id}/pinzhi-order

    签名验证：配置 PINZHI_WEBHOOK_TOKEN 环境变量后自动启用。
    """
    raw = await request.json()

    # 品智签名验证（MD5，与品智 API 签名规则一致）
    if not _verify_pinzhi_signature(raw):
        raise HTTPException(status_code=401, detail="品智签名验证失败")

    payload = _normalize_pinzhi(raw)
    order_id = await _upsert_order(store_id, payload)

    logger.info(
        "pinzhi_webhook.order_received",
        store_id=store_id,
        order_id=order_id,
        bill_id=raw.get("billId"),
    )

    return {"success": True, "order_id": order_id, "source": "pinzhi"}


@router.get("/{store_id}/test")
async def test_webhook_endpoint(store_id: str):
    """连通性测试，POS 系统配置 Webhook 后可先 GET 验证"""
    return {
        "status": "ok",
        "store_id": store_id,
        "supported_sources": ["meituan", "keruyun", "pinzhi", "generic"],
        "signature_required": bool(WEBHOOK_SECRET),
        "pinzhi_signature_required": bool(PINZHI_WEBHOOK_TOKEN),
    }
