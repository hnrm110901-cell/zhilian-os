"""
商户管理 API — 商户开通 / 列表 / 详情 / 更新 / 启停 / 门店 / 用户 / 配置聚合 / 渠道
所有端点仅 ADMIN 可用
"""

import uuid
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.dependencies import require_role
from src.models.channel_config import SalesChannelConfig
from src.models.user import User, UserRole
from src.services import merchant_service

router = APIRouter(prefix="/merchants", tags=["merchants"])


# ── Pydantic Schemas ─────────────────────────────────────────────────────────


class GroupInfo(BaseModel):
    group_name: str
    legal_entity: str
    unified_social_credit_code: str
    industry_type: str = "chinese_formal"
    contact_person: str
    contact_phone: str
    address: Optional[str] = None


class BrandInfo(BaseModel):
    brand_name: str
    cuisine_type: str = "chinese_formal"
    avg_ticket_yuan: Optional[float] = None
    target_food_cost_pct: float = 35.0
    target_labor_cost_pct: float = 25.0
    target_rent_cost_pct: Optional[float] = None
    target_waste_pct: float = 3.0


class AdminInfo(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None


class MerchantOnboardRequest(BaseModel):
    group: GroupInfo
    brand: BrandInfo
    admin: AdminInfo


class MerchantUpdateRequest(BaseModel):
    brand_name: Optional[str] = None
    cuisine_type: Optional[str] = None
    avg_ticket_yuan: Optional[float] = None
    target_food_cost_pct: Optional[float] = None
    target_labor_cost_pct: Optional[float] = None
    target_rent_cost_pct: Optional[float] = None
    target_waste_pct: Optional[float] = None
    status: Optional[str] = None


class GroupUpdateRequest(BaseModel):
    group_name: Optional[str] = None
    legal_entity: Optional[str] = None
    unified_social_credit_code: Optional[str] = None
    industry_type: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None


class AddStoreRequest(BaseModel):
    store_name: str
    store_code: str
    city: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    seats: Optional[int] = None


class AddUserRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None
    role: str = "waiter"
    store_id: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/stats")
async def get_stats(
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """平台级商户统计数据"""
    return await merchant_service.get_merchant_stats(session)


@router.post("/onboard")
async def onboard_merchant(
    req: MerchantOnboardRequest,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """一站式开通商户：创建集团 + 品牌 + 管理员账号"""
    try:
        result = await merchant_service.onboard_merchant(
            session,
            group_name=req.group.group_name,
            legal_entity=req.group.legal_entity,
            unified_social_credit_code=req.group.unified_social_credit_code,
            industry_type=req.group.industry_type,
            contact_person=req.group.contact_person,
            contact_phone=req.group.contact_phone,
            address=req.group.address,
            brand_name=req.brand.brand_name,
            cuisine_type=req.brand.cuisine_type,
            avg_ticket_yuan=req.brand.avg_ticket_yuan,
            target_food_cost_pct=req.brand.target_food_cost_pct,
            target_labor_cost_pct=req.brand.target_labor_cost_pct,
            target_rent_cost_pct=req.brand.target_rent_cost_pct,
            target_waste_pct=req.brand.target_waste_pct,
            admin_username=req.admin.username,
            admin_email=req.admin.email,
            admin_password=req.admin.password,
            admin_full_name=req.admin.full_name,
        )
        await session.commit()
        return {"message": "商户开通成功", **result}
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=f"商户开通失败: {str(e)}")


@router.get("")
async def list_merchants(
    keyword: Optional[str] = Query(None, description="搜索关键词（品牌名/集团名/联系人/品牌ID）"),
    status: Optional[str] = Query(None, description="状态筛选: active/inactive"),
    cuisine_type: Optional[str] = Query(None, description="菜系筛选"),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """商户列表（支持搜索 + 状态/菜系筛选）"""
    return await merchant_service.list_merchants(
        session,
        keyword=keyword,
        status=status,
        cuisine_type=cuisine_type,
    )


@router.get("/{brand_id}")
async def get_merchant_detail(
    brand_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """商户详情"""
    detail = await merchant_service.get_merchant_detail(session, brand_id)
    if not detail:
        raise HTTPException(status_code=404, detail="商户不存在")
    return detail


@router.put("/{brand_id}")
async def update_merchant(
    brand_id: str,
    req: MerchantUpdateRequest,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """更新品牌设置"""
    result = await merchant_service.update_merchant(session, brand_id, **req.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=404, detail="商户不存在")
    await session.commit()
    return result


@router.put("/{brand_id}/group")
async def update_group(
    brand_id: str,
    req: GroupUpdateRequest,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """更新集团信息（通过品牌 ID 找到关联集团）"""
    detail = await merchant_service.get_merchant_detail(session, brand_id)
    if not detail:
        raise HTTPException(status_code=404, detail="商户不存在")
    group_id = detail["group"]["group_id"]
    result = await merchant_service.update_group(session, group_id, **req.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=404, detail="集团不存在")
    await session.commit()
    return result


@router.post("/{brand_id}/toggle-status")
async def toggle_merchant_status(
    brand_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """切换商户启用/停用"""
    result = await merchant_service.toggle_merchant_status(session, brand_id)
    if not result:
        raise HTTPException(status_code=404, detail="商户不存在")
    await session.commit()
    return result


@router.post("/{brand_id}/stores")
async def add_store(
    brand_id: str,
    req: AddStoreRequest,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """为商户添加门店"""
    try:
        result = await merchant_service.add_store_to_merchant(
            session,
            brand_id,
            store_name=req.store_name,
            store_code=req.store_code,
            city=req.city,
            district=req.district,
            address=req.address,
            seats=req.seats,
        )
        await session.commit()
        return result
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=f"添加门店失败: {str(e)}")


@router.delete("/{brand_id}/stores/{store_id}")
async def remove_store(
    brand_id: str,
    store_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """移除门店"""
    result = await merchant_service.remove_store(session, store_id)
    if not result:
        raise HTTPException(status_code=404, detail="门店不存在")
    await session.commit()
    return result


@router.post("/{brand_id}/users")
async def add_user(
    brand_id: str,
    req: AddUserRequest,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """为商户添加用户"""
    try:
        result = await merchant_service.add_user_to_merchant(
            session,
            brand_id,
            username=req.username,
            email=req.email,
            password=req.password,
            full_name=req.full_name,
            role=req.role,
            store_id=req.store_id,
        )
        await session.commit()
        return result
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=f"添加用户失败: {str(e)}")


@router.post("/{brand_id}/users/{user_id}/toggle-status")
async def toggle_user_status(
    brand_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """切换用户启用/禁用"""
    result = await merchant_service.toggle_user_status(session, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="用户不存在")
    await session.commit()
    return result


@router.delete("/{brand_id}/users/{user_id}")
async def remove_user(
    brand_id: str,
    user_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """移除用户"""
    result = await merchant_service.remove_user(session, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="用户不存在")
    await session.commit()
    return result


# ── 配置聚合 ─────────────────────────────────────────────────────────────────


@router.get("/{brand_id}/config-summary")
async def get_config_summary(
    brand_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """聚合返回 IM/Agent/渠道/门店/用户 配置状态"""
    from src.models.agent_config import AgentConfig
    from src.models.brand_im_config import BrandIMConfig

    detail = await merchant_service.get_merchant_detail(session, brand_id)
    if not detail:
        raise HTTPException(status_code=404, detail="商户不存在")

    # IM config
    im_result = await session.execute(select(BrandIMConfig).where(BrandIMConfig.brand_id == brand_id))
    im_config = im_result.scalar_one_or_none()
    im_summary = {
        "configured": im_config is not None,
        "platform": im_config.im_platform if im_config else None,
        "last_sync_status": im_config.last_sync_status if im_config else None,
        "last_sync_at": im_config.last_sync_at.isoformat() if im_config and im_config.last_sync_at else None,
    }

    # Agent configs
    agent_result = await session.execute(select(AgentConfig).where(AgentConfig.brand_id == brand_id))
    agents = agent_result.scalars().all()
    agent_summary = {
        "total": len(agents),
        "enabled": sum(1 for a in agents if a.is_enabled),
    }

    # Channels
    ch_result = await session.execute(select(SalesChannelConfig).where(SalesChannelConfig.brand_id == brand_id))
    channels = ch_result.scalars().all()

    return {
        "im": im_summary,
        "agents": agent_summary,
        "channels": {"count": len(channels)},
        "store_count": len(detail.get("stores", [])),
        "user_count": len(detail.get("users", [])),
    }


# ── 渠道配置 CRUD ────────────────────────────────────────────────────────────


class ChannelConfigRequest(BaseModel):
    channel: str
    platform_commission_pct: float = 0.0
    delivery_cost_fen: int = 0
    packaging_cost_fen: int = 0
    is_active: bool = True


@router.get("/{brand_id}/channels")
async def list_channels(
    brand_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """品牌下 SalesChannelConfig 列表"""
    result = await session.execute(select(SalesChannelConfig).where(SalesChannelConfig.brand_id == brand_id))
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "brand_id": r.brand_id,
            "channel": r.channel,
            "platform_commission_pct": float(r.platform_commission_pct) if r.platform_commission_pct else 0,
            "delivery_cost_fen": r.delivery_cost_fen or 0,
            "packaging_cost_fen": r.packaging_cost_fen or 0,
            "is_active": r.is_active,
        }
        for r in rows
    ]


@router.post("/{brand_id}/channels")
async def upsert_channel(
    brand_id: str,
    req: ChannelConfigRequest,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """创建/更新渠道配置"""
    # 检查是否已存在
    result = await session.execute(
        select(SalesChannelConfig).where(
            SalesChannelConfig.brand_id == brand_id,
            SalesChannelConfig.channel == req.channel,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.platform_commission_pct = Decimal(str(req.platform_commission_pct))
        existing.delivery_cost_fen = req.delivery_cost_fen
        existing.packaging_cost_fen = req.packaging_cost_fen
        existing.is_active = req.is_active
    else:
        existing = SalesChannelConfig(
            id=uuid.uuid4(),
            brand_id=brand_id,
            channel=req.channel,
            platform_commission_pct=Decimal(str(req.platform_commission_pct)),
            delivery_cost_fen=req.delivery_cost_fen,
            packaging_cost_fen=req.packaging_cost_fen,
            is_active=req.is_active,
        )
        session.add(existing)

    await session.commit()
    return {
        "id": str(existing.id),
        "brand_id": brand_id,
        "channel": existing.channel,
        "platform_commission_pct": float(existing.platform_commission_pct),
        "delivery_cost_fen": existing.delivery_cost_fen,
        "packaging_cost_fen": existing.packaging_cost_fen,
        "is_active": existing.is_active,
    }


@router.delete("/{brand_id}/channels/{channel_id}")
async def delete_channel(
    brand_id: str,
    channel_id: str,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
):
    """删除渠道配置"""
    result = await session.execute(
        select(SalesChannelConfig).where(
            SalesChannelConfig.id == uuid.UUID(channel_id),
            SalesChannelConfig.brand_id == brand_id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="渠道配置不存在")
    await session.delete(row)
    await session.commit()
    return {"message": "已删除"}
