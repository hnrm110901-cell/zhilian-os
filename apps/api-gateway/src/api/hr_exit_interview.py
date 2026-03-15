"""
离职回访API — CRUD + AI分析
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
import structlog

from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..models.exit_interview import ExitInterview
from ..services.compliance_alert_service import ComplianceAlertService
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()
router = APIRouter()


class ExitInterviewRequest(BaseModel):
    store_id: str
    brand_id: str
    employee_id: str
    employee_name: Optional[str] = None
    resign_date: str  # YYYY-MM-DD
    resign_reason: str
    resign_detail: Optional[str] = None
    interview_date: Optional[str] = None
    current_status: Optional[str] = None
    willing_to_return: Optional[str] = None
    return_conditions: Optional[str] = None
    interviewer: Optional[str] = None
    remark: Optional[str] = None


@router.post("/hr/exit-interview")
async def create_exit_interview(
    req: ExitInterviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """提交离职回访记录"""
    from datetime import datetime
    interview = ExitInterview(
        store_id=req.store_id,
        brand_id=req.brand_id,
        employee_id=req.employee_id,
        employee_name=req.employee_name,
        resign_date=datetime.strptime(req.resign_date, "%Y-%m-%d").date(),
        resign_reason=req.resign_reason,
        resign_detail=req.resign_detail,
        interview_date=datetime.strptime(req.interview_date, "%Y-%m-%d").date() if req.interview_date else None,
        current_status=req.current_status,
        willing_to_return=req.willing_to_return,
        return_conditions=req.return_conditions,
        interviewer=req.interviewer,
        remark=req.remark,
    )
    db.add(interview)
    await db.commit()
    return {"id": str(interview.id), "message": "离职回访记录已保存"}


@router.get("/hr/exit-interviews")
async def list_exit_interviews(
    store_id: str = Query(...),
    brand_id: Optional[str] = Query(None),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """回访记录列表"""
    query = select(ExitInterview).where(ExitInterview.store_id == store_id)
    if brand_id:
        query = query.where(ExitInterview.brand_id == brand_id)
    query = query.order_by(ExitInterview.resign_date.desc()).limit(limit)

    result = await db.execute(query)
    interviews = result.scalars().all()

    return {
        "items": [
            {
                "id": str(i.id),
                "employee_id": i.employee_id,
                "employee_name": i.employee_name,
                "resign_date": str(i.resign_date),
                "resign_reason": i.resign_reason,
                "resign_detail": i.resign_detail,
                "interview_date": str(i.interview_date) if i.interview_date else None,
                "current_status": i.current_status,
                "willing_to_return": i.willing_to_return,
                "return_conditions": i.return_conditions,
                "interviewer": i.interviewer,
                "remark": i.remark,
            }
            for i in interviews
        ],
        "total": len(interviews),
    }


@router.get("/hr/exit-interview/insights")
async def exit_interview_insights(
    store_id: str = Query(...),
    brand_id: Optional[str] = Query(None),
    months: int = Query(6, description="分析最近N个月"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """AI分析离职原因分布+趋势"""
    from datetime import timedelta
    since = date.today() - timedelta(days=months * 30)

    query = select(ExitInterview).where(
        and_(
            ExitInterview.store_id == store_id,
            ExitInterview.resign_date >= since,
        )
    )
    if brand_id:
        query = query.where(ExitInterview.brand_id == brand_id)

    result = await db.execute(query)
    interviews = result.scalars().all()

    # 原因分布
    reason_dist = {}
    willing_stats = {"yes": 0, "no": 0, "maybe": 0}
    monthly_trend = {}

    reason_labels = {
        "personal": "个人原因", "salary": "薪资待遇", "development": "发展空间",
        "management": "管理问题", "relocation": "搬迁", "other": "其他",
    }

    for i in interviews:
        label = reason_labels.get(i.resign_reason, i.resign_reason)
        reason_dist[label] = reason_dist.get(label, 0) + 1

        if i.willing_to_return:
            willing_stats[i.willing_to_return] = willing_stats.get(i.willing_to_return, 0) + 1

        month_key = str(i.resign_date)[:7]
        monthly_trend[month_key] = monthly_trend.get(month_key, 0) + 1

    # AI建议
    top_reason = max(reason_dist.items(), key=lambda x: x[1]) if reason_dist else None
    suggestion = ""
    if top_reason:
        suggestion = f"近{months}月主要离职原因是「{top_reason[0]}」（{top_reason[1]}人），"
        if top_reason[0] == "薪资待遇":
            suggestion += "建议对标同行薪资水平，考虑调薪或增加福利"
        elif top_reason[0] == "发展空间":
            suggestion += "建议完善晋升通道和培训体系"
        elif top_reason[0] == "管理问题":
            suggestion += "建议开展管理层培训和员工满意度调查"
        else:
            suggestion += "建议深入了解具体原因并制定改进计划"

    return {
        "period_months": months,
        "total_exits": len(interviews),
        "reason_distribution": reason_dist,
        "willing_to_return": willing_stats,
        "monthly_trend": dict(sorted(monthly_trend.items())),
        "ai_suggestion": suggestion,
        "return_rate_pct": round(willing_stats["yes"] / max(len(interviews), 1) * 100, 1),
    }


# ── 合规看板API ──

@router.get("/hr/compliance/dashboard")
async def compliance_dashboard(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """合规看板（健康证/合同/身份证到期预警）"""
    svc = ComplianceAlertService(store_id)
    return await svc.get_compliance_dashboard(db)


@router.get("/hr/compliance/health-certs")
async def health_cert_alerts(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """健康证到期告警详情"""
    svc = ComplianceAlertService(store_id)
    return await svc.check_health_cert_expiry(db)


@router.get("/hr/compliance/contracts")
async def contract_expiry_alerts(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """合同到期告警详情"""
    svc = ComplianceAlertService(store_id)
    return await svc.check_contract_expiry(db)


@router.post("/hr/compliance/send-alerts")
async def send_compliance_alerts(
    store_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """手动触发合规告警推送"""
    svc = ComplianceAlertService(store_id)
    result = await svc.send_compliance_alerts(db)
    return result
