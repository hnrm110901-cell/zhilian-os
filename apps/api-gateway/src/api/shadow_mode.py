"""
影子模式 + 灰度切换 REST API

端点：
  POST   /api/v1/shadow/sessions                    创建影子会话
  GET    /api/v1/shadow/sessions/{session_id}        查看会话统计
  POST   /api/v1/shadow/sessions/{session_id}/record 记录影子数据
  POST   /api/v1/shadow/sessions/{session_id}/check  执行每日一致性检查
  POST   /api/v1/shadow/cutover/init                 初始化切换状态
  GET    /api/v1/shadow/cutover/{store_id}            查看门店切换全景
  POST   /api/v1/shadow/cutover/{store_id}/{module}/advance   推进阶段
  POST   /api/v1/shadow/cutover/{store_id}/{module}/rollback  回退阶段
  POST   /api/v1/shadow/cutover/{store_id}/{module}/canary    设置灰度比例
  GET    /api/v1/shadow/bff/hq/{brand_id}            总部切换驾驶舱BFF
"""

from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.services.shadow_mode_engine import (
    CutoverController,
    ConsistencyChecker,
    ShadowModeEngine,
)

router = APIRouter(prefix="/api/v1/shadow", tags=["shadow-mode"])
logger = structlog.get_logger()

# 单例
_shadow = ShadowModeEngine()
_checker = ConsistencyChecker()
_cutover = CutoverController()


# ── 请求模型 ──────────────────────────────────────────────────────────────────

class CreateSessionIn(BaseModel):
    brand_id: str
    store_id: str
    source_system: str
    modules: Optional[List[str]] = None
    target_pass_days: int = Field(30, ge=1, le=90)


class ShadowRecordIn(BaseModel):
    record_type: str = Field(..., description="order/inventory/payment")
    source_id: str
    source_data: Dict
    source_amount_fen: Optional[int] = None
    shadow_data: Optional[Dict] = None
    shadow_amount_fen: Optional[int] = None


class InitCutoverIn(BaseModel):
    brand_id: str
    store_id: str
    module: str = Field(..., description="analytics/management/operations/finance")


class CanaryIn(BaseModel):
    percentage: int = Field(..., ge=0, le=100)


# ── 影子会话端点 ──────────────────────────────────────────────────────────────

@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_shadow_session(body: CreateSessionIn):
    """创建影子运行会话"""
    session = _shadow.create_session(
        brand_id=body.brand_id,
        store_id=body.store_id,
        source_system=body.source_system,
        modules=body.modules,
        target_pass_days=body.target_pass_days,
    )
    return session


@router.get("/sessions/{session_id}")
async def get_session_stats(session_id: str):
    """查看影子会话统计"""
    stats = _shadow.get_session_stats(session_id)
    if not stats:
        raise HTTPException(status_code=404, detail="影子会话不存在")
    return stats


@router.post("/sessions/{session_id}/record")
async def record_shadow_data(session_id: str, body: ShadowRecordIn):
    """记录一条影子数据并立即对比"""
    record = _shadow.record_shadow(
        session_id=session_id,
        record_type=body.record_type,
        source_id=body.source_id,
        source_data=body.source_data,
        source_amount_fen=body.source_amount_fen,
        shadow_data=body.shadow_data,
        shadow_amount_fen=body.shadow_amount_fen,
    )
    if "error" in record:
        raise HTTPException(status_code=400, detail=record["error"])

    # 立即对比
    compare = _shadow.compare_record(record)
    return {
        "record_id": record["id"],
        "is_consistent": compare.is_consistent,
        "diff_fields": compare.diff_fields,
        "diff_amount_fen": compare.diff_amount_fen,
    }


@router.post("/sessions/{session_id}/check")
async def run_daily_consistency_check(session_id: str):
    """执行每日一致性检查"""
    records = _shadow._records.get(session_id, [])
    session = _shadow._sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="影子会话不存在")

    # 对比所有未对比的记录
    for r in records:
        if r.get("is_consistent") is None:
            _shadow.compare_record(r)

    result = _checker.check_daily(
        session_id=session_id,
        store_id=session["store_id"],
        records=records,
    )
    return {
        "level": result.level,
        "consistency_rate": result.consistency_rate,
        "total_compared": result.total_compared,
        "consistent_count": result.consistent_count,
        "inconsistent_count": result.inconsistent_count,
        "is_pass": result.is_pass,
        "total_diff_amount_yuan": round(result.total_diff_amount_fen / 100, 2),
        "recommendations": result.recommendations,
    }


