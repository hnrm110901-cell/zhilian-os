"""
商户开通服务 — 一站式创建集团+品牌+管理员账号 + 完整 CRUD
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.security import get_password_hash
from src.models.organization import Brand, Group
from src.models.store import Store
from src.models.user import User, UserRole


async def onboard_merchant(
    session: AsyncSession,
    *,
    group_name: str,
    legal_entity: str,
    unified_social_credit_code: str,
    industry_type: str,
    contact_person: str,
    contact_phone: str,
    address: Optional[str] = None,
    brand_name: str,
    cuisine_type: str,
    avg_ticket_yuan: Optional[float] = None,
    target_food_cost_pct: float,
    target_labor_cost_pct: float,
    target_rent_cost_pct: Optional[float] = None,
    target_waste_pct: float,
    admin_username: str,
    admin_email: str,
    admin_password: str,
    admin_full_name: Optional[str] = None,
) -> dict:
    """一个事务内创建 Group + Brand + User(admin)"""
    group_id = f"GRP_{uuid.uuid4().hex[:8].upper()}"
    brand_id = f"BRD_{uuid.uuid4().hex[:8].upper()}"

    group = Group(
        group_id=group_id,
        group_name=group_name,
        legal_entity=legal_entity,
        unified_social_credit_code=unified_social_credit_code,
        industry_type=industry_type,
        contact_person=contact_person,
        contact_phone=contact_phone,
        address=address,
    )
    session.add(group)

    brand = Brand(
        brand_id=brand_id,
        group_id=group_id,
        brand_name=brand_name,
        cuisine_type=cuisine_type,
        avg_ticket_yuan=avg_ticket_yuan,
        target_food_cost_pct=target_food_cost_pct,
        target_labor_cost_pct=target_labor_cost_pct,
        target_rent_cost_pct=target_rent_cost_pct,
        target_waste_pct=target_waste_pct,
        status="active",
    )
    session.add(brand)

    admin_user = User(
        id=uuid.uuid4(),
        username=admin_username,
        email=admin_email,
        hashed_password=get_password_hash(admin_password),
        full_name=admin_full_name or admin_username,
        role=UserRole.STORE_MANAGER,
        is_active=True,
        brand_id=brand_id,
    )
    session.add(admin_user)

    await session.flush()

    return {
        "group_id": group_id,
        "brand_id": brand_id,
        "admin_user_id": str(admin_user.id),
    }


async def get_merchant_stats(session: AsyncSession) -> dict:
    """平台级商户统计"""
    total_brands = (await session.execute(select(func.count(Brand.brand_id)))).scalar() or 0
    active_brands = (await session.execute(select(func.count(Brand.brand_id)).where(Brand.status == "active"))).scalar() or 0
    total_stores = (await session.execute(select(func.count(Store.id)))).scalar() or 0
    active_stores = (await session.execute(select(func.count(Store.id)).where(Store.status == "active"))).scalar() or 0
    total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
    active_users = (await session.execute(select(func.count(User.id)).where(User.is_active.is_(True)))).scalar() or 0
    total_groups = (await session.execute(select(func.count(Group.group_id)))).scalar() or 0

    return {
        "total_merchants": total_brands,
        "active_merchants": active_brands,
        "inactive_merchants": total_brands - active_brands,
        "total_stores": total_stores,
        "active_stores": active_stores,
        "total_users": total_users,
        "active_users": active_users,
        "total_groups": total_groups,
    }


async def list_merchants(
    session: AsyncSession,
    *,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    cuisine_type: Optional[str] = None,
) -> list[dict]:
    """品牌列表 + 集团名 + 门店数 + 用户数（支持搜索/筛选）"""
    store_count_sq = select(func.count(Store.id)).where(Store.brand_id == Brand.brand_id).correlate(Brand).scalar_subquery()
    user_count_sq = select(func.count(User.id)).where(User.brand_id == Brand.brand_id).correlate(Brand).scalar_subquery()

    stmt = select(
        Brand.brand_id,
        Brand.brand_name,
        Brand.cuisine_type,
        Brand.status,
        Brand.avg_ticket_yuan,
        Brand.created_at,
        Group.group_id,
        Group.group_name,
        Group.contact_person,
        Group.contact_phone,
        store_count_sq.label("store_count"),
        user_count_sq.label("user_count"),
    ).join(Group, Group.group_id == Brand.group_id)

    if keyword:
        like_pat = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                Brand.brand_name.ilike(like_pat),
                Group.group_name.ilike(like_pat),
                Group.contact_person.ilike(like_pat),
                Brand.brand_id.ilike(like_pat),
            )
        )
    if status:
        stmt = stmt.where(Brand.status == status)
    if cuisine_type:
        stmt = stmt.where(Brand.cuisine_type == cuisine_type)

    stmt = stmt.order_by(Brand.created_at.desc())
    result = await session.execute(stmt)
    rows = result.all()
    return [
        {
            "brand_id": r.brand_id,
            "brand_name": r.brand_name,
            "cuisine_type": r.cuisine_type,
            "status": r.status,
            "avg_ticket_yuan": float(r.avg_ticket_yuan) if r.avg_ticket_yuan else None,
            "group_id": r.group_id,
            "group_name": r.group_name,
            "contact_person": r.contact_person,
            "contact_phone": r.contact_phone,
            "store_count": r.store_count or 0,
            "user_count": r.user_count or 0,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def get_merchant_detail(session: AsyncSession, brand_id: str) -> Optional[dict]:
    """品牌详情 + 门店列表 + 用户列表"""
    stmt = select(Brand, Group).join(Group, Group.group_id == Brand.group_id).where(Brand.brand_id == brand_id)
    result = await session.execute(stmt)
    row = result.first()
    if not row:
        return None

    brand, group = row

    stores_result = await session.execute(select(Store).where(Store.brand_id == brand_id))
    stores = [
        {
            "id": s.id,
            "name": s.name,
            "code": s.code,
            "city": s.city,
            "district": s.district,
            "status": s.status,
            "address": s.address,
            "seats": s.seats,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in stores_result.scalars().all()
    ]

    users_result = await session.execute(select(User).where(User.brand_id == brand_id))
    users = [
        {
            "id": str(u.id),
            "username": u.username,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role.value if hasattr(u.role, "value") else u.role,
            "is_active": u.is_active,
            "store_id": u.store_id,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users_result.scalars().all()
    ]

    return {
        "brand_id": brand.brand_id,
        "brand_name": brand.brand_name,
        "cuisine_type": brand.cuisine_type,
        "avg_ticket_yuan": float(brand.avg_ticket_yuan) if brand.avg_ticket_yuan else None,
        "target_food_cost_pct": float(brand.target_food_cost_pct),
        "target_labor_cost_pct": float(brand.target_labor_cost_pct),
        "target_rent_cost_pct": float(brand.target_rent_cost_pct) if brand.target_rent_cost_pct else None,
        "target_waste_pct": float(brand.target_waste_pct),
        "logo_url": brand.logo_url,
        "status": brand.status,
        "created_at": brand.created_at.isoformat() if brand.created_at else None,
        "group": {
            "group_id": group.group_id,
            "group_name": group.group_name,
            "legal_entity": group.legal_entity,
            "unified_social_credit_code": group.unified_social_credit_code,
            "industry_type": group.industry_type,
            "contact_person": group.contact_person,
            "contact_phone": group.contact_phone,
            "address": group.address,
        },
        "stores": stores,
        "users": users,
    }


async def update_merchant(
    session: AsyncSession,
    brand_id: str,
    **kwargs,
) -> Optional[dict]:
    """更新品牌配置"""
    result = await session.execute(select(Brand).where(Brand.brand_id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        return None

    allowed_fields = {
        "brand_name",
        "cuisine_type",
        "avg_ticket_yuan",
        "target_food_cost_pct",
        "target_labor_cost_pct",
        "target_rent_cost_pct",
        "target_waste_pct",
        "status",
        "logo_url",
    }
    for key, value in kwargs.items():
        if key in allowed_fields and value is not None:
            setattr(brand, key, value)

    await session.flush()
    return {"brand_id": brand.brand_id, "updated": True}


async def update_group(
    session: AsyncSession,
    group_id: str,
    **kwargs,
) -> Optional[dict]:
    """更新集团信息"""
    result = await session.execute(select(Group).where(Group.group_id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        return None

    allowed_fields = {
        "group_name",
        "legal_entity",
        "unified_social_credit_code",
        "industry_type",
        "contact_person",
        "contact_phone",
        "address",
    }
    for key, value in kwargs.items():
        if key in allowed_fields and value is not None:
            setattr(group, key, value)

    await session.flush()
    return {"group_id": group.group_id, "updated": True}


async def toggle_merchant_status(session: AsyncSession, brand_id: str) -> Optional[dict]:
    """切换商户启用/停用状态"""
    result = await session.execute(select(Brand).where(Brand.brand_id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        return None

    new_status = "inactive" if brand.status == "active" else "active"
    brand.status = new_status
    await session.flush()
    return {"brand_id": brand_id, "status": new_status}


async def toggle_user_status(session: AsyncSession, user_id: str) -> Optional[dict]:
    """切换用户启用/禁用状态"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None

    user.is_active = not user.is_active
    await session.flush()
    return {"user_id": str(user.id), "is_active": user.is_active}


