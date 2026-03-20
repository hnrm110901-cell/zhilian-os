"""
帕累托分析服务（Pareto Analysis Service）
支持多场景（门店/菜品/会员/员工/食材/异常）的帕累托分布分析。

核心能力：
  1. 接收筛选条件 → 聚合数据 → 计算帕累托曲线
  2. 识别 head/body/tail 三段 + 肘点 + 推荐聚焦比例
  3. 基于选定比例生成行动建议
  4. 全部纯函数，无DB依赖，可独立测试
"""
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

import structlog

logger = structlog.get_logger()


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class ParetoItem:
    object_id: str
    object_name: str
    rank: int
    metric_value: float
    contribution: float          # 个体贡献率 0-1
    cumulative_contribution: float  # 累积贡献率 0-1
    segment_type: str            # head / body / tail
    trend_type: Optional[str] = None  # up / down / flat
    risk_level: Optional[str] = None  # low / medium / high
    owner_name: Optional[str] = None
    extra: Optional[Dict] = None


@dataclass
class ParetoCurvePoint:
    ratio: float                 # 对象占比 0-1
    cumulative_contribution: float  # 累积贡献率 0-1
    marginal_gain: float         # 边际收益（每增加10%对象的贡献增量）
    object_count: int            # 该比例下的对象数


@dataclass
class ParetoSummary:
    selected_ratio: float
    selected_object_count: int
    total_object_count: int
    selected_contribution: float
    marginal_gain: float
    recommend_min_ratio: float
    recommend_max_ratio: float
    best_ratio: float
    total_metric_value: float
    elbow_point_ratio: float
    tail_start_ratio: float


@dataclass
class ParetoInsight:
    title: str
    text: str
    insight_type: str            # positive / warning / neutral
    confidence: float
    tags: List[str]


@dataclass
class ParetoAnalysisResult:
    analysis_id: str
    object_type: str
    metric_key: str
    summary: ParetoSummary
    curve: List[ParetoCurvePoint]
    items: List[ParetoItem]
    insight: ParetoInsight
    generated_at: str


@dataclass
class ActionSuggestion:
    action_id: str
    action_title: str
    action_desc: str
    action_type: str             # task / reminder / escalation / export
    priority: str                # high / medium / low
    owner_role: str
    due_in_days: int
    related_object_ids: List[str]


# ── 纯函数 ────────────────────────────────────────────────────────────────────

def compute_pareto_distribution(
    items: List[Dict],
    metric_key: str = "metric_value",
    name_key: str = "name",
    id_key: str = "id",
) -> List[ParetoItem]:
    """
    计算帕累托分布。
    输入：原始数据列表（每项含 metric_value）
    输出：排序后的 ParetoItem 列表（含个体/累积贡献率 + 分段标记）
    """
    if not items:
        return []

    # 按指标降序排列
    sorted_items = sorted(items, key=lambda x: x.get(metric_key, 0), reverse=True)
    total = sum(x.get(metric_key, 0) for x in sorted_items)
    if total <= 0:
        return []

    result = []
    cumulative = 0.0
    n = len(sorted_items)

    for i, item in enumerate(sorted_items):
        val = item.get(metric_key, 0)
        contribution = val / total
        cumulative += contribution
        ratio = (i + 1) / n

        # 分段：前20%对象=head，20-80%=body，80%+=tail
        if ratio <= 0.2:
            segment = "head"
        elif ratio <= 0.8:
            segment = "body"
        else:
            segment = "tail"

        result.append(ParetoItem(
            object_id=str(item.get(id_key, f"obj_{i}")),
            object_name=str(item.get(name_key, f"对象{i+1}")),
            rank=i + 1,
            metric_value=round(val, 2),
            contribution=round(contribution, 4),
            cumulative_contribution=round(cumulative, 4),
            segment_type=segment,
            trend_type=item.get("trend_type"),
            risk_level=item.get("risk_level"),
            owner_name=item.get("owner_name"),
            extra=item.get("extra"),
        ))

    return result


