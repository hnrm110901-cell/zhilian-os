"""
海鲜进货价波动预警服务（Price Fluctuation Service）

核心功能：
- 进货价记录
- 异常检测（均值 ±2σ）
- 趋势分析（涨/跌/平稳 + 幅度%）
- 价格预警通知
- 价格看板（各品种走势 + 异常标记）
- 采购时机建议

金额单位：分（fen），API 返回时 /100 转元
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


@dataclass
class PriceRecord:
    """价格记录"""
    species: str
    supplier_id: str
    price_fen: int
    price_yuan: float
    date: str  # YYYY-MM-DD
    recorded_at: str


@dataclass
class AnomalyResult:
    """异常检测结果"""
    species: str
    is_anomaly: bool
    latest_price_fen: int
    latest_price_yuan: float
    mean_price_fen: int
    mean_price_yuan: float
    std_dev_fen: float
    deviation_sigma: float  # 偏离几个标准差
    direction: str  # 偏高/偏低/正常
    severity: str  # 轻微/显著/严重


@dataclass
class TrendResult:
    """趋势分析结果"""
    species: str
    trend: str  # 上涨/下跌/平稳
    change_pct: float  # 变化幅度 %
    period_days: int
    start_price_fen: int
    start_price_yuan: float
    end_price_fen: int
    end_price_yuan: float
    avg_price_fen: int
    avg_price_yuan: float
    min_price_fen: int
    min_price_yuan: float
    max_price_fen: int
    max_price_yuan: float
    volatility: float  # 波动率 %


@dataclass
class PriceAlert:
    """价格预警"""
    alert_id: str
    species: str
    alert_type: str  # 异常偏高/异常偏低/持续上涨/持续下跌
    current_price_fen: int
    current_price_yuan: float
    reference_price_fen: int
    reference_price_yuan: float
    change_pct: float
    severity: str
    suggested_action: str
    impact_estimate_fen: int  # 按月影响金额（分）
    impact_estimate_yuan: float
    created_at: str


@dataclass
class SpeciesDashboard:
    """单品种看板数据"""
    species: str
    latest_price_fen: int
    latest_price_yuan: float
    trend: str
    change_pct: float
    is_anomaly: bool
    anomaly_direction: str
    price_history: List[Dict[str, Any]]  # [{date, price_fen, price_yuan}]
    supplier_comparison: List[Dict[str, Any]]  # [{supplier_id, avg_price_fen}]


@dataclass
class PurchaseTimingAdvice:
    """采购时机建议"""
    species: str
    recommendation: str  # 立即采购/等待观望/分批采购
    reasoning: str
    confidence: float
    suggested_action: str
    potential_saving_fen: int
    potential_saving_yuan: float


def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    variance = sum((x - avg) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _simple_linear_regression(
    x_vals: List[float], y_vals: List[float]
) -> Tuple[float, float]:
    """简单线性回归，返回 (slope, intercept)"""
    n = len(x_vals)
    if n < 2:
        return (0.0, _mean(y_vals) if y_vals else 0.0)

    x_mean = _mean(x_vals)
    y_mean = _mean(y_vals)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, y_vals))
    den = sum((x - x_mean) ** 2 for x in x_vals)
    if abs(den) < 1e-10:
        return (0.0, y_mean)
    slope = num / den
    intercept = y_mean - slope * x_mean
    return (slope, intercept)


class PriceFluctuationService:
    """
    海鲜进货价波动预警服务

    纯内存存储，所有金额同时提供 fen 和 yuan 两种单位。
    """

    def __init__(self) -> None:
        self._logger = logger.bind(service="price_fluctuation")
        # 价格历史：species → List[PriceRecord]
        self._price_history: Dict[str, List[PriceRecord]] = {}
        # 告警记录
        self._alerts: List[PriceAlert] = []
        self._alert_counter = 0

    def record_price(
        self,
        species: str,
        supplier_id: str,
        price_fen: int,
        record_date: Optional[str] = None,
    ) -> PriceRecord:
        """
        记录进货价

        Args:
            species: 品种
            supplier_id: 供应商ID
            price_fen: 价格（分/斤）
            record_date: 日期 YYYY-MM-DD（默认今天）
        """
        if price_fen <= 0:
            raise ValueError("价格必须大于0")

        if record_date is None:
            record_date = date.today().isoformat()

        record = PriceRecord(
            species=species,
            supplier_id=supplier_id,
            price_fen=price_fen,
            price_yuan=round(price_fen / 100, 2),
            date=record_date,
            recorded_at=datetime.now().isoformat(),
        )

        if species not in self._price_history:
            self._price_history[species] = []
        self._price_history[species].append(record)

        self._logger.info(
            "进货价记录",
            species=species,
            supplier=supplier_id,
            price_yuan=record.price_yuan,
        )
        return record

    def detect_anomaly(
        self,
        species: str,
        latest_price_fen: int,
        historical_prices: Optional[List[int]] = None,
        sigma_threshold: float = 2.0,
    ) -> AnomalyResult:
        """
        异常检测（超过均值 ±2σ 为异常）

        Args:
            species: 品种
            latest_price_fen: 最新价格（分）
            historical_prices: 历史价格列表（分），为空则从内部记录获取
            sigma_threshold: 标准差阈值（默认2.0）
        """
        if historical_prices is None:
            records = self._price_history.get(species, [])
            historical_prices = [r.price_fen for r in records]

        if len(historical_prices) < 3:
            # 数据不足，无法判断
            return AnomalyResult(
                species=species,
                is_anomaly=False,
                latest_price_fen=latest_price_fen,
                latest_price_yuan=round(latest_price_fen / 100, 2),
                mean_price_fen=latest_price_fen,
                mean_price_yuan=round(latest_price_fen / 100, 2),
                std_dev_fen=0.0,
                deviation_sigma=0.0,
                direction="正常",
                severity="无（数据不足）",
            )

        prices_float = [float(p) for p in historical_prices]
        avg = _mean(prices_float)
        std = _std(prices_float)

        if std < 1e-10:
            # 标准差为0，所有价格相同
            is_anomaly = abs(latest_price_fen - avg) > 0
            deviation = float("inf") if is_anomaly else 0.0
        else:
            deviation = (latest_price_fen - avg) / std
            is_anomaly = abs(deviation) > sigma_threshold

        # 方向
        if deviation > sigma_threshold:
            direction = "偏高"
        elif deviation < -sigma_threshold:
            direction = "偏低"
        else:
            direction = "正常"

        # 严重程度
        abs_dev = abs(deviation)
        if abs_dev <= sigma_threshold:
            severity = "正常"
        elif abs_dev <= 3.0:
            severity = "轻微"
        elif abs_dev <= 4.0:
            severity = "显著"
        else:
            severity = "严重"

        mean_fen = round(avg)
        result = AnomalyResult(
            species=species,
            is_anomaly=is_anomaly,
            latest_price_fen=latest_price_fen,
            latest_price_yuan=round(latest_price_fen / 100, 2),
            mean_price_fen=mean_fen,
            mean_price_yuan=round(mean_fen / 100, 2),
            std_dev_fen=round(std, 1),
            deviation_sigma=round(deviation, 2),
            direction=direction,
            severity=severity,
        )

        self._logger.info(
            "异常检测完成",
            species=species,
            is_anomaly=is_anomaly,
            deviation_sigma=round(deviation, 2),
        )
        return result

    def calculate_trend(
        self,
        species: str,
        price_history: Optional[List[Dict[str, Any]]] = None,
        days: int = 30,
    ) -> TrendResult:
        """
        趋势分析

        Args:
            species: 品种
            price_history: 价格历史 [{date: str, price_fen: int}]，为空则从内部获取
            days: 分析天数
        """
        if price_history is None:
            records = self._price_history.get(species, [])
            price_history = [
                {"date": r.date, "price_fen": r.price_fen}
                for r in records
            ]

        if not price_history:
            return TrendResult(
                species=species, trend="数据不足", change_pct=0.0,
                period_days=days,
                start_price_fen=0, start_price_yuan=0.0,
                end_price_fen=0, end_price_yuan=0.0,
                avg_price_fen=0, avg_price_yuan=0.0,
                min_price_fen=0, min_price_yuan=0.0,
                max_price_fen=0, max_price_yuan=0.0,
                volatility=0.0,
            )

        # 按日期排序
        sorted_prices = sorted(price_history, key=lambda p: p.get("date", ""))
        prices = [p["price_fen"] for p in sorted_prices]

        start_price = prices[0]
        end_price = prices[-1]
        avg_price = round(_mean([float(p) for p in prices]))
        min_price = min(prices)
        max_price = max(prices)

        # 变化幅度
        if start_price > 0:
            change_pct = round((end_price - start_price) / start_price * 100, 1)
        else:
            change_pct = 0.0

        # 趋势判断：用线性回归斜率
        x_vals = list(range(len(prices)))
        slope, _ = _simple_linear_regression(
            [float(x) for x in x_vals], [float(p) for p in prices]
        )

        # 以平均价的 1% 为阈值
        threshold = avg_price * 0.01
        if slope > threshold:
            trend = "上涨"
        elif slope < -threshold:
            trend = "下跌"
        else:
            trend = "平稳"

        # 波动率 = 标准差 / 均值 * 100
        std = _std([float(p) for p in prices])
        volatility = round(std / max(1.0, float(avg_price)) * 100, 1)

        return TrendResult(
            species=species,
            trend=trend,
            change_pct=change_pct,
            period_days=days,
            start_price_fen=start_price,
            start_price_yuan=round(start_price / 100, 2),
            end_price_fen=end_price,
            end_price_yuan=round(end_price / 100, 2),
            avg_price_fen=avg_price,
            avg_price_yuan=round(avg_price / 100, 2),
            min_price_fen=min_price,
            min_price_yuan=round(min_price / 100, 2),
            max_price_fen=max_price,
            max_price_yuan=round(max_price / 100, 2),
            volatility=volatility,
        )

    def generate_alert(
        self,
        species: str,
        anomaly_result: AnomalyResult,
        monthly_volume: int = 100,
    ) -> Optional[PriceAlert]:
        """
        生成价格预警通知

        Args:
            species: 品种
            anomaly_result: 异常检测结果
            monthly_volume: 月采购量（斤），用于估算影响金额
        """
        if not anomaly_result.is_anomaly:
            return None

        self._alert_counter += 1
        alert_id = f"PA{self._alert_counter:06d}"

        # 告警类型
        if anomaly_result.direction == "偏高":
            alert_type = "异常偏高"
            action = (
                f"建议：① 与供应商确认涨价原因；"
                f"② 比价其他供应商；"
                f"③ 如非合理涨价，暂缓采购等待回落"
            )
        else:
            alert_type = "异常偏低"
            action = (
                f"建议：① 确认品质是否正常；"
                f"② 如品质无问题，可适当增加采购量锁价；"
                f"③ 警惕是否为低质替代品"
            )

        # 影响金额估算
        diff_fen = abs(anomaly_result.latest_price_fen - anomaly_result.mean_price_fen)
        impact_fen = diff_fen * monthly_volume
        impact_yuan = round(impact_fen / 100, 2)

        change_pct = 0.0
        if anomaly_result.mean_price_fen > 0:
            change_pct = round(
                (anomaly_result.latest_price_fen - anomaly_result.mean_price_fen)
                / anomaly_result.mean_price_fen * 100,
                1,
            )

        alert = PriceAlert(
            alert_id=alert_id,
            species=species,
            alert_type=alert_type,
            current_price_fen=anomaly_result.latest_price_fen,
            current_price_yuan=anomaly_result.latest_price_yuan,
            reference_price_fen=anomaly_result.mean_price_fen,
            reference_price_yuan=anomaly_result.mean_price_yuan,
            change_pct=change_pct,
            severity=anomaly_result.severity,
            suggested_action=action,
            impact_estimate_fen=impact_fen,
            impact_estimate_yuan=impact_yuan,
            created_at=datetime.now().isoformat(),
        )

        self._alerts.append(alert)

        self._logger.info(
            "价格预警生成",
            alert_id=alert_id,
            species=species,
            type=alert_type,
            impact_yuan=impact_yuan,
        )
        return alert

    def get_price_dashboard(
        self,
        species_list: List[str],
        days: int = 30,
    ) -> List[SpeciesDashboard]:
        """
        价格看板

        Args:
            species_list: 品种列表
            days: 展示天数
        """
        dashboards: List[SpeciesDashboard] = []

        for species in species_list:
            records = self._price_history.get(species, [])

            if not records:
                dashboards.append(SpeciesDashboard(
                    species=species,
                    latest_price_fen=0, latest_price_yuan=0.0,
                    trend="无数据", change_pct=0.0,
                    is_anomaly=False, anomaly_direction="正常",
                    price_history=[], supplier_comparison=[],
                ))
                continue

            # 最新价格
            latest = records[-1]

            # 趋势
            trend_result = self.calculate_trend(species, days=days)

            # 异常检测
            anomaly = self.detect_anomaly(species, latest.price_fen)

            # 价格历史
            history = [
                {
                    "date": r.date,
                    "price_fen": r.price_fen,
                    "price_yuan": r.price_yuan,
                    "supplier_id": r.supplier_id,
                }
                for r in records[-days:]
            ]

            # 供应商比价
            supplier_prices: Dict[str, List[int]] = {}
            for r in records:
                if r.supplier_id not in supplier_prices:
                    supplier_prices[r.supplier_id] = []
                supplier_prices[r.supplier_id].append(r.price_fen)

            comparison = [
                {
                    "supplier_id": sid,
                    "avg_price_fen": round(_mean([float(p) for p in prices])),
                    "avg_price_yuan": round(_mean([float(p) for p in prices]) / 100, 2),
                    "records_count": len(prices),
                }
                for sid, prices in supplier_prices.items()
            ]
            comparison.sort(key=lambda x: x["avg_price_fen"])

            dashboards.append(SpeciesDashboard(
                species=species,
                latest_price_fen=latest.price_fen,
                latest_price_yuan=latest.price_yuan,
                trend=trend_result.trend,
                change_pct=trend_result.change_pct,
                is_anomaly=anomaly.is_anomaly,
                anomaly_direction=anomaly.direction,
                price_history=history,
                supplier_comparison=comparison,
            ))

        self._logger.info("价格看板生成", species_count=len(dashboards))
        return dashboards

    def recommend_purchase_timing(
        self,
        species: str,
        trend: Optional[TrendResult] = None,
        days: int = 30,
    ) -> PurchaseTimingAdvice:
        """
        采购时机建议

        规则：
        - 下跌趋势 → 等待观望（价格可能继续降）
        - 上涨趋势 → 立即采购（锁定当前价格）
        - 平稳 → 正常采购节奏

        Args:
            species: 品种
            trend: 趋势分析结果（为空则自动计算）
            days: 分析天数
        """
        if trend is None:
            trend = self.calculate_trend(species, days=days)

        if trend.trend == "数据不足":
            return PurchaseTimingAdvice(
                species=species,
                recommendation="正常采购",
                reasoning="历史价格数据不足，无法给出时机建议，建议按正常节奏采购。",
                confidence=0.3,
                suggested_action="按日常采购计划执行",
                potential_saving_fen=0,
                potential_saving_yuan=0.0,
            )

        if trend.trend == "下跌":
            # 预估等待可节省的金额
            daily_drop_fen = abs(trend.end_price_fen - trend.start_price_fen) / max(1, trend.period_days)
            wait_days = 3
            saving_fen = round(daily_drop_fen * wait_days)
            saving_yuan = round(saving_fen / 100, 2)

            return PurchaseTimingAdvice(
                species=species,
                recommendation="等待观望",
                reasoning=(
                    f"{species}近{trend.period_days}天价格下跌 {abs(trend.change_pct)}%，"
                    f"从 ¥{trend.start_price_yuan} 降至 ¥{trend.end_price_yuan}。"
                    f"建议等待 {wait_days} 天再采购，预计每斤可再降 ¥{saving_yuan}。"
                ),
                confidence=min(0.85, 0.5 + abs(trend.change_pct) / 100),
                suggested_action=f"建议等待 {wait_days} 天后再采购，持续关注价格走势",
                potential_saving_fen=saving_fen,
                potential_saving_yuan=saving_yuan,
            )

        if trend.trend == "上涨":
            # 立即采购可避免的额外成本
            daily_rise_fen = abs(trend.end_price_fen - trend.start_price_fen) / max(1, trend.period_days)
            delay_cost_fen = round(daily_rise_fen * 3)  # 延迟3天的额外成本
            delay_cost_yuan = round(delay_cost_fen / 100, 2)

            return PurchaseTimingAdvice(
                species=species,
                recommendation="立即采购",
                reasoning=(
                    f"{species}近{trend.period_days}天价格上涨 {trend.change_pct}%，"
                    f"从 ¥{trend.start_price_yuan} 涨至 ¥{trend.end_price_yuan}。"
                    f"建议立即采购锁定价格，延迟3天每斤可能多花 ¥{delay_cost_yuan}。"
                ),
                confidence=min(0.85, 0.5 + abs(trend.change_pct) / 100),
                suggested_action="建议立即采购，可适当增加采购量以锁定当前价格",
                potential_saving_fen=delay_cost_fen,
                potential_saving_yuan=delay_cost_yuan,
            )

        # 平稳
        return PurchaseTimingAdvice(
            species=species,
            recommendation="正常采购",
            reasoning=(
                f"{species}近{trend.period_days}天价格平稳，"
                f"波动率 {trend.volatility}%，均价 ¥{trend.avg_price_yuan}。"
                f"按正常采购节奏即可。"
            ),
            confidence=0.7,
            suggested_action="按日常采购计划执行，无需特殊调整",
            potential_saving_fen=0,
            potential_saving_yuan=0.0,
        )
