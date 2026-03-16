"""
BossAgent Service — 老板每日经营智能（Sprint 3）

9-Agent 终态中的 BossAgent，核心能力：
1. 每日经营速览（30秒读懂生意，≤200字）
2. CDP 会员健康仪表盘（各等级分布 + 流失预警）
3. 跨门店对标（哪家店最需要关注）
4. 决策建议聚合（今日 Top3 最该做的事）
5. 唤醒效果追踪（Sprint 3 KPI 达成看板）

定位：老板看得见，管得住，能落地
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.consumer_identity import ConsumerIdentity
from src.models.order import Order
from src.models.private_domain import PrivateDomainMember

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def format_boss_brief(
    revenue_yuan: float,
    order_count: int,
    new_consumers: int,
    dormant_wakeup_sent: int,
    vip_at_risk: int,
    top_issue: str,
) -> str:
    """
    生成老板30秒速览简报（≤200字）

    包含：营收 + 客流 + 新客 + 唤醒 + 风险 + 首要行动
    """
    parts = []
    parts.append(f"今日营收¥{revenue_yuan:,.0f}，共{order_count}单。")

    if new_consumers > 0:
        parts.append(f"新增{new_consumers}位客户。")

    if dormant_wakeup_sent > 0:
        parts.append(f"本周已发送{dormant_wakeup_sent}条沉睡唤醒。")

    if vip_at_risk > 0:
        parts.append(f"注意：{vip_at_risk}位VIP客户有流失风险，建议尽快回访。")

    if top_issue:
        parts.append(f"建议行动：{top_issue}")

    text = "".join(parts)
    # 硬限制200字
    if len(text) > 200:
        text = text[:197] + "..."
    return text


def compute_member_health_score(
    s1_count: int,
    s2_count: int,
    s3_count: int,
    s4_count: int,
    s5_count: int,
) -> float:
    """
    会员健康评分（0-100）

    权重：S1=100, S2=80, S3=60, S4=30, S5=0
    """
    total = s1_count + s2_count + s3_count + s4_count + s5_count
    if total == 0:
        return 0.0
    score = (s1_count * 100 + s2_count * 80 + s3_count * 60 + s4_count * 30 + s5_count * 0) / total
    return round(score, 1)


class BossAgentService:
    """BossAgent — 老板视角经营智能"""

    async def get_daily_brief(
        self,
        db: AsyncSession,
        store_id: str,
    ) -> dict:
        """
        老板每日经营速览

        聚合：今日营收 + 订单数 + 新客 + 唤醒进度 + VIP预警
        """
        today = datetime.utcnow().date()
        today_start = datetime.combine(today, datetime.min.time())

        # 今日营收 + 订单数
        order_stats = await db.execute(
            select(
                func.count(Order.id),
                func.coalesce(func.sum(Order.total_amount), 0),
            ).where(
                Order.store_id == store_id,
                Order.order_time >= today_start,
                Order.status != "cancelled",
            )
        )
        row = order_stats.one()
        order_count = row[0] or 0
        revenue = float(row[1] or 0)
        # total_amount 可能是分或元，统一处理
        revenue_yuan = revenue if revenue < 100000 else revenue / 100

        # 新增消费者（今日创建的 ConsumerIdentity）
        new_consumers = (
            await db.scalar(
                select(func.count(ConsumerIdentity.id)).where(
                    ConsumerIdentity.created_at >= today_start,
                    ConsumerIdentity.is_merged.is_(False),
                )
            )
            or 0
        )

        # 唤醒进度（本周）
        from src.services.member_agent_service import member_agent_service

        wakeup = await member_agent_service.get_wakeup_metrics(db, store_id)

        # VIP预警
        vip_alerts = await member_agent_service.get_vip_protection_alerts(db, store_id)

        # 确定首要行动
        top_issue = ""
        if vip_alerts:
            top_issue = f"回访{len(vip_alerts)}位VIP客户（最高消费¥{vip_alerts[0]['total_spent_yuan']}）"
        elif not wakeup.get("kpi_met"):
            gap = 50 - wakeup.get("sent_this_week", 0)
            top_issue = f"本周还差{gap}条唤醒消息达标"

        brief_text = format_boss_brief(
            revenue_yuan=revenue_yuan,
            order_count=order_count,
            new_consumers=new_consumers,
            dormant_wakeup_sent=wakeup.get("sent_this_week", 0),
            vip_at_risk=len(vip_alerts),
            top_issue=top_issue,
        )

        return {
            "brief": brief_text,
            "revenue_yuan": round(revenue_yuan, 2),
            "order_count": order_count,
            "new_consumers": new_consumers,
            "wakeup_kpi": wakeup,
            "vip_at_risk_count": len(vip_alerts),
            "vip_alerts": vip_alerts[:5],  # 前5条
            "top_action": top_issue,
            "generated_at": datetime.utcnow().isoformat(),
        }

    async def get_member_health_dashboard(
        self,
        db: AsyncSession,
        store_id: Optional[str] = None,
    ) -> dict:
        """
        CDP 会员健康仪表盘

        返回：各 RFM 等级分布 + 健康评分 + 趋势
        """
        where = [PrivateDomainMember.is_active.is_(True)]
        if store_id:
            where.append(PrivateDomainMember.store_id == store_id)

        # RFM 等级分布
        stmt = (
            select(
                PrivateDomainMember.rfm_level,
                func.count(PrivateDomainMember.id),
                func.coalesce(func.sum(PrivateDomainMember.monetary), 0),
            )
            .where(and_(*where))
            .group_by(PrivateDomainMember.rfm_level)
        )
        result = await db.execute(stmt)

        distribution = {}
        total = 0
        counts = {"S1": 0, "S2": 0, "S3": 0, "S4": 0, "S5": 0}
        for level, count, monetary_sum in result.all():
            lv = level or "unknown"
            distribution[lv] = {
                "count": count,
                "monetary_yuan": round(float(monetary_sum or 0) / 100, 2),
            }
            total += count
            if lv in counts:
                counts[lv] = count

        # 各等级占比
        for lv in distribution:
            distribution[lv]["percentage"] = round(distribution[lv]["count"] / total * 100, 1) if total > 0 else 0.0

        # 健康评分
        health_score = compute_member_health_score(
            counts["S1"],
            counts["S2"],
            counts["S3"],
            counts["S4"],
            counts["S5"],
        )

        # CDP 关联率
        linked = (
            await db.scalar(
                select(func.count(PrivateDomainMember.id)).where(
                    and_(
                        *where,
                        PrivateDomainMember.consumer_id.isnot(None),
                    )
                )
            )
            or 0
        )

        return {
            "total_members": total,
            "health_score": health_score,
            "distribution": distribution,
            "cdp_link_rate": round(linked / total, 4) if total > 0 else 0.0,
            "at_risk_count": counts["S4"] + counts["S5"],
        }

    async def get_multi_store_comparison(
        self,
        db: AsyncSession,
        store_ids: Optional[List[str]] = None,
    ) -> List[dict]:
        """
        跨门店会员健康对标（老板总部视角）

        按健康评分排序，标注需要关注的门店
        """
        # 获取所有门店的会员分布
        where = [PrivateDomainMember.is_active.is_(True)]
        if store_ids:
            where.append(PrivateDomainMember.store_id.in_(store_ids))

        stmt = (
            select(
                PrivateDomainMember.store_id,
                PrivateDomainMember.rfm_level,
                func.count(PrivateDomainMember.id),
            )
            .where(and_(*where))
            .group_by(PrivateDomainMember.store_id, PrivateDomainMember.rfm_level)
        )
        result = await db.execute(stmt)

        # 按门店聚合
        store_data = {}
        for sid, level, count in result.all():
            if sid not in store_data:
                store_data[sid] = {"S1": 0, "S2": 0, "S3": 0, "S4": 0, "S5": 0, "total": 0}
            lv = level or "S3"
            if lv in store_data[sid]:
                store_data[sid][lv] = count
            store_data[sid]["total"] += count

        # 计算评分并排序
        stores = []
        for sid, data in store_data.items():
            score = compute_member_health_score(
                data["S1"],
                data["S2"],
                data["S3"],
                data["S4"],
                data["S5"],
            )
            at_risk_rate = (data["S4"] + data["S5"]) / data["total"] if data["total"] > 0 else 0.0
            stores.append(
                {
                    "store_id": sid,
                    "total_members": data["total"],
                    "health_score": score,
                    "s1_count": data["S1"],
                    "at_risk_count": data["S4"] + data["S5"],
                    "at_risk_rate": round(at_risk_rate, 4),
                    "needs_attention": at_risk_rate > 0.3 or score < 40,
                }
            )

        stores.sort(key=lambda x: x["health_score"])
        return stores


# 全局单例
boss_agent_service = BossAgentService()
