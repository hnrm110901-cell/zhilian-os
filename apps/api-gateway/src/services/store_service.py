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
from ..services.pos_service import pos_service
from ..services.member_service import member_service
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
                "employee_count": 0,
                "today_revenue": 0,
                "today_customers": 0,
                "today_orders": 0,
                "monthly_revenue": 0,
                "monthly_revenue_target": store.monthly_revenue_target,
            }

            # 获取今日数据
            try:
                today = datetime.now().strftime("%Y-%m-%d")
                orders_result = await pos_service.query_orders(
                    begin_date=today,
                    end_date=today,
                    page_index=1,
                    page_size=1000,
                )
                orders = orders_result.get("orders", [])
                stats["today_orders"] = len(orders)
                stats["today_revenue"] = sum(order.get("realPrice", 0) for order in orders)
                stats["today_customers"] = sum(order.get("people", 0) for order in orders)
            except Exception as e:
                logger.warning("获取门店今日数据失败", store_id=store_id, error=str(e))

            # 获取本月数据
            try:
                month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
                month_end = datetime.now().strftime("%Y-%m-%d")
                month_orders_result = await pos_service.query_orders(
                    begin_date=month_start,
                    end_date=month_end,
                    page_index=1,
                    page_size=10000,
                )
                month_orders = month_orders_result.get("orders", [])
                stats["monthly_revenue"] = sum(order.get("realPrice", 0) for order in month_orders)
            except Exception as e:
                logger.warning("获取门店本月数据失败", store_id=store_id, error=str(e))

            return stats

    async def compare_stores(self, store_ids: List[str], metrics: List[str]) -> Dict:
        """对比多个门店的数据"""
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

                # 获取门店统计数据
                stats = await self.get_store_stats(store_id)

                for metric in metrics:
                    if metric not in comparison["data"]:
                        comparison["data"][metric] = {}

                    # 映射指标到统计数据
                    metric_value = 0
                    if metric == "revenue":
                        metric_value = stats.get("today_revenue", 0)
                    elif metric == "customers":
                        metric_value = stats.get("today_customers", 0)
                    elif metric == "orders":
                        metric_value = stats.get("today_orders", 0)
                    elif metric == "monthly_revenue":
                        metric_value = stats.get("monthly_revenue", 0)

                    comparison["data"][metric][store_id] = metric_value

        return comparison

    async def get_regional_summary(self) -> Dict:
        """获取区域汇总数据"""
        stores_by_region = await self.get_stores_by_region()

        regional_summary = {}
        for region, stores in stores_by_region.items():
            regional_summary[region] = {
                "store_count": len(stores),
                "active_stores": sum(1 for s in stores if s.is_active),
                "total_seats": sum(s.seats or 0 for s in stores),
                "total_area": sum(s.area or 0 for s in stores),
                "stores": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "city": s.city,
                        "status": s.status,
                    }
                    for s in stores
                ],
            }

        return regional_summary

    async def get_performance_ranking(self, metric: str = "revenue", limit: int = 10) -> List[Dict]:
        """获取门店业绩排名"""
        stores = await self.get_stores(is_active=True, limit=1000)

        store_performance = []
        for store in stores:
            stats = await self.get_store_stats(store.id)

            performance_value = 0
            if metric == "revenue":
                performance_value = stats.get("today_revenue", 0)
            elif metric == "customers":
                performance_value = stats.get("today_customers", 0)
            elif metric == "orders":
                performance_value = stats.get("today_orders", 0)
            elif metric == "monthly_revenue":
                performance_value = stats.get("monthly_revenue", 0)

            store_performance.append({
                "store_id": store.id,
                "store_name": store.name,
                "region": store.region,
                "city": store.city,
                "metric": metric,
                "value": performance_value,
            })

        # 按业绩排序
        store_performance.sort(key=lambda x: x["value"], reverse=True)

        # 添加排名
        for i, item in enumerate(store_performance[:limit]):
            item["rank"] = i + 1

        return store_performance[:limit]


# 全局门店服务实例
store_service = StoreService()
