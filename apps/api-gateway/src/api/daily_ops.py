"""
日清日结 + 周复盘 API 路由
涵盖：日经营数据、日结单、预警、整改任务、周复盘、数据质量
"""
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import structlog

from src.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.daily_metric_service import DailyMetricService
from src.services.daily_settlement_service import DailySettlementService
from src.services.warning_service import WarningService
from src.services.action_task_service import ActionTaskService
from src.services.weekly_review_service import WeeklyReviewService

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["daily-ops"])


# ── Pydantic 请求模型 ────────────────────────────────────────

class SubmitSettlementRequest(BaseModel):
    storeId: str
    bizDate: str
    managerComment: str
    chefComment: Optional[str] = None
    nextDayActionPlan: str
    nextDayFocusTargets: Optional[dict] = None


class ReviewSettlementRequest(BaseModel):
    settlementNo: str
    action: str  # approve / return
    reviewComment: str
    returnedReason: Optional[str] = None


class SubmitTaskRequest(BaseModel):
    submitComment: str
    attachments: Optional[list] = None


class ReviewTaskRequest(BaseModel):
    action: str  # approve / return
    reviewComment: str


class CloseTaskRequest(BaseModel):
    closeComment: str


class SubmitWeeklyReviewRequest(BaseModel):
    weekStartDate: str
    weekEndDate: str
    managerSummary: str
    nextWeekPlan: str
    nextWeekFocusTargets: Optional[dict] = None


class ReviewWeeklyReviewRequest(BaseModel):
    action: str  # approve / return
    reviewComment: str


# ── 日经营数据接口 ───────────────────────────────────────────

@router.get("/store-daily-metrics/{store_id}")
async def get_daily_metrics(
    store_id: str,
    bizDate: str = Query(..., description="日期 yyyy-MM-dd"),
    db: AsyncSession = Depends(get_db),
):
    """获取门店某日经营数据"""
    svc = DailyMetricService(db)
    biz_date = date.fromisoformat(bizDate)
    metric = await svc.get_by_date(store_id, biz_date)
    if not metric:
        raise HTTPException(status_code=404, detail=f"门店 {store_id} 在 {bizDate} 无经营数据")
    return svc.to_api_dict(metric)


