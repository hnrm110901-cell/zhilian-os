"""
贝叶斯销量侵蚀预测（Cannibalization Predictor）
预测新品上线后对现有菜品的替代效应，计算净 GMV 贡献。

贝叶斯网络简化版：
  P(替代|特征) 基于品类相似度、价格带重叠、口味重叠计算
  净GMV = 新品预估销售额 - Σ(被替代菜品 × 替代概率 × 原销售额)
"""
from dataclasses import dataclass
from typing import List

import structlog

logger = structlog.get_logger()


@dataclass
class ExistingDish:
    """现有菜品"""
    dish_id: str
    dish_name: str
    category: str              # 品类（如 "炒菜", "蒸菜", "凉菜"）
    price_yuan: float
    monthly_sales_count: int
    monthly_revenue_yuan: float
    flavor_tags: List[str] = None  # 风味标签（如 ["辣", "鲜"]）

    def __post_init__(self):
        self.flavor_tags = self.flavor_tags or []


@dataclass
class NewDishProfile:
    """新品档案"""
    dish_name: str
    category: str
    price_yuan: float
    estimated_monthly_sales: int
    flavor_tags: List[str] = None

    def __post_init__(self):
        self.flavor_tags = self.flavor_tags or []


@dataclass
class CannibalizationItem:
    """单品侵蚀预测"""
    dish_id: str
    dish_name: str
    substitution_prob: float       # 替代概率 0-1
    estimated_lost_sales: int      # 预计流失销量
    estimated_lost_revenue_yuan: float  # 预计流失营收
    reason: str                    # 侵蚀原因


@dataclass
class CannibalizationResult:
    """侵蚀分析结果"""
    new_dish_name: str
    estimated_new_revenue_yuan: float   # 新品预估月营收
    total_cannibalized_yuan: float      # 被侵蚀的总营收
    net_gmv_contribution_yuan: float    # 净 GMV 贡献
    cannibalization_rate: float         # 侵蚀率（被侵蚀/新品营收）
    affected_dishes: List[CannibalizationItem]
    risk_level: str                     # "低"/"中"/"高"
    summary: str


# ── 纯函数 ────────────────────────────────────────────────────────────────────

def category_similarity(cat_a: str, cat_b: str) -> float:
    """品类相似度：同品类=1.0，相近品类=0.5，不同=0.1"""
    if cat_a == cat_b:
        return 1.0
    related_groups = [
        {"炒菜", "小炒", "干锅"},
        {"蒸菜", "蒸菜点心"},
        {"凉菜", "宴席凉菜", "会员凉菜"},
        {"汤", "炖品", "煲"},
        {"主食", "面食", "米饭"},
    ]
    for group in related_groups:
        if cat_a in group and cat_b in group:
            return 0.5
    return 0.1


def price_overlap(price_a: float, price_b: float) -> float:
    """价格带重叠度：价差越小重叠越高"""
    if price_a <= 0 or price_b <= 0:
        return 0.0
    ratio = min(price_a, price_b) / max(price_a, price_b)
    return ratio  # 0-1，价格越接近越高


def flavor_overlap(tags_a: List[str], tags_b: List[str]) -> float:
    """风味标签重叠度"""
    if not tags_a or not tags_b:
        return 0.3  # 无数据时给中等值
    set_a, set_b = set(tags_a), set(tags_b)
    if not set_a or not set_b:
        return 0.3
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def compute_substitution_prob(
    new_dish: NewDishProfile,
    existing: ExistingDish,
    w_category: float = 0.5,
    w_price: float = 0.3,
    w_flavor: float = 0.2,
) -> float:
    """
    计算新品对现有菜品的替代概率。
    P(替代) = w1×品类相似度 + w2×价格重叠 + w3×风味重叠
    """
    cat_sim = category_similarity(new_dish.category, existing.category)
    price_sim = price_overlap(new_dish.price_yuan, existing.price_yuan)
    flav_sim = flavor_overlap(new_dish.flavor_tags, existing.flavor_tags)

    prob = w_category * cat_sim + w_price * price_sim + w_flavor * flav_sim
    # 侵蚀概率上限 0.4（一道新菜最多替代某道老菜 40% 销量）
    return min(0.4, max(0.0, prob))


