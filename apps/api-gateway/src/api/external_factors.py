"""
ExternalFactors REST API

端点：
  GET /api/v1/external-factors/{target_date}    — 单日完整外部因子（天气/节假日/吉日/商圈事件）
  GET /api/v1/external-factors/calendar         — 30 天因子日历（供前端备战板/销控页面使用）
  GET /api/v1/external-factors/high-impact      — 未来 N 天高影响日（factor ≥ 阈值，供旺季规划）

设计：
  - 统一入口：全部通过 ExternalFactorsAdapter，一致的数据来源
  - 三种组合策略：smart（默认）/ multiply / max
  - composite_factor 是供各预测服务直接使用的最终乘数
  - 无 DB 依赖（纯内存 + 天气 API），响应极快
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.core.dependencies import get_current_user
from src.models.user import User
from src.services.external_factors_adapter import (
    ExternalFactorsAdapter,
    STRATEGY_SMART,
    STRATEGY_MULTIPLY,
    STRATEGY_MAX,
)
from src.services.auspicious_date_service import AuspiciousDateService

router = APIRouter(prefix="/api/v1/external-factors", tags=["external_factors"])

_VALID_STRATEGIES = {STRATEGY_SMART, STRATEGY_MULTIPLY, STRATEGY_MAX}


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class WeatherFactor(BaseModel):
    temperature:   Optional[float] = None
    condition:     Optional[str]   = None
    impact_factor: Optional[float] = None
    temp_factor:   Optional[float] = None
    type_factor:   Optional[float] = None


class HolidayFactor(BaseModel):
    name:          str
    type:          Optional[str]  = None
    impact_factor: float


class AuspiciousFactor(BaseModel):
    label:         str
    demand_factor: float
    sources:       List[str] = []


class EventFactor(BaseModel):
    events:        List[str]
    impact_factor: float


class ExternalFactorsResponse(BaseModel):
    target_date:          str
    weather:              Optional[WeatherFactor]    = None
    holiday:              Optional[HolidayFactor]    = None
    auspicious:           Optional[AuspiciousFactor] = None
    event:                Optional[EventFactor]      = None
    composite_factor:     float
    composition_strategy: str
    factors_breakdown:    Dict[str, float]
    warnings:             List[str] = []


class CalendarDay(BaseModel):
    date:             str
    composite_factor: float
    is_high_impact:   bool           # factor >= 1.5
    auspicious_label: Optional[str]  = None
    holiday_name:     Optional[str]  = None
    breakdown:        Dict[str, float]


class CalendarResponse(BaseModel):
    start_date:       str
    days:             int
    strategy:         str
    calendar:         List[CalendarDay]
    high_impact_count: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/calendar",
    summary="获取外部因子日历（30 天）",
    response_model=CalendarResponse,
)
async def get_factors_calendar(
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD，默认今天"),
    days:       int           = Query(30,   ge=1, le=365, description="日历长度（默认 30 天）"),
    strategy:   str           = Query(STRATEGY_SMART, description="组合策略：smart/multiply/max"),
    _: User = Depends(get_current_user),
):
    """
    获取外部因子日历，供：
    - 备战板生成前的影响因子预览
    - 宴会销控页面标注高影响日期
    - 运营团队提前布局旺季资源

    `composite_factor > 1.5` 的日期标注为 `is_high_impact=true`。
    """
    _validate_strategy(strategy)
    sd = _parse_date(start_date) if start_date else date.today()

    adapter      = ExternalFactorsAdapter()
    auspicious   = AuspiciousDateService()
    calendar     = []
    high_count   = 0

    for i in range(days):
        d      = sd + timedelta(days=i)
        result = await adapter.get_factors(d, strategy=strategy)

        ausp_label  = result.auspicious.get("label")  if result.auspicious else None
        holiday_name = result.holiday.get("name")     if result.holiday    else None
        is_high     = result.composite_factor >= 1.5

        if is_high:
            high_count += 1

        calendar.append(CalendarDay(
            date=d.isoformat(),
            composite_factor=result.composite_factor,
            is_high_impact=is_high,
            auspicious_label=ausp_label,
            holiday_name=holiday_name,
            breakdown=result.factors_breakdown,
        ))

    return CalendarResponse(
        start_date=sd.isoformat(),
        days=days,
        strategy=strategy,
        calendar=calendar,
        high_impact_count=high_count,
    )


@router.get(
    "/high-impact",
    summary="获取高影响日列表（factor ≥ 阈值，供旺季规划）",
)
async def get_high_impact_days(
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD，默认今天"),
    days:       int           = Query(90,  ge=1, le=365, description="前瞻天数（默认 90 天）"),
    threshold:  float         = Query(1.5, ge=1.0, le=3.0, description="因子阈值（默认 1.5）"),
    strategy:   str           = Query(STRATEGY_SMART, description="组合策略"),
    _: User = Depends(get_current_user),
):
    """
    返回未来 N 天中 `composite_factor ≥ threshold` 的高影响日期。

    用途：
    - 旺季提前备货计划（factor ≥ 1.8 提前 2 周下大单）
    - 宴会销售团队重点攻坚（好日子预约转化率高）
    - 员工排班提前锁定（好日子不允许请假）
    """
    _validate_strategy(strategy)
    sd      = _parse_date(start_date) if start_date else date.today()
    adapter = ExternalFactorsAdapter()

    results = []
    for i in range(days):
        d      = sd + timedelta(days=i)
        result = await adapter.get_factors(d, strategy=strategy)
        if result.composite_factor >= threshold:
            results.append({
                "date":             d.isoformat(),
                "composite_factor": result.composite_factor,
                "auspicious":       result.auspicious,
                "holiday":          result.holiday,
                "weather":          result.weather,
                "breakdown":        result.factors_breakdown,
            })

    return {
        "start_date":   sd.isoformat(),
        "days":         days,
        "threshold":    threshold,
        "strategy":     strategy,
        "total_found":  len(results),
        "high_impact_days": results,
    }


@router.get(
    "/{target_date}",
    summary="获取单日完整外部因子",
    response_model=ExternalFactorsResponse,
)
async def get_date_factors(
    target_date: str,
    strategy:    str = Query(STRATEGY_SMART, description="组合策略：smart/multiply/max"),
    _: User = Depends(get_current_user),
):
    """
    获取指定日期的完整外部因子集合：

    - **weather**: 天气影响（温度因子 × 天气类型因子）
    - **holiday**: 法定节假日/营销节日影响
    - **auspicious**: 好日子感知（谐音吉日/七夕/黄金周）
    - **event**: 商圈活动（本端点不传 events，返回 null；可通过查询参数扩展）
    - **composite_factor**: 最终综合系数（供预测模型直接使用）
    - **factors_breakdown**: 各因子明细（可追溯）

    组合策略：
    - `smart`（推荐）: weather × max(holiday, auspicious, event) — 防止需求因子重叠
    - `multiply`: 全部因子连乘 — 精准但极端情况可能高估
    - `max`: 取最大单因子 — 保守，忽略叠加效应
    """
    _validate_strategy(strategy)
    td      = _parse_date(target_date)
    adapter = ExternalFactorsAdapter()
    result  = await adapter.get_factors(td, strategy=strategy)
    return result.to_dict()


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"日期格式错误，应为 YYYY-MM-DD: {raw}",
        )


def _validate_strategy(strategy: str) -> None:
    if strategy not in _VALID_STRATEGIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"无效策略 '{strategy}'，可选：{sorted(_VALID_STRATEGIES)}",
        )
