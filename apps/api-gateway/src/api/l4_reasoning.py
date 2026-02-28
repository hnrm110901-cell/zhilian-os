"""
L4 推理层 REST API

端点：
  POST /api/v1/l4/stores/{store_id}/diagnose         — 全维度推理诊断（主入口）
  POST /api/v1/l4/stores/{store_id}/reason/{dim}     — 单维度轻量推理
  GET  /api/v1/l4/stores/{store_id}/reports          — 历史推理报告列表
  GET  /api/v1/l4/stores/{store_id}/reports/{id}     — 单报告证据链详情
  PATCH /api/v1/l4/stores/{store_id}/reports/{id}/action — 标记已行动
  GET  /api/v1/l4/stores/{store_id}/causal-chain     — Neo4j 因果链摘要
  GET  /api/v1/l4/stores/{store_id}/improvement-plan — 跨店改善方案
  GET  /api/v1/l4/reports/alerts                     — 全平台 P1/P2 告警报告
  POST /api/v1/l4/scan/batch                         — 批量扫描（触发 Celery 任务）

设计：
  - 每个推理端点写入 reasoning_reports，支持幂等重试
  - causal-chain 直接查询 Neo4j（实时）
  - improvement-plan 整合 L3 SIMILAR_TO 图谱
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.reasoning import ReasoningReport
from src.models.user import User
from src.services.diagnosis_service import DiagnosisService
from src.services.reasoning_engine import (
    ALL_DIMENSIONS,
    UniversalReasoningEngine,
)

router = APIRouter(prefix="/api/v1/l4", tags=["l4_reasoning"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class DiagnoseIn(BaseModel):
    kpi_context: Dict[str, Any] = Field(
        ...,
        description="KPI 实际值字典，如 {waste_rate: 0.15, labor_cost_ratio: 0.38}",
    )
    dimensions: Optional[List[str]] = Field(
        None,
        description=(
            "指定推理维度（默认全部 6 维度）："
            " waste / efficiency / quality / cost / inventory / cross_store"
        ),
    )


class ReasonSingleIn(BaseModel):
    kpi_context: Dict[str, Any] = Field(...)
    peer_context: Optional[Dict[str, float]] = Field(
        None,
        description="同伴组百分位（可从 /l3/stores/{id}/benchmarks 获取）",
    )


class BatchScanIn(BaseModel):
    store_ids: Optional[List[str]] = Field(
        None,
        description="指定门店列表（None=全部活跃门店）",
    )
    kpi_context_map: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="门店 KPI 上下文映射（key=store_id）；不提供时 Celery 任务自行拉取",
    )


class ActionIn(BaseModel):
    actioned_by: str = Field(..., description="操作人（员工 ID 或姓名）")


# ── 全维度诊断 ────────────────────────────────────────────────────────────────

@router.post(
    "/stores/{store_id}/diagnose",
    summary="全维度推理诊断",
    status_code=status.HTTP_200_OK,
)
async def diagnose_store(
    store_id: str,
    body:     DiagnoseIn,
    db:       AsyncSession = Depends(get_db),
    _:        User         = Depends(get_current_user),
):
    """
    对目标门店执行 L4 全维度推理诊断。

    推理流程（五步）：
    1. 从 L3 获取同伴组百分位
    2. 从 Neo4j 获取因果图谱提示
    3. 250+ 规则全维度匹配
    4. 置信度融合，确定 P1/P2/P3/OK 严重程度
    5. 结论持久化到 reasoning_reports 表

    返回 StoreHealthReport（整体分 / 维度详情 / 优先行动 / 因果洞察）。
    """
    svc    = DiagnosisService(db)
    report = await svc.run_full_diagnosis(
        store_id=store_id,
        kpi_context=body.kpi_context,
        dimensions=body.dimensions,
    )
    await db.commit()

    return {
        "store_id":         report.store_id,
        "report_date":      report.report_date.isoformat(),
        "overall_score":    report.overall_score,
        "severity_summary": report.severity_summary,
        "peer_group":       report.peer_group,
        "priority_actions": report.priority_actions,
        "causal_insights":  report.causal_insights,
        "cross_store_hints": report.cross_store_hints,
        "dimensions": {
            dim: {
                "severity":            c.severity,
                "root_cause":          c.root_cause,
                "confidence":          round(c.confidence, 3),
                "evidence_chain":      c.evidence_chain,
                "triggered_rules":     c.triggered_rules,
                "recommended_actions": c.recommended_actions,
                "peer_percentile":     c.peer_percentile,
                "kpi_values":          c.kpi_values,
            }
            for dim, c in report.dimensions.items()
        },
    }


# ── 单维度轻量推理 ────────────────────────────────────────────────────────────

@router.post(
    "/stores/{store_id}/reason/{dimension}",
    summary="单维度轻量推理",
)
async def reason_single_dimension(
    store_id:  str,
    dimension: str,
    body:      ReasonSingleIn,
    db:        AsyncSession = Depends(get_db),
    _:         User         = Depends(get_current_user),
):
    """
    对指定门店的单一维度执行轻量推理。

    支持维度: waste / efficiency / quality / cost / inventory / cross_store

    `peer_context` 可从 `GET /api/v1/l3/stores/{store_id}/benchmarks` 获取，
    格式: {"peer.p25": 0.05, "peer.p50": 0.08, "peer.p75": 0.12, "peer.p90": 0.18}
    """
    if dimension not in ALL_DIMENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"不支持的维度: {dimension}，可选: {ALL_DIMENSIONS}",
        )
    engine     = UniversalReasoningEngine(db)
    conclusion = await engine.reason_single(
        store_id=store_id,
        dimension=dimension,
        kpi_context=body.kpi_context,
        peer_context=body.peer_context,
    )
    await db.commit()
    return {
        "store_id":            store_id,
        "dimension":           conclusion.dimension,
        "severity":            conclusion.severity,
        "root_cause":          conclusion.root_cause,
        "confidence":          round(conclusion.confidence, 3),
        "evidence_chain":      conclusion.evidence_chain,
        "triggered_rules":     conclusion.triggered_rules,
        "recommended_actions": conclusion.recommended_actions,
        "peer_percentile":     conclusion.peer_percentile,
        "kpi_values":          conclusion.kpi_values,
    }


# ── 历史推理报告 ──────────────────────────────────────────────────────────────

@router.get(
    "/stores/{store_id}/reports",
    summary="历史推理报告列表",
    response_model=List[dict],
)
async def list_reports(
    store_id:   str,
    days:       int          = Query(30, ge=1, le=365),
    dimension:  Optional[str] = Query(None),
    severity:   Optional[str] = Query(None, regex="^(P1|P2|P3|OK)$"),
    limit:      int          = Query(50, ge=1, le=200),
    db:         AsyncSession = Depends(get_db),
    _:          User         = Depends(get_current_user),
):
    """查询门店历史推理报告，支持维度和严重程度过滤，可用于趋势图表展示。"""
    svc = DiagnosisService(db)
    return await svc.get_diagnosis_history(
        store_id=store_id,
        days=days,
        dimension=dimension,
    )


@router.get(
    "/stores/{store_id}/reports/{report_id}",
    summary="推理报告详情（含完整证据链）",
)
async def get_report_detail(
    store_id:  str,
    report_id: str,
    db:        AsyncSession = Depends(get_db),
    _:         User         = Depends(get_current_user),
):
    """获取单条推理报告的完整详情，包括证据链、触发规则和 KPI 快照。"""
    import uuid as _uuid
    try:
        rid = _uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="report_id 格式错误")

    stmt = select(ReasoningReport).where(
        and_(
            ReasoningReport.id       == rid,
            ReasoningReport.store_id == store_id,
        )
    )
    report = (await db.execute(stmt)).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="推理报告不存在")
    return {
        "report_id":           str(report.id),
        "store_id":            report.store_id,
        "report_date":         report.report_date.isoformat(),
        "dimension":           report.dimension,
        "severity":            report.severity,
        "root_cause":          report.root_cause,
        "confidence":          report.confidence,
        "evidence_chain":      report.evidence_chain,
        "triggered_rule_codes": report.triggered_rule_codes,
        "recommended_actions": report.recommended_actions,
        "peer_group":          report.peer_group,
        "peer_context":        report.peer_context,
        "peer_percentile":     report.peer_percentile,
        "kpi_snapshot":        report.kpi_snapshot,
        "is_actioned":         report.is_actioned,
        "actioned_by":         report.actioned_by,
        "actioned_at":         report.actioned_at.isoformat() if report.actioned_at else None,
        "created_at":          report.created_at.isoformat() if report.created_at else None,
    }


@router.patch(
    "/stores/{store_id}/reports/{report_id}/action",
    summary="标记推理报告已行动（Human-in-the-Loop 闭环）",
)
async def mark_report_actioned(
    store_id:  str,
    report_id: str,
    body:      ActionIn,
    db:        AsyncSession = Depends(get_db),
    _:         User         = Depends(get_current_user),
):
    """将推理报告标记为已行动，完成 P1/P2 告警的人工处理闭环。"""
    engine = UniversalReasoningEngine(db)
    ok     = await engine.mark_actioned(report_id, body.actioned_by)
    await db.commit()
    return {"success": ok, "report_id": report_id, "actioned_by": body.actioned_by}


# ── 因果链查询（实时 Neo4j） ──────────────────────────────────────────────────

@router.get(
    "/stores/{store_id}/causal-chain",
    summary="Neo4j 因果链实时查询",
    response_model=List[str],
)
async def get_causal_chain(
    store_id:    str,
    window_days: int = Query(14, ge=1, le=90),
    _:           User = Depends(get_current_user),
):
    """
    实时查询 Neo4j 图谱，返回目标门店的综合因果证据（最多 12 条）。

    包含：根因分布 / 供应链溯源 / BOM 合规 / 设备故障 / 员工误差时段
    """
    from src.services.causal_graph_service import CausalGraphService
    svc = CausalGraphService()
    try:
        return await svc.get_full_causal_summary(store_id, window_days=window_days)
    finally:
        svc.close()


# ── 跨店改善方案 ──────────────────────────────────────────────────────────────

@router.get(
    "/stores/{store_id}/improvement-plan",
    summary="跨店学习改善方案",
)
async def get_improvement_plan(
    store_id:    str,
    metric_name: str = Query("waste_rate", description="目标优化指标"),
    db:          AsyncSession = Depends(get_db),
    _:           User         = Depends(get_current_user),
):
    """
    基于 SIMILAR_TO 图谱边，识别表现更好的相似门店，生成跨店学习改善方案。

    对应知识规则 CROSS-045~CROSS-050（最佳实践传播）。
    """
    svc = DiagnosisService(db)
    return await svc.get_cross_store_improvement_plan(store_id, metric_name)


# ── 全平台 P1/P2 告警报告 ─────────────────────────────────────────────────────

@router.get(
    "/reports/alerts",
    summary="全平台 P1/P2 告警报告",
    response_model=List[dict],
)
async def get_platform_alerts(
    severity:  str          = Query("P1", regex="^(P1|P2)$"),
    days:      int          = Query(7, ge=1, le=30),
    dimension: Optional[str] = Query(None),
    limit:     int          = Query(100, ge=1, le=500),
    db:        AsyncSession = Depends(get_db),
    _:         User         = Depends(get_current_user),
):
    """
    查询全平台最近 N 天内的 P1/P2 未行动推理告警报告。

    可用于大屏展示「当前需要关注的门店异常」。
    """
    since = date.today() - timedelta(days=days)
    conditions = [
        ReasoningReport.severity    == severity,
        ReasoningReport.report_date >= since,
        ReasoningReport.is_actioned == False,  # noqa: E712
    ]
    if dimension:
        conditions.append(ReasoningReport.dimension == dimension)

    stmt = (
        select(ReasoningReport)
        .where(and_(*conditions))
        .order_by(ReasoningReport.report_date.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "report_id":   str(r.id),
            "store_id":    r.store_id,
            "report_date": r.report_date.isoformat(),
            "dimension":   r.dimension,
            "severity":    r.severity,
            "root_cause":  r.root_cause,
            "confidence":  r.confidence,
        }
        for r in rows
    ]


# ── 批量扫描（触发 Celery 夜间任务） ─────────────────────────────────────────

@router.post(
    "/scan/batch",
    summary="触发全平台批量推理扫描",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_batch_scan(
    body: BatchScanIn = BatchScanIn(),
    _:    User        = Depends(get_current_user),
):
    """
    触发 Celery 夜间全平台推理扫描任务（nightly_reasoning_scan）。

    适用于：
    - 手动补跑扫描
    - 指定门店子集重新推理
    - 告警 SLA 到期前强制刷新

    注意：Celery worker 需提供 kpi_context，此端点仅触发任务入队。
    """
    try:
        from src.core.celery_tasks import nightly_reasoning_scan
        task = nightly_reasoning_scan.delay(store_ids=body.store_ids)
        return {
            "status":   "accepted",
            "task_id":  task.id,
            "store_ids": body.store_ids,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Celery 任务提交失败: {str(e)}",
        )
