"""
FCT REST API — 业财税资金一体化

端点：
  GET  /api/v1/fct/{store_id}/dashboard                    — FCT 综合仪表盘
  GET  /api/v1/fct/{store_id}/reconciliation/{year}/{month} — 月度业财对账
  GET  /api/v1/fct/{store_id}/tax/{year}/{month}           — 月度税务测算
  POST /api/v1/fct/{store_id}/tax/{year}/{month}/save      — 保存税务记录
  GET  /api/v1/fct/{store_id}/cash-flow                    — 资金流预测
  GET  /api/v1/fct/{store_id}/budget-execution/{year}/{month} — 预算执行率
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User
from src.services.fct_service import FCTService

router = APIRouter(
    prefix="/api/v1/fct",
    tags=["fct"],
)


# ── Pydantic Schemas ───────────────────────────────────────────────────────────

class TaxEstimateResponse(BaseModel):
    store_id:       str
    period:         str
    taxpayer_type:  str
    total_tax:      int
    effective_rate: float
    vat:            dict
    cit:            dict
    revenue:        dict
    disclaimer:     str


class CashFlowRequest(BaseModel):
    days:             int = Field(30, ge=7, le=90,  description="预测天数（7-90）")
    starting_balance: int = Field(0,  ge=0,         description="当前账面余额（分）")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/{store_id}/dashboard",
    summary="FCT 综合仪表盘",
)
async def get_fct_dashboard(
    store_id: str,
    db:   AsyncSession = Depends(get_db),
    _:    User         = Depends(get_current_user),
):
    """
    FCT 综合仪表盘（快照视图）：

    - `cash_flow`:  未来 7 天净流 + 余额 + 预警数
    - `tax`:        当月税务估算摘要
    - `budget`:     当月利润率 + 超预算科目数
    - `health_score`: FCT 综合健康分（0-100）

    适合管理驾驶舱首屏展示。
    """
    svc = FCTService(db)
    try:
        return await svc.get_dashboard(store_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{store_id}/reconciliation/{year}/{month}",
    summary="月度业财对账汇总",
)
async def get_monthly_reconciliation(
    store_id: str,
    year:     int,
    month:    int,
    db:   AsyncSession = Depends(get_db),
    _:    User         = Depends(get_current_user),
):
    """
    月度业财对账汇总报告：

    - `summary.pos_total`:      POS 系统月度总收入
    - `summary.finance_total`:  财务系统登记收入
    - `summary.variance`:       差异（分）= finance - pos
    - `summary.health`:         normal / warning / critical
    - `anomaly_days`:           差异率 > 1% 的高风险日期列表
    - `daily_details`:          逐日明细

    **对账健康判断**：`|variance_pct| ≤ 1%` = normal；≤ 3% = warning；> 3% = critical
    """
    if not (1 <= month <= 12):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"月份无效：{month}（应为 1-12）",
        )
    svc = FCTService(db)
    return await svc.get_monthly_reconciliation(store_id, year, month)


@router.get(
    "/{store_id}/tax/{year}/{month}",
    summary="月度税务测算",
)
async def estimate_tax(
    store_id:      str,
    year:          int,
    month:         int,
    taxpayer_type: str = Query("general", description="纳税人类型：general / small / micro"),
    db:   AsyncSession = Depends(get_db),
    _:    User         = Depends(get_current_user),
):
    """
    月度税务测算（基于历史数据估算，仅供参考）：

    - `vat.net_vat`:        应纳增值税（销项 - 进项）
    - `vat.surcharge`:      增值税附加（城建 7% + 教育附加 3% + 地方教育 2%）
    - `cit.cit_amount`:     企业所得税估算（收入 × 利润率假设 × CIT 税率）
    - `total_tax`:          三项合计
    - `effective_rate`:     综合税负率（%）

    纳税人类型影响税率：
      - `general`（一般纳税人）：VAT 6%，CIT 25%
      - `small`（小规模）：VAT 3%，CIT 25%
      - `micro`（微型企业）：VAT 3%，CIT 20%
    """
    if not (1 <= month <= 12):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"月份无效：{month}",
        )
    valid_types = ("general", "small", "micro")
    if taxpayer_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"纳税人类型无效：{taxpayer_type}，有效值：{valid_types}",
        )

    svc = FCTService(db)
    return await svc.estimate_monthly_tax(store_id, year, month,
                                           taxpayer_type=taxpayer_type, save=False)


@router.post(
    "/{store_id}/tax/{year}/{month}/save",
    summary="保存月度税务测算记录",
    status_code=status.HTTP_201_CREATED,
)
async def save_tax_record(
    store_id:      str,
    year:          int,
    month:         int,
    taxpayer_type: str = Query("general", description="纳税人类型"),
    db:   AsyncSession = Depends(get_db),
    _:    User         = Depends(get_current_user),
):
    """
    执行月度税务测算并将结果持久化到 `fct_tax_records` 表。

    通常在月末由财务人员手动确认后触发，或由 Celery 月度定时任务自动调用。
    """
    svc    = FCTService(db)
    result = await svc.estimate_monthly_tax(
        store_id, year, month, taxpayer_type=taxpayer_type, save=True,
    )
    await db.commit()
    return {
        "message":       f"{year}-{month:02d} 税务测算已保存",
        "total_tax":     result["total_tax"],
        "effective_rate": result["effective_rate"],
    }


@router.get(
    "/{store_id}/cash-flow",
    summary="资金流预测",
)
async def forecast_cash_flow(
    store_id:         str,
    days:             int = Query(30, ge=7, le=90,  description="预测天数（7-90）"),
    starting_balance: int = Query(0,  ge=0,          description="当前账面余额（分）"),
    db:   AsyncSession = Depends(get_db),
    _:    User         = Depends(get_current_user),
):
    """
    未来 N 天资金流预测：

    - `daily_forecast[].inflow`:             当日预计进流（基于历史日均）
    - `daily_forecast[].outflow`:            当日预计出流（食材 + 人工 + 房租 + 水电）
    - `daily_forecast[].cumulative_balance`: 当日末累计余额
    - `daily_forecast[].is_alert`:           是否触发资金预警
    - `daily_forecast[].confidence`:         预测置信度（7天内 85%，14天内 70%，以后 55%）
    - `alerts`:                              触发预警的日期（最多 5 条）

    **资金预警线**：累计余额 < 日均收入 × 7 天时触发。
    """
    svc = FCTService(db)
    return await svc.forecast_cash_flow(store_id, days=days, starting_balance=starting_balance)


@router.get(
    "/{store_id}/budget-execution/{year}/{month}",
    summary="预算执行率分析",
)
async def get_budget_execution(
    store_id: str,
    year:     int,
    month:    int,
    db:   AsyncSession = Depends(get_db),
    _:    User         = Depends(get_current_user),
):
    """
    月度预算执行率分析（按科目）：

    - `revenue.exec_rate`:           收入达成率（实际/预算 × 100%）
    - `categories[].exec_rate`:      各支出科目执行率
    - `categories[].status`:         over（超 110%）/ normal / under（低 80%）/ no_budget
    - `overall.profit_margin_pct`:   本月利润率（(收入-支出)/收入）
    - `alerts`:                      超预算科目预警

    超预算阈值：
      - > 110% = warning
      - > 130% = high（需关注）
    """
    if not (1 <= month <= 12):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"月份无效：{month}",
        )
    svc = FCTService(db)
    return await svc.get_budget_execution(store_id, year, month)