@router.get("/store-daily-metrics/{store_id}/summary")
async def get_daily_summary(
    store_id: str,
    bizDate: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """获取门店某日经营摘要（含预警等级和主要问题）"""
    svc = DailyMetricService(db)
    biz_date = date.fromisoformat(bizDate)
    return await svc.get_summary(store_id, biz_date)


# ── 日结接口 ─────────────────────────────────────────────────

@router.get("/daily-settlements/{store_id}")
async def get_daily_settlement(
    store_id: str,
    bizDate: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """获取门店日结详情"""
    svc = DailySettlementService(db)
    biz_date = date.fromisoformat(bizDate)
    s = await svc.get_or_create(store_id, biz_date)
    return svc.to_api_dict(s)


@router.post("/daily-settlements/submit")
async def submit_daily_settlement(
    req: SubmitSettlementRequest,
    db: AsyncSession = Depends(get_db),
):
    """提交日结"""
    svc = DailySettlementService(db)
    try:
        biz_date = date.fromisoformat(req.bizDate)
        s = await svc.submit(
            store_id=req.storeId,
            biz_date=biz_date,
            submitted_by="current_user",  # TODO: 接入 JWT
            manager_comment=req.managerComment,
            chef_comment=req.chefComment,
            next_day_action_plan=req.nextDayActionPlan,
            next_day_focus_targets=req.nextDayFocusTargets,
        )
        return {"success": True, "settlementNo": s.settlement_no, "status": s.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/daily-settlements/review")
async def review_daily_settlement(
    req: ReviewSettlementRequest,
    db: AsyncSession = Depends(get_db),
):
    """审核日结"""
    svc = DailySettlementService(db)
    try:
        s = await svc.review(
            settlement_no=req.settlementNo,
            reviewed_by="current_user",
            action=req.action,
            review_comment=req.reviewComment,
            returned_reason=req.returnedReason,
        )
        return {"success": True, "status": s.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 预警接口 ─────────────────────────────────────────────────

@router.get("/warnings/{store_id}")
async def get_warnings(
    store_id: str,
    bizDate: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """获取门店某日预警列表"""
    svc = WarningService(db)
    biz_date = date.fromisoformat(bizDate)
    records = await svc.list_by_date(store_id, biz_date)
    return {
        "storeId": store_id,
        "bizDate": bizDate,
        "warnings": [svc.record_to_dict(r) for r in records],
    }


@router.get("/warning-rules")
async def list_warning_rules(
    db: AsyncSession = Depends(get_db),
):
    """获取预警规则列表"""
    svc = WarningService(db)
    rules = await svc.list_rules(enabled_only=False)
    return {
        "items": [
            {
                "id": str(r.id),
                "ruleCode": r.rule_code,
                "ruleName": r.rule_name,
                "businessScope": r.business_scope,
                "metricCode": r.metric_code,
                "compareOperator": r.compare_operator,
                "yellowThreshold": r.yellow_threshold,
                "redThreshold": r.red_threshold,
                "isMandatoryComment": r.is_mandatory_comment,
                "isAutoTask": r.is_auto_task,
                "enabled": r.enabled,
            }
            for r in rules
        ]
    }


@router.post("/warning-rules")
async def upsert_warning_rule(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """新增或更新预警规则"""
    svc = WarningService(db)
    rule = await svc.upsert_rule(data)
    return {"success": True, "id": str(rule.id), "ruleCode": rule.rule_code}


# ── 任务接口 ─────────────────────────────────────────────────

@router.get("/action-tasks")
async def list_action_tasks(
    storeId: Optional[str] = Query(None),
    bizDate: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    assigneeId: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """获取任务列表"""
    svc = ActionTaskService(db)
    tasks = await svc.list(
        store_id=storeId,
        biz_date=bizDate,
        status=status,
        assignee_id=assigneeId,
    )
    return {"items": [svc.to_api_dict(t) for t in tasks]}


@router.post("/action-tasks/{task_id}/submit")
async def submit_task(
    task_id: str,
    req: SubmitTaskRequest,
    db: AsyncSession = Depends(get_db),
):
    """提交任务说明"""
    svc = ActionTaskService(db)
    try:
        task = await svc.submit(task_id, req.submitComment, req.attachments)
        return {"success": True, "taskId": task_id, "status": task.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/action-tasks/{task_id}/review")
async def review_task(
    task_id: str,
    req: ReviewTaskRequest,
    db: AsyncSession = Depends(get_db),
):
    """审核任务"""
    svc = ActionTaskService(db)
    try:
        task = await svc.review(task_id, req.action, req.reviewComment)
        return {"success": True, "taskId": task_id, "status": task.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/action-tasks/{task_id}/close")
async def close_task(
    task_id: str,
    req: CloseTaskRequest,
    db: AsyncSession = Depends(get_db),
):
    """关闭任务"""
    svc = ActionTaskService(db)
    try:
        await svc.close(task_id, req.closeComment)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 周复盘接口 ───────────────────────────────────────────────

@router.get("/weekly-reviews/store/{store_id}")
async def get_store_weekly_review(
    store_id: str,
    weekStartDate: str = Query(...),
    weekEndDate: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """获取门店周复盘（不存在则自动生成草稿）"""
    svc = WeeklyReviewService(db)
    week_start = date.fromisoformat(weekStartDate)
    week_end = date.fromisoformat(weekEndDate)
    review = await svc.get_or_generate("store", store_id, week_start, week_end)
    return svc.to_api_dict(review)


@router.post("/weekly-reviews/store/{store_id}/submit")
async def submit_store_weekly_review(
    store_id: str,
    req: SubmitWeeklyReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """提交门店周复盘"""
    svc = WeeklyReviewService(db)
    week_start = date.fromisoformat(req.weekStartDate)
    week_end = date.fromisoformat(req.weekEndDate)
    # 先确保存在草稿
    review = await svc.get_or_generate("store", store_id, week_start, week_end)
    try:
        review = await svc.submit(
            review_id=str(review.id),
            submitted_by="current_user",
            manager_summary=req.managerSummary,
            next_week_plan=req.nextWeekPlan,
            next_week_focus_targets=req.nextWeekFocusTargets,
        )
        return {"success": True, "reviewNo": review.review_no, "status": review.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
