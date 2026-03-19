"""
智能备料建议服务

算法：
  建议采购量 = (明日预订桌数 × 平均人数 × 菜品点击率 × BOM单位用量)
             + (历史同日销量均值 × BOM单位用量 × 安全系数1.1)
             - 当前库存量
             + 损耗补偿量(损耗率 × 总需求)
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.bom import BOMItem, BOMTemplate
from src.models.inventory import InventoryItem, InventoryTransaction
from src.models.supply_chain import PurchaseOrder

# ---------- 常量 ----------
SAFETY_FACTOR = Decimal("1.1")  # 安全系数
DEFAULT_WASTE_RATE = Decimal("0.05")  # 默认损耗率 5%
DEFAULT_AVG_GUESTS = 3  # 默认每桌人数
DEFAULT_DISH_HIT_RATE = Decimal("0.6")  # 默认菜品点击率


class PrepSuggestionService:
    """备料建议引擎"""

    def __init__(self, db: AsyncSession, store_id: str):
        self.db = db
        self.store_id = store_id

    # ======================== 核心：生成建议 ========================

    async def generate_suggestions(
        self,
        target_date: Optional[date] = None,
    ) -> dict:
        """
        生成指定日期的备料建议单。

        返回:
        {
            "suggestion_id": str,
            "store_id": str,
            "target_date": str,
            "generated_at": str,
            "items": [
                {
                    "ingredient_id": str,
                    "ingredient_name": str,
                    "category": str,
                    "unit": str,
                    "current_stock": float,
                    "predicted_demand": float,
                    "suggested_qty": float,
                    "estimated_cost_yuan": float,
                    "sources": { "reservation": float, "history": float, "waste_buffer": float },
                    "confidence": str,  # high / medium / low
                }
            ],
            "total_estimated_cost_yuan": float,
        }
        """
        if target_date is None:
            target_date = date.today() + timedelta(days=1)

        # 1. 获取活跃 BOM 及其明细
        bom_map = await self._get_active_bom_items()
        if not bom_map:
            return self._empty_result(target_date)

        # 2. 获取明日预订数据
        reservation_demand = await self._get_reservation_demand(target_date)

        # 3. 获取历史同日销售（最近 4 周同一星期几的平均值）
        history_demand = await self._get_history_demand(target_date)

        # 4. 获取当前库存
        stock_map = await self._get_current_stock()

        # 5. 合并计算
        items = []
        total_cost = Decimal("0")

        all_ingredient_ids = set(bom_map.keys())
        for ingredient_id in sorted(all_ingredient_ids):
            bom_info = bom_map[ingredient_id]
            std_qty = bom_info["std_qty"]  # BOM 单位用量
            waste_factor = bom_info["waste_factor"]  # 损耗系数
            unit_cost_fen = bom_info["unit_cost"]  # 分

            # 预订需求（桌数 × 人均 × 点击率 × BOM用量）
            res_qty = reservation_demand * DEFAULT_AVG_GUESTS * DEFAULT_DISH_HIT_RATE * std_qty

            # 历史需求（同日均值 × BOM用量 × 安全系数）
            hist_dishes = history_demand.get(ingredient_id, Decimal("0"))
            hist_qty = hist_dishes * std_qty * SAFETY_FACTOR

            # 综合需求取较大值
            predicted = max(res_qty, hist_qty)

            # 损耗补偿
            effective_waste = waste_factor if waste_factor > 0 else DEFAULT_WASTE_RATE
            waste_buffer = predicted * effective_waste

            # 减去现有库存
            current_stock = Decimal(str(stock_map.get(ingredient_id, 0)))
            suggested = predicted + waste_buffer - current_stock

            if suggested <= 0:
                continue  # 库存充足，无需采购

            # 成本估算（分 → 元）
            cost_yuan = (suggested * Decimal(str(unit_cost_fen or 0))) / Decimal("100")
            total_cost += cost_yuan

            # 置信度
            confidence = (
                "high"
                if hist_dishes > 0 and reservation_demand > 0
                else ("medium" if hist_dishes > 0 or reservation_demand > 0 else "low")
            )

            items.append(
                {
                    "ingredient_id": ingredient_id,
                    "ingredient_name": bom_info["name"],
                    "category": bom_info["category"],
                    "unit": bom_info["unit"],
                    "current_stock": float(current_stock),
                    "predicted_demand": float(predicted),
                    "suggested_qty": float(suggested.quantize(Decimal("0.01"))),
                    "estimated_cost_yuan": float(cost_yuan.quantize(Decimal("0.01"))),
                    "sources": {
                        "reservation": float(res_qty.quantize(Decimal("0.01"))),
                        "history": float(hist_qty.quantize(Decimal("0.01"))),
                        "waste_buffer": float(waste_buffer.quantize(Decimal("0.01"))),
                    },
                    "confidence": confidence,
                }
            )

        # 按建议量降序
        items.sort(key=lambda x: x["suggested_qty"], reverse=True)

        return {
            "suggestion_id": f"PREP_{uuid.uuid4().hex[:12].upper()}",
            "store_id": self.store_id,
            "target_date": target_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "items": items,
            "total_estimated_cost_yuan": float(total_cost.quantize(Decimal("0.01"))),
        }

    # ======================== 确认建议 → 生成采购单 ========================

    async def confirm_suggestion(
        self,
        suggestion_items: list[dict],
        created_by: str,
        notes: str = "",
    ) -> dict:
        """
        确认备料建议并自动生成采购申请单。

        suggestion_items: [{ "ingredient_id": str, "qty": float }]
        """
        order_number = f"PO-PREP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"

        po_items = []
        total_amount = 0

        for item in suggestion_items:
            inv = await self.db.get(InventoryItem, item["ingredient_id"])
            unit_cost = inv.unit_cost or 0 if inv else 0
            qty = item["qty"]
            line_total = int(qty * unit_cost)
            total_amount += line_total
            po_items.append(
                {
                    "ingredient_id": item["ingredient_id"],
                    "name": inv.name if inv else item["ingredient_id"],
                    "quantity": qty,
                    "unit": inv.unit if inv else "kg",
                    "unit_cost_fen": unit_cost,
                    "line_total_fen": line_total,
                }
            )

        po = PurchaseOrder(
            id=str(uuid.uuid4()),
            order_number=order_number,
            supplier_id="",  # 由采购人员后续指定
            store_id=self.store_id,
            status="pending",
            total_amount=total_amount,
            items=po_items,
            notes=f"[智能备料建议] {notes}",
            created_by=created_by,
        )
        self.db.add(po)
        await self.db.flush()

        return {
            "purchase_order_id": po.id,
            "order_number": order_number,
            "status": "pending",
            "total_amount_yuan": round(total_amount / 100, 2),
            "item_count": len(po_items),
        }

    # ======================== 历史查询 ========================

    async def list_history(self, limit: int = 20) -> list[dict]:
        """查询本店由备料建议生成的采购单历史"""
        stmt = (
            select(PurchaseOrder)
            .where(
                PurchaseOrder.store_id == self.store_id,
                PurchaseOrder.notes.ilike("%智能备料建议%"),
            )
            .order_by(PurchaseOrder.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        orders = result.scalars().all()

        return [
            {
                "purchase_order_id": po.id,
                "order_number": po.order_number,
                "status": po.status,
                "total_amount_yuan": round((po.total_amount or 0) / 100, 2),
                "item_count": len(po.items) if po.items else 0,
                "created_at": po.created_at.isoformat() if po.created_at else None,
                "created_by": po.created_by,
            }
            for po in orders
        ]

    # ======================== 内部辅助 ========================

    async def _get_active_bom_items(self) -> dict:
        """获取本店所有活跃 BOM 的食材明细，按 ingredient_id 聚合"""
        stmt = (
            select(
                BOMItem.ingredient_id,
                BOMItem.standard_qty,
                BOMItem.waste_factor,
                BOMItem.unit_cost,
                InventoryItem.name,
                InventoryItem.category,
                InventoryItem.unit,
            )
            .join(BOMTemplate, BOMItem.bom_id == BOMTemplate.id)
            .join(InventoryItem, BOMItem.ingredient_id == InventoryItem.id)
            .where(
                BOMTemplate.store_id == self.store_id,
                BOMTemplate.is_active == True,
            )
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        # 同一食材可能出现在多道菜的 BOM 中，累加用量
        bom_map: dict = {}
        for row in rows:
            iid = row.ingredient_id
            if iid not in bom_map:
                bom_map[iid] = {
                    "name": row.name,
                    "category": row.category,
                    "unit": row.unit,
                    "std_qty": Decimal(str(row.standard_qty)),
                    "waste_factor": Decimal(str(row.waste_factor or 0)),
                    "unit_cost": row.unit_cost or 0,
                }
            else:
                bom_map[iid]["std_qty"] += Decimal(str(row.standard_qty))
        return bom_map

    async def _get_reservation_demand(self, target_date: date) -> Decimal:
        """获取目标日期的预订桌数（从 orders 或 reservations 表估算）"""
        # 尝试从 reservations 表获取
        try:
            stmt = text("""
                SELECT COUNT(*) as cnt
                FROM reservations
                WHERE store_id = :store_id
                  AND DATE(reservation_time) = :target_date
                  AND status NOT IN ('cancelled', 'no_show')
            """)
            result = await self.db.execute(
                stmt,
                {"store_id": self.store_id, "target_date": target_date},
            )
            row = result.first()
            return Decimal(str(row.cnt)) if row and row.cnt else Decimal("0")
        except Exception:
            return Decimal("0")

    async def _get_history_demand(self, target_date: date) -> dict:
        """
        获取最近 4 周同一星期几的食材消耗均值。
        返回 { ingredient_id: avg_dishes_sold }
        """
        weekday = target_date.weekday()  # 0=Monday
        four_weeks_ago = target_date - timedelta(days=28)

        try:
            stmt = text("""
                SELECT t.item_id as ingredient_id,
                       AVG(ABS(t.quantity)) as avg_qty
                FROM inventory_transactions t
                WHERE t.store_id = :store_id
                  AND t.transaction_type = 'usage'
                  AND t.transaction_time >= :start_date
                  AND t.transaction_time < :end_date
                  AND EXTRACT(DOW FROM t.transaction_time) = :dow
                GROUP BY t.item_id
            """)
            result = await self.db.execute(
                stmt,
                {
                    "store_id": self.store_id,
                    "start_date": four_weeks_ago,
                    "end_date": target_date,
                    "dow": weekday,
                },
            )
            rows = result.all()
            return {row.ingredient_id: Decimal(str(row.avg_qty)) for row in rows}
        except Exception:
            return {}

    async def _get_current_stock(self) -> dict:
        """获取本店当前库存"""
        stmt = select(InventoryItem.id, InventoryItem.current_quantity).where(InventoryItem.store_id == self.store_id)
        result = await self.db.execute(stmt)
        return {row.id: row.current_quantity for row in result.all()}

    def _empty_result(self, target_date: date) -> dict:
        return {
            "suggestion_id": None,
            "store_id": self.store_id,
            "target_date": target_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "items": [],
            "total_estimated_cost_yuan": 0,
        }
