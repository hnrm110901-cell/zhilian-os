"""
BanquetLifecycleService — 宴会全生命周期管理服务

职责：
  - 管理宴会预约从"商机"到"完成"的 7 阶段销售漏斗
  - 锁台冲突检测（同一门店同一日期场地重复锁台）
  - 锁台超时自动释放（room_lock 超过 N 天未签约）
  - 漏斗转化率统计（各阶段数量 + 阶段间转化率）
  - 销控日历（按月展示哪些日期已有宴会预约，以及当天的吉日因子）

与其他服务的集成：
  - AuspiciousDateService：销控日历注入吉日需求因子
  - BanquetPlanningEngine：signed 阶段自动生成 / 刷新 BEO 单
  - BanquetEventOrder（DB）：BEO 持久化

设计：
  - 所有写操作先校验状态机合法性，不合法直接 raise ValueError
  - room_lock 操作检查当天场地容量（via check_resource_conflicts）
  - 每次阶段变更追加 BanquetStageHistory（审计完整性）
  - 非致命：BEO 生成失败不阻断阶段推进
"""

from __future__ import annotations

import os
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.reservation import Reservation, ReservationStatus, ReservationType
from src.models.banquet_lifecycle import (
    BanquetStage,
    BanquetStageHistory,
    STAGE_TRANSITIONS,
    INITIAL_STAGE,
    ROOM_LOCK_TIMEOUT_DAYS,
)

logger = structlog.get_logger()


class StageTransitionError(ValueError):
    """阶段转换不合法时抛出。"""
    pass


class RoomConflictError(ValueError):
    """锁台冲突时抛出（容量超限 / 时间重叠）。"""
    pass


