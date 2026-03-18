"""TalentPipelineService — WF-5 新店人才梯队复制流.

功能：
1. analyze(new_store_org_node_id, open_date, headcount_plan)
   → 分析岗位需求矩阵
   → 扫描集团内 employment_assignments 识别内部储备人员
   → 识别技能缺口 → 生成培训时间线
   → 输出「人才就绪率」+ 补招建议（含¥预算）

纯函数：
- _compute_readiness_score(required, available) → float
- _estimate_recruit_cost(headcount) → float （元，行业基准：月薪×50%）
- _build_training_timeline(open_date_str, gap_count) → list[dict]
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 行业基准：连锁餐饮各岗位月薪（元），用于估算补招成本
_POSITION_SALARY_BASELINE: dict[str, float] = {
    "kitchen":    4500.0,
    "service":    3800.0,
    "cashier":    3600.0,
    "supervisor": 6000.0,
    "manager":    9000.0,
    "default":    4000.0,
}

# 默认岗位需求（若 headcount_plan 为 None）
_DEFAULT_HEADCOUNT: dict[str, int] = {
    "kitchen":    5,
    "service":    8,
    "cashier":    2,
    "supervisor": 2,
    "manager":    1,
}


def _compute_readiness_score(required: int, available: int) -> float:
    """纯函数：计算人才就绪率（0.0–1.0）.

    available > required 时仍返回 1.0（超配），不超过 100%。
    """
    if required <= 0:
        return 1.0
    return round(min(1.0, available / required), 4)


def _estimate_recruit_cost(position: str, headcount: int) -> float:
    """纯函数：估算补招成本（元）.

    公式：行业基准月薪 × 50%（替换成本） × 需补招人数
    """
    base_salary = _POSITION_SALARY_BASELINE.get(position, _POSITION_SALARY_BASELINE["default"])
    return round(base_salary * 0.5 * headcount, 2)


def _build_training_timeline(open_date_str: Optional[str], gap_count: int) -> list:
    """纯函数：基于技能缺口数生成培训时间线.

    每个缺口技能估算2周培训时间，时间线从今日开始，以开业日为截止。
    gap_count == 0 时返回空列表。
    """
    if gap_count <= 0:
        return []

    try:
        open_date = date.fromisoformat(open_date_str) if open_date_str else None
    except ValueError:
        open_date = None

    today = date.today()
    timeline = []
    weeks_per_gap = 2

    for i in range(min(gap_count, 8)):  # 最多显示8个里程碑
        milestone_date = today + timedelta(weeks=(i + 1) * weeks_per_gap)
        if open_date and milestone_date > open_date:
            # 培训时间超出开业日，标记为「紧急」
            milestone_date = open_date - timedelta(days=3)
            timeline.append({
                "week": i + 1,
                "milestone": f"技能缺口 #{i+1} 快速培训",
                "target_date": milestone_date.isoformat(),
                "urgent": True,
            })
            break
        timeline.append({
            "week": i + 1,
            "milestone": f"技能缺口 #{i+1} 培训完成",
            "target_date": milestone_date.isoformat(),
            "urgent": False,
        })

    return timeline


class TalentPipelineService:
    """WF-5 新店人才梯队复制流主服务."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def analyze(
        self,
        new_store_org_node_id: str,
        open_date: Optional[str] = None,
        headcount_plan: Optional[dict] = None,
    ) -> dict:
        """WF-5 核心分析：内部储备 → 技能缺口 → 就绪率 → 补招建议.

        数据库不可用时降级：返回空候选人列表 + 0就绪率，不抛异常。
        """
        plan = headcount_plan or _DEFAULT_HEADCOUNT
        total_required = sum(plan.values())

        # ── 1. 扫描集团内活跃在职人员 ─────────────────────────────────
        candidates = []
        try:
            # 集团内活跃员工 + 已认证技能数 + 最新风险分
            result = await self._session.execute(
                sa.text(
                    "SELECT p.id, p.name, p.phone, "
                    "       ea.id AS assignment_id, ea.employment_type, "
                    "       js.title AS job_title, "
                    "       (SELECT COUNT(*) FROM person_achievements pa2 "
                    "        WHERE pa2.person_id = p.id) AS skill_count, "
                    "       (SELECT rs.risk_score FROM retention_signals rs "
                    "        WHERE rs.assignment_id = ea.id "
                    "        ORDER BY rs.computed_at DESC LIMIT 1) AS risk_score, "
                    "       s.name AS current_store, s.id AS current_store_id "
                    "FROM persons p "
                    "JOIN employment_assignments ea ON ea.person_id = p.id "
                    "JOIN org_nodes on_node ON on_node.id = ea.org_node_id "
                    "LEFT JOIN stores s ON s.org_node_id = ea.org_node_id "
                    "LEFT JOIN job_standards js ON js.id = ea.job_standard_id "
                    "WHERE on_node.root_id = ("
                    "  SELECT root_id FROM org_nodes WHERE id = :target_node_id"
                    ") "
                    "  AND ea.org_node_id != :target_node_id "
                    "  AND ea.status = 'active' "
                    "ORDER BY skill_count DESC, risk_score ASC NULLS LAST "
                    "LIMIT 30"
                ),
                {"target_node_id": new_store_org_node_id},
            )
            rows = result.fetchall()
            candidates = [
                {
                    "person_id": str(r.id),
                    "name": r.name,
                    "phone": r.phone,
                    "job_title": r.job_title,
                    "skill_count": int(r.skill_count or 0),
                    "risk_score": float(r.risk_score) if r.risk_score is not None else None,
                    "current_store": r.current_store,
                    "current_store_id": str(r.current_store_id) if r.current_store_id else None,
                    "transfer_eligible": (r.risk_score or 0) < 0.5,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning(
                "talent_pipeline.candidates_failed",
                org_node_id=new_store_org_node_id,
                error=str(exc),
            )

        # ── 2. 技能缺口分析 ────────────────────────────────────────────
        skill_gaps = []
        try:
            # 集团内全部 skill_nodes vs 新店候选人已有认证技能
            candidate_ids = [c["person_id"] for c in candidates]

            if candidate_ids:
                # 统计候选人群体已掌握的技能
                placeholders = ", ".join(f":p{i}" for i in range(len(candidate_ids)))
                params = {f"p{i}": cid for i, cid in enumerate(candidate_ids)}
                params["target_node_id"] = new_store_org_node_id

                gap_result = await self._session.execute(
                    sa.text(
                        "SELECT sn.id, sn.skill_name, sn.category, "
                        f"       sn.estimated_revenue_lift, "
                        f"       (SELECT COUNT(*) FROM person_achievements pa "
                        f"        WHERE pa.skill_node_id = sn.id "
                        f"        AND pa.person_id IN ({placeholders})) AS holder_count "
                        "FROM skill_nodes sn "
                        "WHERE sn.is_active IS NOT FALSE "
                        "ORDER BY sn.estimated_revenue_lift DESC NULLS LAST "
                        "LIMIT 20"
                    ),
                    params,
                )
            else:
                gap_result = await self._session.execute(
                    sa.text(
                        "SELECT id, skill_name, category, estimated_revenue_lift, "
                        "       0 AS holder_count "
                        "FROM skill_nodes "
                        "WHERE is_active IS NOT FALSE "
                        "ORDER BY estimated_revenue_lift DESC NULLS LAST "
                        "LIMIT 20"
                    ),
                )

            for r in gap_result.fetchall():
                holder_count = int(r.holder_count or 0)
                if holder_count < 2:  # 少于2人掌握 = 技能缺口
                    skill_gaps.append({
                        "skill_name": r.skill_name,
                        "category": r.category,
                        "holder_count": holder_count,
                        "estimated_revenue_lift": float(r.estimated_revenue_lift)
                            if r.estimated_revenue_lift else None,
                        "urgency": "high" if holder_count == 0 else "medium",
                    })
        except Exception as exc:
            logger.warning(
                "talent_pipeline.skill_gaps_failed",
                org_node_id=new_store_org_node_id,
                error=str(exc),
            )

        # ── 3. 就绪率 & 补招建议 ───────────────────────────────────────
        eligible_count = sum(1 for c in candidates if c.get("transfer_eligible"))
        readiness_score = _compute_readiness_score(total_required, eligible_count)

        # 按岗位估算补招人数和成本
        recruit_plan = []
        total_recruit_cost = 0.0
        for position, required in plan.items():
            available_for_pos = min(eligible_count, required)
            shortage = max(0, required - available_for_pos)
            if shortage > 0:
                cost = _estimate_recruit_cost(position, shortage)
                total_recruit_cost += cost
                recruit_plan.append({
                    "position": position,
                    "required": required,
                    "internal_available": available_for_pos,
                    "shortage": shortage,
                    "recruit_cost_yuan": cost,
                })

        # ── 4. 培训时间线 ──────────────────────────────────────────────
        training_timeline = _build_training_timeline(open_date, len(skill_gaps))

        logger.info(
            "talent_pipeline.analyzed",
            org_node_id=new_store_org_node_id,
            candidates=len(candidates),
            skill_gaps=len(skill_gaps),
            readiness_score=readiness_score,
        )

        return {
            "new_store_org_node_id": new_store_org_node_id,
            "open_date": open_date,
            "headcount_plan": plan,
            "total_required": total_required,
            "eligible_candidates_count": eligible_count,
            "readiness_score": readiness_score,
            "readiness_pct": round(readiness_score * 100, 1),
            "candidates": candidates[:10],  # 仅返回Top10候选人
            "skill_gaps": skill_gaps,
            "recruit_plan": recruit_plan,
            "total_recruit_cost_yuan": round(total_recruit_cost, 2),
            "training_timeline": training_timeline,
        }
