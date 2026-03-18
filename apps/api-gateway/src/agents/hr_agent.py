"""HRAgent v1 — B级规则驱动诊断Agent.

支持意图:
- retention_risk: 离职风险扫描 (WF-1)
- skill_gaps: 技能差距分析 (WF-3)
- staffing: 人力配置诊断 (预留，M3实现)

不含ML预测，纯规则+启发式评分。
"""
import time
import uuid as uuid_mod
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
import structlog

from src.core.base_agent import AgentResponse, BaseAgent
from src.core.database import AsyncSessionLocal
from src.services.hr.knowledge_service import HrKnowledgeService
from src.services.hr.retention_risk_service import RetentionRiskService
from src.services.hr.skill_gap_service import SkillGapService

logger = structlog.get_logger()

# Lazy import — 避免 sklearn 未安装时崩溃
_retention_ml_cls = None


def _get_retention_ml_cls():
    global _retention_ml_cls
    if _retention_ml_cls is None:
        try:
            from src.services.hr.retention_ml_service import RetentionMLService
            _retention_ml_cls = RetentionMLService
        except ImportError:
            logger.warning("hr_agent.retention_ml_import_failed")
    return _retention_ml_cls


_SUPPORTED_INTENTS = [
    "retention_risk",
    "skill_gaps",
    "staffing",
]


@dataclass
class HRDiagnosis:
    """Structured output of an HR diagnosis."""
    intent: str
    store_id: str
    summary: str
    recommendations: list = field(default_factory=list)
    high_risk_persons: list = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["generated_at"] = self.generated_at.isoformat()
        return result


