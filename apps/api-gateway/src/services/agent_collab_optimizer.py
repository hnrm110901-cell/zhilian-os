"""
AgentCollaborationOptimizer — 多Agent协同总线
冲突检测·优先级仲裁·全局优化

核心职责：
1. 接收多个 Agent 的建议列表
2. 检测跨Agent冲突（资源争抢/财务约束/时间冲突/矛盾动作）
3. 通过优先级规则仲裁冲突
4. 全局优化建议列表（去重/重排/打包/抑制）
5. 返回经过协同的最终建议集合
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional

# ──────────────────────────────────────────────
# Agent 优先级表（来源：PPT 增长价值映射）
# ──────────────────────────────────────────────

AGENT_PRIORITY: dict[str, int] = {
    # P0 — 收入+成本双向高影响
    "business_intel": 100,
    "ops_flow": 95,
    "people": 90,
    # P1 — 增长引擎
    "marketing": 80,
    "banquet": 75,
    "dish_rd": 70,
    "supplier": 65,
    # 底座层
    "compliance": 60,
    "fct": 55,
    "private_domain": 50,
}

# 冲突规则：Agent 对 → 冲突类型
# key = (agent_a, agent_b, action_keyword_a, action_keyword_b)
# 简化为：特定 Agent 对之间总是可能发生特定类型冲突

KNOWN_CONFLICT_PAIRS: list[tuple[str, str, str, str]] = [
    # OpsFlowAgent 紧急补货 vs SupplierAgent 切换供应商
    ("ops_flow", "supplier", "补货", "切换供应商"),
    # BusinessIntelAgent 促销折扣 vs FctAgent 现金流约束
    ("business_intel", "fct", "折扣", "现金流"),
    # MarketingAgent 高频推送 vs 企业微信频控
    ("marketing", "ops_flow", "发券", "推送"),
    # PeopleAgent 排班削减 vs OpsFlowAgent 高峰预警
    ("people", "ops_flow", "减少排班", "高峰"),
    # DishRdAgent 推新品 vs SupplierAgent 供应风险
    ("dish_rd", "supplier", "新品上市", "供应风险"),
    # BanquetAgent 宴会日满场 vs OpsFlowAgent 库存不足
    ("banquet", "ops_flow", "宴会满场", "库存不足"),
]


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────


@dataclass
class AgentRecommendation:
    """单条 Agent 建议（传入协同总线的格式）"""

    id: str
    agent_name: str
    store_id: str
    recommendation_type: str
    recommendation_text: str
    expected_impact_yuan: float = 0.0
    confidence_score: float = 0.5
    priority_override: Optional[int] = None  # 允许 Agent 自定义优先级


@dataclass
class ConflictRecord:
    """检测到的冲突"""

    conflict_id: str
    agent_a: str
    agent_b: str
    rec_a_id: str
    rec_b_id: str
    conflict_type: str
    severity: str
    description: str
    winning_agent: Optional[str] = None
    arbitration_method: str = "priority_wins"
    impact_yuan_saved: float = 0.0


@dataclass
class OptimizationAction:
    """单次优化操作"""

    action: str  # dedup/reorder/bundle/suppress
    rec_ids: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class CollabResult:
    """协同总线输出结果"""

    optimized_recommendations: list[AgentRecommendation]
    conflicts: list[ConflictRecord]
    optimization_actions: list[OptimizationAction]
    input_count: int
    output_count: int
    conflicts_detected: int
    dedup_count: int
    suppressed_count: int
    bundled_count: int
    total_impact_yuan_before: float
    total_impact_yuan_after: float
    ai_insight: str


# ──────────────────────────────────────────────
# 纯函数
# ──────────────────────────────────────────────


def get_agent_priority(agent_name: str, override: Optional[int] = None) -> int:
    """获取 Agent 优先级（越大越优先）"""
    if override is not None:
        return override
    return AGENT_PRIORITY.get(agent_name, 50)


def classify_conflict_severity(impact_a: float, impact_b: float) -> str:
    """根据双方建议的¥影响量判断冲突严重度"""
    max_impact = max(abs(impact_a), abs(impact_b))
    if max_impact >= 10000:
        return "high"
    if max_impact >= 2000:
        return "medium"
    return "low"


def detect_keyword_conflict(
    agent_a: str,
    text_a: str,
    agent_b: str,
    text_b: str,
) -> Optional[tuple[str, str]]:
    """
    检测两条建议之间是否存在已知关键词冲突
    返回 (conflict_type, description) 或 None
    """
    for aa, ab, kw_a, kw_b in KNOWN_CONFLICT_PAIRS:
        if agent_a == aa and agent_b == ab:
            if kw_a in text_a and kw_b in text_b:
                return ("resource_contention", f"{agent_a}建议「{kw_a}」与{agent_b}建议「{kw_b}」存在冲突")
        if agent_a == ab and agent_b == aa:
            if kw_b in text_a and kw_a in text_b:
                return ("resource_contention", f"{agent_a}建议「{kw_b}」与{agent_b}建议「{kw_a}」存在冲突")

    # 通用检测：相同store+相反动作
    contra_pairs = [("增加", "减少"), ("买入", "卖出"), ("促销", "提价"), ("扩张", "收缩")]
    for pos, neg in contra_pairs:
        if pos in text_a and neg in text_b:
            return ("contradictory_action", f"{agent_a}建议{pos}，{agent_b}建议{neg}，动作互相矛盾")
        if neg in text_a and pos in text_b:
            return ("contradictory_action", f"{agent_a}建议{neg}，{agent_b}建议{pos}，动作互相矛盾")

    return None


def arbitrate_conflict(
    conflict_type: str,
    agent_a: str,
    priority_a: int,
    impact_a: float,
    agent_b: str,
    priority_b: int,
    impact_b: float,
) -> tuple[Optional[str], str]:
    """
    仲裁冲突，返回 (winning_agent, arbitration_method)
    winning_agent=None 表示合并建议
    """
    # 财务约束最高优先
    if "fct" in (agent_a, agent_b) and conflict_type == "financial_constraint":
        winner = "fct"
        return (winner, "financial_first")

    # 合规证照风险优先
    if "compliance" in (agent_a, agent_b):
        winner = "compliance"
        return (winner, "risk_first")

    # 优先级高的胜出
    if priority_a > priority_b:
        return (agent_a, "priority_wins")
    if priority_b > priority_a:
        return (agent_b, "priority_wins")

    # 优先级相同：¥影响大的胜出
    if abs(impact_a) >= abs(impact_b):
        return (agent_a, "revenue_first")
    return (agent_b, "revenue_first")


def is_duplicate(rec_a: AgentRecommendation, rec_b: AgentRecommendation) -> bool:
    """
    判断两条建议是否实质重复
    同 store + 相似内容（字符2-gram Jaccard相似度 > 0.5）
    """
    if rec_a.store_id != rec_b.store_id:
        return False
    ta = rec_a.recommendation_text
    tb = rec_b.recommendation_text
    if not ta or not tb:
        return False
    # 字符2-gram
    bigrams_a = {ta[i : i + 2] for i in range(len(ta) - 1)}
    bigrams_b = {tb[i : i + 2] for i in range(len(tb) - 1)}
    if not bigrams_a or not bigrams_b:
        return False
    jaccard = len(bigrams_a & bigrams_b) / len(bigrams_a | bigrams_b)
    return jaccard > 0.5


def should_suppress(rec: AgentRecommendation, threshold_yuan: float = 100.0) -> bool:
    """低影响建议应被抑制（避免噪音）"""
    return rec.expected_impact_yuan < threshold_yuan and rec.confidence_score < 0.4


def compute_global_impact(recs: list[AgentRecommendation]) -> float:
    """计算建议列表的总¥影响"""
    return sum(r.expected_impact_yuan for r in recs)


def build_ai_insight(
    input_count: int,
    output_count: int,
    conflicts: list[ConflictRecord],
    impact_before: float,
    impact_after: float,
) -> str:
    """生成 AI 协同洞察文本"""
    lines = []
    if conflicts:
        high_conflicts = [c for c in conflicts if c.severity == "high"]
        lines.append(
            f"检测到 {len(conflicts)} 个跨Agent冲突"
            + (f"（其中 {len(high_conflicts)} 个高风险）" if high_conflicts else "")
            + "，已完成自动仲裁。"
        )
    removed = input_count - output_count
    if removed > 0:
        lines.append(f"全局优化去除 {removed} 条冗余/低价值建议，推送噪音降低 {removed/max(input_count,1)*100:.0f}%。")
    gain = impact_after - impact_before
    if gain > 0:
        lines.append(f"通过建议重排序，预期额外增益 ¥{gain:.0f}。")
    elif abs(gain) < 1:
        lines.append(f"优化后总预期影响 ¥{impact_after:.0f}，质量提升但总量未降。")
    if not lines:
        lines.append(f"本次协同优化处理 {input_count} 条建议，最终输出 {output_count} 条高质量推荐，无冲突。")
    return " ".join(lines)


# ──────────────────────────────────────────────
# 核心服务类
# ──────────────────────────────────────────────


class AgentCollabOptimizer:
    """
    多Agent协同总线

    用法：
        optimizer = AgentCollabOptimizer()
        result = optimizer.optimize(recommendations)
    """

    def optimize(
        self,
        recommendations: list[AgentRecommendation],
        suppress_threshold_yuan: float = 100.0,
    ) -> CollabResult:
        """
        对多Agent建议列表执行协同优化

        流程：
        1. 冲突检测（O(n²)，建议数量通常 < 30）
        2. 优先级仲裁（移除被仲裁失败的建议）
        3. 去重（相同建议只保留一条）
        4. 低影响建议抑制
        5. 重新排序（¥影响 × 置信度降序）
        """
        recs = list(recommendations)
        input_count = len(recs)
        total_impact_before = compute_global_impact(recs)

        conflicts: list[ConflictRecord] = []
        actions: list[OptimizationAction] = []
        suppressed_ids: set[str] = set()
        dedup_ids: set[str] = set()
        bundled_count = 0

        # Step 1: 冲突检测 + 仲裁
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                ra, rb = recs[i], recs[j]
                if ra.store_id != rb.store_id:
                    continue
                detection = detect_keyword_conflict(
                    ra.agent_name, ra.recommendation_text, rb.agent_name, rb.recommendation_text
                )
                if detection is None:
                    continue
                conflict_type, description = detection
                pa = get_agent_priority(ra.agent_name, ra.priority_override)
                pb = get_agent_priority(rb.agent_name, rb.priority_override)
                severity = classify_conflict_severity(ra.expected_impact_yuan, rb.expected_impact_yuan)
                winner, method = arbitrate_conflict(
                    conflict_type,
                    ra.agent_name,
                    pa,
                    ra.expected_impact_yuan,
                    rb.agent_name,
                    pb,
                    rb.expected_impact_yuan,
                )
                impact_saved = min(abs(ra.expected_impact_yuan), abs(rb.expected_impact_yuan))
                cf = ConflictRecord(
                    conflict_id=str(uuid.uuid4()),
                    agent_a=ra.agent_name,
                    agent_b=rb.agent_name,
                    rec_a_id=ra.id,
                    rec_b_id=rb.id,
                    conflict_type=conflict_type,
                    severity=severity,
                    description=description,
                    winning_agent=winner,
                    arbitration_method=method,
                    impact_yuan_saved=impact_saved,
                )
                conflicts.append(cf)
                # 失败方建议被抑制
                loser_id = rb.id if winner == ra.agent_name else ra.id
                if loser_id and winner is not None:
                    suppressed_ids.add(loser_id)
                    actions.append(
                        OptimizationAction(
                            action="suppress",
                            rec_ids=[loser_id],
                            reason=f"冲突仲裁：{winner} 胜出，{description}",
                        )
                    )

        # Step 2: 去重
        seen_texts: list[AgentRecommendation] = []
        for rec in recs:
            if rec.id in suppressed_ids:
                continue
            dup = next((s for s in seen_texts if is_duplicate(rec, s)), None)
            if dup:
                # 保留¥影响更高的
                if rec.expected_impact_yuan > dup.expected_impact_yuan:
                    dedup_ids.add(dup.id)
                    seen_texts = [s for s in seen_texts if s.id != dup.id]
                    seen_texts.append(rec)
                    actions.append(
                        OptimizationAction(
                            action="dedup",
                            rec_ids=[dup.id, rec.id],
                            reason=f"去重：{rec.agent_name} 建议与 {dup.agent_name} 实质相同，保留高影响版本",
                        )
                    )
                else:
                    dedup_ids.add(rec.id)
                    actions.append(
                        OptimizationAction(
                            action="dedup",
                            rec_ids=[rec.id, dup.id],
                            reason=f"去重：{rec.agent_name} 建议与 {dup.agent_name} 实质相同，保留高影响版本",
                        )
                    )
            else:
                seen_texts.append(rec)

        # Step 3: 低影响抑制
        for rec in seen_texts:
            if should_suppress(rec, suppress_threshold_yuan):
                suppressed_ids.add(rec.id)
                actions.append(
                    OptimizationAction(
                        action="suppress",
                        rec_ids=[rec.id],
                        reason=f"抑制：¥影响{rec.expected_impact_yuan:.0f} < 阈值{suppress_threshold_yuan:.0f}，且置信度{rec.confidence_score:.2f}偏低",
                    )
                )

        # Step 4: 最终过滤 + 重排序（¥影响 × 置信度降序）
        excluded = suppressed_ids | dedup_ids
        final_recs = [r for r in recs if r.id not in excluded]
        final_recs.sort(
            key=lambda r: r.expected_impact_yuan * r.confidence_score,
            reverse=True,
        )

        total_impact_after = compute_global_impact(final_recs)
        ai_insight = build_ai_insight(
            input_count,
            len(final_recs),
            conflicts,
            total_impact_before,
            total_impact_after,
        )

        return CollabResult(
            optimized_recommendations=final_recs,
            conflicts=conflicts,
            optimization_actions=actions,
            input_count=input_count,
            output_count=len(final_recs),
            conflicts_detected=len(conflicts),
            dedup_count=len(dedup_ids),
            suppressed_count=len(suppressed_ids),
            bundled_count=bundled_count,
            total_impact_yuan_before=total_impact_before,
            total_impact_yuan_after=total_impact_after,
            ai_insight=ai_insight,
        )

    def detect_conflicts_only(
        self,
        recommendations: list[AgentRecommendation],
    ) -> list[ConflictRecord]:
        """仅检测冲突，不执行优化（供调试/监控用）"""
        result = self.optimize(recommendations)
        return result.conflicts


# Singleton
agent_collab_optimizer = AgentCollabOptimizer()
