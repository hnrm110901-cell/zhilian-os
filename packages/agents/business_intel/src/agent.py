"""
BusinessIntelAgent — Phase 12 经营智能体
合并 DecisionAgent + KPIAgent + OrderAgent

5个核心 Agent：
  RevenueAnomalyAgent  营收异常检测
  KpiScorecardAgent    KPI健康度快照
  OrderForecastAgent   订单量/营收预测
  BizInsightAgent      综合经营洞察（Top3决策）
  ScenarioMatchAgent   经营场景识别
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.business_intel import (
    BizMetricSnapshot, RevenueAlert, KpiScorecard, OrderForecast,
    BizDecision, ScenarioRecord, BizIntelLog,
    AnomalyLevelEnum, ScenarioTypeEnum, BizIntelAgentTypeEnum,
    DecisionPriorityEnum, DecisionStatusEnum,
)
from src.services.org_hierarchy_service import OrgHierarchyService

logger = logging.getLogger(__name__)

_LLM_ENABLED = os.getenv("LLM_ENABLED", "true").lower() == "true"


async def _ai_insight(system: str, user_data: dict) -> Optional[str]:
    """调用 Claude API 生成洞察（LLM_ENABLED=false 时降级为 None）"""
    if not _LLM_ENABLED:
        return None
    try:
        from src.core.llm import get_llm_client
        prompt = json.dumps(user_data, ensure_ascii=False, default=str)
        return (await get_llm_client().generate(prompt=prompt, system_prompt=system, max_tokens=400)).strip() or None
    except Exception as exc:
        logger.warning("biz_intel_llm_insight_failed: %s", str(exc))
        return None


# ─────────────────────────────────────────────
# 纯函数层（可独立测试）
# ─────────────────────────────────────────────

def compute_deviation_pct(actual: float, expected: float) -> float:
    """营收偏差百分比（正=超预期，负=不及预期）"""
    if expected <= 0:
        return 0.0
    return round((actual - expected) / expected * 100, 2)


def classify_anomaly_level(deviation_pct: float) -> str:
    """根据偏差幅度分级"""
    abs_dev = abs(deviation_pct)
    if abs_dev >= 30:
        return "severe"
    if abs_dev >= 15:
        return "critical"
    if abs_dev >= 8:
        return "warning"
    return "normal"


def estimate_revenue_impact_yuan(deviation_pct: float, expected_yuan: float) -> float:
    """¥影响金额 = 偏差% × 预期营收"""
    return round(deviation_pct / 100 * expected_yuan, 2)


def compute_kpi_achievement(actual: float, target: float) -> float:
    """KPI达成率（0-∞，>1 为超额完成）"""
    if target <= 0:
        return 1.0
    return round(actual / target, 4)


def compute_health_score(achievements: list[float], weights: list[float]) -> float:
    """
    综合健康度（0-100）
    - 达成率=1.0 → 80分基础分
    - 每超出 10% → +5分（上限100）
    - 每低于 10% → -10分（下限0）
    """
    if not achievements:
        return 50.0
    scores = []
    for ach in achievements:
        if ach >= 1.0:
            score = min(100.0, 80 + (ach - 1.0) * 50)
        else:
            score = max(0.0, 80 - (1.0 - ach) * 100)
        scores.append(score)
    if weights and len(weights) == len(scores):
        total_w = sum(weights)
        return round(sum(s * w for s, w in zip(scores, weights)) / total_w, 1)
    return round(sum(scores) / len(scores), 1)


def classify_kpi_status(achievement: float) -> str:
    if achievement >= 1.10:
        return "excellent"
    if achievement >= 1.0:
        return "on_track"
    if achievement >= 0.85:
        return "at_risk"
    return "off_track"


def compute_trend_slope(values: list[float]) -> float:
    """简单线性回归斜率（日均变化量）"""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return round(num / den, 4) if den else 0.0


def predict_next_period(recent_avg: float, slope: float, days: int) -> float:
    """线性外推预测"""
    return round(max(0.0, recent_avg + slope * days), 2)


def compute_forecast_confidence(data_days: int, trend_stability: float) -> float:
    """预测置信度（数据越多、趋势越稳定，置信度越高）"""
    data_factor = min(data_days / 30.0, 1.0) * 0.6
    stability_factor = max(0.0, 1.0 - trend_stability) * 0.4
    return round(min(0.95, data_factor + stability_factor), 2)


def score_recommendation(saving_yuan: float, urgency_hours: int, confidence: float) -> float:
    """推荐建议优先级评分（0-100）"""
    saving_score = min(saving_yuan / 10000.0, 1.0) * 40
    urgency_score = max(0.0, (48 - urgency_hours) / 48.0) * 30
    conf_score = confidence * 30
    return round(saving_score + urgency_score + conf_score, 1)


def classify_scenario(
    revenue_deviation_pct: float,
    food_cost_ratio: float,
    labor_cost_ratio: float,
    complaint_count: int,
    food_cost_alert: float = 0.42,
    labor_cost_alert: float = 0.35,
) -> str:
    if revenue_deviation_pct >= 15:
        return "peak_revenue"
    if revenue_deviation_pct <= -15:
        return "revenue_slump"
    if food_cost_ratio >= food_cost_alert or labor_cost_ratio >= labor_cost_alert:
        return "cost_overrun"
    if complaint_count >= 5:
        return "inventory_crisis"
    return "normal_ops"


# ─────────────────────────────────────────────
# Agent 1: 营收异常检测
# ─────────────────────────────────────────────

class RevenueAnomalyAgent:
    """
    营收异常检测
    OKR: 每日营收异常识别率 >95%
    """

    async def detect(
        self,
        brand_id: str,
        store_id: str,
        check_date: date,
        actual_yuan: float,
        expected_yuan: float,
        db: AsyncSession,
        save: bool = True,
    ) -> dict:
        t0 = datetime.utcnow()
        deviation_pct = compute_deviation_pct(actual_yuan, expected_yuan)
        level = classify_anomaly_level(deviation_pct)
        impact_yuan = estimate_revenue_impact_yuan(deviation_pct, expected_yuan)

        root_causes = self._infer_root_causes(deviation_pct, actual_yuan, expected_yuan)
        action = self._build_action(level, deviation_pct, impact_yuan)

        alert_id = str(uuid.uuid4())
        if save and level != "normal":
            existing = await db.execute(
                select(RevenueAlert).where(
                    and_(
                        RevenueAlert.brand_id == brand_id,
                        RevenueAlert.store_id == store_id,
                        RevenueAlert.alert_date == check_date,
                        RevenueAlert.is_resolved == False,
                    )
                )
            )
            if not existing.scalar_one_or_none():
                db.add(RevenueAlert(
                    id=alert_id,
                    brand_id=brand_id,
                    store_id=store_id,
                    alert_date=check_date,
                    anomaly_level=level,
                    actual_revenue_yuan=Decimal(str(actual_yuan)),
                    expected_revenue_yuan=Decimal(str(expected_yuan)),
                    deviation_pct=deviation_pct,
                    impact_yuan=Decimal(str(abs(impact_yuan))),
                    root_causes=root_causes,
                    recommended_action=action,
                    confidence=0.88,
                ))
                await self._log(brand_id, db, {"store_id": store_id, "date": str(check_date)},
                                {"level": level, "impact_yuan": abs(impact_yuan)})
                await db.flush()

        duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        return {
            "alert_id": alert_id if level != "normal" else None,
            "store_id": store_id,
            "check_date": str(check_date),
            "anomaly_level": level,
            "actual_revenue_yuan": actual_yuan,
            "expected_revenue_yuan": expected_yuan,
            "deviation_pct": deviation_pct,
            "impact_yuan": abs(impact_yuan),
            "root_causes": root_causes,
            "recommended_action": action,
            "ai_insight": await _ai_insight(
                system=(
                    "你是智链OS营收分析AI。根据营收异常数据，用2-3句话给出应对建议，"
                    "必须包含：异常原因判断、建议动作、¥预期挽回金额、置信度。"
                    "回复语言：中文，简洁。"
                ),
                user_data={
                    "anomaly_level": level,
                    "deviation_pct": deviation_pct,
                    "impact_yuan": abs(impact_yuan),
                    "root_causes": root_causes,
                    "actual_yuan": actual_yuan,
                    "expected_yuan": expected_yuan,
                },
            ),
            "confidence": 0.88,
            "duration_ms": duration_ms,
        }

    def _infer_root_causes(self, deviation_pct: float, actual: float, expected: float) -> list:
        causes = []
        if deviation_pct < -15:
            causes.append("severe_revenue_miss")
        elif deviation_pct < -8:
            causes.append("moderate_revenue_miss")
        if deviation_pct > 15:
            causes.append("peak_demand_surge")
        if not causes:
            causes.append("minor_fluctuation")
        return causes

    def _build_action(self, level: str, deviation_pct: float, impact_yuan: float) -> str:
        if level == "severe":
            return f"严重异常：营收偏差 {abs(deviation_pct):.1f}%，¥{abs(impact_yuan):.0f} 损失，立即排查并启动应急预案。"
        if level == "critical":
            return f"重要预警：营收偏差 {abs(deviation_pct):.1f}%，¥{abs(impact_yuan):.0f} 损失，今日需重点复盘。"
        if level == "warning":
            return f"轻微异常：营收偏差 {abs(deviation_pct):.1f}%，关注趋势，必要时调整运营策略。"
        return "营收正常，保持当前策略。"

    async def _log(self, brand_id, db, inp, out):
        db.add(BizIntelLog(
            id=str(uuid.uuid4()), brand_id=brand_id,
            agent_type=BizIntelAgentTypeEnum.enums[0] if hasattr(BizIntelAgentTypeEnum, 'enums') else "revenue_anomaly",
            input_params=inp, output_summary=out, success=True,
        ))


# ─────────────────────────────────────────────
# Agent 2: KPI 健康度快照
# ─────────────────────────────────────────────

class KpiScorecardAgent:
    """
    KPI健康度快照
    OKR: 预测准确度 ±5%以内
    """

    # 默认KPI配置（可从数据库覆盖）
    DEFAULT_KPI_CONFIG = [
        {"kpi_id": "revenue_achievement", "name": "营收达成率", "category": "revenue", "weight": 0.30, "target": 1.0},
        {"kpi_id": "food_cost_ratio",     "name": "食材成本率", "category": "cost",    "weight": 0.25, "target": 0.38},
        {"kpi_id": "labor_cost_ratio",    "name": "人力成本率", "category": "cost",    "weight": 0.20, "target": 0.28},
        {"kpi_id": "table_turnover",      "name": "翻台率",     "category": "efficiency", "weight": 0.15, "target": 3.5},
        {"kpi_id": "complaint_rate",      "name": "投诉率",     "category": "cost",    "weight": 0.10, "target": 0.01},
    ]

    async def snapshot(
        self,
        brand_id: str,
        store_id: str,
        period: str,
        db: AsyncSession,
        kpi_values: Optional[dict] = None,
        save: bool = True,
    ) -> dict:
        """
        生成KPI健康度评分卡
        kpi_values: {"revenue_achievement": 1.05, "food_cost_ratio": 0.40, ...}
        """
        t0 = datetime.utcnow()
        values = kpi_values or {}

        # 从 OrgHierarchyService 动态读取 KPI 权重配置
        svc = OrgHierarchyService(db)
        kpi_weights = await svc.resolve(store_id, "biz_intel_kpi_weights", default={
            "food_cost": 0.25, "table_turnover": 0.15, "revenue": 0.30,
            "labor_cost": 0.20, "complaint": 0.10,
        })
        food_cost_weight = kpi_weights.get("food_cost", 0.25)
        table_turnover_weight = kpi_weights.get("table_turnover", 0.15)
        revenue_weight = kpi_weights.get("revenue", 0.30)
        labor_cost_weight = kpi_weights.get("labor_cost", 0.20)
        complaint_weight = kpi_weights.get("complaint", 0.10)

        # 使用动态权重覆盖默认 KPI 配置
        kpi_config = [
            {"kpi_id": "revenue_achievement", "name": "营收达成率", "category": "revenue",   "weight": revenue_weight,       "target": 1.0},
            {"kpi_id": "food_cost_ratio",     "name": "食材成本率", "category": "cost",      "weight": food_cost_weight,     "target": 0.38},
            {"kpi_id": "labor_cost_ratio",    "name": "人力成本率", "category": "cost",      "weight": labor_cost_weight,    "target": 0.28},
            {"kpi_id": "table_turnover",      "name": "翻台率",     "category": "efficiency", "weight": table_turnover_weight, "target": 3.5},
            {"kpi_id": "complaint_rate",      "name": "投诉率",     "category": "cost",      "weight": complaint_weight,     "target": 0.01},
        ]

        kpi_items = []
        achievements = []
        weights = []

        for cfg in kpi_config:
            kid = cfg["kpi_id"]
            actual = values.get(kid)
            if actual is None:
                continue
            target = cfg["target"]
            # 成本类KPI：实际越低越好（倒置达成率）
            if cfg["category"] == "cost":
                ach = compute_kpi_achievement(target, actual) if actual > 0 else 1.0
            else:
                ach = compute_kpi_achievement(actual, target)
            status = classify_kpi_status(ach)
            kpi_items.append({
                "kpi_id": kid,
                "name": cfg["name"],
                "category": cfg["category"],
                "actual": actual,
                "target": target,
                "achievement_pct": round(ach * 100, 1),
                "status": status,
            })
            achievements.append(ach)
            weights.append(cfg["weight"])

        health_score = compute_health_score(achievements, weights) if achievements else 50.0

        # 分类得分
        cat_scores = {"revenue": [], "cost": [], "efficiency": [], "quality": []}
        for item in kpi_items:
            cat_scores[item["category"]].append(item["achievement_pct"])
        def avg(lst): return round(sum(lst) / len(lst), 1) if lst else None

        at_risk = sum(1 for i in kpi_items if i["status"] == "at_risk")
        off_track = sum(1 for i in kpi_items if i["status"] == "off_track")

        # 改进优先级（按达成率升序）
        priorities = sorted(
            [i for i in kpi_items if i["status"] in ("at_risk", "off_track")],
            key=lambda x: x["achievement_pct"],
        )[:3]
        improvement = [
            {"kpi": p["name"], "gap_pct": round(100 - p["achievement_pct"], 1),
             "action": f"将{p['name']}从{p['actual']:.2f}提升至目标{p['target']:.2f}"}
            for p in priorities
        ]

        scorecard_id = str(uuid.uuid4())
        if save and db is not None and kpi_items:
            db.add(KpiScorecard(
                id=scorecard_id, brand_id=brand_id, store_id=store_id, period=period,
                overall_health_score=health_score,
                revenue_score=avg(cat_scores["revenue"]),
                cost_score=avg(cat_scores["cost"]),
                efficiency_score=avg(cat_scores["efficiency"]),
                quality_score=avg(cat_scores["quality"]),
                kpi_items=kpi_items,
                at_risk_count=at_risk,
                off_track_count=off_track,
                improvement_priorities=improvement,
                confidence=0.85,
            ))
            await db.flush()

        duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        return {
            "scorecard_id": scorecard_id,
            "store_id": store_id,
            "period": period,
            "overall_health_score": health_score,
            "revenue_score": avg(cat_scores["revenue"]),
            "cost_score": avg(cat_scores["cost"]),
            "efficiency_score": avg(cat_scores["efficiency"]),
            "quality_score": avg(cat_scores["quality"]),
            "kpi_items": kpi_items,
            "at_risk_count": at_risk,
            "off_track_count": off_track,
            "improvement_priorities": improvement,
            "ai_insight": await _ai_insight(
                system=(
                    "你是智链OS KPI分析AI。根据KPI健康度数据，用2-3句给出改进建议，"
                    "必须包含：最需改善的KPI、建议动作、¥预期改善金额、置信度。"
                    "回复语言：中文，简洁。"
                ),
                user_data={
                    "overall_health_score": health_score,
                    "at_risk_count": at_risk,
                    "off_track_count": off_track,
                    "worst_kpis": [i["name"] for i in kpi_items if i["status"] == "off_track"][:3],
                    "improvement_priorities": improvement,
                },
            ),
            "confidence": 0.85,
            "duration_ms": duration_ms,
        }


# ─────────────────────────────────────────────
# Agent 3: 订单量/营收预测
# ─────────────────────────────────────────────

class OrderForecastAgent:
    """
    订单量/营收预测
    OKR: 预测准确度 ±5%以内
    """

    async def forecast(
        self,
        brand_id: str,
        store_id: str,
        horizon_days: int,
        db: AsyncSession,
        save: bool = True,
    ) -> dict:
        t0 = datetime.utcnow()
        today = date.today()

        # 取最近30天快照
        cutoff = today - timedelta(days=30)
        result = await db.execute(
            select(BizMetricSnapshot).where(
                and_(
                    BizMetricSnapshot.brand_id == brand_id,
                    BizMetricSnapshot.store_id == store_id,
                    BizMetricSnapshot.snapshot_date >= cutoff,
                )
            ).order_by(BizMetricSnapshot.snapshot_date)
        )
        snapshots = result.scalars().all()

        if not snapshots:
            return self._empty_forecast(store_id, horizon_days)

        orders_series = [s.order_count for s in snapshots]
        revenue_series = [float(s.revenue_yuan) for s in snapshots]

        avg_orders = sum(orders_series) / len(orders_series)
        avg_revenue = sum(revenue_series) / len(revenue_series)
        slope_orders = compute_trend_slope(orders_series)
        slope_revenue = compute_trend_slope(revenue_series)

        predicted_orders = int(predict_next_period(avg_orders, slope_orders, horizon_days))
        predicted_revenue = predict_next_period(avg_revenue, slope_revenue, horizon_days)

        # 置信区间 ±15%
        lower = round(predicted_revenue * 0.85, 2)
        upper = round(predicted_revenue * 1.15, 2)

        # 趋势稳定性（标准差/均值）
        if avg_revenue > 0:
            variance = sum((v - avg_revenue) ** 2 for v in revenue_series) / len(revenue_series)
            stability = (variance ** 0.5) / avg_revenue
        else:
            stability = 0.5

        confidence = compute_forecast_confidence(len(snapshots), stability)

        forecast_id = str(uuid.uuid4())
        if save:
            db.add(OrderForecast(
                id=forecast_id, brand_id=brand_id, store_id=store_id,
                forecast_date=today, horizon_days=horizon_days,
                predicted_orders=predicted_orders,
                predicted_revenue_yuan=Decimal(str(predicted_revenue)),
                lower_bound_yuan=Decimal(str(lower)),
                upper_bound_yuan=Decimal(str(upper)),
                trend_slope=slope_revenue,
                avg_daily_orders_7d=avg_orders,
                avg_daily_revenue_7d=Decimal(str(avg_revenue)),
                confidence=confidence,
            ))
            await db.flush()

        duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        return {
            "forecast_id": forecast_id,
            "store_id": store_id,
            "horizon_days": horizon_days,
            "predicted_orders": predicted_orders,
            "predicted_revenue_yuan": predicted_revenue,
            "lower_bound_yuan": lower,
            "upper_bound_yuan": upper,
            "trend_slope_revenue": slope_revenue,
            "trend_direction": "up" if slope_revenue > 50 else ("down" if slope_revenue < -50 else "stable"),
            "data_points": len(snapshots),
            "ai_insight": await _ai_insight(
                system=(
                    "你是智链OS订单预测AI。根据预测数据，用2-3句给出经营建议，"
                    "必须包含：趋势判断、建议行动（备货/促销/调人）、¥预期营收、置信度。"
                    "回复语言：中文，简洁。"
                ),
                user_data={
                    "horizon_days": horizon_days,
                    "predicted_orders": predicted_orders,
                    "predicted_revenue_yuan": predicted_revenue,
                    "trend_slope": slope_revenue,
                    "confidence": confidence,
                },
            ),
            "confidence": confidence,
            "duration_ms": duration_ms,
        }

    def _empty_forecast(self, store_id: str, horizon_days: int) -> dict:
        return {
            "forecast_id": None,
            "store_id": store_id,
            "horizon_days": horizon_days,
            "predicted_orders": 0,
            "predicted_revenue_yuan": 0.0,
            "confidence": 0.0,
            "ai_insight": None,
            "reason": "暂无历史快照数据，请先录入BizMetricSnapshot。",
        }


# ─────────────────────────────────────────────
# Agent 4: 综合经营洞察（Top3决策）
# ─────────────────────────────────────────────

class BizInsightAgent:
    """
    综合经营洞察 — Top3建议
    OKR: 决策建议采纳率 >70%
    整合营收/KPI/订单三维数据，生成优先级排序的行动建议
    """

    async def generate(
        self,
        brand_id: str,
        store_id: str,
        db: AsyncSession,
        context: Optional[dict] = None,
        save: bool = True,
    ) -> dict:
        """
        生成今日Top3经营建议
        context: 可传入当日指标覆盖（否则从快照表读取）
        """
        t0 = datetime.utcnow()
        today = date.today()

        # 读取最新指标
        snap_result = await db.execute(
            select(BizMetricSnapshot).where(
                and_(
                    BizMetricSnapshot.brand_id == brand_id,
                    BizMetricSnapshot.store_id == store_id,
                )
            ).order_by(desc(BizMetricSnapshot.snapshot_date)).limit(1)
        )
        snap = snap_result.scalar_one_or_none()

        # 未处理预警
        alert_result = await db.execute(
            select(RevenueAlert).where(
                and_(
                    RevenueAlert.brand_id == brand_id,
                    RevenueAlert.store_id == store_id,
                    RevenueAlert.is_resolved == False,
                )
            ).order_by(desc(RevenueAlert.created_at)).limit(3)
        )
        alerts = alert_result.scalars().all()

        # 最新预测
        forecast_result = await db.execute(
            select(OrderForecast).where(
                and_(
                    OrderForecast.brand_id == brand_id,
                    OrderForecast.store_id == store_id,
                )
            ).order_by(desc(OrderForecast.created_at)).limit(1)
        )
        forecast = forecast_result.scalar_one_or_none()

        # 构建推荐建议
        recs = []
        ctx = context or {}

        # 推荐1：最紧急预警处理
        if alerts:
            top_alert = alerts[0]
            saving = float(top_alert.impact_yuan or 0)
            recs.append({
                "rank": 1,
                "category": "revenue_recovery",
                "title": f"营收异常处置（{top_alert.anomaly_level}级）",
                "action": top_alert.recommended_action or "立即复盘今日营收异常原因",
                "expected_saving_yuan": saving,
                "urgency_hours": 2,
                "confidence": float(top_alert.confidence or 0.8),
                "source": "revenue_alert",
            })

        # 推荐2：食材成本优化（如食材成本率高）
        food_cost_ratio = float(snap.food_cost_ratio or 0) if snap else ctx.get("food_cost_ratio", 0)
        if food_cost_ratio > 0.40:
            saving2 = float(snap.revenue_yuan or 0) * (food_cost_ratio - 0.38) if snap else 0
            recs.append({
                "rank": len(recs) + 1,
                "category": "cost_reduction",
                "title": f"食材成本率偏高（{food_cost_ratio*100:.1f}%，目标38%）",
                "action": "核查高损耗食材，优化采购计划，联系供应商比价",
                "expected_saving_yuan": round(saving2, 2),
                "urgency_hours": 24,
                "confidence": 0.82,
                "source": "kpi_analysis",
            })

        # 推荐3：预测驱动的营销建议
        if forecast and float(forecast.predicted_revenue_yuan) > 0:
            pred_rev = float(forecast.predicted_revenue_yuan)
            recs.append({
                "rank": len(recs) + 1,
                "category": "revenue_growth",
                "title": f"{forecast.horizon_days}天营收预测 ¥{pred_rev:,.0f}",
                "action": "趋势" + ("向好，维持现有运营策略" if float(forecast.trend_slope or 0) >= 0 else "下行，建议启动促销活动提振客流"),
                "expected_saving_yuan": max(0, pred_rev * 0.05),  # 5%弹性空间
                "urgency_hours": 48,
                "confidence": float(forecast.confidence or 0.75),
                "source": "order_forecast",
            })

        # 如无数据，生成通用建议
        if not recs:
            recs = [{
                "rank": 1,
                "category": "general",
                "title": "录入今日经营数据",
                "action": "请录入今日营收快照以启用AI经营建议",
                "expected_saving_yuan": 0,
                "urgency_hours": 4,
                "confidence": 1.0,
                "source": "system",
            }]

        # 排序并截取Top3
        recs = sorted(recs, key=lambda x: -score_recommendation(
            x["expected_saving_yuan"], x["urgency_hours"], x["confidence"]
        ))[:3]
        for i, r in enumerate(recs):
            r["rank"] = i + 1

        total_saving = sum(r["expected_saving_yuan"] for r in recs)
        priority = "p0" if any(r["urgency_hours"] <= 2 for r in recs) else "p1"

        decision_id = str(uuid.uuid4())
        if save:
            db.add(BizDecision(
                id=decision_id, brand_id=brand_id, store_id=store_id,
                decision_date=today,
                recommendations=recs,
                total_saving_yuan=Decimal(str(total_saving)),
                priority=priority,
                data_sources=["revenue_alerts", "biz_metric_snapshots", "order_forecasts"],
                confidence=0.80,
            ))
            await db.flush()

        duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        return {
            "decision_id": decision_id,
            "store_id": store_id,
            "decision_date": str(today),
            "top3_recommendations": recs,
            "total_saving_yuan": total_saving,
            "priority": priority,
            "ai_insight": await _ai_insight(
                system=(
                    "你是智链OS经营决策AI。根据Top3建议，用2-3句话给出今日经营重点，"
                    "必须包含：最优先行动、¥总预期收益、置信度。"
                    "回复语言：中文，简洁。"
                ),
                user_data={
                    "top3": [{"title": r["title"], "saving_yuan": r["expected_saving_yuan"],
                              "urgency_hours": r["urgency_hours"]} for r in recs],
                    "total_saving_yuan": total_saving,
                    "priority": priority,
                },
            ),
            "confidence": 0.80,
            "duration_ms": duration_ms,
        }


# ─────────────────────────────────────────────
# Agent 5: 经营场景识别
# ─────────────────────────────────────────────

class ScenarioMatchAgent:
    """
    经营场景识别
    - 识别当前门店经营场景（6类）
    - 匹配历史相似案例
    - 输出推荐作战手册
    """

    PLAYBOOKS = {
        "peak_revenue": [
            {"step": 1, "action": "立即增派服务员，缩短翻台等待", "owner": "楼面经理"},
            {"step": 2, "action": "开放备用库存，补充高销菜品", "owner": "厨师长"},
            {"step": 3, "action": "复盘峰值触发因素，复制成功经验", "owner": "店长"},
        ],
        "revenue_slump": [
            {"step": 1, "action": "今日启动优惠券推送（面向沉睡会员）", "owner": "营销"},
            {"step": 2, "action": "排查昨日差评，今日专项整改", "owner": "店长"},
            {"step": 3, "action": "联系周边企业推团购，拉升工作日客流", "owner": "店长"},
        ],
        "cost_overrun": [
            {"step": 1, "action": "核查食材损耗记录，识别高损耗SKU", "owner": "厨师长"},
            {"step": 2, "action": "临时停售利润率低于15%的菜品", "owner": "店长"},
            {"step": 3, "action": "联系供应商比价，本周完成询价对比", "owner": "采购"},
        ],
        "staff_shortage": [
            {"step": 1, "action": "启动跨店借调申请", "owner": "店长"},
            {"step": 2, "action": "临时简化菜单，聚焦高周转品类", "owner": "厨师长"},
        ],
        "inventory_crisis": [
            {"step": 1, "action": "紧急联系备用供应商，3小时内确认到货", "owner": "采购"},
            {"step": 2, "action": "下架缺货菜品，标注售罄", "owner": "楼面经理"},
        ],
        "normal_ops": [
            {"step": 1, "action": "按常规SOP执行，重点关注用餐高峰备货", "owner": "全员"},
        ],
    }

    async def match(
        self,
        brand_id: str,
        store_id: str,
        db: AsyncSession,
        metrics: Optional[dict] = None,
        save: bool = True,
    ) -> dict:
        t0 = datetime.utcnow()
        today = date.today()

        # 读取最新快照
        snap_result = await db.execute(
            select(BizMetricSnapshot).where(
                and_(
                    BizMetricSnapshot.brand_id == brand_id,
                    BizMetricSnapshot.store_id == store_id,
                )
            ).order_by(desc(BizMetricSnapshot.snapshot_date)).limit(1)
        )
        snap = snap_result.scalar_one_or_none()
        m = metrics or {}

        rev_dev = float(snap.revenue_deviation_pct or 0) if snap else m.get("revenue_deviation_pct", 0)
        food_ratio = float(snap.food_cost_ratio or 0) if snap else m.get("food_cost_ratio", 0.38)
        labor_ratio = float(snap.labor_cost_ratio or 0) if snap else m.get("labor_cost_ratio", 0.28)
        complaint_cnt = int(snap.complaint_count or 0) if snap else m.get("complaint_count", 0)

        # 从 OrgHierarchyService 动态读取成本告警阈值
        svc = OrgHierarchyService(db)
        food_cost_alert = await svc.resolve(store_id, "food_cost_alert_threshold", default=0.42)
        labor_cost_alert = await svc.resolve(store_id, "labor_cost_alert_threshold", default=0.35)
        cost_ratio_threshold = await svc.resolve(store_id, "labor_cost_ratio_target", default=0.35)

        scenario = classify_scenario(rev_dev, food_ratio, labor_ratio, complaint_cnt,
                                     food_cost_alert=food_cost_alert, labor_cost_alert=labor_cost_alert)
        playbook = self.PLAYBOOKS.get(scenario, self.PLAYBOOKS["normal_ops"])

        key_signals = [
            {"signal": "revenue_deviation_pct", "value": rev_dev, "threshold": 15},
            {"signal": "food_cost_ratio", "value": food_ratio, "threshold": food_cost_alert},
            {"signal": "labor_cost_ratio", "value": labor_ratio, "threshold": cost_ratio_threshold},
            {"signal": "complaint_count", "value": complaint_cnt, "threshold": 5},
        ]

        # 历史匹配（同品牌同场景最近3次）
        hist_result = await db.execute(
            select(ScenarioRecord).where(
                and_(
                    ScenarioRecord.brand_id == brand_id,
                    ScenarioRecord.scenario_type == scenario,
                )
            ).order_by(desc(ScenarioRecord.record_date)).limit(3)
        )
        hist = hist_result.scalars().all()
        historical_matches = [
            {"date": str(h.record_date), "store_id": h.store_id,
             "similarity": 0.85, "outcome": h.recommended_playbook}
            for h in hist
        ]

        record_id = str(uuid.uuid4())
        if save:
            db.add(ScenarioRecord(
                id=record_id, brand_id=brand_id, store_id=store_id,
                record_date=today, scenario_type=scenario, scenario_score=0.85,
                key_signals=key_signals, historical_matches=historical_matches,
                recommended_playbook=playbook, confidence=0.80,
            ))
            await db.flush()

        duration_ms = int((datetime.utcnow() - t0).total_seconds() * 1000)
        return {
            "record_id": record_id,
            "store_id": store_id,
            "record_date": str(today),
            "current_scenario": scenario,
            "scenario_score": 0.85,
            "key_signals": key_signals,
            "historical_matches": historical_matches,
            "recommended_playbook": playbook,
            "ai_insight": await _ai_insight(
                system=(
                    "你是智链OS场景识别AI。根据经营场景，用2-3句给出今日作战重点，"
                    "必须包含：场景判断、最关键的一步行动、¥预期收益/节省、置信度。"
                    "回复语言：中文，简洁。"
                ),
                user_data={
                    "scenario": scenario,
                    "revenue_deviation_pct": rev_dev,
                    "food_cost_ratio": food_ratio,
                    "playbook_steps": len(playbook),
                },
            ),
            "confidence": 0.80,
            "duration_ms": duration_ms,
        }
