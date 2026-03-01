"""
FEAT-002: 预测性备料引擎

DemandForecaster.predict(store_id, target_date)

三档降级策略：
  < 14天历史  → rule_based （基于菜品均值 × 季节因子）
  < 60天历史  → statistical（移动加权平均）
  ≥ 60天历史  → ML（Prophet，需要安装 prophet 包）

ForecastResult 包含：confidence, basis, items（备料建议清单）
"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger()


@dataclass
class ForecastItem:
    """单品备料建议"""
    sku_id: str
    name: str
    unit: str
    suggested_quantity: float
    unit_price: Optional[float] = None
    reason: Optional[str] = None   # 为何建议此数量（如"同期上升20%"）


@dataclass
class ForecastResult:
    """预测结果"""
    store_id: str
    target_date: date
    estimated_revenue: float
    confidence: str          # low / medium / high
    basis: str               # rule_based / statistical / ml
    items: List[ForecastItem] = field(default_factory=list)
    note: Optional[str] = None   # 给用户的备注（如"数据积累中，建议参考近期经验"）


class DemandForecaster:
    """
    需求预测器（三档降级）

    依赖数据库获取历史数据，结果可选存库（通过 db_session）。
    """

    def __init__(self, db_session=None):
        self._db = db_session

    async def predict(
        self,
        store_id: str,
        target_date: date,
        brand_id: Optional[str] = None,
    ) -> ForecastResult:
        """
        预测目标日期的营收和备料需求

        Args:
            store_id: 门店ID
            target_date: 目标预测日期
            brand_id: 品牌ID（可选）

        Returns:
            ForecastResult
        """
        # 获取历史数据天数
        history_days = await self._get_history_days(store_id)

        logger.info(
            "demand_forecaster.predict",
            store_id=store_id,
            target_date=str(target_date),
            history_days=history_days,
        )

        # 三档降级
        if history_days < 14:
            return await self._rule_based(store_id, target_date, history_days)
        elif history_days < 60:
            return await self._statistical(store_id, target_date, history_days)
        else:
            return await self._ml_prophet(store_id, target_date, history_days)

    async def _get_history_days(self, store_id: str) -> int:
        """获取该门店的历史数据天数"""
        if not self._db:
            return 0  # 无 DB 时返回 0，走 rule_based

        try:
            from sqlalchemy import select, func, text
            from ..models.order import Order

            result = await self._db.execute(
                select(func.count(func.distinct(func.date(Order.created_at))))
                .where(Order.store_id == store_id)
            )
            return int(result.scalar() or 0)
        except Exception as e:
            logger.warning("get_history_days.failed", store_id=store_id, error=str(e))
            return 0

    async def _rule_based(
        self,
        store_id: str,
        target_date: date,
        history_days: int,
    ) -> ForecastResult:
        """
        规则基础预测（< 14天历史数据）

        使用行业基准数据：
        - 餐饮日均营收 ≈ 3000元（小店参考值）
        - 周末系数 1.3，工作日系数 1.0
        """
        is_weekend = target_date.weekday() >= 5
        base_revenue = 3000.0
        estimated = base_revenue * (1.3 if is_weekend else 1.0)

        items = await self._fetch_bom_items(store_id, estimated)

        return ForecastResult(
            store_id=store_id,
            target_date=target_date,
            estimated_revenue=estimated,
            confidence="low",
            basis="rule_based",
            items=items,
            note="数据积累中（历史数据不足14天），建议以近期经验为主。",
        )

    async def _statistical(
        self,
        store_id: str,
        target_date: date,
        history_days: int,
    ) -> ForecastResult:
        """
        统计预测（14-60天历史数据）：移动加权平均

        使用最近4周的同星期数据，加权计算（最近权重最高）。
        """
        if not self._db:
            return await self._rule_based(store_id, target_date, history_days)

        try:
            from sqlalchemy import select, func
            from ..models.order import Order

            day_of_week = target_date.weekday()
            lookback = min(history_days, 42)  # 最多6周
            start_date = target_date - timedelta(days=lookback)

            result = await self._db.execute(
                select(
                    func.date(Order.created_at).label("d"),
                    func.sum(Order.total_amount).label("revenue"),
                )
                .where(
                    Order.store_id == store_id,
                    func.date(Order.created_at) >= start_date,
                    func.date(Order.created_at) < target_date,
                    func.extract("dow", Order.created_at) == day_of_week,
                )
                .group_by("d")
                .order_by("d")
            )
            rows = result.all()

            if not rows:
                return await self._rule_based(store_id, target_date, history_days)

            # 加权移动平均（最新权重最高）
            n = len(rows)
            weights = [i + 1 for i in range(n)]
            total_weight = sum(weights)
            weighted_revenue = sum(
                float(row.revenue or 0) * w
                for row, w in zip(rows, weights)
            ) / total_weight

            items = await self._fetch_bom_items(store_id, weighted_revenue)

            return ForecastResult(
                store_id=store_id,
                target_date=target_date,
                estimated_revenue=weighted_revenue,
                confidence="medium",
                basis="statistical",
                items=items,
            )

        except Exception as e:
            logger.warning("statistical_forecast.failed", store_id=store_id, error=str(e))
            return await self._rule_based(store_id, target_date, history_days)

    async def _ml_prophet(
        self,
        store_id: str,
        target_date: date,
        history_days: int,
    ) -> ForecastResult:
        """
        ML预测（≥ 60天历史数据）：Facebook Prophet

        Prophet 不在标准依赖中，降级处理。
        """
        try:
            from prophet import Prophet
            import pandas as pd

            if not self._db:
                return await self._statistical(store_id, target_date, history_days)

            from sqlalchemy import select, func
            from ..models.order import Order

            result = await self._db.execute(
                select(
                    func.date(Order.created_at).label("ds"),
                    func.sum(Order.total_amount).label("y"),
                )
                .where(Order.store_id == store_id)
                .group_by("ds")
                .order_by("ds")
            )
            rows = result.all()

            if len(rows) < 30:
                return await self._statistical(store_id, target_date, history_days)

            df = pd.DataFrame([{"ds": str(r.ds), "y": float(r.y or 0)} for r in rows])
            df["ds"] = pd.to_datetime(df["ds"])

            model = Prophet(weekly_seasonality=True, daily_seasonality=False)
            model.fit(df)

            future = model.make_future_dataframe(periods=1, freq="D")
            forecast = model.predict(future)

            target_dt = pd.Timestamp(target_date)
            row = forecast[forecast["ds"] == target_dt]
            if row.empty:
                return await self._statistical(store_id, target_date, history_days)

            estimated = max(0.0, float(row["yhat"].iloc[0]))
            items = await self._fetch_bom_items(store_id, estimated)

            return ForecastResult(
                store_id=store_id,
                target_date=target_date,
                estimated_revenue=estimated,
                confidence="high",
                basis="ml",
                items=items,
            )

        except ImportError:
            logger.info("prophet_not_installed.fallback_to_statistical", store_id=store_id)
            return await self._statistical(store_id, target_date, history_days)
        except Exception as e:
            logger.warning("ml_prophet.failed", store_id=store_id, error=str(e))
            return await self._statistical(store_id, target_date, history_days)

    async def _fetch_bom_items(
        self, store_id: str, estimated_revenue: float
    ) -> List[ForecastItem]:
        """从 BOM 查询活跃配方，按预估营收缩放后返回备料建议。

        算法：
          1. 查询门店所有 is_active BOM 模板及对应菜品售价
          2. 均匀分配预估营收 → 每道菜份数 = estimated_revenue / avg_price / num_dishes
          3. 汇总各食材需求量（含 waste_factor 损耗）
          4. 按需求量降序返回

        无 DB、无 BOM 数据或发生异常时均返回空列表。
        """
        if not self._db:
            return []

        try:
            from collections import defaultdict
            from sqlalchemy import select
            from ..models.bom import BOMTemplate, BOMItem
            from ..models.inventory import InventoryItem
            from ..models.dish import Dish

            # 1. 活跃 BOM 模板 + 菜品售价
            bom_stmt = (
                select(BOMTemplate.id, Dish.price)
                .join(Dish, BOMTemplate.dish_id == Dish.id)
                .where(
                    BOMTemplate.store_id == store_id,
                    BOMTemplate.is_active.is_(True),
                )
            )
            bom_rows = (await self._db.execute(bom_stmt)).all()
            if not bom_rows:
                return []

            # 2. 估算每道菜份数（均匀分配）
            num_dishes = len(bom_rows)
            avg_price_fen = sum(int(r.price or 0) for r in bom_rows) / num_dishes
            avg_price_yuan = avg_price_fen / 100.0 if avg_price_fen > 0 else 50.0
            portions_per_dish = (estimated_revenue / avg_price_yuan) / num_dishes

            # 3. BOM 明细 + 食材名称/单位
            bom_ids = [str(r.id) for r in bom_rows]
            items_stmt = (
                select(
                    BOMItem.ingredient_id,
                    BOMItem.standard_qty,
                    BOMItem.unit,
                    BOMItem.waste_factor,
                    InventoryItem.name,
                )
                .join(InventoryItem, BOMItem.ingredient_id == InventoryItem.id)
                .where(BOMItem.bom_id.in_(bom_ids))
            )
            item_rows = (await self._db.execute(items_stmt)).all()

            # 4. 按食材汇总需求量（含损耗系数）
            totals: Dict[str, Dict] = defaultdict(
                lambda: {"name": "", "unit": "", "qty": 0.0}
            )
            for r in item_rows:
                waste = float(r.waste_factor or 0)
                qty = float(r.standard_qty or 0) * (1.0 + waste) * portions_per_dish
                totals[r.ingredient_id]["name"] = r.name
                totals[r.ingredient_id]["unit"] = r.unit or "kg"
                totals[r.ingredient_id]["qty"] += qty

            return sorted(
                [
                    ForecastItem(
                        sku_id=iid,
                        name=d["name"],
                        unit=d["unit"],
                        suggested_quantity=round(d["qty"], 2),
                        reason="基于BOM配方及预估营收",
                    )
                    for iid, d in totals.items()
                    if d["qty"] > 0
                ],
                key=lambda x: x.suggested_quantity,
                reverse=True,
            )

        except Exception as e:
            logger.warning(
                "demand_forecaster.fetch_bom_items_failed",
                store_id=store_id,
                error=str(e),
            )
            return []