def build_curve(items: List[ParetoItem], points: int = 10) -> List[ParetoCurvePoint]:
    """
    从帕累托分布构建曲线（默认10个采样点）。
    """
    if not items:
        return []

    n = len(items)
    curve = []
    prev_contrib = 0.0

    for i in range(1, points + 1):
        ratio = i / points
        idx = min(int(ratio * n), n) - 1
        if idx < 0:
            idx = 0
        cum = items[idx].cumulative_contribution
        marginal = cum - prev_contrib

        curve.append(ParetoCurvePoint(
            ratio=round(ratio, 2),
            cumulative_contribution=round(cum, 4),
            marginal_gain=round(marginal, 4),
            object_count=idx + 1,
        ))
        prev_contrib = cum

    return curve


def find_elbow_point(curve: List[ParetoCurvePoint]) -> float:
    """
    找肘点：边际收益下降最快的位置。
    返回 ratio 值。
    """
    if len(curve) < 3:
        return 0.2

    max_drop = 0.0
    elbow = 0.2

    for i in range(1, len(curve)):
        drop = curve[i - 1].marginal_gain - curve[i].marginal_gain
        if drop > max_drop:
            max_drop = drop
            elbow = curve[i].ratio

    return elbow


def compute_summary(
    items: List[ParetoItem],
    curve: List[ParetoCurvePoint],
    selected_ratio: float = 0.2,
) -> ParetoSummary:
    """计算帕累托摘要指标"""
    n = len(items)
    if n == 0:
        return ParetoSummary(
            selected_ratio=selected_ratio, selected_object_count=0,
            total_object_count=0, selected_contribution=0,
            marginal_gain=0, recommend_min_ratio=0.1,
            recommend_max_ratio=0.3, best_ratio=0.2,
            total_metric_value=0, elbow_point_ratio=0.2,
            tail_start_ratio=0.8,
        )

    selected_count = max(1, min(n, int(math.ceil(n * selected_ratio))))
    selected_contrib = items[selected_count - 1].cumulative_contribution
    total_value = sum(it.metric_value for it in items)

    # 边际收益
    marginal = 0.0
    for cp in curve:
        if cp.ratio >= selected_ratio:
            marginal = cp.marginal_gain
            break

    elbow = find_elbow_point(curve)
    best = elbow

    # 推荐范围
    rec_min = max(0.05, elbow - 0.1)
    rec_max = min(0.5, elbow + 0.1)

    # tail起始点：累积贡献达到95%的位置
    tail_start = 0.8
    for it in items:
        if it.cumulative_contribution >= 0.95:
            tail_start = it.rank / n
            break

    return ParetoSummary(
        selected_ratio=round(selected_ratio, 2),
        selected_object_count=selected_count,
        total_object_count=n,
        selected_contribution=round(selected_contrib, 4),
        marginal_gain=round(marginal, 4),
        recommend_min_ratio=round(rec_min, 2),
        recommend_max_ratio=round(rec_max, 2),
        best_ratio=round(best, 2),
        total_metric_value=round(total_value, 2),
        elbow_point_ratio=round(elbow, 2),
        tail_start_ratio=round(tail_start, 2),
    )


def generate_insight(
    summary: ParetoSummary,
    object_type: str,
    metric_key: str,
) -> ParetoInsight:
    """生成帕累托分析洞察"""
    pct = round(summary.selected_contribution * 100, 1)
    obj_pct = round(summary.selected_ratio * 100, 0)

    type_names = {
        "store": "门店", "sku": "菜品", "member": "会员",
        "employee": "员工", "material": "食材", "issue": "异常",
    }
    type_name = type_names.get(object_type, "对象")

    if pct >= 80:
        return ParetoInsight(
            title=f"典型帕累托分布：{obj_pct:.0f}%的{type_name}贡献{pct}%",
            text=f"前{summary.selected_object_count}个{type_name}贡献了{pct}%的{metric_key}。"
                 f"建议集中资源管理这些头部{type_name}，边际收益最高。"
                 f"超过{summary.recommend_max_ratio*100:.0f}%后边际收益明显下降。",
            insight_type="positive",
            confidence=0.9,
            tags=["帕累托", "头部集中", "资源聚焦"],
        )
    elif pct >= 60:
        return ParetoInsight(
            title=f"中度集中：{obj_pct:.0f}%的{type_name}贡献{pct}%",
            text=f"分布集中度中等，前{summary.selected_object_count}个{type_name}贡献{pct}%。"
                 f"建议关注头部的同时也不忽视腰部{type_name}的提升空间。",
            insight_type="neutral",
            confidence=0.75,
            tags=["中度集中", "腰部潜力"],
        )
    else:
        return ParetoInsight(
            title=f"分散分布：{obj_pct:.0f}%的{type_name}仅贡献{pct}%",
            text=f"分布较分散，无明显头部效应。"
                 f"建议检查是否存在数据异常，或考虑采用均匀管理策略。",
            insight_type="warning",
            confidence=0.6,
            tags=["分散", "均匀分布", "需关注"],
        )


