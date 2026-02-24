"""
Prophet 时序预测服务

用 Facebook Prophet 替代手工乘法因子模型，实现：
- 营收/客流量多步预测（1-30天）
- 自动捕捉周季节性、年季节性
- 内置中国节假日效应
- 置信区间输出
- 模型持久化（Redis 缓存，避免每次重训）

降级策略：Prophet 未安装或数据不足时，回退到 EnhancedForecastService。
"""
import json
import os
import pickle
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# Prophet 需要至少这么多历史数据点才能训练
MIN_TRAINING_POINTS = int(os.getenv("PROPHET_MIN_POINTS", "14"))
# 模型缓存 TTL（秒），默认 6 小时
MODEL_CACHE_TTL = int(os.getenv("PROPHET_MODEL_CACHE_TTL", "21600"))


def _chinese_holidays_df():
    """生成中国节假日 DataFrame 供 Prophet 使用"""
    try:
        import pandas as pd
        holidays = []
        for year in range(2023, 2028):
            holidays += [
                {"holiday": "春节", "ds": f"{year}-01-01", "lower_window": -3, "upper_window": 7},
                {"holiday": "清明节", "ds": f"{year}-04-05", "lower_window": -1, "upper_window": 1},
                {"holiday": "劳动节", "ds": f"{year}-05-01", "lower_window": -1, "upper_window": 3},
                {"holiday": "端午节", "ds": f"{year}-06-10", "lower_window": -1, "upper_window": 1},
                {"holiday": "中秋节", "ds": f"{year}-09-15", "lower_window": -1, "upper_window": 1},
                {"holiday": "国庆节", "ds": f"{year}-10-01", "lower_window": -1, "upper_window": 7},
            ]
        return pd.DataFrame(holidays)
    except Exception:
        return None


