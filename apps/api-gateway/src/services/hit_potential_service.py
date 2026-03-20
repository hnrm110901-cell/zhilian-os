"""
爆品潜力指数（Hit Potential Index, HPI）+ 伪爆品鉴别

HPI 实时评分：上线后 48h 即可预判菜品前景
伪爆品识别：揪出"销量高但不健康"的菜品

指标体系：
  HPI = w1×点单率 + w2×复购率 + w3×好评率 + w4×毛利达标
      + w5×连带销售提升 + w6×制作效率达标 + w7×(1-退菜率)

评级：
  HPI ≥ 80  → 爆品苗子
  60 ≤ HPI < 80 → 潜力股
  40 ≤ HPI < 60 → 平庸品
  HPI < 40  → 失败品
"""
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class DishPerformance:
    """菜品经营表现数据（从 POS/订单数据汇总）"""
    dish_id: str
    dish_name: str
    brand_id: str
    store_id: Optional[str] = None   # None=全品牌汇总
    period_days: int = 7             # 统计周期（天）
    launch_date: Optional[date] = None

    # 核心指标
    total_orders: int = 0            # 总订单数（含该菜品的订单）
    dish_order_count: int = 0        # 该菜品被点次数
    unique_customers: int = 0        # 点过该菜品的独立客户数
    repeat_customers: int = 0        # 复购客户数（2次及以上）
    positive_feedback_count: int = 0 # 好评数
    total_feedback_count: int = 0    # 总评价数
    return_count: int = 0            # 退菜次数
    complaint_count: int = 0         # 投诉次数

    # 财务指标
    revenue_yuan: float = 0.0        # 菜品营收
    cost_yuan: float = 0.0           # 菜品成本
    target_margin_pct: float = 65.0  # 品牌目标毛利率

    # 连带指标
    avg_ticket_with_dish: float = 0.0   # 含该菜品订单的平均客单价
    avg_ticket_without_dish: float = 0.0 # 不含该菜品订单的平均客单价

    # 效率指标
    avg_prep_time_minutes: float = 0.0  # 平均出品时间
    target_prep_time_minutes: float = 15.0  # 目标出品时间

    # 折扣依赖
    discount_order_count: int = 0    # 有折扣/优惠的订单中点该菜品次数
    full_price_order_count: int = 0  # 无折扣订单中点该菜品次数


@dataclass
class HPIResult:
    """HPI 评分结果"""
    dish_id: str
    dish_name: str
    hpi_score: float                 # 0-100
    grade: str                       # 爆品苗子/潜力股/平庸品/失败品
    is_fake_hit: bool                # 是否伪爆品
    fake_hit_reasons: List[str]      # 伪爆品原因
    dimension_scores: Dict[str, float]  # 各维度得分
    recommendations: List[str]       # 运营建议
    days_since_launch: Optional[int] = None


# ── HPI 纯函数 ────────────────────────────────────────────────────────────────

DEFAULT_HPI_WEIGHTS = {
    "order_rate": 0.20,       # 点单率
    "repurchase_rate": 0.20,  # 复购率
    "positive_rate": 0.15,    # 好评率
    "margin_hit": 0.15,       # 毛利达标
    "ticket_lift": 0.10,      # 连带销售提升
    "efficiency": 0.10,       # 制作效率达标
    "low_return": 0.10,       # 退菜率倒数
}


def calc_order_rate(perf: DishPerformance) -> float:
    """点单率：该菜品被点次数 / 总订单数 × 归一化"""
    if perf.total_orders == 0:
        return 0.0
    rate = perf.dish_order_count / perf.total_orders
    # 点单率 10% 以上算优秀，归一化到 0-100
    return min(100, rate / 0.10 * 100)


def calc_repurchase_rate(perf: DishPerformance) -> float:
    """复购率：复购客户 / 独立客户"""
    if perf.unique_customers == 0:
        return 0.0
    rate = perf.repeat_customers / perf.unique_customers
    # 30% 以上复购率算优秀
    return min(100, rate / 0.30 * 100)


def calc_positive_rate(perf: DishPerformance) -> float:
    """好评率"""
    if perf.total_feedback_count == 0:
        return 50.0  # 无评价时给中间分
    rate = perf.positive_feedback_count / perf.total_feedback_count
    return rate * 100


