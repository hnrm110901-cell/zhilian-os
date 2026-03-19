"""
TenantReplicator Service — 多客户复制引擎（Sprint 6）

9-Agent 终态中的平台能力，核心功能：
1. 新租户初始化（从模板门店克隆全套本体）
2. 入驻进度追踪（菜品/BOM/食材/员工 完成率）
3. 入驻时间估算（基于历史数据）

定位：新客户快速入驻的自动化引擎，降低实施成本
复用：基于 StoreOntologyReplicator 的克隆能力
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.bom import BOMTemplate
from src.models.dish import Dish
from src.models.hr.person import Person
from src.models.inventory import InventoryItem
from src.models.store import Store

logger = logging.getLogger(__name__)


# ── 纯函数 ──────────────────────────────────────────────────────


def compute_onboarding_progress(
    dish_count: int,
    bom_count: int,
    inventory_count: int,
    employee_count: int,
    min_dishes: int = 20,
    min_boms: int = 10,
    min_inventory: int = 30,
    min_employees: int = 5,
) -> dict:
    """
    入驻完成度

    各维度独立计算，超过基准线即100%
    返回：各维度进度 + 综合进度
    """
    dish_pct = min(dish_count / max(min_dishes, 1), 1.0)
    bom_pct = min(bom_count / max(min_boms, 1), 1.0)
    inv_pct = min(inventory_count / max(min_inventory, 1), 1.0)
    emp_pct = min(employee_count / max(min_employees, 1), 1.0)

    # 综合进度（加权）
    overall = dish_pct * 0.30 + bom_pct * 0.25 + inv_pct * 0.25 + emp_pct * 0.20

    return {
        "dish_progress": round(dish_pct, 4),
        "bom_progress": round(bom_pct, 4),
        "inventory_progress": round(inv_pct, 4),
        "employee_progress": round(emp_pct, 4),
        "overall_progress": round(overall, 4),
    }


def estimate_onboarding_days(overall_progress: float) -> int:
    """
    估算剩余入驻天数

    基于经验值：完整入驻约7天
    进度越高，剩余天数越少
    """
    if overall_progress >= 1.0:
        return 0
    remaining = 1.0 - overall_progress
    # 基准7天，按剩余比例估算
    return max(1, round(remaining * 7))


def classify_onboarding_status(overall_progress: float) -> str:
    """
    入驻状态分级

    completed: 100%
    almost_ready: ≥ 80%
    in_progress: ≥ 40%
    just_started: < 40%
    """
    if overall_progress >= 1.0:
        return "completed"
    if overall_progress >= 0.80:
        return "almost_ready"
    if overall_progress >= 0.40:
        return "in_progress"
    return "just_started"


class TenantReplicatorService:
    """多客户复制引擎"""

    async def get_onboarding_status(
        self,
        db: AsyncSession,
        store_id: str,
    ) -> dict:
        """
        门店入驻进度

        返回：各维度数据量 + 完成进度 + 状态 + 预计剩余天数
        """
        dish_count = (
            await db.scalar(
                select(func.count(Dish.id)).where(
                    Dish.store_id == store_id,
                    Dish.is_available.is_(True),
                )
            )
            or 0
        )

        bom_count = (
            await db.scalar(
                select(func.count(BOMTemplate.id)).where(
                    BOMTemplate.store_id == store_id,
                    BOMTemplate.is_active.is_(True),
                )
            )
            or 0
        )

        inventory_count = (
            await db.scalar(
                select(func.count(InventoryItem.id)).where(
                    InventoryItem.store_id == store_id,
                )
            )
            or 0
        )

        employee_count = (
            await db.scalar(
                select(func.count(Person.id)).where(
                    Person.store_id == store_id,
                    Person.is_active.is_(True),
                )
            )
            or 0
        )

        progress = compute_onboarding_progress(
            dish_count,
            bom_count,
            inventory_count,
            employee_count,
        )
        status = classify_onboarding_status(progress["overall_progress"])
        est_days = estimate_onboarding_days(progress["overall_progress"])

        return {
            "store_id": store_id,
            "counts": {
                "dishes": dish_count,
                "bom_templates": bom_count,
                "inventory_items": inventory_count,
                "employees": employee_count,
            },
            "progress": progress,
            "status": status,
            "estimated_remaining_days": est_days,
        }

    async def replicate_store(
        self,
        db: AsyncSession,
        source_store_id: str,
        target_store_id: str,
    ) -> dict:
        """
        从源门店复制本体到目标门店

        委托给 StoreOntologyReplicator 执行克隆
        返回：克隆报告
        """
        from src.services.store_ontology_replicator import StoreOntologyReplicator

        replicator = StoreOntologyReplicator(db)

        # 获取目标门店名称
        target_store = await db.scalar(select(Store.name).where(Store.id == target_store_id))
        target_name = target_store or target_store_id

        report = await replicator.replicate(
            source_store_id=source_store_id,
            target_store_id=target_store_id,
            target_store_name=target_name,
        )
        return report

    async def get_multi_store_onboarding(
        self,
        db: AsyncSession,
        store_ids: Optional[List[str]] = None,
    ) -> List[dict]:
        """
        多门店入驻进度一览

        用于总部查看所有门店的数据就绪程度
        """
        # 获取门店列表
        store_query = select(Store.id, Store.name).where(Store.is_active.is_(True))
        if store_ids:
            store_query = store_query.where(Store.id.in_(store_ids))

        stores = await db.execute(store_query)
        results = []

        for row in stores.all():
            sid, sname = row[0], row[1]
            status = await self.get_onboarding_status(db, str(sid))
            status["store_name"] = sname
            results.append(status)

        # 按综合进度排序（低的排前面，方便关注）
        results.sort(key=lambda x: x["progress"]["overall_progress"])
        return results


# 全局单例
tenant_replicator_service = TenantReplicatorService()
