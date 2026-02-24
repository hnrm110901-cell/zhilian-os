"""
AI决策演进度量服务
AI Evolution Metrics Service

核心价值：让客户用数据回答"AI这周帮我省了多少钱"
支撑RaaS商业模式的续费论证
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.core.database import get_db_session
from src.models.decision_log import DecisionLog, DecisionStatus, DecisionOutcome

logger = structlog.get_logger()


class AIEvolutionService:
    """AI决策演进度量服务"""

    async def get_adoption_rate(
        self,
        store_id: Optional[str] = None,
        days: int = 7,
    ) -> Dict[str, Any]:
        """
        建议采纳率统计

        Args:
            store_id: 门店ID（None=全部门店）
            days: 统计天数

        Returns:
            采纳率及分类明细
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        async with get_db_session() as session:
            filters = [DecisionLog.created_at >= cutoff]
            if store_id:
                filters.append(DecisionLog.store_id == store_id)

            result = await session.execute(
                select(
                    DecisionLog.decision_status,
                    func.count(DecisionLog.id).label("count"),
                ).where(and_(*filters)).group_by(DecisionLog.decision_status)
            )
            rows = result.all()

        counts: Dict[str, int] = {r.decision_status: r.count for r in rows}
        total = sum(counts.values()) or 1

        adopted = counts.get(DecisionStatus.APPROVED, 0) + counts.get(DecisionStatus.EXECUTED, 0)
        modified = counts.get(DecisionStatus.MODIFIED, 0)
        rejected = counts.get(DecisionStatus.REJECTED, 0)
        pending = counts.get(DecisionStatus.PENDING, 0)

        return {
            "period_days": days,
            "store_id": store_id,
            "total_suggestions": total,
            "adopted": adopted,
            "modified": modified,
            "rejected": rejected,
            "pending": pending,
            "adoption_rate": round(adopted / total, 4),
            "modification_rate": round(modified / total, 4),
            "rejection_rate": round(rejected / total, 4),
        }

    async def get_outcome_summary(
        self,
        store_id: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        采纳后实际效果汇总

        Returns:
            成本节省、营收影响、成功率
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        async with get_db_session() as session:
            filters = [
                DecisionLog.created_at >= cutoff,
                DecisionLog.outcome.isnot(None),
                DecisionLog.decision_status.in_([
                    DecisionStatus.APPROVED,
                    DecisionStatus.EXECUTED,
                    DecisionStatus.MODIFIED,
                ]),
            ]
            if store_id:
                filters.append(DecisionLog.store_id == store_id)

            result = await session.execute(
                select(
                    func.count(DecisionLog.id).label("total"),
                    func.sum(
                        case(
                            (DecisionLog.outcome == DecisionOutcome.SUCCESS, 1),
                            else_=0,
                        )
                    ).label("success_count"),
                    func.sum(DecisionLog.cost_impact).label("total_cost_impact"),
                    func.sum(DecisionLog.revenue_impact).label("total_revenue_impact"),
                    func.avg(DecisionLog.result_deviation).label("avg_deviation"),
                ).where(and_(*filters))
            )
            row = result.one()

        total = row.total or 0
        success = int(row.success_count or 0)

        return {
            "period_days": days,
            "store_id": store_id,
            "evaluated_decisions": total,
            "success_count": success,
            "success_rate": round(success / total, 4) if total else 0.0,
            "total_cost_saved_yuan": float(row.total_cost_impact or 0),
            "total_revenue_impact_yuan": float(row.total_revenue_impact or 0),
            "avg_result_deviation_pct": round(float(row.avg_deviation or 0), 2),
        }

    async def get_weekly_trend(
        self,
        store_id: Optional[str] = None,
        weeks: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        周维度采纳率趋势（用于折线图）

        Returns:
            按周排列的采纳率列表
        """
        trend = []
        now = datetime.utcnow()

        for i in range(weeks - 1, -1, -1):
            week_start = now - timedelta(weeks=i + 1)
            week_end = now - timedelta(weeks=i)

            async with get_db_session() as session:
                filters = [
                    DecisionLog.created_at >= week_start,
                    DecisionLog.created_at < week_end,
                ]
                if store_id:
                    filters.append(DecisionLog.store_id == store_id)

                result = await session.execute(
                    select(
                        DecisionLog.decision_status,
                        func.count(DecisionLog.id).label("count"),
                    ).where(and_(*filters)).group_by(DecisionLog.decision_status)
                )
                rows = result.all()

            counts = {r.decision_status: r.count for r in rows}
            total = sum(counts.values()) or 1
            adopted = counts.get(DecisionStatus.APPROVED, 0) + counts.get(DecisionStatus.EXECUTED, 0)

            trend.append({
                "week_start": week_start.strftime("%Y-%m-%d"),
                "week_end": week_end.strftime("%Y-%m-%d"),
                "total": total,
                "adopted": adopted,
                "adoption_rate": round(adopted / total, 4),
            })

        return trend

    async def get_hitl_escalation_trend(
        self,
        store_id: Optional[str] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        HITL升级次数趋势（高风险操作需人工介入的频率）

        Returns:
            升级次数及趋势
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        async with get_db_session() as session:
            filters = [
                DecisionLog.created_at >= cutoff,
                DecisionLog.approval_chain.isnot(None),
            ]
            if store_id:
                filters.append(DecisionLog.store_id == store_id)

            result = await session.execute(
                select(func.count(DecisionLog.id).label("escalations"))
                .where(and_(*filters))
            )
            escalations = result.scalar() or 0

            # 对比上一个同等周期
            prev_start = cutoff - timedelta(days=days)
            prev_filters = [
                DecisionLog.created_at >= prev_start,
                DecisionLog.created_at < cutoff,
                DecisionLog.approval_chain.isnot(None),
            ]
            if store_id:
                prev_filters.append(DecisionLog.store_id == store_id)

            prev_result = await session.execute(
                select(func.count(DecisionLog.id).label("prev_escalations"))
                .where(and_(*prev_filters))
            )
            prev_escalations = prev_result.scalar() or 0

        change_pct = (
            round((escalations - prev_escalations) / prev_escalations * 100, 1)
            if prev_escalations else None
        )

        return {
            "period_days": days,
            "store_id": store_id,
            "escalations": escalations,
            "prev_period_escalations": prev_escalations,
            "change_pct": change_pct,
            "trend": "down" if (change_pct or 0) < 0 else "up" if (change_pct or 0) > 0 else "flat",
        }

    async def get_agent_performance(
        self,
        store_id: Optional[str] = None,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        各Agent类型的建议质量对比

        Returns:
            按Agent分组的采纳率和效果
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        async with get_db_session() as session:
            filters = [DecisionLog.created_at >= cutoff]
            if store_id:
                filters.append(DecisionLog.store_id == store_id)

            result = await session.execute(
                select(
                    DecisionLog.agent_type,
                    func.count(DecisionLog.id).label("total"),
                    func.sum(
                        case(
                            (DecisionLog.decision_status.in_([
                                DecisionStatus.APPROVED,
                                DecisionStatus.EXECUTED,
                            ]), 1),
                            else_=0,
                        )
                    ).label("adopted"),
                    func.avg(DecisionLog.ai_confidence).label("avg_confidence"),
                    func.sum(DecisionLog.cost_impact).label("cost_impact"),
                ).where(and_(*filters)).group_by(DecisionLog.agent_type)
            )
            rows = result.all()

        return [
            {
                "agent_type": r.agent_type,
                "total_suggestions": r.total,
                "adopted": int(r.adopted or 0),
                "adoption_rate": round(int(r.adopted or 0) / r.total, 4) if r.total else 0.0,
                "avg_confidence": round(float(r.avg_confidence or 0), 3),
                "total_cost_impact_yuan": float(r.cost_impact or 0),
            }
            for r in rows
        ]
