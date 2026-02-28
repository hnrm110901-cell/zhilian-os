"""
Daily Hub (每日经营罗盘) REST API

端点：
  GET  /api/v1/daily-hub/reports/summary            — 全平台今日审批进度（大屏）
  GET  /api/v1/daily-hub/{store_id}/status           — 快速查看审批状态（前端轮询）
  GET  /api/v1/daily-hub/{store_id}/workflow-phases  — 关联工作流阶段状态（含倒计时）
  GET  /api/v1/daily-hub/{store_id}                  — 获取当日备战板（五模块聚合）
  POST /api/v1/daily-hub/{store_id}/approve          — 一键审批（触发 L5 WeChat 通知）

设计：
  - 五模块：昨日复盘 / 外部因子 / 明日预测（宴会+散客双轨合并）/ 执行计划 / 审批状态
  - 工作流集成：若当日工作流 procurement/scheduling 阶段已锁定，
    优先使用 DecisionVersion 内容覆盖对应模块（data_sources 字段标注来源）
  - 审批后通过 L5 行动层（WeChatActionFSM）发送企微通知
  - 缓存：Redis 24h，?refresh=true 强制重新生成
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_current_user
from src.models.user import User
from src.services.daily_hub_service import daily_hub_service

router = APIRouter(prefix="/api/v1/daily-hub", tags=["daily_hub"])


# ── Pydantic Response Schemas ─────────────────────────────────────────────────

class WeatherInfo(BaseModel):
    temperature:   Optional[float] = None
    condition:     Optional[str]   = None
    impact_factor: Optional[float] = None


class HolidayInfo(BaseModel):
    name:          str
    impact_factor: float


class BanquetItem(BaseModel):
    reservation_id:   Optional[str]   = None
    customer_name:    Optional[str]   = None
    party_size:       Optional[int]   = None
    estimated_budget: Optional[float] = None
    reservation_time: Optional[str]   = None


class BanquetTrack(BaseModel):
    active:                bool
    banquets:              List[BanquetItem]
    deterministic_revenue: float


class RegularTrack(BaseModel):
    predicted_revenue:   float
    confidence_interval: Optional[Dict[str, float]] = None
    confidence_level:    str


class TomorrowForecast(BaseModel):
    weather:                 Optional[WeatherInfo] = None
    holiday:                 Optional[HolidayInfo] = None
    banquet_track:           BanquetTrack
    regular_track:           RegularTrack
    total_predicted_revenue: float
    total_lower:             float
    total_upper:             float


class PurchaseItem(BaseModel):
    item_name:            Optional[str]   = None
    current_stock:        Optional[float] = None
    recommended_quantity: Optional[float] = None
    alert_level:          Optional[str]   = None
    supplier_name:        Optional[str]   = None


class StaffingPlan(BaseModel):
    shifts:      List[Dict[str, Any]]
    total_staff: int


class YesterdayReview(BaseModel):
    total_revenue: float
    order_count:   int
    health_score:  Optional[float] = None
    highlights:    List[str]
    alerts:        List[str]


class WorkflowPhaseInfo(BaseModel):
    phase_name:     str
    phase_order:    int
    status:         str
    deadline:       Optional[str] = None
    countdown:      Optional[str] = None
    latest_version: int
    is_overdue:     bool


class DailyHubBoard(BaseModel):
    store_id:          str
    target_date:       str
    generated_at:      str
    approval_status:   str                       # pending / approved / adjusted
    approved_by:       Optional[str]             = None
    approved_at:       Optional[str]             = None
    adjustments:       Optional[Dict[str, Any]]  = None
    yesterday_review:  YesterdayReview
    tomorrow_forecast: TomorrowForecast
    purchase_order:    List[PurchaseItem]
    staffing_plan:     StaffingPlan
    workflow_phases:   Optional[List[WorkflowPhaseInfo]] = None
    data_sources:      Optional[Dict[str, str]]          = None


class HubStatusResponse(BaseModel):
    store_id:        str
    target_date:     str
    approval_status: str                # pending / approved / adjusted / not_generated
    approved_by:     Optional[str]      = None
    approved_at:     Optional[str]      = None
    has_workflow:    bool
    workflow_phase:  Optional[str]      = None


# ── Request Schemas ───────────────────────────────────────────────────────────

class ApproveRequest(BaseModel):
    target_date:   str                      = Field(..., description="规划日期 YYYY-MM-DD")
    adjustments:   Optional[Dict[str, Any]] = Field(None, description="店长微调内容（覆盖系统建议）")
    notify_wechat: bool                     = Field(True,  description="审批后是否推送企微通知")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/reports/summary",
    summary="全平台今日备战板审批进度（大屏）",
)
async def get_platform_summary(
    db: AsyncSession = Depends(get_db),
    _:  User         = Depends(get_current_user),
):
    """
    全平台今日备战板汇总，供大屏展示：
    - 总门店数、已审批、待审批、未生成
    - 审批完成率
    """
    return await daily_hub_service.get_platform_summary(db=db)


@router.get(
    "/{store_id}/status",
    summary="快速查看备战板审批状态（前端轮询）",
    response_model=HubStatusResponse,
)
async def get_hub_status(
    store_id:    str,
    target_date: Optional[str] = Query(None, description="YYYY-MM-DD，默认=明天"),
    db:          AsyncSession  = Depends(get_db),
    _:           User          = Depends(get_current_user),
):
    """
    轻量查询审批状态和工作流当前阶段，不触发完整数据聚合（适合前端每 30 秒轮询）。
    """
    td = _parse_date(target_date) if target_date else date.today() + timedelta(days=1)
    return await daily_hub_service.get_status(store_id=store_id, target_date=td, db=db)


@router.get(
    "/{store_id}/workflow-phases",
    summary="获取备战板关联的工作流阶段状态（含倒计时）",
)
async def get_workflow_phases(
    store_id:    str,
    target_date: Optional[str] = Query(None, description="YYYY-MM-DD，默认=明天"),
    db:          AsyncSession  = Depends(get_db),
    _:           User          = Depends(get_current_user),
):
    """
    获取门店与备战板关联的 6 阶段工作流状态（deadline 倒计时、锁定情况、最新版本号）。

    若当日尚未启动工作流，返回 `{"workflow": null, "message": "工作流尚未启动"}`.
    """
    td = _parse_date(target_date) if target_date else date.today() + timedelta(days=1)
    return await daily_hub_service.get_workflow_phases(store_id=store_id, target_date=td, db=db)


@router.get(
    "/{store_id}",
    summary="获取门店当日备战板（五模块聚合）",
)
async def get_daily_hub(
    store_id:    str,
    target_date: Optional[str] = Query(None, description="YYYY-MM-DD，默认=明天"),
    refresh:     bool          = Query(False, description="强制跳过 Redis 缓存重新生成"),
    db:          AsyncSession  = Depends(get_db),
    _:           User          = Depends(get_current_user),
):
    """
    获取门店备战板，聚合五个模块：

    1. **昨日复盘** — 实际营收 vs 预测、成本率、亮点/预警
    2. **外部因子** — 天气影响系数、节假日影响系数
    3. **明日预测** — 宴会轨道（确定性）+ 散客轨道（概率）双轨合并
    4. **执行计划** — 采购清单 + 排班方案
    5. **工作流状态** — 若已启动工作流，展示各阶段锁定情况

    **工作流优先策略**：若工作流的 `procurement` / `scheduling` 阶段已锁定，
    优先使用对应 `DecisionVersion` 内容覆盖采购/排班模块。
    `data_sources` 字段标注每个模块的数据来源（`workflow:phase:v版本号` 或 `agent`）。
    """
    td = _parse_date(target_date) if target_date else date.today() + timedelta(days=1)
    return await daily_hub_service.generate_battle_board(
        store_id=store_id,
        target_date=td,
        db=db,
        refresh=refresh,
    )


@router.post(
    "/{store_id}/approve",
    summary="一键审批备战板（触发 L5 行动派发）",
)
async def approve_hub(
    store_id: str,
    body:     ApproveRequest,
    db:       AsyncSession = Depends(get_db),
    user:     User         = Depends(get_current_user),
):
    """
    店长一键审批当日备战板：

    1. 更新审批状态为 `approved`（有调整则为 `adjusted`）
    2. 若 `notify_wechat=true`，通过 L5 WeChat FSM 推送企微通知：
       - 采购清单 → 采购负责人
       - 排班表   → 员工群
       - 营销方案 → 营销专员
    3. 若存在关联工作流且有阶段未锁定，标记"已人工确认"

    审批后状态持久化到 Redis（24h），后续查询直接返回已审批状态。
    """
    td       = _parse_date(body.target_date)
    approver = str(user.id) if hasattr(user, "id") else "store_manager"

    return await daily_hub_service.approve_battle_board(
        store_id=store_id,
        target_date=td,
        approver_id=approver,
        adjustments=body.adjustments,
        notify_wechat=body.notify_wechat,
        db=db,
    )


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"日期格式错误，应为 YYYY-MM-DD: {raw}",
        )
