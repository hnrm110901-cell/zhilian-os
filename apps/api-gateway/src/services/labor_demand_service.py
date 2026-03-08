"""
人力需求预测服务（LaborDemandService）— Phase 8 Step 2

职责：
  1. 根据历史客流预测目标日期/餐段的到店人数（±15% 精度目标）
  2. 基于客流推荐各岗位所需人数
  3. 生成 3 条可解释推理链（客流因子 / 历史同类日 / 节假日权重）
  4. 结果持久化到 labor_demand_forecasts（ON CONFLICT DO UPDATE）

预测策略（三档降级）：
  < 14天历史  → rule_based  （行业基准 × 星期/节假日权重）
  14-56天历史 → statistical （近4-8周同星期加权平均）
  ≥ 56天历史  → weighted    （近12周，距今越近权重越高）

岗位换算（行业经验值）：
  waiter   : 1人 / 18 客流（午/晚）；1人 / 15 客流（早）
  chef     : 1人 / 22 客流（午/晚）；1人 / 18 客流（早）
  cashier  : 1人 / 45 客流；最低 1 人
  manager  : 固定 1 人；客流 > 80 时配 2 人

离线降级（Rule 10）：DB 不可用时返回 rule_based 估算，不持久化。
SQL：全部使用 text() + :param 绑定（Rule L010/L011）。
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, List

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ─── 常量 ──────────────────────────────────────────────────────────────────────

# 节假日权重表（CN 法定节假日/调休）
# key: date 字符串 'YYYY-MM-DD'；value: (weight, label)
_CN_HOLIDAY_WEIGHTS: Dict[str, tuple] = {
    # 2025
    "2025-01-01": (1.20, "元旦"),
    "2025-01-28": (1.50, "春节前夕"),
    "2025-01-29": (1.35, "春节假期"),
    "2025-01-30": (1.35, "春节假期"),
    "2025-01-31": (1.30, "春节假期"),
    "2025-02-01": (1.30, "春节假期"),
    "2025-02-02": (1.25, "春节假期"),
    "2025-02-03": (1.25, "春节假期"),
    "2025-02-04": (1.20, "春节假期"),
    "2025-04-04": (1.20, "清明"),
    "2025-04-05": (1.20, "清明"),
    "2025-05-01": (1.20, "劳动节"),
    "2025-05-02": (1.15, "劳动节"),
    "2025-05-03": (1.15, "劳动节"),
    "2025-05-31": (1.20, "端午"),
    "2025-06-01": (1.20, "端午"),
    "2025-06-02": (1.15, "端午"),
    "2025-10-01": (1.35, "国庆黄金周"),
    "2025-10-02": (1.35, "国庆黄金周"),
    "2025-10-03": (1.30, "国庆黄金周"),
    "2025-10-04": (1.30, "国庆黄金周"),
    "2025-10-05": (1.25, "国庆黄金周"),
    "2025-10-06": (1.25, "国庆黄金周"),
    "2025-10-07": (1.20, "国庆黄金周"),
    # 2026（春节预估）
    "2026-01-01": (1.20, "元旦"),
    "2026-02-17": (1.50, "春节前夕"),
    "2026-02-18": (1.35, "春节假期"),
    "2026-02-19": (1.35, "春节假期"),
    "2026-02-20": (1.30, "春节假期"),
    "2026-02-21": (1.30, "春节假期"),
    "2026-02-22": (1.25, "春节假期"),
    "2026-02-23": (1.25, "春节假期"),
    "2026-02-24": (1.20, "春节假期"),
    "2026-04-05": (1.20, "清明"),
    "2026-05-01": (1.20, "劳动节"),
    "2026-05-02": (1.15, "劳动节"),
    "2026-05-03": (1.15, "劳动节"),
    "2026-10-01": (1.35, "国庆黄金周"),
    "2026-10-02": (1.35, "国庆黄金周"),
    "2026-10-03": (1.30, "国庆黄金周"),
    "2026-10-04": (1.30, "国庆黄金周"),
    "2026-10-05": (1.25, "国庆黄金周"),
    "2026-10-06": (1.25, "国庆黄金周"),
    "2026-10-07": (1.20, "国庆黄金周"),
}

# 餐段客流基准（行业参考：一家 40-60 座中档餐厅午/晚高峰）
_PERIOD_BASE_CUSTOMERS = {
    "morning": 25,
    "lunch":   55,
    "dinner":  70,
    "all_day": 120,
}

# 星期系数（0=周一 … 6=周日）
_DOW_FACTOR = {0: 0.85, 1: 0.88, 2: 0.90, 3: 0.92, 4: 1.05, 5: 1.25, 6: 1.20}

# 岗位换算规则 per meal_period：(customers_per_staff, min_headcount)
_POSITION_RATIOS: Dict[str, Dict[str, tuple]] = {
    "morning": {"waiter": (15, 2), "chef": (18, 1), "cashier": (40, 1), "manager": (999, 1)},
    "lunch":   {"waiter": (18, 2), "chef": (22, 1), "cashier": (45, 1), "manager": (999, 1)},
    "dinner":  {"waiter": (15, 2), "chef": (20, 1), "cashier": (40, 1), "manager": (999, 1)},
    "all_day": {"waiter": (25, 3), "chef": (28, 2), "cashier": (55, 1), "manager": (999, 1)},
}
_MANAGER_HIGH_THRESHOLD = 80  # 超过此客流时经理配 2 人


# ─── 服务类 ────────────────────────────────────────────────────────────────────

class LaborDemandService:
    """人力需求预测服务（全静态方法）"""

    # ── 主入口 ──────────────────────────────────────────────────────────────────

    @staticmethod
    async def forecast(
        store_id: str,
        forecast_date: date,
        meal_period: str,
        db: Optional[AsyncSession] = None,
        *,
        save: bool = True,
        weather_score: float = 1.0,
    ) -> dict:
        """
        预测指定门店/日期/餐段的客流和所需岗位人数。

        Args:
            store_id:      门店ID
            forecast_date: 预测目标日期
            meal_period:   餐段（morning/lunch/dinner/all_day）
            db:            异步数据库会话；为 None 时走 rule_based 离线降级
            save:          是否持久化到 labor_demand_forecasts
            weather_score: 天气影响系数（1.0=正常，0.85=恶劣，1.05=好天气）

        Returns:
            包含预测结果、岗位推荐、3条推理链、¥影响的 dict
        """
        if meal_period not in _PERIOD_BASE_CUSTOMERS:
            raise ValueError(f"meal_period 必须是 morning/lunch/dinner/all_day，收到: {meal_period}")

        log = logger.bind(store_id=store_id, date=str(forecast_date), period=meal_period)

        # 获取历史客流天数（决定使用哪档策略）
        history_days = await LaborDemandService._get_history_days(store_id, db)

        if history_days < 14:
            result = await LaborDemandService._rule_based(
                store_id, forecast_date, meal_period, weather_score
            )
        elif history_days < 56:
            result = await LaborDemandService._statistical(
                store_id, forecast_date, meal_period, weather_score, db, history_days
            )
        else:
            result = await LaborDemandService._weighted_historical(
                store_id, forecast_date, meal_period, weather_score, db
            )

        log.info(
            "labor_demand.forecast_done",
            basis=result["basis"],
            predicted_customers=result["predicted_customer_count"],
            total_headcount=result["total_headcount_needed"],
            confidence=result["confidence_score"],
        )

        if save and db is not None:
            await LaborDemandService._upsert_forecast(result, db)

        return result

    # ── 三档预测策略 ────────────────────────────────────────────────────────────

    @staticmethod
    async def _rule_based(
        store_id: str,
        forecast_date: date,
        meal_period: str,
        weather_score: float,
    ) -> dict:
        """基准规则预测（< 14天历史）：行业基准 × 星期系数 × 节假日权重"""
        base = _PERIOD_BASE_CUSTOMERS[meal_period]
        dow_factor = _DOW_FACTOR[forecast_date.weekday()]
        holiday_weight, holiday_label = _get_holiday_info(forecast_date)

        predicted = max(1, round(base * dow_factor * holiday_weight * weather_score))
        confidence = 0.40

        weekday_cn = _weekday_cn(forecast_date.weekday())
        reason_1 = (
            f"行业基准客流 {base} 人，{weekday_cn} 系数 {dow_factor:.2f}，"
            f"预测基准客流 {round(base * dow_factor)} 人（置信度低，历史数据不足14天）"
        )
        reason_2 = "历史数据不足，暂无同类日参考，建议以经验值为主"
        reason_3 = (
            f"节假日权重 {holiday_weight:.2f}（{holiday_label}），"
            f"天气系数 {weather_score:.2f}，最终预测 {predicted} 人"
        )

        return _build_result(
            store_id, forecast_date, meal_period,
            predicted, confidence, weather_score, holiday_weight, None,
            reason_1, reason_2, reason_3,
            basis="rule_based", model_version="v1.0-rule",
        )

    @staticmethod
    async def _statistical(
        store_id: str,
        forecast_date: date,
        meal_period: str,
        weather_score: float,
        db: Optional[AsyncSession],
        history_days: int,
    ) -> dict:
        """统计预测（14-56天历史）：近4-8周同星期/餐段加权平均"""
        if db is None:
            return await LaborDemandService._rule_based(
                store_id, forecast_date, meal_period, weather_score
            )

        try:
            lookback_weeks = 4 if history_days < 28 else 8
            start_lookback = forecast_date - timedelta(weeks=lookback_weeks)
            dow = forecast_date.weekday()
            period_start_h, period_end_h = _period_hours(meal_period)

            rows_result = await db.execute(
                text("""
                    SELECT
                        DATE(created_at)        AS order_date,
                        COUNT(DISTINCT id)      AS customer_count
                    FROM orders
                    WHERE store_id   = :sid
                      AND created_at >= :start
                      AND created_at  < :end
                      AND EXTRACT(DOW FROM created_at) = :dow
                      AND EXTRACT(HOUR FROM created_at) >= :ph_start
                      AND EXTRACT(HOUR FROM created_at) <  :ph_end
                    GROUP BY DATE(created_at)
                    ORDER BY order_date
                """),
                {
                    "sid":      store_id,
                    "start":    start_lookback,
                    "end":      forecast_date,
                    "dow":      _pg_dow(dow),
                    "ph_start": period_start_h,
                    "ph_end":   period_end_h,
                },
            )
            rows = rows_result.fetchall()

            if not rows:
                return await LaborDemandService._rule_based(
                    store_id, forecast_date, meal_period, weather_score
                )

            # 加权平均（最新周权重最高）
            n = len(rows)
            weights = list(range(1, n + 1))
            total_w = sum(weights)
            hist_avg = sum(
                int(r.customer_count) * w for r, w in zip(rows, weights)
            ) / total_w
            hist_avg_int = round(hist_avg)

            holiday_weight, holiday_label = _get_holiday_info(forecast_date)
            predicted_base = hist_avg * holiday_weight * weather_score

            recent_result = await db.execute(
                text("""
                    SELECT DATE(created_at) AS d, COUNT(DISTINCT id) AS c
                    FROM orders
                    WHERE store_id = :sid
                      AND created_at >= :start
                      AND created_at < :end
                      AND EXTRACT(HOUR FROM created_at) >= :ph_start
                      AND EXTRACT(HOUR FROM created_at) <  :ph_end
                    GROUP BY DATE(created_at)
                    ORDER BY d DESC
                    LIMIT 14
                """),
                {
                    "sid": store_id,
                    "start": forecast_date - timedelta(days=14),
                    "end": forecast_date,
                    "ph_start": period_start_h,
                    "ph_end": period_end_h,
                },
            )
            recent_rows = recent_result.fetchall()
            recent_series = [int(r.c) for r in recent_rows]
            recent7 = recent_series[:7]
            prev7 = recent_series[7:14]
            momentum = compute_momentum_factor(recent7, prev7)
            volatility_penalty = compute_volatility_penalty(recent_series)
            adjusted = apply_micro_event_adjustment(predicted_base, momentum, volatility_penalty)

            predicted = max(1, round(adjusted))
            confidence = 0.68 if history_days < 28 else 0.75

            weekday_cn = _weekday_cn(dow)
            reason_1 = (
                f"近 {lookback_weeks} 周{weekday_cn}同餐段均值 {hist_avg_int} 人"
                f"（共 {n} 个样本，加权平均）"
            )
            reason_2 = (
                f"历史最高 {max(int(r.customer_count) for r in rows)} 人，"
                f"最低 {min(int(r.customer_count) for r in rows)} 人，"
                f"波动区间 ±{round(abs(max(int(r.customer_count) for r in rows) - hist_avg_int))} 人"
            )
            reason_3 = (
                f"节假日权重 {holiday_weight:.2f}（{holiday_label}），"
                f"天气系数 {weather_score:.2f}，短期动量×{momentum:.2f}，"
                f"波动惩罚×{volatility_penalty:.2f}，最终预测 {predicted} 人"
            )

            return _build_result(
                store_id, forecast_date, meal_period,
                predicted, confidence, weather_score, holiday_weight, hist_avg_int,
                reason_1, reason_2, reason_3,
                basis="statistical", model_version="v1.0-stat",
            )

        except Exception as exc:
            logger.warning(
                "labor_demand.statistical_failed",
                store_id=store_id, error=str(exc),
            )
            return await LaborDemandService._rule_based(
                store_id, forecast_date, meal_period, weather_score
            )

    @staticmethod
    async def _weighted_historical(
        store_id: str,
        forecast_date: date,
        meal_period: str,
        weather_score: float,
        db: Optional[AsyncSession],
    ) -> dict:
        """
        加权历史预测（≥ 56天历史）：
        近12周同星期/餐段，距今越近权重越高（线性递增）。
        同时参考同店同月份历史均值做修正。
        """
        if db is None:
            return await LaborDemandService._rule_based(
                store_id, forecast_date, meal_period, weather_score
            )

        try:
            start_lookback = forecast_date - timedelta(weeks=12)
            dow = forecast_date.weekday()
            period_start_h, period_end_h = _period_hours(meal_period)

            rows_result = await db.execute(
                text("""
                    SELECT
                        DATE(created_at)        AS order_date,
                        COUNT(DISTINCT id)      AS customer_count,
                        EXTRACT(WEEK FROM created_at) AS week_num
                    FROM orders
                    WHERE store_id   = :sid
                      AND created_at >= :start
                      AND created_at  < :end
                      AND EXTRACT(DOW FROM created_at) = :dow
                      AND EXTRACT(HOUR FROM created_at) >= :ph_start
                      AND EXTRACT(HOUR FROM created_at) <  :ph_end
                    GROUP BY DATE(created_at), EXTRACT(WEEK FROM created_at)
                    ORDER BY order_date
                """),
                {
                    "sid":      store_id,
                    "start":    start_lookback,
                    "end":      forecast_date,
                    "dow":      _pg_dow(dow),
                    "ph_start": period_start_h,
                    "ph_end":   period_end_h,
                },
            )
            rows = rows_result.fetchall()

            if not rows:
                return await LaborDemandService._statistical(
                    store_id, forecast_date, meal_period, weather_score, db, 60
                )

            # 同月份历史均值（跨年同月，提升季节性感知）
            same_month_result = await db.execute(
                text("""
                    SELECT AVG(daily_count) AS monthly_avg
                    FROM (
                        SELECT DATE(created_at) AS d, COUNT(DISTINCT id) AS daily_count
                        FROM orders
                        WHERE store_id  = :sid
                          AND EXTRACT(MONTH FROM created_at) = :month
                          AND EXTRACT(HOUR FROM created_at) >= :ph_start
                          AND EXTRACT(HOUR FROM created_at) <  :ph_end
                          AND created_at < :end
                        GROUP BY DATE(created_at)
                    ) sub
                """),
                {
                    "sid":      store_id,
                    "month":    forecast_date.month,
                    "ph_start": period_start_h,
                    "ph_end":   period_end_h,
                    "end":      forecast_date,
                },
            )
            monthly_avg = float(same_month_result.scalar() or 0)

            n = len(rows)
            weights = list(range(1, n + 1))
            total_w = sum(weights)
            hist_avg = sum(
                int(r.customer_count) * w for r, w in zip(rows, weights)
            ) / total_w

            # 混合：70% 近期加权 + 30% 月份均值（如果月均有效）
            blended = hist_avg
            if monthly_avg > 0:
                blended = hist_avg * 0.70 + monthly_avg * 0.30

            holiday_weight, holiday_label = _get_holiday_info(forecast_date)
            predicted_base = blended * holiday_weight * weather_score

            recent_result = await db.execute(
                text("""
                    SELECT DATE(created_at) AS d, COUNT(DISTINCT id) AS c
                    FROM orders
                    WHERE store_id = :sid
                      AND created_at >= :start
                      AND created_at < :end
                      AND EXTRACT(HOUR FROM created_at) >= :ph_start
                      AND EXTRACT(HOUR FROM created_at) <  :ph_end
                    GROUP BY DATE(created_at)
                    ORDER BY d DESC
                    LIMIT 14
                """),
                {
                    "sid": store_id,
                    "start": forecast_date - timedelta(days=14),
                    "end": forecast_date,
                    "ph_start": period_start_h,
                    "ph_end": period_end_h,
                },
            )
            recent_rows = recent_result.fetchall()
            recent_series = [int(r.c) for r in recent_rows]
            recent7 = recent_series[:7]
            prev7 = recent_series[7:14]
            momentum = compute_momentum_factor(recent7, prev7)
            volatility_penalty = compute_volatility_penalty(recent_series)
            adjusted = apply_micro_event_adjustment(predicted_base, momentum, volatility_penalty)

            predicted = max(1, round(adjusted))
            confidence = 0.85

            weekday_cn = _weekday_cn(dow)
            hist_avg_int = round(hist_avg)
            reason_1 = (
                f"近12周{weekday_cn}同餐段加权均值 {hist_avg_int} 人"
                f"（{n} 个样本，权重从旧到新递增）"
            )
            reason_2 = (
                f"同月份历史客流均值 {round(monthly_avg)} 人，"
                f"混合修正后基准 {round(blended)} 人"
            )
            reason_3 = (
                f"节假日权重 {holiday_weight:.2f}（{holiday_label}），"
                f"天气系数 {weather_score:.2f}，短期动量×{momentum:.2f}，"
                f"波动惩罚×{volatility_penalty:.2f}，最终预测 {predicted} 人"
            )

            return _build_result(
                store_id, forecast_date, meal_period,
                predicted, confidence, weather_score, holiday_weight, hist_avg_int,
                reason_1, reason_2, reason_3,
                basis="weighted", model_version="v1.1-weighted-micro",
            )

        except Exception as exc:
            logger.warning(
                "labor_demand.weighted_failed",
                store_id=store_id, error=str(exc),
            )
            return await LaborDemandService._statistical(
                store_id, forecast_date, meal_period, weather_score, db, 60
            )

    # ── 批量预测（一次预测全天所有餐段） ───────────────────────────────────────

    @staticmethod
    async def forecast_all_periods(
        store_id: str,
        forecast_date: date,
        db: Optional[AsyncSession] = None,
        *,
        save: bool = True,
        weather_score: float = 1.0,
    ) -> dict:
        """
        一次性预测目标日期所有餐段（morning/lunch/dinner）。
        返回包含各餐段预测结果的汇总 dict。
        """
        periods = ["morning", "lunch", "dinner"]
        results = {}
        total_headcount = 0

        for period in periods:
            r = await LaborDemandService.forecast(
                store_id, forecast_date, period, db,
                save=save, weather_score=weather_score,
            )
            results[period] = r
            total_headcount += r["total_headcount_needed"]

        return {
            "store_id":       store_id,
            "forecast_date":  forecast_date.isoformat(),
            "weather_score":  weather_score,
            "periods":        results,
            "daily_peak_headcount": max(
                r["total_headcount_needed"] for r in results.values()
            ),
            "daily_total_headcount_slots": total_headcount,
        }

    # ── 内部工具方法 ────────────────────────────────────────────────────────────

    @staticmethod
    async def _get_history_days(
        store_id: str,
        db: Optional[AsyncSession],
    ) -> int:
        """查询门店有效历史客流天数（去重）"""
        if db is None:
            return 0
        try:
            result = await db.execute(
                text("""
                    SELECT COUNT(DISTINCT DATE(created_at)) AS days
                    FROM orders
                    WHERE store_id = :sid
                """),
                {"sid": store_id},
            )
            return int(result.scalar() or 0)
        except Exception as exc:
            logger.warning(
                "labor_demand.get_history_days_failed",
                store_id=store_id, error=str(exc),
            )
            return 0

    @staticmethod
    async def _upsert_forecast(result: dict, db: AsyncSession) -> None:
        """
        将预测结果 upsert 到 labor_demand_forecasts。
        ON CONFLICT (store_id, forecast_date, meal_period) → 更新所有字段。
        """
        try:
            await db.execute(
                text("""
                    INSERT INTO labor_demand_forecasts (
                        id, store_id, forecast_date, meal_period,
                        predicted_customer_count, predicted_revenue_yuan, confidence_score,
                        position_requirements, total_headcount_needed,
                        factor_holiday_weight, factor_weather_score, factor_historical_avg,
                        model_version, created_at, updated_at
                    ) VALUES (
                        gen_random_uuid(), :store_id, :forecast_date, :meal_period,
                        :predicted_customers, :predicted_revenue_yuan, :confidence,
                        CAST(:position_req AS JSON), :total_headcount,
                        :holiday_weight, :weather_score, :hist_avg,
                        :model_version, NOW(), NOW()
                    )
                    ON CONFLICT (store_id, forecast_date, meal_period)
                    DO UPDATE SET
                        predicted_customer_count = EXCLUDED.predicted_customer_count,
                        predicted_revenue_yuan   = EXCLUDED.predicted_revenue_yuan,
                        confidence_score         = EXCLUDED.confidence_score,
                        position_requirements    = EXCLUDED.position_requirements,
                        total_headcount_needed   = EXCLUDED.total_headcount_needed,
                        factor_holiday_weight    = EXCLUDED.factor_holiday_weight,
                        factor_weather_score     = EXCLUDED.factor_weather_score,
                        factor_historical_avg    = EXCLUDED.factor_historical_avg,
                        model_version            = EXCLUDED.model_version,
                        updated_at               = NOW()
                """),
                {
                    "store_id":              result["store_id"],
                    "forecast_date":         result["forecast_date"],
                    "meal_period":           result["meal_period"],
                    "predicted_customers":   result["predicted_customer_count"],
                    "predicted_revenue_yuan": result.get("predicted_revenue_yuan"),
                    "confidence":            result["confidence_score"],
                    "position_req":          _dict_to_json_str(result["position_requirements"]),
                    "total_headcount":       result["total_headcount_needed"],
                    "holiday_weight":        result["factor_holiday_weight"],
                    "weather_score":         result["factor_weather_score"],
                    "hist_avg":              result["factor_historical_avg"],
                    "model_version":         result["model_version"],
                },
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error(
                "labor_demand.upsert_failed",
                store_id=result["store_id"], error=str(exc),
            )
            raise


# ─── 纯函数工具（可单元测试） ──────────────────────────────────────────────────

def compute_position_requirements(
    predicted_customers: int,
    meal_period: str,
) -> Dict[str, int]:
    """
    根据预测客流和餐段，计算各岗位所需人数。

    Args:
        predicted_customers: 预测到店客流
        meal_period:         餐段（morning/lunch/dinner/all_day）

    Returns:
        {"waiter": N, "chef": N, "cashier": N, "manager": N}
    """
    period = meal_period if meal_period in _POSITION_RATIOS else "lunch"
    ratios = _POSITION_RATIOS[period]
    result: Dict[str, int] = {}

    for position, (ratio, min_count) in ratios.items():
        if position == "manager":
            result[position] = 2 if predicted_customers > _MANAGER_HIGH_THRESHOLD else 1
        else:
            raw = math.ceil(predicted_customers / ratio)
            result[position] = max(raw, min_count)

    return result


def get_holiday_weight(target_date: date) -> tuple:
    """
    返回 (weight: float, label: str)。
    未命中节假日表时：周末 1.10，工作日 1.00。
    """
    return _get_holiday_info(target_date)


def compute_momentum_factor(recent_counts: List[int], previous_counts: List[int]) -> float:
    """
    计算短期动量因子，限制在 [0.85, 1.15] 之间。
    recent 均值高于 previous 均值 -> >1.0，反之 <1.0。
    """
    if not recent_counts or not previous_counts:
        return 1.0

    recent_avg = sum(recent_counts) / len(recent_counts)
    prev_avg = sum(previous_counts) / len(previous_counts)
    if prev_avg <= 0:
        return 1.0

    raw = recent_avg / prev_avg
    return round(max(0.85, min(1.15, raw)), 3)


def compute_volatility_penalty(counts: List[int]) -> float:
    """
    基于样本波动率生成惩罚因子，范围 [0.90, 1.00]。
    波动越大，惩罚越强，避免过拟合尖峰。
    """
    if len(counts) < 4:
        return 1.0

    avg = sum(counts) / len(counts)
    if avg <= 0:
        return 1.0

    variance = sum((c - avg) ** 2 for c in counts) / len(counts)
    std = math.sqrt(variance)
    cv = std / avg  # 变异系数
    penalty = 1.0 - min(0.10, cv * 0.12)
    return round(max(0.90, min(1.00, penalty)), 3)


def apply_micro_event_adjustment(base_prediction: float, momentum_factor: float, volatility_penalty: float) -> float:
    """应用微事件修正。"""
    adjusted = float(base_prediction) * float(momentum_factor) * float(volatility_penalty)
    return max(1.0, adjusted)


# ─── 私有工具函数 ──────────────────────────────────────────────────────────────

def _get_holiday_info(target_date: date) -> tuple:
    key = target_date.strftime("%Y-%m-%d")
    if key in _CN_HOLIDAY_WEIGHTS:
        return _CN_HOLIDAY_WEIGHTS[key]
    if target_date.weekday() >= 5:
        return (1.10, "周末")
    return (1.00, "工作日")


def _period_hours(meal_period: str) -> tuple:
    """返回餐段的 (start_hour, end_hour) 整数对"""
    mapping = {
        "morning": (6,  11),
        "lunch":   (11, 15),
        "dinner":  (17, 22),
        "all_day": (6,  23),
    }
    return mapping.get(meal_period, (6, 23))


def _pg_dow(python_dow: int) -> int:
    """Python weekday（0=Mon）→ PostgreSQL DOW（0=Sun）"""
    return (python_dow + 1) % 7


def _weekday_cn(python_dow: int) -> str:
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return names[python_dow]


def _dict_to_json_str(d: dict) -> str:
    import json
    return json.dumps(d, ensure_ascii=False)


def _build_result(
    store_id: str,
    forecast_date: date,
    meal_period: str,
    predicted_customers: int,
    confidence: float,
    weather_score: float,
    holiday_weight: float,
    hist_avg: Optional[int],
    reason_1: str,
    reason_2: str,
    reason_3: str,
    *,
    basis: str,
    model_version: str,
) -> dict:
    """组装标准返回结构（被三档策略复用）"""
    positions = compute_position_requirements(predicted_customers, meal_period)
    total_headcount = sum(positions.values())

    return {
        "store_id":               store_id,
        "forecast_date":          forecast_date.isoformat(),
        "meal_period":            meal_period,
        "predicted_customer_count": predicted_customers,
        "predicted_revenue_yuan": None,          # 由上层业务按客单价填充
        "confidence_score":       round(confidence, 3),
        "position_requirements":  positions,
        "total_headcount_needed": total_headcount,
        "factor_holiday_weight":  round(holiday_weight, 3),
        "factor_weather_score":   round(weather_score, 3),
        "factor_historical_avg":  hist_avg,
        "model_version":          model_version,
        "basis":                  basis,
        # 3条推理链（直接供 StaffingAdvice.reason_1/2/3 使用）
        "reason_1": reason_1,
        "reason_2": reason_2,
        "reason_3": reason_3,
    }
