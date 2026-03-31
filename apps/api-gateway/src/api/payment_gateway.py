"""
支付网关 API
路由前缀: /api/v1/payments

端点列表：
  POST /wechat/jsapi       — 微信JSAPI下单（小程序/H5）
  POST /wechat/native      — 微信Native下单（扫码）
  POST /wechat/callback    — 微信支付回调（无需JWT，微信服务器调用）
  POST /alipay/callback    — 支付宝回调（无需JWT，支付宝服务器调用）
  POST /{payment_id}/refund — 退款
  GET  /{payment_id}/status — 查询支付状态
  GET  /records            — 支付记录列表

重要：回调端点不包含在 JWT 中间件保护范围内（微信/支付宝服务器无法传JWT）。
"""

import json
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_active_user
from src.models.user import User
from src.services.payment_gateway_service import PaymentGatewayService

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


# ================================================================
# 请求/响应模型
# ================================================================


class WechatJsapiRequest(BaseModel):
    """微信JSAPI下单请求"""

    store_id: str = Field(..., description="门店ID（UUID）")
    order_id: str = Field(..., description="订单ID（UUID）")
    amount_fen: int = Field(..., gt=0, description="支付金额（分），必须大于0")
    openid: str = Field(..., min_length=1, description="微信用户openid")
    description: str = Field(..., min_length=1, max_length=127,
                             description="商品描述（最多127字符）")


class WechatNativeRequest(BaseModel):
    """微信Native下单请求"""

    store_id: str = Field(..., description="门店ID（UUID）")
    order_id: str = Field(..., description="订单ID（UUID）")
    amount_fen: int = Field(..., gt=0, description="支付金额（分），必须大于0")
    description: str = Field(..., min_length=1, max_length=127,
                             description="商品描述（最多127字符）")


class AlipayRequest(BaseModel):
    """支付宝下单请求"""

    store_id: str = Field(..., description="门店ID（UUID）")
    order_id: str = Field(..., description="订单ID（UUID）")
    amount_fen: int = Field(..., gt=0, description="支付金额（分），必须大于0")
    subject: str = Field(..., min_length=1, max_length=256,
                         description="订单标题（最多256字符）")


class RefundRequest(BaseModel):
    """退款请求"""

    refund_amount_fen: int = Field(..., gt=0, description="退款金额（分），必须大于0")
    reason: str = Field(default="", max_length=80, description="退款原因（最多80字符）")


# ================================================================
# 微信支付端点（需要JWT认证）
# ================================================================


