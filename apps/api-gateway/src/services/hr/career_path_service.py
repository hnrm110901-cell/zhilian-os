"""CareerPathService — WF-7 晋升路径推荐

基于技能图谱和餐饮行业岗位本体，计算最优晋升路径。
"""
import uuid
from typing import Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# 餐饮行业岗位晋升本体（简化版）
_CAREER_LADDER: dict[str, dict] = {
    "server": {
        "next_role": "senior_server",
        "required_skills": ["VIP接待", "客诉处理", "带新人"],
        "typical_months": 12,
        "salary_increase_yuan": 800,
    },
    "senior_server": {
        "next_role": "floor_manager",
        "required_skills": ["楼面管理", "排班优化", "服务质量监控"],
        "typical_months": 18,
        "salary_increase_yuan": 1500,
    },
    "chef": {
        "next_role": "head_chef",
        "required_skills": ["菜品研发", "成本控制", "厨房管理"],
        "typical_months": 24,
        "salary_increase_yuan": 2000,
    },
    "head_chef": {
        "next_role": "kitchen_director",
        "required_skills": ["菜单规划", "供应链管理", "食品安全体系"],
        "typical_months": 36,
        "salary_increase_yuan": 3000,
    },
    "manager": {
        "next_role": "area_manager",
        "required_skills": ["多店管理", "P&L分析", "团队建设"],
        "typical_months": 24,
        "salary_increase_yuan": 3000,
    },
}

_ROLE_LABELS: dict[str, str] = {
    "server": "服务员",
    "senior_server": "资深服务员",
    "floor_manager": "楼面经理",
    "chef": "厨师",
    "head_chef": "厨师长",
    "kitchen_director": "厨政总监",
    "manager": "店长",
    "area_manager": "区域经理",
}


class CareerPathService:

    async def recommend_next_role(
        self,
        current_role: str,
        current_skills: list[str],
        session: AsyncSession,
    ) -> dict:
        """推荐下一个晋升目标"""
        ladder = _CAREER_LADDER.get(current_role)
        if ladder is None:
            return {
                "current_role": current_role,
                "next_role": None,
                "message": "当前岗位暂无预设晋升路径",
            }

        required = set(ladder["required_skills"])
        achieved = set(current_skills)
        gap = required - achieved
        progress = len(required - gap) / max(len(required), 1) * 100

        return {
            "current_role": current_role,
            "current_role_label": _ROLE_LABELS.get(current_role, current_role),
            "next_role": ladder["next_role"],
            "next_role_label": _ROLE_LABELS.get(ladder["next_role"], ladder["next_role"]),
            "required_skills": sorted(required),
            "achieved_skills": sorted(achieved & required),
            "skill_gap": sorted(gap),
            "progress_pct": round(progress, 1),
            "typical_months": ladder["typical_months"],
            "salary_increase_yuan": ladder["salary_increase_yuan"],
        }

    async def analyze_skill_gap_to_target(
        self,
        current_skills: list[str],
        target_role: str,
        session: AsyncSession,
    ) -> dict:
        """分析到目标岗位的技能差距"""
        ladder = _CAREER_LADDER.get(target_role)
        if ladder is None:
            return {"target_role": target_role, "gap": [], "message": "目标岗位不在晋升路径中"}

        required = set(ladder["required_skills"])
        gap = sorted(required - set(current_skills))
        estimated_weeks = len(gap) * 4  # 每个技能约4周

        return {
            "target_role": target_role,
            "target_role_label": _ROLE_LABELS.get(target_role, target_role),
            "skill_gap": gap,
            "gap_count": len(gap),
            "estimated_weeks": estimated_weeks,
            "salary_increase_yuan": ladder["salary_increase_yuan"],
        }

    async def compare_with_peers(
        self,
        current_role: str,
        current_skills: list[str],
        tenure_months: int,
        session: AsyncSession,
    ) -> dict:
        """与同岗位同期员工对比（基于行业基准）"""
        # 行业基准：同岗位12个月应掌握的技能数
        benchmark_skills_12m: dict[str, int] = {
            "server": 4,
            "chef": 3,
            "manager": 4,
        }
        benchmark = benchmark_skills_12m.get(current_role, 3)
        expected_at_tenure = round(benchmark * min(tenure_months, 12) / 12)
        actual = len(current_skills)

        if actual >= expected_at_tenure:
            percentile = min(90, 50 + (actual - expected_at_tenure) * 15)
        else:
            percentile = max(10, 50 - (expected_at_tenure - actual) * 15)

        delta = actual - expected_at_tenure

        return {
            "current_role": current_role,
            "tenure_months": tenure_months,
            "skill_count": actual,
            "expected_skill_count": expected_at_tenure,
            "skill_delta": delta,
            "percentile": percentile,
            "assessment": "超越同期" if delta > 0 else "持平" if delta == 0 else "需加速成长",
        }
