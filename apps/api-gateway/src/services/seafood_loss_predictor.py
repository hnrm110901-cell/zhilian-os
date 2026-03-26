"""
海鲜损耗预测 AI 模型（Seafood Loss Predictor）

核心功能：
- 基于线性回归 + 季节系数 + 温度修正预测每日死亡量
- 最优采购量建议
- 高损耗风险品种排名
- 损耗趋势报告（按品种/鱼缸/原因）

金额单位：分（fen），API 返回时 /100 转元
纯 Python 实现，不依赖 sklearn / numpy
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()

# ── 季节系数（月份 → 系数，夏季高温损耗更高） ─────────────────────────────────
SEASON_COEFFICIENTS: Dict[int, float] = {
    1: 0.8, 2: 0.8, 3: 0.9, 4: 1.0,
    5: 1.1, 6: 1.3, 7: 1.5, 8: 1.5,
    9: 1.2, 10: 1.0, 11: 0.9, 12: 0.85,
}

# ── 品种基础死亡率（每日，无外部因素时的自然死亡率%） ───────────────────────────
SPECIES_BASE_MORTALITY: Dict[str, float] = {
    "波士顿龙虾": 0.005,
    "澳洲龙虾": 0.008,
    "帝王蟹": 0.010,
    "石斑鱼": 0.006,
    "东星斑": 0.007,
    "多宝鱼": 0.004,
    "鲈鱼": 0.003,
    "基围虾": 0.012,
    "皮皮虾": 0.015,
    "鲍鱼": 0.003,
    "生蚝": 0.002,
    "花甲": 0.008,
    "扇贝": 0.006,
}

# ── 最适水温范围（超出范围会增加死亡率） ──────────────────────────────────────
SPECIES_OPTIMAL_TEMP: Dict[str, Tuple[float, float]] = {
    "波士顿龙虾": (10.0, 15.0),
    "澳洲龙虾": (14.0, 18.0),
    "帝王蟹": (4.0, 8.0),
    "石斑鱼": (18.0, 24.0),
    "东星斑": (18.0, 25.0),
    "多宝鱼": (14.0, 18.0),
    "鲈鱼": (16.0, 22.0),
    "基围虾": (18.0, 25.0),
    "皮皮虾": (15.0, 22.0),
    "鲍鱼": (15.0, 20.0),
    "生蚝": (10.0, 18.0),
    "花甲": (15.0, 25.0),
    "扇贝": (10.0, 18.0),
}

# ── 鱼缸存放天数衰减因子（天数越长，死亡率递增） ──────────────────────────────
DAYS_DECAY_FACTOR = 0.02  # 每多一天，额外增加 2% 死亡率


@dataclass
class LossPrediction:
    """损耗预测结果"""
    species: str
    current_stock: int
    predicted_deaths: int
    mortality_rate: float  # 预测死亡率
    loss_amount_fen: int  # 损耗金额（分）
    loss_amount_yuan: float  # 损耗金额（元）
    confidence: float  # 置信度 0~1
    risk_level: str  # 低/中/高/极高
    factors: Dict[str, float]  # 各因子影响权重


@dataclass
class PurchaseRecommendation:
    """采购量建议"""
    species: str
    recommended_qty: int
    safety_stock: int
    expected_loss_during_lead: int
    expected_demand_during_lead: int
    reasoning: str
    cost_estimate_fen: int
    cost_estimate_yuan: float


@dataclass
class SpeciesRisk:
    """品种风险排名"""
    species: str
    risk_score: float  # 0~100
    risk_level: str
    predicted_daily_loss: int
    loss_value_fen: int
    loss_value_yuan: float
    primary_risk_factor: str


@dataclass
class LossReportItem:
    """损耗报告单项"""
    species: str
    total_deaths: int
    total_loss_fen: int
    total_loss_yuan: float
    avg_daily_loss: float
    trend: str  # 上升/下降/平稳
    trend_pct: float
    top_reason: str


@dataclass
class LossReport:
    """损耗趋势报告"""
    period_days: int
    start_date: str
    end_date: str
    total_loss_fen: int
    total_loss_yuan: float
    total_deaths: int
    by_species: List[LossReportItem]
    worst_species: str
    improvement_suggestions: List[str]


def _mean(values: List[float]) -> float:
    """计算平均值"""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: List[float]) -> float:
    """计算标准差"""
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    variance = sum((x - avg) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _simple_linear_regression(
    x_values: List[float], y_values: List[float]
) -> Tuple[float, float]:
    """
    简单线性回归：y = slope * x + intercept
    返回 (slope, intercept)
    """
    n = len(x_values)
    if n < 2 or n != len(y_values):
        return (0.0, _mean(y_values) if y_values else 0.0)

    x_mean = _mean(x_values)
    y_mean = _mean(y_values)

    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
    denominator = sum((x - x_mean) ** 2 for x in x_values)

    if abs(denominator) < 1e-10:
        return (0.0, y_mean)

    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    return (slope, intercept)


class SeafoodLossPredictor:
    """
    海鲜损耗预测 AI 模型

    使用简单线性回归 + 季节系数 + 温度修正，纯 Python 实现。
    所有金额同时返回 fen（分）和 yuan（元）。
    """

    def __init__(self) -> None:
        self._logger = logger.bind(service="seafood_loss_predictor")

    # ── 核心预测方法 ────────────────────────────────────────────────────────

    def predict_daily_loss(
        self,
        species: str,
        current_stock: int,
        season: str,
        tank_temp: float,
        days_in_tank: int,
        historical_mortality_rates: List[float],
        unit_price_fen: int = 0,
    ) -> LossPrediction:
        """
        预测明日死亡数量 + 损耗¥金额

        Args:
            species: 品种名称
            current_stock: 当前存活数量
            season: 季节（spring/summer/autumn/winter）或月份数字字符串
            tank_temp: 鱼缸当前水温（°C）
            days_in_tank: 已在缸天数
            historical_mortality_rates: 历史每日死亡率列表（最近N天）
            unit_price_fen: 单位价格（分/条或分/斤）
        """
        if current_stock <= 0:
            return LossPrediction(
                species=species, current_stock=0, predicted_deaths=0,
                mortality_rate=0.0, loss_amount_fen=0, loss_amount_yuan=0.0,
                confidence=1.0, risk_level="低",
                factors={"base": 0, "season": 0, "temp": 0, "days": 0},
            )

        # 1. 基础死亡率
        base_rate = SPECIES_BASE_MORTALITY.get(species, 0.008)

        # 2. 季节系数
        season_coeff = self._get_season_coefficient(season)

        # 3. 温度修正因子
        temp_factor = self._compute_temp_factor(species, tank_temp)

        # 4. 存放天数衰减
        days_factor = 1.0 + DAYS_DECAY_FACTOR * max(0, days_in_tank - 1)

        # 5. 历史趋势修正（线性回归预测下一天的死亡率）
        trend_adjustment = 0.0
        if len(historical_mortality_rates) >= 3:
            x_vals = list(range(len(historical_mortality_rates)))
            slope, intercept = _simple_linear_regression(
                [float(x) for x in x_vals], historical_mortality_rates
            )
            # 预测下一天
            predicted_rate = slope * len(historical_mortality_rates) + intercept
            trend_adjustment = max(0, predicted_rate - base_rate)

        # 综合死亡率
        predicted_rate = base_rate * season_coeff * temp_factor * days_factor + trend_adjustment
        # 限制在合理范围内
        predicted_rate = max(0.0, min(predicted_rate, 0.5))

        # 预测死亡数
        predicted_deaths = max(0, round(current_stock * predicted_rate))

        # 损耗金额
        loss_fen = predicted_deaths * unit_price_fen
        loss_yuan = round(loss_fen / 100, 2)

        # 置信度（基于历史数据量）
        data_points = len(historical_mortality_rates)
        confidence = min(0.95, 0.5 + data_points * 0.05)

        # 风险等级
        risk_level = self._classify_risk(predicted_rate)

        self._logger.info(
            "损耗预测完成",
            species=species,
            predicted_deaths=predicted_deaths,
            rate=round(predicted_rate, 4),
            risk=risk_level,
        )

        return LossPrediction(
            species=species,
            current_stock=current_stock,
            predicted_deaths=predicted_deaths,
            mortality_rate=round(predicted_rate, 6),
            loss_amount_fen=loss_fen,
            loss_amount_yuan=loss_yuan,
            confidence=round(confidence, 2),
            risk_level=risk_level,
            factors={
                "base_rate": round(base_rate, 4),
                "season_coeff": round(season_coeff, 2),
                "temp_factor": round(temp_factor, 2),
                "days_factor": round(days_factor, 2),
                "trend_adjustment": round(trend_adjustment, 4),
            },
        )

    def optimize_purchase_quantity(
        self,
        species: str,
        daily_demand: int,
        current_stock: int,
        predicted_loss: int,
        lead_days: int,
        unit_price_fen: int = 0,
        safety_factor: float = 1.2,
    ) -> PurchaseRecommendation:
        """
        最优采购量建议

        Args:
            species: 品种
            daily_demand: 日均需求量
            current_stock: 当前库存
            predicted_loss: 预测每日损耗
            lead_days: 供应商交付天数
            unit_price_fen: 单价（分）
            safety_factor: 安全系数（默认1.2，即20%安全余量）
        """
        # 交付期内的预计需求
        expected_demand = daily_demand * lead_days
        # 交付期内的预计损耗
        expected_loss = predicted_loss * lead_days
        # 安全库存 = 1天需求量 * 安全系数
        safety_stock = max(1, round(daily_demand * safety_factor))

        # 最优采购量 = 交付期需求 + 交付期损耗 + 安全库存 - 当前库存
        raw_qty = expected_demand + expected_loss + safety_stock - current_stock
        recommended_qty = max(0, raw_qty)

        cost_fen = recommended_qty * unit_price_fen
        cost_yuan = round(cost_fen / 100, 2)

        # 生成建议说明
        if recommended_qty == 0:
            reasoning = f"当前库存 {current_stock} 足够覆盖 {lead_days} 天需求，暂不需要采购"
        elif current_stock < safety_stock:
            reasoning = (
                f"当前库存 {current_stock} 低于安全库存 {safety_stock}，"
                f"建议立即采购 {recommended_qty} 单位，"
                f"预计采购成本 ¥{cost_yuan}"
            )
        else:
            reasoning = (
                f"考虑 {lead_days} 天交付期，预计需求 {expected_demand}，"
                f"预计损耗 {expected_loss}，建议采购 {recommended_qty} 单位，"
                f"预计采购成本 ¥{cost_yuan}"
            )

        self._logger.info(
            "采购量优化建议",
            species=species,
            recommended_qty=recommended_qty,
            cost_yuan=cost_yuan,
        )

        return PurchaseRecommendation(
            species=species,
            recommended_qty=recommended_qty,
            safety_stock=safety_stock,
            expected_loss_during_lead=expected_loss,
            expected_demand_during_lead=expected_demand,
            reasoning=reasoning,
            cost_estimate_fen=cost_fen,
            cost_estimate_yuan=cost_yuan,
        )

    def get_high_risk_species(
        self, tank_data_list: List[Dict[str, Any]]
    ) -> List[SpeciesRisk]:
        """
        高损耗风险品种排名

        Args:
            tank_data_list: 鱼缸数据列表，每项包含：
                - species: 品种
                - current_stock: 当前数量
                - tank_temp: 水温
                - days_in_tank: 在缸天数
                - unit_price_fen: 单价（分）
                - historical_mortality_rates: 历史死亡率（可选）
        """
        risks: List[SpeciesRisk] = []

        for data in tank_data_list:
            species = data.get("species", "未知")
            stock = data.get("current_stock", 0)
            temp = data.get("tank_temp", 18.0)
            days = data.get("days_in_tank", 1)
            price = data.get("unit_price_fen", 0)
            hist_rates = data.get("historical_mortality_rates", [])

            if stock <= 0:
                continue

            # 用预测方法计算风险
            prediction = self.predict_daily_loss(
                species=species,
                current_stock=stock,
                season=str(datetime.now().month),
                tank_temp=temp,
                days_in_tank=days,
                historical_mortality_rates=hist_rates,
                unit_price_fen=price,
            )

            # 风险分数 = 死亡率 * 100 * 价值权重
            value_weight = 1.0 + (price * stock) / 100000  # 价值越高权重越大
            risk_score = min(100, prediction.mortality_rate * 100 * value_weight * 10)

            # 主要风险因素
            factors = prediction.factors
            primary_factor = max(
                [
                    ("温度偏离", factors.get("temp_factor", 1.0) - 1.0),
                    ("存放过久", factors.get("days_factor", 1.0) - 1.0),
                    ("季节影响", factors.get("season_coeff", 1.0) - 1.0),
                    ("趋势恶化", factors.get("trend_adjustment", 0.0)),
                ],
                key=lambda x: abs(x[1]),
            )

            risks.append(SpeciesRisk(
                species=species,
                risk_score=round(risk_score, 1),
                risk_level=prediction.risk_level,
                predicted_daily_loss=prediction.predicted_deaths,
                loss_value_fen=prediction.loss_amount_fen,
                loss_value_yuan=prediction.loss_amount_yuan,
                primary_risk_factor=primary_factor[0],
            ))

        # 按风险分数降序排列
        risks.sort(key=lambda r: r.risk_score, reverse=True)

        self._logger.info("高风险品种排名完成", count=len(risks))
        return risks

    def generate_loss_report(
        self,
        records: List[Dict[str, Any]],
        period_days: int,
    ) -> LossReport:
        """
        损耗趋势报告

        Args:
            records: 损耗记录列表，每项包含：
                - species: 品种
                - date: 日期字符串 YYYY-MM-DD
                - deaths: 死亡数量
                - loss_fen: 损耗金额（分）
                - reason: 死亡原因（可选）
                - tank_id: 鱼缸ID（可选）
            period_days: 报告期天数
        """
        if not records:
            today = date.today()
            return LossReport(
                period_days=period_days,
                start_date=(today - timedelta(days=period_days)).isoformat(),
                end_date=today.isoformat(),
                total_loss_fen=0,
                total_loss_yuan=0.0,
                total_deaths=0,
                by_species=[],
                worst_species="无",
                improvement_suggestions=["暂无损耗数据，建议开始记录"],
            )

        # 按品种聚合
        species_data: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            sp = rec.get("species", "未知")
            if sp not in species_data:
                species_data[sp] = {
                    "deaths": [],
                    "loss_fen": [],
                    "reasons": {},
                    "daily": {},
                }
            species_data[sp]["deaths"].append(rec.get("deaths", 0))
            species_data[sp]["loss_fen"].append(rec.get("loss_fen", 0))
            reason = rec.get("reason", "未知")
            species_data[sp]["reasons"][reason] = (
                species_data[sp]["reasons"].get(reason, 0) + rec.get("deaths", 0)
            )
            d = rec.get("date", "")
            species_data[sp]["daily"][d] = (
                species_data[sp]["daily"].get(d, 0) + rec.get("deaths", 0)
            )

        # 汇总
        total_deaths = sum(r.get("deaths", 0) for r in records)
        total_loss_fen = sum(r.get("loss_fen", 0) for r in records)

        # 按品种生成报告项
        by_species: List[LossReportItem] = []
        for sp, data in species_data.items():
            sp_deaths = sum(data["deaths"])
            sp_loss_fen = sum(data["loss_fen"])
            avg_daily = sp_deaths / max(1, period_days)

            # 趋势分析（前半段 vs 后半段）
            daily_vals = sorted(data["daily"].items())
            if len(daily_vals) >= 4:
                mid = len(daily_vals) // 2
                first_half_avg = _mean([v for _, v in daily_vals[:mid]])
                second_half_avg = _mean([v for _, v in daily_vals[mid:]])
                if first_half_avg > 0:
                    change_pct = (second_half_avg - first_half_avg) / first_half_avg * 100
                else:
                    change_pct = 0.0
                if change_pct > 10:
                    trend = "上升"
                elif change_pct < -10:
                    trend = "下降"
                else:
                    trend = "平稳"
            else:
                trend = "数据不足"
                change_pct = 0.0

            # 最主要原因
            top_reason = max(data["reasons"], key=data["reasons"].get) if data["reasons"] else "未知"

            by_species.append(LossReportItem(
                species=sp,
                total_deaths=sp_deaths,
                total_loss_fen=sp_loss_fen,
                total_loss_yuan=round(sp_loss_fen / 100, 2),
                avg_daily_loss=round(avg_daily, 2),
                trend=trend,
                trend_pct=round(change_pct, 1),
                top_reason=top_reason,
            ))

        # 按损耗金额降序
        by_species.sort(key=lambda x: x.total_loss_fen, reverse=True)
        worst = by_species[0].species if by_species else "无"

        # 改进建议
        suggestions = self._generate_suggestions(by_species)

        today = date.today()
        report = LossReport(
            period_days=period_days,
            start_date=(today - timedelta(days=period_days)).isoformat(),
            end_date=today.isoformat(),
            total_loss_fen=total_loss_fen,
            total_loss_yuan=round(total_loss_fen / 100, 2),
            total_deaths=total_deaths,
            by_species=by_species,
            worst_species=worst,
            improvement_suggestions=suggestions,
        )

        self._logger.info(
            "损耗报告生成",
            period_days=period_days,
            total_deaths=total_deaths,
            total_loss_yuan=report.total_loss_yuan,
        )
        return report

    # ── 内部辅助方法 ─────────────────────────────────────────────────────────

    def _get_season_coefficient(self, season: str) -> float:
        """获取季节系数"""
        # 支持月份数字或季节名
        season_map = {
            "spring": 5, "summer": 7, "autumn": 10, "winter": 1,
            "春": 4, "夏": 7, "秋": 10, "冬": 1,
        }
        try:
            month = int(season)
        except ValueError:
            month = season_map.get(season.lower(), 6)

        return SEASON_COEFFICIENTS.get(month, 1.0)

    def _compute_temp_factor(self, species: str, tank_temp: float) -> float:
        """
        计算温度修正因子

        水温在最适范围内→1.0；偏离越多因子越大
        """
        optimal = SPECIES_OPTIMAL_TEMP.get(species, (15.0, 22.0))
        min_temp, max_temp = optimal

        if min_temp <= tank_temp <= max_temp:
            return 1.0

        # 偏离度，每偏离1°C，死亡率增加 15%
        if tank_temp < min_temp:
            deviation = min_temp - tank_temp
        else:
            deviation = tank_temp - max_temp

        return 1.0 + 0.15 * deviation

    def _classify_risk(self, mortality_rate: float) -> str:
        """根据死亡率分类风险等级"""
        if mortality_rate < 0.01:
            return "低"
        elif mortality_rate < 0.03:
            return "中"
        elif mortality_rate < 0.08:
            return "高"
        else:
            return "极高"

    def _generate_suggestions(self, by_species: List[LossReportItem]) -> List[str]:
        """根据报告数据生成改进建议"""
        suggestions = []

        for item in by_species[:3]:  # 只看损耗最大的前3个品种
            if item.trend == "上升":
                suggestions.append(
                    f"【{item.species}】损耗呈上升趋势（+{item.trend_pct}%），"
                    f"建议：检查水质参数、减少单次进货量"
                )
            if item.top_reason == "水质异常":
                suggestions.append(
                    f"【{item.species}】主要死因为水质异常，建议加密水质检测频率"
                )
            if item.top_reason == "存放过久":
                suggestions.append(
                    f"【{item.species}】主要死因为存放过久，建议缩短库存周转天数"
                )
            if item.avg_daily_loss > 5:
                suggestions.append(
                    f"【{item.species}】日均损耗 {item.avg_daily_loss} 条，"
                    f"日损耗 ¥{item.total_loss_yuan / max(1, item.total_deaths) * item.avg_daily_loss:.2f}，"
                    f"建议调整采购频次为少量多次"
                )

        if not suggestions:
            suggestions.append("整体损耗控制良好，建议继续保持现有管理水平")

        return suggestions