def calc_margin_hit(perf: DishPerformance) -> float:
    """毛利达标度"""
    if perf.revenue_yuan == 0:
        return 0.0
    actual_margin = (perf.revenue_yuan - perf.cost_yuan) / perf.revenue_yuan * 100
    target = perf.target_margin_pct
    if actual_margin >= target:
        return 100.0
    elif actual_margin >= target - 5:
        return 70.0
    elif actual_margin >= target - 10:
        return 40.0
    return 10.0


def calc_ticket_lift(perf: DishPerformance) -> float:
    """连带销售提升"""
    if perf.avg_ticket_without_dish == 0:
        return 50.0
    lift = (perf.avg_ticket_with_dish - perf.avg_ticket_without_dish) / perf.avg_ticket_without_dish
    # 提升 10% 以上算优秀
    return min(100, max(0, (lift / 0.10) * 100))


def calc_efficiency(perf: DishPerformance) -> float:
    """制作效率达标度"""
    if perf.target_prep_time_minutes == 0:
        return 50.0
    ratio = perf.avg_prep_time_minutes / perf.target_prep_time_minutes
    if ratio <= 1.0:
        return 100.0
    elif ratio <= 1.2:
        return 70.0
    elif ratio <= 1.5:
        return 40.0
    return 10.0


def calc_low_return(perf: DishPerformance) -> float:
    """低退菜率得分"""
    if perf.dish_order_count == 0:
        return 50.0
    return_rate = perf.return_count / perf.dish_order_count
    if return_rate <= 0.02:
        return 100.0
    elif return_rate <= 0.05:
        return 70.0
    elif return_rate <= 0.10:
        return 40.0
    return 10.0