# ── 服务类 ────────────────────────────────────────────────────────────────────

class CannibalizationService:
    """
    销量侵蚀预测服务。

    使用方式：
    1. 构建 NewDishProfile 和 List[ExistingDish]
    2. 调用 predict() 获取侵蚀分析结果
    """

    def predict(
        self,
        new_dish: NewDishProfile,
        existing_dishes: List[ExistingDish],
        significance_threshold: float = 0.15,
    ) -> CannibalizationResult:
        """
        预测新品对现有菜品的侵蚀效应。

        Args:
            new_dish: 新品档案
            existing_dishes: 现有菜品列表
            significance_threshold: 替代概率高于此值才纳入分析

        Returns:
            CannibalizationResult
        """
        new_revenue = new_dish.estimated_monthly_sales * new_dish.price_yuan
        affected = []

        for dish in existing_dishes:
            prob = compute_substitution_prob(new_dish, dish)
            if prob < significance_threshold:
                continue

            lost_sales = int(dish.monthly_sales_count * prob)
            lost_revenue = dish.monthly_revenue_yuan * prob

            reason_parts = []
            if category_similarity(new_dish.category, dish.category) >= 0.5:
                reason_parts.append("同品类竞争")
            if price_overlap(new_dish.price_yuan, dish.price_yuan) >= 0.7:
                reason_parts.append("价格带重叠")
            if flavor_overlap(new_dish.flavor_tags, dish.flavor_tags) >= 0.4:
                reason_parts.append("口味相似")

            affected.append(CannibalizationItem(
                dish_id=dish.dish_id,
                dish_name=dish.dish_name,
                substitution_prob=round(prob, 3),
                estimated_lost_sales=lost_sales,
                estimated_lost_revenue_yuan=round(lost_revenue, 2),
                reason="、".join(reason_parts) if reason_parts else "综合因素",
            ))

        affected.sort(key=lambda x: x.estimated_lost_revenue_yuan, reverse=True)

        total_cannibalized = sum(a.estimated_lost_revenue_yuan for a in affected)
        net_gmv = new_revenue - total_cannibalized
        cannibal_rate = total_cannibalized / new_revenue if new_revenue > 0 else 0

        if cannibal_rate <= 0.2:
            risk = "低"
            summary = f"新品净增 GMV ¥{net_gmv:,.0f}/月，侵蚀率仅{cannibal_rate:.0%}，属于增量型新品"
        elif cannibal_rate <= 0.5:
            risk = "中"
            top3 = "、".join(a.dish_name for a in affected[:3])
            summary = f"新品净增 GMV ¥{net_gmv:,.0f}/月，但会分流{top3}等菜品约{cannibal_rate:.0%}的销量"
        else:
            risk = "高"
            summary = f"新品侵蚀率{cannibal_rate:.0%}，净增仅 ¥{net_gmv:,.0f}/月，建议重新定位价格带或品类"

        logger.info(
            "侵蚀预测完成",
            new_dish=new_dish.dish_name,
            net_gmv=round(net_gmv, 0),
            cannibalization_rate=round(cannibal_rate, 2),
            affected_count=len(affected),
        )

        return CannibalizationResult(
            new_dish_name=new_dish.dish_name,
            estimated_new_revenue_yuan=round(new_revenue, 2),
            total_cannibalized_yuan=round(total_cannibalized, 2),
            net_gmv_contribution_yuan=round(net_gmv, 2),
            cannibalization_rate=round(cannibal_rate, 3),
            affected_dishes=affected,
            risk_level=risk,
            summary=summary,
        )
