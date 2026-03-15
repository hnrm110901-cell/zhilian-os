"""
决策飞轮API — Palantir闭环控制面板
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.core.database import get_db
from src.services.decision_flywheel_service import DecisionFlywheelService

logger = structlog.get_logger()
router = APIRouter(prefix="/hr/decision-flywheel", tags=["decision_flywheel"])
_service = DecisionFlywheelService()


# ── Pydantic Models ──────────────────────────────────────


class RecordDecisionRequest(BaseModel):
    brand_id: str
    store_id: str
    decision_type: str
    module: str
    source: str = "ai"
    target_type: str
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    recommendation: str
    risk_score: Optional[int] = None
    confidence: Optional[float] = None
    predicted_impact_fen: Optional[int] = None
    ai_analysis: Optional[str] = None
    context_snapshot: Optional[dict] = None
    model_version: Optional[str] = None


class UserActionRequest(BaseModel):
    user_id: str
    action: str = Field(..., pattern="^(accept|reject|modify|ignore|defer)$")
    note: Optional[str] = None
    modified_action: Optional[str] = None


class ExecuteRequest(BaseModel):
    execution_detail: Optional[dict] = None


# ── Endpoints ────────────────────────────────────────────


@router.post("/record")
async def record_decision(
    req: RecordDecisionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    记录一条新的AI决策建议

    当AI模块（离职风险、排班优化、薪资调整等）产出建议时，
    调用此接口记录到飞轮中，等待用户响应。

    返回：
    - decision_id: 决策记录UUID
    - status: "pending"
    """
    try:
        result = await _service.record_decision(
            db,
            brand_id=req.brand_id,
            store_id=req.store_id,
            decision_type=req.decision_type,
            module=req.module,
            source=req.source,
            target_type=req.target_type,
            target_id=req.target_id,
            target_name=req.target_name,
            recommendation=req.recommendation,
            risk_score=req.risk_score,
            confidence=req.confidence,
            predicted_impact_fen=req.predicted_impact_fen,
            ai_analysis=req.ai_analysis,
            context_snapshot=req.context_snapshot,
            model_version=req.model_version,
        )
        return result
    except Exception as e:
        logger.error("record_decision_api_error", error=str(e))
        raise HTTPException(status_code=500, detail="决策记录创建失败")


@router.post("/{decision_id}/action")
async def record_action(
    decision_id: str,
    req: UserActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    记录用户对AI决策的响应

    用户可以：accept（采纳）、reject（拒绝）、modify（修改后执行）、
    ignore（忽略）、defer（延后处理）。

    返回：
    - decision_id: 决策记录UUID
    - user_action: 用户动作
    - status: "actioned"
    """
    try:
        result = await _service.record_user_action(
            db,
            decision_id=decision_id,
            user_id=req.user_id,
            action=req.action,
            note=req.note,
            modified_action=req.modified_action,
        )
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "record_action_api_error",
            decision_id=decision_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="用户响应记录失败")


@router.post("/{decision_id}/execute")
async def mark_executed(
    decision_id: str,
    req: ExecuteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    标记决策已执行

    决策被采纳或修改后，实际执行完毕时调用此接口。
    进入效果追踪阶段（30/60/90天自动Review）。

    返回：
    - decision_id: 决策记录UUID
    - executed: true
    - status: "tracking"
    """
    try:
        result = await _service.mark_executed(
            db,
            decision_id=decision_id,
            execution_detail=req.execution_detail,
        )
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "mark_executed_api_error",
            decision_id=decision_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="执行标记失败")


@router.get("/dashboard/{store_id}")
async def get_dashboard(
    store_id: str,
    brand_id: str = Query(None, description="品牌ID（可选，跨品牌聚合）"),
    db: AsyncSession = Depends(get_db),
):
    """
    决策飞轮仪表盘

    汇总门店/品牌的决策闭环数据：
    - total_decisions: 总决策数
    - acceptance_rate: 采纳率
    - avg_deviation_pct: 平均预测偏差
    - impact_summary: ¥影响汇总（预测 vs 实际）
    - by_type: 按决策类型分组统计
    - recent_decisions: 最近的决策记录
    """
    try:
        result = await _service.get_dashboard(
            db,
            store_id=store_id,
            brand_id=brand_id,
        )
        return result
    except Exception as e:
        logger.error(
            "dashboard_api_error",
            store_id=store_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="飞轮仪表盘加载失败")


@router.get("/calibration/{store_id}")
async def get_calibration(
    store_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    AI模型校准分析

    分析已完成效果追踪的决策，计算预测准确度，
    识别系统性偏差，为模型调优提供依据。

    返回：
    - total_calibrated: 已校准决策数
    - avg_deviation_pct: 整体预测偏差
    - by_type: 各决策类型的偏差分析
    - systematic_biases: 系统性偏差识别
    - calibration_recommendations: 校准建议
    """
    try:
        result = await _service.get_calibration_analysis(
            db,
            store_id=store_id,
        )
        return result
    except Exception as e:
        logger.error(
            "calibration_api_error",
            store_id=store_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="校准分析失败")


@router.get("/decisions/{store_id}")
async def list_decisions(
    store_id: str,
    decision_type: str = Query(None, description="决策类型过滤"),
    status: str = Query(None, description="状态过滤"),
    limit: int = Query(20, le=100, description="每页数量"),
    offset: int = Query(0, description="偏移量"),
    db: AsyncSession = Depends(get_db),
):
    """
    查询决策记录列表

    支持按决策类型、状态过滤，分页返回。

    返回：
    - total: 总记录数
    - items: 决策记录列表
    - limit / offset: 分页信息
    """
    try:
        result = await _service.list_decisions(
            db,
            store_id=store_id,
            decision_type=decision_type,
            status=status,
            limit=limit,
            offset=offset,
        )
        return result
    except Exception as e:
        logger.error(
            "list_decisions_api_error",
            store_id=store_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="决策记录查询失败")


@router.post("/run-reviews")
async def trigger_effect_reviews(
    db: AsyncSession = Depends(get_db),
):
    """
    手动触发效果回顾

    扫描所有处于tracking状态且到达30/60/90天节点的决策，
    执行效果评估。也可由Celery beat定时调用。

    返回：
    - reviewed_count: 本次回顾的决策数
    - results: 各决策的回顾结果摘要
    """
    try:
        result = await _service.run_effect_reviews(db)
        return result
    except Exception as e:
        logger.error("run_reviews_api_error", error=str(e))
        raise HTTPException(status_code=500, detail="效果回顾触发失败")
