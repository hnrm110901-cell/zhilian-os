"""
Multi-Agent 博弈协议（三体审计）
研发Agent × 财务Agent × 供应链Agent 对新品方案的多轮博弈。

协议流程：
  Round 1: 研发Agent提出方案 → 财务/供应链各自审计
  Round 2: 研发Agent根据反馈调整 → 再审计
  Round 3: 最终方案 → 三方表决（全通过 or 标注分歧交人类裁决）
  最多 3 轮，避免无限循环。
"""
from dataclasses import dataclass
from typing import Dict, List

import structlog

logger = structlog.get_logger()


@dataclass
class DishProposal:
    """菜品方案提案"""
    dish_name: str
    recipe_version_id: str
    bom_cost_yuan: float
    suggested_price_yuan: float
    margin_pct: float
    prep_steps: int
    key_ingredients: List[Dict]   # [{"name": "xx", "cost_yuan": x, "substitute": "yy"}]
    flavor_score: float = 75.0
    target_margin_pct: float = 65.0


@dataclass
class AgentAudit:
    """单个Agent的审计意见"""
    agent_name: str                # "研发" / "财务" / "供应链"
    verdict: str                   # "通过" / "有条件通过" / "否决"
    score: float                   # 0-100 评分
    issues: List[str]              # 问题列表
    suggestions: List[str]         # 建议列表


@dataclass
class NegotiationRound:
    """一轮博弈"""
    round_number: int
    proposal: DishProposal
    audits: List[AgentAudit]
    all_passed: bool
    adjustments_made: List[str]    # 本轮做的调整


@dataclass
class NegotiationResult:
    """博弈结果"""
    dish_name: str
    total_rounds: int
    final_verdict: str             # "全票通过" / "多数通过" / "有分歧需裁决" / "否决"
    rounds: List[NegotiationRound]
    final_proposal: DishProposal
    unresolved_issues: List[str]   # 未解决的分歧
    summary: str


# ── Agent 审计纯函数 ──────────────────────────────────────────────────────────

def finance_audit(proposal: DishProposal) -> AgentAudit:
    """财务Agent审计：毛利率是否达标"""
    issues = []
    suggestions = []

    # 毛利红线
    if proposal.margin_pct < proposal.target_margin_pct - 10:
        issues.append(f"毛利率{proposal.margin_pct:.1f}%严重低于目标{proposal.target_margin_pct:.0f}%")
        suggestions.append("建议提价或降低食材成本")
    elif proposal.margin_pct < proposal.target_margin_pct - 5:
        issues.append(f"毛利率{proposal.margin_pct:.1f}%偏低（目标{proposal.target_margin_pct:.0f}%）")
        suggestions.append("建议优化高成本食材用量")
    elif proposal.margin_pct < proposal.target_margin_pct:
        issues.append(f"毛利率{proposal.margin_pct:.1f}%略低于目标{proposal.target_margin_pct:.0f}%")

    # BOM 成本合理性
    if proposal.bom_cost_yuan > proposal.suggested_price_yuan * 0.5:
        issues.append(f"食材成本占比过高（{proposal.bom_cost_yuan/proposal.suggested_price_yuan:.0%}）")
        # 找出高成本食材
        sorted_ing = sorted(proposal.key_ingredients, key=lambda x: x.get("cost_yuan", 0), reverse=True)
        if sorted_ing:
            top = sorted_ing[0]
            suggestions.append(f"最高成本食材「{top['name']}」¥{top.get('cost_yuan',0):.1f}，建议考虑替代方案")

    if not issues:
        return AgentAudit("财务", "通过", 95.0, [], ["毛利率达标，财务审计通过"])

    score = max(30, 100 - len(issues) * 20)
    verdict = "否决" if proposal.margin_pct < proposal.target_margin_pct - 10 else "有条件通过"
    return AgentAudit("财务", verdict, score, issues, suggestions)


def supply_audit(proposal: DishProposal) -> AgentAudit:
    """供应链Agent审计：食材可得性"""
    issues = []
    suggestions = []

    for ing in proposal.key_ingredients:
        # 检查是否有替代方案
        has_sub = bool(ing.get("substitute"))
        cost = ing.get("cost_yuan", 0)

        # 高价食材无替代 = 供应风险
        if cost > 15 and not has_sub:
            issues.append(f"「{ing['name']}」成本¥{cost:.1f}且无替代方案，供应风险高")
            suggestions.append(f"建议为「{ing['name']}」建立至少一个替代食材")

        # 标记季节性食材
        seasonal = ing.get("seasonal", False)
        if seasonal:
            issues.append(f"「{ing['name']}」为季节性食材，供应可能不稳定")
            suggestions.append(f"建议锁定「{ing['name']}」供应合同或准备替代料")

    if not issues:
        return AgentAudit("供应链", "通过", 90.0, [], ["食材供应稳定，供应链审计通过"])

    score = max(40, 100 - len(issues) * 15)
    verdict = "有条件通过" if len(issues) <= 2 else "否决"
    return AgentAudit("供应链", verdict, score, issues, suggestions)


def rd_audit(proposal: DishProposal) -> AgentAudit:
    """研发Agent审计：风味与出品可行性"""
    issues = []
    suggestions = []

    if proposal.flavor_score < 70:
        issues.append(f"风味评分{proposal.flavor_score:.0f}分偏低，口味吸引力不足")
        suggestions.append("建议增加增鲜/提香食材或调整调味比例")

    if proposal.prep_steps > 12:
        issues.append(f"工序{proposal.prep_steps}步过多，出品效率低")
        suggestions.append("建议合并工序或增加预制环节")
    elif proposal.prep_steps > 8:
        issues.append(f"工序{proposal.prep_steps}步偏多，高峰期可能影响出品速度")

    if not issues:
        return AgentAudit("研发", "通过", 90.0, [], ["风味和出品可行性良好"])

    score = max(50, 100 - len(issues) * 15)
    return AgentAudit("研发", "有条件通过", score, issues, suggestions)