class BanquetLifecycleService:
    """
    宴会全生命周期管理服务。

    Usage:
        svc = BanquetLifecycleService(db)
        await svc.advance_stage("RES001", BanquetStage.INTENT, operator="manager_01")
        pipeline = await svc.get_pipeline("STORE001")
        calendar = await svc.get_availability_calendar("STORE001", 2026, 5)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 阶段管理 ──────────────────────────────────────────────────────────────

    async def initialize_stage(
        self,
        reservation_id: str,
        operator:       str = "system",
        reason:         str = "宴会预约创建，进入销售漏斗",
    ) -> Reservation:
        """
        初始化宴会预约的销售阶段（设为 lead）。

        调用时机：
          ReservationService 创建 BANQUET 类型预约后自动调用。
        """
        reservation = await self._get_reservation(reservation_id)
        if reservation.reservation_type != ReservationType.BANQUET:
            raise StageTransitionError(f"预约 {reservation_id} 不是宴会类型，无法初始化阶段")
        if reservation.banquet_stage:
            raise StageTransitionError(
                f"预约 {reservation_id} 已有阶段 {reservation.banquet_stage}，请使用 advance_stage"
            )

        return await self._apply_stage_change(
            reservation=reservation,
            from_stage=None,
            to_stage=INITIAL_STAGE.value,
            operator=operator,
            reason=reason,
        )

    async def advance_stage(
        self,
        reservation_id: str,
        to_stage:       BanquetStage,
        operator:       str                   = "system",
        reason:         Optional[str]         = None,
        metadata:       Optional[Dict[str, Any]] = None,
        store_id:       str                   = "",
    ) -> Reservation:
        """
        推进宴会预约到指定阶段。

        Args:
            reservation_id: 预约 ID
            to_stage:       目标阶段（BanquetStage 枚举）
            operator:       操作人（用户 ID）
            reason:         变更原因
            metadata:       额外元数据（如合同编号、定金金额）
            store_id:       门店 ID（room_lock 冲突检测需要）

        Raises:
            StageTransitionError: 转换不合法
            RoomConflictError:    锁台时资源冲突
        """
        reservation = await self._get_reservation(reservation_id)
        from_stage  = reservation.banquet_stage

        # 1. 校验转换合法性
        self._validate_transition(from_stage, to_stage.value)

        # 2. room_lock 特殊处理：检查锁台冲突
        if to_stage == BanquetStage.ROOM_LOCK:
            await self._check_room_lock_conflict(reservation, store_id or reservation.store_id)

        # 3. 执行阶段变更
        updated = await self._apply_stage_change(
            reservation=reservation,
            from_stage=from_stage,
            to_stage=to_stage.value,
            operator=operator,
            reason=reason or f"手动推进到 {to_stage.value}",
            metadata=metadata,
        )

        # 4. 签约时自动生成/刷新 BEO（非致命）
        if to_stage == BanquetStage.SIGNED:
            await self._trigger_beo_on_signed(reservation, operator)

        logger.info(
            "宴会阶段已推进",
            reservation_id=reservation_id,
            from_stage=from_stage,
            to_stage=to_stage.value,
            operator=operator,
        )
        return updated

    async def release_expired_locks(self) -> List[str]:
        """
        释放超时的锁台预约（room_lock 超过 ROOM_LOCK_TIMEOUT_DAYS 天未签约）。

        Returns:
            释放的预约 ID 列表
        """
        cutoff = datetime.utcnow() - timedelta(days=ROOM_LOCK_TIMEOUT_DAYS)
        stmt   = select(Reservation).where(
            and_(
                Reservation.banquet_stage == BanquetStage.ROOM_LOCK.value,
                Reservation.room_locked_at <= cutoff,
            )
        )
        rows     = (await self.db.execute(stmt)).scalars().all()
        released = []

        for r in rows:
            try:
                await self._apply_stage_change(
                    reservation=r,
                    from_stage=r.banquet_stage,
                    to_stage=BanquetStage.INTENT.value,  # 回退到意向阶段
                    operator="system",
                    reason=f"锁台超时自动释放（{ROOM_LOCK_TIMEOUT_DAYS}天未签约）",
                )
                released.append(r.id)
                logger.info("锁台超时自动释放", reservation_id=r.id)
            except Exception as e:
                logger.warning("自动释放锁台失败", reservation_id=r.id, error=str(e))

        return released

    # ── 销售漏斗视图 ──────────────────────────────────────────────────────────

    async def get_pipeline(
        self,
        store_id:       str,
        event_date_gte: Optional[date] = None,
        event_date_lte: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        获取门店宴会销售漏斗（按阶段分组）。

        Returns:
            {
                stages: {
                    "lead":        [{reservation summary}, ...],
                    "intent":      [...],
                    ...
                },
                total_banquets: int,
                total_confirmed_revenue: float,
                stage_counts: {"lead": 2, "room_lock": 5, ...}
            }
        """
        stmt = select(Reservation).where(
            and_(
                Reservation.store_id         == store_id,
                Reservation.reservation_type == ReservationType.BANQUET,
                Reservation.banquet_stage    != None,  # noqa: E711
            )
        )
        if event_date_gte:
            stmt = stmt.where(Reservation.reservation_date >= event_date_gte)
        if event_date_lte:
            stmt = stmt.where(Reservation.reservation_date <= event_date_lte)

        rows      = (await self.db.execute(stmt)).scalars().all()
        stages: Dict[str, List] = {s.value: [] for s in BanquetStage}
        total_rev = 0.0

        for r in rows:
            stage = r.banquet_stage or BanquetStage.LEAD.value
            entry = self._reservation_summary(r)
            stages.setdefault(stage, []).append(entry)
            if r.banquet_stage in (BanquetStage.SIGNED.value,
                                    BanquetStage.PREPARATION.value,
                                    BanquetStage.SERVICE.value,
                                    BanquetStage.COMPLETED.value):
                total_rev += float(r.estimated_budget or 0) / 100  # 分→元

        return {
            "store_id":               store_id,
            "stages":                 stages,
            "stage_counts":           {k: len(v) for k, v in stages.items()},
            "total_banquets":         len(rows),
            "total_confirmed_revenue": round(total_rev, 2),
        }

    async def get_funnel_stats(
        self,
        store_id:  str,
        days_back: int = 90,
    ) -> Dict[str, Any]:
        """
        漏斗转化率统计（过去 N 天）。

        Returns:
            {
                stage_counts: {"lead": 50, "intent": 30, ...},
                conversion_rates: {"lead→intent": 60.0%, ...},
                avg_days_to_signed: float,
            }
        """
        since = date.today() - timedelta(days=days_back)
        stmt  = (
            select(
                Reservation.banquet_stage,
                func.count(Reservation.id).label("cnt"),
            )
            .where(
                and_(
                    Reservation.store_id         == store_id,
                    Reservation.reservation_type == ReservationType.BANQUET,
                    Reservation.reservation_date >= since,
                )
            )
            .group_by(Reservation.banquet_stage)
        )
        rows   = (await self.db.execute(stmt)).all()
        counts = {r[0]: r[1] for r in rows if r[0]}

        # 转化率（相邻阶段比值）
        ordered_stages = [s.value for s in BanquetStage if s not in (
            BanquetStage.CANCELLED, BanquetStage.COMPLETED
        )]
        conversion_rates: Dict[str, float] = {}
        for i in range(len(ordered_stages) - 1):
            fr  = ordered_stages[i]
            to  = ordered_stages[i + 1]
            cnt = counts.get(fr, 0)
            nxt = counts.get(to, 0)
            if cnt > 0:
                conversion_rates[f"{fr}→{to}"] = round(nxt / cnt * 100, 1)

        # 平均签约天数（lead→signed 历史记录）
        avg_days_to_signed = await self._calc_avg_days_to_signed(store_id, since)

        return {
            "store_id":             store_id,
            "days_back":            days_back,
            "stage_counts":         counts,
            "conversion_rates":     conversion_rates,
            "avg_days_to_signed":   avg_days_to_signed,
            "total_leads":          counts.get(BanquetStage.LEAD.value, 0),
            "total_completed":      counts.get(BanquetStage.COMPLETED.value, 0),
        }

    # ── 销控日历 ──────────────────────────────────────────────────────────────

    async def get_availability_calendar(
        self,
        store_id:    str,
        year:        int,
        month:       int,
        max_capacity: int = 200,
    ) -> Dict[str, Any]:
        """
        宴会销控日历（月视图）。

        每日展示：
        - confirmed_count:  已确认宴会场数（signed 及以后阶段）
        - total_guests:     预计接待总人数
        - locked_count:     锁台中（room_lock，尚未签约）
        - available:        True = 当日仍有剩余容量
        - demand_factor:    吉日需求倍增因子（来自 AuspiciousDateService）
        - is_auspicious:    是否为好日子
        """
        from src.services.auspicious_date_service import AuspiciousDateService

        auspicious_svc = AuspiciousDateService()
        days_in_month  = monthrange(year, month)[1]
        month_start    = date(year, month, 1)
        month_end      = date(year, month, days_in_month)

        # 查询当月所有 BANQUET 预约（已锁台及之后阶段）
        stmt = select(
            Reservation.reservation_date,
            Reservation.banquet_stage,
            Reservation.party_size,
            Reservation.room_name,
        ).where(
            and_(
                Reservation.store_id         == store_id,
                Reservation.reservation_type == ReservationType.BANQUET,
                Reservation.reservation_date >= month_start,
                Reservation.reservation_date <= month_end,
                Reservation.banquet_stage.in_([
                    BanquetStage.ROOM_LOCK.value,
                    BanquetStage.SIGNED.value,
                    BanquetStage.PREPARATION.value,
                    BanquetStage.SERVICE.value,
                    BanquetStage.COMPLETED.value,
                ]),
            )
        )
        rows = (await self.db.execute(stmt)).all()

        # 按日期汇总
        day_map: Dict[date, Dict] = {}
        for r in rows:
            d = r.reservation_date
            if d not in day_map:
                day_map[d] = {"confirmed": 0, "locked": 0, "total_guests": 0}
            if r.banquet_stage == BanquetStage.ROOM_LOCK.value:
                day_map[d]["locked"] += 1
            else:
                day_map[d]["confirmed"] += 1
            day_map[d]["total_guests"] += r.party_size or 0

        # 构造日历
        calendar = []
        for day_num in range(1, days_in_month + 1):
            d        = date(year, month, day_num)
            info     = day_map.get(d, {"confirmed": 0, "locked": 0, "total_guests": 0})
            ausp     = auspicious_svc.get_info(d)
            guests   = info["total_guests"]
            calendar.append({
                "date":             d.isoformat(),
                "weekday":          ["周一","周二","周三","周四","周五","周六","周日"][d.weekday()],
                "confirmed_count":  info["confirmed"],
                "locked_count":     info["locked"],
                "total_guests":     guests,
                "available":        guests < max_capacity,
                "capacity_pct":     round(guests / max_capacity * 100, 1) if max_capacity > 0 else 0,
                "demand_factor":    ausp.demand_factor,
                "is_auspicious":    ausp.is_auspicious,
                "auspicious_label": ausp.label if ausp.is_auspicious else None,
            })

        return {
            "store_id":     store_id,
            "year":         year,
            "month":        month,
            "max_capacity": max_capacity,
            "calendar":     calendar,
            "auspicious_days": sum(1 for d in calendar if d["is_auspicious"]),
            "fully_booked_days": sum(1 for d in calendar if not d["available"]),
        }

    async def get_stage_history(
        self,
        reservation_id: str,
    ) -> List[Dict[str, Any]]:
        """获取指定预约的完整阶段变更历史。"""
        stmt = (
            select(BanquetStageHistory)
            .where(BanquetStageHistory.reservation_id == reservation_id)
            .order_by(BanquetStageHistory.changed_at.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            {
                "id":           r.id,
                "from_stage":   r.from_stage,
                "to_stage":     r.to_stage,
                "changed_by":   r.changed_by,
                "changed_at":   r.changed_at.isoformat() if r.changed_at else None,
                "reason":       r.reason,
                "metadata":     r.metadata_,
            }
            for r in rows
        ]

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _get_reservation(self, reservation_id: str) -> Reservation:
        stmt  = select(Reservation).where(Reservation.id == reservation_id)
        r     = (await self.db.execute(stmt)).scalar_one_or_none()
        if not r:
            raise ValueError(f"预约不存在：{reservation_id}")
        return r

    @staticmethod
    def _validate_transition(from_stage: Optional[str], to_stage: str) -> None:
        """校验阶段转换合法性。"""
        if from_stage is None:
            # 初始化：仅允许 → lead
            if to_stage != BanquetStage.LEAD.value:
                raise StageTransitionError(
                    f"初始化只能设为 lead，不能设为 {to_stage}"
                )
            return

        allowed = STAGE_TRANSITIONS.get(from_stage, [])
        if to_stage not in [s.value if isinstance(s, BanquetStage) else s for s in allowed]:
            raise StageTransitionError(
                f"不允许从 {from_stage} 转换到 {to_stage}。"
                f"当前阶段允许转换到：{[s.value if isinstance(s, BanquetStage) else s for s in allowed]}"
            )

    async def _check_room_lock_conflict(
        self,
        reservation: Reservation,
        store_id:    str,
    ) -> None:
        """
        锁台前检查场地容量冲突（同日同场地已有锁台/签约宴会）。
        """
        from src.services.banquet_planning_engine import banquet_planning_engine

        stmt = select(Reservation).where(
            and_(
                Reservation.store_id         == store_id,
                Reservation.reservation_type == ReservationType.BANQUET,
                Reservation.reservation_date == reservation.reservation_date,
                Reservation.id               != reservation.id,
                Reservation.banquet_stage.in_([
                    BanquetStage.ROOM_LOCK.value,
                    BanquetStage.SIGNED.value,
                    BanquetStage.PREPARATION.value,
                ]),
            )
        )
        existing = (await self.db.execute(stmt)).scalars().all()
        banquets_to_check = [
            {
                "reservation_id":   r.id,
                "party_size":       r.party_size,
                "reservation_time": str(r.reservation_time) if r.reservation_time else None,
                "venue":            r.room_name,
            }
            for r in existing
        ] + [{
            "reservation_id":   reservation.id,
            "party_size":       reservation.party_size,
            "reservation_time": str(reservation.reservation_time) if reservation.reservation_time else None,
            "venue":            reservation.room_name,
        }]

        max_cap = int(os.getenv("BANQUET_MAX_CAPACITY", "200"))
        result  = banquet_planning_engine.check_resource_conflicts(
            banquets=banquets_to_check, max_capacity=max_cap
        )
        if result["has_conflict"]:
            conflicts_str = "; ".join(c["description"] for c in result["conflicts"])
            raise RoomConflictError(f"锁台冲突检测到资源冲突：{conflicts_str}")

    async def _apply_stage_change(
        self,
        reservation: Reservation,
        from_stage:  Optional[str],
        to_stage:    str,
        operator:    str,
        reason:      str,
        metadata:    Optional[Dict[str, Any]] = None,
    ) -> Reservation:
        """原子性更新 Reservation.banquet_stage + 追加 BanquetStageHistory。"""
        now = datetime.utcnow()

        # 更新 Reservation 字段
        reservation.banquet_stage            = to_stage
        reservation.banquet_stage_updated_at = now

        # 阶段专属时间戳
        if to_stage == BanquetStage.ROOM_LOCK.value and not reservation.room_locked_at:
            reservation.room_locked_at = now
        if to_stage == BanquetStage.SIGNED.value and not reservation.signed_at:
            reservation.signed_at = now

        self.db.add(reservation)

        # 追加历史记录
        history = BanquetStageHistory(
            reservation_id=reservation.id,
            store_id=reservation.store_id,
            from_stage=from_stage,
            to_stage=to_stage,
            changed_by=operator,
            changed_at=now,
            reason=reason,
            metadata_=metadata,
        )
        self.db.add(history)
        await self.db.flush()
        return reservation

    async def _trigger_beo_on_signed(
        self,
        reservation: Reservation,
        operator:    str,
    ) -> None:
        """签约后自动生成/刷新 BEO 单（非致命）。"""
        try:
            from src.services.banquet_planning_engine import banquet_planning_engine

            banquet_dict = {
                "reservation_id":   reservation.id,
                "customer_name":    reservation.customer_name,
                "customer_phone":   reservation.customer_phone,
                "party_size":       reservation.party_size,
                "reservation_time": str(reservation.reservation_time) if reservation.reservation_time else None,
                "estimated_budget": float(reservation.estimated_budget or 0) / 100,
                "venue":            reservation.room_name,
                "event_type":       "婚宴",
                "special_requests": reservation.special_requests,
            }
            beo = banquet_planning_engine.generate_beo(
                banquet=banquet_dict,
                store_id=reservation.store_id,
                plan_date=reservation.reservation_date,
                operator=operator,
            )
            await banquet_planning_engine.save_beo(
                beo=beo, banquet=banquet_dict, db=self.db, operator=operator
            )
        except Exception as e:
            logger.warning(
                "签约触发 BEO 生成失败（非致命）",
                reservation_id=reservation.id,
                error=str(e),
            )

    async def _calc_avg_days_to_signed(
        self,
        store_id: str,
        since:    date,
    ) -> Optional[float]:
        """计算从 lead 到 signed 的平均天数（利用 stage_history 时间戳）。"""
        try:
            lead_stmt = (
                select(
                    BanquetStageHistory.reservation_id,
                    BanquetStageHistory.changed_at,
                )
                .where(
                    and_(
                        BanquetStageHistory.store_id  == store_id,
                        BanquetStageHistory.to_stage  == BanquetStage.LEAD.value,
                        BanquetStageHistory.changed_at >= datetime.combine(since, datetime.min.time()),
                    )
                )
            )
            signed_stmt = (
                select(
                    BanquetStageHistory.reservation_id,
                    BanquetStageHistory.changed_at,
                )
                .where(
                    and_(
                        BanquetStageHistory.store_id  == store_id,
                        BanquetStageHistory.to_stage  == BanquetStage.SIGNED.value,
                        BanquetStageHistory.changed_at >= datetime.combine(since, datetime.min.time()),
                    )
                )
            )
            leads   = {r[0]: r[1] for r in (await self.db.execute(lead_stmt)).all()}
            signeds = {r[0]: r[1] for r in (await self.db.execute(signed_stmt)).all()}

            diffs = []
            for rid, lead_time in leads.items():
                if rid in signeds:
                    diff = (signeds[rid] - lead_time).days
                    if diff >= 0:
                        diffs.append(diff)

            return round(sum(diffs) / len(diffs), 1) if diffs else None
        except Exception:
            return None

    @staticmethod
    def _reservation_summary(r: Reservation) -> Dict[str, Any]:
        return {
            "reservation_id":    r.id,
            "customer_name":     r.customer_name,
            "customer_phone":    r.customer_phone,
            "reservation_date":  r.reservation_date.isoformat() if r.reservation_date else None,
            "party_size":        r.party_size,
            "estimated_budget":  round(float(r.estimated_budget or 0) / 100, 2),
            "room_name":         r.room_name,
            "banquet_stage":     r.banquet_stage,
            "room_locked_at":    r.room_locked_at.isoformat() if r.room_locked_at else None,
            "signed_at":         r.signed_at.isoformat() if r.signed_at else None,
        }
