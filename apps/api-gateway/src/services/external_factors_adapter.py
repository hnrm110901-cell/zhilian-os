"""
ExternalFactorsAdapter — 统一外部因子适配器

职责：
  将天气、节假日、吉日（好日子）、商圈事件四类外部因子聚合为单一复合系数，
  供 EnhancedForecastService、DailyHubService、FastPlanningService 等所有
  预测服务统一调用。

设计原则：
  - 单一数据源：所有外部因子只走这一个 adapter，不再各自分散调用
  - 可插拔策略：MULTIPLY / MAX / SMART 三种组合策略
  - 非致命降级：子系统调用失败时自动降级（factor=1.0），不影响主流程
  - 可追溯：返回 factors_breakdown，让 frontend/日志可以看到每个因子贡献

组合策略说明：
  MULTIPLY : 所有因子连乘（传统做法；可能高估极端情况）
  MAX      : 取单个最大因子（保守；但忽略多因子叠加效应）
  SMART    : 天气因子单独相乘（减少客流的物理因素）；
             需求侧取 max(holiday_factor, auspicious_factor, event_factor)
             → 最终 = weather_factor × max_demand_factor
             这是推荐默认策略，避免多个"需求提振"因子重复叠加

使用示例：
    adapter = ExternalFactorsAdapter()
    result  = await adapter.get_factors(
        target_date=date(2026, 5, 20),  # 我爱你
        store_config={"custom_auspicious": [...]},
        strategy="smart",
    )
    result.composite_factor      # → ~2.0
    result.factors_breakdown      # {"auspicious": 2.2, "weather": 0.85, ...}
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

import structlog

from src.services.forecast_features import ChineseHolidays, WeatherImpact, BusinessDistrictEvents
from src.services.auspicious_date_service import AuspiciousDateService
from src.services.weather_adapter import weather_adapter

logger = structlog.get_logger()

# 组合策略枚举字符串常量
STRATEGY_MULTIPLY = "multiply"
STRATEGY_MAX      = "max"
STRATEGY_SMART    = "smart"   # 推荐默认值


@dataclass
class ExternalFactorsResult:
    """统一外部因子计算结果。"""

    # ── 各子系统原始结果 ──────────────────────────────────────────────────────
    weather:    Optional[Dict[str, Any]] = None   # {temperature, condition, impact_factor}
    holiday:    Optional[Dict[str, Any]] = None   # {name, impact_factor}
    auspicious: Optional[Dict[str, Any]] = None   # {label, demand_factor, sources}
    event:      Optional[Dict[str, Any]] = None   # {type, impact_factor}

    # ── 组合结果 ─────────────────────────────────────────────────────────────
    composite_factor:     float             = 1.0   # 最终乘以 base_sales 的系数
    composition_strategy: str              = STRATEGY_SMART
    factors_breakdown:    Dict[str, float] = field(default_factory=dict)
    # e.g. {"weather": 0.85, "holiday": 1.6, "auspicious": 2.2}

    # ── 元数据 ────────────────────────────────────────────────────────────────
    target_date: str = ""
    warnings:    List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_date":         self.target_date,
            "weather":             self.weather,
            "holiday":             self.holiday,
            "auspicious":          self.auspicious,
            "event":               self.event,
            "composite_factor":    round(self.composite_factor, 3),
            "composition_strategy": self.composition_strategy,
            "factors_breakdown":   {k: round(v, 3) for k, v in self.factors_breakdown.items()},
            "warnings":            self.warnings,
        }


class ExternalFactorsAdapter:
    """
    统一外部因子适配器（无状态，可直接实例化）。

    Usage:
        adapter = ExternalFactorsAdapter()
        result  = await adapter.get_factors(date(2026, 5, 20))
        factor  = result.composite_factor   # 供预测服务乘以 base_sales
        summary = result.to_dict()          # 供前端展示
    """

    def __init__(
        self,
        store_config: Optional[Dict[str, Any]] = None,
        restaurant_type: str = "正餐",
    ):
        """
        Args:
            store_config:    门店配置（传入 AuspiciousDateService 用于自定义吉日）
            restaurant_type: 餐厅类型（影响天气温度因子；火锅 vs 正餐）
        """
        self._store_config    = store_config or {}
        self._restaurant_type = restaurant_type
        self._auspicious_svc  = AuspiciousDateService(store_config=store_config)

    # ── Public API ─────────────────────────────────────────────────────────────

    async def get_factors(
        self,
        target_date:  date,
        strategy:     str                            = STRATEGY_SMART,
        events:       Optional[List[Dict[str, Any]]] = None,
    ) -> ExternalFactorsResult:
        """
        获取指定日期的完整外部因子集合。

        Args:
            target_date: 目标日期
            strategy:    组合策略（"smart" | "multiply" | "max"）
            events:      可选商圈事件列表（由调用方传入；未来可接入商圈事件 API）

        Returns:
            ExternalFactorsResult（包含 composite_factor 和 factors_breakdown）
        """
        result = ExternalFactorsResult(
            target_date=target_date.isoformat(),
            composition_strategy=strategy,
        )
        breakdown: Dict[str, float] = {}

        # 1. 天气因子
        weather_factor = await self._fetch_weather_factor(target_date, result)
        if weather_factor != 1.0:
            breakdown["weather"] = weather_factor

        # 2. 节假日因子
        holiday_factor = self._fetch_holiday_factor(target_date, result)
        if holiday_factor != 1.0:
            breakdown["holiday"] = holiday_factor

        # 3. 吉日因子（好日子）
        auspicious_factor = self._fetch_auspicious_factor(target_date, result)
        if auspicious_factor != 1.0:
            breakdown["auspicious"] = auspicious_factor

        # 4. 商圈事件因子
        event_factor = self._fetch_event_factor(events, result)
        if event_factor != 1.0:
            breakdown["event"] = event_factor

        result.factors_breakdown = breakdown

        # 5. 组合计算
        result.composite_factor = self._compose(
            strategy=strategy,
            weather_factor=weather_factor,
            holiday_factor=holiday_factor,
            auspicious_factor=auspicious_factor,
            event_factor=event_factor,
        )

        logger.debug(
            "外部因子计算完成",
            target_date=target_date.isoformat(),
            composite=round(result.composite_factor, 3),
            strategy=strategy,
            breakdown=breakdown,
        )
        return result

    # ── Private: factor fetchers ───────────────────────────────────────────────

    async def _fetch_weather_factor(
        self,
        target_date: date,
        result:      ExternalFactorsResult,
    ) -> float:
        """获取天气影响因子（非致命）。"""
        try:
            weather = await weather_adapter.get_tomorrow_weather()
            if not weather:
                return 1.0

            temperature = weather.get("temperature")
            weather_type = weather.get("weather")

            # 温度影响
            temp_factor = 1.0
            if temperature is not None:
                temp_factor = WeatherImpact.get_temperature_impact(
                    temperature, self._restaurant_type
                )

            # 天气类型影响
            weather_type_factor = 1.0
            if weather_type:
                weather_type_factor = WeatherImpact.get_weather_impact(weather_type)

            combined = round(temp_factor * weather_type_factor, 3)
            result.weather = {
                "temperature":    temperature,
                "condition":      weather_type,
                "impact_factor":  combined,
                "temp_factor":    round(temp_factor, 3),
                "type_factor":    round(weather_type_factor, 3),
            }
            return combined

        except Exception as e:
            result.warnings.append(f"天气因子获取失败（降级=1.0）: {e}")
            logger.warning("天气因子获取失败（非致命）", error=str(e))
            return 1.0

    def _fetch_holiday_factor(
        self,
        target_date: date,
        result:      ExternalFactorsResult,
    ) -> float:
        """获取节假日影响因子（纯内存，不会失败）。"""
        factor = ChineseHolidays.get_holiday_impact_score(target_date)
        holiday_info = ChineseHolidays.get_holiday_info(target_date)
        if holiday_info:
            result.holiday = {
                "name":          holiday_info.get("name", ""),
                "type":          holiday_info.get("type", ""),
                "impact_factor": round(factor, 3),
            }
        return factor

    def _fetch_auspicious_factor(
        self,
        target_date: date,
        result:      ExternalFactorsResult,
    ) -> float:
        """获取吉日需求因子（好日子；纯内存，不会失败）。"""
        try:
            info = self._auspicious_svc.get_info(target_date)
            if info.is_auspicious:
                result.auspicious = {
                    "label":         info.label,
                    "demand_factor": info.demand_factor,
                    "sources":       info.sources,
                }
                return info.demand_factor
        except Exception as e:
            result.warnings.append(f"吉日因子获取失败: {e}")
        return 1.0

    def _fetch_event_factor(
        self,
        events: Optional[List[Dict[str, Any]]],
        result: ExternalFactorsResult,
    ) -> float:
        """获取商圈事件影响因子。"""
        if not events:
            return 1.0
        factor = 1.0
        for evt in events:
            event_type = evt.get("type")
            if event_type:
                factor *= BusinessDistrictEvents.get_event_impact(event_type)
        if factor != 1.0:
            result.event = {
                "events":        [e.get("type", "") for e in events],
                "impact_factor": round(factor, 3),
            }
        return round(factor, 3)

    # ── Private: composition strategies ───────────────────────────────────────

    @staticmethod
    def _compose(
        strategy:          str,
        weather_factor:    float,
        holiday_factor:    float,
        auspicious_factor: float,
        event_factor:      float,
    ) -> float:
        """
        按策略组合四类因子为单一复合系数。

        MULTIPLY: weather × holiday × auspicious × event
          → 精准但可能高估（2.2 × 1.8 × 0.85 = 3.37 极端情况）

        MAX: max(weather, holiday, auspicious, event)
          → 保守，忽略叠加效应

        SMART（推荐）:
          - 天气是物理减损，单独保留（连乘）
          - 需求侧取 max(holiday, auspicious, event) 防止重复叠加
          - composite = weather_factor × max_demand_factor
          → 既保留天气减损，又避免节日 + 吉日双重叠加虚高
        """
        if strategy == STRATEGY_MULTIPLY:
            result = weather_factor * holiday_factor * auspicious_factor * event_factor

        elif strategy == STRATEGY_MAX:
            result = max(weather_factor, holiday_factor, auspicious_factor, event_factor)

        else:  # STRATEGY_SMART（默认）
            demand_factors = [holiday_factor, auspicious_factor, event_factor]
            max_demand     = max(demand_factors) if demand_factors else 1.0
            result         = weather_factor * max_demand

        return round(result, 3)


# ── 全局单例（无门店配置；门店专属实例请传入 store_config） ──────────────────
external_factors_adapter = ExternalFactorsAdapter()
