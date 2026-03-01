"""
ARCH-003: 门店记忆层 — 数据模型

存储门店的运营模式记忆，包括高峰时段模式、员工基线、菜品健康度、异常模式。
使用 Redis JSON 存储（TTL 72小时），支持按需全量刷新。
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


# ==================== Pydantic 模型 ====================

class PeakHourPattern(BaseModel):
    """高峰时段模式"""
    hour: int = Field(..., ge=0, le=23, description="小时（0-23）")
    avg_orders: float = Field(..., ge=0, description="平均订单数")
    avg_revenue: float = Field(..., ge=0, description="平均营收（元）")
    avg_customers: float = Field(..., ge=0, description="平均客流量")
    is_peak: bool = Field(False, description="是否高峰时段")
    weight: float = Field(1.0, description="滚动加权系数")


class StaffProfile(BaseModel):
    """员工绩效基线"""
    staff_id: str
    name: Optional[str] = None
    avg_orders_per_shift: float = 0.0    # 每班次平均服务订单数
    avg_revenue_per_shift: float = 0.0   # 每班次平均营收
    attendance_rate: float = 1.0          # 出勤率
    complaint_rate: float = 0.0          # 投诉率
    sample_days: int = 0                  # 数据样本天数


class DishHealth(BaseModel):
    """菜品健康度"""
    sku_id: str
    name: Optional[str] = None
    trend_7d: float = 0.0           # 7日销量趋势（正=上升，负=下降）
    refund_rate: float = 0.0        # 7日退单率
    avg_daily_sales: float = 0.0    # 日均销量
    profit_margin: float = 0.0      # 毛利率
    is_healthy: bool = True         # 综合健康度判断


class AnomalyPattern(BaseModel):
    """异常模式记录"""
    pattern_type: str               # revenue_drop / staff_shortage / dish_refund_spike
    description: str
    first_seen: datetime
    occurrence_count: int = 1
    last_seen: datetime
    severity: str = "medium"        # low / medium / high


class StoreMemory(BaseModel):
    """门店记忆快照"""
    store_id: str
    brand_id: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    peak_patterns: List[PeakHourPattern] = Field(default_factory=list)
    staff_profiles: List[StaffProfile] = Field(default_factory=list)
    dish_health: List[DishHealth] = Field(default_factory=list)
    anomaly_patterns: List[AnomalyPattern] = Field(default_factory=list)

    # 元数据
    data_coverage_days: int = 0     # 数据覆盖天数
    confidence: str = "low"         # low / medium / high


# ==================== Redis 存储层 ====================

class StoreMemoryStore:
    """
    StoreMemory 的 Redis JSON 存储

    Key 格式: store_memory:{store_id}
    TTL: 72小时（3天）
    """

    REDIS_KEY_PREFIX = "store_memory:"
    DEFAULT_TTL = 72 * 3600  # 72小时

    def __init__(self, redis_client=None):
        self._redis = redis_client

    def _key(self, store_id: str) -> str:
        return f"{self.REDIS_KEY_PREFIX}{store_id}"

    async def load(self, store_id: str) -> Optional[StoreMemory]:
        """从 Redis 加载门店记忆"""
        if not self._redis:
            logger.debug("store_memory.redis_not_configured", store_id=store_id)
            return None

        try:
            raw = await self._redis.get(self._key(store_id))
            if not raw:
                return None
            data = json.loads(raw)
            return StoreMemory(**data)
        except Exception as e:
            logger.warning("store_memory.load_failed", store_id=store_id, error=str(e))
            return None

    async def save(self, memory: StoreMemory) -> bool:
        """保存门店记忆到 Redis"""
        if not self._redis:
            logger.debug("store_memory.redis_not_configured", store_id=memory.store_id)
            return False

        try:
            key = self._key(memory.store_id)
            raw = memory.model_dump_json()
            await self._redis.set(key, raw, ex=self.DEFAULT_TTL)
            logger.info("store_memory.saved", store_id=memory.store_id)
            return True
        except Exception as e:
            logger.error("store_memory.save_failed", store_id=memory.store_id, error=str(e))
            return False

    async def delete(self, store_id: str) -> bool:
        """删除门店记忆缓存"""
        if not self._redis:
            return False
        try:
            await self._redis.delete(self._key(store_id))
            return True
        except Exception as e:
            logger.warning("store_memory.delete_failed", store_id=store_id, error=str(e))
            return False
