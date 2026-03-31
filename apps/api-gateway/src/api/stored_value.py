"""
储值卡 API

POST /api/v1/stored-value/recharge              — 充值
POST /api/v1/stored-value/consume               — 消费扣款
GET  /api/v1/stored-value/{member_id}/balance   — 余额查询
GET  /api/v1/stored-value/{member_id}/transactions — 流水
POST /api/v1/stored-value/promotions            — 创建充值活动
GET  /api/v1/stored-value/promotions            — 活动列表
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.stored_value_service import StoredValueService

router = APIRouter(prefix="/api/v1/stored-value", tags=["储值卡"])


# ── Request / Response Schemas ────────────────────────────────────────────────


class RechargeRequest(BaseModel):
    member_id: str = Field(..., description="会员ID")
    store_id: str = Field(..., description="门店ID")
    amount_fen: int = Field(..., gt=0, description="充值金额（分）")
    payment_method: str = Field(..., description="支付方式（wechat/alipay/cash/card）")
    operator_id: str = Field(..., description="操作员ID")


class ConsumeRequest(BaseModel):
    member_id: str = Field(..., description="会员ID")
    store_id: str = Field(..., description="门店ID")
    amount_fen: int = Field(..., gt=0, description="消费金额（分）")
    order_id: str = Field(..., description="订单ID")
    use_gift_first: bool = Field(True, description="是否优先扣赠送金")


class CreatePromotionRequest(BaseModel):
    store_id: str = Field(..., description="门店ID")
    name: str = Field(..., description="活动名称")
    min_recharge_fen: int = Field(..., gt=0, description="充值门槛（分）")
    gift_amount_fen: int = Field(0, ge=0, description="固定赠送额（分）")
    gift_rate: float = Field(0.0, ge=0.0, le=1.0, description="比例赠送率（0.0~1.0）")
    valid_from: Optional[datetime] = Field(None, description="活动开始时间")
    valid_until: Optional[datetime] = Field(None, description="活动结束时间")


# ── 路由 ──────────────────────────────────────────────────────────────────────


@router.post("/recharge", summary="储值充值")
async def recharge(
    body: RechargeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    充值接口

    自动查找最优赠送规则，在同一事务内更新账户余额并写流水。
    返回充值后余额（分）及本次赠送金额（分）。
    """
    svc = StoredValueService(db)
    try:
        result = await svc.recharge(
            member_id=body.member_id,
            store_id=body.store_id,
            amount_fen=body.amount_fen,
            payment_method=body.payment_method,
            operator_id=body.operator_id,
        )
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"充值失败: {e}")


@router.post("/consume", summary="储值消费扣款")
async def consume(
    body: ConsumeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    消费扣款接口

    优先扣赠送金（use_gift_first=True），余额不足时返回 400。
    """
    svc = StoredValueService(db)
    try:
        result = await svc.consume(
            member_id=body.member_id,
            store_id=body.store_id,
            amount_fen=body.amount_fen,
            order_id=body.order_id,
            use_gift_first=body.use_gift_first,
        )
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"消费扣款失败: {e}")


@router.get("/{member_id}/balance", summary="余额查询")
async def get_balance(
    member_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    查询会员储值余额

    返回本金余额、赠送金余额及合计（均转换为元，2位小数）。
    """
    svc = StoredValueService(db)
    result = await svc.get_balance(member_id=member_id)
    return {"success": True, "data": result}


@router.get("/{member_id}/transactions", summary="储值流水")
async def get_transactions(
    member_id: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
):
    """
    查询会员储值流水（分页，按时间倒序）
    """
    svc = StoredValueService(db)
    result = await svc.get_transactions(
        member_id=member_id,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": result}


@router.post("/promotions", summary="创建充值活动")
async def create_promotion(
    body: CreatePromotionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    创建充值赠送活动

    支持固定赠送（gift_amount_fen）和比例赠送（gift_rate），两者可叠加。
    """
    svc = StoredValueService(db)
    try:
        result = await svc.create_promotion(
            store_id=body.store_id,
            name=body.name,
            min_recharge_fen=body.min_recharge_fen,
            gift_amount_fen=body.gift_amount_fen,
            gift_rate=body.gift_rate,
            valid_from=body.valid_from,
            valid_until=body.valid_until,
        )
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建活动失败: {e}")


@router.get("/promotions", summary="充值活动列表")
async def list_promotions(
    store_id: str = Query(..., description="门店ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取门店所有充值活动（含已停用）
    """
    svc = StoredValueService(db)
    result = await svc.list_promotions(store_id=store_id)
    return {"success": True, "data": result}
