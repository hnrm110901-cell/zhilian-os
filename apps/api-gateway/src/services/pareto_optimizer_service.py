"""
帕累托寻优器（Pareto Optimizer）
F-M-X-S-R 五维约束下的菜品方案优化引擎

五维模型：
  F (Flavor)      — 风味得分：配方与目标口味画像的匹配度
  M (Margin)      — 毛利率：(售价-BOM成本)/售价
  X (compleXity)  — 出品复杂度：工序数×技能要求×设备依赖（越低越好）
  S (Supply)      — 供应稳定性：食材可得率×价格波动×替代方案数
  R (Repurchase)  — 复购预测：同品类历史复购率×差异化系数

输出帕累托前沿上的非劣解集合，每个解标注"牺牲了什么、换来了什么"。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class DishCandidate:
    """一个菜品方案候选"""
    candidate_id: str
    name: str
    flavor_score: float       # F: 0-100
    margin_pct: float         # M: 0-100 (毛利率百分比)
    complexity_score: float   # X: 0-100 (越高越复杂，优化目标是越低越好)
    supply_score: float       # S: 0-100 (供应稳定性)
    repurchase_score: float   # R: 0-100 (复购预测)
    bom_cost_yuan: float = 0.0
    suggested_price_yuan: float = 0.0
    recipe_version_id: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParetoSolution:
    """帕累托前沿上的一个解"""
    candidate: DishCandidate
    rank: int                           # 1=最优
    weighted_score: float               # 加权综合分
    label: str                          # 方案标签（如"口味最优""性价比之王"）
    tradeoff_description: str           # 牺牲/换取说明
    dimension_scores: Dict[str, float]  # 五维原始分


# ── 纯函数 ────────────────────────────────────────────────────────────────────

def normalize_score(value: float, min_val: float = 0, max_val: float = 100) -> float:
    """将分数归一化到 0-1"""
    if max_val <= min_val:
        return 0.5
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))


def invert_complexity(complexity: float) -> float:
    """复杂度是越低越好，取反后越高越好"""
    return max(0, 100 - complexity)


def dominates(a: DishCandidate, b: DishCandidate) -> bool:
    """
    判断方案 a 是否帕累托支配方案 b。
    a 支配 b 条件：a 在所有维度 >= b，且至少一个维度 > b。
    注意：complexity 取反（越低越好）。
    """
    dims_a = [a.flavor_score, a.margin_pct, invert_complexity(a.complexity_score),
              a.supply_score, a.repurchase_score]
    dims_b = [b.flavor_score, b.margin_pct, invert_complexity(b.complexity_score),
              b.supply_score, b.repurchase_score]

    at_least_one_better = False
    for va, vb in zip(dims_a, dims_b):
        if va < vb:
            return False
        if va > vb:
            at_least_one_better = True
    return at_least_one_better


def find_pareto_front(candidates: List[DishCandidate]) -> List[DishCandidate]:
    """
    从候选集中找出帕累托前沿（非劣解集）。
    O(n^2) 算法，候选数通常 < 50，性能无问题。
    """
    if not candidates:
        return []

    front = []
    for c in candidates:
        is_dominated = any(dominates(other, c) for other in candidates if other.candidate_id != c.candidate_id)
        if not is_dominated:
            front.append(c)
    return front


def compute_weighted_score(
    candidate: DishCandidate,
    weights: Dict[str, float],
) -> float:
    """
    计算加权综合分。
    weights 示例: {"F": 0.25, "M": 0.30, "X": 0.15, "S": 0.15, "R": 0.15}
    """
    f = normalize_score(candidate.flavor_score)
    m = normalize_score(candidate.margin_pct)
    x = normalize_score(invert_complexity(candidate.complexity_score))
    s = normalize_score(candidate.supply_score)
    r = normalize_score(candidate.repurchase_score)

    score = (
        weights.get("F", 0.2) * f
        + weights.get("M", 0.3) * m
        + weights.get("X", 0.15) * x
        + weights.get("S", 0.15) * s
        + weights.get("R", 0.2) * r
    )
    return round(score * 100, 1)


def label_solution(candidate: DishCandidate, all_candidates: List[DishCandidate]) -> str:
    """根据候选在各维度的相对位置，生成方案标签"""
    if not all_candidates:
        return "默认方案"

    dims = {
        "flavor_score": "口味最优",
        "margin_pct": "性价比之王",
        "supply_score": "供应最稳",
        "repurchase_score": "复购潜力最高",
    }

    for attr, label in dims.items():
        val = getattr(candidate, attr)
        max_val = max(getattr(c, attr) for c in all_candidates)
        if val >= max_val and val > 0:
            return label

    # 复杂度最低
    min_complexity = min(c.complexity_score for c in all_candidates)
    if candidate.complexity_score <= min_complexity:
        return "出品最简"

    return "均衡方案"


def describe_tradeoff(candidate: DishCandidate, weights: Dict[str, float]) -> str:
    """生成该方案的牺牲/换取描述"""
    dims = [
        ("风味", candidate.flavor_score),
        ("毛利", candidate.margin_pct),
        ("简易度", invert_complexity(candidate.complexity_score)),
        ("供应", candidate.supply_score),
        ("复购", candidate.repurchase_score),
    ]
    sorted_dims = sorted(dims, key=lambda x: x[1], reverse=True)
    strengths = [d[0] for d in sorted_dims[:2]]
    weaknesses = [d[0] for d in sorted_dims[-1:] if d[1] < 60]

    parts = []
    parts.append(f"{'/'.join(strengths)}突出")
    if weaknesses:
        parts.append(f"{'、'.join(weaknesses)}偏弱")
    return "，".join(parts)


# ── 服务类 ────────────────────────────────────────────────────────────────────

DEFAULT_WEIGHTS = {"F": 0.20, "M": 0.30, "X": 0.15, "S": 0.15, "R": 0.20}


class ParetoOptimizerService:
    """
    帕累托寻优服务。

    使用方式：
    1. 从 RecipeVersion + CostModel 构建 DishCandidate 列表
    2. 调用 optimize() 获取帕累托前沿 + 加权排名
    """

    def optimize(
        self,
        candidates: List[DishCandidate],
        weights: Optional[Dict[str, float]] = None,
        top_n: int = 5,
    ) -> List[ParetoSolution]:
        """
        对候选方案做帕累托寻优。

        Args:
            candidates: 方案候选列表
            weights: F-M-X-S-R 权重，不传用默认值
            top_n: 返回前 N 个解

        Returns:
            帕累托前沿解列表，按加权分降序排列
        """
        if not candidates:
            return []

        w = weights or DEFAULT_WEIGHTS
        # 归一化权重
        total_w = sum(w.values())
        if total_w > 0:
            w = {k: v / total_w for k, v in w.items()}

        # 找帕累托前沿
        front = find_pareto_front(candidates)

        # 如果前沿不够 top_n，从被支配的解中补充
        if len(front) < top_n:
            dominated = [c for c in candidates if c not in front]
            dominated.sort(key=lambda c: compute_weighted_score(c, w), reverse=True)
            front.extend(dominated[: top_n - len(front)])

        # 按加权分排序
        solutions = []
        for c in front:
            ws = compute_weighted_score(c, w)
            solutions.append(ParetoSolution(
                candidate=c,
                rank=0,  # 下面赋值
                weighted_score=ws,
                label=label_solution(c, candidates),
                tradeoff_description=describe_tradeoff(c, w),
                dimension_scores={
                    "F_flavor": round(c.flavor_score, 1),
                    "M_margin": round(c.margin_pct, 1),
                    "X_complexity": round(c.complexity_score, 1),
                    "S_supply": round(c.supply_score, 1),
                    "R_repurchase": round(c.repurchase_score, 1),
                },
            ))

        solutions.sort(key=lambda s: s.weighted_score, reverse=True)
        for i, s in enumerate(solutions[:top_n], 1):
            s.rank = i

        logger.info(
            "帕累托寻优完成",
            total_candidates=len(candidates),
            pareto_front_size=len(find_pareto_front(candidates)),
            returned=min(top_n, len(solutions)),
        )
        return solutions[:top_n]

    def build_candidate_from_cost_model(
        self,
        dish_name: str,
        recipe_version_id: str,
        bom_cost_yuan: float,
        suggested_price_yuan: float,
        prep_steps: int = 5,
        skill_level: int = 3,
        equipment_count: int = 2,
        supply_availability: float = 85.0,
        price_volatility: float = 10.0,
        substitute_count: int = 2,
        category_repurchase_rate: float = 30.0,
        differentiation_factor: float = 1.0,
        flavor_score: float = 75.0,
    ) -> DishCandidate:
        """
        从经营测算数据构建候选方案。

        简化了各维度的计算逻辑，生产环境会接入更精细的数据源。
        """
        # M: 毛利率
        margin = ((suggested_price_yuan - bom_cost_yuan) / suggested_price_yuan * 100
                  if suggested_price_yuan > 0 else 0)

        # X: 复杂度 = 工序数×技能等级×设备依赖的归一化
        raw_complexity = (prep_steps / 15) * 40 + (skill_level / 5) * 35 + (equipment_count / 5) * 25
        complexity = min(100, max(0, raw_complexity))

        # S: 供应稳定性
        supply = min(100, max(0,
            supply_availability * 0.5
            + (100 - price_volatility) * 0.3
            + min(substitute_count * 15, 100) * 0.2
        ))

        # R: 复购预测
        repurchase = min(100, max(0, category_repurchase_rate * differentiation_factor))

        return DishCandidate(
            candidate_id=f"cand_{recipe_version_id}",
            name=dish_name,
            flavor_score=flavor_score,
            margin_pct=round(margin, 1),
            complexity_score=round(complexity, 1),
            supply_score=round(supply, 1),
            repurchase_score=round(repurchase, 1),
            bom_cost_yuan=bom_cost_yuan,
            suggested_price_yuan=suggested_price_yuan,
            recipe_version_id=recipe_version_id,
        )
