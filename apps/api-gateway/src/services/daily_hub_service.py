"""
DailyHubService - T+1 经营统筹控制台核心编排器

职责：
  - 聚合五个模块：昨日复盘 / 外部因子 / 明日预测 / 执行计划 / 工作流状态
  - 工作流优先策略：procurement/scheduling 阶段锁定时，覆盖对应模块
  - 审批后通过 L5 WeChat FSM 发送企微通知
  - Redis 24h 缓存（幂等，refresh=True 强制重生成）

数据来源优先级（procurement/staffing）：
  1. WorkflowEngine DecisionVersion（阶段已锁定）
  2. BanquetPlanningEngine 加成（宴会熔断触发时叠加）
  3. InventoryService / ScheduleService（兜底）
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

from src.services.redis_cache_service import redis_cache
from src.services.weather_adapter import weather_adapter
from src.services.forecast_features import ChineseHolidays, WeatherImpact
from src.services.auspicious_date_service import AuspiciousDateService
from src.services.banquet_planning_engine import banquet_planning_engine, BANQUET_CIRCUIT_THRESHOLD

logger = structlog.get_logger()

BANQUET_AVG_SPEND_PER_HEAD = int(os.getenv("BANQUET_AVG_SPEND_PER_HEAD", "30000"))
CACHE_TTL = 86400  # 24h


def _cache_key(store_id: str, target_date: date) -> str:
    return f"daily_hub:{store_id}:{target_date.isoformat()}"


class DailyHubService:
    """每日备战板编排服务"""

    # ── Public API ────────────────────────────────────────────────────────────

    async def generate_battle_board(
        self,
        store_id:    str,
        target_date: Optional[date]    = None,
        db:          Optional[Any]     = None,
        refresh:     bool              = False,
    ) -> Dict[str, Any]:
        """
        生成/获取备战板（幂等，优先读缓存）。

        Args:
            store_id:    门店 ID
            target_date: 规划日期（默认=明天）
            db:          AsyncSession（传入则启用工作流集成）
            refresh:     True = 跳过缓存，强制重新生成

        Returns:
            完整的备战板 dict（五模块）
        """
        if target_date is None:
            target_date = date.today() + timedelta(days=1)

        key    = _cache_key(store_id, target_date)
        if not refresh:
            cached = await redis_cache.get(key)
            if cached:
                return cached

        board = await self._build_board(store_id, target_date, db=db)
        await redis_cache.set(key, board, expire=CACHE_TTL)
        return board

    async def approve_battle_board(
        self,
        store_id:      str,
        target_date:   date,
        approver_id:   str,
        adjustments:   Optional[Dict[str, Any]] = None,
        notify_wechat: bool                     = True,
        db:            Optional[Any]            = None,
    ) -> Dict[str, Any]:
        """
        一键审批备战板：更新状态 → 写回 Redis → 发送企微通知（可选）。

        Args:
            notify_wechat: True = 通过 L5 WeChat FSM 推送企微通知
        """
        key   = _cache_key(store_id, target_date)
        board = await redis_cache.get(key)
        if not board:
            board = await self._build_board(store_id, target_date, db=db)

        board["approval_status"] = "adjusted" if adjustments else "approved"
        board["approved_by"]     = approver_id
        board["approved_at"]     = datetime.now().isoformat()
        if adjustments:
            board["adjustments"] = adjustments

        await redis_cache.set(key, board, expire=CACHE_TTL)

        if notify_wechat:
            await self._notify_approval(store_id, target_date, board, approver_id)

        logger.info(
            "备战板已审批",
            store_id=store_id,
            target_date=str(target_date),
            approver_id=approver_id,
            has_adjustments=bool(adjustments),
        )
        return board

    async def get_status(
        self,
        store_id:    str,
        target_date: date,
        db:          Optional[Any] = None,
    ) -> Dict[str, Any]:
        """轻量查询：审批状态 + 工作流当前阶段（不触发完整聚合）。"""
        key    = _cache_key(store_id, target_date)
        board  = await redis_cache.get(key)

        has_workflow  = False
        wf_phase      = None
        if db:
            try:
                from src.services.workflow_engine import WorkflowEngine
                engine = WorkflowEngine(db)
                wf = await engine.get_workflow_by_date(store_id, target_date)
                if wf:
                    has_workflow = True
                    wf_phase     = wf.current_phase
            except Exception as e:
                logger.warning("工作流状态查询失败（非致命）", error=str(e))

        return {
            "store_id":        store_id,
            "target_date":     target_date.isoformat(),
            "approval_status": board.get("approval_status", "not_generated") if board else "not_generated",
            "approved_by":     board.get("approved_by")  if board else None,
            "approved_at":     board.get("approved_at")  if board else None,
            "has_workflow":    has_workflow,
            "workflow_phase":  wf_phase,
        }

    async def get_workflow_phases(
        self,
        store_id:    str,
        target_date: date,
        db:          Any,
    ) -> Dict[str, Any]:
        """
        获取与备战板关联的工作流 6 阶段状态（含倒计时和最新版本）。

        若工作流尚未启动，返回 {workflow: null, message: "..."}。
        """
        try:
            from src.services.workflow_engine import WorkflowEngine
            from src.services.timing_service import TimingService

            engine = WorkflowEngine(db)
            wf     = await engine.get_workflow_by_date(store_id, target_date)
            if not wf:
                return {"workflow": None, "message": "工作流尚未启动，请先调用 POST /workflow/stores/{store_id}/start"}

            timing    = TimingService(db)
            phases    = await engine.get_all_phases(wf.id)
            countdown = await timing.get_workflow_countdown(wf.id)

            result = []
            for phase, cd in zip(phases, countdown):
                latest = await engine.get_latest_version(phase.id)
                result.append({
                    **cd,
                    "phase_id":          str(phase.id),
                    "latest_version":    latest.version_number if latest else 0,
                    "latest_mode":       latest.generation_mode if latest else None,
                    "latest_confidence": latest.confidence if latest else None,
                })

            return {
                "workflow_id":     str(wf.id),
                "workflow_status": wf.status,
                "current_phase":   wf.current_phase,
                "phases":          result,
            }
        except Exception as e:
            logger.warning("获取工作流阶段失败", store_id=store_id, error=str(e))
            return {"workflow": None, "message": f"工作流查询失败: {str(e)}"}

    async def get_platform_summary(self, db: Optional[Any] = None) -> Dict[str, Any]:
        """全平台今日备战板审批进度统计（大屏）。"""
        today       = date.today()
        target_date = today + timedelta(days=1)

        store_ids: List[str] = []
        if db:
            try:
                from src.models.store import Store
                from sqlalchemy import select
                rows      = (await db.execute(select(Store.id).where(Store.is_active == True))).all()  # noqa: E712
                store_ids = [str(r[0]) for r in rows]
            except Exception as e:
                logger.warning("获取门店列表失败", error=str(e))

        approved      = 0
        pending       = 0
        not_generated = 0

        for sid in store_ids:
            key   = _cache_key(sid, target_date)
            board = await redis_cache.get(key)
            if not board:
                not_generated += 1
            elif board.get("approval_status") in ("approved", "adjusted"):
                approved += 1
            else:
                pending += 1

        total = len(store_ids)
        return {
            "date":            today.isoformat(),
            "target_date":     target_date.isoformat(),
            "total_stores":    total,
            "approved":        approved,
            "pending":         pending,
            "not_generated":   not_generated,
            "approval_rate":   round(approved / total * 100, 1) if total else 0,
        }

    # ── Private: build board ──────────────────────────────────────────────────

    async def _build_board(
        self,
        store_id:    str,
        target_date: date,
        db:          Optional[Any] = None,
    ) -> Dict[str, Any]:
        yesterday = target_date - timedelta(days=1)

        yesterday_review = await self._get_yesterday_review(store_id, yesterday)
        weather_factors  = await self._get_weather_factors(target_date)
        banquet_track    = await self._get_banquet_variables(store_id, target_date)
        regular_track    = await self._compute_regular_forecast(store_id, target_date, weather_factors)
        total_predicted, total_lower, total_upper = self._merge_tracks(banquet_track, regular_track)

        purchase_order = await self._build_purchase_order(store_id)
        staffing_plan  = await self._get_staffing_plan(store_id, target_date)

        # 宴会熔断：将各宴会的采购加成合并到采购清单
        circuit_breaker_addons = banquet_track.pop("circuit_breaker_addons", [])
        for addon in circuit_breaker_addons:
            purchase_order = purchase_order + addon.get("procurement_addon", [])

        data_sources   = {
            "purchase_order": "agent:inventory",
            "staffing_plan":  "agent:schedule",
        }
        workflow_phases = None

        # ── 工作流集成：用锁定阶段的 DecisionVersion 覆盖采购/排班 ─────────────
        if db:
            sync = await self._sync_from_workflow(store_id, target_date, db)
            workflow_phases = sync.get("phases")
            data_sources.update(sync.get("data_sources", {}))
            if sync.get("purchase_order_override"):
                purchase_order = sync["purchase_order_override"]
            if sync.get("staffing_plan_override"):
                staffing_plan = sync["staffing_plan_override"]

        return {
            "store_id":         store_id,
            "target_date":      target_date.isoformat(),
            "generated_at":     datetime.now().isoformat(),
            "approval_status":  "pending",
            "yesterday_review": yesterday_review,
            "tomorrow_forecast": {
                "weather":                weather_factors.get("weather"),
                "holiday":                weather_factors.get("holiday"),
                "auspicious":             weather_factors.get("auspicious"),
                "banquet_track":          banquet_track,
                "regular_track":          regular_track,
                "total_predicted_revenue": total_predicted,
                "total_lower":            total_lower,
                "total_upper":            total_upper,
            },
            "purchase_order":   purchase_order,
            "staffing_plan":    staffing_plan,
            "workflow_phases":  workflow_phases,
            "data_sources":     data_sources,
        }

    # ── Private: workflow sync ────────────────────────────────────────────────

    async def _sync_from_workflow(
        self,
        store_id:    str,
        target_date: date,
        db:          Any,
    ) -> Dict[str, Any]:
        """
        从工作流引擎同步锁定阶段的 DecisionVersion 内容。

        当 procurement / scheduling 阶段已锁定时，
        将 DecisionVersion.content 转换为 Daily Hub 格式并覆盖对应模块。
        """
        try:
            from src.services.workflow_engine import WorkflowEngine
            from src.services.timing_service import TimingService
            from src.models.workflow import PhaseStatus

            engine = WorkflowEngine(db)
            wf     = await engine.get_workflow_by_date(store_id, target_date)
            if not wf:
                return {"phases": None, "data_sources": {}}

            timing    = TimingService(db)
            phases    = await engine.get_all_phases(wf.id)
            countdown = await timing.get_workflow_countdown(wf.id)

            phase_info:        List[Dict] = []
            data_sources:      Dict[str, str] = {}
            purchase_override: Optional[List[Dict]] = None
            staffing_override: Optional[Dict]       = None

            for phase, cd in zip(phases, countdown):
                latest = await engine.get_latest_version(phase.id)
                phase_info.append({
                    "phase_name":     phase.phase_name,
                    "phase_order":    phase.phase_order,
                    "status":         phase.status,
                    "deadline":       cd.get("deadline"),
                    "countdown":      cd.get("countdown"),
                    "latest_version": latest.version_number if latest else 0,
                    "is_overdue":     cd.get("is_overdue", False),
                })

                # 仅在 LOCKED 时覆盖
                if phase.status != PhaseStatus.LOCKED.value:
                    continue
                if not latest or not latest.content:
                    continue

                if phase.phase_name == "procurement":
                    items = latest.content.get("items", [])
                    if items:
                        purchase_override = [
                            {
                                "item_name":            i.get("ingredient"),
                                "current_stock":        None,
                                "recommended_quantity": i.get("qty"),
                                "alert_level":          i.get("urgency", "normal"),
                                "supplier_name":        None,
                            }
                            for i in items
                        ]
                        data_sources["purchase_order"] = (
                            f"workflow:procurement:v{latest.version_number}"
                        )

                elif phase.phase_name == "scheduling":
                    shifts = latest.content.get("shifts", [])
                    if shifts:
                        staffing_override = {
                            "shifts":      shifts,
                            "total_staff": latest.content.get("total_staff", 0),
                        }
                        data_sources["staffing_plan"] = (
                            f"workflow:scheduling:v{latest.version_number}"
                        )

            return {
                "phases":                 phase_info,
                "data_sources":           data_sources,
                "purchase_order_override": purchase_override,
                "staffing_plan_override":  staffing_override,
            }

        except Exception as e:
            logger.warning("工作流同步失败（非致命，降级到 Agent 数据）", error=str(e))
            return {"phases": None, "data_sources": {}}

    # ── Private: individual modules ───────────────────────────────────────────

    async def _get_yesterday_review(
        self, store_id: str, report_date: date
    ) -> Dict[str, Any]:
        try:
            from src.services.daily_report_service import daily_report_service

            report = await daily_report_service.generate_daily_report(
                store_id=store_id, report_date=report_date
            )
            return {
                "total_revenue": report.total_revenue,
                "order_count":   report.order_count,
                "health_score":  getattr(report, "health_score", None),
                "highlights":    report.highlights or [],
                "alerts":        report.alerts or [],
            }
        except Exception as e:
            logger.warning("获取昨日复盘失败，使用空数据", error=str(e))
            return {
                "total_revenue": 0,
                "order_count":   0,
                "health_score":  None,
                "highlights":    [],
                "alerts":        [],
            }

    async def _get_weather_factors(
        self,
        target_date: date,
        store_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {"weather": None, "holiday": None, "auspicious": None}

        # 天气影响
        weather = await weather_adapter.get_tomorrow_weather()
        if weather:
            impact_factor = WeatherImpact.WEATHER_IMPACT.get(weather["weather"], 1.0)
            result["weather"] = {
                "temperature":  weather["temperature"],
                "condition":    weather["weather"],
                "impact_factor": impact_factor,
            }

        # 节假日影响
        holiday_info = ChineseHolidays.get_holiday_info(target_date)
        if holiday_info:
            result["holiday"] = {
                "name":          holiday_info.get("name", ""),
                "impact_factor": ChineseHolidays.get_holiday_impact_score(target_date),
            }

        # 吉日感知（宴会好日子需求倍增因子）
        try:
            auspicious_svc = AuspiciousDateService(store_config=store_config)
            auspicious_info = auspicious_svc.get_info(target_date)
            if auspicious_info.is_auspicious:
                result["auspicious"] = {
                    "label":         auspicious_info.label,
                    "demand_factor": auspicious_info.demand_factor,
                    "sources":       auspicious_info.sources,
                }
        except Exception as e:
            logger.warning("吉日感知失败（非致命）", error=str(e))

        return result

    async def _get_banquet_variables(
        self, store_id: str, target_date: date
    ) -> Dict[str, Any]:
        """
        获取明日宴会数据（确定性收入轨道）。

        宴会收入 = 确认宴会 × 人均预算（确定性，不走概率模型）。
        这正是"宴会熔断"的核心：将宴会从散客预测轨道中分离出去。

        对 party_size ≥ BANQUET_CIRCUIT_THRESHOLD 的宴会额外触发熔断引擎，
        生成 BEO 单 + 采购加成 + 排班加成，写入 banquet["circuit_breaker"] 字段。
        """
        banquets:              List[Dict[str, Any]] = []
        deterministic_revenue: float                = 0
        circuit_breaker_addons: List[Dict[str, Any]] = []   # 熔断宴会的 BEO / 加成汇总

        try:
            from src.services.reservation_service import ReservationService
            from src.models.reservation import ReservationStatus, ReservationType

            svc          = ReservationService(store_id=store_id)
            reservations = await svc.get_reservations(
                reservation_date=target_date.isoformat(),
                status=ReservationStatus.CONFIRMED.value,
            )

            for r in reservations:
                if r.get("reservation_type") != ReservationType.BANQUET.value:
                    continue
                budget = r.get("estimated_budget") or (
                    (r.get("party_size") or 0) * BANQUET_AVG_SPEND_PER_HEAD
                )
                deterministic_revenue += budget

                banquet_entry = {
                    "reservation_id":   r.get("reservation_id"),
                    "customer_name":    r.get("customer_name"),
                    "party_size":       r.get("party_size"),
                    "estimated_budget": budget,
                    "reservation_time": r.get("reservation_time"),
                }

                # 宴会熔断：大宴会（≥ 阈值）触发确定性规划路径
                cb = banquet_planning_engine.check_circuit_breaker(
                    banquet=r,
                    store_id=store_id,
                    plan_date=target_date,
                )
                if cb.triggered:
                    banquet_entry["circuit_breaker"] = {
                        "triggered":    True,
                        "beo_id":       cb.beo.get("beo_id") if cb.beo else None,
                        "addon_staff":  cb.staffing_addon.get("total_addon_staff", 0),
                        "addon_items":  len(cb.procurement_addon),
                    }
                    circuit_breaker_addons.append({
                        "reservation_id":    r.get("reservation_id"),
                        "procurement_addon": cb.procurement_addon,
                        "staffing_addon":    cb.staffing_addon,
                        "beo":               cb.beo,
                    })

                banquets.append(banquet_entry)

        except Exception as e:
            logger.warning("获取宴会变量失败", error=str(e))

        result = {
            "active":                len(banquets) > 0,
            "banquets":              banquets,
            "deterministic_revenue": deterministic_revenue,
        }
        if circuit_breaker_addons:
            result["circuit_breaker_addons"] = circuit_breaker_addons

        return result

    async def _compute_regular_forecast(
        self,
        store_id:       str,
        target_date:    date,
        weather_factors: Dict[str, Any],
    ) -> Dict[str, Any]:
        """散客 + 外卖的概率性收入预测（天气已注入）。"""
        try:
            from src.services.enhanced_forecast_service import EnhancedForecastService

            svc          = EnhancedForecastService(store_id=store_id)
            weather_input = None
            if weather_factors.get("weather"):
                w             = weather_factors["weather"]
                weather_input = {"temperature": w["temperature"], "weather": w["condition"]}

            result = await svc.forecast_sales(
                target_date=target_date, weather_forecast=weather_input
            )
            ci = result.get("confidence_interval", {})
            return {
                "predicted_revenue":   result.get("predicted_sales", 0),
                "confidence_interval": ci,
                "confidence_level":    "95%",
            }
        except Exception as e:
            logger.warning("散客预测失败，使用零值", error=str(e))
            return {
                "predicted_revenue":   0,
                "confidence_interval": {"lower": 0, "upper": 0},
                "confidence_level":    "N/A",
            }

    def _merge_tracks(
        self,
        banquet_track: Dict[str, Any],
        regular_track: Dict[str, Any],
    ):
        """合并宴会（确定性）+ 散客（概率）双轨收入。"""
        banquet_rev = banquet_track.get("deterministic_revenue", 0)
        regular_rev = regular_track.get("predicted_revenue", 0)
        ci          = regular_track.get("confidence_interval", {})
        lower       = ci.get("lower", 0)
        upper       = ci.get("upper", 0)

        total       = banquet_rev + regular_rev
        total_lower = banquet_rev + lower
        total_upper = banquet_rev + upper
        return round(total, 2), round(total_lower, 2), round(total_upper, 2)

    async def _build_purchase_order(self, store_id: str) -> List[Dict[str, Any]]:
        """从 InventoryService 生成采购清单（工作流未锁定时使用）。"""
        try:
            from src.services.inventory_service import InventoryService

            svc    = InventoryService(store_id=store_id)
            alerts = await svc.generate_restock_alerts()
            return [
                {
                    "item_name":            a.get("item_name"),
                    "current_stock":        a.get("current_stock"),
                    "recommended_quantity": a.get("recommended_quantity"),
                    "alert_level":          a.get("alert_level"),
                    "supplier_name":        a.get("supplier_name"),
                }
                for a in alerts
            ]
        except Exception as e:
            logger.warning("获取采购清单失败", error=str(e))
            return []

    async def _get_staffing_plan(
        self, store_id: str, target_date: date
    ) -> Dict[str, Any]:
        """从 ScheduleService 获取排班计划（工作流未锁定时使用）。"""
        try:
            from src.services.schedule_service import ScheduleService

            svc      = ScheduleService(store_id=store_id)
            schedule = await svc.get_schedule_by_date(target_date.isoformat())
            if not schedule:
                return {"shifts": [], "total_staff": 0}
            shifts = schedule.get("shifts", [])
            return {"shifts": shifts, "total_staff": len(shifts)}
        except Exception as e:
            logger.warning("获取排班计划失败", error=str(e))
            return {"shifts": [], "total_staff": 0}

    # ── Private: L5 WeChat notification ──────────────────────────────────────

    async def _notify_approval(
        self,
        store_id:    str,
        target_date: date,
        board:       Dict[str, Any],
        approver_id: str,
    ) -> None:
        """
        审批后通过 L5 WeChat FSM 推送企微通知（非致命）。
        """
        try:
            from src.services.wechat_action_fsm import get_wechat_fsm, ActionCategory, ActionPriority

            fsm      = get_wechat_fsm()
            receiver = os.getenv("WECHAT_DEFAULT_RECEIVER", "store_manager")

            purchase_count  = len(board.get("purchase_order", []))
            total_revenue   = (
                board.get("tomorrow_forecast", {}).get("total_predicted_revenue", 0)
            )
            has_banquet     = board.get("tomorrow_forecast", {}).get(
                "banquet_track", {}
            ).get("active", False)

            banquet_note = ""
            if has_banquet:
                banquets = board["tomorrow_forecast"]["banquet_track"].get("banquets", [])
                banquet_note = f"\n宴会预约: {len(banquets)} 场（已分离确定性收入）"

            action = await fsm.create_action(
                store_id=store_id,
                category=ActionCategory.SYSTEM,
                priority=ActionPriority.P2,
                title=f"✅ {target_date.strftime('%m/%d')} 备战板已审批",
                content=(
                    f"【明日经营规划已确认】\n"
                    f"规划日期: {target_date.isoformat()}\n"
                    f"预测营收: ¥{total_revenue:,.0f}"
                    f"{banquet_note}\n"
                    f"采购清单: {purchase_count} 项\n"
                    f"确认人: {approver_id}\n"
                    f"所有执行任务已自动下发"
                ),
                receiver_user_id=receiver,
                source_event_id=f"hub:{store_id}:{target_date.isoformat()}",
            )
            await fsm.push_to_wechat(action.action_id)

        except Exception as e:
            logger.warning(
                "备战板审批通知推送失败（非致命）",
                store_id=store_id,
                error=str(e),
            )


# 全局单例
daily_hub_service = DailyHubService()
