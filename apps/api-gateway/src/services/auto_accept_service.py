"""
外卖自动接单服务
根据策略（始终/时段/产能/手动）自动判断是否接单
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


class AcceptStrategy(str, Enum):
    """接单策略"""
    ALWAYS = "always"      # 始终自动接单
    HOURS = "hours"        # 指定时段自动接单
    CAPACITY = "capacity"  # 按产能自动接单
    MANUAL = "manual"      # 全部手动


@dataclass
class StoreAcceptConfig:
    """门店接单配置"""
    store_id: str = ""
    strategy: AcceptStrategy = AcceptStrategy.MANUAL
    # 时段策略参数
    auto_hours_start: time = time(10, 0)
    auto_hours_end: time = time(21, 0)
    # 产能策略参数
    max_concurrent_orders: int = 20     # 同时处理订单上限
    current_orders: int = 0
    # 黑名单时段（如午高峰不接外卖）
    blackout_periods: List[Tuple[time, time]] = field(default_factory=list)
    enabled: bool = True


class AutoAcceptService:
    """外卖自动接单服务"""

    def __init__(self):
        self._configs: Dict[str, StoreAcceptConfig] = {}

    def set_config(self, config: StoreAcceptConfig) -> StoreAcceptConfig:
        """设置门店接单配置"""
        self._configs[config.store_id] = config
        logger.info("设置接单策略", store_id=config.store_id, strategy=config.strategy.value)
        return config

    def get_config(self, store_id: str) -> StoreAcceptConfig:
        """获取配置，不存在则返回默认（手动）"""
        return self._configs.get(store_id, StoreAcceptConfig(store_id=store_id))

    def should_auto_accept(
        self,
        store_id: str,
        check_time: Optional[datetime] = None,
    ) -> Dict:
        """
        判断是否应自动接单
        返回: {"accept": bool, "reason": str, "strategy": str}
        """
        config = self.get_config(store_id)
        now = check_time or datetime.now(timezone.utc)
        current_time = now.time()

        if not config.enabled:
            return {"accept": False, "reason": "自动接单已关闭", "strategy": config.strategy.value}

        # 先检查黑名单时段
        if self.is_in_blackout(store_id, current_time):
            return {"accept": False, "reason": "当前在黑名单时段内", "strategy": config.strategy.value}

        if config.strategy == AcceptStrategy.ALWAYS:
            return {"accept": True, "reason": "始终自动接单", "strategy": "always"}

        if config.strategy == AcceptStrategy.MANUAL:
            return {"accept": False, "reason": "手动接单模式", "strategy": "manual"}

        if config.strategy == AcceptStrategy.HOURS:
            in_hours = config.auto_hours_start <= current_time <= config.auto_hours_end
            if in_hours:
                return {"accept": True, "reason": "在自动接单时段内", "strategy": "hours"}
            return {"accept": False, "reason": "不在自动接单时段", "strategy": "hours"}

        if config.strategy == AcceptStrategy.CAPACITY:
            cap_ok = self.check_capacity(store_id)
            if cap_ok["has_capacity"]:
                return {"accept": True, "reason": "产能充足", "strategy": "capacity"}
            return {"accept": False, "reason": f"产能已满({config.current_orders}/{config.max_concurrent_orders})",
                     "strategy": "capacity"}

        return {"accept": False, "reason": "未知策略", "strategy": config.strategy.value}

    def check_capacity(self, store_id: str) -> Dict:
        """检查门店当前产能"""
        config = self.get_config(store_id)
        has_capacity = config.current_orders < config.max_concurrent_orders
        return {
            "store_id": store_id,
            "current_orders": config.current_orders,
            "max_concurrent": config.max_concurrent_orders,
            "has_capacity": has_capacity,
            "utilization": round(config.current_orders / max(1, config.max_concurrent_orders), 2),
        }

    def is_in_blackout(self, store_id: str, check_time: Optional[time] = None) -> bool:
        """检查当前是否在黑名单时段"""
        config = self.get_config(store_id)
        t = check_time or datetime.now(timezone.utc).time()
        for start, end in config.blackout_periods:
            if start <= t <= end:
                return True
        return False

    def update_current_orders(self, store_id: str, count: int) -> None:
        """更新当前在处理的订单数"""
        config = self.get_config(store_id)
        config.current_orders = max(0, count)
        self._configs[store_id] = config
