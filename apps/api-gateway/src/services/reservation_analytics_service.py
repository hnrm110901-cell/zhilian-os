"""
预订数据分析引擎 — 8维度深度分析
提供：总览/渠道ROI/高峰热力图/客户洞察/No-Show预测/营收影响/取消深度/趋势
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, case, distinct, extract, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.order import Order
from src.models.reservation import Reservation, ReservationStatus, ReservationType
from src.models.reservation_channel import ChannelType, ReservationChannel

logger = logging.getLogger(__name__)


class ReservationAnalyticsService:
    """预订分析引擎"""

    # ── 1. 总览 ──────────────────────────────────────────

    async def get_overview(self, db: AsyncSession, store_id: str, start_date: date, end_date: date) -> dict:
        """预订经营总览"""
        base_filter = and_(
            Reservation.store_id == store_id,
            Reservation.reservation_date >= start_date,
            Reservation.reservation_date <= end_date,
        )

        # 各状态计数
        result = await db.execute(
            select(
                Reservation.status,
                func.count(Reservation.id).label("cnt"),
                func.sum(Reservation.party_size).label("total_guests"),
            )
            .where(base_filter)
            .group_by(Reservation.status)
        )
        status_map = {}
        total = 0
        total_guests = 0
        for row in result.all():
            status_val = row.status.value if hasattr(row.status, "value") else str(row.status)
            status_map[status_val] = row.cnt
            total += row.cnt
            total_guests += row.total_guests or 0

        confirmed = (
            status_map.get("confirmed", 0)
            + status_map.get("completed", 0)
            + status_map.get("seated", 0)
            + status_map.get("arrived", 0)
        )
        cancelled = status_map.get("cancelled", 0)
        no_show = status_map.get("no_show", 0)

        # 平均桌位
        avg_party = round(total_guests / total, 1) if total > 0 else 0

        # 预订类型分布
        type_result = await db.execute(
            select(
                Reservation.reservation_type,
                func.count(Reservation.id),
            )
            .where(base_filter)
            .group_by(Reservation.reservation_type)
        )
        type_dist = {}
        for row in type_result.all():
            t = row[0].value if hasattr(row[0], "value") else str(row[0])
            type_dist[t] = row[1]

        days = (end_date - start_date).days + 1

        return {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat(), "days": days},
            "total_reservations": total,
            "avg_daily": round(total / days, 1) if days > 0 else 0,
            "total_guests": total_guests,
            "avg_party_size": avg_party,
            "status_breakdown": status_map,
            "confirmation_rate": round(confirmed / total * 100, 1) if total > 0 else 0,
            "cancellation_rate": round(cancelled / total * 100, 1) if total > 0 else 0,
            "no_show_rate": round(no_show / total * 100, 1) if total > 0 else 0,
            "completion_rate": round(status_map.get("completed", 0) / total * 100, 1) if total > 0 else 0,
            "type_distribution": type_dist,
        }

    # ── 2. 渠道ROI ──────────────────────────────────────

    async def get_channel_roi(self, db: AsyncSession, store_id: str, start_date: date, end_date: date) -> dict:
        """各渠道预订量/转化率/佣金成本"""
        result = await db.execute(
            select(
                ReservationChannel.channel,
                func.count(ReservationChannel.id).label("count"),
                func.sum(ReservationChannel.channel_commission_amount).label("commission"),
            )
            .join(Reservation, Reservation.id == ReservationChannel.reservation_id)
            .where(
                and_(
                    ReservationChannel.store_id == store_id,
                    Reservation.reservation_date >= start_date,
                    Reservation.reservation_date <= end_date,
                )
            )
            .group_by(ReservationChannel.channel)
        )
        channels = []
        total_count = 0
        total_commission = 0

        for row in result.all():
            ch = row.channel.value if hasattr(row.channel, "value") else str(row.channel)
            cnt = row.count
            comm = float(row.commission or 0)
            total_count += cnt
            total_commission += comm
            channels.append(
                {
                    "channel": ch,
                    "count": cnt,
                    "commission_yuan": round(comm, 2),
                }
            )

        # 每个渠道的转化率（完成/总数）
        for ch_data in channels:
            ch_enum = ch_data["channel"]
            completed_result = await db.execute(
                select(func.count(ReservationChannel.id))
                .join(Reservation, Reservation.id == ReservationChannel.reservation_id)
                .where(
                    and_(
                        ReservationChannel.store_id == store_id,
                        ReservationChannel.channel == ch_enum,
                        Reservation.reservation_date >= start_date,
                        Reservation.reservation_date <= end_date,
                        Reservation.status == ReservationStatus.COMPLETED,
                    )
                )
            )
            completed = completed_result.scalar() or 0
            ch_data["completed"] = completed
            ch_data["conversion_rate"] = round(completed / ch_data["count"] * 100, 1) if ch_data["count"] > 0 else 0
            ch_data["percentage"] = round(ch_data["count"] / total_count * 100, 1) if total_count > 0 else 0
            ch_data["cost_per_reservation"] = (
                round(ch_data["commission_yuan"] / ch_data["count"], 2) if ch_data["count"] > 0 else 0
            )

        channels.sort(key=lambda x: x["count"], reverse=True)

        return {
            "total_reservations": total_count,
            "total_commission_yuan": round(total_commission, 2),
            "channels": channels,
        }

    # ── 3. 高峰时段热力图 ──────────────────────────────

    async def get_peak_heatmap(self, db: AsyncSession, store_id: str, start_date: date, end_date: date) -> dict:
        """按星期×时段的预订分布热力图"""
        result = await db.execute(
            select(
                extract("dow", Reservation.reservation_date).label("dow"),  # 0=Sun, 6=Sat
                extract("hour", Reservation.reservation_time).label("hour"),
                func.count(Reservation.id).label("cnt"),
                func.sum(Reservation.party_size).label("guests"),
            )
            .where(
                and_(
                    Reservation.store_id == store_id,
                    Reservation.reservation_date >= start_date,
                    Reservation.reservation_date <= end_date,
                    Reservation.status.notin_([ReservationStatus.CANCELLED]),
                )
            )
            .group_by("dow", "hour")
        )

        # 构造 7×24 矩阵
        heatmap = []
        day_names = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
        for row in result.all():
            dow = int(row.dow)
            hour = int(row.hour)
            heatmap.append(
                {
                    "day": dow,
                    "day_name": day_names[dow],
                    "hour": hour,
                    "count": row.cnt,
                    "guests": row.guests or 0,
                }
            )

        # 找出最高峰
        peak = max(heatmap, key=lambda x: x["count"]) if heatmap else None

        # 按星期汇总
        day_totals = defaultdict(int)
        for item in heatmap:
            day_totals[item["day_name"]] += item["count"]

        return {
            "heatmap": heatmap,
            "peak": peak,
            "day_totals": dict(day_totals),
            "busiest_day": max(day_totals, key=day_totals.get) if day_totals else None,
        }

    # ── 4. 客户洞察 ──────────────────────────────────────

    async def get_customer_insights(self, db: AsyncSession, store_id: str, start_date: date, end_date: date) -> dict:
        """新客/回头客/VIP分析"""
        # 当期所有不同手机号
        current_phones = await db.execute(
            select(
                Reservation.customer_phone,
                func.count(Reservation.id).label("visit_count"),
                func.sum(Reservation.party_size).label("total_guests"),
            )
            .where(
                and_(
                    Reservation.store_id == store_id,
                    Reservation.reservation_date >= start_date,
                    Reservation.reservation_date <= end_date,
                    Reservation.status.notin_([ReservationStatus.CANCELLED]),
                )
            )
            .group_by(Reservation.customer_phone)
        )
        customers = current_phones.all()
        total_customers = len(customers)

        # 检查谁在 start_date 之前有过预订（回头客）
        phones_in_period = [c.customer_phone for c in customers]
        returning_count = 0
        if phones_in_period:
            # 分批查询避免参数过多
            batch_size = 500
            for i in range(0, len(phones_in_period), batch_size):
                batch = phones_in_period[i : i + batch_size]
                prior_result = await db.execute(
                    select(func.count(distinct(Reservation.customer_phone))).where(
                        and_(
                            Reservation.store_id == store_id,
                            Reservation.reservation_date < start_date,
                            Reservation.customer_phone.in_(batch),
                            Reservation.status.notin_([ReservationStatus.CANCELLED]),
                        )
                    )
                )
                returning_count += prior_result.scalar() or 0

        new_count = total_customers - returning_count

        # 高频客户（当期2次以上）
        frequent = [c for c in customers if c.visit_count >= 2]

        # 大桌客户（平均桌位 >= 6）
        big_party = [c for c in customers if (c.total_guests / c.visit_count) >= 6]

        return {
            "total_unique_customers": total_customers,
            "new_customers": new_count,
            "returning_customers": returning_count,
            "new_rate": round(new_count / total_customers * 100, 1) if total_customers > 0 else 0,
            "returning_rate": round(returning_count / total_customers * 100, 1) if total_customers > 0 else 0,
            "frequent_customers": len(frequent),
            "big_party_customers": len(big_party),
            "avg_visits_per_customer": (
                round(sum(c.visit_count for c in customers) / total_customers, 2) if total_customers > 0 else 0
            ),
        }

    # ── 5. No-Show 风险预测 ──────────────────────────────

    async def get_no_show_risk(self, db: AsyncSession, store_id: str, target_date: Optional[date] = None) -> dict:
        """基于历史数据预测明天/指定日期的 No-Show 风险"""
        if not target_date:
            target_date = date.today() + timedelta(days=1)

        # 获取目标日期的预订
        upcoming = await db.execute(
            select(Reservation).where(
                and_(
                    Reservation.store_id == store_id,
                    Reservation.reservation_date == target_date,
                    Reservation.status.in_([ReservationStatus.PENDING, ReservationStatus.CONFIRMED]),
                )
            )
        )
        reservations = upcoming.scalars().all()

        # 历史 no-show 率（按手机号）
        risk_list = []
        for r in reservations:
            # 查该客户历史 no-show 次数 / 总预订次数
            history = await db.execute(
                select(
                    func.count(Reservation.id).label("total"),
                    func.sum(case((Reservation.status == ReservationStatus.NO_SHOW, 1), else_=0)).label("no_shows"),
                    func.sum(case((Reservation.status == ReservationStatus.CANCELLED, 1), else_=0)).label("cancels"),
                ).where(
                    and_(
                        Reservation.customer_phone == r.customer_phone,
                        Reservation.store_id == store_id,
                        Reservation.reservation_date < target_date,
                    )
                )
            )
            row = history.one()
            total_history = row.total or 0
            no_shows = row.no_shows or 0
            cancels = row.cancels or 0

            # 风险评分（0-100）
            if total_history == 0:
                # 新客户，默认中等风险
                risk_score = 15
                risk_level = "low"
            else:
                no_show_rate = no_shows / total_history
                cancel_rate = cancels / total_history
                risk_score = min(100, int(no_show_rate * 60 + cancel_rate * 30 + 10))
                if risk_score >= 60:
                    risk_level = "high"
                elif risk_score >= 30:
                    risk_level = "medium"
                else:
                    risk_level = "low"

            # 状态加权：PENDING 比 CONFIRMED 风险高
            if r.status == ReservationStatus.PENDING:
                risk_score = min(100, risk_score + 10)

            risk_list.append(
                {
                    "reservation_id": r.id,
                    "customer_name": r.customer_name,
                    "customer_phone": r.customer_phone[-4:],  # 脱敏
                    "party_size": r.party_size,
                    "time": str(r.reservation_time)[:5],
                    "status": r.status.value,
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "history_visits": total_history,
                    "history_no_shows": no_shows,
                    "suggestion": self._no_show_suggestion(risk_level, r.status.value),
                }
            )

        risk_list.sort(key=lambda x: x["risk_score"], reverse=True)

        high_risk = [r for r in risk_list if r["risk_level"] == "high"]
        total_at_risk_guests = sum(r["party_size"] for r in high_risk)

        return {
            "target_date": target_date.isoformat(),
            "total_upcoming": len(risk_list),
            "high_risk_count": len(high_risk),
            "medium_risk_count": len([r for r in risk_list if r["risk_level"] == "medium"]),
            "at_risk_guests": total_at_risk_guests,
            "reservations": risk_list,
        }

    @staticmethod
    def _no_show_suggestion(risk_level: str, status: str) -> str:
        if risk_level == "high":
            return "建议电话确认到店意向，或要求预付订金"
        elif risk_level == "medium" and status == "pending":
            return "建议发送确认短信提醒"
        elif risk_level == "medium":
            return "建议到店前2小时发送提醒"
        return "正常跟进"

    # ── 6. 营收影响分析 ──────────────────────────────────

    async def get_revenue_impact(self, db: AsyncSession, store_id: str, start_date: date, end_date: date) -> dict:
        """预订客 vs 非预订客的消费对比"""
        # 有预订的订单（通过 table_number 匹配或时间重叠）
        # 简化逻辑：统计有预订记录且完成的客户的消费
        completed_reservations = await db.execute(
            select(
                func.count(Reservation.id).label("count"),
                func.sum(Reservation.party_size).label("guests"),
                func.avg(Reservation.estimated_budget).label("avg_budget"),
            ).where(
                and_(
                    Reservation.store_id == store_id,
                    Reservation.reservation_date >= start_date,
                    Reservation.reservation_date <= end_date,
                    Reservation.status == ReservationStatus.COMPLETED,
                )
            )
        )
        comp = completed_reservations.one()

        # 取消的预订 → 潜在损失
        cancelled = await db.execute(
            select(
                func.count(Reservation.id).label("count"),
                func.sum(Reservation.party_size).label("guests"),
                func.sum(Reservation.estimated_budget).label("lost_budget"),
            ).where(
                and_(
                    Reservation.store_id == store_id,
                    Reservation.reservation_date >= start_date,
                    Reservation.reservation_date <= end_date,
                    Reservation.status == ReservationStatus.CANCELLED,
                )
            )
        )
        canc = cancelled.one()

        # No-show 损失
        no_show = await db.execute(
            select(
                func.count(Reservation.id).label("count"),
                func.sum(Reservation.party_size).label("guests"),
                func.sum(Reservation.estimated_budget).label("lost_budget"),
            ).where(
                and_(
                    Reservation.store_id == store_id,
                    Reservation.reservation_date >= start_date,
                    Reservation.reservation_date <= end_date,
                    Reservation.status == ReservationStatus.NO_SHOW,
                )
            )
        )
        ns = no_show.one()

        # 将分转元
        avg_budget_yuan = round(float(comp.avg_budget or 0) / 100, 2)
        cancelled_loss_yuan = round(float(canc.lost_budget or 0) / 100, 2)
        no_show_loss_yuan = round(float(ns.lost_budget or 0) / 100, 2)

        return {
            "completed_reservations": comp.count or 0,
            "completed_guests": comp.guests or 0,
            "avg_budget_yuan": avg_budget_yuan,
            "cancelled_count": canc.count or 0,
            "cancelled_guests": canc.guests or 0,
            "cancelled_loss_yuan": cancelled_loss_yuan,
            "no_show_count": ns.count or 0,
            "no_show_guests": ns.guests or 0,
            "no_show_loss_yuan": no_show_loss_yuan,
            "total_loss_yuan": round(cancelled_loss_yuan + no_show_loss_yuan, 2),
            "recovery_suggestion": self._revenue_suggestion(
                canc.count or 0, ns.count or 0, cancelled_loss_yuan + no_show_loss_yuan
            ),
        }

    @staticmethod
    def _revenue_suggestion(cancelled: int, no_show: int, total_loss: float) -> str:
        suggestions = []
        if no_show > 3:
            suggestions.append(f"No-Show {no_show}次，建议启用预付订金制度")
        if cancelled > 5:
            suggestions.append(f"取消 {cancelled}次，建议分析取消原因并优化确认流程")
        if total_loss > 5000:
            suggestions.append(f"潜在损失 ¥{total_loss:.0f}，建议建立等位候补机制填补空位")
        if not suggestions:
            suggestions.append("预订损失在可控范围，继续保持")
        return "；".join(suggestions)

    # ── 7. 取消深度分析 ──────────────────────────────────

    async def get_cancellation_deep(self, db: AsyncSession, store_id: str, start_date: date, end_date: date) -> dict:
        """取消预订的深度分析：提前量/时段分布/损失"""
        result = await db.execute(
            select(Reservation).where(
                and_(
                    Reservation.store_id == store_id,
                    Reservation.reservation_date >= start_date,
                    Reservation.reservation_date <= end_date,
                    Reservation.status == ReservationStatus.CANCELLED,
                )
            )
        )
        cancelled = result.scalars().all()

        if not cancelled:
            return {
                "total_cancelled": 0,
                "advance_distribution": {},
                "hour_distribution": {},
                "type_distribution": {},
                "total_lost_guests": 0,
                "total_lost_yuan": 0,
                "insights": ["当期无取消预订，表现优秀"],
            }

        # 取消提前量分布（取消时间 vs 预订日期）
        advance_buckets = {"当天": 0, "1天前": 0, "2-3天前": 0, "4-7天前": 0, "7天以上": 0}
        hour_dist = defaultdict(int)  # 取消发生在哪个时段
        type_dist = defaultdict(int)
        total_guests = 0
        total_budget = 0

        for r in cancelled:
            total_guests += r.party_size
            total_budget += r.estimated_budget or 0

            # 取消提前量
            if r.cancelled_at:
                cancel_date = r.cancelled_at.date() if isinstance(r.cancelled_at, datetime) else r.cancelled_at
                delta = (r.reservation_date - cancel_date).days
                if delta <= 0:
                    advance_buckets["当天"] += 1
                elif delta == 1:
                    advance_buckets["1天前"] += 1
                elif delta <= 3:
                    advance_buckets["2-3天前"] += 1
                elif delta <= 7:
                    advance_buckets["4-7天前"] += 1
                else:
                    advance_buckets["7天以上"] += 1

                # 取消发生的小时
                if isinstance(r.cancelled_at, datetime):
                    hour_dist[r.cancelled_at.hour] += 1

            # 预订类型
            t = r.reservation_type.value if r.reservation_type else "regular"
            type_dist[t] += 1

        total_lost_yuan = round(total_budget / 100, 2)

        # 洞察
        insights = []
        same_day = advance_buckets["当天"]
        if same_day > len(cancelled) * 0.3:
            insights.append(f"当天取消占比 {round(same_day / len(cancelled) * 100)}%，建议设置取消截止时间")
        if total_lost_yuan > 10000:
            insights.append(f"取消导致潜在损失 ¥{total_lost_yuan:.0f}，建议引入不可退订金")
        if not insights:
            insights.append("取消模式正常，建议持续监控")

        return {
            "total_cancelled": len(cancelled),
            "total_lost_guests": total_guests,
            "total_lost_yuan": total_lost_yuan,
            "advance_distribution": advance_buckets,
            "hour_distribution": dict(hour_dist),
            "type_distribution": dict(type_dist),
            "avg_party_size": round(total_guests / len(cancelled), 1),
            "insights": insights,
        }

    # ── 8. 每日趋势 ──────────────────────────────────────

    async def get_daily_trend(self, db: AsyncSession, store_id: str, days: int = 30) -> dict:
        """每日预订量/确认量/取消量折线数据"""
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        result = await db.execute(
            select(
                Reservation.reservation_date,
                Reservation.status,
                func.count(Reservation.id).label("cnt"),
                func.sum(Reservation.party_size).label("guests"),
            )
            .where(
                and_(
                    Reservation.store_id == store_id,
                    Reservation.reservation_date >= start_date,
                    Reservation.reservation_date <= end_date,
                )
            )
            .group_by(Reservation.reservation_date, Reservation.status)
            .order_by(Reservation.reservation_date)
        )

        # 按日期聚合
        daily_data = defaultdict(
            lambda: {"total": 0, "confirmed": 0, "cancelled": 0, "no_show": 0, "completed": 0, "guests": 0}
        )
        for row in result.all():
            d = row.reservation_date.isoformat()
            status = row.status.value if hasattr(row.status, "value") else str(row.status)
            daily_data[d]["total"] += row.cnt
            daily_data[d]["guests"] += row.guests or 0
            if status in ("confirmed", "arrived", "seated"):
                daily_data[d]["confirmed"] += row.cnt
            elif status == "cancelled":
                daily_data[d]["cancelled"] += row.cnt
            elif status == "no_show":
                daily_data[d]["no_show"] += row.cnt
            elif status == "completed":
                daily_data[d]["completed"] += row.cnt

        # 填充缺失日期
        trend = []
        current = start_date
        while current <= end_date:
            d = current.isoformat()
            entry = daily_data.get(d, {"total": 0, "confirmed": 0, "cancelled": 0, "no_show": 0, "completed": 0, "guests": 0})
            trend.append({"date": d, **entry})
            current += timedelta(days=1)

        return {
            "days": days,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "trend": trend,
        }


# 单例
reservation_analytics_service = ReservationAnalyticsService()
