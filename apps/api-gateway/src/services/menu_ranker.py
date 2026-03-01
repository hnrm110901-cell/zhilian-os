"""
FEAT-004: 动态菜单权重引擎

MenuRanker.rank(store_id) → List[RankedDish]

5因子评分：
  趋势     30%  — 7日销量趋势（与前7日对比）
  毛利     25%  — 菜品毛利率
  库存     20%  — 库存充裕度（库存/预期用量）
  时段匹配 15%  — 当前时段（早/午/晚）的历史销售匹配度
  低退单   10%  — 7日退单率（越低越好）

Redis 缓存：TTL 5分钟（高频读场景，< 200ms 响应目标）
"""
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import structlog

from ..models.menu_rank import DishScore, RankedDish

logger = structlog.get_logger()

CACHE_TTL = 5 * 60  # 5分钟
CACHE_KEY_PREFIX = "menu_rank:"


def _current_time_slot() -> str:
    """返回当前时段：breakfast/lunch/dinner/off_peak"""
    hour = datetime.now().hour
    if 6 <= hour < 10:
        return "breakfast"
    elif 10 <= hour < 14:
        return "lunch"
    elif 17 <= hour < 21:
        return "dinner"
    return "off_peak"


class MenuRanker:
    """
    动态菜单权重引擎

    从数据库读取菜品销售/库存/毛利数据，计算5因子评分，
    按加权总分排序，返回 Top N 推荐菜品。
    """

    def __init__(self, db_session=None, redis_client=None):
        self._db = db_session
        self._redis = redis_client

    def _cache_key(self, store_id: str) -> str:
        return f"{CACHE_KEY_PREFIX}{store_id}"

    async def rank(
        self,
        store_id: str,
        limit: int = 10,
    ) -> List[RankedDish]:
        """
        计算并返回 Top N 推荐菜品

        Args:
            store_id: 门店ID
            limit: 返回条数

        Returns:
            List[RankedDish]，按 total_score 降序
        """
        # 优先读 Redis 缓存
        cached = await self._load_cache(store_id)
        if cached is not None:
            return cached[:limit]

        # 计算评分
        ranked = await self._compute_ranking(store_id)

        # 写入缓存
        await self._save_cache(store_id, ranked)

        return ranked[:limit]

    async def invalidate_cache(self, store_id: str) -> None:
        """手动使缓存失效"""
        if self._redis:
            await self._redis.delete(self._cache_key(store_id))

    async def _compute_ranking(self, store_id: str) -> List[RankedDish]:
        """核心评分计算"""
        if not self._db:
            return self._mock_ranking()

        try:
            dish_data = await self._fetch_dish_data(store_id)
            if not dish_data:
                return self._mock_ranking()

            time_slot = _current_time_slot()
            scored_dishes = []

            for dish in dish_data:
                score = DishScore(
                    dish_id=dish["dish_id"],
                    dish_name=dish["dish_name"],
                    trend_score=self._calc_trend_score(dish),
                    margin_score=self._calc_margin_score(dish),
                    stock_score=self._calc_stock_score(dish),
                    time_slot_score=self._calc_time_slot_score(dish, time_slot),
                    low_refund_score=self._calc_low_refund_score(dish),
                ).compute_total()

                highlight = self._generate_highlight(score, dish)

                scored_dishes.append(RankedDish(
                    rank=0,  # 排名在排序后重新赋值
                    dish_id=dish["dish_id"],
                    dish_name=dish["dish_name"],
                    category=dish.get("category"),
                    price=dish.get("price"),
                    score=score,
                    highlight=highlight,
                ))

            # 按总分降序排序
            scored_dishes.sort(key=lambda d: d.score.total_score, reverse=True)

            # 赋予排名
            for i, dish in enumerate(scored_dishes, start=1):
                dish.rank = i

            return scored_dishes

        except Exception as e:
            logger.error("menu_ranker.compute_failed", store_id=store_id, error=str(e))
            return self._mock_ranking()

    async def _fetch_dish_data(self, store_id: str) -> List[Dict[str, Any]]:
        """从数据库批量获取菜品及销售统计数据

        使用3条聚合查询替代逐菜品 N+1 查询：
          1. 各菜品近7天 / 前7天销量（趋势因子）
          2. 各菜品午市 / 晚市销量占比（时段因子）
          3. 各菜品近7天取消/退单量（低退单因子）
        """
        from sqlalchemy import select, func, case, extract
        from ..models.dish import Dish
        from ..models.order import Order, OrderItem, OrderStatus

        # 获取所有活跃菜品
        stmt = select(Dish).where(Dish.store_id == store_id, Dish.is_available == True)
        result = await self._db.execute(stmt)
        dishes = result.scalars().all()
        if not dishes:
            return []

        dish_ids = [str(d.id) for d in dishes]

        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        completed_statuses = [OrderStatus.COMPLETED.value, OrderStatus.SERVED.value]

        # ── Query 1: 近7天 & 前7天销量（一次查询，用 CASE 分组）──────────────────
        sales_stmt = (
            select(
                OrderItem.item_id,
                func.sum(
                    case(
                        (Order.order_time >= week_ago, OrderItem.quantity),
                        else_=0,
                    )
                ).label("recent_qty"),
                func.sum(
                    case(
                        (
                            (Order.order_time >= two_weeks_ago)
                            & (Order.order_time < week_ago),
                            OrderItem.quantity,
                        ),
                        else_=0,
                    )
                ).label("prev_qty"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.store_id == store_id,
                Order.order_time >= two_weeks_ago,
                Order.status.in_(completed_statuses),
                OrderItem.item_id.in_(dish_ids),
            )
            .group_by(OrderItem.item_id)
        )
        sales_rows = (await self._db.execute(sales_stmt)).all()
        sales_map = {r.item_id: (int(r.recent_qty or 0), int(r.prev_qty or 0)) for r in sales_rows}

        # ── Query 2: 时段销量（午市10-14点 / 晚市17-21点）──────────────────────
        slot_stmt = (
            select(
                OrderItem.item_id,
                func.sum(OrderItem.quantity).label("total_qty"),
                func.sum(
                    case(
                        (extract("hour", Order.order_time).between(10, 13), OrderItem.quantity),
                        else_=0,
                    )
                ).label("lunch_qty"),
                func.sum(
                    case(
                        (extract("hour", Order.order_time).between(17, 20), OrderItem.quantity),
                        else_=0,
                    )
                ).label("dinner_qty"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.store_id == store_id,
                Order.order_time >= week_ago,
                Order.status.in_(completed_statuses),
                OrderItem.item_id.in_(dish_ids),
            )
            .group_by(OrderItem.item_id)
        )
        slot_rows = (await self._db.execute(slot_stmt)).all()
        slot_map: Dict[str, Dict] = {}
        for r in slot_rows:
            total = int(r.total_qty or 0)
            slot_map[r.item_id] = {
                "lunch_pct": (int(r.lunch_qty or 0) / total) if total > 0 else 0.5,
                "dinner_pct": (int(r.dinner_qty or 0) / total) if total > 0 else 0.5,
            }

        # ── Query 3: 近7天取消订单量（退单率因子）──────────────────────────────
        cancel_stmt = (
            select(
                OrderItem.item_id,
                func.sum(OrderItem.quantity).label("cancelled_qty"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.store_id == store_id,
                Order.order_time >= week_ago,
                Order.status == OrderStatus.CANCELLED.value,
                OrderItem.item_id.in_(dish_ids),
            )
            .group_by(OrderItem.item_id)
        )
        cancel_rows = (await self._db.execute(cancel_stmt)).all()
        cancel_map = {r.item_id: int(r.cancelled_qty or 0) for r in cancel_rows}

        # ── 组装 dish_data ──────────────────────────────────────────────────────
        dish_data = []
        for dish in dishes:
            did = str(dish.id)
            recent_sales, prev_sales = sales_map.get(did, (0, 0))
            slot = slot_map.get(did, {"lunch_pct": 0.5, "dinner_pct": 0.5})
            cancelled = cancel_map.get(did, 0)
            total_recent = recent_sales or 1
            refund_rate = min(1.0, cancelled / total_recent)

            dish_data.append({
                "dish_id": did,
                "dish_name": dish.name,
                "category": dish.category,
                "price": dish.price,
                "cost": getattr(dish, "cost", 0) or 0,
                "current_stock": getattr(dish, "current_stock", 999),
                "min_stock": getattr(dish, "min_stock", 10),
                "recent_sales": recent_sales,
                "prev_sales": prev_sales,
                "refund_rate": refund_rate,
                "lunch_sales_pct": slot["lunch_pct"],
                "dinner_sales_pct": slot["dinner_pct"],
            })

        return dish_data

    def _calc_trend_score(self, dish: Dict) -> float:
        """趋势得分：(近7天 - 前7天) / 前7天，归一化到[0,1]"""
        recent = dish.get("recent_sales", 0)
        prev = dish.get("prev_sales", 0)
        if prev == 0:
            return 0.5  # 无历史数据，给中位分
        trend = (recent - prev) / max(prev, 1)
        # 归一化：[-1, +∞) → [0, 1]（trend=-100%时为0，trend=+100%时为~0.75）
        return float(min(1.0, max(0.0, 0.5 + trend * 0.5)))

    def _calc_margin_score(self, dish: Dict) -> float:
        """毛利得分：毛利率归一化"""
        price = float(dish.get("price", 0) or 0)
        cost = float(dish.get("cost", 0) or 0)
        if price <= 0:
            return 0.3
        margin_rate = (price - cost) / price
        return float(min(1.0, max(0.0, margin_rate)))

    def _calc_stock_score(self, dish: Dict) -> float:
        """库存得分：当前库存 / min_stock，超过3倍则满分"""
        stock = float(dish.get("current_stock", 999))
        min_stock = float(dish.get("min_stock", 10))
        if min_stock <= 0:
            return 1.0
        ratio = stock / min_stock
        if ratio >= 3.0:
            return 1.0
        elif ratio <= 0.5:
            return 0.0
        return float(min(1.0, (ratio - 0.5) / 2.5))

    def _calc_time_slot_score(self, dish: Dict, time_slot: str) -> float:
        """时段匹配得分：当前时段的历史销售占比"""
        if time_slot == "lunch":
            return float(dish.get("lunch_sales_pct", 0.5))
        elif time_slot == "dinner":
            return float(dish.get("dinner_sales_pct", 0.5))
        elif time_slot == "breakfast":
            return float(dish.get("breakfast_sales_pct", 0.3))
        return 0.3  # off_peak

    def _calc_low_refund_score(self, dish: Dict) -> float:
        """低退单得分：退单率越低分越高"""
        refund_rate = float(dish.get("refund_rate", 0.0))
        return float(max(0.0, 1.0 - refund_rate * 10))  # 退单率10%时得0分

    def _generate_highlight(self, score: DishScore, dish: Dict) -> Optional[str]:
        """生成推荐理由"""
        if score.trend_score >= 0.8:
            return "销量持续上升"
        elif score.margin_score >= 0.8:
            return "高毛利推荐"
        elif score.stock_score >= 0.9:
            return "库存充足"
        elif score.low_refund_score >= 0.9:
            return "顾客满意度高"
        return None

    def _mock_ranking(self) -> List[RankedDish]:
        """无 DB 时返回示例排名（降级）"""
        mock_dishes = [
            ("D001", "招牌红烧肉", 0.85, 0.80, 0.90, 0.75, 0.95),
            ("D002", "清蒸鲈鱼", 0.75, 0.85, 0.70, 0.80, 0.90),
            ("D003", "麻婆豆腐", 0.65, 0.75, 0.95, 0.85, 0.85),
        ]
        result = []
        for i, (dish_id, name, t, m, s, ts, lr) in enumerate(mock_dishes, start=1):
            score = DishScore(
                dish_id=dish_id, dish_name=name,
                trend_score=t, margin_score=m, stock_score=s,
                time_slot_score=ts, low_refund_score=lr,
            ).compute_total()
            result.append(RankedDish(rank=i, dish_id=dish_id, dish_name=name, score=score))
        return result

    async def _load_cache(self, store_id: str) -> Optional[List[RankedDish]]:
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(self._cache_key(store_id))
            if not raw:
                return None
            data = json.loads(raw)
            return [RankedDish(**d) for d in data]
        except Exception as e:
            logger.warning("menu_ranker.cache_load_failed", store_id=store_id, error=str(e))
            return None

    async def _save_cache(self, store_id: str, ranked: List[RankedDish]) -> None:
        if not self._redis:
            return
        try:
            raw = json.dumps([d.model_dump() for d in ranked], default=str)
            await self._redis.set(self._cache_key(store_id), raw, ex=CACHE_TTL)
        except Exception as e:
            logger.warning("menu_ranker.cache_save_failed", store_id=store_id, error=str(e))
