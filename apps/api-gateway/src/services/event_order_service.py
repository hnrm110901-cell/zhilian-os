"""
EO执行引擎服务 — Phase P3 (宴小猪能力)
EO单管理 · AI自动生成 · 演职人员调度 · 履约追踪 · 厅位展示
"""
import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.models.banquet_event_order import BanquetEventOrder, BEOStatus
from src.models.event_staff import EventStaff, StaffRole, StaffConfirmStatus
from src.models.hall_showcase import HallShowcase

logger = structlog.get_logger()


class EventOrderService:
    """EO 执行引擎核心服务"""

    # ── EO 单管理 ──

    async def list_event_orders(
        self,
        session: AsyncSession,
        store_id: str,
        status: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """获取 EO 单列表（仅最新版本）"""
        q = select(BanquetEventOrder).where(
            BanquetEventOrder.store_id == store_id,
            BanquetEventOrder.is_latest == True,
        )
        if status:
            q = q.where(BanquetEventOrder.status == status)
        if start_date:
            q = q.where(BanquetEventOrder.event_date >= start_date)
        if end_date:
            q = q.where(BanquetEventOrder.event_date <= end_date)
        q = q.order_by(BanquetEventOrder.event_date.desc())

        result = await session.execute(q)
        rows = result.scalars().all()
        return [self._eo_to_dict(r) for r in rows]

    async def get_event_order(
        self, session: AsyncSession, eo_id: str,
    ) -> Optional[Dict[str, Any]]:
        """获取 EO 单详情（含演职人员列表）"""
        result = await session.execute(
            select(BanquetEventOrder).where(BanquetEventOrder.id == eo_id)
        )
        eo = result.scalar_one_or_none()
        if not eo:
            return None

        # 获取关联演职人员
        staff_result = await session.execute(
            select(EventStaff).where(EventStaff.event_order_id == str(eo.id))
        )
        staff_list = [self._staff_to_dict(s) for s in staff_result.scalars().all()]

        d = self._eo_to_dict(eo)
        d["staff"] = staff_list
        return d

    async def generate_eo(
        self,
        session: AsyncSession,
        store_id: str,
        reservation_id: str,
        event_date: date,
        event_type: str = "wedding",
        guest_count: int = 100,
        table_count: int = 10,
        hall_id: Optional[str] = None,
        budget_fen: int = 0,
        special_requirements: str = "",
    ) -> Dict[str, Any]:
        """AI 自动生成 EO 单（预填 80% 内容）"""
        # 查找是否已有该预约的 EO，有则创建新版本
        existing = await session.execute(
            select(BanquetEventOrder).where(
                BanquetEventOrder.store_id == store_id,
                BanquetEventOrder.reservation_id == reservation_id,
                BanquetEventOrder.is_latest == True,
            )
        )
        old_eo = existing.scalar_one_or_none()
        new_version = 1
        if old_eo:
            new_version = old_eo.version + 1
            old_eo.is_latest = False

        # AI 预填内容
        content = self._ai_generate_content(
            event_type=event_type,
            guest_count=guest_count,
            table_count=table_count,
            budget_fen=budget_fen,
            special_requirements=special_requirements,
        )

        eo = BanquetEventOrder(
            store_id=store_id,
            reservation_id=reservation_id,
            event_date=event_date,
            version=new_version,
            is_latest=True,
            status=BEOStatus.DRAFT.value,
            content=content,
            party_size=guest_count,
            estimated_budget=budget_fen,
            generated_by="ai_generator",
            change_summary=f"AI自动生成v{new_version}（{event_type}，{table_count}桌）",
        )
        session.add(eo)
        await session.flush()

        # 自动生成默认演职人员槽位
        if event_type == "wedding":
            default_roles = [StaffRole.MC, StaffRole.PHOTOGRAPHER, StaffRole.VIDEOGRAPHER, StaffRole.FLORIST]
        else:
            default_roles = [StaffRole.MC, StaffRole.PHOTOGRAPHER]

        for role in default_roles:
            staff = EventStaff(
                store_id=store_id,
                event_order_id=str(eo.id),
                event_date=datetime.combine(event_date, datetime.min.time()),
                role=role.value,
                staff_name="待分配",
                confirm_status=StaffConfirmStatus.PENDING.value,
            )
            session.add(staff)

        await session.flush()
        return self._eo_to_dict(eo)

    async def confirm_eo(
        self,
        session: AsyncSession,
        eo_id: str,
        approved_by: str,
    ) -> Dict[str, Any]:
        """店长确认 EO 单"""
        result = await session.execute(
            select(BanquetEventOrder).where(BanquetEventOrder.id == eo_id)
        )
        eo = result.scalar_one_or_none()
        if not eo:
            raise ValueError("EO单不存在")
        if eo.status != BEOStatus.DRAFT.value:
            raise ValueError(f"当前状态 {eo.status} 不允许确认")

        eo.status = BEOStatus.CONFIRMED.value
        eo.approved_by = approved_by
        eo.approved_at = datetime.utcnow()
        await session.flush()
        return self._eo_to_dict(eo)

    async def update_eo_status(
        self,
        session: AsyncSession,
        eo_id: str,
        new_status: str,
    ) -> Dict[str, Any]:
        """更新 EO 状态（executed/archived/cancelled）"""
        result = await session.execute(
            select(BanquetEventOrder).where(BanquetEventOrder.id == eo_id)
        )
        eo = result.scalar_one_or_none()
        if not eo:
            raise ValueError("EO单不存在")

        eo.status = new_status
        await session.flush()
        return self._eo_to_dict(eo)

    # ── 履约时间线 ──

    async def update_fulfillment(
        self,
        session: AsyncSession,
        eo_id: str,
        node: str,
        actual_time: Optional[datetime] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        """更新履约节点打卡（布场/迎宾/开席/结束/撤场）"""
        result = await session.execute(
            select(BanquetEventOrder).where(BanquetEventOrder.id == eo_id)
        )
        eo = result.scalar_one_or_none()
        if not eo:
            raise ValueError("EO单不存在")

        content = dict(eo.content or {})
        timeline = content.get("fulfillment_timeline", {})
        timeline[node] = {
            "actual_time": (actual_time or datetime.utcnow()).isoformat(),
            "notes": notes,
            "checked_at": datetime.utcnow().isoformat(),
        }
        content["fulfillment_timeline"] = timeline
        eo.content = content
        await session.flush()
        return self._eo_to_dict(eo)

    # ── 演职人员调度 ──

    async def list_staff(
        self, session: AsyncSession, event_order_id: str,
    ) -> List[Dict[str, Any]]:
        """获取 EO 关联的演职人员列表"""
        result = await session.execute(
            select(EventStaff).where(EventStaff.event_order_id == event_order_id)
        )
        return [self._staff_to_dict(s) for s in result.scalars().all()]

    async def assign_staff(
        self,
        session: AsyncSession,
        store_id: str,
        event_order_id: str,
        role: str,
        staff_name: str,
        staff_phone: Optional[str] = None,
        company: Optional[str] = None,
        fee_fen: int = 0,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分配演职人员"""
        staff = EventStaff(
            store_id=store_id,
            event_order_id=event_order_id,
            role=role,
            staff_name=staff_name,
            staff_phone=staff_phone,
            company=company,
            fee_fen=fee_fen,
            notes=notes,
            confirm_status=StaffConfirmStatus.PENDING.value,
        )
        session.add(staff)
        await session.flush()
        return self._staff_to_dict(staff)

    async def update_staff_status(
        self,
        session: AsyncSession,
        staff_id: str,
        status: str,
    ) -> Dict[str, Any]:
        """更新人员确认状态"""
        result = await session.execute(
            select(EventStaff).where(EventStaff.id == staff_id)
        )
        staff = result.scalar_one_or_none()
        if not staff:
            raise ValueError("人员记录不存在")

        staff.confirm_status = status
        if status == StaffConfirmStatus.CONFIRMED.value:
            staff.confirmed_at = datetime.utcnow()
        await session.flush()
        return self._staff_to_dict(staff)

    # ── 宴会厅展示 ──

    async def list_halls(
        self, session: AsyncSession, store_id: str,
    ) -> List[Dict[str, Any]]:
        """获取门店宴会厅展示列表"""
        result = await session.execute(
            select(HallShowcase).where(
                HallShowcase.store_id == store_id,
                HallShowcase.is_active == True,
            ).order_by(HallShowcase.sort_order)
        )
        return [self._hall_to_dict(h) for h in result.scalars().all()]

    async def get_hall(
        self, session: AsyncSession, hall_id: str,
    ) -> Optional[Dict[str, Any]]:
        """获取厅位详情"""
        result = await session.execute(
            select(HallShowcase).where(HallShowcase.id == hall_id)
        )
        hall = result.scalar_one_or_none()
        return self._hall_to_dict(hall) if hall else None

    async def create_hall(
        self,
        session: AsyncSession,
        store_id: str,
        hall_name: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """创建宴会厅展示"""
        hall = HallShowcase(
            store_id=store_id,
            hall_name=hall_name,
            **kwargs,
        )
        session.add(hall)
        await session.flush()
        return self._hall_to_dict(hall)

    async def update_hall(
        self,
        session: AsyncSession,
        hall_id: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """更新宴会厅展示"""
        result = await session.execute(
            select(HallShowcase).where(HallShowcase.id == hall_id)
        )
        hall = result.scalar_one_or_none()
        if not hall:
            raise ValueError("厅位不存在")

        for k, v in kwargs.items():
            if hasattr(hall, k) and v is not None:
                setattr(hall, k, v)
        await session.flush()
        return self._hall_to_dict(hall)

    # ── AI 生成辅助 ──

    def _ai_generate_content(
        self,
        event_type: str,
        guest_count: int,
        table_count: int,
        budget_fen: int,
        special_requirements: str,
    ) -> Dict[str, Any]:
        """AI 预填 EO 内容（规则引擎版本，后续接入 LLM）"""
        # 按宴会类型生成默认配置
        type_configs = {
            "wedding": {
                "welcome_setup": {"arch": True, "sign_board": True, "red_carpet": True, "photo_wall": True},
                "stage_setup": {"led_screen": True, "stage_size": "6x4m", "backdrop": True},
                "flower_requirements": {"centerpiece": table_count, "arch_flower": 1, "corsage": 4},
                "audio_video": {"speakers": 4, "wireless_mic": 2, "spotlight": 4, "follow_spot": 1},
                "default_menu": "婚宴尊享套餐",
            },
            "birthday": {
                "welcome_setup": {"sign_board": True, "balloon_arch": True},
                "stage_setup": {"led_screen": True, "stage_size": "4x3m"},
                "flower_requirements": {"centerpiece": table_count},
                "audio_video": {"speakers": 2, "wireless_mic": 1},
                "default_menu": "寿宴吉祥套餐",
            },
            "corporate": {
                "welcome_setup": {"sign_board": True, "banner": True},
                "stage_setup": {"led_screen": True, "projector": True, "podium": True},
                "flower_requirements": {"centerpiece": table_count},
                "audio_video": {"speakers": 4, "wireless_mic": 3, "projector": True},
                "default_menu": "商务宴请套餐",
            },
        }

        config = type_configs.get(event_type, type_configs["corporate"])
        service_staff = max(table_count // 2, 2)

        return {
            "event_type": event_type,
            "guest_count": guest_count,
            "table_count": table_count,
            "budget_fen": budget_fen,
            "menu": {
                "package_name": config["default_menu"],
                "items": [],  # 后续关联 MenuPackage
            },
            "welcome_setup": config["welcome_setup"],
            "stage_setup": config["stage_setup"],
            "flower_requirements": config["flower_requirements"],
            "audio_video": config["audio_video"],
            "service_staff_count": service_staff,
            "chef_notes": "",
            "special_requirements": special_requirements,
            "fulfillment_timeline": {
                "setup_start": {"planned_time": None, "actual_time": None},
                "guest_arrival": {"planned_time": None, "actual_time": None},
                "event_start": {"planned_time": None, "actual_time": None},
                "event_end": {"planned_time": None, "actual_time": None},
                "teardown_end": {"planned_time": None, "actual_time": None},
            },
            "ai_generated": True,
            "ai_confidence": 0.8,
        }

    # ── 序列化 ──

    def _eo_to_dict(self, eo: BanquetEventOrder) -> Dict[str, Any]:
        content = eo.content or {}
        return {
            "id": str(eo.id),
            "store_id": eo.store_id,
            "reservation_id": eo.reservation_id,
            "event_date": eo.event_date.isoformat() if eo.event_date else None,
            "version": eo.version,
            "is_latest": eo.is_latest,
            "status": eo.status,
            "party_size": eo.party_size,
            "estimated_budget_yuan": (eo.estimated_budget or 0) / 100,
            "event_type": content.get("event_type", ""),
            "table_count": content.get("table_count", 0),
            "menu_package": content.get("menu", {}).get("package_name", ""),
            "service_staff_count": content.get("service_staff_count", 0),
            "fulfillment_timeline": content.get("fulfillment_timeline", {}),
            "ai_generated": content.get("ai_generated", False),
            "ai_confidence": content.get("ai_confidence", 0),
            "approved_by": eo.approved_by,
            "approved_at": eo.approved_at.isoformat() if eo.approved_at else None,
            "generated_by": eo.generated_by,
            "change_summary": eo.change_summary,
            "created_at": eo.created_at.isoformat() if eo.created_at else None,
        }

    def _staff_to_dict(self, s: EventStaff) -> Dict[str, Any]:
        return {
            "id": str(s.id),
            "event_order_id": s.event_order_id,
            "role": s.role,
            "staff_name": s.staff_name,
            "staff_phone": s.staff_phone,
            "company": s.company,
            "fee_yuan": s.fee_fen / 100,
            "confirm_status": s.confirm_status,
            "confirmed_at": s.confirmed_at.isoformat() if s.confirmed_at else None,
            "notes": s.notes,
        }

    def _hall_to_dict(self, h: HallShowcase) -> Dict[str, Any]:
        return {
            "id": str(h.id),
            "store_id": h.store_id,
            "hall_name": h.hall_name,
            "description": h.description,
            "capacity_min": h.capacity_min,
            "capacity_max": h.capacity_max,
            "table_count_max": h.table_count_max,
            "area_sqm": float(h.area_sqm) if h.area_sqm else None,
            "ceiling_height": float(h.ceiling_height) if h.ceiling_height else None,
            "has_led_screen": h.has_led_screen,
            "has_stage": h.has_stage,
            "has_natural_light": h.has_natural_light,
            "has_independent_entrance": h.has_independent_entrance,
            "images": h.images or [],
            "virtual_tour_url": h.virtual_tour_url,
            "price_range": h.price_range,
            "min_price_yuan": (h.min_price_fen or 0) / 100,
            "max_price_yuan": (h.max_price_fen or 0) / 100,
            "features": h.features or [],
            "sort_order": h.sort_order,
            "is_active": h.is_active,
        }


event_order_service = EventOrderService()
