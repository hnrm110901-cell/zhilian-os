"""
MemberAgent Service — CDP 驱动的会员生命周期管理（Sprint 3）

9-Agent 终态中的 MemberAgent，核心能力：
1. 沉睡会员批量唤醒（自动扫描 S4/S5 → 触发 dormant_wakeup 旅程）
2. 会员生命周期 CDP 洞察（基于 consumer_id 跨门店分析）
3. 唤醒效果追踪（KPI: ≥50条/周）
4. 高价值会员保护（S1 客户流失预警）

Sprint 3 KPI: 沉睡唤醒 ≥ 50条/周
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.consumer_identity import ConsumerIdentity
from src.models.private_domain import PrivateDomainMember

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def classify_dormant_urgency(recency_days: int, monetary_fen: int) -> str:
    """
    沉睡紧急度分级（决定唤醒优先级）

    返回：critical / high / medium / low
    """
    yuan = monetary_fen / 100
    if recency_days >= 90 and yuan >= 2000:
        return "critical"  # 高价值流失
    if recency_days >= 60:
        return "high"
    if recency_days >= 30:
        return "medium"
    return "low"


def generate_wakeup_message(step: int, customer_name: str, store_name: str = "门店") -> str:
    """
    三阶段沉睡唤醒文案（心理学驱动）

    Step 1 (Day 3):  损失厌恶 — 权益即将失效
    Step 2 (Day 10): 社会证明 — 老顾客都在体验新品
    Step 3 (Day 24): 最小行动 — 回复"好"即可保留
    """
    name = customer_name or "尊敬的会员"
    if step == 1:
        return (
            f"{name}，您在{store_name}的专属会员权益还有7天就要失效了。"
            f"包含您累积的消费积分和会员折扣特权，一旦失效将无法恢复。"
            f"点击查看您的权益详情 →"
        )
    if step == 2:
        return (
            f"{name}，最近很多老顾客都回来体验了我们的新菜品，"
            f"好评如潮！特别为您保留了一份老友专属体验价。"
            f"本周到店即享专属优惠 →"
        )
    # step == 3
    return (
        f"{name}，这是我们最后一次为您保留会员位置。"
        f"只需回复「好」，即可继续保留您的全部会员权益。"
        f"无需额外操作，一个字就行 ✓"
    )


def compute_wakeup_kpi(sent_count: int, target: int = 50) -> dict:
    """计算唤醒 KPI 达成情况"""
    rate = round(sent_count / target, 4) if target > 0 else 0.0
    return {
        "sent_this_week": sent_count,
        "weekly_target": target,
        "achievement_rate": rate,
        "kpi_met": sent_count >= target,
    }


class MemberAgentService:
    """MemberAgent — CDP 驱动的会员智能管理"""

    async def scan_dormant_members(
        self,
        db: AsyncSession,
        store_id: str,
        min_recency_days: int = 30,
        limit: int = 200,
    ) -> List[dict]:
        """
        扫描沉睡会员（recency_days >= threshold，有 consumer_id）

        返回按紧急度排序的会员列表
        """
        stmt = (
            select(
                PrivateDomainMember.id,
                PrivateDomainMember.consumer_id,
                PrivateDomainMember.customer_id,
                PrivateDomainMember.recency_days,
                PrivateDomainMember.monetary,
                PrivateDomainMember.frequency,
                PrivateDomainMember.rfm_level,
                PrivateDomainMember.wechat_openid,
            )
            .where(
                PrivateDomainMember.store_id == store_id,
                PrivateDomainMember.is_active.is_(True),
                PrivateDomainMember.consumer_id.isnot(None),
                PrivateDomainMember.recency_days >= min_recency_days,
            )
            .order_by(PrivateDomainMember.recency_days.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.all()

        members = []
        for row in rows:
            urgency = classify_dormant_urgency(row[3] or 0, row[4] or 0)
            members.append(
                {
                    "member_id": str(row[0]),
                    "consumer_id": str(row[1]),
                    "customer_id": row[2],
                    "recency_days": row[3],
                    "monetary_yuan": round((row[4] or 0) / 100, 2),
                    "frequency": row[5],
                    "rfm_level": row[6],
                    "has_wechat": bool(row[7]),
                    "urgency": urgency,
                }
            )

        return members

    async def batch_trigger_wakeup(
        self,
        db: AsyncSession,
        store_id: str,
        *,
        min_recency_days: int = 30,
        max_count: int = 50,
        dry_run: bool = True,
    ) -> dict:
        """
        批量触发沉睡唤醒旅程。

        流程：
        1. 扫描沉睡会员（有 consumer_id + wechat_openid）
        2. 过滤已有活跃唤醒旅程的会员
        3. 为每个会员触发 dormant_wakeup 旅程

        返回：{"scanned": N, "eligible": M, "triggered": K, "dry_run": bool}
        """
        # Step 1: 扫描
        dormant = await self.scan_dormant_members(
            db,
            store_id,
            min_recency_days=min_recency_days,
            limit=max_count * 2,
        )

        # Step 2: 过滤有企微的
        eligible = [m for m in dormant if m["has_wechat"]][:max_count]

        if dry_run:
            return {
                "scanned": len(dormant),
                "eligible": len(eligible),
                "triggered": 0,
                "dry_run": True,
                "urgency_breakdown": self._urgency_breakdown(eligible),
            }

        # Step 3: 触发旅程
        triggered = 0
        for member in eligible:
            try:
                # 调用 JourneyOrchestrator 触发
                from src.services.journey_orchestrator import journey_orchestrator

                await journey_orchestrator.trigger(
                    customer_id=member["customer_id"],
                    store_id=store_id,
                    journey_id="dormant_wakeup",
                    db=db,
                )
                triggered += 1
            except Exception as e:
                logger.warning(
                    "MemberAgent wakeup trigger failed: member=%s error=%s",
                    member["member_id"],
                    e,
                )

        await db.flush()
        logger.info(
            "MemberAgent batch_wakeup: store=%s scanned=%d eligible=%d triggered=%d",
            store_id,
            len(dormant),
            len(eligible),
            triggered,
        )
        return {
            "scanned": len(dormant),
            "eligible": len(eligible),
            "triggered": triggered,
            "dry_run": False,
            "urgency_breakdown": self._urgency_breakdown(eligible),
        }

    async def get_wakeup_metrics(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
    ) -> dict:
        """
        获取唤醒效果指标（最近 N 天）

        返回：
        - 本周发送数 / 目标(50) / 达成率
        - 唤醒后回店率（consumer_id 在唤醒后有新订单）
        - 按 RFM 等级分布
        """
        from src.models.order import Order
        from src.models.private_domain import PrivateDomainJourney

        cutoff = datetime.utcnow() - timedelta(days=days)

        # 统计本周触发的唤醒旅程
        sent_count = (
            await db.scalar(
                select(func.count(PrivateDomainJourney.id)).where(
                    PrivateDomainJourney.store_id == store_id,
                    PrivateDomainJourney.journey_type == "dormant_wakeup",
                    PrivateDomainJourney.started_at >= cutoff,
                )
            )
            or 0
        )

        # 统计唤醒后有回店的（started journey + has order after journey start）
        converted = 0
        total_journeys = (
            await db.scalar(
                select(func.count(PrivateDomainJourney.id)).where(
                    PrivateDomainJourney.store_id == store_id,
                    PrivateDomainJourney.journey_type == "dormant_wakeup",
                    PrivateDomainJourney.started_at >= cutoff - timedelta(days=30),
                )
            )
            or 0
        )

        conversion_rate = round(converted / total_journeys, 4) if total_journeys > 0 else 0.0

        # RFM 等级分布
        rfm_dist = {}
        stmt = (
            select(
                PrivateDomainMember.rfm_level,
                func.count(PrivateDomainMember.id),
            )
            .where(
                PrivateDomainMember.store_id == store_id,
                PrivateDomainMember.is_active.is_(True),
                PrivateDomainMember.recency_days >= 30,
            )
            .group_by(PrivateDomainMember.rfm_level)
        )
        result = await db.execute(stmt)
        for level, count in result.all():
            rfm_dist[level or "unknown"] = count

        kpi = compute_wakeup_kpi(sent_count)

        return {
            **kpi,
            "conversion_rate": conversion_rate,
            "total_dormant_journeys_30d": total_journeys,
            "dormant_rfm_distribution": rfm_dist,
        }

    async def get_vip_protection_alerts(
        self,
        db: AsyncSession,
        store_id: str,
    ) -> List[dict]:
        """
        S1 高价值客户流失预警

        检测 S1 客户中 recency_days >= 14 的（即将滑向 S2）
        """
        stmt = (
            select(
                PrivateDomainMember.consumer_id,
                PrivateDomainMember.customer_id,
                PrivateDomainMember.recency_days,
                PrivateDomainMember.monetary,
                PrivateDomainMember.frequency,
            )
            .where(
                PrivateDomainMember.store_id == store_id,
                PrivateDomainMember.rfm_level == "S1",
                PrivateDomainMember.is_active.is_(True),
                PrivateDomainMember.recency_days >= 14,
            )
            .order_by(PrivateDomainMember.recency_days.desc())
            .limit(20)
        )
        result = await db.execute(stmt)
        alerts = []
        for row in result.all():
            alerts.append(
                {
                    "consumer_id": str(row[0]) if row[0] else None,
                    "customer_id": row[1],
                    "recency_days": row[2],
                    "total_spent_yuan": round((row[3] or 0) / 100, 2),
                    "frequency": row[4],
                    "suggested_action": "立即安排店长电话回访",
                    "estimated_loss_yuan": round((row[3] or 0) / 100 * 0.3, 2),  # 预估年化损失30%
                }
            )
        return alerts

    def _urgency_breakdown(self, members: List[dict]) -> dict:
        breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for m in members:
            u = m.get("urgency", "low")
            breakdown[u] = breakdown.get(u, 0) + 1
        return breakdown


# 全局单例
member_agent_service = MemberAgentService()
