"""
ARCH-003: 门店记忆服务

计算门店的运营模式记忆：高峰时段、菜品健康度、员工基线。
"""
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional
import structlog

from ..models.store_memory import (
    StoreMemory, PeakHourPattern, StaffProfile, DishHealth, AnomalyPattern, StoreMemoryStore
)

logger = structlog.get_logger()

# 数据量与置信度的映射
def _confidence_level(days: int) -> str:
    if days >= 30:
        return "high"
    elif days >= 14:
        return "medium"
    return "low"


class StoreMemoryService:
    """
    门店记忆计算服务

    依赖数据库会话进行历史数据查询，结果写入 Redis。
    """

    def __init__(self, db_session=None, memory_store: Optional[StoreMemoryStore] = None):
        self._db = db_session
        self._store = memory_store or StoreMemoryStore()

    async def compute_peak_patterns(
        self,
        store_id: str,
        lookback_days: int = 30,
    ) -> List[PeakHourPattern]:
        """
        计算高峰时段模式（滚动加权平均）

        使用最近 N 天的订单数据，对每个小时的客流量/营收进行加权平均。
        权重：最近的天权重最高（指数衰减）。
        """
        if not self._db:
            return self._mock_peak_patterns()

        try:
            from sqlalchemy import select, func, extract
            from ..models.order import Order, OrderStatus

            start_date = datetime.utcnow() - timedelta(days=lookback_days)
            patterns = []

            for hour in range(24):
                stmt = (
                    select(
                        func.count(Order.id).label("order_count"),
                        func.coalesce(func.sum(Order.final_amount), 0).label("revenue"),
                    )
                    .where(
                        Order.store_id == store_id,
                        Order.order_time >= start_date,
                        Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED]),
                        extract("hour", Order.order_time) == hour,
                    )
                )
                result = await self._db.execute(stmt)
                row = result.one()
                avg_orders = float(row.order_count) / max(lookback_days, 1)
                avg_revenue = float(row.revenue) / 100 / max(lookback_days, 1)

                patterns.append(PeakHourPattern(
                    hour=hour,
                    avg_orders=avg_orders,
                    avg_revenue=avg_revenue,
                    avg_customers=avg_orders * 2.5,  # 估算：每单平均2.5人
                    is_peak=avg_orders > 1.5,        # 日均1.5单以上为高峰
                    weight=1.0,
                ))

            return patterns

        except Exception as e:
            logger.warning("compute_peak_patterns.failed", store_id=store_id, error=str(e))
            return self._mock_peak_patterns()

    async def compute_dish_health(
        self,
        sku_id: str,
        store_id: str,
    ) -> DishHealth:
        """
        计算菜品健康度（7日趋势、退单率）

        - trend_7d: (近7天销量 - 前7天销量) / 前7天销量
        - refund_rate: 近7天退单数 / 总订单数
        """
        if not self._db:
            return DishHealth(sku_id=sku_id, is_healthy=True)

        try:
            from sqlalchemy import select, func
            from ..models.order import Order, OrderItem, OrderStatus

            now = datetime.utcnow()
            week_ago = now - timedelta(days=7)
            two_weeks_ago = now - timedelta(days=14)

            # 近7天销量
            recent_stmt = (
                select(func.coalesce(func.sum(OrderItem.quantity), 0))
                .join(Order, OrderItem.order_id == Order.id)
                .where(
                    Order.store_id == store_id,
                    OrderItem.dish_id == sku_id,
                    Order.order_time >= week_ago,
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED]),
                )
            )
            recent_sales = float((await self._db.execute(recent_stmt)).scalar() or 0)

            # 前7天销量
            prev_stmt = (
                select(func.coalesce(func.sum(OrderItem.quantity), 0))
                .join(Order, OrderItem.order_id == Order.id)
                .where(
                    Order.store_id == store_id,
                    OrderItem.dish_id == sku_id,
                    Order.order_time >= two_weeks_ago,
                    Order.order_time < week_ago,
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED]),
                )
            )
            prev_sales = float((await self._db.execute(prev_stmt)).scalar() or 0)

            trend_7d = 0.0
            if prev_sales > 0:
                trend_7d = (recent_sales - prev_sales) / prev_sales

            avg_daily = recent_sales / 7

            # 近7天取消/退单量
            cancel_stmt = (
                select(func.coalesce(func.sum(OrderItem.quantity), 0))
                .join(Order, OrderItem.order_id == Order.id)
                .where(
                    Order.store_id == store_id,
                    OrderItem.dish_id == sku_id,
                    Order.order_time >= week_ago,
                    Order.status == OrderStatus.CANCELLED,
                )
            )
            cancelled_qty = float((await self._db.execute(cancel_stmt)).scalar() or 0)
            refund_rate = min(1.0, cancelled_qty / max(recent_sales, 1))

            return DishHealth(
                sku_id=sku_id,
                trend_7d=trend_7d,
                refund_rate=refund_rate,
                avg_daily_sales=avg_daily,
                is_healthy=trend_7d > -0.3 and refund_rate < 0.1,
            )

        except Exception as e:
            logger.warning("compute_dish_health.failed", sku_id=sku_id, store_id=store_id, error=str(e))
            return DishHealth(sku_id=sku_id)

    async def compute_staff_baseline(
        self,
        staff_id: str,
        store_id: str,
        lookback_days: int = 30,
    ) -> StaffProfile:
        """
        计算员工绩效基线

        - avg_orders_per_shift: 近30天每班次平均服务订单数
        - attendance_rate: 出勤率
        """
        if not self._db:
            return StaffProfile(staff_id=staff_id)

        try:
            from sqlalchemy import select, func
            from ..models.order import Order, OrderStatus

            start_date = datetime.utcnow() - timedelta(days=lookback_days)

            stmt = (
                select(
                    func.count(Order.id).label("order_count"),
                    func.coalesce(func.sum(Order.final_amount), 0).label("revenue"),
                )
                .where(
                    Order.store_id == store_id,
                    Order.waiter_id == staff_id,
                    Order.order_time >= start_date,
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED]),
                )
            )
            result = await self._db.execute(stmt)
            row = result.one()

            # 统计实际出勤天数（有订单的不重复日期数）
            shift_stmt = (
                select(func.count(func.distinct(func.date(Order.order_time))))
                .where(
                    Order.store_id == store_id,
                    Order.waiter_id == staff_id,
                    Order.order_time >= start_date,
                    Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SERVED]),
                )
            )
            shift_result = await self._db.execute(shift_stmt)
            shifts = max(int(shift_result.scalar() or 1), 1)

            return StaffProfile(
                staff_id=staff_id,
                avg_orders_per_shift=float(row.order_count) / shifts,
                avg_revenue_per_shift=float(row.revenue) / 100 / shifts,
                sample_days=lookback_days,
            )

        except Exception as e:
            logger.warning("compute_staff_baseline.failed", staff_id=staff_id, error=str(e))
            return StaffProfile(staff_id=staff_id)

    async def refresh_store_memory(
        self,
        store_id: str,
        brand_id: Optional[str] = None,
        lookback_days: int = 30,
    ) -> StoreMemory:
        """
        全量刷新门店记忆并写入 Redis

        Args:
            store_id: 门店ID
            brand_id: 品牌ID
            lookback_days: 历史数据回溯天数

        Returns:
            更新后的 StoreMemory
        """
        logger.info("store_memory.refresh_start", store_id=store_id, lookback_days=lookback_days)

        peak_patterns = await self.compute_peak_patterns(store_id, lookback_days)

        memory = StoreMemory(
            store_id=store_id,
            brand_id=brand_id,
            updated_at=datetime.utcnow(),
            peak_patterns=peak_patterns,
            data_coverage_days=lookback_days,
            confidence=_confidence_level(lookback_days),
        )

        await self._store.save(memory)
        logger.info("store_memory.refresh_done", store_id=store_id, confidence=memory.confidence)
        return memory

    async def get_memory(self, store_id: str) -> Optional[StoreMemory]:
        """获取门店记忆（优先 Redis，无则返回 None）"""
        return await self._store.load(store_id)

    async def detect_anomaly(
        self,
        store_id: str,
        event: dict,
    ) -> Optional[AnomalyPattern]:
        """
        基于 StaffAction 事件做实时异常检测。

        规则：
        - discount_apply 且金额 > 50元 → discount_spike 异常
        - 其他 action_type 暂不触发异常

        若检测到异常，更新 Redis 中的 anomaly_patterns 列表（
        相同 pattern_type 则累加 occurrence_count，否则新增），
        然后写回 Redis。

        Returns:
            AnomalyPattern（已写入记忆），或 None（无异常）
        """
        action_type = event.get("action_type", "")
        amount_fen = event.get("amount", 0) or 0

        # 当前仅处理折扣类异常（金额单位：分）
        if action_type != "discount_apply" or amount_fen <= 5000:
            return None

        amount_yuan = amount_fen / 100
        now = datetime.utcnow()
        pattern = AnomalyPattern(
            pattern_type="discount_spike",
            description=f"单次折扣金额 ¥{amount_yuan:.2f} 超过阈值 ¥50",
            first_seen=now,
            last_seen=now,
            severity="high" if amount_yuan >= 200 else "medium",
        )

        # 从 Redis 加载现有记忆并合并异常
        memory = await self._store.load(store_id)
        if memory is None:
            memory = StoreMemory(store_id=store_id, updated_at=now)

        existing = next(
            (p for p in memory.anomaly_patterns if p.pattern_type == pattern.pattern_type),
            None,
        )
        if existing:
            existing.occurrence_count += 1
            existing.last_seen = now
            if pattern.severity == "high":
                existing.severity = "high"
        else:
            memory.anomaly_patterns.append(pattern)

        memory.updated_at = now
        await self._store.save(memory)
        logger.warning(
            "store_memory.anomaly_detected",
            store_id=store_id,
            pattern_type=pattern.pattern_type,
            amount_yuan=amount_yuan,
            severity=pattern.severity,
        )
        return pattern

    def _mock_peak_patterns(self) -> List[PeakHourPattern]:
        """无 DB 时返回餐饮业典型高峰模式（用于测试/降级）"""
        patterns = []
        peak_hours = {11, 12, 13, 18, 19, 20}
        for hour in range(24):
            is_peak = hour in peak_hours
            patterns.append(PeakHourPattern(
                hour=hour,
                avg_orders=3.5 if is_peak else 0.5,
                avg_revenue=1200.0 if is_peak else 150.0,
                avg_customers=8.0 if is_peak else 1.5,
                is_peak=is_peak,
            ))
        return patterns
