"""
BOM 服务层 — 配方版本管理 CRUD

职责：
  1. BOMTemplate CRUD（含版本激活/停用）
  2. BOMItem CRUD
  3. 版本链管理（新版本激活时停用旧版本）
  4. 触发 Neo4j 本体同步（调用 OntologyDataSync）
"""

import uuid
from datetime import datetime
from typing import List, Optional

import structlog
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.bom import BOMTemplate, BOMItem
from src.models.inventory import InventoryItem

logger = structlog.get_logger()


class BOMService:
    """BOM 版本化配方管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ══════════════════════════════════════════════════════════════════
    # BOMTemplate CRUD
    # ══════════════════════════════════════════════════════════════════

    async def create_bom(
        self,
        store_id: str,
        dish_id: str,
        version: str,
        effective_date: Optional[datetime] = None,
        yield_rate: float = 1.0,
        standard_portion: Optional[float] = None,
        prep_time_minutes: Optional[int] = None,
        notes: Optional[str] = None,
        created_by: Optional[str] = None,
        activate: bool = True,
    ) -> BOMTemplate:
        """
        创建新版 BOM。
        当 activate=True 时，自动将同菜品的旧版本设为 is_active=False。
        """
        eff = effective_date or datetime.utcnow()

        # 停用该菜品的现有激活版本
        if activate:
            await self.db.execute(
                update(BOMTemplate)
                .where(and_(BOMTemplate.dish_id == dish_id, BOMTemplate.is_active.is_(True)))
                .values(is_active=False, expiry_date=eff)
            )

        bom = BOMTemplate(
            id=uuid.uuid4(),
            store_id=store_id,
            dish_id=dish_id,
            version=version,
            effective_date=eff,
            yield_rate=yield_rate,
            standard_portion=standard_portion,
            prep_time_minutes=prep_time_minutes,
            notes=notes,
            created_by=created_by,
            is_active=activate,
        )
        self.db.add(bom)
        await self.db.flush()
        await self.db.refresh(bom)

        logger.info("BOM 版本创建", bom_id=str(bom.id), dish_id=str(dish_id), version=version)
        return bom

    async def get_bom(self, bom_id: str) -> Optional[BOMTemplate]:
        """按 ID 查询 BOM（含明细行）"""
        stmt = (
            select(BOMTemplate)
            .options(selectinload(BOMTemplate.items))
            .where(BOMTemplate.id == uuid.UUID(bom_id))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_bom(self, dish_id: str) -> Optional[BOMTemplate]:
        """查询菜品当前激活版本"""
        stmt = (
            select(BOMTemplate)
            .options(selectinload(BOMTemplate.items))
            .where(
                and_(
                    BOMTemplate.dish_id == uuid.UUID(dish_id),
                    BOMTemplate.is_active.is_(True),
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_bom_history(self, dish_id: str) -> List[BOMTemplate]:
        """查询菜品所有历史版本（按有效日期倒序）"""
        stmt = (
            select(BOMTemplate)
            .options(selectinload(BOMTemplate.items))
            .where(BOMTemplate.dish_id == uuid.UUID(dish_id))
            .order_by(BOMTemplate.effective_date.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_boms(self, store_id: str, active_only: bool = True) -> List[BOMTemplate]:
        """查询门店所有 BOM（默认仅激活版本）"""
        conditions = [BOMTemplate.store_id == store_id]
        if active_only:
            conditions.append(BOMTemplate.is_active.is_(True))

        stmt = (
            select(BOMTemplate)
            .options(selectinload(BOMTemplate.items))
            .where(and_(*conditions))
            .order_by(BOMTemplate.effective_date.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def approve_bom(self, bom_id: str, approver: str) -> Optional[BOMTemplate]:
        """审核 BOM 版本"""
        stmt = select(BOMTemplate).where(BOMTemplate.id == uuid.UUID(bom_id))
        result = await self.db.execute(stmt)
        bom = result.scalar_one_or_none()
        if not bom:
            return None
        bom.is_approved = True
        bom.approved_by = approver
        bom.approved_at = datetime.utcnow()
        await self.db.flush()
        return bom

    async def deactivate_bom(self, bom_id: str) -> bool:
        """停用 BOM 版本"""
        await self.db.execute(
            update(BOMTemplate)
            .where(BOMTemplate.id == uuid.UUID(bom_id))
            .values(is_active=False, expiry_date=datetime.utcnow())
        )
        return True

    async def delete_bom(self, bom_id: str) -> bool:
        """删除 BOM（仅允许删除未审核版本）"""
        stmt = select(BOMTemplate).where(BOMTemplate.id == uuid.UUID(bom_id))
        result = await self.db.execute(stmt)
        bom = result.scalar_one_or_none()
        if not bom or bom.is_approved:
            return False
        await self.db.delete(bom)
        return True

    # ══════════════════════════════════════════════════════════════════
    # BOMItem CRUD
    # ══════════════════════════════════════════════════════════════════

    async def add_bom_item(
        self,
        bom_id: str,
        ingredient_id: str,
        standard_qty: float,
        unit: str,
        raw_qty: Optional[float] = None,
        unit_cost: Optional[int] = None,
        waste_factor: float = 0.0,
        is_key_ingredient: bool = False,
        is_optional: bool = False,
        prep_notes: Optional[str] = None,
    ) -> BOMItem:
        """向 BOM 添加食材明细行"""
        bom = await self.get_bom(bom_id)
        if not bom:
            raise ValueError(f"BOM {bom_id} 不存在")

        # 若未提供 unit_cost，从 InventoryItem 查最新成本
        if unit_cost is None:
            ing_stmt = select(InventoryItem).where(InventoryItem.id == ingredient_id)
            ing_result = await self.db.execute(ing_stmt)
            ing = ing_result.scalar_one_or_none()
            if ing:
                unit_cost = ing.unit_cost

        item = BOMItem(
            id=uuid.uuid4(),
            bom_id=bom.id,
            store_id=bom.store_id,
            ingredient_id=ingredient_id,
            standard_qty=standard_qty,
            raw_qty=raw_qty,
            unit=unit,
            unit_cost=unit_cost,
            waste_factor=waste_factor,
            is_key_ingredient=is_key_ingredient,
            is_optional=is_optional,
            prep_notes=prep_notes,
        )
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)

        logger.info(
            "BOM 食材行添加",
            bom_id=bom_id,
            ingredient_id=ingredient_id,
            qty=standard_qty,
            unit=unit,
        )
        return item

    async def update_bom_item(
        self,
        item_id: str,
        standard_qty: Optional[float] = None,
        raw_qty: Optional[float] = None,
        unit: Optional[str] = None,
        unit_cost: Optional[int] = None,
        waste_factor: Optional[float] = None,
        is_key_ingredient: Optional[bool] = None,
        prep_notes: Optional[str] = None,
    ) -> Optional[BOMItem]:
        """更新 BOM 明细行"""
        stmt = select(BOMItem).where(BOMItem.id == uuid.UUID(item_id))
        result = await self.db.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            return None

        if standard_qty is not None:
            item.standard_qty = standard_qty
        if raw_qty is not None:
            item.raw_qty = raw_qty
        if unit is not None:
            item.unit = unit
        if unit_cost is not None:
            item.unit_cost = unit_cost
        if waste_factor is not None:
            item.waste_factor = waste_factor
        if is_key_ingredient is not None:
            item.is_key_ingredient = is_key_ingredient
        if prep_notes is not None:
            item.prep_notes = prep_notes

        await self.db.flush()
        return item

    async def remove_bom_item(self, item_id: str) -> bool:
        """删除 BOM 明细行"""
        stmt = select(BOMItem).where(BOMItem.id == uuid.UUID(item_id))
        result = await self.db.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            return False
        await self.db.delete(item)
        return True

    # ══════════════════════════════════════════════════════════════════
    # 本体同步触发
    # ══════════════════════════════════════════════════════════════════

    async def sync_to_neo4j(self, bom: BOMTemplate) -> None:
        """
        将 BOMTemplate 及其明细行同步到 Neo4j 本体层。
        在 session.commit() 后调用（同步驱动不需要 await）。
        """
        try:
            from src.ontology.data_sync import OntologyDataSync
            sync = OntologyDataSync()
            dish_id_str = f"DISH-{bom.dish_id}"

            sync.upsert_bom(
                dish_id=dish_id_str,
                version=bom.version,
                effective_date=bom.effective_date,
                yield_rate=float(bom.yield_rate),
                expiry_date=bom.expiry_date,
                notes=bom.notes,
            )

            for item in bom.items:
                ing_id_str = item.ingredient_id
                sync.upsert_bom_item(
                    dish_id=dish_id_str,
                    bom_version=bom.version,
                    ingredient_id=ing_id_str,
                    quantity=float(item.standard_qty),
                    unit=item.unit,
                )
            sync.close()
            logger.info("BOM 已同步到 Neo4j", bom_id=str(bom.id), version=bom.version)
        except Exception as e:
            # 同步失败不阻断业务，记录告警
            logger.warning("BOM Neo4j 同步失败（非致命）", error=str(e), bom_id=str(bom.id))
