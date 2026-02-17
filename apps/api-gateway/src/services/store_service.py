"""
Store Service
门店管理服务
"""
from typing import List, Optional, Dict
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from ..models.store import Store, StoreStatus
from ..models.user import User
from ..core.database import get_db_session
import structlog

logger = structlog.get_logger()


class StoreService:
    """门店服务"""

    async def create_store(
        self,
        id: str,
        name: str,
        code: str,
        address: Optional[str] = None,
        city: Optional[str] = None,
        district: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        manager_id: Optional[str] = None,
        region: Optional[str] = None,
        area: Optional[float] = None,
        seats: Optional[int] = None,
        floors: Optional[int] = 1,
        opening_date: Optional[str] = None,
        business_hours: Optional[dict] = None,
        **kwargs,
    ) -> Store:
        """创建门店"""
        async with get_db_session() as session:
            # 检查门店ID是否已存在
            stmt = select(Store).where(Store.id == id)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                raise ValueError(f"门店ID {id} 已存在")

            # 检查门店编码是否已存在
            stmt = select(Store).where(Store.code == code)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                raise ValueError(f"门店编码 {code} 已存在")

            store = Store(
                id=id,
                name=name,
                code=code,
                address=address,
                city=city,
                district=district,
                phone=phone,
                email=email,
                manager_id=manager_id,
                region=region,
                status=StoreStatus.ACTIVE.value,
                is_active=True,
                area=area,
                seats=seats,
                floors=floors,
                opening_date=opening_date,
                business_hours=business_hours or {},
                **kwargs,
            )

            session.add(store)
            await session.commit()
            await session.refresh(store)

            logger.info("门店创建成功", store_id=id, name=name)
            return store

    async def get_store(self, store_id: str) -> Optional[Store]:
        """获取门店信息"""
        async with get_db_session() as session:
            stmt = select(Store).where(Store.id == store_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_stores(
        self,
        region: Optional[str] = None,
        city: Optional[str] = None,
        status: Optional[StoreStatus] = None,
        is_active: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Store]:
        """获取门店列表"""
        async with get_db_session() as session:
            stmt = select(Store)

            # 过滤条件
            conditions = []
            if region:
                conditions.append(Store.region == region)
            if city:
                conditions.append(Store.city == city)
            if status:
                conditions.append(Store.status == status.value)
            if is_active is not None:
                conditions.append(Store.is_active == is_active)

            if conditions:
                stmt = stmt.where(and_(*conditions))

            # 排序和分页
            stmt = stmt.order_by(Store.created_at.desc()).limit(limit).offset(offset)

            result = await session.execute(stmt)
            return result.scalars().all()

    async def update_store(
        self,
        store_id: str,
        **kwargs,
    ) -> Optional[Store]:
        """更新门店信息"""
        async with get_db_session() as session:
            stmt = select(Store).where(Store.id == store_id)
            result = await session.execute(stmt)
            store = result.scalar_one_or_none()

            if not store:
                return None

            # 更新字段
            for key, value in kwargs.items():
                if hasattr(store, key) and value is not None:
                    setattr(store, key, value)

            await session.commit()
            await session.refresh(store)

            logger.info("门店信息更新成功", store_id=store_id)
            return store

    async def delete_store(self, store_id: str) -> bool:
        """删除门店(软删除)"""
        async with get_db_session() as session:
            stmt = select(Store).where(Store.id == store_id)
            result = await session.execute(stmt)
            store = result.scalar_one_or_none()

            if not store:
                return False

            store.is_active = False
            store.status = StoreStatus.CLOSED.value

            await session.commit()
            logger.info("门店已删除", store_id=store_id)
            return True

    async def get_store_count(
        self,
        region: Optional[str] = None,
        status: Optional[StoreStatus] = None,
    ) -> int:
        """获取门店数量"""
        async with get_db_session() as session:
            stmt = select(func.count(Store.id))

            conditions = []
            if region:
                conditions.append(Store.region == region)
            if status:
                conditions.append(Store.status == status.value)

            if conditions:
                stmt = stmt.where(and_(*conditions))

            result = await session.execute(stmt)
            return result.scalar()

    async def get_stores_by_region(self) -> Dict[str, List[Store]]:
        """按区域分组获取门店"""
        async with get_db_session() as session:
            stmt = select(Store).where(Store.is_active == True).order_by(Store.region, Store.name)
            result = await session.execute(stmt)
            stores = result.scalars().all()

            # 按区域分组
            stores_by_region = {}
            for store in stores:
                region = store.region or "未分配"
                if region not in stores_by_region:
                    stores_by_region[region] = []
                stores_by_region[region].append(store)

            return stores_by_region

    async def get_store_stats(self, store_id: str) -> Dict:
        """获取门店统计信息"""
        # TODO: 实现门店统计(营业额、客流量、员工数等)
        # 这里需要查询订单、员工等表
        async with get_db_session() as session:
            store = await self.get_store(store_id)
            if not store:
                return {}

            # 基础统计
            stats = {
                "store_id": store_id,
                "store_name": store.name,
                "status": store.status,
                "area": store.area,
                "seats": store.seats,
                # TODO: 添加实际业务数据统计
                "employee_count": 0,  # 从员工表查询
                "today_revenue": 0,  # 从订单表查询
                "today_customers": 0,  # 从订单表查询
                "monthly_revenue": 0,  # 从订单表查询
                "monthly_revenue_target": store.monthly_revenue_target,
            }

            return stats

    async def compare_stores(self, store_ids: List[str], metrics: List[str]) -> Dict:
        """对比多个门店的数据"""
        # TODO: 实现门店对比功能
        comparison = {
            "stores": [],
            "metrics": metrics,
            "data": {},
        }

        for store_id in store_ids:
            store = await self.get_store(store_id)
            if store:
                comparison["stores"].append({
                    "id": store.id,
                    "name": store.name,
                    "region": store.region,
                })

                # TODO: 查询实际业务数据
                for metric in metrics:
                    if metric not in comparison["data"]:
                        comparison["data"][metric] = {}
                    comparison["data"][metric][store_id] = 0  # 占位符

        return comparison


# 全局门店服务实例
store_service = StoreService()
