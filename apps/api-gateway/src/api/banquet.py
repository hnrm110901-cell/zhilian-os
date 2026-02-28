"""
Banquet Circuit Breaker REST API

端点：
  GET  /api/v1/banquet/auspicious-calendar        — 吉日日历（30天/90天）
  GET  /api/v1/banquet/auspicious-calendar/peaks  — 高峰日一览（因子 ≥ 阈值）
  GET  /api/v1/banquet/{store_id}/today-check     — 今日/明日宴会熔断检查
  POST /api/v1/banquet/{store_id}/beo             — 手动为指定宴会生成 BEO 单
  GET  /api/v1/banquet/{store_id}/conflicts       — 当日宴会资源冲突检测

设计：
  - AuspiciousDateService：吉日感知（纯内存，无 DB）
  - BanquetPlanningEngine：熔断判定 + BEO 生成 + 采购/排班加成
  - 冲突检测：场地容量 + 时间重叠双维度
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
from src.services.auspicious_date_service import AuspiciousDateService
from src.services.banquet_planning_engine import banquet_planning_engine

router = APIRouter(prefix="/api/v1/banquet", tags=["banquet"])


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class AuspiciousDay(BaseModel):
    date:          str
    is_auspicious: bool
    label:         str
    demand_factor: float
    sources:       List[str]


class AuspiciousCalendarResponse(BaseModel):
    start_date:     str
    days:           int
    calendar:       List[AuspiciousDay]
    auspicious_count: int


class PeakDaysResponse(BaseModel):
    start_date:  str
    days:        int
    threshold:   float
    peaks:       List[AuspiciousDay]
    total_peaks: int


class BEORequest(BaseModel):
    reservation_id:   str              = Field(..., description="宴会预约 ID")
    customer_name:    Optional[str]    = Field(None, description="客户姓名")
    party_size:       int              = Field(..., ge=1, description="宴会人数")
    reservation_time: Optional[str]   = Field(None, description="宴会时间 HH:MM 或完整 ISO 时间")
    estimated_budget: Optional[float] = Field(None, description="预算（元）")
    event_type:       str              = Field("婚宴", description="宴会类型")
    venue:            Optional[str]    = Field(None, description="场地名称")
    menu_package_name: Optional[str]  = Field(None, description="菜单套餐名称")
    special_requests: Optional[str]   = Field(None, description="特殊要求")
    operator:         Optional[str]   = Field("system", description="操作人 ID")


class ConflictCheckRequest(BaseModel):
    banquets:     List[Dict[str, Any]] = Field(..., description="当日宴会列表")
    max_capacity: int                  = Field(200, ge=1, description="场地最大容量")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/auspicious-calendar",
    summary="获取吉日日历（好日子感知）",
    response_model=AuspiciousCalendarResponse,
)
async def get_auspicious_calendar(
    start_date:   Optional[str] = Query(None, description="起始日期 YYYY-MM-DD，默认今天"),
    days:         int           = Query(30,   ge=1, le=365, description="日历长度（默认 30 天）"),
    store_config: Optional[str] = Query(None, description="门店配置 JSON 字符串（可选）"),
    _: User = Depends(get_current_user),
):
    """
    获取吉日日历，用于：
    - 前端宴会销控页面标注「好日子」
    - 销售团队提前布局旺季营销
    - 宴会经理预判资源瓶颈

    demand_factor > 1.0 表示宴会需求倍增（2.2 = 最高峰，如 5/20「我爱你」）。
    """
    sd  = _parse_date(start_date) if start_date else date.today()
    svc = AuspiciousDateService()
    cal = svc.get_calendar(days=days, start_date=sd)

    return {
        "start_date":       sd.isoformat(),
        "days":             days,
        "calendar":         cal,
        "auspicious_count": sum(1 for d in cal if d["is_auspicious"]),
    }


@router.get(
    "/auspicious-calendar/peaks",
    summary="获取高峰日列表（demand_factor ≥ 阈值）",
    response_model=PeakDaysResponse,
)
async def get_peak_days(
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD，默认今天"),
    days:       int           = Query(90,   ge=1, le=365, description="前瞻天数（默认 90 天）"),
    threshold:  float         = Query(1.5,  ge=1.0, le=3.0, description="需求因子阈值（默认 1.5）"),
    _: User = Depends(get_current_user),
):
    """
    返回未来 N 天中需求因子 ≥ threshold 的高峰日期。

    建议阈值：
    - 1.3 → 包含情人节、11/11 等一般吉日
    - 1.5 → 仅返回黄金周 / 8.8 / 9.9 等重大节点
    - 1.9 → 仅返回 5/20、七夕等顶级高峰
    """
    sd    = _parse_date(start_date) if start_date else date.today()
    svc   = AuspiciousDateService()
    peaks = svc.get_high_demand_dates(days=days, threshold=threshold, start_date=sd)

    return {
        "start_date":  sd.isoformat(),
        "days":        days,
        "threshold":   threshold,
        "peaks":       peaks,
        "total_peaks": len(peaks),
    }


@router.get(
    "/{store_id}/today-check",
    summary="检查明日宴会熔断状态",
)
async def today_banquet_check(
    store_id:    str,
    target_date: Optional[str] = Query(None, description="YYYY-MM-DD，默认=明天"),
    db: AsyncSession = Depends(get_db),
    _:  User         = Depends(get_current_user),
):
    """
    查询门店指定日期的宴会熔断状态：
    - 有哪些宴会触发熔断（party_size ≥ 阈值）
    - 是否有资源冲突（场地容量 / 时间重叠）
    - 吉日感知因子（当天是否为「好日子」）

    适合每日早上 9:00 运营人员快速 check。
    """
    td = _parse_date(target_date) if target_date else date.today() + timedelta(days=1)

    # 1. 吉日感知
    auspicious_svc  = AuspiciousDateService()
    auspicious_info = auspicious_svc.get_info(td)

    # 2. 从 DB 拉取当日确认宴会
    banquets: List[Dict[str, Any]] = []
    try:
        from src.services.reservation_service import ReservationService
        from src.models.reservation import ReservationStatus, ReservationType

        svc          = ReservationService(store_id=store_id)
        reservations = await svc.get_reservations(
            reservation_date=td.isoformat(),
            status=ReservationStatus.CONFIRMED.value,
        )
        banquets = [
            r for r in reservations
            if r.get("reservation_type") == ReservationType.BANQUET.value
        ]
    except Exception as e:
        # 非致命，返回空列表 + 警告
        pass

    # 3. 熔断检查
    circuit_results = []
    for b in banquets:
        cb = banquet_planning_engine.check_circuit_breaker(
            banquet=b, store_id=store_id, plan_date=td
        )
        circuit_results.append({
            "reservation_id": b.get("reservation_id"),
            "customer_name":  b.get("customer_name"),
            "party_size":     b.get("party_size"),
            "triggered":      cb.triggered,
            "beo_id":         cb.beo.get("beo_id") if cb.triggered and cb.beo else None,
            "addon_staff":    cb.staffing_addon.get("total_addon_staff", 0) if cb.triggered else 0,
            "addon_items":    len(cb.procurement_addon) if cb.triggered else 0,
        })

    # 4. 资源冲突检测（仅对触发熔断的大宴会）
    large_banquets = [b for b in banquets if int(b.get("party_size") or 0) >= 20]
    conflict_result = banquet_planning_engine.check_resource_conflicts(large_banquets)

    return {
        "store_id":    store_id,
        "target_date": td.isoformat(),
        "auspicious":  auspicious_info.to_dict(),
        "banquets_total":      len(banquets),
        "circuit_breaker_triggered": sum(1 for r in circuit_results if r["triggered"]),
        "circuit_results":     circuit_results,
        "resource_conflicts":  conflict_result,
    }


@router.post(
    "/{store_id}/beo",
    summary="手动生成 BEO 单（宴会执行协调文档）",
)
async def generate_beo(
    store_id: str,
    body:     BEORequest,
    _:        User = Depends(get_current_user),
):
    """
    为指定宴会手动生成 BEO（Banquet Event Order）单。

    BEO 单内容：
    - 活动基本信息（客户、时间、场地、人数）
    - 菜单快照（版本号 + 变更记录）
    - 采购清单（8 大类食材用量 + 安全系数）
    - 排班方案（协调员/服务员/厨师/收银岗位人数 + 班次时间）
    - 财务摘要（预算/定金/尾款）
    - 变更日志

    也可通过备战板审批流程自动生成；此端点供运营手动补单使用。
    """
    banquet_dict = body.model_dump(exclude={"operator"})
    beo = banquet_planning_engine.generate_beo(
        banquet=banquet_dict,
        store_id=store_id,
        plan_date=date.today() + timedelta(days=1),
        operator=body.operator or "manual",
    )
    return beo


@router.post(
    "/{store_id}/conflicts",
    summary="检测当日宴会资源冲突（场地容量 + 时间重叠）",
)
async def check_conflicts(
    store_id: str,
    body:     ConflictCheckRequest,
    _:        User = Depends(get_current_user),
):
    """
    对一批宴会预约进行资源冲突检测：

    1. **容量超限**：所有宴会客人合计 > max_capacity
    2. **时间重叠**：同一场地在重叠时间段安排多场宴会

    适用场景：
    - 宴会销售在录入新预约前预检冲突
    - 运营人员日常巡检当日/次日宴会安排
    """
    result = banquet_planning_engine.check_resource_conflicts(
        banquets=body.banquets,
        max_capacity=body.max_capacity,
    )
    return {
        "store_id":     store_id,
        "checked_at":   date.today().isoformat(),
        "banquet_count": len(body.banquets),
        **result,
    }


@router.get(
    "/{store_id}/beo/{reservation_id}",
    summary="查询宴会 BEO 单（已持久化版本）",
)
async def get_beo(
    store_id:       str,
    reservation_id: str,
    version:        Optional[int] = Query(None, description="指定版本号；不传则返回最新版本"),
    db:             AsyncSession  = Depends(get_db),
    _:              User          = Depends(get_current_user),
):
    """
    查询宴会 BEO 单：

    - 不传 version → 返回最新版本（is_latest=True）
    - 传入 version → 返回指定历史版本（用于 diff 对比）
    - 不存在则返回 404

    BEO 在备战板生成或手动调用 POST /{store_id}/beo 时自动持久化。
    """
    try:
        from sqlalchemy import select
        from src.models.banquet_event_order import BanquetEventOrder

        stmt = select(BanquetEventOrder).where(
            BanquetEventOrder.store_id       == store_id,
            BanquetEventOrder.reservation_id == reservation_id,
        )
        if version is not None:
            stmt = stmt.where(BanquetEventOrder.version == version)
        else:
            stmt = stmt.where(BanquetEventOrder.is_latest == True)  # noqa: E712

        beo_record = (await db.execute(stmt)).scalar_one_or_none()
        if not beo_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"BEO 单不存在：store={store_id} reservation={reservation_id}"
                       + (f" v{version}" if version else "（最新版本）"),
            )

        return {
            "id":              str(beo_record.id),
            "store_id":        beo_record.store_id,
            "reservation_id":  beo_record.reservation_id,
            "event_date":      beo_record.event_date.isoformat() if beo_record.event_date else None,
            "version":         beo_record.version,
            "is_latest":       beo_record.is_latest,
            "status":          beo_record.status,
            "party_size":      beo_record.party_size,
            "circuit_triggered": beo_record.circuit_triggered,
            "generated_by":    beo_record.generated_by,
            "approved_by":     beo_record.approved_by,
            "approved_at":     beo_record.approved_at.isoformat() if beo_record.approved_at else None,
            "change_summary":  beo_record.change_summary,
            "content":         beo_record.content,
            "created_at":      beo_record.created_at.isoformat() if beo_record.created_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询 BEO 失败: {str(e)}",
        )


@router.get(
    "/{store_id}/beo/{reservation_id}/history",
    summary="查询 BEO 版本历史列表",
)
async def get_beo_history(
    store_id:       str,
    reservation_id: str,
    db:             AsyncSession = Depends(get_db),
    _:              User         = Depends(get_current_user),
):
    """
    查询该预约的所有 BEO 版本（从旧到新排列）。

    用于前端展示变更历史，支持版本对比。
    """
    try:
        from sqlalchemy import select
        from src.models.banquet_event_order import BanquetEventOrder

        stmt = (
            select(
                BanquetEventOrder.id,
                BanquetEventOrder.version,
                BanquetEventOrder.is_latest,
                BanquetEventOrder.status,
                BanquetEventOrder.generated_by,
                BanquetEventOrder.approved_by,
                BanquetEventOrder.approved_at,
                BanquetEventOrder.change_summary,
                BanquetEventOrder.created_at,
            )
            .where(
                BanquetEventOrder.store_id       == store_id,
                BanquetEventOrder.reservation_id == reservation_id,
            )
            .order_by(BanquetEventOrder.version.asc())
        )
        rows = (await db.execute(stmt)).all()
        return {
            "store_id":       store_id,
            "reservation_id": reservation_id,
            "version_count":  len(rows),
            "versions": [
                {
                    "id":             str(r.id),
                    "version":        r.version,
                    "is_latest":      r.is_latest,
                    "status":         r.status,
                    "generated_by":   r.generated_by,
                    "approved_by":    r.approved_by,
                    "approved_at":    r.approved_at.isoformat() if r.approved_at else None,
                    "change_summary": r.change_summary,
                    "created_at":     r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询 BEO 历史失败: {str(e)}",
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
