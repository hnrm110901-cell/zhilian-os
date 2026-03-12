"""
Task3B: BOMResolverService — 多层 BOM 继承解析器

解析优先级（scope）：store > region > brand > group
Delta BOM 按 group→brand→region→store→channel 顺序叠加：
  ADD / OVERRIDE → 更新 working_items[ingredient_id]
  REMOVE         → 删除 working_items[ingredient_id]

现有 BOMTemplate（scope='store', is_delta=False by server_default）
自动被识别为 store-level base BOM，无需数据迁移。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional
import inspect

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.bom import BOMItem, BOMTemplate
from src.models.store import Store

logger = structlog.get_logger()

# 优先级映射：数字越小优先级越高
_SCOPE_PRIORITY = {"store": 0, "region": 1, "brand": 2, "group": 3}
# Delta 叠加顺序（从粗到细）
_DELTA_SCOPE_ORDER = ["group", "brand", "region", "store", "channel"]


@dataclass
class ResolvedBOMItem:
    """解析后的单行 BOM 食材数据"""
    ingredient_id: str
    ingredient_master_id: Optional[str]
    standard_qty: Decimal
    unit: str
    unit_cost: int  # 分/单位，0 表示未知

    @property
    def line_cost_fen(self) -> Decimal:
        return self.standard_qty * self.unit_cost


@dataclass
class ResolvedBOM:
    """完整解析结果（继承链叠加后的最终 BOM）"""
    dish_id: str
    store_id: str
    channel: Optional[str]
    items: List[ResolvedBOMItem] = field(default_factory=list)
    source_bom_ids: List[str] = field(default_factory=list)

    @property
    def total_bom_cost_fen(self) -> Decimal:
        """所有食材行成本之和（分）"""
        return sum(item.line_cost_fen for item in self.items)


def _item_to_resolved(item: BOMItem) -> ResolvedBOMItem:
    return ResolvedBOMItem(
        ingredient_id=str(item.ingredient_id),
        ingredient_master_id=item.ingredient_master_id,
        standard_qty=Decimal(str(item.standard_qty)),
        unit=item.unit,
        unit_cost=item.unit_cost or 0,
    )


def _find_base_bom(
    templates: List[BOMTemplate],
    store: Store,
    channel: Optional[str],
) -> Optional[BOMTemplate]:
    """
    从候选 BOMTemplate 列表中选出最佳 base BOM（is_delta=False）。
    优先级：store > region > brand > group
    """
    candidates = [t for t in templates if not t.is_delta]
    if not candidates:
        return None

    def _priority(t: BOMTemplate) -> int:
        scope = t.scope or "group"
        base = _SCOPE_PRIORITY.get(scope, 99)
        # scope_id 匹配加权
        if scope == "store" and t.scope_id and t.scope_id == store.id:
            return 0
        if scope == "region" and t.scope_id and t.scope_id == getattr(store, "region", None):
            return 1
        if scope == "brand" and t.scope_id and t.scope_id == getattr(store, "brand_id", None):
            return 2
        if scope == "group":
            return 3
        # scope 匹配但 scope_id 不精确
        return base + 10

    candidates.sort(key=_priority)
    return candidates[0]


def _collect_deltas(
    templates: List[BOMTemplate],
    store: Store,
    channel: Optional[str],
) -> List[BOMTemplate]:
    """
    按叠加顺序收集 delta BOM（is_delta=True）。
    顺序：group → brand → region → store → channel
    """
    deltas: List[BOMTemplate] = [t for t in templates if t.is_delta]

    def _delta_order(t: BOMTemplate) -> int:
        scope = t.scope or "group"
        if scope == "channel":
            return 40
        return _DELTA_SCOPE_ORDER.index(scope) if scope in _DELTA_SCOPE_ORDER else 99

    deltas.sort(key=_delta_order)
    return deltas


class BOMResolverService:
    """
    多层 BOM 继承解析器（全静态方法，无状态）

    典型调用：
        resolved = await BOMResolverService.resolve(session, dish_id, store_id)
        cost = resolved.total_bom_cost_fen
    """

    @staticmethod
    async def resolve(
        session: AsyncSession,
        dish_id: str,
        store_id: str,
        channel: Optional[str] = None,
    ) -> ResolvedBOM:
        """
        解析指定菜品在指定门店（和渠道）的最终 BOM。

        1. 查 stores 表取 brand_id / region
        2. 查所有 active BOMTemplate for dish_id（eager load items）
        3. 选出 base BOM（优先级：store > region > brand > group）
        4. 收集 delta BOM 并按 group→brand→region→store→channel 顺序叠加
        5. Apply deltas: ADD/OVERRIDE→更新, REMOVE→删除
        6. 返回 ResolvedBOM
        """
        # 1. 取 Store 信息
        store_result = await session.execute(
            select(Store).where(Store.id == store_id)
        )
        store: Optional[Store] = await _maybe_await(store_result.scalar_one_or_none())
        if store is None:
            logger.warning("bom_resolver_store_not_found", store_id=store_id)
            return ResolvedBOM(dish_id=str(dish_id), store_id=store_id, channel=channel)

        # 2. 查所有 active BOMTemplate（含 items）
        templates_result = await session.execute(
            select(BOMTemplate)
            .where(
                BOMTemplate.dish_id == dish_id,
                BOMTemplate.is_active == True,  # noqa: E712
            )
            .options(selectinload(BOMTemplate.items))
        )
        templates_scalars = templates_result.scalars()
        templates_all = await _maybe_await(templates_scalars.all())
        templates: List[BOMTemplate] = list(templates_all)

        if not templates:
            logger.debug("bom_resolver_no_templates", dish_id=str(dish_id), store_id=store_id)
            return ResolvedBOM(dish_id=str(dish_id), store_id=store_id, channel=channel)

        # 3. 选 base BOM
        base = _find_base_bom(templates, store, channel)
        if base is None:
            return ResolvedBOM(dish_id=str(dish_id), store_id=store_id, channel=channel)

        # 4. 初始化 working_items（ingredient_id → ResolvedBOMItem）
        working_items: Dict[str, ResolvedBOMItem] = {
            str(item.ingredient_id): _item_to_resolved(item)
            for item in base.items
        }
        source_ids = [str(base.id)]

        # 5. 叠加 delta BOMs
        deltas = _collect_deltas(templates, store, channel)
        for delta in deltas:
            # 渠道 delta 仅在 channel 参数匹配时应用
            if delta.scope == "channel" and delta.channel and delta.channel != channel:
                continue
            source_ids.append(str(delta.id))
            for item in delta.items:
                ing_id = str(item.ingredient_id)
                action = (item.item_action or "ADD").upper()
                if action in ("ADD", "OVERRIDE"):
                    working_items[ing_id] = _item_to_resolved(item)
                elif action == "REMOVE":
                    working_items.pop(ing_id, None)

        return ResolvedBOM(
            dish_id=str(dish_id),
            store_id=store_id,
            channel=channel,
            items=list(working_items.values()),
            source_bom_ids=source_ids,
        )

    @staticmethod
    async def get_theoretical_qty(
        session: AsyncSession,
        dish_id: str,
        store_id: str,
        ingredient_id: str,
        channel: Optional[str] = None,
    ) -> Decimal:
        """
        返回指定菜品在指定门店的特定食材标准用量（Decimal）。
        未找到 BOM 或食材不在配方中时返回 Decimal("0")，不抛异常。
        """
        try:
            resolved = await BOMResolverService.resolve(session, dish_id, store_id, channel)
            for item in resolved.items:
                if item.ingredient_id == str(ingredient_id):
                    return item.standard_qty
        except Exception as e:
            logger.warning(
                "bom_resolver_get_theoretical_qty_error",
                dish_id=str(dish_id),
                store_id=store_id,
                ingredient_id=str(ingredient_id),
                error=str(e),
            )
        return Decimal("0")


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value
