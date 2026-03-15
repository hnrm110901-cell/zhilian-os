"""
月度人事报表API — 生成/查看/导出
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from io import BytesIO
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..services.hr_report_engine import HRReportEngine
from ..services.hr_excel_export import HRExcelExporter
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter()

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/hr/report/monthly/{store_id}/{pay_month}")
async def get_monthly_report(
    store_id: str,
    pay_month: str,
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """获取月度人事报表（7张表）"""
    engine = HRReportEngine(store_id, brand_id)
    try:
        report = await engine.generate_monthly_report(db, pay_month)
        return report
    except Exception as e:
        logger.error("monthly_report_failed", store_id=store_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"报表生成失败: {str(e)}")


@router.get("/hr/report/cross-store/{brand_id}/{pay_month}")
async def cross_store_report(
    brand_id: str,
    pay_month: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """跨门店人事汇总"""
    from ..models.store import Store
    from sqlalchemy import select

    # 获取品牌下所有门店
    result = await db.execute(
        select(Store).where(
            Store.brand_id == brand_id,
            Store.is_active.is_(True),
        )
    )
    stores = result.scalars().all()

    store_reports = []
    total_headcount = 0
    total_new = 0
    total_resign = 0

    for store in stores:
        try:
            engine = HRReportEngine(store.id, brand_id)
            report = await engine.generate_monthly_report(db, pay_month)
            sc = report.get("salary_changes", {})
            hc = report.get("headcount_inventory", {})
            store_reports.append({
                "store_id": store.id,
                "store_name": store.name,
                "headcount": hc.get("total_headcount", 0),
                "new_count": sc.get("new_count", 0),
                "resign_count": sc.get("resignation_count", 0),
                "turnover_rate_pct": report.get("hr_summary", {}).get("turnover_rate_pct", 0),
            })
            total_headcount += hc.get("total_headcount", 0)
            total_new += sc.get("new_count", 0)
            total_resign += sc.get("resignation_count", 0)
        except Exception as e:
            logger.warning("cross_store_report_failed", store_id=store.id, error=str(e))

    return {
        "brand_id": brand_id,
        "pay_month": pay_month,
        "total_stores": len(stores),
        "total_headcount": total_headcount,
        "total_new": total_new,
        "total_resign": total_resign,
        "overall_turnover_rate_pct": round(total_resign / max(total_headcount, 1) * 100, 1),
        "stores": store_reports,
    }


# ── AI深度洞察端点 ─────────────────────────────────────────


@router.get("/hr/report/ai-insights/{store_id}/{month}")
async def get_ai_insights(
    store_id: str,
    month: str,
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    AI深度人力洞察 — 离职模式/成本异常/排班效率/薪资竞争力

    Response:
    - generated_at: 生成时间
    - data_source: "ai+data"（LLM可用）或 "rules_only"（LLM不可用时规则兜底）
    - summary: 结构化洞察结果
    - raw_metrics: 原始数据供前端展示
    """
    engine = HRReportEngine(store_id, brand_id)
    try:
        insights = await engine.generate_ai_insights(db, month)
        return insights
    except Exception as e:
        logger.error(
            "ai_insights_failed",
            store_id=store_id,
            month=month,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"AI洞察生成失败: {str(e)}")


# ── Excel 导出端点 ──────────────────────────────────────────


@router.get("/hr/report/monthly/{store_id}/{pay_month}/export")
async def export_monthly_report(
    store_id: str,
    pay_month: str,
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """导出月度人事报表 Excel（7张表）"""
    exporter = HRExcelExporter()
    try:
        xlsx_bytes = await exporter.export_monthly_report(db, store_id, pay_month, brand_id)
        filename = f"月度人事报表_{store_id}_{pay_month}.xlsx"
        return StreamingResponse(
            BytesIO(xlsx_bytes),
            media_type=XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("monthly_report_export_failed", store_id=store_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"报表导出失败: {str(e)}")


@router.get("/hr/report/payroll/{store_id}/{pay_month}/export")
async def export_payroll_detail(
    store_id: str,
    pay_month: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """导出工资明细表 Excel"""
    exporter = HRExcelExporter()
    try:
        xlsx_bytes = await exporter.export_payroll_detail(db, store_id, pay_month)
        filename = f"工资明细_{store_id}_{pay_month}.xlsx"
        return StreamingResponse(
            BytesIO(xlsx_bytes),
            media_type=XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("payroll_export_failed", store_id=store_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"工资明细导出失败: {str(e)}")


@router.get("/hr/report/attendance/{store_id}/{pay_month}/export")
async def export_attendance_report(
    store_id: str,
    pay_month: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """导出考勤报表 Excel"""
    exporter = HRExcelExporter()
    try:
        xlsx_bytes = await exporter.export_attendance_report(db, store_id, pay_month)
        filename = f"考勤报表_{store_id}_{pay_month}.xlsx"
        return StreamingResponse(
            BytesIO(xlsx_bytes),
            media_type=XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("attendance_export_failed", store_id=store_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"考勤报表导出失败: {str(e)}")


@router.get("/hr/report/roster/{store_id}/export")
async def export_roster(
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """导出员工花名册 Excel"""
    exporter = HRExcelExporter()
    try:
        xlsx_bytes = await exporter.export_roster(db, store_id)
        filename = f"花名册_{store_id}.xlsx"
        return StreamingResponse(
            BytesIO(xlsx_bytes),
            media_type=XLSX_MEDIA_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("roster_export_failed", store_id=store_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"花名册导出失败: {str(e)}")
