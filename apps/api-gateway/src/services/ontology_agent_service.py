"""
OntologyAgent Service — 本体知识智能（Sprint 6）

9-Agent 终态中的 OntologyAgent，核心能力：
1. 知识覆盖度（菜品/食材/BOM 完整率）
2. 数据质量评分（缺失字段/异常值/孤立记录）
3. 实体统计（各类实体数量 + 关系密度）
4. 本体健康报告（数据一致性检查）

定位：数据治理的自动巡检员，确保系统知识库的完整性和准确性
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.bom import BOMItem, BOMTemplate
from src.models.dish import Dish, DishCategory
from src.models.inventory import InventoryItem
from src.models.order import Order, OrderItem

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def compute_knowledge_coverage(
    total_entities: int,
    complete_entities: int,
) -> float:
    """
    知识覆盖率 = 完整实体数 / 总实体数

    完整定义：核心字段全部非空
    行业基准：≥ 85% 为健康
    """
    if total_entities <= 0:
        return 0.0
    return round(complete_entities / total_entities, 4)


def classify_data_quality(coverage: float) -> str:
    """
    数据质量分级

    excellent: ≥ 90%
    good: 70%-90%
    warning: 50%-70%
    critical: < 50%
    """
    if coverage >= 0.90:
        return "excellent"
    if coverage >= 0.70:
        return "good"
    if coverage >= 0.50:
        return "warning"
    return "critical"


def compute_relationship_density(
    total_relationships: int,
    total_entities: int,
) -> float:
    """
    关系密度 = 关系数 / 实体数

    密度越高说明知识图谱越丰富
    基准：≥ 2.0 为丰富
    """
    if total_entities <= 0:
        return 0.0
    return round(total_relationships / total_entities, 2)


def compute_ontology_health_score(
    dish_coverage: float,
    bom_coverage: float,
    inventory_coverage: float,
) -> float:
    """
    本体健康评分（0-100）

    权重：菜品40% + BOM35% + 食材25%
    """
    score = dish_coverage * 100 * 0.40 + bom_coverage * 100 * 0.35 + inventory_coverage * 100 * 0.25
    return round(min(max(score, 0), 100), 1)


class OntologyAgentService:
    """OntologyAgent — 本体知识智能"""

    async def get_ontology_dashboard(
        self,
        db: AsyncSession,
        store_id: str,
    ) -> dict:
        """
        本体知识仪表盘

        返回：实体统计 + 各维度覆盖率 + 健康评分 + 数据质量等级
        """
        # 菜品覆盖率（有价格+有分类=完整）
        dish_total = (
            await db.scalar(
                select(func.count(Dish.id)).where(
                    Dish.store_id == store_id,
                    Dish.is_available.is_(True),
                )
            )
            or 0
        )

        dish_complete = (
            await db.scalar(
                select(func.count(Dish.id)).where(
                    Dish.store_id == store_id,
                    Dish.is_available.is_(True),
                    Dish.price.isnot(None),
                    Dish.category_id.isnot(None),
                )
            )
            or 0
        )

        dish_coverage = compute_knowledge_coverage(dish_total, dish_complete)

        # BOM覆盖率（有BOM模板的菜品占比）
        dishes_with_bom = (
            await db.scalar(
                select(func.count(func.distinct(BOMTemplate.dish_id))).where(
                    BOMTemplate.store_id == store_id,
                    BOMTemplate.is_active.is_(True),
                )
            )
            or 0
        )

        bom_coverage = compute_knowledge_coverage(dish_total, dishes_with_bom)

        # 食材覆盖率（有单位成本的食材占比）
        inv_total = (
            await db.scalar(
                select(func.count(InventoryItem.id)).where(
                    InventoryItem.store_id == store_id,
                )
            )
            or 0
        )

        inv_complete = (
            await db.scalar(
                select(func.count(InventoryItem.id)).where(
                    InventoryItem.store_id == store_id,
                    InventoryItem.unit_cost.isnot(None),
                    InventoryItem.unit.isnot(None),
                )
            )
            or 0
        )

        inv_coverage = compute_knowledge_coverage(inv_total, inv_complete)

        # BOM关系密度
        bom_item_count = (
            await db.scalar(
                select(func.count(BOMItem.id))
                .join(BOMTemplate, BOMTemplate.id == BOMItem.bom_id)
                .where(
                    BOMTemplate.store_id == store_id,
                    BOMTemplate.is_active.is_(True),
                )
            )
            or 0
        )

        total_entities = dish_total + inv_total
        relationship_density = compute_relationship_density(bom_item_count, total_entities)

        # 健康评分
        health_score = compute_ontology_health_score(
            dish_coverage,
            bom_coverage,
            inv_coverage,
        )
        quality = classify_data_quality(health_score / 100)

        return {
            "store_id": store_id,
            "health_score": health_score,
            "data_quality": quality,
            "entity_counts": {
                "dishes": dish_total,
                "inventory_items": inv_total,
                "bom_templates": dishes_with_bom,
                "bom_items": bom_item_count,
            },
            "coverage": {
                "dish": {"rate": dish_coverage, "complete": dish_complete, "total": dish_total},
                "bom": {"rate": bom_coverage, "with_bom": dishes_with_bom, "total_dishes": dish_total},
                "inventory": {"rate": inv_coverage, "complete": inv_complete, "total": inv_total},
            },
            "relationship_density": relationship_density,
        }

    async def get_entity_stats(
        self,
        db: AsyncSession,
        store_id: str,
    ) -> dict:
        """
        实体详细统计

        按品类统计菜品分布 + 食材分类分布
        """
        # 菜品按品类分布
        dish_by_cat = await db.execute(
            select(
                DishCategory.name,
                func.count(Dish.id),
            )
            .outerjoin(
                Dish,
                and_(
                    Dish.category_id == DishCategory.id,
                    Dish.is_available.is_(True),
                ),
            )
            .where(DishCategory.store_id == store_id)
            .group_by(DishCategory.name)
        )
        dish_distribution = {(row[0] or "未分类"): row[1] for row in dish_by_cat.all()}

        # 食材按类别分布
        inv_by_cat = await db.execute(
            select(
                InventoryItem.category,
                func.count(InventoryItem.id),
            )
            .where(InventoryItem.store_id == store_id)
            .group_by(InventoryItem.category)
        )
        inv_distribution = {(row[0] or "未分类"): row[1] for row in inv_by_cat.all()}

        # 孤立菜品（有菜品但没BOM）
        orphan_dishes = (
            await db.scalar(
                select(func.count(Dish.id)).where(
                    Dish.store_id == store_id,
                    Dish.is_available.is_(True),
                    ~Dish.id.in_(
                        select(BOMTemplate.dish_id).where(
                            BOMTemplate.store_id == store_id,
                            BOMTemplate.is_active.is_(True),
                        )
                    ),
                )
            )
            or 0
        )

        return {
            "dish_by_category": dish_distribution,
            "inventory_by_category": inv_distribution,
            "orphan_dishes_no_bom": orphan_dishes,
        }

    async def get_data_issues(
        self,
        db: AsyncSession,
        store_id: str,
        limit: int = 20,
    ) -> List[dict]:
        """
        数据质量问题清单

        检测：缺价格的菜品、缺成本的食材、空BOM模板
        """
        issues = []

        # 缺价格的菜品
        no_price = await db.execute(
            select(Dish.id, Dish.name)
            .where(
                Dish.store_id == store_id,
                Dish.is_available.is_(True),
                Dish.price.is_(None),
            )
            .limit(limit)
        )
        for row in no_price.all():
            issues.append(
                {
                    "entity_type": "dish",
                    "entity_id": str(row[0]),
                    "entity_name": row[1],
                    "issue": "missing_price",
                    "severity": "high",
                }
            )

        # 缺单位成本的食材
        no_cost = await db.execute(
            select(InventoryItem.id, InventoryItem.name)
            .where(
                InventoryItem.store_id == store_id,
                InventoryItem.unit_cost.is_(None),
            )
            .limit(limit)
        )
        for row in no_cost.all():
            issues.append(
                {
                    "entity_type": "inventory_item",
                    "entity_id": str(row[0]),
                    "entity_name": row[1],
                    "issue": "missing_unit_cost",
                    "severity": "medium",
                }
            )

        # 空BOM模板（有模板但无明细项）
        empty_bom = await db.execute(
            select(BOMTemplate.id, BOMTemplate.dish_id)
            .where(
                BOMTemplate.store_id == store_id,
                BOMTemplate.is_active.is_(True),
                ~BOMTemplate.id.in_(select(func.distinct(BOMItem.bom_id))),
            )
            .limit(limit)
        )
        for row in empty_bom.all():
            issues.append(
                {
                    "entity_type": "bom_template",
                    "entity_id": str(row[0]),
                    "entity_name": f"BOM for dish {row[1]}",
                    "issue": "empty_bom_no_items",
                    "severity": "high",
                }
            )

        return issues


# 全局单例
ontology_agent_service = OntologyAgentService()
