"""
BOM管理服务
处理配方卡管理、成本计算、损耗分析等业务逻辑
"""
import uuid
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import structlog
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models.bom import BOM, Material, WasteRecord
from ..models.order import Order, OrderItem
from ..models.inventory import InventoryItem

logger = structlog.get_logger()


class BOMService:
    """BOM管理服务"""

    async def create_bom(
        self,
        dish_id: str,
        dish_name: str,
        store_id: str,
        ingredients: List[Dict[str, Any]],
        yield_portions: float = float(os.getenv("BOM_DEFAULT_YIELD_PORTIONS", "1.0")),
        preparation_notes: Optional[str] = None,
        cooking_time: Optional[int] = None,
        difficulty_level: Optional[str] = None,
        created_by: Optional[str] = None,
        db: Session = None
    ) -> BOM:
        """
        创建配方卡

        Args:
            dish_id: 菜品ID
            dish_name: 菜品名称
            store_id: 门店ID
            ingredients: 原材料列表
            yield_portions: 产出份数
            preparation_notes: 制作说明
            cooking_time: 烹饪时间
            difficulty_level: 难度等级
            created_by: 创建人ID
            db: 数据库会话

        Returns:
            BOM: 配方卡对象
        """
        try:
            # 创建BOM对象
            bom = BOM(
                id=str(uuid.uuid4()),
                dish_id=dish_id,
                dish_name=dish_name,
                store_id=store_id,
                yield_portions=yield_portions,
                ingredients=ingredients,
                preparation_notes=preparation_notes,
                cooking_time=cooking_time,
                difficulty_level=difficulty_level,
                created_by=created_by,
                created_at=datetime.utcnow()
            )

            # 计算成本
            bom.calculate_total_cost()

            # 保存到数据库
            db.add(bom)
            db.commit()
            db.refresh(bom)

            logger.info(
                "bom_created",
                bom_id=bom.id,
                dish_name=dish_name,
                store_id=store_id,
                total_cost=bom.total_cost
            )

            return bom

        except Exception as e:
            logger.error("create_bom_failed", error=str(e))
            db.rollback()
            raise

    async def update_bom(
        self,
        bom_id: str,
        ingredients: Optional[List[Dict[str, Any]]] = None,
        yield_portions: Optional[float] = None,
        preparation_notes: Optional[str] = None,
        updated_by: Optional[str] = None,
        db: Session = None
    ) -> BOM:
        """
        更新配方卡

        Args:
            bom_id: 配方卡ID
            ingredients: 原材料列表
            yield_portions: 产出份数
            preparation_notes: 制作说明
            updated_by: 更新人ID
            db: 数据库会话

        Returns:
            BOM: 更新后的配方卡对象
        """
        try:
            bom = db.query(BOM).filter(BOM.id == bom_id).first()
            if not bom:
                raise ValueError(f"BOM not found: {bom_id}")

            # 更新字段
            if ingredients is not None:
                bom.ingredients = ingredients
            if yield_portions is not None:
                bom.yield_portions = yield_portions
            if preparation_notes is not None:
                bom.preparation_notes = preparation_notes

            bom.updated_by = updated_by
            bom.updated_at = datetime.utcnow()
            bom.version += 1

            # 重新计算成本
            bom.calculate_total_cost()

            db.commit()
            db.refresh(bom)

            logger.info(
                "bom_updated",
                bom_id=bom_id,
                version=bom.version,
                total_cost=bom.total_cost
            )

            return bom

        except Exception as e:
            logger.error("update_bom_failed", error=str(e))
            db.rollback()
            raise

    async def calculate_dish_consumption(
        self,
        dish_id: str,
        store_id: str,
        quantity: int,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        计算菜品的原材料消耗

        Args:
            dish_id: 菜品ID
            store_id: 门店ID
            quantity: 菜品数量
            db: 数据库会话

        Returns:
            Dict: 原材料消耗明细
        """
        try:
            # 获取配方卡
            bom = db.query(BOM).filter(
                BOM.dish_id == dish_id,
                BOM.store_id == store_id,
                BOM.is_active == 1
            ).first()

            if not bom:
                raise ValueError(f"BOM not found for dish: {dish_id}")

            # 计算每种原材料的消耗
            consumption = []
            for ingredient in bom.ingredients:
                # 实际消耗 = (配方用量 / 净菜率 / (1 - 烹饪损耗率)) * 菜品数量 / 产出份数
                quantity_per_portion = ingredient.get("quantity", 0)
                net_rate = ingredient.get("net_rate", 1.0)
                cooking_loss = ingredient.get("cooking_loss", 0.0)

                actual_consumption_per_portion = quantity_per_portion / net_rate / (1 - cooking_loss)
                total_consumption = actual_consumption_per_portion * quantity / bom.yield_portions

                consumption.append({
                    "material_id": ingredient.get("material_id"),
                    "material_name": ingredient.get("material_name"),
                    "quantity": round(total_consumption, 2),
                    "unit": ingredient.get("unit"),
                    "cost": round(total_consumption / 1000 * ingredient.get("unit_cost", 0), 2)
                })

            total_cost = sum([item["cost"] for item in consumption])

            return {
                "dish_id": dish_id,
                "dish_name": bom.dish_name,
                "quantity": quantity,
                "consumption": consumption,
                "total_cost": round(total_cost, 2)
            }

        except Exception as e:
            logger.error("calculate_dish_consumption_failed", error=str(e))
            raise

    async def predict_inventory_needs(
        self,
        store_id: str,
        start_date: datetime,
        end_date: datetime,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        基于BOM预测库存需求

        Args:
            store_id: 门店ID
            start_date: 开始日期
            end_date: 结束日期
            db: 数据库会话

        Returns:
            Dict: 库存需求预测
        """
        try:
            # 1. 获取历史订单数据
            orders = db.query(Order).filter(
                Order.store_id == store_id,
                Order.created_at >= start_date,
                Order.created_at <= end_date,
                Order.status.in_(["completed", "paid"])
            ).all()

            # 2. 统计每个菜品的销量
            dish_sales = {}
            for order in orders:
                for item in order.items:
                    dish_id = item.dish_id
                    if dish_id not in dish_sales:
                        dish_sales[dish_id] = 0
                    dish_sales[dish_id] += item.quantity

            # 3. 基于BOM计算原材料需求
            material_needs = {}
            for dish_id, quantity in dish_sales.items():
                consumption = await self.calculate_dish_consumption(
                    dish_id=dish_id,
                    store_id=store_id,
                    quantity=quantity,
                    db=db
                )

                for item in consumption["consumption"]:
                    material_id = item["material_id"]
                    if material_id not in material_needs:
                        material_needs[material_id] = {
                            "material_name": item["material_name"],
                            "quantity": 0,
                            "unit": item["unit"],
                            "cost": 0
                        }
                    material_needs[material_id]["quantity"] += item["quantity"]
                    material_needs[material_id]["cost"] += item["cost"]

            # 4. 计算预测需求（基于历史数据）
            days = (end_date - start_date).days
            daily_needs = {}
            for material_id, data in material_needs.items():
                daily_needs[material_id] = {
                    "material_name": data["material_name"],
                    "daily_quantity": round(data["quantity"] / days, 2),
                    "unit": data["unit"],
                    "daily_cost": round(data["cost"] / days, 2),
                    "weekly_quantity": round(data["quantity"] / days * 7, 2),
                    "weekly_cost": round(data["cost"] / days * 7, 2)
                }

            return {
                "store_id": store_id,
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": days
                },
                "dish_sales": dish_sales,
                "material_needs": daily_needs,
                "total_daily_cost": round(sum([item["daily_cost"] for item in daily_needs.values()]), 2),
                "total_weekly_cost": round(sum([item["weekly_cost"] for item in daily_needs.values()]), 2)
            }

        except Exception as e:
            logger.error("predict_inventory_needs_failed", error=str(e))
            raise

    async def record_waste(
        self,
        store_id: str,
        material_id: str,
        waste_quantity: float,
        waste_unit: str,
        waste_type: str,
        waste_reason: Optional[str] = None,
        waste_date: Optional[datetime] = None,
        responsible_person_id: Optional[str] = None,
        created_by: Optional[str] = None,
        db: Session = None
    ) -> WasteRecord:
        """
        记录损耗

        Args:
            store_id: 门店ID
            material_id: 物料ID
            waste_quantity: 损耗数量
            waste_unit: 损耗单位
            waste_type: 损耗类型
            waste_reason: 损耗原因
            waste_date: 损耗日期
            responsible_person_id: 责任人ID
            created_by: 创建人ID
            db: 数据库会话

        Returns:
            WasteRecord: 损耗记录对象
        """
        try:
            # 获取物料信息
            material = db.query(Material).filter(Material.id == material_id).first()
            if not material:
                raise ValueError(f"Material not found: {material_id}")

            # 计算损耗成本
            waste_cost = waste_quantity * material.latest_cost if material.latest_cost else 0

            # 创建损耗记录
            waste_record = WasteRecord(
                id=str(uuid.uuid4()),
                store_id=store_id,
                material_id=material_id,
                waste_quantity=waste_quantity,
                waste_unit=waste_unit,
                waste_cost=waste_cost,
                waste_type=waste_type,
                waste_reason=waste_reason,
                waste_date=waste_date or datetime.utcnow(),
                responsible_person_id=responsible_person_id,
                created_by=created_by,
                created_at=datetime.utcnow()
            )

            db.add(waste_record)
            db.commit()
            db.refresh(waste_record)

            logger.info(
                "waste_recorded",
                waste_id=waste_record.id,
                material_id=material_id,
                quantity=waste_quantity,
                cost=waste_cost
            )

            return waste_record

        except Exception as e:
            logger.error("record_waste_failed", error=str(e))
            db.rollback()
            raise

    async def analyze_waste(
        self,
        store_id: str,
        start_date: datetime,
        end_date: datetime,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        分析损耗情况

        Args:
            store_id: 门店ID
            start_date: 开始日期
            end_date: 结束日期
            db: 数据库会话

        Returns:
            Dict: 损耗分析结果
        """
        try:
            # 查询损耗记录
            waste_records = db.query(WasteRecord).filter(
                WasteRecord.store_id == store_id,
                WasteRecord.waste_date >= start_date,
                WasteRecord.waste_date <= end_date
            ).all()

            # 按损耗类型统计
            by_type = {}
            for record in waste_records:
                waste_type = record.waste_type
                if waste_type not in by_type:
                    by_type[waste_type] = {
                        "count": 0,
                        "total_cost": 0,
                        "records": []
                    }
                by_type[waste_type]["count"] += 1
                by_type[waste_type]["total_cost"] += record.waste_cost or 0
                by_type[waste_type]["records"].append(record.to_dict())

            # 按物料统计
            by_material = {}
            for record in waste_records:
                material_id = record.material_id
                if material_id not in by_material:
                    by_material[material_id] = {
                        "material_name": record.material.material_name if record.material else "Unknown",
                        "count": 0,
                        "total_quantity": 0,
                        "total_cost": 0
                    }
                by_material[material_id]["count"] += 1
                by_material[material_id]["total_quantity"] += record.waste_quantity
                by_material[material_id]["total_cost"] += record.waste_cost or 0

            # 计算总损耗
            total_waste_cost = sum([record.waste_cost or 0 for record in waste_records])
            total_waste_count = len(waste_records)

            # 计算损耗率
            days = (end_date - start_date).days
            daily_waste_cost = total_waste_cost / days if days > 0 else 0

            return {
                "store_id": store_id,
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": days
                },
                "summary": {
                    "total_waste_count": total_waste_count,
                    "total_waste_cost": round(total_waste_cost, 2),
                    "daily_waste_cost": round(daily_waste_cost, 2),
                    "average_waste_per_record": round(total_waste_cost / total_waste_count, 2) if total_waste_count > 0 else 0
                },
                "by_type": by_type,
                "by_material": by_material,
                "top_waste_materials": sorted(
                    by_material.items(),
                    key=lambda x: x[1]["total_cost"],
                    reverse=True
                )[:10]
            }

        except Exception as e:
            logger.error("analyze_waste_failed", error=str(e))
            raise


# 全局实例
bom_service = BOMService()