def auto_adjust_proposal(
    proposal: DishProposal,
    audits: List[AgentAudit],
) -> tuple:
    """
    根据审计意见自动调整方案。
    返回 (调整后的方案, 调整说明列表)
    """
    adjustments = []
    new_price = proposal.suggested_price_yuan
    new_cost = proposal.bom_cost_yuan
    new_steps = proposal.prep_steps

    for audit in audits:
        if audit.verdict == "通过":
            continue

        if audit.agent_name == "财务" and proposal.margin_pct < proposal.target_margin_pct:
            # 策略1: 尝试提价 5%
            gap = proposal.target_margin_pct - proposal.margin_pct
            if gap <= 5:
                new_price = round(new_price * 1.05, 0)
                adjustments.append(f"售价从¥{proposal.suggested_price_yuan}调整至¥{new_price}（+5%）以达到毛利目标")
            else:
                # 策略2: 降成本——替换最贵食材
                sorted_ing = sorted(proposal.key_ingredients, key=lambda x: x.get("cost_yuan", 0), reverse=True)
                if sorted_ing and sorted_ing[0].get("substitute"):
                    old_name = sorted_ing[0]["name"]
                    sub_name = sorted_ing[0]["substitute"]
                    cost_save = sorted_ing[0].get("cost_yuan", 0) * 0.3
                    new_cost = round(new_cost - cost_save, 2)
                    adjustments.append(f"「{old_name}」部分替换为「{sub_name}」，成本降低¥{cost_save:.1f}")

        if audit.agent_name == "研发" and proposal.prep_steps > 8:
            new_steps = max(6, new_steps - 2)
            adjustments.append(f"工序从{proposal.prep_steps}步简化至{new_steps}步")

    if not adjustments:
        return proposal, []

    new_margin = ((new_price - new_cost) / new_price * 100) if new_price > 0 else 0
    adjusted = DishProposal(
        dish_name=proposal.dish_name,
        recipe_version_id=proposal.recipe_version_id,
        bom_cost_yuan=new_cost,
        suggested_price_yuan=new_price,
        margin_pct=round(new_margin, 1),
        prep_steps=new_steps,
        key_ingredients=proposal.key_ingredients,
        flavor_score=proposal.flavor_score,
        target_margin_pct=proposal.target_margin_pct,
    )
    return adjusted, adjustments


# ── 服务类 ────────────────────────────────────────────────────────────────────

class MultiAgentNegotiationService:
    """
    三Agent博弈协商服务。

    最多 3 轮博弈：
    Round 1: 原始方案审计
    Round 2: 自动调整后重新审计
    Round 3: 最终表决
    """

    def negotiate(
        self,
        proposal: DishProposal,
        max_rounds: int = 3,
    ) -> NegotiationResult:
        """
        执行多轮博弈。

        Args:
            proposal: 初始方案
            max_rounds: 最大轮数

        Returns:
            NegotiationResult
        """
        rounds = []
        current = proposal

        for round_num in range(1, max_rounds + 1):
            audits = [
                rd_audit(current),
                finance_audit(current),
                supply_audit(current),
            ]

            all_passed = all(a.verdict == "通过" for a in audits)

            if round_num < max_rounds and not all_passed:
                adjusted, adjustments = auto_adjust_proposal(current, audits)
            else:
                adjusted = current
                adjustments = []

            rounds.append(NegotiationRound(
                round_number=round_num,
                proposal=current,
                audits=audits,
                all_passed=all_passed,
                adjustments_made=adjustments,
            ))

            if all_passed:
                break

            current = adjusted

        # 最终裁决
        last_round = rounds[-1]
        pass_count = sum(1 for a in last_round.audits if a.verdict in ("通过", "有条件通过"))
        deny_count = sum(1 for a in last_round.audits if a.verdict == "否决")

        if last_round.all_passed:
            verdict = "全票通过"
        elif deny_count == 0:
            verdict = "多数通过"
        elif pass_count >= 2:
            verdict = "有分歧需裁决"
        else:
            verdict = "否决"

        unresolved = []
        for audit in last_round.audits:
            if audit.verdict not in ("通过",):
                unresolved.extend(audit.issues)

        summary_parts = [f"经过{len(rounds)}轮博弈"]
        if verdict == "全票通过":
            summary_parts.append("三方一致通过")
        elif verdict == "多数通过":
            summary_parts.append("多数通过，部分条件待落实")
        elif verdict == "有分歧需裁决":
            summary_parts.append("存在分歧，建议提交研发总监/老板裁决")
        else:
            summary_parts.append("方案未通过，需重大调整后重新提案")

        final = last_round.proposal
        summary_parts.append(f"（毛利{final.margin_pct:.1f}%，成本¥{final.bom_cost_yuan:.1f}，售价¥{final.suggested_price_yuan:.0f}）")

        logger.info(
            "博弈完成",
            dish=proposal.dish_name,
            rounds=len(rounds),
            verdict=verdict,
        )

        return NegotiationResult(
            dish_name=proposal.dish_name,
            total_rounds=len(rounds),
            final_verdict=verdict,
            rounds=rounds,
            final_proposal=last_round.proposal,
            unresolved_issues=unresolved,
            summary="，".join(summary_parts),
        )
