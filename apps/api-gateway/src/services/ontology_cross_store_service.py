"""
跨店分析（Phase 3）：多门店损耗对比、连锁级 KPI 雏形
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Store
from src.ontology import get_ontology_repository
from src.services.waste_reasoning_service import run_waste_reasoning


async def cross_store_waste_comparison(
    session: AsyncSession,
    tenant_id: str,
    date_start: str,
    date_end: str,
    store_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    多门店损耗推理对比：按门店跑损耗五步推理，汇总 TOP3 根因与差异率等。
    store_ids 为空时从图谱或 PG 取该租户下所有门店。
    """
    if store_ids is None:
        # 从图谱取门店列表
        repo = get_ontology_repository()
        if repo:
            rows = repo.run_read_only_query(
                "MATCH (s:Store) RETURN s.store_id AS store_id, s.name AS name"
            )
            store_ids = [r["store_id"] for r in rows if r.get("store_id")]
        if not store_ids:
            # 从 PG 取
            q = select(Store.id).where(Store.id.isnot(None))
            result = await session.execute(q)
            store_ids = [str(r[0]) for r in result.all()]

    by_store: List[Dict[str, Any]] = []
    for sid in (store_ids or [])[:50]:
        try:
            report = await run_waste_reasoning(
                session,
                tenant_id=tenant_id,
                store_id=sid,
                date_start=date_start,
                date_end=date_end,
            )
            top3 = report.get("top3_root_causes") or []
            variances = report.get("step1_inventory_variance") or []
            by_store.append({
                "store_id": sid,
                "top3_root_causes": top3,
                "variance_count": len(variances),
                "max_diff_rate_pct": max((abs(v.get("diff_rate_pct", 0)) for v in variances) if variances else [0]),
            })
        except Exception:
            by_store.append({"store_id": sid, "error": "reasoning_failed", "top3_root_causes": [], "variance_count": 0, "max_diff_rate_pct": 0})

    return {
        "tenant_id": tenant_id,
        "date_start": date_start,
        "date_end": date_end,
        "stores": by_store,
        "comparison_summary": f"共 {len(by_store)} 个门店完成损耗推理对比",
    }
