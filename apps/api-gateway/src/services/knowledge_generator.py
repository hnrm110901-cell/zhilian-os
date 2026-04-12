"""
知识库生成管道 — 从历史数据自动提炼经营智能
对标 Palantir Foundry 的 Ontology + Action

核心能力：
  1. StoreMemory 回填：从历史订单推算峰值模式/季节模式/节假日效应
  2. CostTruth 基线：从历史采购+销售交叉验证成本真相
  3. 菜品表现矩阵：毛利×销量四象限分析
  4. 会员RFM分群：从消费记录计算 Recency/Frequency/Monetary
  5. 人效基线：营收/人/时
  6. 供应商评分：交付准时率/价格稳定性/质量

输出：经营体检报告（接入屯象OS第一天就能看到）

使用方式：
  generator = KnowledgeGenerator()
  report = generator.generate_health_report(timeline_analysis, entity_maps)
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import structlog

from .timeline_assembler import TimelineAnalysis, DailySnapshot

logger = structlog.get_logger()


# ── 知识实体 ──────────────────────────────────────────────────────────────────

@dataclass
class DishPerformance:
    """菜品表现"""
    dish_id: str
    dish_name: str
    total_sold: int
    total_revenue_fen: int
    avg_price_fen: int
    estimated_cost_rate: float     # 估算成本率 0.0~1.0
    quadrant: str                  # star/cash_cow/question/dog
    recommendation: str


@dataclass
class CustomerSegment:
    """会员分群（RFM）"""
    segment_name: str              # 高价值/活跃/沉睡/流失预警/新客
    count: int
    avg_monetary_fen: int
    avg_frequency: float
    avg_recency_days: float
    action: str                    # 建议动作


@dataclass
class StaffEfficiency:
    """人效分析"""
    total_employees: int
    revenue_per_person_per_hour_fen: int
    peak_hour_gap: int             # 峰值时段人力缺口
    recommendation: str


@dataclass
class SupplierScore:
    """供应商评分"""
    supplier_id: str
    supplier_name: str
    price_stability: float         # 价格稳定性 0~1
    delivery_timeliness: float     # 交付准时率 0~1
    overall_score: float           # 综合评分 0~1


@dataclass
class HealthReport:
    """
    经营体检报告 — 接入屯象OS第一天即出

    6维分析：
    1. 营收健康度：月营收趋势/客单价/翻台率
    2. 成本真相：食材成本率/TOP5异常菜品/¥可优化空间
    3. 菜品表现：四象限分析（明星/金牛/问题/瘦狗）
    4. 会员资产：RFM分群/流失预警
    5. 人效分析：营收/人/时/峰值缺口
    6. 供应商评估：价格稳定性/集中度风险
    """
    store_id: str
    brand_id: str
    report_date: str
    data_period: str               # "2025-09 至 2026-03"

    # 1. 营收健康度
    revenue_summary: Dict = field(default_factory=dict)

    # 2. 成本真相
    cost_summary: Dict = field(default_factory=dict)

    # 3. 菜品表现
    dish_performances: List[DishPerformance] = field(default_factory=list)
    dish_quadrant_summary: Dict = field(default_factory=dict)

    # 4. 会员资产
    customer_segments: List[CustomerSegment] = field(default_factory=list)
    customer_summary: Dict = field(default_factory=dict)

    # 5. 人效分析
    staff_efficiency: Optional[StaffEfficiency] = None

    # 6. 供应商评估
    supplier_scores: List[SupplierScore] = field(default_factory=list)

    # AI建议（3个立即可执行的¥节省动作）
    ai_recommendations: List[Dict] = field(default_factory=list)

    # 综合健康分（0~100）
    overall_health_score: float = 0.0


class KnowledgeGenerator:
    """
    知识库生成器

    从融合后的历史数据中提炼经营知识，
    生成经营体检报告
    """

    def generate_health_report(
        self,
        store_id: str,
        brand_id: str,
        timeline: Optional[TimelineAnalysis] = None,
        orders: Optional[List[Dict]] = None,
        dishes: Optional[List[Dict]] = None,
        customers: Optional[List[Dict]] = None,
        employees: Optional[List[Dict]] = None,
        suppliers: Optional[List[Dict]] = None,
    ) -> HealthReport:
        """
        生成经营体检报告

        Args:
            store_id: 门店ID
            brand_id: 品牌ID
            timeline: 时间线分析结果（可选）
            orders: 历史订单列表
            dishes: 菜品列表（含销量/成本）
            customers: 客户列表（含消费记录）
            employees: 员工列表
            suppliers: 供应商列表
        """
        report = HealthReport(
            store_id=store_id,
            brand_id=brand_id,
            report_date=date.today().isoformat(),
            data_period="",
        )

        # 1. 营收健康度
        if timeline:
            report.revenue_summary = self._analyze_revenue(timeline)
            report.data_period = (
                f"{timeline.date_range_start.isoformat()} 至 "
                f"{timeline.date_range_end.isoformat()}"
            )

        # 2. 成本分析（从菜品数据推算）
        if dishes:
            report.cost_summary = self._analyze_cost(dishes)

        # 3. 菜品表现
        if dishes:
            report.dish_performances = self._analyze_dishes(dishes)
            report.dish_quadrant_summary = self._summarize_quadrants(
                report.dish_performances
            )

        # 4. 会员分群
        if customers:
            report.customer_segments = self._segment_customers(customers)
            report.customer_summary = self._summarize_customers(
                customers, report.customer_segments
            )

        # 5. 人效分析
        if employees and timeline:
            report.staff_efficiency = self._analyze_staff_efficiency(
                employees, timeline
            )

        # 6. 供应商评分
        if suppliers:
            report.supplier_scores = self._score_suppliers(suppliers)

        # 综合健康分
        report.overall_health_score = self._calculate_health_score(report)

        # AI建议
        report.ai_recommendations = self._generate_recommendations(report)

        logger.info(
            "knowledge_generator.report_generated",
            store_id=store_id,
            health_score=report.overall_health_score,
            recommendations=len(report.ai_recommendations),
        )

        return report

    def _analyze_revenue(self, timeline: TimelineAnalysis) -> Dict:
        """分析营收健康度"""
        snapshots = timeline.daily_snapshots
        if not snapshots:
            return {"status": "no_data"}

        total_revenue_fen = sum(s.total_revenue_fen for s in snapshots)
        total_orders = sum(s.total_orders for s in snapshots)
        total_days = len(snapshots)

        avg_daily_revenue_fen = total_revenue_fen // max(total_days, 1)
        avg_order_value_fen = total_revenue_fen // max(total_orders, 1) if total_orders > 0 else 0

        # 月度趋势（按自然月分组）
        monthly: Dict[str, Dict] = defaultdict(lambda: {"revenue_fen": 0, "orders": 0, "days": 0})
        for snap in snapshots:
            month_key = snap.date.strftime("%Y-%m")
            monthly[month_key]["revenue_fen"] += snap.total_revenue_fen
            monthly[month_key]["orders"] += snap.total_orders
            monthly[month_key]["days"] += 1

        monthly_trend = []
        for month_key in sorted(monthly.keys()):
            m = monthly[month_key]
            monthly_trend.append({
                "month": month_key,
                "revenue_fen": m["revenue_fen"],
                "revenue_yuan": round(m["revenue_fen"] / 100, 2),
                "orders": m["orders"],
                "avg_order_value_yuan": round(
                    m["revenue_fen"] / max(m["orders"], 1) / 100, 2
                ),
            })

        # 近3月环比
        mom_change = None
        if len(monthly_trend) >= 2:
            last = monthly_trend[-1]["revenue_fen"]
            prev = monthly_trend[-2]["revenue_fen"]
            if prev > 0:
                mom_change = round((last - prev) / prev * 100, 1)

        return {
            "total_revenue_yuan": round(total_revenue_fen / 100, 2),
            "total_orders": total_orders,
            "total_days": total_days,
            "avg_daily_revenue_yuan": round(avg_daily_revenue_fen / 100, 2),
            "avg_order_value_yuan": round(avg_order_value_fen / 100, 2),
            "monthly_trend": monthly_trend,
            "month_over_month_change_pct": mom_change,
            "peak_patterns": timeline.peak_patterns,
            "weekly_patterns": timeline.weekly_patterns,
        }

    def _analyze_cost(self, dishes: List[Dict]) -> Dict:
        """分析成本真相"""
        total_revenue_fen = 0
        total_cost_fen = 0
        high_cost_dishes = []

        for dish in dishes:
            revenue = dish.get("total_revenue_fen", 0)
            cost = dish.get("total_cost_fen", 0)
            total_revenue_fen += revenue
            total_cost_fen += cost

            if revenue > 0:
                cost_rate = cost / revenue
                if cost_rate > 0.45:  # 成本率超过45%的是异常菜品
                    high_cost_dishes.append({
                        "dish_name": dish.get("name", ""),
                        "cost_rate": round(cost_rate * 100, 1),
                        "revenue_yuan": round(revenue / 100, 2),
                        "cost_yuan": round(cost / 100, 2),
                        "optimization_yuan": round((cost - revenue * 0.35) / 100, 2),
                    })

        cost_rate = total_cost_fen / max(total_revenue_fen, 1)
        # 行业基准：正餐35%，快餐30%
        benchmark = 0.35
        optimization_fen = max(0, total_cost_fen - int(total_revenue_fen * benchmark))

        high_cost_dishes.sort(key=lambda d: d["optimization_yuan"], reverse=True)

        return {
            "total_cost_yuan": round(total_cost_fen / 100, 2),
            "cost_rate_pct": round(cost_rate * 100, 1),
            "industry_benchmark_pct": round(benchmark * 100, 1),
            "optimization_potential_yuan": round(optimization_fen / 100, 2),
            "top_high_cost_dishes": high_cost_dishes[:5],
        }

    def _analyze_dishes(self, dishes: List[Dict]) -> List[DishPerformance]:
        """菜品四象限分析"""
        if not dishes:
            return []

        # 计算中位数作为分界线
        revenues = [d.get("total_revenue_fen", 0) for d in dishes if d.get("total_revenue_fen", 0) > 0]
        sold_counts = [d.get("total_sold", 0) for d in dishes if d.get("total_sold", 0) > 0]

        if not revenues or not sold_counts:
            return []

        median_revenue = sorted(revenues)[len(revenues) // 2]
        median_sold = sorted(sold_counts)[len(sold_counts) // 2]

        performances = []
        for dish in dishes:
            sold = dish.get("total_sold", 0)
            revenue_fen = dish.get("total_revenue_fen", 0)
            cost_fen = dish.get("total_cost_fen", 0)
            if sold == 0:
                continue

            avg_price = revenue_fen // sold
            cost_rate = cost_fen / max(revenue_fen, 1)
            margin_rate = 1 - cost_rate
            high_margin = margin_rate > 0.55  # 毛利率>55%为高毛利
            high_volume = sold > median_sold

            if high_margin and high_volume:
                quadrant = "star"
                recommendation = "维持现状，可适当提价测试"
            elif not high_margin and high_volume:
                quadrant = "cash_cow"
                recommendation = "优化BOM配方或调整价格"
            elif high_margin and not high_volume:
                quadrant = "question"
                recommendation = "加大推荐力度，提升曝光"
            else:
                quadrant = "dog"
                recommendation = "考虑下架或彻底改良"

            performances.append(DishPerformance(
                dish_id=dish.get("id", ""),
                dish_name=dish.get("name", ""),
                total_sold=sold,
                total_revenue_fen=revenue_fen,
                avg_price_fen=avg_price,
                estimated_cost_rate=round(cost_rate, 3),
                quadrant=quadrant,
                recommendation=recommendation,
            ))

        return performances

    def _summarize_quadrants(self, performances: List[DishPerformance]) -> Dict:
        """汇总四象限"""
        counts = {"star": 0, "cash_cow": 0, "question": 0, "dog": 0}
        for p in performances:
            counts[p.quadrant] = counts.get(p.quadrant, 0) + 1

        return {
            "star": {"count": counts["star"], "label": "明星菜（高毛利高销量）"},
            "cash_cow": {"count": counts["cash_cow"], "label": "金牛菜（低毛利高销量）"},
            "question": {"count": counts["question"], "label": "问题菜（高毛利低销量）"},
            "dog": {"count": counts["dog"], "label": "瘦狗菜（低毛利低销量）"},
        }

    def _segment_customers(self, customers: List[Dict]) -> List[CustomerSegment]:
        """RFM分群"""
        today = date.today()
        segments: Dict[str, List[Dict]] = {
            "高价值": [],
            "活跃": [],
            "沉睡": [],
            "流失预警": [],
            "新客": [],
        }

        for c in customers:
            total_amount = c.get("total_amount", 0)
            total_visits = c.get("total_visits", 0)
            last_visit = c.get("last_visit_date")

            # 计算 recency（天数）
            recency_days = 999
            if last_visit:
                if isinstance(last_visit, str):
                    try:
                        last_visit = datetime.fromisoformat(
                            last_visit.replace("Z", "+00:00")
                        ).date()
                    except (ValueError, TypeError):
                        last_visit = None
                if isinstance(last_visit, date):
                    recency_days = (today - last_visit).days

            # 分群规则
            if total_visits >= 10 and total_amount > 5000 and recency_days < 30:
                segments["高价值"].append(c)
            elif total_visits >= 3 and recency_days < 60:
                segments["活跃"].append(c)
            elif total_visits >= 3 and 60 <= recency_days < 120:
                segments["沉睡"].append(c)
            elif total_visits >= 3 and recency_days >= 120:
                segments["流失预警"].append(c)
            else:
                segments["新客"].append(c)

        actions = {
            "高价值": "VIP专属服务，生日/纪念日关怀，优先推新品试吃",
            "活跃": "积分奖励，推荐新菜，鼓励储值",
            "沉睡": "发送唤醒优惠券，短信/企微触达",
            "流失预警": "高折扣召回，电话回访了解原因",
            "新客": "首次消费优惠，引导注册会员",
        }

        result = []
        for seg_name, members in segments.items():
            if not members:
                result.append(CustomerSegment(
                    segment_name=seg_name, count=0,
                    avg_monetary_fen=0, avg_frequency=0,
                    avg_recency_days=0, action=actions[seg_name],
                ))
                continue

            avg_amount = sum(m.get("total_amount", 0) for m in members) / len(members)
            avg_visits = sum(m.get("total_visits", 0) for m in members) / len(members)

            result.append(CustomerSegment(
                segment_name=seg_name,
                count=len(members),
                avg_monetary_fen=int(avg_amount * 100),
                avg_frequency=round(avg_visits, 1),
                avg_recency_days=0,
                action=actions[seg_name],
            ))

        return result

    def _summarize_customers(
        self, customers: List[Dict], segments: List[CustomerSegment]
    ) -> Dict:
        """汇总客户概况"""
        total = len(customers)
        active = sum(1 for s in segments if s.segment_name in ("高价值", "活跃") for _ in range(s.count))
        sleeping = sum(s.count for s in segments if s.segment_name == "沉睡")
        lost = sum(s.count for s in segments if s.segment_name == "流失预警")

        return {
            "total_customers": total,
            "active_customers": active,
            "sleeping_customers": sleeping,
            "lost_warning_customers": lost,
        }

    def _analyze_staff_efficiency(
        self, employees: List[Dict], timeline: TimelineAnalysis
    ) -> StaffEfficiency:
        """人效分析"""
        total_emp = len(employees)
        total_revenue_fen = sum(s.total_revenue_fen for s in timeline.daily_snapshots)
        total_days = max(len(timeline.daily_snapshots), 1)

        # 假设每天工作8小时
        total_hours = total_emp * total_days * 8
        rev_per_person_hour = total_revenue_fen // max(total_hours, 1)

        # 峰值人力缺口估算
        peak_patterns = timeline.peak_patterns
        peak_hours = peak_patterns.get("peak_hours", [])
        avg_daily_orders = peak_patterns.get("avg_daily_orders", 0)
        # 峰值时段如果订单量是平均的2倍以上，说明人力可能不足
        peak_gap = 0
        if peak_hours:
            max_peak = max(p.get("avg_events", 0) for p in peak_hours)
            avg_hourly = avg_daily_orders / 12 if avg_daily_orders > 0 else 0
            if avg_hourly > 0 and max_peak > avg_hourly * 2:
                peak_gap = max(1, int((max_peak - avg_hourly * 1.5) / 10))

        rec = "人效良好" if rev_per_person_hour > 5000 else "建议优化排班，峰值时段增加兼职"

        return StaffEfficiency(
            total_employees=total_emp,
            revenue_per_person_per_hour_fen=rev_per_person_hour,
            peak_hour_gap=peak_gap,
            recommendation=rec,
        )

    def _score_suppliers(self, suppliers: List[Dict]) -> List[SupplierScore]:
        """供应商评分（基于历史数据推算）"""
        scores = []
        for s in suppliers:
            # 从供应商元数据中提取评分因子
            on_time_rate = s.get("delivery_on_time_rate", 0.8)
            price_variance = s.get("price_variance", 0.05)
            price_stability = max(0, 1 - price_variance * 5)  # 波动越小分数越高

            overall = round(on_time_rate * 0.6 + price_stability * 0.4, 2)

            scores.append(SupplierScore(
                supplier_id=s.get("id", ""),
                supplier_name=s.get("name", ""),
                price_stability=round(price_stability, 2),
                delivery_timeliness=round(on_time_rate, 2),
                overall_score=overall,
            ))

        scores.sort(key=lambda s: s.overall_score, reverse=True)
        return scores

    def _calculate_health_score(self, report: HealthReport) -> float:
        """计算综合健康分（0~100）"""
        score = 50.0  # 基础分

        # 营收趋势加分
        mom = report.revenue_summary.get("month_over_month_change_pct")
        if mom is not None:
            if mom > 5:
                score += 15
            elif mom > 0:
                score += 10
            elif mom > -5:
                score += 5
            # 下降超过5%不加分

        # 成本率评分
        cost_rate = report.cost_summary.get("cost_rate_pct", 35)
        if cost_rate < 30:
            score += 15
        elif cost_rate < 35:
            score += 10
        elif cost_rate < 40:
            score += 5

        # 菜品健康度
        quad = report.dish_quadrant_summary
        if quad:
            star_pct = quad.get("star", {}).get("count", 0)
            dog_pct = quad.get("dog", {}).get("count", 0)
            total = sum(q.get("count", 0) for q in quad.values())
            if total > 0:
                if star_pct / total > 0.3:
                    score += 10
                if dog_pct / total < 0.2:
                    score += 5

        # 会员健康度
        cs = report.customer_summary
        if cs:
            total_c = cs.get("total_customers", 0)
            active_c = cs.get("active_customers", 0)
            if total_c > 0 and active_c / total_c > 0.4:
                score += 10

        return min(100.0, round(score, 1))

    def _generate_recommendations(self, report: HealthReport) -> List[Dict]:
        """生成AI建议（3个立即可执行的¥节省动作）"""
        recommendations = []

        # 建议1：高成本菜品优化
        top_cost = report.cost_summary.get("top_high_cost_dishes", [])
        if top_cost:
            dish = top_cost[0]
            recommendations.append({
                "action": f"优化「{dish['dish_name']}」的BOM配方",
                "expected_saving_yuan": dish.get("optimization_yuan", 0),
                "confidence": 0.8,
                "priority": "high",
                "detail": f"当前成本率 {dish['cost_rate']}%，行业基准 35%",
            })

        # 建议2：沉睡客户唤醒
        sleeping = 0
        for seg in report.customer_segments:
            if seg.segment_name == "沉睡":
                sleeping = seg.count
        if sleeping > 0:
            estimated_recovery = int(sleeping * 0.1 * 150 * 100)  # 10%唤醒率×客单150元
            recommendations.append({
                "action": f"发送沉睡客户唤醒优惠券（{sleeping}人）",
                "expected_saving_yuan": round(estimated_recovery / 100, 2),
                "confidence": 0.6,
                "priority": "medium",
                "detail": f"预计10%唤醒率，每人消费¥150",
            })

        # 建议3：瘦狗菜品下架
        dog_dishes = [d for d in report.dish_performances if d.quadrant == "dog"]
        if dog_dishes:
            recommendations.append({
                "action": f"考虑下架 {len(dog_dishes)} 道低效菜品",
                "expected_saving_yuan": round(
                    sum(d.total_revenue_fen * d.estimated_cost_rate for d in dog_dishes[:3]) / 100, 2
                ),
                "confidence": 0.7,
                "priority": "medium",
                "detail": "释放备料成本和厨房产能",
            })

        return recommendations[:3]