def compute_hpi(
    perf: DishPerformance,
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """计算 HPI 综合分"""
    w = weights or DEFAULT_HPI_WEIGHTS
    total_w = sum(w.values())
    if total_w == 0:
        return 0.0

    dimensions = {
        "order_rate": calc_order_rate(perf),
        "repurchase_rate": calc_repurchase_rate(perf),
        "positive_rate": calc_positive_rate(perf),
        "margin_hit": calc_margin_hit(perf),
        "ticket_lift": calc_ticket_lift(perf),
        "efficiency": calc_efficiency(perf),
        "low_return": calc_low_return(perf),
    }

    score = sum(w.get(k, 0) * v for k, v in dimensions.items()) / total_w
    return round(score, 1)


def grade_hpi(score: float) -> str:
    """HPI 评级"""
    if score >= 80:
        return "爆品苗子"
    elif score >= 60:
        return "潜力股"
    elif score >= 40:
        return "平庸品"
    return "失败品"


# ── 伪爆品鉴别纯函数 ──────────────────────────────────────────────────────────

def detect_fake_hit(perf: DishPerformance) -> tuple[bool, list[str]]:
    """
    伪爆品鉴别：销量高但不健康的菜品。

    5 个伪爆品特征（命中 2 个及以上判定为伪爆品）：
    1. 折扣依赖：折扣订单占比 > 60%
    2. 低毛利：实际毛利率 < 目标 - 10%
    3. 高退菜率：退菜率 > 10%
    4. 高投诉率：投诉率 > 5%
    5. 无复购：复购率 < 5%
    """
    reasons = []

    # 1. 折扣依赖
    total_with_info = perf.discount_order_count + perf.full_price_order_count
    if total_with_info > 0:
        discount_ratio = perf.discount_order_count / total_with_info
        if discount_ratio > 0.60:
            reasons.append(f"折扣依赖严重（{discount_ratio:.0%}的订单靠折扣驱动）")

    # 2. 低毛利
    if perf.revenue_yuan > 0:
        actual_margin = (perf.revenue_yuan - perf.cost_yuan) / perf.revenue_yuan * 100
        threshold = perf.target_margin_pct - 10
        if actual_margin < threshold:
            reasons.append(f"毛利率过低（实际{actual_margin:.1f}%，目标{perf.target_margin_pct:.0f}%）")

    # 3. 高退菜率
    if perf.dish_order_count > 0:
        return_rate = perf.return_count / perf.dish_order_count
        if return_rate > 0.10:
            reasons.append(f"退菜率过高（{return_rate:.1%}）")

    # 4. 高投诉率
    if perf.dish_order_count > 0:
        complaint_rate = perf.complaint_count / perf.dish_order_count
        if complaint_rate > 0.05:
            reasons.append(f"投诉率过高（{complaint_rate:.1%}）")

    # 5. 无复购
    if perf.unique_customers > 10:  # 至少 10 个客户才有意义
        repurchase_rate = perf.repeat_customers / perf.unique_customers
        if repurchase_rate < 0.05:
            reasons.append(f"几乎无复购（复购率{repurchase_rate:.1%}）")

    is_fake = len(reasons) >= 2
    return is_fake, reasons


def generate_recommendations(perf: DishPerformance, hpi: float, grade: str, is_fake: bool) -> List[str]:
    """根据评分和表现数据生成运营建议"""
    recs = []

    if is_fake:
        recs.append("伪爆品告警：建议立即复盘折扣策略和成本结构，考虑调价或下架")
        return recs

    if grade == "爆品苗子":
        recs.append("爆品苗子：建议加大推广力度，锁定供应链，推动全国门店上线")
    elif grade == "潜力股":
        if calc_margin_hit(perf) < 60:
            recs.append("毛利偏低：建议优化 BOM 配方或调整售价")
        if calc_repurchase_rate(perf) < 50:
            recs.append("复购待提升：建议设计会员专属价或搭配套餐")
        if calc_efficiency(perf) < 50:
            recs.append("出品效率偏低：建议简化工序或增加预制")
    elif grade == "平庸品":
        recs.append("表现平庸：建议微调配方/定价后再观察 2 周，无改善则启动退出流程")
    else:
        recs.append("建议下架或大幅改良后重新试点")

    return recs


# ── 服务类 ────────────────────────────────────────────────────────────────────

class HitPotentialService:
    """
    爆品潜力评分 + 伪爆品鉴别服务。

    使用方式：
    1. 从 POS 订单数据构建 DishPerformance
    2. 调用 evaluate() 获取 HPI 评分 + 伪爆品判定
    3. 调用 batch_evaluate() 批量评估品牌下所有在售菜品
    """

    def evaluate(
        self,
        perf: DishPerformance,
        weights: Optional[Dict[str, float]] = None,
    ) -> HPIResult:
        """评估单个菜品的 HPI 和伪爆品风险"""
        hpi = compute_hpi(perf, weights)
        grade = grade_hpi(hpi)
        is_fake, fake_reasons = detect_fake_hit(perf)
        recs = generate_recommendations(perf, hpi, grade, is_fake)

        days_since = None
        if perf.launch_date:
            days_since = (date.today() - perf.launch_date).days

        return HPIResult(
            dish_id=perf.dish_id,
            dish_name=perf.dish_name,
            hpi_score=hpi,
            grade=grade,
            is_fake_hit=is_fake,
            fake_hit_reasons=fake_reasons,
            dimension_scores={
                "点单率": round(calc_order_rate(perf), 1),
                "复购率": round(calc_repurchase_rate(perf), 1),
                "好评率": round(calc_positive_rate(perf), 1),
                "毛利达标": round(calc_margin_hit(perf), 1),
                "连带提升": round(calc_ticket_lift(perf), 1),
                "出品效率": round(calc_efficiency(perf), 1),
                "低退菜": round(calc_low_return(perf), 1),
            },
            recommendations=recs,
            days_since_launch=days_since,
        )

    def batch_evaluate(
        self,
        performances: List[DishPerformance],
        weights: Optional[Dict[str, float]] = None,
        sort_by: str = "hpi",
    ) -> List[HPIResult]:
        """
        批量评估多个菜品。

        Args:
            performances: 菜品表现数据列表
            weights: HPI 权重
            sort_by: 排序方式 - "hpi"(分数降序) 或 "fake_first"(伪爆品优先)

        Returns:
            HPIResult 列表
        """
        results = [self.evaluate(p, weights) for p in performances]

        if sort_by == "fake_first":
            results.sort(key=lambda r: (not r.is_fake_hit, -r.hpi_score))
        else:
            results.sort(key=lambda r: -r.hpi_score)

        logger.info(
            "批量 HPI 评估完成",
            total=len(results),
            hits=sum(1 for r in results if r.grade == "爆品苗子"),
            potential=sum(1 for r in results if r.grade == "潜力股"),
            fake_hits=sum(1 for r in results if r.is_fake_hit),
        )
        return results
