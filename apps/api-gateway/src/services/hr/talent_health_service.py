"""TalentHealthService — WF-9 门店人才健康度大盘

触发：HQ大盘页面加载 / 每周报告推送
能力：门店人才健康度评分、风险门店识别、人才流动图谱
"""
import uuid
from typing import Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class TalentHealthService:

    async def score_store(
        self,
        store_data: dict,
        session: AsyncSession,
    ) -> dict:
        """计算门店人才健康度评分

        store_data: {
            org_node_id, store_name,
            total_staff, turnover_count_90d,
            avg_skill_count, target_skill_count,
            avg_tenure_months, new_hire_count_90d
        }
        """
        total = store_data.get("total_staff", 0)
        if total == 0:
            return {
                "org_node_id": store_data.get("org_node_id"),
                "health_score": 0,
                "skill_coverage": 0,
                "stability_index": 0,
                "growth_rate": 0,
            }

        # 技能覆盖率（0-100）
        avg_skill = store_data.get("avg_skill_count", 0)
        target_skill = store_data.get("target_skill_count", 1)
        skill_coverage = round(min(avg_skill / max(target_skill, 1), 1.0) * 100, 1)

        # 人员稳定性（0-100，90天内离职率越低越好）
        turnover = store_data.get("turnover_count_90d", 0)
        turnover_rate = turnover / max(total, 1)
        stability_index = round(max(0, (1 - turnover_rate * 2)) * 100, 1)

        # 成长速度（0-100，新人占比+平均工龄综合）
        avg_tenure = store_data.get("avg_tenure_months", 0)
        new_hires = store_data.get("new_hire_count_90d", 0)
        growth_rate = round(min(1.0, (avg_tenure / 24 * 0.6 + (1 - new_hires / max(total, 1)) * 0.4)) * 100, 1)

        # 综合评分（加权平均）
        health_score = round(
            skill_coverage * 0.35 +
            stability_index * 0.40 +
            growth_rate * 0.25,
            1
        )

        return {
            "org_node_id": store_data.get("org_node_id"),
            "store_name": store_data.get("store_name", ""),
            "health_score": health_score,
            "skill_coverage": skill_coverage,
            "stability_index": stability_index,
            "growth_rate": growth_rate,
            "risk_level": "high" if health_score < 50 else "medium" if health_score < 70 else "low",
        }

    async def hq_dashboard(
        self,
        stores_data: list[dict],
        session: AsyncSession,
    ) -> dict:
        """HQ人才健康度大盘（多门店汇总）"""
        scores = []
        for sd in stores_data:
            score = await self.score_store(sd, session)
            scores.append(score)

        if not scores:
            return {"store_count": 0, "avg_health": 0, "risk_stores": [], "scores": []}

        avg_health = round(sum(s["health_score"] for s in scores) / len(scores), 1)
        risk_stores = [s for s in scores if s["risk_level"] == "high"]

        # 按health_score排序
        scores.sort(key=lambda x: x["health_score"])

        return {
            "store_count": len(scores),
            "avg_health_score": avg_health,
            "risk_store_count": len(risk_stores),
            "risk_stores": risk_stores,
            "all_scores": scores,
        }

    async def talent_flow_matrix(
        self,
        transfers: list[dict],
        session: AsyncSession,
    ) -> dict:
        """人才流向矩阵

        transfers: [{from_store, to_store, count}]
        """
        matrix: dict[str, dict[str, int]] = {}
        for t in transfers:
            src = t.get("from_store", "unknown")
            dst = t.get("to_store", "unknown")
            if src not in matrix:
                matrix[src] = {}
            matrix[src][dst] = matrix[src].get(dst, 0) + t.get("count", 1)

        total_transfers = sum(t.get("count", 1) for t in transfers)
        return {
            "total_transfers": total_transfers,
            "flow_matrix": matrix,
            "top_sources": sorted(
                [(k, sum(v.values())) for k, v in matrix.items()],
                key=lambda x: x[1], reverse=True
            )[:5],
        }