async def remove_store(session: AsyncSession, store_id: str) -> Optional[dict]:
    """删除门店"""
    result = await session.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        return None

    store_name = store.name
    await session.delete(store)
    await session.flush()
    return {"store_id": store_id, "name": store_name, "deleted": True}


async def remove_user(session: AsyncSession, user_id: str) -> Optional[dict]:
    """删除用户"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None

    username = user.username
    await session.delete(user)
    await session.flush()
    return {"user_id": user_id, "username": username, "deleted": True}


async def add_store_to_merchant(
    session: AsyncSession,
    brand_id: str,
    *,
    store_name: str,
    store_code: str,
    city: Optional[str] = None,
    district: Optional[str] = None,
    address: Optional[str] = None,
    seats: Optional[int] = None,
) -> dict:
    """为品牌添加门店"""
    store_id = f"STORE_{uuid.uuid4().hex[:8].upper()}"
    store = Store(
        id=store_id,
        name=store_name,
        code=store_code,
        brand_id=brand_id,
        city=city,
        district=district,
        address=address,
        seats=seats,
        status="active",
        is_active=True,
    )
    session.add(store)
    await session.flush()
    return {"store_id": store_id, "name": store_name}


async def add_user_to_merchant(
    session: AsyncSession,
    brand_id: str,
    *,
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    role: str = "waiter",
    store_id: Optional[str] = None,
) -> dict:
    """为品牌添加用户"""
    user = User(
        id=uuid.uuid4(),
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        full_name=full_name or username,
        role=UserRole(role),
        is_active=True,
        brand_id=brand_id,
        store_id=store_id,
    )
    session.add(user)
    await session.flush()
    return {"user_id": str(user.id), "username": username}
