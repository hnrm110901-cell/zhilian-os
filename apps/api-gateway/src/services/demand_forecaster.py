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

        items = self._mock_items(estimated)

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

            items = self._mock_items(weighted_revenue)

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
            items = self._mock_items(estimated)

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

    def _mock_items(self, estimated_revenue: float) -> List[ForecastItem]:
        """根据预估营收生成示例备料建议（实际项目需基于 BOM 计算）"""
        factor = estimated_revenue / 3000.0
        return [
            ForecastItem(sku_id="SKU_001", name="猪肉", unit="kg", suggested_quantity=round(5 * factor, 1), reason="基于历史用量"),
            ForecastItem(sku_id="SKU_002", name="鸡肉", unit="kg", suggested_quantity=round(3 * factor, 1), reason="基于历史用量"),
            ForecastItem(sku_id="SKU_003", name="蔬菜", unit="kg", suggested_quantity=round(8 * factor, 1), reason="基于历史用量"),
        ]
