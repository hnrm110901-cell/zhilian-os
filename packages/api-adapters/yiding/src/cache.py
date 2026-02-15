"""
易订缓存策略 - YiDing Cache Strategy

使用内存缓存提升性能,减少API调用
"""

import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import json

from .types import UnifiedReservation


class YiDingCache:
    """易订缓存管理器"""

    def __init__(self, ttl: int = 300):
        """
        初始化缓存

        Args:
            ttl: 缓存过期时间(秒),默认5分钟
        """
        self.ttl = ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def _is_expired(self, cache_entry: Dict[str, Any]) -> bool:
        """检查缓存是否过期"""
        expire_at = cache_entry.get("expire_at")
        if not expire_at:
            return True
        return datetime.now() > expire_at

    def _set_cache(self, key: str, value: Any, ttl: Optional[int] = None):
        """设置缓存"""
        expire_at = datetime.now() + timedelta(seconds=ttl or self.ttl)
        self._cache[key] = {
            "value": value,
            "expire_at": expire_at
        }

    def _get_cache(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if key not in self._cache:
            return None

        entry = self._cache[key]
        if self._is_expired(entry):
            del self._cache[key]
            return None

        return entry["value"]

    def _delete_cache(self, key: str):
        """删除缓存"""
        if key in self._cache:
            del self._cache[key]

    # ============================================
    # 预订缓存 Reservation Cache
    # ============================================

    async def get_reservation(
        self,
        reservation_id: str
    ) -> Optional[UnifiedReservation]:
        """获取预订缓存"""
        async with self._lock:
            key = f"reservation:{reservation_id}"
            return self._get_cache(key)

    async def set_reservation(
        self,
        reservation_id: str,
        reservation: UnifiedReservation,
        ttl: Optional[int] = None
    ):
        """设置预订缓存"""
        async with self._lock:
            key = f"reservation:{reservation_id}"
            self._set_cache(key, reservation, ttl)

    async def invalidate_reservation(self, reservation_id: str):
        """清除预订缓存"""
        async with self._lock:
            key = f"reservation:{reservation_id}"
            self._delete_cache(key)

    async def get_reservations(
        self,
        store_id: str,
        date: str
    ) -> Optional[List[UnifiedReservation]]:
        """获取预订列表缓存"""
        async with self._lock:
            key = f"reservations:{store_id}:{date}"
            return self._get_cache(key)

    async def set_reservations(
        self,
        store_id: str,
        date: str,
        reservations: List[UnifiedReservation],
        ttl: Optional[int] = None
    ):
        """设置预订列表缓存"""
        async with self._lock:
            key = f"reservations:{store_id}:{date}"
            self._set_cache(key, reservations, ttl)

    async def invalidate_reservations(self, store_id: str, date: str):
        """清除预订列表缓存"""
        async with self._lock:
            key = f"reservations:{store_id}:{date}"
            self._delete_cache(key)

            # 同时清除该日期下的所有单个预订缓存
            keys_to_delete = [
                k for k in self._cache.keys()
                if k.startswith("reservation:") and date in str(self._cache[k].get("value", {}))
            ]
            for key in keys_to_delete:
                self._delete_cache(key)

    # ============================================
    # 客户缓存 Customer Cache
    # ============================================

    async def get_customer(self, customer_id: str) -> Optional[Any]:
        """获取客户缓存"""
        async with self._lock:
            key = f"customer:{customer_id}"
            return self._get_cache(key)

    async def set_customer(
        self,
        customer_id: str,
        customer: Any,
        ttl: Optional[int] = None
    ):
        """设置客户缓存"""
        async with self._lock:
            key = f"customer:{customer_id}"
            self._set_cache(key, customer, ttl)

    async def invalidate_customer(self, customer_id: str):
        """清除客户缓存"""
        async with self._lock:
            key = f"customer:{customer_id}"
            self._delete_cache(key)

    # ============================================
    # 通用方法 General Methods
    # ============================================

    async def clear_all(self):
        """清除所有缓存"""
        async with self._lock:
            self._cache.clear()

    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        async with self._lock:
            total_keys = len(self._cache)
            expired_keys = sum(
                1 for entry in self._cache.values()
                if self._is_expired(entry)
            )

            return {
                "total_keys": total_keys,
                "active_keys": total_keys - expired_keys,
                "expired_keys": expired_keys
            }