class HRAgentV1(BaseAgent):
    """B级诊断Agent — 规则驱动，不含ML预测。"""

    def __init__(self):
        super().__init__(config={})

    def get_supported_actions(self) -> List[str]:
        return _SUPPORTED_INTENTS

    async def execute(self, action: str, params: Dict[str, Any]) -> AgentResponse:
        """BaseAgent interface: dispatch to diagnose()."""
        start = time.time()
        store_id = params.get("store_id", "")
        logger.info("hr_agent.execute", action=action, store_id=store_id)

        if not store_id:
            return AgentResponse(
                success=False,
                error="缺少必要参数: store_id",
                execution_time=time.time() - start,
            )

        try:
            async with AsyncSessionLocal() as session:
                diagnosis = await self.diagnose(
                    action,
                    store_id=store_id,
                    session=session,
                    person_id=params.get("person_id"),
                )
            return AgentResponse(
                success=True,
                data=diagnosis.to_dict(),
                execution_time=time.time() - start,
            )
        except Exception as exc:
            logger.error("hr_agent.execute_error", action=action, error=str(exc))
            return AgentResponse(
                success=False,
                error=str(exc),
                execution_time=time.time() - start,
            )

    async def diagnose(
        self,
        intent: str,
        store_id: str,
        session=None,
        person_id: Optional[str] = None,
        **kwargs,
    ) -> HRDiagnosis:
        """Main entry point. Routes to appropriate diagnosis method."""
        if intent == "retention_risk":
            if person_id:
                return await self._predict_retention_risk(store_id, session, person_id)
            return await self._diagnose_retention(store_id, session)
        elif intent == "skill_gaps":
            return await self._diagnose_skill_gaps(store_id, session, person_id)
        elif intent == "staffing":
            return await self._diagnose_staffing(store_id, session)
        else:
            return HRDiagnosis(
                intent=intent,
                store_id=store_id,
                summary=f"不支持的诊断意图: {intent}。支持: {', '.join(_SUPPORTED_INTENTS)}",
            )

    async def _diagnose_retention(self, store_id: str, session) -> HRDiagnosis:
        """WF-1: scan store for retention risk, enrich with knowledge rules."""
        # Resolve store → org_node_id
        org_result = await session.execute(
            sa.text("SELECT org_node_id FROM stores WHERE id = :store_id"),
            {"store_id": store_id},
        )
        org_node_id = org_result.scalar_one_or_none()
        if not org_node_id:
            return HRDiagnosis(
                intent="retention_risk",
                store_id=store_id,
                summary=f"门店 {store_id} 未配置组织节点，无法扫描",
            )

        rrs = RetentionRiskService(session=session)
        high_risk, _ = await rrs.scan_store(org_node_id)

        # Enrich with knowledge rules for recommendations
        ks = HrKnowledgeService(session=session)
        turnover_rules = await ks.query_rules(category="turnover")

        recommendations = []
        for rule in turnover_rules:
            action = rule.get("action", {})
            recommendations.append({
                "action": action.get("recommend", "面谈了解诉求"),
                "expected_yuan": 3000.00,
                "confidence": rule.get("confidence", 0.8),
                "source": "hr_knowledge_rule",
            })

        # If no rules available, provide a default recommendation
        if not recommendations and high_risk:
            recommendations.append({
                "action": "安排1对1面谈，了解离职意向并制定挽留方案",
                "expected_yuan": 3000.00,
                "confidence": 0.7,
                "source": "default_heuristic",
            })

        summary = (
            f"扫描完成：发现 {len(high_risk)} 名高风险员工"
            if high_risk
            else "扫描完成：无高风险员工（0名超过阈值0.70）"
        )

        return HRDiagnosis(
            intent="retention_risk",
            store_id=store_id,
            summary=summary,
            recommendations=recommendations,
            high_risk_persons=high_risk,
        )

    async def _predict_retention_risk(
        self, store_id: str, session, person_id: str
    ) -> HRDiagnosis:
        """C级 ML预测 — 有 person_id 时走 ML路径，失败回退 B级扫描。"""
        redis_client = None
        try:
            import redis as redis_lib
            from src.core.config import settings
            redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=False)
        except Exception:
            logger.warning("hr_agent.redis_connect_failed", store_id=store_id)

        MLSvc = _get_retention_ml_cls()
        if MLSvc is None:
            return await self._diagnose_retention(store_id, session)

        svc = MLSvc(session=session, redis_client=redis_client)
        prediction = await svc.predict(
            person_id=uuid_mod.UUID(person_id), store_id=store_id
        )

        level = prediction["risk_level"]
        score = prediction["risk_score"]
        source = prediction["prediction_source"]
        summary = f"ML预测 [{source}]: 离职风险 {level} (score={score:.2f})"

        return HRDiagnosis(
            intent="retention_risk",
            store_id=store_id,
            summary=summary,
            recommendations=[prediction.get("intervention", {})],
            high_risk_persons=[prediction] if level == "high" else [],
        )

    async def _diagnose_skill_gaps(
        self, store_id: str, session, person_id: Optional[str] = None
    ) -> HRDiagnosis:
        """WF-3: skill gap analysis with revenue impact."""
        org_result = await session.execute(
            sa.text("SELECT org_node_id FROM stores WHERE id = :store_id"),
            {"store_id": store_id},
        )
        org_node_id = org_result.scalar_one_or_none()
        if not org_node_id:
            return HRDiagnosis(
                intent="skill_gaps",
                store_id=store_id,
                summary=f"门店 {store_id} 未配置组织节点",
            )

        sgs = SkillGapService(session=session)

        if person_id:
            analyses = [await sgs.analyze_person(uuid_mod.UUID(person_id))]
        else:
            analyses = await sgs.analyze_store(org_node_id)

        recommendations = []
        total_potential = 0.0
        for analysis in analyses:
            next_skill = analysis.get("next_recommended")
            if next_skill:
                lift = float(next_skill.get("estimated_revenue_lift", 0) or 0)
                total_potential += lift
                if lift > 0:
                    recommendations.append({
                        "action": f"培训 {next_skill['skill_name']}",
                        "expected_yuan": lift,
                        "confidence": 0.75,
                        "person_id": analysis["person_id"],
                        "source": "skill_gap_analysis",
                    })

        summary = (
            f"技能差距分析：{len(analyses)} 人，总潜在提升 "
            f"¥{total_potential:.2f}/月"
        )

        return HRDiagnosis(
            intent="skill_gaps",
            store_id=store_id,
            summary=summary,
            recommendations=recommendations,
        )

    async def _diagnose_staffing(self, store_id: str, session) -> HRDiagnosis:
        """WF-2: 排班健康度诊断 — 调用 StaffingService."""
        from datetime import date as date_cls
        redis_client = None
        try:
            import redis as redis_lib
            from src.core.config import settings
            redis_client = redis_lib.from_url(settings.REDIS_URL, decode_responses=False)
        except Exception:
            logger.warning("hr_agent.staffing_redis_failed", store_id=store_id)

        from src.services.hr.staffing_service import StaffingService
        svc = StaffingService(session=session, redis_client=redis_client)
        d = await svc.diagnose_staffing(store_id, date_cls.today())

        peak = d.get("peak_hours", [])
        savings = d.get("estimated_savings_yuan", 0.0)
        understaffed = d.get("understaffed_hours", [])
        overstaffed = d.get("overstaffed_hours", [])
        confidence = d.get("confidence", 0.0)

        summary = (
            f"排班诊断 (置信度{confidence:.0%})："
            f"峰值 {peak}，缺编 {understaffed}，超编 {overstaffed}，可节省 ¥{savings:.2f}"
        )
        recommendations = []
        if understaffed:
            recommendations.append({
                "action": f"在 {understaffed} 时段增加排班",
                "expected_yuan": 0.0,
                "confidence": confidence,
                "source": "staffing_service",
            })
        if savings > 0:
            recommendations.append({
                "action": f"减少 {overstaffed} 超编，可节省 ¥{savings:.2f}",
                "expected_yuan": savings,
                "confidence": confidence,
                "source": "staffing_service",
            })

        return HRDiagnosis(
            intent="staffing", store_id=store_id,
            summary=summary, recommendations=recommendations,
        )
