"""
WorkforcePushService

每日 07:00 主动推送人力排班建议：
1. 生成明日客流/人力预测
2. 写入 staffing_advice（all_day 建议）
3. 发送企微决策卡片
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.labor_demand_service import LaborDemandService
from src.services.wechat_service import wechat_service

logger = structlog.get_logger()

_APPROVAL_BASE_URL = os.getenv(
    "WORKFORCE_APPROVAL_BASE_URL",
    "https://your-domain.com/workforce",
)


class WorkforcePushService:
    """人力建议主动推送服务。"""

    @staticmethod
    def _format_staffing_recommendation(
        store_name: str,
        target_date: date,
        forecast: Dict[str, Any],
        recommended_headcount: int,
        current_headcount: Optional[int],
        estimated_saving_yuan: float,
    ) -> str:
        periods = forecast.get("periods", {})
        predicted_customers = sum(
            int((periods.get(p) or {}).get("predicted_customer_count") or 0) for p in ("morning", "lunch", "dinner")
        )
        morning_need = int((periods.get("morning") or {}).get("total_headcount_needed") or 0)
        lunch_need = int((periods.get("lunch") or {}).get("total_headcount_needed") or 0)
        dinner_need = int((periods.get("dinner") or {}).get("total_headcount_needed") or 0)
        reason_1 = (periods.get("morning") or {}).get("reason_1") or ""
        reason_2 = (periods.get("lunch") or {}).get("reason_2") or ""
        reason_3 = (periods.get("dinner") or {}).get("reason_3") or ""
        delta = None if current_headcount is None else recommended_headcount - current_headcount

        lines = [
            f"【{store_name}】{target_date.isoformat()} 人力建议",
            f"明日客流预测：{predicted_customers} 人",
            f"建议排班：{recommended_headcount} 人（早{morning_need}/午{lunch_need}/晚{dinner_need}）",
        ]
        if current_headcount is not None:
            lines.append(f"当前已排：{current_headcount} 人（差值 {delta:+d}）")
        lines.append(f"预计节省：¥{estimated_saving_yuan:.0f}")
        if reason_1:
            lines.append(f"1) {reason_1[:72]}")
        if reason_2:
            lines.append(f"2) {reason_2[:72]}")
        if reason_3:
            lines.append(f"3) {reason_3[:72]}")
        lines.append("请点击“一键确认”完成排班确认")
        return "\n".join(lines)[:510]

    @staticmethod
    async def push_daily_staffing_advice(
        store_id: str,
        db: AsyncSession,
        *,
        store_name: str = "",
        recipient_user_id: Optional[str] = None,
        target_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        为单门店生成并推送每日人力建议。
        """
        advice_date = target_date or (date.today() + timedelta(days=1))
        forecast = await LaborDemandService.forecast_all_periods(
            store_id=store_id,
            forecast_date=advice_date,
            db=db,
            save=True,
            weather_score=1.0,
        )

        recommended_headcount = int(forecast.get("daily_peak_headcount") or 0)

        current_result = await db.execute(
            text("""
                SELECT total_employees
                FROM schedules
                WHERE store_id = :sid
                  AND schedule_date = :schedule_date
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """),
            {"sid": store_id, "schedule_date": advice_date},
        )
        current_row = current_result.fetchone()
        current_headcount: Optional[int] = None
        if current_row and current_row.total_employees is not None:
            try:
                current_headcount = int(current_row.total_employees)
            except (TypeError, ValueError):
                current_headcount = None

        delta = None if current_headcount is None else (recommended_headcount - current_headcount)
        avg_wage_per_day = float(os.getenv("L8_AVG_WAGE_PER_DAY", "200"))
        estimated_saving_yuan = float(max((0 - (delta or 0)) * avg_wage_per_day, 0))
        estimated_overspend_yuan = float(max((delta or 0) * avg_wage_per_day, 0))

        periods = forecast.get("periods", {})
        position_breakdown = {
            "morning": (periods.get("morning") or {}).get("position_requirements", {}),
            "lunch": (periods.get("lunch") or {}).get("position_requirements", {}),
            "dinner": (periods.get("dinner") or {}).get("position_requirements", {}),
        }

        reason_1 = (periods.get("morning") or {}).get("reason_1")
        reason_2 = (periods.get("lunch") or {}).get("reason_2")
        reason_3 = (periods.get("dinner") or {}).get("reason_3")
        confidence_candidates = [
            float((periods.get("morning") or {}).get("confidence_score") or 0),
            float((periods.get("lunch") or {}).get("confidence_score") or 0),
            float((periods.get("dinner") or {}).get("confidence_score") or 0),
        ]
        confidence_score = round(sum(confidence_candidates) / 3, 3)

        existing = await db.execute(
            text("""
                SELECT id
                FROM staffing_advice
                WHERE store_id = :sid
                  AND advice_date = :advice_date
                  AND meal_period = CAST(:meal_period AS meal_period_type)
                ORDER BY created_at DESC
                LIMIT 1
                """),
            {"sid": store_id, "advice_date": advice_date, "meal_period": "all_day"},
        )
        existing_row = existing.fetchone()
        if existing_row:
            advice_id = existing_row.id
            await db.execute(
                text("""
                    UPDATE staffing_advice
                    SET status = CAST(:status AS staffing_advice_status),
                        recommended_headcount = :recommended_headcount,
                        current_scheduled_headcount = :current_headcount,
                        headcount_delta = :headcount_delta,
                        estimated_saving_yuan = :estimated_saving_yuan,
                        estimated_overspend_yuan = :estimated_overspend_yuan,
                        reason_1 = :reason_1,
                        reason_2 = :reason_2,
                        reason_3 = :reason_3,
                        confidence_score = :confidence_score,
                        position_breakdown = CAST(:position_breakdown AS JSON),
                        expires_at = :expires_at,
                        updated_at = NOW()
                    WHERE id = :advice_id
                    """),
                {
                    "status": "pending",
                    "recommended_headcount": recommended_headcount,
                    "current_headcount": current_headcount,
                    "headcount_delta": delta,
                    "estimated_saving_yuan": estimated_saving_yuan,
                    "estimated_overspend_yuan": estimated_overspend_yuan,
                    "reason_1": reason_1,
                    "reason_2": reason_2,
                    "reason_3": reason_3,
                    "confidence_score": confidence_score,
                    "position_breakdown": json.dumps(position_breakdown, ensure_ascii=False),
                    "expires_at": datetime.combine(advice_date, datetime.min.time()) + timedelta(days=1),
                    "advice_id": advice_id,
                },
            )
        else:
            await db.execute(
                text("""
                    INSERT INTO staffing_advice (
                        id, store_id, advice_date, meal_period, status,
                        recommended_headcount, current_scheduled_headcount, headcount_delta,
                        estimated_saving_yuan, estimated_overspend_yuan,
                        reason_1, reason_2, reason_3, confidence_score,
                        position_breakdown, push_sent_at, expires_at, created_at, updated_at
                    ) VALUES (
                        gen_random_uuid(), :store_id, :advice_date,
                        CAST(:meal_period AS meal_period_type),
                        CAST(:status AS staffing_advice_status),
                        :recommended_headcount, :current_headcount, :headcount_delta,
                        :estimated_saving_yuan, :estimated_overspend_yuan,
                        :reason_1, :reason_2, :reason_3, :confidence_score,
                        CAST(:position_breakdown AS JSON), NULL, :expires_at, NOW(), NOW()
                    )
                    """),
                {
                    "store_id": store_id,
                    "advice_date": advice_date,
                    "meal_period": "all_day",
                    "status": "pending",
                    "recommended_headcount": recommended_headcount,
                    "current_headcount": current_headcount,
                    "headcount_delta": delta,
                    "estimated_saving_yuan": estimated_saving_yuan,
                    "estimated_overspend_yuan": estimated_overspend_yuan,
                    "reason_1": reason_1,
                    "reason_2": reason_2,
                    "reason_3": reason_3,
                    "confidence_score": confidence_score,
                    "position_breakdown": json.dumps(position_breakdown, ensure_ascii=False),
                    "expires_at": datetime.combine(advice_date, datetime.min.time()) + timedelta(days=1),
                },
            )

        recipient = recipient_user_id or f"store_{store_id}"
        description = WorkforcePushService._format_staffing_recommendation(
            store_name=store_name or store_id,
            target_date=advice_date,
            forecast=forecast,
            recommended_headcount=recommended_headcount,
            current_headcount=current_headcount,
            estimated_saving_yuan=estimated_saving_yuan,
        )
        card_result = await wechat_service.send_decision_card(
            title=f"【07:00排班建议】{store_name or store_id}",
            description=description,
            action_url=f"{_APPROVAL_BASE_URL}?store_id={store_id}&date={advice_date.isoformat()}",
            btntxt="一键确认",
            to_user_id=recipient,
        )

        await db.execute(
            text("""
                UPDATE staffing_advice
                SET push_sent_at = NOW(), updated_at = NOW()
                WHERE store_id = :sid
                  AND advice_date = :advice_date
                  AND meal_period = CAST(:meal_period AS meal_period_type)
                """),
            {"sid": store_id, "advice_date": advice_date, "meal_period": "all_day"},
        )

        logger.info(
            "workforce_push.daily_staffing_advice_done",
            store_id=store_id,
            advice_date=advice_date.isoformat(),
            recommended_headcount=recommended_headcount,
            current_headcount=current_headcount,
            status=card_result.get("status"),
        )
        return {
            "store_id": store_id,
            "advice_date": advice_date.isoformat(),
            "recommended_headcount": recommended_headcount,
            "current_headcount": current_headcount,
            "estimated_saving_yuan": estimated_saving_yuan,
            "message_status": card_result.get("status"),
            "message_id": card_result.get("message_id"),
        }