def generate_action_suggestions(
    items: List[ParetoItem],
    selected_ratio: float,
    object_type: str,
) -> List[ActionSuggestion]:
    """基于选定比例生成行动建议"""
    n = len(items)
    selected_count = max(1, min(n, int(math.ceil(n * selected_ratio))))
    head_items = items[:selected_count]
    actions = []

    type_names = {"store": "门店", "sku": "菜品", "member": "会员",
                  "employee": "员工", "material": "食材", "issue": "异常"}
    tn = type_names.get(object_type, "对象")

    # 行动1：头部重点关注
    actions.append(ActionSuggestion(
        action_id=str(uuid4()),
        action_title=f"重点关注 Top{selected_count} {tn}",
        action_desc=f"对前{selected_count}个{tn}进行专项分析和管理，它们贡献了大部分价值。",
        action_type="task",
        priority="high",
        owner_role="store_manager" if object_type == "store" else "hq_operator",
        due_in_days=3,
        related_object_ids=[it.object_id for it in head_items[:10]],
    ))

    # 行动2：风险项处理
    risky = [it for it in head_items if it.risk_level in ("high", "medium")]
    if risky:
        actions.append(ActionSuggestion(
            action_id=str(uuid4()),
            action_title=f"{len(risky)}个头部{tn}存在风险",
            action_desc=f"{'、'.join(it.object_name for it in risky[:3])}等{len(risky)}个{tn}有风险标记，需优先处理。",
            action_type="escalation",
            priority="high",
            owner_role="regional_manager",
            due_in_days=1,
            related_object_ids=[it.object_id for it in risky],
        ))

    # 行动3：尾部优化
    tail_items = [it for it in items if it.segment_type == "tail"]
    if tail_items:
        actions.append(ActionSuggestion(
            action_id=str(uuid4()),
            action_title=f"尾部{len(tail_items)}个{tn}评估",
            action_desc=f"尾部{tn}贡献极低，建议评估是否需要优化、合并或淘汰。",
            action_type="reminder",
            priority="low",
            owner_role="store_manager",
            due_in_days=7,
            related_object_ids=[it.object_id for it in tail_items[:5]],
        ))

    return actions


# ── 服务类 ────────────────────────────────────────────────────────────────────

class ParetoAnalysisService:
    """
    帕累托分析服务。

    使用方式：
    1. 准备原始数据列表 [{id, name, metric_value, ...}]
    2. 调用 analyze() 获取完整分析结果
    3. 调用 get_action_suggestions() 获取行动建议
    """

    def analyze(
        self,
        raw_items: List[Dict],
        object_type: str = "store",
        metric_key: str = "revenue",
        selected_ratio: float = 0.2,
        id_key: str = "id",
        name_key: str = "name",
        value_key: str = "metric_value",
    ) -> ParetoAnalysisResult:
        """执行完整帕累托分析"""
        items = compute_pareto_distribution(raw_items, value_key, name_key, id_key)
        curve = build_curve(items)
        summary = compute_summary(items, curve, selected_ratio)
        insight = generate_insight(summary, object_type, metric_key)

        analysis_id = str(uuid4())

        logger.info(
            "帕累托分析完成",
            analysis_id=analysis_id,
            object_type=object_type,
            total_items=len(items),
            selected_contribution=summary.selected_contribution,
        )

        return ParetoAnalysisResult(
            analysis_id=analysis_id,
            object_type=object_type,
            metric_key=metric_key,
            summary=summary,
            curve=curve,
            items=items,
            insight=insight,
            generated_at=datetime.utcnow().isoformat(),
        )

    def get_action_suggestions(
        self,
        items: List[ParetoItem],
        selected_ratio: float,
        object_type: str,
    ) -> List[ActionSuggestion]:
        """获取行动建议"""
        return generate_action_suggestions(items, selected_ratio, object_type)