# ── 灰度切换端点 ──────────────────────────────────────────────────────────────

@router.post("/cutover/init")
async def init_cutover(body: InitCutoverIn):
    """初始化切换状态"""
    status_obj = _cutover.init_cutover(
        brand_id=body.brand_id,
        store_id=body.store_id,
        module=body.module,
    )
    return {
        "store_id": status_obj.store_id,
        "module": status_obj.module,
        "phase": status_obj.phase,
        "can_advance": status_obj.can_advance,
        "can_rollback": status_obj.can_rollback,
    }


@router.get("/cutover/{store_id}")
async def get_store_cutover_overview(store_id: str):
    """查看门店所有模块的切换全景"""
    statuses = _cutover.get_store_overview(store_id)
    return {
        "store_id": store_id,
        "modules": [
            {
                "module": s.module,
                "phase": s.phase,
                "shadow_pass_days": s.shadow_pass_days,
                "health_gate_passed": s.health_gate_passed,
                "canary_percentage": s.canary_percentage,
                "can_advance": s.can_advance,
                "can_rollback": s.can_rollback,
            }
            for s in statuses
        ],
    }


@router.post("/cutover/{store_id}/{module}/advance")
async def advance_cutover(
    store_id: str,
    module: str,
    operator: str = Query("manual"),
    reason: str = Query(""),
):
    """推进到下一阶段"""
    try:
        status_obj = _cutover.advance(store_id, module, operator, reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "store_id": status_obj.store_id,
        "module": status_obj.module,
        "phase": status_obj.phase,
        "previous_phase": status_obj.previous_phase,
        "can_advance": status_obj.can_advance,
        "can_rollback": status_obj.can_rollback,
    }


@router.post("/cutover/{store_id}/{module}/rollback")
async def rollback_cutover(
    store_id: str,
    module: str,
    operator: str = Query("manual"),
    reason: str = Query(""),
):
    """回退到上一阶段（< 30秒生效）"""
    try:
        status_obj = _cutover.rollback(store_id, module, operator, reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "store_id": status_obj.store_id,
        "module": status_obj.module,
        "phase": status_obj.phase,
        "previous_phase": status_obj.previous_phase,
        "message": "回退成功",
    }


@router.post("/cutover/{store_id}/{module}/canary")
async def set_canary_percentage(store_id: str, module: str, body: CanaryIn):
    """设置灰度流量比例"""
    try:
        status_obj = _cutover.set_canary_percentage(store_id, module, body.percentage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "module": status_obj.module,
        "canary_percentage": status_obj.canary_percentage,
    }


# ── BFF 驾驶舱 ───────────────────────────────────────────────────────────────

@router.get("/bff/hq/{brand_id}")
async def bff_hq_shadow_dashboard(brand_id: str):
    """总部影子模式 + 切换驾驶舱"""
    # 汇总所有影子会话
    sessions = [
        s for s in _shadow._sessions.values()
        if s.get("brand_id") == brand_id
    ]

    # 汇总所有切换状态
    all_states = []
    for key, state in _cutover._states.items():
        if state.get("brand_id") == brand_id:
            all_states.append(state)

    phase_counts = {"shadow": 0, "canary": 0, "primary": 0, "sole": 0}
    for s in all_states:
        phase = s.get("phase", "shadow")
        phase_counts[phase] = phase_counts.get(phase, 0) + 1

    return {
        "brand_id": brand_id,
        "shadow_summary": {
            "total_sessions": len(sessions),
            "active_sessions": sum(1 for s in sessions if s["status"] == "active"),
            "avg_consistency_rate": round(
                sum(s.get("consistency_rate", 0) for s in sessions) / max(len(sessions), 1), 4
            ),
        },
        "cutover_summary": {
            "total_modules": len(all_states),
            "phase_distribution": phase_counts,
        },
        "sessions": [
            {
                "id": s["id"],
                "store_id": s["store_id"],
                "source_system": s["source_system"],
                "status": s["status"],
                "consistency_rate": s.get("consistency_rate", 0),
                "consecutive_pass_days": s.get("consecutive_pass_days", 0),
            }
            for s in sessions
        ],
    }
