"""
食品安全追溯服务 — FoodSafetyService
提供食材溯源记录管理、食品安全检查管理、预警统计等功能。
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.food_safety import FoodSafetyInspection, FoodTraceRecord

logger = structlog.get_logger()


class FoodSafetyService:
    """食品安全追溯服务"""

    # ── 溯源记录 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def create_trace_record(
        db: AsyncSession,
        data: Dict[str, Any],
    ) -> FoodTraceRecord:
        """创建食材溯源记录"""
        record = FoodTraceRecord(
            id=uuid.uuid4(),
            brand_id=data["brand_id"],
            store_id=data["store_id"],
            ingredient_name=data["ingredient_name"],
            ingredient_id=data.get("ingredient_id"),
            batch_number=data["batch_number"],
            supplier_name=data["supplier_name"],
            supplier_id=data.get("supplier_id"),
            production_date=data.get("production_date"),
            expiry_date=data.get("expiry_date"),
            receive_date=data["receive_date"],
            quantity=data["quantity"],
            unit=data["unit"],
            origin=data.get("origin"),
            certificate_url=data.get("certificate_url"),
            qr_code=data.get("qr_code"),
            temperature_on_receive=data.get("temperature_on_receive"),
            status=data.get("status", "normal"),
            notes=data.get("notes"),
        )
        db.add(record)
        await db.flush()
        logger.info(
            "food_trace_record_created",
            record_id=str(record.id),
            ingredient=record.ingredient_name,
            batch=record.batch_number,
        )
        return record

    @staticmethod
    async def list_trace_records(
        db: AsyncSession,
        brand_id: str,
        store_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        ingredient_name: Optional[str] = None,
    ) -> Tuple[List[FoodTraceRecord], int]:
        """分页查询溯源记录，返回 (records, total)"""
        conditions = [FoodTraceRecord.brand_id == brand_id]
        if store_id:
            conditions.append(FoodTraceRecord.store_id == store_id)
        if status:
            conditions.append(FoodTraceRecord.status == status)
        if ingredient_name:
            conditions.append(FoodTraceRecord.ingredient_name.ilike(f"%{ingredient_name}%"))

        where_clause = and_(*conditions)

        # 总数
        count_q = select(func.count()).select_from(FoodTraceRecord).where(where_clause)
        total = (await db.execute(count_q)).scalar() or 0

        # 分页数据
        q = (
            select(FoodTraceRecord)
            .where(where_clause)
            .order_by(FoodTraceRecord.receive_date.desc(), FoodTraceRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(q)
        records = list(result.scalars().all())

        return records, total

    @staticmethod
    async def get_trace_record(
        db: AsyncSession,
        record_id: str,
    ) -> Optional[FoodTraceRecord]:
        """获取单条溯源记录"""
        return await db.get(FoodTraceRecord, record_id)

    @staticmethod
    async def update_trace_status(
        db: AsyncSession,
        record_id: str,
        status: str,
        notes: Optional[str] = None,
    ) -> Optional[FoodTraceRecord]:
        """更新溯源记录状态（如召回）"""
        record = await db.get(FoodTraceRecord, record_id)
        if not record:
            return None
        record.status = status
        if notes is not None:
            record.notes = notes
        await db.flush()
        logger.info(
            "food_trace_status_updated",
            record_id=str(record_id),
            new_status=status,
        )
        return record

    @staticmethod
    async def check_expiring_items(
        db: AsyncSession,
        brand_id: str,
        days_ahead: int = 7,
    ) -> List[FoodTraceRecord]:
        """查询即将过期的食材（未来 days_ahead 天内到期且状态正常）"""
        today = date.today()
        deadline = today + timedelta(days=days_ahead)
        q = (
            select(FoodTraceRecord)
            .where(
                and_(
                    FoodTraceRecord.brand_id == brand_id,
                    FoodTraceRecord.status == "normal",
                    FoodTraceRecord.expiry_date.isnot(None),
                    FoodTraceRecord.expiry_date <= deadline,
                    FoodTraceRecord.expiry_date >= today,
                )
            )
            .order_by(FoodTraceRecord.expiry_date.asc())
        )
        result = await db.execute(q)
        return list(result.scalars().all())

    # ── 安全检查 ──────────────────────────────────────────────────────────────

    @staticmethod
    async def create_inspection(
        db: AsyncSession,
        data: Dict[str, Any],
    ) -> FoodSafetyInspection:
        """创建食品安全检查记录"""
        inspection = FoodSafetyInspection(
            id=uuid.uuid4(),
            brand_id=data["brand_id"],
            store_id=data["store_id"],
            inspection_type=data["inspection_type"],
            inspector_name=data["inspector_name"],
            inspection_date=data["inspection_date"],
            score=data.get("score"),
            status=data.get("status", "pending"),
            items=data.get("items", []),
            photos=data.get("photos"),
            corrective_actions=data.get("corrective_actions"),
            next_inspection_date=data.get("next_inspection_date"),
        )
        db.add(inspection)
        await db.flush()
        logger.info(
            "food_safety_inspection_created",
            inspection_id=str(inspection.id),
            type=inspection.inspection_type,
        )
        return inspection

    @staticmethod
    async def list_inspections(
        db: AsyncSession,
        brand_id: str,
        store_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        inspection_type: Optional[str] = None,
    ) -> Tuple[List[FoodSafetyInspection], int]:
        """分页查询检查记录"""
        conditions = [FoodSafetyInspection.brand_id == brand_id]
        if store_id:
            conditions.append(FoodSafetyInspection.store_id == store_id)
        if inspection_type:
            conditions.append(FoodSafetyInspection.inspection_type == inspection_type)

        where_clause = and_(*conditions)

        count_q = select(func.count()).select_from(FoodSafetyInspection).where(where_clause)
        total = (await db.execute(count_q)).scalar() or 0

        q = (
            select(FoodSafetyInspection)
            .where(where_clause)
            .order_by(FoodSafetyInspection.inspection_date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(q)
        records = list(result.scalars().all())

        return records, total

    @staticmethod
    async def get_inspection(
        db: AsyncSession,
        inspection_id: str,
    ) -> Optional[FoodSafetyInspection]:
        """获取单条检查记录"""
        return await db.get(FoodSafetyInspection, inspection_id)

    # ── 统计 ──────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_stats(
        db: AsyncSession,
        brand_id: str,
    ) -> Dict[str, Any]:
        """获取食品安全统计概览"""
        today = date.today()
        deadline = today + timedelta(days=7)

        # 溯源记录总数
        total_q = select(func.count()).select_from(FoodTraceRecord).where(FoodTraceRecord.brand_id == brand_id)
        total_records = (await db.execute(total_q)).scalar() or 0

        # 即将过期数量
        expiring_q = (
            select(func.count())
            .select_from(FoodTraceRecord)
            .where(
                and_(
                    FoodTraceRecord.brand_id == brand_id,
                    FoodTraceRecord.status == "normal",
                    FoodTraceRecord.expiry_date.isnot(None),
                    FoodTraceRecord.expiry_date <= deadline,
                    FoodTraceRecord.expiry_date >= today,
                )
            )
        )
        expiring_count = (await db.execute(expiring_q)).scalar() or 0

        # 已召回数量
        recalled_q = (
            select(func.count())
            .select_from(FoodTraceRecord)
            .where(
                and_(
                    FoodTraceRecord.brand_id == brand_id,
                    FoodTraceRecord.status == "recalled",
                )
            )
        )
        recalled_count = (await db.execute(recalled_q)).scalar() or 0

        # 检查通过率
        inspection_total_q = (
            select(func.count()).select_from(FoodSafetyInspection).where(FoodSafetyInspection.brand_id == brand_id)
        )
        inspection_total = (await db.execute(inspection_total_q)).scalar() or 0

        inspection_passed_q = (
            select(func.count())
            .select_from(FoodSafetyInspection)
            .where(
                and_(
                    FoodSafetyInspection.brand_id == brand_id,
                    FoodSafetyInspection.status == "passed",
                )
            )
        )
        inspection_passed = (await db.execute(inspection_passed_q)).scalar() or 0

        pass_rate = round(inspection_passed / inspection_total * 100, 1) if inspection_total > 0 else 0

        # 最近检查日期
        latest_q = select(func.max(FoodSafetyInspection.inspection_date)).where(FoodSafetyInspection.brand_id == brand_id)
        latest_date = (await db.execute(latest_q)).scalar()

        return {
            "total_trace_records": total_records,
            "expiring_count": expiring_count,
            "recalled_count": recalled_count,
            "inspection_total": inspection_total,
            "inspection_pass_rate": pass_rate,
            "latest_inspection_date": str(latest_date) if latest_date else None,
        }
