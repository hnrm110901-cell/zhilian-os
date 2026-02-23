"""
易订适配器 - YiDing Adapter

实现智链OS统一接口,对接易订预订系统
"""

import os
import structlog
from typing import List, Optional

from .client import YiDingClient, YiDingAPIError
from .mapper import YiDingMapper
from .cache import YiDingCache
from .types import (
    YiDingConfig,
    UnifiedReservation,
    UnifiedCustomer,
    UnifiedTable,
    ReservationStats,
    CreateReservationDTO,
    UpdateReservationDTO,
    CreateCustomerDTO,
    UpdateCustomerDTO
)

logger = structlog.get_logger()


class YiDingAdapter:
    """
    易订适配器

    实现智链OS统一接口,提供:
    - 预订管理
    - 客户管理
    - 桌台管理
    - 统计分析
    """

    def __init__(self, config: YiDingConfig):
        """
        初始化易订适配器

        Args:
            config: 易订配置
        """
        self.config = config
        self.client = YiDingClient(config)
        self.mapper = YiDingMapper()
        self.cache = YiDingCache(ttl=config.get("cache_ttl", 300))

        self.logger = logger.bind(adapter="yiding")

    async def close(self):
        """关闭适配器"""
        await self.client.close()

    # ============================================
    # 系统信息 System Info
    # ============================================

    def get_system_name(self) -> str:
        """获取系统名称"""
        return "yiding"

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            是否健康
        """
        try:
            return await self.client.ping()
        except Exception as e:
            self.logger.error("health_check_failed", error=str(e))
            return False

    # ============================================
    # 预订管理 Reservation Management
    # ============================================

    async def create_reservation(
        self,
        data: CreateReservationDTO
    ) -> UnifiedReservation:
        """
        创建预订

        Args:
            data: 创建预订数据

        Returns:
            统一格式预订

        Raises:
            YiDingAPIError: API调用失败
        """
        self.logger.info("creating_reservation", data=data)

        try:
            # 1. 转换为易订格式
            yiding_data = self.mapper.to_yiding_reservation(data)

            # 2. 调用易订API
            response = await self.client.post("/api/reservations", json=yiding_data)

            # 3. 转换为统一格式
            unified = self.mapper.to_unified_reservation(response["data"])

            # 4. 清除相关缓存
            await self.cache.invalidate_reservations(
                data["store_id"],
                data["reservation_date"]
            )

            self.logger.info(
                "reservation_created",
                reservation_id=unified["id"],
                external_id=unified["external_id"]
            )

            return unified

        except YiDingAPIError as e:
            self.logger.error("create_reservation_failed", error=str(e))
            raise
        except Exception as e:
            self.logger.error("create_reservation_error", error=str(e))
            raise YiDingAPIError(f"创建预订失败: {str(e)}")

    async def get_reservation(self, reservation_id: str) -> UnifiedReservation:
        """
        查询预订详情

        Args:
            reservation_id: 预订ID

        Returns:
            统一格式预订
        """
        # 1. 尝试从缓存读取
        cached = await self.cache.get_reservation(reservation_id)
        if cached:
            self.logger.debug("reservation_cache_hit", reservation_id=reservation_id)
            return cached

        # 2. 调用易订API
        response = await self.client.get(f"/api/reservations/{reservation_id}")

        # 3. 转换并缓存
        unified = self.mapper.to_unified_reservation(response["data"])
        await self.cache.set_reservation(reservation_id, unified)

        return unified

    async def update_reservation(
        self,
        reservation_id: str,
        data: UpdateReservationDTO
    ) -> UnifiedReservation:
        """
        更新预订

        Args:
            reservation_id: 预订ID
            data: 更新数据

        Returns:
            更新后的预订
        """
        self.logger.info("updating_reservation", reservation_id=reservation_id)

        # 1. 转换为易订格式
        yiding_data = self.mapper.to_yiding_reservation_update(data)

        # 2. 调用易订API
        response = await self.client.put(
            f"/api/reservations/{reservation_id}",
            json=yiding_data
        )

        # 3. 转换并清除缓存
        unified = self.mapper.to_unified_reservation(response["data"])
        await self.cache.invalidate_reservation(reservation_id)

        return unified

    async def cancel_reservation(
        self,
        reservation_id: str,
        reason: Optional[str] = None
    ) -> None:
        """
        取消预订

        Args:
            reservation_id: 预订ID
            reason: 取消原因
        """
        self.logger.info("cancelling_reservation", reservation_id=reservation_id)

        await self.client.delete(
            f"/api/reservations/{reservation_id}",
            json={"reason": reason} if reason else None
        )

        await self.cache.invalidate_reservation(reservation_id)

    async def get_reservations(
        self,
        store_id: str,
        date: str
    ) -> List[UnifiedReservation]:
        """
        获取预订列表

        Args:
            store_id: 门店ID
            date: 日期 (YYYY-MM-DD)

        Returns:
            预订列表
        """
        # 1. 尝试从缓存读取
        cached = await self.cache.get_reservations(store_id, date)
        if cached:
            self.logger.debug("reservations_cache_hit", store_id=store_id, date=date)
            return cached

        # 2. 调用易订API
        response = await self.client.get(
            "/api/reservations/list",
            params={
                "store_id": store_id,
                "date": date,
                "page_size": int(os.getenv("YIDING_PAGE_SIZE", "1000"))
            }
        )

        # 3. 转换并缓存
        unified_list = [
            self.mapper.to_unified_reservation(item)
            for item in response["data"]["items"]
        ]

        await self.cache.set_reservations(store_id, date, unified_list)

        return unified_list

    # ============================================
    # 客户管理 Customer Management
    # ============================================

    async def get_customer_by_phone(
        self,
        phone: str
    ) -> Optional[UnifiedCustomer]:
        """
        根据手机号查询客户

        Args:
            phone: 手机号

        Returns:
            客户信息,不存在返回None
        """
        try:
            response = await self.client.get(f"/api/customers/phone/{phone}")

            if not response.get("data"):
                return None

            return self.mapper.to_unified_customer(response["data"])

        except YiDingAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def get_customer_by_id(self, customer_id: str) -> UnifiedCustomer:
        """
        根据ID查询客户

        Args:
            customer_id: 客户ID

        Returns:
            客户信息
        """
        response = await self.client.get(f"/api/customers/{customer_id}")
        return self.mapper.to_unified_customer(response["data"])

    async def create_customer(self, data: CreateCustomerDTO) -> UnifiedCustomer:
        """
        创建客户

        Args:
            data: 客户数据

        Returns:
            创建的客户
        """
        response = await self.client.post("/api/customers", json=data)
        return self.mapper.to_unified_customer(response["data"])

    async def update_customer(
        self,
        customer_id: str,
        data: UpdateCustomerDTO
    ) -> UnifiedCustomer:
        """
        更新客户

        Args:
            customer_id: 客户ID
            data: 更新数据

        Returns:
            更新后的客户
        """
        response = await self.client.put(
            f"/api/customers/{customer_id}",
            json=data
        )
        return self.mapper.to_unified_customer(response["data"])

    # ============================================
    # 桌台管理 Table Management
    # ============================================

    async def get_available_tables(
        self,
        store_id: str,
        date: str,
        time: str,
        party_size: int
    ) -> List[UnifiedTable]:
        """
        查询可用桌台

        Args:
            store_id: 门店ID
            date: 日期
            time: 时间
            party_size: 人数

        Returns:
            可用桌台列表
        """
        response = await self.client.get(
            "/api/tables/available",
            params={
                "store_id": store_id,
                "date": date,
                "time": time,
                "party_size": party_size
            }
        )

        return [
            self.mapper.to_unified_table(item)
            for item in response["data"]
        ]

    async def get_table_status(self, store_id: str) -> List[UnifiedTable]:
        """
        获取桌台状态

        Args:
            store_id: 门店ID

        Returns:
            桌台状态列表
        """
        response = await self.client.get(
            "/api/tables/status",
            params={"store_id": store_id}
        )

        return [
            self.mapper.to_unified_table(item)
            for item in response["data"]
        ]

    # ============================================
    # 统计分析 Statistics & Analytics
    # ============================================

    async def get_reservation_stats(
        self,
        store_id: str,
        start_date: str,
        end_date: str
    ) -> ReservationStats:
        """
        获取预订统计

        Args:
            store_id: 门店ID
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            预订统计
        """
        response = await self.client.get(
            "/api/stats/reservations",
            params={
                "store_id": store_id,
                "start_date": start_date,
                "end_date": end_date
            }
        )

        return self.mapper.to_reservation_stats(response["data"])
