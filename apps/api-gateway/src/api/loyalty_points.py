"""
积分与会员等级 API

POST /api/v1/points/earn                        — 消费得积分
POST /api/v1/points/redeem                      — 积分兑换抵扣
GET  /api/v1/points/{member_id}                 — 积分账户+等级
GET  /api/v1/points/{member_id}/history         — 积分历史
GET  /api/v1/points/level-config                — 等级配置
PUT  /api/v1/points/level-config/{level}        — 更新等级配置
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.loyalty_points_service import LoyaltyPointsService

router = APIRouter(prefix="/api/v1/points", tags=["积分与等级"])


# ── Request / Response Schemas ────────────────────────────────────────────────


class EarnPointsRequest(BaseModel):
    member_id: str = Field(..., description="会员ID")
    store_id: str = Field(..., description="门店ID")
    order_amount_fen: int = Field(..., gt=0, description="订单金额（分）")
    order_id: str = Field(..., description="订单ID")


class RedeemPointsRequest(BaseModel):
    member_id: str = Field(..., description="会员ID")
    points_to_use: int = Field(..., gt=0, description="兑换积分数量")
    order_id: str = Field(..., description="订单ID")


class UpsertLevelConfigRequest(BaseModel):
    store_id: str = Field(..., description="门店ID")
    level_name: Optional[str] = Field(None, description="等级显示名称")
    min_lifetime_points: Optional[int] = Field(None, ge=0, description="升级所需历史累计积分")
    points_rate: Optional[float] = Field(None, ge=0.1, le=10.0, description="积分倍率")
    discount_rate: Optional[float] = Field(None, ge=0.5, le=1.0, description="折扣率")
    birthday_bonus: Optional[int] = Field(None, ge=0, description="生日赠分")
    priority_reservation: Optional[bool] = Field(None, description="优先订台权益")
    is_active: Optional[bool] = Field(None, description="是否启用")


# ── 路由 ──────────────────────────────────────────────────────────────────────


@router.post("/earn", summary="消费得积分")
async def earn_points(
    body: EarnPointsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    消费得积分

    根据会员当前等级的积分倍率计算本次获得积分，
    消费满1元得1积分（默认），高等级享有更高倍率。
    自动检查并触发等级升级。
    """
    svc = LoyaltyPointsService(db)
    try:
        result = await svc.earn_points(
            member_id=body.member_id,
            store_id=body.store_id,
            order_amount_fen=body.order_amount_fen,
            order_id=body.order_id,
        )
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"积分操作失败: {e}")


@router.post("/redeem", summary="积分兑换抵扣")
async def redeem_points(
    body: RedeemPointsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    积分兑换

    100积分 = 1元 = 100分。积分不足时返回 400。
    返回本次抵扣金额（分）及剩余积分。
    """
    svc = LoyaltyPointsService(db)
    try:
        result = await svc.redeem_points(
            member_id=body.member_id,
            points_to_use=body.points_to_use,
            order_id=body.order_id,
        )
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"积分兑换失败: {e}")


@router.get("/level-config", summary="等级配置列表")
async def get_level_config(
    store_id: str = Query(..., description="门店ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取门店等级配置

    若门店无自定义配置，返回系统默认配置。
    """
    svc = LoyaltyPointsService(db)
    result = await svc.get_level_config(store_id=store_id)
    return {"success": True, "data": result}


@router.put("/level-config/{level}", summary="更新等级配置")
async def upsert_level_config(
    level: str,
    body: UpsertLevelConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    创建或更新指定等级的配置

    level 有效值：bronze / silver / gold / platinum / diamond
    """
    svc = LoyaltyPointsService(db)
    try:
        config_data = body.model_dump(exclude_none=True, exclude={"store_id"})
        result = await svc.upsert_level_config(
            store_id=body.store_id,
            level=level,
            config_data=config_data,
        )
        await db.commit()
        return {"success": True, "data": result}
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"更新等级配置失败: {e}")


@router.get("/{member_id}", summary="积分账户+等级")
async def get_account(
    member_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    查询积分账户及当前等级权益
    """
    svc = LoyaltyPointsService(db)
    result = await svc.get_account(member_id=member_id)
    return {"success": True, "data": result}


@router.get("/{member_id}/history", summary="积分历史")
async def get_history(
    member_id: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
):
    """
    查询积分流水历史（分页，按时间倒序）
    """
    svc = LoyaltyPointsService(db)
    result = await svc.get_history(
        member_id=member_id,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": result}
