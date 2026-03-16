"""
智能采购服务
自动检测库存低于阈值的食材，生成采购建议，支持审批/跳过/自动下单
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, delete, extract, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.auto_procurement import ProcurementExecution, ProcurementRule
from src.models.inventory import InventoryItem
from src.models.supplier_b2b import B2BPurchaseItem, B2BPurchaseOrder


class AutoProcurementService:
    """智能采购业务逻辑"""

    async def check_and_generate(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        检查库存并生成采购建议
        1. 加载所有启用的规则
        2. 对比当前库存与最低阈值
        3. 低于阈值则创建 ProcurementExecution（status=suggested）
        """
        # 加载启用的规则
        conditions = [
            ProcurementRule.brand_id == brand_id,
            ProcurementRule.is_enabled.is_(True),
        ]
        if store_id:
            # 匹配指定门店或全局规则（store_id=null）
            conditions.append((ProcurementRule.store_id == store_id) | (ProcurementRule.store_id.is_(None)))

        result = await db.execute(select(ProcurementRule).where(and_(*conditions)))
        rules = result.scalars().all()

        if not rules:
            return []

        suggestions: List[Dict[str, Any]] = []

        for rule in rules:
            # 确定要检查的门店
            target_store_id = rule.store_id or store_id
            if not target_store_id:
                continue

            # 查询当前库存
            inv_result = await db.execute(
                select(InventoryItem).where(
                    and_(
                        InventoryItem.store_id == target_store_id,
                        InventoryItem.name == rule.ingredient_name,
                    )
                )
            )
            inv_item = inv_result.scalar_one_or_none()

            current_qty = inv_item.current_quantity if inv_item else 0
            min_qty = float(rule.min_stock_qty)

            if current_qty >= min_qty:
                continue

            # 检查是否已有待处理的建议（避免重复）
            existing = await db.execute(
                select(func.count(ProcurementExecution.id)).where(
                    and_(
                        ProcurementExecution.rule_id == rule.id,
                        ProcurementExecution.status == "suggested",
                    )
                )
            )
            if existing.scalar_one() > 0:
                continue

            # 创建采购建议
            reorder_qty = float(rule.reorder_qty)
            deficit = min_qty - current_qty
            reason = (
                f"当前库存 {current_qty:.1f}{rule.unit}，"
                f"低于阈值 {min_qty:.1f}{rule.unit}，"
                f"缺口 {deficit:.1f}{rule.unit}"
            )

            execution = ProcurementExecution(
                id=uuid.uuid4(),
                rule_id=rule.id,
                brand_id=brand_id,
                store_id=target_store_id,
                trigger_type="auto_low_stock",
                ingredient_name=rule.ingredient_name,
                quantity=Decimal(str(reorder_qty)),
                status="suggested",
                reason=reason,
                executed_at=datetime.utcnow(),
            )
            db.add(execution)

            # 更新规则最后触发时间
            rule.last_triggered_at = datetime.utcnow()

            suggestion = execution.to_dict()
            suggestion["current_stock"] = current_qty
            suggestion["min_stock_qty"] = min_qty
            suggestion["supplier_name"] = rule.supplier_name
            suggestion["supplier_id"] = rule.supplier_id
            suggestion["unit"] = rule.unit
            suggestion["unit_price_fen"] = rule.unit_price_fen
            suggestion["estimated_cost_fen"] = int(reorder_qty * rule.unit_price_fen)
            suggestions.append(suggestion)

        await db.flush()
        return suggestions

    async def get_suggestions(
        self,
        db: AsyncSession,
        brand_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """获取待处理的采购建议"""
        where_clause = and_(
            ProcurementExecution.brand_id == brand_id,
            ProcurementExecution.status == "suggested",
        )

        count_result = await db.execute(select(func.count(ProcurementExecution.id)).where(where_clause))
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        result = await db.execute(
            select(ProcurementExecution)
            .where(where_clause)
            .order_by(ProcurementExecution.executed_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        executions = result.scalars().all()

        # 为每条建议附加规则信息
        items = []
        for ex in executions:
            item = ex.to_dict()
            if ex.rule_id:
                rule_result = await db.execute(select(ProcurementRule).where(ProcurementRule.id == ex.rule_id))
                rule = rule_result.scalar_one_or_none()
                if rule:
                    item["supplier_name"] = rule.supplier_name
                    item["supplier_id"] = rule.supplier_id
                    item["unit"] = rule.unit
                    item["unit_price_fen"] = rule.unit_price_fen
                    item["min_stock_qty"] = float(rule.min_stock_qty)
                    item["estimated_cost_fen"] = int(float(ex.quantity) * rule.unit_price_fen)
            items.append(item)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def approve_suggestion(self, db: AsyncSession, execution_id: str) -> Dict[str, Any]:
        """审批建议 -> 生成B2B采购单"""
        result = await db.execute(select(ProcurementExecution).where(ProcurementExecution.id == execution_id))
        execution = result.scalar_one_or_none()
        if not execution:
            raise ValueError("采购建议不存在")
        if execution.status != "suggested":
            raise ValueError(f"当前状态 {execution.status} 不允许审批")

        # 查找关联规则获取供应商信息
        rule = None
        if execution.rule_id:
            rule_result = await db.execute(select(ProcurementRule).where(ProcurementRule.id == execution.rule_id))
            rule = rule_result.scalar_one_or_none()

        if not rule:
            raise ValueError("关联规则不存在，无法生成采购单")

        # 生成采购单号
        order_number = await self._generate_order_number(db)

        qty = float(execution.quantity)
        unit_price_fen = rule.unit_price_fen
        amount_fen = int(qty * unit_price_fen)

        expected_date = date.today() + timedelta(days=rule.lead_days)

        order_item = B2BPurchaseItem(
            id=uuid.uuid4(),
            ingredient_name=execution.ingredient_name,
            ingredient_id=rule.ingredient_id,
            quantity=execution.quantity,
            unit=rule.unit,
            unit_price_fen=unit_price_fen,
            amount_fen=amount_fen,
        )

        order = B2BPurchaseOrder(
            id=uuid.uuid4(),
            brand_id=execution.brand_id,
            store_id=execution.store_id,
            supplier_id=rule.supplier_id,
            supplier_name=rule.supplier_name,
            order_number=order_number,
            status="draft",
            total_amount_fen=amount_fen,
            expected_delivery_date=expected_date,
            notes=f"智能采购自动生成 - {execution.reason or ''}",
            items=[order_item],
        )
        db.add(order)
        await db.flush()

        # 更新执行记录
        execution.status = "ordered"
        execution.generated_order_id = order.id
        await db.flush()

        result_dict = execution.to_dict()
        result_dict["order_number"] = order_number
        result_dict["total_amount_fen"] = amount_fen
        return result_dict

    async def skip_suggestion(self, db: AsyncSession, execution_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """跳过采购建议"""
        result = await db.execute(select(ProcurementExecution).where(ProcurementExecution.id == execution_id))
        execution = result.scalar_one_or_none()
        if not execution:
            raise ValueError("采购建议不存在")
        if execution.status != "suggested":
            raise ValueError(f"当前状态 {execution.status} 不允许跳过")

        execution.status = "skipped"
        if reason:
            execution.reason = f"{execution.reason or ''}\n跳过原因: {reason}".strip()
        await db.flush()
        return execution.to_dict()

    # ── 规则管理 ───────────────────────────────────────────────────────────────

    async def create_rule(self, db: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建采购规则"""
        rule = ProcurementRule(
            id=uuid.uuid4(),
            brand_id=data["brand_id"],
            store_id=data.get("store_id"),
            ingredient_id=data["ingredient_id"],
            ingredient_name=data["ingredient_name"],
            supplier_id=data["supplier_id"],
            supplier_name=data["supplier_name"],
            min_stock_qty=Decimal(str(data["min_stock_qty"])),
            reorder_qty=Decimal(str(data["reorder_qty"])),
            unit=data.get("unit", "kg"),
            unit_price_fen=data.get("unit_price_fen", 0),
            lead_days=data.get("lead_days", 1),
            is_enabled=data.get("is_enabled", True),
        )
        db.add(rule)
        await db.flush()
        return rule.to_dict()

    async def list_rules(
        self,
        db: AsyncSession,
        brand_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """分页查询采购规则"""
        where_clause = ProcurementRule.brand_id == brand_id

        count_result = await db.execute(select(func.count(ProcurementRule.id)).where(where_clause))
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        result = await db.execute(
            select(ProcurementRule)
            .where(where_clause)
            .order_by(ProcurementRule.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rules = result.scalars().all()

        return {
            "items": [r.to_dict() for r in rules],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def update_rule(self, db: AsyncSession, rule_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新采购规则"""
        result = await db.execute(select(ProcurementRule).where(ProcurementRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule:
            raise ValueError("规则不存在")

        updatable = [
            "ingredient_id",
            "ingredient_name",
            "supplier_id",
            "supplier_name",
            "unit",
            "lead_days",
            "is_enabled",
            "store_id",
        ]
        for field in updatable:
            if field in data:
                setattr(rule, field, data[field])

        if "min_stock_qty" in data:
            rule.min_stock_qty = Decimal(str(data["min_stock_qty"]))
        if "reorder_qty" in data:
            rule.reorder_qty = Decimal(str(data["reorder_qty"]))
        if "unit_price_fen" in data:
            rule.unit_price_fen = data["unit_price_fen"]

        await db.flush()
        return rule.to_dict()

    async def delete_rule(self, db: AsyncSession, rule_id: str) -> bool:
        """删除采购规则"""
        result = await db.execute(select(ProcurementRule).where(ProcurementRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule:
            raise ValueError("规则不存在")

        await db.delete(rule)
        await db.flush()
        return True

    # ── 执行历史 ───────────────────────────────────────────────────────────────

    async def get_executions(
        self,
        db: AsyncSession,
        brand_id: str,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        trigger_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页查询执行记录"""
        conditions = [ProcurementExecution.brand_id == brand_id]
        if status:
            conditions.append(ProcurementExecution.status == status)
        if trigger_type:
            conditions.append(ProcurementExecution.trigger_type == trigger_type)

        where_clause = and_(*conditions)

        count_result = await db.execute(select(func.count(ProcurementExecution.id)).where(where_clause))
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        result = await db.execute(
            select(ProcurementExecution)
            .where(where_clause)
            .order_by(ProcurementExecution.executed_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        executions = result.scalars().all()

        return {
            "items": [e.to_dict() for e in executions],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ── 统计 ───────────────────────────────────────────────────────────────────

    async def get_stats(self, db: AsyncSession, brand_id: str) -> Dict[str, Any]:
        """统计概览：活跃规则、待处理建议、本月自动下单、预估节省"""
        # 活跃规则数
        active_result = await db.execute(
            select(func.count(ProcurementRule.id)).where(
                and_(
                    ProcurementRule.brand_id == brand_id,
                    ProcurementRule.is_enabled.is_(True),
                )
            )
        )
        active_rules = active_result.scalar_one()

        # 待处理建议数
        pending_result = await db.execute(
            select(func.count(ProcurementExecution.id)).where(
                and_(
                    ProcurementExecution.brand_id == brand_id,
                    ProcurementExecution.status == "suggested",
                )
            )
        )
        pending_suggestions = pending_result.scalar_one()

        # 本月自动下单数和金额
        now = datetime.utcnow()
        month_conditions = and_(
            ProcurementExecution.brand_id == brand_id,
            ProcurementExecution.status == "ordered",
            extract("year", ProcurementExecution.executed_at) == now.year,
            extract("month", ProcurementExecution.executed_at) == now.month,
        )
        ordered_result = await db.execute(select(func.count(ProcurementExecution.id)).where(month_conditions))
        monthly_ordered = ordered_result.scalar_one()

        # 本月跳过数（节省参考）
        skipped_result = await db.execute(
            select(func.count(ProcurementExecution.id)).where(
                and_(
                    ProcurementExecution.brand_id == brand_id,
                    ProcurementExecution.status == "skipped",
                    extract("year", ProcurementExecution.executed_at) == now.year,
                    extract("month", ProcurementExecution.executed_at) == now.month,
                )
            )
        )
        monthly_skipped = skipped_result.scalar_one()

        return {
            "active_rules": active_rules,
            "pending_suggestions": pending_suggestions,
            "monthly_ordered": monthly_ordered,
            "monthly_skipped": monthly_skipped,
        }

    # ── 内部方法 ───────────────────────────────────────────────────────────────

    async def _generate_order_number(self, db: AsyncSession) -> str:
        """生成采购单号：AP-YYYYMMDD-XXXX"""
        today = datetime.utcnow().strftime("%Y%m%d")
        prefix = f"AP-{today}-"

        result = await db.execute(
            select(func.max(B2BPurchaseOrder.order_number)).where(B2BPurchaseOrder.order_number.like(f"{prefix}%"))
        )
        max_number = result.scalar_one_or_none()

        if max_number:
            seq = int(max_number.split("-")[-1]) + 1
        else:
            seq = 1

        return f"{prefix}{seq:04d}"


# 单例
auto_procurement_service = AutoProcurementService()
