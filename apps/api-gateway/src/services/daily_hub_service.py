"""
DailyHubService - T+1 经营统筹控制台核心编排器
"""
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

from src.services.redis_cache_service import redis_cache
from src.services.weather_adapter import weather_adapter
from src.services.forecast_features import ChineseHolidays, WeatherImpact

logger = structlog.get_logger()

BANQUET_AVG_SPEND_PER_HEAD = int(os.getenv("BANQUET_AVG_SPEND_PER_HEAD", "30000"))
CACHE_TTL = 86400  # 24h


def _cache_key(store_id: str, target_date: date) -> str:
    return f"daily_hub:{store_id}:{target_date.isoformat()}"


class DailyHubService:
    """每日备战板编排服务"""

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def generate_battle_board(
        self, store_id: str, target_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """生成/获取备战板（幂等，优先读缓存）"""
        if target_date is None:
            target_date = date.today() + timedelta(days=1)

        key = _cache_key(store_id, target_date)
        cached = await redis_cache.get(key)
        if cached:
            return cached

        board = await self._build_board(store_id, target_date)
        await redis_cache.set(key, board, expire=CACHE_TTL)
        return board

    async def approve_battle_board(
        self,
        store_id: str,
        target_date: date,
        approver_id: str,
        adjustments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """一键审批备战板，写回 Redis"""
        key = _cache_key(store_id, target_date)
        board = await redis_cache.get(key)
        if not board:
            board = await self._build_board(store_id, target_date)

        board["approval_status"] = "adjusted" if adjustments else "approved"
        board["approved_by"] = approver_id
        board["approved_at"] = datetime.now().isoformat()
        if adjustments:
            board["adjustments"] = adjustments

        await redis_cache.set(key, board, expire=CACHE_TTL)
        return board

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _build_board(self, store_id: str, target_date: date) -> Dict[str, Any]:
        yesterday = target_date - timedelta(days=1)

        yesterday_review = await self._get_yesterday_review(store_id, yesterday)
        weather_factors = await self._get_weather_factors(target_date)
        banquet_track = await self._get_banquet_variables(store_id, target_date)
        regular_track = await self._compute_regular_forecast(
            store_id, target_date, weather_factors
        )
        total_predicted, total_lower, total_upper = self._merge_tracks(
            banquet_track, regular_track
        )
        purchase_order = await self._build_purchase_order(store_id)
        staffing_plan = await self._get_staffing_plan(store_id, target_date)

        return {
            "store_id": store_id,
            "target_date": target_date.isoformat(),
            "generated_at": datetime.now().isoformat(),
            "approval_status": "pending",
            "yesterday_review": yesterday_review,
            "tomorrow_forecast": {
                "weather": weather_factors.get("weather"),
                "holiday": weather_factors.get("holiday"),
                "banquet_track": banquet_track,
                "regular_track": regular_track,
                "total_predicted_revenue": total_predicted,
                "total_lower": total_lower,
                "total_upper": total_upper,
            },
            "purchase_order": purchase_order,
            "staffing_plan": staffing_plan,
        }

    async def _get_yesterday_review(
        self, store_id: str, report_date: date
    ) -> Dict[str, Any]:
        try:
            from src.services.daily_report_service import daily_report_service

            report = await daily_report_service.generate_daily_report(
                store_id=store_id, report_date=report_date
            )
            return {
                "total_revenue": report.total_revenue,
                "order_count": report.order_count,
                "health_score": getattr(report, "health_score", None),
                "highlights": report.highlights or [],
                "alerts": report.alerts or [],
            }
        except Exception as e:
            logger.warning("获取昨日复盘失败，使用空数据", error=str(e))
            return {
                "total_revenue": 0,
                "order_count": 0,
                "health_score": None,
                "highlights": [],
                "alerts": [],
            }

    async def _get_weather_factors(self, target_date: date) -> Dict[str, Any]:
        result: Dict[str, Any] = {"weather": None, "holiday": None}

        # 天气
        weather = await weather_adapter.get_tomorrow_weather()
        if weather:
            impact_factor = WeatherImpact.WEATHER_IMPACT.get(
                weather["weather"], 1.0
            )
            result["weather"] = {
                "temperature": weather["temperature"],
                "condition": weather["weather"],
                "impact_factor": impact_factor,
            }

        # 节假日
        holiday_info = ChineseHolidays.get_holiday_info(target_date)
        if holiday_info:
            result["holiday"] = {
                "name": holiday_info.get("name", ""),
                "impact_factor": ChineseHolidays.get_holiday_impact_score(target_date),
            }

        return result

    async def _get_banquet_variables(
        self, store_id: str, target_date: date
    ) -> Dict[str, Any]:
        banquets: List[Dict[str, Any]] = []
        deterministic_revenue = 0

        try:
            from src.services.reservation_service import ReservationService
            from src.models.reservation import ReservationStatus, ReservationType

            svc = ReservationService(store_id=store_id)
            reservations = await svc.get_reservations(
                reservation_date=target_date.isoformat(),
                status=ReservationStatus.CONFIRMED.value,
            )

            for r in reservations:
                if r.get("reservation_type") != ReservationType.BANQUET.value:
                    continue
                budget = r.get("estimated_budget") or (
                    (r.get("party_size") or 0) * BANQUET_AVG_SPEND_PER_HEAD
                )
                deterministic_revenue += budget
                banquets.append(
                    {
                        "reservation_id": r.get("reservation_id"),
                        "customer_name": r.get("customer_name"),
                        "party_size": r.get("party_size"),
                        "estimated_budget": budget,
                        "reservation_time": r.get("reservation_time"),
                    }
                )
        except Exception as e:
            logger.warning("获取宴会变量失败", error=str(e))

        return {
            "active": len(banquets) > 0,
            "banquets": banquets,
            "deterministic_revenue": deterministic_revenue,
        }

    async def _compute_regular_forecast(
        self,
        store_id: str,
        target_date: date,
        weather_factors: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            from src.services.enhanced_forecast_service import EnhancedForecastService

            svc = EnhancedForecastService(store_id=store_id)
            weather_input = None
            if weather_factors.get("weather"):
                w = weather_factors["weather"]
                weather_input = {
                    "temperature": w["temperature"],
                    "weather": w["condition"],
                }
            result = await svc.forecast_sales(
                target_date=target_date, weather_forecast=weather_input
            )
            ci = result.get("confidence_interval", {})
            return {
                "predicted_revenue": result.get("predicted_sales", 0),
                "confidence_interval": ci,
                "confidence_level": "95%",
            }
        except Exception as e:
            logger.warning("散客预测失败，使用零值", error=str(e))
            return {
                "predicted_revenue": 0,
                "confidence_interval": {"lower": 0, "upper": 0},
                "confidence_level": "N/A",
            }

    def _merge_tracks(
        self,
        banquet_track: Dict[str, Any],
        regular_track: Dict[str, Any],
    ):
        banquet_rev = banquet_track.get("deterministic_revenue", 0)
        regular_rev = regular_track.get("predicted_revenue", 0)
        ci = regular_track.get("confidence_interval", {})
        lower = ci.get("lower", 0)
        upper = ci.get("upper", 0)

        total = banquet_rev + regular_rev
        total_lower = banquet_rev + lower
        total_upper = banquet_rev + upper
        return round(total, 2), round(total_lower, 2), round(total_upper, 2)

    async def _build_purchase_order(self, store_id: str) -> List[Dict[str, Any]]:
        try:
            from src.services.inventory_service import InventoryService

            svc = InventoryService(store_id=store_id)
            alerts = await svc.generate_restock_alerts()
            return [
                {
                    "item_name": a.get("item_name"),
                    "current_stock": a.get("current_stock"),
                    "recommended_quantity": a.get("recommended_quantity"),
                    "alert_level": a.get("alert_level"),
                    "supplier_name": a.get("supplier_name"),
                }
                for a in alerts
            ]
        except Exception as e:
            logger.warning("获取采购清单失败", error=str(e))
            return []

    async def _get_staffing_plan(
        self, store_id: str, target_date: date
    ) -> Dict[str, Any]:
        try:
            from src.services.schedule_service import ScheduleService

            svc = ScheduleService(store_id=store_id)
            schedule = await svc.get_schedule_by_date(target_date.isoformat())
            if not schedule:
                return {"shifts": [], "total_staff": 0}
            shifts = schedule.get("shifts", [])
            return {"shifts": shifts, "total_staff": len(shifts)}
        except Exception as e:
            logger.warning("获取排班计划失败", error=str(e))
            return {"shifts": [], "total_staff": 0}


# 全局单例
daily_hub_service = DailyHubService()
