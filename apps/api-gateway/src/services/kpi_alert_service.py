"""
KPI 食材成本率告警服务（KPI Alert Service）

功能：
  1. 从 KPI 表读取用户在 AlertThresholdsPage 配置的食材成本率阈值
  2. 调用 FoodCostService 获取各门店近期实际成本率
  3. 对比阈值，生成 warning / critical 告警
  4. 通过企业微信发送告警消息

Rule 6 兼容：告警消息包含 ¥ 金额
Rule 7 兼容：每条告警包含动作建议 + ¥ 影响 + 置信度
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.food_cost_service import FoodCostService
from src.models.kpi import KPI

logger = structlog.get_logger()

# 系统默认阈值（未在 AlertThresholdsPage 配置时的兜底值）
_DEFAULT_WARNING_PCT  = float(os.getenv("FOOD_COST_WARNING_THRESHOLD",  "32"))
_DEFAULT_CRITICAL_PCT = float(os.getenv("FOOD_COST_CRITICAL_THRESHOLD", "35"))

# 默认回望窗口（天）
_DEFAULT_LOOKBACK_DAYS = int(os.getenv("FOOD_COST_ALERT_LOOKBACK_DAYS", "7"))

# 趋势告警：回望天数和向前预测天数
_TREND_LOOKBACK_DAYS  = int(os.getenv("FOOD_COST_TREND_LOOKBACK_DAYS", "14"))
_TREND_FORECAST_DAYS  = int(os.getenv("FOOD_COST_TREND_FORECAST_DAYS", "7"))


# ── 纯函数：告警级别判断 ──────────────────────────────────────────────────────

def classify_alert(
    actual_pct: float,
    warning_threshold: float,
    critical_threshold: float,
) -> str:
    """
    根据实际成本率和阈值返回 'ok' | 'warning' | 'critical'。

    >>> classify_alert(28.0, 32.0, 35.0)
    'ok'
    >>> classify_alert(33.5, 32.0, 35.0)
    'warning'
    >>> classify_alert(37.0, 32.0, 35.0)
    'critical'
    """
    if actual_pct >= critical_threshold:
        return "critical"
    if actual_pct >= warning_threshold:
        return "warning"
    return "ok"


def build_alert_message(
    store_id: str,
    actual_pct: float,
    warning_threshold: float,
    critical_threshold: float,
    actual_cost_yuan: float,
    top_ingredients: List[Dict[str, Any]],
    status: str,
) -> str:
    """
    构建企业微信告警文本（Rule 7：含动作 + ¥ + 置信度）。
    """
    emoji   = "🚨" if status == "critical" else "⚠️"
    level   = "超标" if status == "critical" else "偏高"
    excess  = actual_pct - (critical_threshold if status == "critical" else warning_threshold)

    top_lines = "\n".join(
        f"  • {ing['name']}: ¥{ing['cost_yuan']:,.0f}"
        for ing in top_ingredients[:3]
    ) or "  （暂无数据）"

    return (
        f"{emoji} 食材成本率{level}告警\n\n"
        f"门店：{store_id}\n"
        f"实际成本率：{actual_pct:.1f}%（{level} {excess:+.1f}%）\n"
        f"预警阈值：{warning_threshold:.0f}% / {critical_threshold:.0f}%\n"
        f"本期成本支出：¥{actual_cost_yuan:,.0f}\n\n"
        f"📌 Top3 高消耗食材：\n{top_lines}\n\n"
        f"💡 建议：立即审阅今日 AI 决策推荐，执行压缩成本方案\n"
        f"---\n屯象OS · 食材成本率监控"
    )


# ════════════════════════════════════════════════════════════════════════════════
# KPIAlertService
# ════════════════════════════════════════════════════════════════════════════════

class KPIAlertService:
    """食材成本率 KPI 告警服务（读取 DB 阈值 → 检查 → 推送企微）"""

    # ── 读取 DB 中配置的食材成本率阈值 ────────────────────────────────────────

    @staticmethod
    async def _get_food_cost_thresholds(db: AsyncSession) -> Dict[str, float]:
        """
        从 KPI 表读取 category='food_cost' 的警告/超标阈值。
        若未配置则返回环境变量默认值。
        """
        result = await db.execute(
            select(KPI).where(
                KPI.category == "food_cost",
                KPI.is_active == "true",
            )
        )
        kpis = result.scalars().all()

        warnings  = [k.warning_threshold  for k in kpis if k.warning_threshold  is not None]
        criticals = [k.critical_threshold for k in kpis if k.critical_threshold is not None]

        return {
            "warning":  min(warnings)  if warnings  else _DEFAULT_WARNING_PCT,
            "critical": min(criticals) if criticals else _DEFAULT_CRITICAL_PCT,
        }

    # ── 获取所有激活门店 ID ────────────────────────────────────────────────────

    @staticmethod
    async def _get_active_store_ids(db: AsyncSession) -> List[str]:
        """从 stores 表获取所有激活门店 ID。"""
        result = await db.execute(
            text(
                "SELECT id FROM stores "
                "WHERE is_active = TRUE "
                "ORDER BY id"
            )
        )
        return [row[0] for row in result.fetchall()]

    # ── 检查单店 ─────────────────────────────────────────────────────────────

    @staticmethod
    async def check_store(
        store_id:      str,
        db:            AsyncSession,
        thresholds:    Dict[str, float],
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
    ) -> Dict[str, Any]:
        """
        检查单店食材成本率并返回告警结构。

        Returns:
            {
              store_id, actual_cost_pct, actual_cost_yuan,
              warning_threshold, critical_threshold,
              status, needs_alert, top_ingredients
            }
        """
        end_date   = date.today()
        start_date = end_date - timedelta(days=lookback_days)

        variance = await FoodCostService.get_store_food_cost_variance(
            store_id=store_id, start_date=start_date, end_date=end_date, db=db
        )

        actual_pct  = variance.get("actual_cost_pct",  0.0)
        actual_yuan = variance.get("actual_cost_yuan",
                      variance.get("actual_cost_fen",  0) / 100)
        top_ings    = variance.get("top_ingredients",  [])

        w = thresholds["warning"]
        c = thresholds["critical"]
        status = classify_alert(actual_pct, w, c)

        return {
            "store_id":          store_id,
            "actual_cost_pct":   actual_pct,
            "actual_cost_yuan":  actual_yuan,
            "warning_threshold": w,
            "critical_threshold": c,
            "status":            status,
            "needs_alert":       status != "ok",
            "top_ingredients":   top_ings,
        }

    # ── 检查所有门店 ─────────────────────────────────────────────────────────

    @staticmethod
    async def run_all_stores(
        db:            AsyncSession,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
    ) -> Dict[str, Any]:
        """
        遍历所有激活门店，返回需要告警的门店列表及汇总。

        Returns:
            {total, alert_count, ok_count, alerts: [...]}
        """
        thresholds = await KPIAlertService._get_food_cost_thresholds(db)
        store_ids  = await KPIAlertService._get_active_store_ids(db)

        alerts: List[Dict[str, Any]] = []
        ok_count = 0

        for sid in store_ids:
            try:
                result = await KPIAlertService.check_store(
                    store_id=sid, db=db, thresholds=thresholds,
                    lookback_days=lookback_days,
                )
                if result["needs_alert"]:
                    alerts.append(result)
                else:
                    ok_count += 1
            except Exception as exc:
                logger.warning("kpi_alert_store_check_failed", store_id=sid, error=str(exc))

        logger.info(
            "kpi_food_cost_check_complete",
            total=len(store_ids), alerts=len(alerts), ok=ok_count,
        )
        return {
            "total":       len(store_ids),
            "alert_count": len(alerts),
            "ok_count":    ok_count,
            "alerts":      alerts,
        }

    # ── 发送单店告警 ──────────────────────────────────────────────────────────

    @staticmethod
    async def send_alert(
        check_result:      Dict[str, Any],
        recipient_user_id: str,
    ) -> Dict[str, Any]:
        """
        向企业微信发送食材成本率告警文本消息。
        """
        from src.services.wechat_work_message_service import wechat_work_message_service

        message = build_alert_message(
            store_id          = check_result["store_id"],
            actual_pct        = check_result["actual_cost_pct"],
            warning_threshold = check_result["warning_threshold"],
            critical_threshold= check_result["critical_threshold"],
            actual_cost_yuan  = check_result["actual_cost_yuan"],
            top_ingredients   = check_result["top_ingredients"],
            status            = check_result["status"],
        )
        return await wechat_work_message_service.send_text_message(
            user_id=recipient_user_id,
            content=message,
        )

    # ── 全流程：检查 + 推送 ────────────────────────────────────────────────────

    @staticmethod
    async def run_and_notify(
        db:            AsyncSession,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
    ) -> Dict[str, Any]:
        """
        完整流程：检查所有门店 → 对 needs_alert 门店发送企微告警。
        Celery task 直接调用此方法。
        """
        summary = await KPIAlertService.run_all_stores(db=db, lookback_days=lookback_days)

        sent_count   = 0
        failed_count = 0

        for alert in summary["alerts"]:
            recipient = os.getenv(
                f"WECHAT_RECIPIENT_{alert['store_id'].upper()}",
                os.getenv("WECHAT_DEFAULT_RECIPIENT", f"store_{alert['store_id']}"),
            )
            try:
                res = await KPIAlertService.send_alert(
                    check_result=alert, recipient_user_id=recipient
                )
                if res.get("success"):
                    sent_count += 1
                    logger.info("kpi_alert_sent", store_id=alert["store_id"], status=alert["status"])
                else:
                    failed_count += 1
            except Exception as exc:
                failed_count += 1
                logger.error("kpi_alert_send_failed", store_id=alert["store_id"], error=str(exc))

        return {
            **summary,
            "sent_count":   sent_count,
            "failed_count": failed_count,
        }

    # ── 趋势预测告警 ──────────────────────────────────────────────────────────

    @staticmethod
    def _linear_trend(values: List[float]) -> float:
        """
        最小二乘线性回归，返回每步斜率（slope）。

        x = [0, 1, ..., n-1]，y = values
        slope = (n * Σxy - Σx * Σy) / (n * Σx² - (Σx)²)
        """
        n = len(values)
        if n < 2:
            return 0.0
        sx  = n * (n - 1) / 2          # Σx
        sx2 = n * (n - 1) * (2 * n - 1) / 6  # Σx²
        sy  = sum(values)
        sxy = sum(i * v for i, v in enumerate(values))
        denom = n * sx2 - sx * sx
        if denom == 0:
            return 0.0
        return (n * sxy - sx * sy) / denom

    @staticmethod
    async def check_store_trend(
        store_id:       str,
        db:             AsyncSession,
        thresholds:     Dict[str, float],
        lookback_days:  int = _TREND_LOOKBACK_DAYS,
        forecast_days:  int = _TREND_FORECAST_DAYS,
    ) -> Dict[str, Any]:
        """
        趋势预测告警：计算近 lookback_days 天成本率线性趋势，
        预测 forecast_days 天后是否会突破 warning / critical 阈值。

        Returns:
            {
              store_id, current_cost_pct, slope_per_day,
              forecasted_pct, forecast_days,
              trend_status: ok | warning_trend | critical_trend,
              days_to_warning, days_to_critical,
              needs_trend_alert, history
            }
        """
        end_date   = date.today()
        history: List[float] = []

        for offset in range(lookback_days - 1, -1, -1):
            d = end_date - timedelta(days=offset)
            try:
                v = await FoodCostService.get_store_food_cost_variance(
                    store_id=store_id,
                    start_date=d,
                    end_date=d,
                    db=db,
                )
                history.append(float(v.get("actual_cost_pct", 0.0)))
            except Exception:
                pass  # 某天无数据时跳过，不阻断

        if len(history) < 3:
            return {
                "store_id":         store_id,
                "trend_status":     "insufficient_data",
                "needs_trend_alert": False,
                "history":          history,
                "message":          f"历史数据不足（仅 {len(history)} 天），无法计算趋势",
            }

        slope   = KPIAlertService._linear_trend(history)
        current = history[-1]
        w_thr   = thresholds["warning"]
        c_thr   = thresholds["critical"]

        # 预测 forecast_days 天后的成本率
        forecasted = current + slope * forecast_days

        # 计算到达阈值还需多少天（slope > 0 才会超标）
        def _days_to_threshold(threshold: float) -> Optional[int]:
            if slope <= 0 or current >= threshold:
                return None
            days = (threshold - current) / slope
            return int(days) if days <= 30 else None  # 超过 30 天不告警

        days_to_warning  = _days_to_threshold(w_thr)
        days_to_critical = _days_to_threshold(c_thr)

        # 判断趋势告警级别
        if slope > 0 and forecasted >= c_thr:
            trend_status = "critical_trend"
        elif slope > 0 and forecasted >= w_thr:
            trend_status = "warning_trend"
        else:
            trend_status = "ok"

        needs_alert = trend_status != "ok"

        return {
            "store_id":           store_id,
            "current_cost_pct":   round(current, 2),
            "slope_per_day":      round(slope, 4),
            "forecasted_pct":     round(forecasted, 2),
            "forecast_days":      forecast_days,
            "warning_threshold":  w_thr,
            "critical_threshold": c_thr,
            "trend_status":       trend_status,
            "days_to_warning":    days_to_warning,
            "days_to_critical":   days_to_critical,
            "needs_trend_alert":  needs_alert,
            "history":            [round(v, 2) for v in history],
        }

    @staticmethod
    def _build_trend_alert_message(result: Dict[str, Any]) -> str:
        """构建趋势预警消息（Rule 7：动作 + ¥ + 预测窗口）。"""
        emoji  = "📈" if result["trend_status"] == "warning_trend" else "🚨"
        level  = "偏高趋势" if result["trend_status"] == "warning_trend" else "超标趋势"
        d2w    = result.get("days_to_warning")
        d2c    = result.get("days_to_critical")
        reach_line = ""
        if d2c is not None:
            reach_line = f"\n预计 {d2c} 天后突破超标阈值 {result['critical_threshold']:.0f}%"
        elif d2w is not None:
            reach_line = f"\n预计 {d2w} 天后突破警告阈值 {result['warning_threshold']:.0f}%"

        return (
            f"{emoji} 食材成本率{level}预警\n\n"
            f"门店：{result['store_id']}\n"
            f"当前成本率：{result['current_cost_pct']:.1f}%\n"
            f"日均增速：+{result['slope_per_day']:.3f}%/天\n"
            f"预测 {result['forecast_days']} 天后：{result['forecasted_pct']:.1f}%"
            f"{reach_line}\n\n"
            f"💡 建议：尽早执行 AI 决策推荐中的降本方案，防止成本率持续上升\n"
            f"---\n屯象OS · 成本率趋势监控"
        )

    @staticmethod
    async def run_trend_alerts(
        db:            AsyncSession,
        lookback_days: int = _TREND_LOOKBACK_DAYS,
        forecast_days: int = _TREND_FORECAST_DAYS,
    ) -> Dict[str, Any]:
        """
        扫描所有门店的成本率趋势，对趋势恶化的门店发送预警。

        Returns:
            {total, trend_alert_count, ok_count, sent_count, failed_count, results}
        """
        thresholds = await KPIAlertService._get_food_cost_thresholds(db)
        store_ids  = await KPIAlertService._get_active_store_ids(db)

        results: List[Dict[str, Any]] = []
        ok_count = 0

        for sid in store_ids:
            try:
                r = await KPIAlertService.check_store_trend(
                    store_id=sid, db=db, thresholds=thresholds,
                    lookback_days=lookback_days, forecast_days=forecast_days,
                )
                results.append(r)
                if not r["needs_trend_alert"]:
                    ok_count += 1
            except Exception as exc:
                logger.warning("kpi_trend_check_failed", store_id=sid, error=str(exc))

        # 向需要告警的门店发送趋势预警
        from src.services.wechat_work_message_service import wechat_work_message_service

        sent_count = failed_count = 0
        for r in results:
            if not r["needs_trend_alert"]:
                continue
            recipient = os.getenv(
                f"WECHAT_RECIPIENT_{r['store_id'].upper()}",
                os.getenv("WECHAT_DEFAULT_RECIPIENT", f"store_{r['store_id']}"),
            )
            try:
                msg = KPIAlertService._build_trend_alert_message(r)
                res = await wechat_work_message_service.send_text_message(
                    user_id=recipient, content=msg
                )
                if res.get("success"):
                    sent_count += 1
                    logger.info("kpi_trend_alert_sent", store_id=r["store_id"], status=r["trend_status"])
                else:
                    failed_count += 1
            except Exception as exc:
                failed_count += 1
                logger.error("kpi_trend_alert_send_failed", store_id=r["store_id"], error=str(exc))

        alert_results = [r for r in results if r["needs_trend_alert"]]
        logger.info(
            "kpi_trend_check_complete",
            total=len(store_ids), alerts=len(alert_results),
            ok=ok_count, sent=sent_count,
        )
        return {
            "total":             len(store_ids),
            "trend_alert_count": len(alert_results),
            "ok_count":          ok_count,
            "sent_count":        sent_count,
            "failed_count":      failed_count,
            "results":           results,
        }