@router.post("/wechat/jsapi", summary="微信JSAPI下单")
async def create_wechat_jsapi_payment(
    body: WechatJsapiRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    微信JSAPI支付下单（适用于小程序、微信内H5）

    返回前端调起支付所需参数包（timeStamp / nonceStr / package / signType / paySign）。
    """
    svc = PaymentGatewayService(db)
    try:
        result = await svc.create_wechat_jsapi_order(
            store_id=body.store_id,
            order_id=body.order_id,
            amount_fen=body.amount_fen,
            openid=body.openid,
            description=body.description,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("微信JSAPI下单异常", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="微信支付下单失败，请稍后重试",
        )


@router.post("/wechat/native", summary="微信Native扫码下单")
async def create_wechat_native_payment(
    body: WechatNativeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    微信Native支付下单（扫码支付）

    返回 {payment_record_id, code_url}，前端据此生成二维码供用户扫描。
    """
    svc = PaymentGatewayService(db)
    try:
        result = await svc.create_wechat_native_order(
            store_id=body.store_id,
            order_id=body.order_id,
            amount_fen=body.amount_fen,
            description=body.description,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("微信Native下单异常", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="微信支付下单失败，请稍后重试",
        )


# ================================================================
# 支付回调端点（不需要JWT认证，微信/支付宝服务器直接调用）
# include_in_schema=False：不在 OpenAPI 文档中暴露
# ================================================================


@router.post("/wechat/callback", include_in_schema=False)
async def wechat_payment_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    微信支付回调端点（无需JWT认证）

    微信服务器通知支付结果。本端点：
    1. 验证签名（失败返回 400，微信将重试）
    2. 解密回调数据
    3. 更新DB支付状态
    4. 返回 {"code": "SUCCESS"} 告知微信已处理
    """
    headers = dict(request.headers)
    body = await request.body()
    callback_raw = body.decode("utf-8")

    svc = PaymentGatewayService(db)
    try:
        payment_result = await svc.verify_wechat_callback(headers, body)
        await svc.handle_wechat_payment_success(payment_result, callback_raw)
        await db.commit()
        logger.info(
            "微信支付回调处理成功",
            trade_state=payment_result.get("trade_state"),
            transaction_id=payment_result.get("transaction_id"),
        )
        return {"code": "SUCCESS", "message": "成功"}
    except ValueError as e:
        logger.warning("微信支付回调处理失败（验签或格式错误）", error=str(e))
        # 返回 400：微信收到非200/非{code:SUCCESS}时会重试
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FAIL", "message": str(e)},
        )
    except Exception as e:
        logger.error("微信支付回调系统异常", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "FAIL", "message": "系统错误"},
        )


@router.post("/alipay/callback", include_in_schema=False)
async def alipay_payment_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    支付宝异步通知端点（无需JWT认证）

    支付宝服务器通知支付结果。本端点：
    1. 验证签名（RSA2）—— 失败返回 "fail"
    2. 更新DB支付状态
    3. 返回纯文本 "success" 告知支付宝已处理
    """
    form_data = await request.form()
    form_dict = dict(form_data)

    svc = PaymentGatewayService(db)
    try:
        is_valid = await svc.verify_alipay_callback(form_dict)
        if not is_valid:
            logger.warning("支付宝回调验签失败")
            return "fail"

        trade_status = form_dict.get("trade_status", "")
        trade_no = form_dict.get("trade_no", "")       # 支付宝交易号
        out_trade_no = form_dict.get("out_trade_no", "")

        if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
            # 查找并更新对应的支付记录（按 out_trade_no 匹配）
            from sqlalchemy import select
            from src.models.payment_record import GatewayPaymentRecord, PaymentStatus

            stmt = select(GatewayPaymentRecord).where(
                GatewayPaymentRecord.third_party_trade_no == trade_no
            )
            result_db = await db.execute(stmt)
            existing = result_db.scalar_one_or_none()

            if existing and existing.status == PaymentStatus.PAID.value:
                # 幂等处理
                logger.info("支付宝回调幂等处理", trade_no=trade_no)
            elif existing:
                from datetime import datetime
                existing.status = PaymentStatus.PAID.value
                existing.third_party_trade_no = trade_no
                existing.paid_at = datetime.utcnow()
                existing.callback_raw = json.dumps(form_dict, ensure_ascii=False)
                await db.flush()

            await db.commit()
            logger.info("支付宝回调处理成功", trade_no=trade_no,
                        trade_status=trade_status)

        return "success"
    except Exception as e:
        logger.error("支付宝回调处理异常", error=str(e))
        return "fail"


# ================================================================
# 退款、查询（需要JWT认证）
# ================================================================


@router.post("/{payment_id}/refund", summary="申请退款")
async def refund_payment(
    payment_id: str,
    body: RefundRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    申请退款（支持部分退款）

    退款金额不能超过原始支付金额 - 已退款金额。
    根据原始支付方式自动路由到微信或支付宝退款接口。
    """
    svc = PaymentGatewayService(db)
    try:
        result = await svc.refund(
            payment_record_id=payment_id,
            refund_amount_fen=body.refund_amount_fen,
            reason=body.reason,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("退款申请异常", payment_id=payment_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="退款申请失败，请稍后重试",
        )


@router.get("/{payment_id}/status", summary="查询支付状态")
async def get_payment_status(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    查询指定支付记录的状态

    返回：payment_record_id / status / amount_fen / amount_yuan / paid_at 等
    """
    svc = PaymentGatewayService(db)
    try:
        return await svc.get_payment_status(payment_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/records", summary="支付记录列表")
async def list_payment_records(
    store_id: str = Query(..., description="门店ID"),
    page: int = Query(default=1, ge=1, description="页码（从1开始）"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数（最多100）"),
    status: Optional[str] = Query(default=None,
                                   description="状态过滤：pending/paid/refunding/refunded/failed/closed"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    查询指定门店的支付记录列表（分页）

    支持按状态筛选，按 created_at 倒序排列。
    """
    svc = PaymentGatewayService(db)
    return await svc.list_payment_records(
        store_id=store_id, page=page, page_size=page_size, status=status
    )