class ProphetForecastService:
    """Prophet 时序预测服务"""

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        return self._redis

    def _cache_key(self, store_id: str, metric: str) -> str:
        return f"prophet:model:{store_id}:{metric}"

    async def _load_model(self, store_id: str, metric: str):
        """从 Redis 加载缓存的 Prophet 模型"""
        try:
            r = await self._get_redis()
            data = await r.get(self._cache_key(store_id, metric))
            if data:
                return pickle.loads(data)
        except Exception as e:
            logger.warning("Prophet 模型缓存读取失败", error=str(e))
        return None

    async def _save_model(self, store_id: str, metric: str, model) -> None:
        """将训练好的 Prophet 模型序列化到 Redis"""
        try:
            r = await self._get_redis()
            await r.setex(self._cache_key(store_id, metric), MODEL_CACHE_TTL, pickle.dumps(model))
        except Exception as e:
            logger.warning("Prophet 模型缓存写入失败", error=str(e))

    def _train(self, history: List[Dict[str, Any]], metric: str = "revenue"):
        """
        训练 Prophet 模型

        Args:
            history: [{"date": "2024-01-01", "value": 12345.0}, ...]
            metric:  "revenue" | "traffic"

        Returns:
            训练好的 Prophet 模型，或 None（数据不足/Prophet 未安装）
        """
        try:
            import pandas as pd
            from prophet import Prophet
        except ImportError:
            logger.warning("Prophet 未安装，跳过训练")
            return None

        if len(history) < MIN_TRAINING_POINTS:
            logger.warning("历史数据不足，跳过 Prophet 训练", points=len(history), required=MIN_TRAINING_POINTS)
            return None

        df = pd.DataFrame([
            {"ds": pd.to_datetime(r["date"]), "y": float(r["value"])}
            for r in history
        ]).dropna()

        if len(df) < MIN_TRAINING_POINTS:
            return None

        holidays = _chinese_holidays_df()
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            holidays=holidays,
            interval_width=0.95,
            changepoint_prior_scale=float(os.getenv("PROPHET_CHANGEPOINT_SCALE", "0.05")),
        )
        model.fit(df)
        return model

    async def forecast(
        self,
        store_id: str,
        history: List[Dict[str, Any]],
        horizon_days: int = 7,
        metric: str = "revenue",
        retrain: bool = False,
    ) -> Dict[str, Any]:
        """
        预测未来 N 天的指标值

        Args:
            store_id:     门店ID
            history:      历史数据 [{"date": "YYYY-MM-DD", "value": float}]
            horizon_days: 预测天数（1-30）
            metric:       指标名称 (revenue / traffic / orders)
            retrain:      强制重训（忽略缓存）

        Returns:
            {
              "store_id": ...,
              "metric": ...,
              "horizon_days": ...,
              "forecasts": [{"date": "...", "predicted": ..., "lower": ..., "upper": ...}],
              "model": "prophet" | "fallback",
              "training_points": int,
            }
        """
        horizon_days = max(1, min(30, horizon_days))

        # 尝试加载缓存模型
        model = None if retrain else await self._load_model(store_id, metric)

        # 训练新模型
        if model is None:
            model = self._train(history, metric)
            if model is not None:
                await self._save_model(store_id, metric, model)

        if model is None:
            # 降级：用历史均值 + 简单趋势
            return self._fallback_forecast(store_id, history, horizon_days, metric)

        try:
            import pandas as pd
            future = model.make_future_dataframe(periods=horizon_days)
            forecast_df = model.predict(future)
            # 只取未来部分
            last_history_date = pd.to_datetime(max(r["date"] for r in history))
            future_rows = forecast_df[forecast_df["ds"] > last_history_date].tail(horizon_days)

            forecasts = [
                {
                    "date": row["ds"].strftime("%Y-%m-%d"),
                    "predicted": round(max(0, row["yhat"]), 2),
                    "lower": round(max(0, row["yhat_lower"]), 2),
                    "upper": round(max(0, row["yhat_upper"]), 2),
                }
                for _, row in future_rows.iterrows()
            ]

            logger.info("Prophet 预测完成", store_id=store_id, metric=metric, horizon=horizon_days)
            return {
                "store_id": store_id,
                "metric": metric,
                "horizon_days": horizon_days,
                "forecasts": forecasts,
                "model": "prophet",
                "training_points": len(history),
            }
        except Exception as e:
            logger.error("Prophet 预测失败，降级", error=str(e))
            return self._fallback_forecast(store_id, history, horizon_days, metric)

    def _fallback_forecast(
        self,
        store_id: str,
        history: List[Dict[str, Any]],
        horizon_days: int,
        metric: str,
    ) -> Dict[str, Any]:
        """降级预测：7日移动平均 + 线性趋势外推"""
        if not history:
            return {
                "store_id": store_id, "metric": metric, "horizon_days": horizon_days,
                "forecasts": [], "model": "fallback", "training_points": 0,
            }

        values = [float(r["value"]) for r in sorted(history, key=lambda x: x["date"])]
        window = values[-7:] if len(values) >= 7 else values
        base = sum(window) / len(window)

        # 简单线性趋势（最近14天 vs 前14天）
        if len(values) >= 14:
            recent = sum(values[-7:]) / 7
            older = sum(values[-14:-7]) / 7
            daily_trend = (recent - older) / 7
        else:
            daily_trend = 0.0

        last_date = date.fromisoformat(max(r["date"] for r in history))
        std = (sum((v - base) ** 2 for v in window) / len(window)) ** 0.5

        forecasts = []
        for i in range(1, horizon_days + 1):
            pred = max(0, base + daily_trend * i)
            forecasts.append({
                "date": (last_date + timedelta(days=i)).isoformat(),
                "predicted": round(pred, 2),
                "lower": round(max(0, pred - 1.96 * std), 2),
                "upper": round(pred + 1.96 * std, 2),
            })

        return {
            "store_id": store_id,
            "metric": metric,
            "horizon_days": horizon_days,
            "forecasts": forecasts,
            "model": "fallback",
            "training_points": len(history),
        }

    async def invalidate_model(self, store_id: str, metric: str) -> None:
        """清除门店指定指标的模型缓存（数据更新后调用）"""
        try:
            r = await self._get_redis()
            await r.delete(self._cache_key(store_id, metric))
            logger.info("Prophet 模型缓存已清除", store_id=store_id, metric=metric)
        except Exception as e:
            logger.warning("Prophet 模型缓存清除失败", error=str(e))


# Singleton
prophet_forecast_service = ProphetForecastService()
