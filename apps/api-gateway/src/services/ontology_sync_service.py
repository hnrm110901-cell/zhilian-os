"""
本体同步服务：从 PostgreSQL 主数据同步到 Neo4j 图谱（L2 本体层）
Phase 1：Store、Dish、Ingredient（InventoryItem）同步；P1：Order、Staff（Employee）同步。
BOM 双向同步：图谱 BOM 变更后回写 PG Dish.bom_version / effective_date。
Phase 3：门店同步后自动计算 SIMILAR_TO 相似度关系（同城市/同地区/规模相近）。
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Store, Dish, DishCategory, InventoryItem, Order, OrderItem, Employee
from src.ontology import get_ontology_repository, NodeLabel, RelType

# InventoryItem.id 作为 ing_id；Store.id 作为 store_id；Dish.id 转为 str 作为 dish_id


async def sync_stores_to_graph(
    session: AsyncSession,
    tenant_id: str,
    store_ids: Optional[list[str]] = None,
) -> int:
    """将门店从 PG 同步到图谱，含 city/region/area/seats 属性。同步后自动计算 SIMILAR_TO 关系。"""
    repo = get_ontology_repository()
    if not repo:
        return 0
    q = select(Store)
    if store_ids:
        q = q.where(Store.id.in_(store_ids))
    result = await session.execute(q)
    stores = result.scalars().all()
    count = 0
    for s in stores:
        props: dict = {"name": s.name or "", "tenant_id": tenant_id}
        if getattr(s, "city", None):
            props["city"] = s.city
        if getattr(s, "region", None):
            props["region"] = s.region
        if getattr(s, "area", None) is not None:
            props["area"] = float(s.area)
        if getattr(s, "seats", None) is not None:
            props["seats"] = int(s.seats)
        repo.merge_node(
            NodeLabel.Store.value,
            "store_id",
            s.id,
            props,
            tenant_id=tenant_id,
        )
        count += 1

    # Phase 3: 同步完成后自动计算相似门店关系
    if count > 1:
        _compute_store_similarities(stores, repo)

    return count


def _compute_store_similarities(stores: list, repo) -> None:
    """
    基于 city / region / area / seats 自动计算门店间相似度，写入 SIMILAR_TO 关系。

    相似度规则（取最高命中分）：
    - 同城市（city 相同）：score = 0.9，reason = "city"
    - 同地区、不同城市（region 相同）：score = 0.7，reason = "region"
    - 规模相近（area 相差 ≤30% 且 seats 相差 ≤20%）：额外 +0.1

    得分 ≥ 0.5 才写入关系，避免无关门店误连。
    """
    import itertools

    for a, b in itertools.combinations(stores, 2):
        sid_a, sid_b = str(a.id), str(b.id)
        city_a = getattr(a, "city", None) or ""
        city_b = getattr(b, "city", None) or ""
        region_a = getattr(a, "region", None) or ""
        region_b = getattr(b, "region", None) or ""
        area_a = float(getattr(a, "area", None) or 0)
        area_b = float(getattr(b, "area", None) or 0)
        seats_a = int(getattr(a, "seats", None) or 0)
        seats_b = int(getattr(b, "seats", None) or 0)

        score = 0.0
        reason = ""
        if city_a and city_b and city_a == city_b:
            score, reason = 0.9, "city"
        elif region_a and region_b and region_a == region_b:
            score, reason = 0.7, "region"

        # 规模相近加权
        if score > 0:
            area_similar = (
                area_a > 0 and area_b > 0
                and abs(area_a - area_b) / max(area_a, area_b) <= 0.3
            )
            seats_similar = (
                seats_a > 0 and seats_b > 0
                and abs(seats_a - seats_b) / max(seats_a, seats_b) <= 0.2
            )
            if area_similar or seats_similar:
                score = min(1.0, score + 0.1)
                reason = reason + "+scale"

        if score >= 0.5:
            try:
                repo.merge_store_similarity(
                    store_id_a=sid_a,
                    store_id_b=sid_b,
                    similarity_score=round(score, 2),
                    reason=reason,
                )
            except Exception as e:
                import structlog
                structlog.get_logger().warning(
                    "store_similarity_compute_failed",
                    store_a=sid_a, store_b=sid_b, error=str(e),
                )


async def sync_dishes_to_graph(
    session: AsyncSession,
    tenant_id: str,
    store_id: Optional[str] = None,
) -> int:
    """将菜品从 PG 同步到图谱（Dish 节点）。"""
    repo = get_ontology_repository()
    if not repo:
        return 0
    q = select(Dish)
    if store_id:
        q = q.where(Dish.store_id == store_id)
    result = await session.execute(q)
    dishes = result.scalars().all()
    count = 0
    for d in dishes:
        props = {
            "name": d.name or "",
            "store_id": d.store_id or "",
            "tenant_id": tenant_id,
        }
        if getattr(d, "bom_version", None):
            props["bom_version"] = d.bom_version
        if getattr(d, "effective_date", None):
            props["effective_date"] = d.effective_date.isoformat()
        repo.merge_node(
            NodeLabel.Dish.value,
            "dish_id",
            str(d.id),
            props,
            tenant_id=tenant_id,
        )
        count += 1
    return count


async def sync_ingredients_to_graph(
    session: AsyncSession,
    tenant_id: str,
    store_id: Optional[str] = None,
) -> int:
    """将库存品项（食材）从 PG 同步到图谱（Ingredient 节点）。"""
    repo = get_ontology_repository()
    if not repo:
        return 0
    q = select(InventoryItem)
    if store_id:
        q = q.where(InventoryItem.store_id == store_id)
    result = await session.execute(q)
    items = result.scalars().all()
    count = 0
    for i in items:
        repo.merge_node(
            NodeLabel.Ingredient.value,
            "ing_id",
            i.id,
            {
                "name": i.name or "",
                "unit": i.unit or "",
                "store_id": i.store_id or "",
                "tenant_id": tenant_id,
            },
            tenant_id=tenant_id,
        )
        count += 1
    return count


async def sync_staff_to_graph(
    session: AsyncSession,
    tenant_id: str,
    store_id: Optional[str] = None,
) -> int:
    """将员工（Employee）从 PG 同步到图谱（Staff 节点），并建立 Staff -[:BELONGS_TO]-> Store。"""
    repo = get_ontology_repository()
    if not repo:
        return 0
    q = select(Employee).where(Employee.is_active == True)
    if store_id:
        q = q.where(Employee.store_id == store_id)
    result = await session.execute(q)
    employees = result.scalars().all()
    count = 0
    for e in employees:
        repo.merge_node(
            NodeLabel.Staff.value,
            "staff_id",
            e.id,
            {
                "name": e.name or "",
                "role": (e.position or ""),
                "store_id": e.store_id or "",
                "tenant_id": tenant_id,
            },
            tenant_id=tenant_id,
        )
        if e.store_id:
            repo.merge_relation(
                NodeLabel.Staff.value, "staff_id", e.id,
                RelType.BELONGS_TO.value,
                NodeLabel.Store.value, "store_id", e.store_id,
            )
        count += 1
    return count


async def sync_orders_to_graph(
    session: AsyncSession,
    tenant_id: str,
    store_id: Optional[str] = None,
) -> int:
    """将订单从 PG 同步到图谱（Order 节点），建立 Order -[:BELONGS_TO]-> Store，Order -[:CONTAINS {quantity}]-> Dish。"""
    repo = get_ontology_repository()
    if not repo:
        return 0
    q = select(Order).options(selectinload(Order.items))
    if store_id:
        q = q.where(Order.store_id == store_id)
    result = await session.execute(q)
    orders = result.scalars().all()
    count = 0
    for o in orders:
        ts = o.order_time.isoformat() if getattr(o.order_time, "isoformat", None) else str(o.order_time or "")
        repo.merge_node(
            NodeLabel.Order.value,
            "order_id",
            o.id,
            {
                "store_id": o.store_id or "",
                "status": o.status or "",
                "timestamp": ts,
                "tenant_id": tenant_id,
            },
            tenant_id=tenant_id,
        )
        if o.store_id:
            repo.merge_relation(
                NodeLabel.Order.value, "order_id", o.id,
                RelType.BELONGS_TO.value,
                NodeLabel.Store.value, "store_id", o.store_id,
            )
        for item in o.items or []:
            # item_id 视为 dish_id（与 Dish 节点关联）
            dish_id = str(item.item_id)
            repo.merge_relation(
                NodeLabel.Order.value, "order_id", o.id,
                RelType.CONTAINS.value,
                NodeLabel.Dish.value, "dish_id", dish_id,
                rel_props={"quantity": getattr(item, "quantity", 1)},
            )
        count += 1
    return count


async def sync_ontology_from_pg(
    session: AsyncSession,
    tenant_id: str,
    store_id: Optional[str] = None,
) -> dict:
    """统一入口：同步 Store、Dish、Ingredient、Staff、Order 到图谱。"""
    stores_n = await sync_stores_to_graph(
        session, tenant_id,
        store_ids=[store_id] if store_id else None,
    )
    dishes_n = await sync_dishes_to_graph(session, tenant_id, store_id)
    ingredients_n = await sync_ingredients_to_graph(session, tenant_id, store_id)
    staff_n = await sync_staff_to_graph(session, tenant_id, store_id)
    orders_n = await sync_orders_to_graph(session, tenant_id, store_id)
    return {
        "stores": stores_n,
        "dishes": dishes_n,
        "ingredients": ingredients_n,
        "staff": staff_n,
        "orders": orders_n,
    }


def push_normalized_order_to_graph(
    tenant_id: str,
    store_id: str,
    order_id: str,
    order_time_iso: str,
    status: str,
    items: list,
) -> bool:
    """
    L1 感知层 → 图谱：将已标准化的订单写入 Neo4j（Order 节点 + BELONGS_TO Store + CONTAINS Dish）。
    供 POS Webhook、品智拉取等管道在写入 PG 后调用。
    items: [{"item_id": dish_id, "quantity": n}, ...]
    """
    repo = get_ontology_repository()
    if not repo:
        return False
    repo.merge_node(
        NodeLabel.Order.value,
        "order_id",
        order_id,
        {
            "store_id": store_id,
            "status": status,
            "timestamp": order_time_iso,
            "tenant_id": tenant_id,
        },
        tenant_id=tenant_id,
    )
    repo.merge_relation(
        NodeLabel.Order.value, "order_id", order_id,
        RelType.BELONGS_TO.value,
        NodeLabel.Store.value, "store_id", store_id,
    )
    for it in items:
        dish_id = str(it.get("item_id") or it.get("dish_id") or "")
        if not dish_id:
            continue
        qty = int(it.get("quantity", 1))
        repo.merge_relation(
            NodeLabel.Order.value, "order_id", order_id,
            RelType.CONTAINS.value,
            NodeLabel.Dish.value, "dish_id", dish_id,
            rel_props={"quantity": qty},
        )
    return True


async def sync_bom_version_to_pg(
    session: AsyncSession,
    dish_id: str,
    version: int,
    effective_date: str,
) -> bool:
    """
    BOM 双向同步：将图谱侧 BOM 的 version / effective_date 回写到 PG Dish。
    在 POST /ontology/bom/upsert 成功后调用，保证 PG 与图谱一致。
    """
    if not dish_id or not effective_date:
        return False
    try:
        uid = UUID(dish_id) if isinstance(dish_id, str) and len(dish_id) == 36 else None
        if uid is None:
            return False
        eff_date = date.fromisoformat(effective_date)
        stmt = (
            update(Dish)
            .where(Dish.id == uid)
            .values(bom_version=str(version), effective_date=eff_date)
        )
        result = await session.execute(stmt)
        return result.rowcount > 0
    except (ValueError, TypeError):
        return False
