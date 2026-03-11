"""
月度经营报告 API

提供：
  GET /api/v1/reports/monthly/{store_id}       — JSON 报告数据
  GET /api/v1/reports/monthly/{store_id}/html  — HTML 报告（可打印为 PDF）
"""

from __future__ import annotations

from datetime import date
from typing import Optional
import structlog

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_current_active_user, get_db
from ..models.user import User

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/reports", tags=["monthly_report"])


@router.get("/monthly/{store_id}")
async def get_monthly_report(
    store_id:     str,
    year:         Optional[int] = None,
    month:        Optional[int] = None,
    current_user: User          = Depends(get_current_active_user),
    db: AsyncSession            = Depends(get_db),
):
    """
    获取月度经营报告 JSON 数据。

    默认返回上个月的报告，可通过 ?year=2026&month=2 指定月份。

    返回：
      - executive_summary：高管摘要（成本率/营业额/决策采纳率/节省¥）
      - weekly_trend_chart：周成本率趋势（ECharts 数据格式）
      - top3_decisions：Top3 节省决策案例
      - cost_metrics：完整成本指标
      - decision_summary：决策汇总统计
    """
    from src.services.monthly_report_service import MonthlyReportService

    today = date.today()
    # 默认上月
    if year is None or month is None:
        first_of_this = today.replace(day=1)
        prev = first_of_this.replace(day=1)
        from datetime import timedelta
        prev = (first_of_this - timedelta(days=1)).replace(day=1)
        year  = prev.year
        month = prev.month

    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month 必须在 1–12 之间")
    if year < 2020 or year > today.year + 1:
        raise HTTPException(status_code=400, detail="year 超出合理范围")

    try:
        report = await MonthlyReportService.generate(store_id, year, month, db)
        return report
    except Exception as exc:
        logger.error("monthly_report_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"报告生成失败: {exc}")


@router.get("/monthly/{store_id}/html", response_class=HTMLResponse)
async def get_monthly_report_html(
    store_id:     str,
    year:         Optional[int] = None,
    month:        Optional[int] = None,
    current_user: User          = Depends(get_current_active_user),
    db: AsyncSession            = Depends(get_db),
):
    """
    获取月度经营报告 HTML（可直接在浏览器打印为 PDF）。

    浏览器打印快捷键：Ctrl+P (Windows) / Cmd+P (Mac)，选择「另存为 PDF」。
    """
    from src.services.monthly_report_service import MonthlyReportService

    today = date.today()
    if year is None or month is None:
        from datetime import timedelta
        prev  = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        year  = prev.year
        month = prev.month

    try:
        html = await MonthlyReportService.generate_html(store_id, year, month, db)
        return HTMLResponse(content=html, status_code=200)
    except Exception as exc:
        logger.error("monthly_report_html_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"HTML 报告生成失败: {exc}")


@router.get("/monthly/{store_id}/excel")
async def get_monthly_report_excel(
    store_id:     str,
    year:         Optional[int] = None,
    month:        Optional[int] = None,
    current_user: User          = Depends(get_current_active_user),
    db: AsyncSession            = Depends(get_db),
):
    """
    下载月度经营报告 Excel（.xlsx）。

    包含三个工作表：经营摘要 / 周趋势 / Top3决策明细。
    """
    from src.services.monthly_report_service import MonthlyReportService

    today = date.today()
    if year is None or month is None:
        from datetime import timedelta
        prev  = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        year  = prev.year
        month = prev.month

    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month 必须在 1–12 之间")

    try:
        xlsx_bytes = await MonthlyReportService.generate_excel(store_id, year, month, db)
        filename = f"monthly_report_{store_id}_{year}{month:02d}.xlsx"
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        logger.error("monthly_report_excel_failed", store_id=store_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Excel 报告生成失败: {exc}")
