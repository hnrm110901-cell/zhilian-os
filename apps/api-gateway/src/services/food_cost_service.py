"""
食材成本分析服务

提供三个核心分析能力：
  1. BOM 版本标准食材成本报告
  2. 门店实际 vs 理论食材成本差异分析
  3. 总部跨店食材成本排名
"""

from datetime import date, timedelta
from typing import Optional

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dish import Dish
from src.models.store import Store
from src.services.bom_service import BOMService

logger = structlog.get_logger()


class FoodCostService:

    @staticmethod
    async def get_bom_cost_report(bom_id: str, db: AsyncSession) -> Optional[dict]:
        """计算 BOM 版本的标准食材成本报告"""
        svc = BOMService(db)
        bom = await svc.get_bom(bom_id)
        if not bom:
            return None

        dish = await db.get(Dish, bom.dish_id)
        price_yuan = float(dish.price) if dish and dish.price else 0.0

        total_cost_fen = 0.0
        items = []
        for item in (bom.items or []):
            uc = item.unit_cost or 0
            qty = float(item.standard_qty)
            item_cost_fen = qty * uc
            total_cost_fen += item_cost_fen
            items.append({
                "ingredient_id": item.ingredient_id,
                "standard_qty": qty,
                "unit": item.unit,
                "unit_cost_fen": uc,
                "item_cost_fen": item_cost_fen,
                "item_cost_yuan": round(item_cost_fen / 100, 2),
                "cost_pct": 0.0,
            })

        # 按成本贡献降序
        items.sort(key=lambda x: x["item_cost_fen"], reverse=True)

        # 计算各食材占比
        for it in items:
            it["cost_pct"] = round(it["item_cost_fen"] / total_cost_fen * 100, 2) if total_cost_fen > 0 else 0.0

        # food_cost_pct = total_cost_fen / (price_yuan * 100) * 100
        food_cost_pct = round(total_cost_fen / (price_yuan * 100) * 100, 2) if price_yuan > 0 else 0.0

        return {
            "bom_id": str(bom.id),
            "dish_id": str(bom.dish_id),
            "version": bom.version,
            "total_cost_fen": total_cost_fen,
            "total_cost_yuan": round(total_cost_fen / 100, 2),
            "price_yuan": price_yuan,
            "food_cost_pct": food_cost_pct,
            "items": items,
        }

    @staticmethod
    async def get_store_food_cost_variance(
        store_id: str, start_date: date, end_date: date, db: AsyncSession
    ) -> dict:
        """门店实际 vs 理论食材成本差异分析"""
        end_exclusive = end_date + timedelta(days=1)

        # SQL 1: 实际用料成本（分）
        r1 = await db.execute(
            text(
                "SELECT COALESCE(ABS(SUM(total_cost)), 0) AS actual_cost "
                "FROM inventory_transactions "
                "WHERE store_id = :sid "
                "  AND transaction_type = 'usage' "
                "  AND transaction_time >= :start "
                "  AND transaction_time < :end"
            ),
            {"sid": store_id, "start": start_date, "end": end_exclusive},
        )
        actual_cost_fen = float(r1.scalar() or 0)

        # SQL 2: 实际收入（分）
        r2 = await db.execute(
            text(
                "SELECT COALESCE(SUM(total_amount), 0) AS revenue "
                "FROM orders "
                "WHERE store_id = :sid "
                "  AND created_at >= :start "
                "  AND created_at < :end"
            ),
            {"sid": store_id, "start": start_date, "end": end_exclusive},
        )
        revenue_fen = float(r2.scalar() or 0)

        # SQL 3: 理论食材成本率（BOM × dish 价格）
        r3 = await db.execute(
            text(
                "SELECT b.id, d.price, "
                "       COALESCE(SUM(bi.standard_qty * bi.unit_cost), 0) AS computed_cost "
                "FROM bom_templates b "
                "LEFT JOIN bom_items bi ON bi.bom_id = b.id "
                "LEFT JOIN dishes d ON b.dish_id = d.id "
                "WHERE b.store_id = :sid "
                "  AND b.is_active = true "
                "GROUP BY b.id, d.price"
            ),
            {"sid": store_id},
        )
        rows3 = r3.fetchall()

        theoretical_pcts = []
        for row in rows3:
            price_yuan = float(row.price) if row.price else 0.0
            computed_cost = float(row.computed_cost) if row.computed_cost else 0.0
            if price_yuan > 0:
                pct = computed_cost / (price_yuan * 100) * 100
                theoretical_pcts.append(pct)

        theoretical_pct = round(sum(theoretical_pcts) / len(theoretical_pcts), 2) if theoretical_pcts else 0.0

        # 实际食材成本率
        actual_pct = round(actual_cost_fen / revenue_fen * 100, 2) if revenue_fen > 0 else 0.0

        # 差异 = 实际 - 理论
        variance_pct = round(actual_pct - theoretical_pct, 2)

        # 状态分级
        if actual_pct >= 35 or variance_pct >= 5:
            variance_status = "critical"
        elif variance_pct >= 2:
            variance_status = "warning"
        else:
            variance_status = "ok"

        # SQL 4: Top 10 食材用料
        r4 = await db.execute(
            text(
                "SELECT it.item_id, ii.name, ABS(SUM(it.total_cost)) AS usage_cost_fen "
                "FROM inventory_transactions it "
                "JOIN inventory_items ii ON it.item_id = ii.id "
                "WHERE it.store_id = :sid "
                "  AND it.transaction_type = 'usage' "
                "  AND it.transaction_time >= :start "
                "  AND it.transaction_time < :end "
                "GROUP BY it.item_id, ii.name "
                "ORDER BY usage_cost_fen DESC "
                "LIMIT 10"
            ),
            {"sid": store_id, "start": start_date, "end": end_exclusive},
        )
        top_ingredients = [
            {
                "item_id": row.item_id,
                "name": row.name,
                "usage_cost_fen": float(row.usage_cost_fen),
                "usage_cost_yuan": round(float(row.usage_cost_fen) / 100, 2),
            }
            for row in r4.fetchall()
        ]

        return {
            "store_id": store_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "actual_cost_fen": actual_cost_fen,
            "actual_cost_yuan": round(actual_cost_fen / 100, 2),
            "revenue_fen": revenue_fen,
            "revenue_yuan": round(revenue_fen / 100, 2),
            "actual_pct": actual_pct,
            "theoretical_pct": theoretical_pct,
            "variance_pct": variance_pct,
            "variance_status": variance_status,
            "top_ingredients": top_ingredients,
        }

    @staticmethod
    async def get_hq_food_cost_ranking(
        start_date: date, end_date: date, db: AsyncSession
    ) -> dict:
        """总部跨店食材成本排名（按差异率倒序）"""
        result = await db.execute(select(Store).where(Store.is_active == True))
        stores = result.scalars().all()

        store_results = []
        for store in stores:
            try:
                variance = await FoodCostService.get_store_food_cost_variance(
                    store_id=store.id,
                    start_date=start_date,
                    end_date=end_date,
                    db=db,
                )
                store_results.append({
                    "store_name": store.name,
                    **variance,
                })
            except Exception as e:
                logger.warning("food_cost_ranking.store_failed", store_id=store.id, error=str(e))

        # 按差异率倒序排名
        store_results.sort(key=lambda x: x["variance_pct"], reverse=True)
        for i, item in enumerate(store_results, 1):
            item["rank"] = i

        total_stores = len(store_results)
        over_budget = sum(1 for s in store_results if s["variance_status"] in ("warning", "critical"))
        avg_actual_pct = (
            round(sum(s["actual_pct"] for s in store_results) / total_stores, 2)
            if total_stores > 0
            else 0.0
        )

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "summary": {
                "total_stores": total_stores,
                "avg_actual_food_cost_pct": avg_actual_pct,
                "over_budget_stores": over_budget,
            },
            "stores": store_results,
        }
