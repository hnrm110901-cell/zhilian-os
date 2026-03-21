"""多品牌运营分析报告 API

路由前缀: /api/v1/reports/ops-analysis
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.ops_analysis_report_service import OpsAnalysisReportService

router = APIRouter(prefix="/api/v1/reports/ops-analysis", tags=["运营分析报告"])


@router.get("", summary="生成多品牌运营分析报告(JSON)")
async def get_ops_analysis_report(
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    brand_id: Optional[str] = Query(None, description="品牌ID(不传=全部种子客户)"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """生成多品牌运营分析报告JSON。"""
    brand_ids = [brand_id] if brand_id else None
    return await OpsAnalysisReportService.generate(
        db=db, start_date=start_date, end_date=end_date, brand_ids=brand_ids,
    )


@router.get("/html", summary="生成多品牌运营分析报告(HTML)")
async def get_ops_analysis_report_html(
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    brand_id: Optional[str] = Query(None, description="品牌ID(不传=全部种子客户)"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """生成HTML版多品牌运营分析报告（可打印为PDF）。"""
    brand_ids = [brand_id] if brand_id else None
    html = await OpsAnalysisReportService.generate_html(
        db=db, start_date=start_date, end_date=end_date, brand_ids=brand_ids,
    )
    return HTMLResponse(content=html)
