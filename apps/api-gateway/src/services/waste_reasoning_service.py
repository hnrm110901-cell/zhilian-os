"""
损耗五步推理引擎（L3 推理层）
库存差异检测 → BOM 偏差计算 → 时间窗口关联员工 → 供应商批次定位 → 根因评分（TOP3）
输出带溯源的根因报告。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Schedule, Shift, PurchaseOrder, Order, OrderItem
from src.ontology import get_ontology_repository

logger = structlog.get_logger()


async def _step1_inventory_variance(
    store_id: str,
    date_start: str,
    date_end: str,
) -> List[Dict[str, Any]]:
    """步骤1：库存差异检测。按食材汇总期初/期末快照，计算差异量与差异率。"""
    repo = get_ontology_repository()
    if not repo:
        return []
    ts_start = date_start + "T00:00:00"
    ts_end = date_end + "T23:59:59"
    snapshots = repo.get_inventory_snapshots(store_id, ts_start, ts_end)
    by_ing: Dict[str, List[Dict]] = {}
    for s in snapshots:
        ing = s.get("ing_id", "")
        if ing not in by_ing:
            by_ing[ing] = []
        by_ing[ing].append(s)
    variances = []
    for ing_id, snaps in by_ing.items():
        if not snaps:
            continue
        snaps_sorted = sorted(snaps, key=lambda x: x.get("ts", ""))
        qty_first = float(snaps_sorted[0].get("qty", 0))
        qty_last = float(snaps_sorted[-1].get("qty", 0))
        diff = qty_last - qty_first
        rate = (diff / qty_first * 100) if qty_first else 0
        variances.append({
            "ing_id": ing_id,
            "qty_start": qty_first,
            "qty_end": qty_last,
            "diff": diff,
            "diff_rate_pct": round(rate, 2),
            "trace": [snaps_sorted[0].get("ts"), snaps_sorted[-1].get("ts")],
        })
    return variances


async def _step2_bom_deviation(
    session: AsyncSession,
    store_id: str,
    date_start: str,
    date_end: str,
    variances: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """步骤2：BOM 偏差计算。实际消耗 vs 标准用量×销量，标异常。"""
    repo = get_ontology_repository()
    if not repo:
        return []
    deviations = []
    for v in variances:
        ing_id = v.get("ing_id", "")
        actual_consumption = abs(v.get("diff", 0))  # 简化：用库存变化量作为实际消耗
        # 从图谱取该食材被哪些 BOM 使用
        with repo.session() as neo_session:
            r = neo_session.run(
                """
                MATCH (b:BOM)-[r:REQUIRES]->(i:Ingredient { ing_id: $ing_id })
                WHERE b.store_id = $store_id
                RETURN b.dish_id AS dish_id, r.qty AS std_qty, r.unit AS unit
                """,
                ing_id=ing_id,
                store_id=store_id,
            )
            bom_rows = [dict(rec) for rec in r]
        if not bom_rows:
            deviations.append({
                "ing_id": ing_id,
                "actual": actual_consumption,
                "expected": 0,
                "deviation": actual_consumption,
                "anomaly": actual_consumption > 0,
                "trace": "无BOM关联",
            })
            continue
        # 简化：预期用量用 BOM 标准量之和的某个倍数（无订单时用 0）
        expected = 0.0
        try:
            dt_start = datetime.fromisoformat(date_start + "T00:00:00")
            dt_end = datetime.fromisoformat(date_end + "T23:59:59")
            for row in bom_rows:
                dish_id = row.get("dish_id")
                std_qty = float(row.get("std_qty", 0))
                q = select(OrderItem).join(Order, OrderItem.order_id == Order.id).where(
                    Order.store_id == store_id,
                    Order.order_time >= dt_start,
                    Order.order_time <= dt_end,
                    OrderItem.item_id == str(dish_id),
                )
                res = await session.execute(q)
                items = res.scalars().all()
                sales = sum(getattr(it, "quantity", 0) or 0 for it in items)
                expected += std_qty * sales
        except Exception as e:
            logger.debug("waste_reasoning_bom_expected_skip", ing_id=ing_id, error=str(e))
        dev = actual_consumption - expected
        deviations.append({
            "ing_id": ing_id,
            "actual": actual_consumption,
            "expected": expected,
            "deviation": dev,
            "anomaly": abs(dev) > (expected * 0.2 if expected else 0),
            "trace": [row.get("dish_id") for row in bom_rows],
        })
    return deviations


async def _step3_time_window_staff(
    session: AsyncSession,
    store_id: str,
    date_start: str,
    date_end: str,
) -> List[Dict[str, Any]]:
    """步骤3：时间窗口关联排班，得到候选员工列表。"""
    q = (
        select(Shift, Schedule)
        .join(Schedule, Shift.schedule_id == Schedule.id)
        .where(
            Schedule.store_id == store_id,
            Schedule.schedule_date >= date_start,
            Schedule.schedule_date <= date_end,
        )
    )
    result = await session.execute(q)
    rows = result.all()
    staff_ids = set()
    for shift, sched in rows:
        staff_ids.add(shift.employee_id)
    return [{"staff_id": sid, "trace": "排班表"} for sid in staff_ids]


async def _step4_supplier_batch(
    session: AsyncSession,
    store_id: str,
    ing_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """步骤4：异常食材关联采购记录与供应商。"""
    q = select(PurchaseOrder).where(
        PurchaseOrder.store_id == store_id,
        PurchaseOrder.status.in_(["delivered", "completed", "ordered"]),
    )
    result = await session.execute(q)
    pos = result.scalars().all()
    batches = []
    for po in pos:
        items = getattr(po, "items", None) or []
        for it in items:
            if isinstance(it, dict):
                it_ing = it.get("ingredient_id") or it.get("ing_id") or it.get("material_id")
            else:
                it_ing = getattr(it, "ingredient_id", None) or getattr(it, "ing_id", None)
            if ing_id and str(it_ing) != str(ing_id):
                continue
            ed = getattr(po, "expected_delivery", None)
            batches.append({
                "supplier_id": po.supplier_id,
                "order_id": po.id,
                "ing_id": it_ing,
                "trace": ed.isoformat() if ed else str(po.id),
            })
    return batches[:20]


def _step5_root_cause_score(
    variances: List[Dict],
    deviations: List[Dict],
    staff: List[Dict],
    batches: List[Dict],
) -> List[Dict[str, Any]]:
    """步骤5：四维度根因评分，输出 TOP3。"""
    candidates: List[Dict[str, Any]] = []
    for v in variances:
        if abs(v.get("diff_rate_pct", 0)) > 10:
            candidates.append({
                "dimension": "inventory_variance",
                "ing_id": v.get("ing_id"),
                "score": min(100, abs(v.get("diff_rate_pct", 0)) * 2),
                "reason": f"库存变化率 {v.get('diff_rate_pct')}%",
                "trace": v.get("trace", []),
            })
    for d in deviations:
        if d.get("anomaly"):
            candidates.append({
                "dimension": "bom_deviation",
                "ing_id": d.get("ing_id"),
                "score": 70,
                "reason": f"BOM偏差 实际{d.get('actual')} vs 预期{d.get('expected')}",
                "trace": d.get("trace", []),
            })
    for s in staff[:5]:
        candidates.append({
            "dimension": "time_window_staff",
            "staff_id": s.get("staff_id"),
            "score": 40,
            "reason": "当班员工",
            "trace": s.get("trace", []),
        })
    for b in batches[:3]:
        candidates.append({
            "dimension": "supplier_batch",
            "supplier_id": b.get("supplier_id"),
            "score": 50,
            "reason": "近期采购批次",
            "trace": b.get("trace", []),
        })
    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    return candidates[:3]


async def run_waste_reasoning(
    session: AsyncSession,
    tenant_id: str,
    store_id: str,
    date_start: str,
    date_end: Optional[str] = None,
) -> Dict[str, Any]:
    """
    执行损耗五步推理，返回带溯源的根因报告。
    date_start/date_end: YYYY-MM-DD
    """
    if not date_end:
        date_end = date_start
    variances = await _step1_inventory_variance(store_id, date_start, date_end)
    deviations = await _step2_bom_deviation(session, store_id, date_start, date_end, variances)
    staff = await _step3_time_window_staff(session, store_id, date_start, date_end)
    batches = await _step4_supplier_batch(session, store_id, None)
    top3 = _step5_root_cause_score(variances, deviations, staff, batches)

    # 将 TOP3 根因写入图谱 WasteEvent 节点并关联 Staff（溯源）
    repo = get_ontology_repository()
    if repo and top3:
        for i, cause in enumerate(top3):
            event_id = f"waste_{store_id}_{date_start}_{i}"
            repo.merge_waste_event(
                event_id=event_id,
                store_id=store_id,
                event_type=cause.get("dimension", "waste"),
                amount=0,
                root_cause=cause.get("reason", ""),
                staff_id=cause.get("staff_id"),
                ing_id=cause.get("ing_id"),
                tenant_id=tenant_id,
            )

    # 触发培训推荐分发：为每个根因维度向当班员工推送针对性培训
    affected_staff_ids = [s.get("staff_id") for s in staff if s.get("staff_id")]
    if top3:
        try:
            from src.core.celery_tasks import dispatch_training_recommendation
            for i, cause in enumerate(top3):
                dimension = cause.get("dimension", "")
                if dimension:
                    dispatch_training_recommendation.delay(
                        store_id=store_id,
                        tenant_id=tenant_id,
                        root_cause_dimension=dimension,
                        affected_staff_ids=affected_staff_ids,
                        waste_event_id=f"waste_{store_id}_{date_start}_{i}",
                    )
        except Exception as dispatch_err:
            logger.warning(
                "waste_training_dispatch_trigger_failed",
                store_id=store_id,
                error=str(dispatch_err),
            )

    return {
        "tenant_id": tenant_id,
        "store_id": store_id,
        "date_start": date_start,
        "date_end": date_end,
        "step1_inventory_variance": variances,
        "step2_bom_deviation": deviations,
        "step3_staff_in_window": staff,
        "step4_supplier_batches": batches[:10],
        "top3_root_causes": top3,
    }
