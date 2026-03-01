"""
PostgreSQL → Neo4j 本体同步管道（Palantir Fusion Layer 实现）

机制：
  - 使用 SQLAlchemy after_flush_postexec 事件监听 Session 变更
  - 拦截 BOMTemplate / BOMItem / Dish / InventoryItem 的 INSERT / UPDATE
  - 异步后台任务写入 Neo4j（不阻断 HTTP 响应）
  - 幂等 MERGE：重复触发安全

使用方式：
  在 startup_event 中调用 register_sync_listeners(engine) 完成注册
"""

import asyncio
import structlog
from typing import Set
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine
from sqlalchemy.orm import Session

from src.models.bom import BOMTemplate, BOMItem
from src.models.dish import Dish
from src.models.inventory import InventoryItem

logger = structlog.get_logger()


# ── 待同步队列（内存级，per-session） ────────────────────────────────────────

class _SyncQueue:
    """跟踪一个 SQLAlchemy Session 中需要同步到 Neo4j 的对象"""

    def __init__(self):
        self.bom_ids: Set[str] = set()
        self.dish_ids: Set[str] = set()
        self.ingredient_ids: Set[str] = set()


# ── 同步执行函数 ──────────────────────────────────────────────────────────────

def _sync_bom(bom_id: str) -> None:
    """将单个 BOM（含明细）同步到 Neo4j（同步驱动）"""
    try:
        from src.ontology.data_sync import OntologyDataSync
        # 由于此处在同步上下文，需要创建新的同步 DB session
        from src.core.database import sync_session_factory  # type: ignore[import]

        with sync_session_factory() as db:
            from sqlalchemy.orm import joinedload
            from src.models.bom import BOMTemplate
            bom = db.query(BOMTemplate).options(
                joinedload(BOMTemplate.items)
            ).filter(BOMTemplate.id == bom_id).first()

            if not bom:
                return

            with OntologyDataSync() as sync:
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
                    sync.upsert_bom_item(
                        dish_id=dish_id_str,
                        bom_version=bom.version,
                        ingredient_id=item.ingredient_id,
                        quantity=float(item.standard_qty),
                        unit=item.unit,
                    )
        logger.info("BOM 同步管道完成", bom_id=bom_id)
    except Exception as e:
        logger.warning("BOM 同步管道失败（非致命）", bom_id=bom_id, error=str(e))


def _sync_dish(dish_id: str) -> None:
    """将单个 Dish 节点同步到 Neo4j"""
    try:
        from src.ontology.data_sync import OntologyDataSync
        from src.core.database import sync_session_factory  # type: ignore[import]

        with sync_session_factory() as db:
            from src.models.dish import Dish
            dish = db.query(Dish).filter(Dish.id == dish_id).first()
            if not dish:
                return

            with OntologyDataSync() as sync:
                sync.upsert_dish(
                    dish_id=f"DISH-{dish.id}",
                    name=dish.name,
                    category=dish.category.name if dish.category else "未分类",
                    price=float(dish.price),
                    store_id=dish.store_id,
                )
        logger.info("Dish 同步管道完成", dish_id=dish_id)
    except Exception as e:
        logger.warning("Dish 同步管道失败（非致命）", dish_id=dish_id, error=str(e))


def _sync_ingredient(ing_id: str) -> None:
    """将单个食材节点同步到 Neo4j"""
    try:
        from src.ontology.data_sync import OntologyDataSync
        from src.core.database import sync_session_factory  # type: ignore[import]

        with sync_session_factory() as db:
            from src.models.inventory import InventoryItem
            ing = db.query(InventoryItem).filter(InventoryItem.id == ing_id).first()
            if not ing:
                return

            with OntologyDataSync() as sync:
                sync.upsert_ingredient(
                    ing_id=ing.id,
                    name=ing.name,
                    category=ing.category or "其他",
                    unit_type=ing.unit or "克",
                    external_ids={"postgres_id": ing.id},
                )
        logger.info("食材同步管道完成", ing_id=ing_id)
    except Exception as e:
        logger.warning("食材同步管道失败（非致命）", ing_id=ing_id, error=str(e))


# ── SQLAlchemy 事件监听器 ─────────────────────────────────────────────────────

def register_sync_listeners(session_factory) -> None:
    """
    注册 SQLAlchemy Session 级别的 after_flush 监听器。

    在 startup_event 中调用一次：
        register_sync_listeners(async_session_factory)
    """

    @event.listens_for(session_factory, "after_flush_postexec")
    def _on_flush(session: Session, flush_context):
        """拦截 flush 后的新增/修改对象，投递到后台同步队列"""
        bom_ids = set()
        dish_ids = set()
        ing_ids = set()

        for obj in list(session.new) + list(session.dirty):
            if isinstance(obj, BOMTemplate):
                bom_ids.add(str(obj.id))
            elif isinstance(obj, BOMItem):
                # BOMItem 变更 → 触发父 BOM 同步
                bom_ids.add(str(obj.bom_id))
            elif isinstance(obj, Dish):
                dish_ids.add(str(obj.id))
            elif isinstance(obj, InventoryItem):
                ing_ids.add(str(obj.id))

        if bom_ids or dish_ids or ing_ids:
            # 在后台线程中执行 Neo4j 写入（不阻断业务）
            _dispatch_async_sync(bom_ids, dish_ids, ing_ids)


def _dispatch_async_sync(
    bom_ids: Set[str],
    dish_ids: Set[str],
    ing_ids: Set[str],
) -> None:
    """将同步任务投递到事件循环（非阻塞）"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.run_in_executor(
                None,
                _run_sync_batch,
                list(bom_ids),
                list(dish_ids),
                list(ing_ids),
            )
        else:
            _run_sync_batch(list(bom_ids), list(dish_ids), list(ing_ids))
    except Exception as e:
        logger.warning("同步投递失败", error=str(e))


def _run_sync_batch(
    bom_ids: list,
    dish_ids: list,
    ing_ids: list,
) -> None:
    """批量执行 Neo4j 同步（在线程池中运行）"""
    for bid in bom_ids:
        _sync_bom(bid)
    for did in dish_ids:
        _sync_dish(did)
    for iid in ing_ids:
        _sync_ingredient(iid)
