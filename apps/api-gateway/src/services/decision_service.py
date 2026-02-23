"""
Decision Agent Service with Database Integration
Provides decision support using real database data
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from collections import defaultdict
from statistics import mean
import os

from src.core.database import get_db_session
from src.models import KPI, KPIRecord, Store
from src.repositories import KPIRepository


class DecisionService:
    """Decision service using database"""

    def __init__(self, store_id: str = "STORE001"):
        self.store_id = store_id

    async def get_decision_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive decision report from database

        Args:
            start_date: Start date (ISO format)
            end_date: End date (ISO format)

        Returns:
            Decision report with KPIs, insights, and recommendations
        """
        async with get_db_session() as session:
            # Parse dates
            if not end_date:
                end_dt = date.today()
            else:
                end_dt = date.fromisoformat(end_date.split('T')[0])

            if not start_date:
                start_dt = end_dt - timedelta(days=int(os.getenv("DECISION_DEFAULT_DAYS", "30")))
            else:
                start_dt = date.fromisoformat(start_date.split('T')[0])

            # Get KPI data from database
            kpis = await self._get_kpis_from_db(session, start_dt, end_dt)

            # Calculate KPI summary
            kpi_summary = self._calculate_kpi_summary(kpis)

            # Generate insights based on real data
            insights = await self._generate_insights_from_db(session, kpis)

            # Generate recommendations
            recommendations = self._generate_recommendations(kpis, insights)

            # Calculate overall health score
            health_score = self._calculate_health_score(kpis)

            return {
                "store_id": self.store_id,
                "report_date": datetime.now().isoformat(),
                "period_start": start_dt.isoformat(),
                "period_end": end_dt.isoformat(),
                "kpi_summary": kpi_summary,
                "insights_summary": {
                    "total_insights": len(insights),
                    "high_impact": sum(1 for i in insights if i["impact_level"] == "high"),
                    "key_insights": insights[:5]
                },
                "recommendations_summary": {
                    "total_recommendations": len(recommendations),
                    "priority_distribution": self._count_by_priority(recommendations),
                    "critical_recommendations": [
                        r for r in recommendations if r["priority"] == "critical"
                    ][:5]
                },
                "overall_health_score": health_score,
                "action_required": sum(
                    1 for r in recommendations if r["priority"] in ["critical", "high"]
                )
            }

    async def _get_kpis_from_db(
        self,
        session: AsyncSession,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """Get KPI data from database - optimized to avoid N+1 queries"""
        from sqlalchemy import func, case
        from sqlalchemy.orm import aliased

        # Get all active KPIs
        kpi_defs = await KPIRepository.get_all_active(session)
        if not kpi_defs:
            return []

        kpi_ids = [kpi.id for kpi in kpi_defs]
        kpi_dict = {kpi.id: kpi for kpi in kpi_defs}

        # Use window function to get latest and previous records in a single query
        # This eliminates the N+1 query problem
        latest_subq = (
            select(
                KPIRecord.kpi_id,
                KPIRecord.value.label('current_value'),
                KPIRecord.target_value,
                KPIRecord.achievement_rate,
                KPIRecord.trend,
                KPIRecord.status,
                KPIRecord.record_date,
                func.row_number().over(
                    partition_by=KPIRecord.kpi_id,
                    order_by=desc(KPIRecord.record_date)
                ).label('rn')
            )
            .where(
                and_(
                    KPIRecord.kpi_id.in_(kpi_ids),
                    KPIRecord.store_id == self.store_id,
                    KPIRecord.record_date <= end_date
                )
            )
            .subquery()
        )

        # Get latest records (rn = 1)
        latest_alias = aliased(latest_subq)
        latest_query = select(latest_alias).where(latest_alias.c.rn == 1)
        latest_result = await session.execute(latest_query)
        latest_records = {row.kpi_id: row for row in latest_result}

        # Get previous records (rn = 2)
        prev_alias = aliased(latest_subq)
        prev_query = select(prev_alias).where(prev_alias.c.rn == 2)
        prev_result = await session.execute(prev_query)
        prev_records = {row.kpi_id: row for row in prev_result}

        # Build KPI data list
        kpis = []
        for kpi_id, latest_record in latest_records.items():
            kpi_def = kpi_dict.get(kpi_id)
            if not kpi_def:
                continue

            prev_record = prev_records.get(kpi_id)

            kpi_data = {
                "metric_id": kpi_def.id,
                "metric_name": kpi_def.name,
                "category": kpi_def.category,
                "current_value": latest_record.current_value,
                "target_value": latest_record.target_value or kpi_def.target_value,
                "previous_value": prev_record.current_value if prev_record else latest_record.current_value,
                "unit": kpi_def.unit,
                "achievement_rate": latest_record.achievement_rate or 0,
                "trend": latest_record.trend or "stable",
                "status": latest_record.status or "on_track"
            }
            kpis.append(kpi_data)

        return kpis

    def _calculate_kpi_summary(self, kpis: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate KPI summary statistics"""
        status_counts = defaultdict(int)
        for kpi in kpis:
            status_counts[kpi["status"]] += 1

        on_track_rate = status_counts["on_track"] / len(kpis) if kpis else 0

        return {
            "total_kpis": len(kpis),
            "status_distribution": dict(status_counts),
            "on_track_rate": on_track_rate,
            "key_kpis": kpis[:5]  # Top 5 KPIs
        }

    async def _generate_insights_from_db(
        self,
        session: AsyncSession,
        kpis: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Generate insights based on real KPI data"""
        insights = []

        # Analyze off-track KPIs
        for kpi in kpis:
            if kpi["status"] == "off_track":
                insight = {
                    "insight_id": f"INSIGHT_KPI_{kpi['metric_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "title": f"{kpi['metric_name']}未达标",
                    "description": f"{kpi['metric_name']}当前为{kpi['current_value']:.2f}{kpi['unit']}，目标为{kpi['target_value']:.2f}{kpi['unit']}，达成率仅{kpi['achievement_rate']:.1%}",
                    "category": kpi["category"],
                    "impact_level": "high" if kpi["achievement_rate"] < float(os.getenv("DECISION_HIGH_IMPACT_THRESHOLD", "0.80")) else "medium",
                    "data_points": [
                        {"label": "当前值", "value": kpi["current_value"]},
                        {"label": "目标值", "value": kpi["target_value"]},
                        {"label": "达成率", "value": kpi["achievement_rate"]}
                    ],
                    "discovered_at": datetime.now().isoformat()
                }
                insights.append(insight)

        # Add general insights if no specific issues
        if not insights:
            insights.append({
                "insight_id": f"INSIGHT_GENERAL_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "title": "整体运营良好",
                "description": "所有KPI指标均在正常范围内，建议继续保持当前运营策略",
                "category": "general",
                "impact_level": "low",
                "data_points": [],
                "discovered_at": datetime.now().isoformat()
            })

        return insights

    def _generate_recommendations(
        self,
        kpis: List[Dict[str, Any]],
        insights: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Generate recommendations based on KPIs and insights"""
        recommendations = []

        # Generate recommendations for off-track KPIs
        for kpi in kpis:
            if kpi["status"] == "off_track":
                priority = "critical" if kpi["achievement_rate"] < 0.80 else "high"

                recommendation = {
                    "recommendation_id": f"REC_KPI_{kpi['metric_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "title": f"改善{kpi['metric_name']}",
                    "description": f"当前{kpi['metric_name']}为{kpi['current_value']:.2f}{kpi['unit']}，需要提升至目标值{kpi['target_value']:.2f}{kpi['unit']}",
                    "decision_type": "tactical",
                    "priority": priority,
                    "rationale": f"达成率仅{kpi['achievement_rate']:.1%}，低于预期",
                    "expected_impact": f"提升{kpi['metric_name']}至目标水平",
                    "action_items": [
                        "分析根本原因",
                        "制定改进计划",
                        "实施并监控效果"
                    ],
                    "estimated_cost": None,
                    "estimated_roi": None,
                    "created_at": datetime.now().isoformat()
                }
                recommendations.append(recommendation)

        return recommendations

    def _calculate_health_score(self, kpis: List[Dict[str, Any]]) -> float:
        """Calculate overall health score"""
        if not kpis:
            return 0.0

        achievement_rates = [kpi["achievement_rate"] for kpi in kpis]
        avg_achievement = mean(achievement_rates)

        # Convert to 0-100 scale
        health_score = min(100, avg_achievement * 100)

        return round(health_score, 1)

    def _count_by_priority(self, recommendations: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count recommendations by priority"""
        counts = defaultdict(int)
        for rec in recommendations:
            counts[rec["priority"]] += 1
        return dict(counts)


# Create singleton instance
decision_service = DecisionService()
