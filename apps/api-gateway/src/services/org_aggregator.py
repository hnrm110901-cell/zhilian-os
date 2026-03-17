"""
OrgAggregator — 跨模块组织层级数据汇总

按组织层级上卷数据：
  门店快照 → 区域聚合 → 品牌聚合 → 集团聚合

每个层级的 OrgSnapshot 包含：
  - 营收（来自 daily_settlements）
  - 成本率（来自 cost_truth）
  - 人力（来自 employees）
  - KPI（来自 kpis）
  - 子节点快照列表（树形结构）
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import sqlalchemy as sa
import structlog

logger = structlog.get_logger()


@dataclass
class OrgSnapshot:
    """一个组织节点在某周期的数据快照"""
    node_id: str
    node_name: str
    node_type: str
    period: str                          # 格式: "2026-03" 或 "2026-03-17"

    # 财务
    revenue_total_fen: int = 0           # 营收（分）
    revenue_target_fen: int = 0          # 营收目标（分）
    cost_total_fen: int = 0              # 成本（分）
    cost_ratio: float = 0.0             # 成本率

    # 人力
    headcount: int = 0                   # 在职人数
    labor_cost_fen: int = 0             # 人力成本（分）
    labor_cost_ratio: float = 0.0       # 人力成本率

    # 绩效
    kpi_score: float = 0.0              # 综合 KPI 分
    store_count: int = 0                # 子门店数量

    # 子节点快照（树形递归）
    children: list[OrgSnapshot] = field(default_factory=list)

    @property
    def revenue_total_yuan(self) -> float:
        return self.revenue_total_fen / 100

    @property
    def revenue_achievement_rate(self) -> float:
        if self.revenue_target_fen == 0:
            return 0.0
        return self.revenue_total_fen / self.revenue_target_fen

    def to_dict(self, include_children=True) -> dict:
        d = {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "node_type": self.node_type,
            "period": self.period,
            "revenue_total_yuan": round(self.revenue_total_yuan, 2),
            "revenue_target_yuan": round(self.revenue_target_fen / 100, 2),
            "revenue_achievement_rate": round(self.revenue_achievement_rate * 100, 1),
            "cost_ratio": round(self.cost_ratio * 100, 1),
            "headcount": self.headcount,
            "labor_cost_ratio": round(self.labor_cost_ratio * 100, 1),
            "kpi_score": round(self.kpi_score, 1),
            "store_count": self.store_count,
        }
        if include_children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


class OrgAggregator:
    """
    按组织层级汇总数据
    使用方式：
        aggregator = OrgAggregator(db)
        snapshot = await aggregator.get_snapshot("reg-south", period="2026-03")
        # snapshot.revenue_total_yuan = 华南区本月总营收
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_snapshot(
        self,
        node_id: str,
        period: str,           # "2026-03" 月度 或 "2026-03-17" 日度
        include_children: bool = True,
    ) -> OrgSnapshot:
        """
        获取节点的聚合快照
        如果是叶子节点（门店）：直接查数据
        如果是中间节点（区域/品牌）：递归聚合子节点
        """
        from src.services.org_hierarchy_service import OrgHierarchyService
        from src.models.org_node import OrgNodeType
        svc = OrgHierarchyService(self.db)

        node = await svc.get_node(node_id)
        if not node:
            raise ValueError(f"节点不存在: {node_id}")

        # 获取子树内所有门店节点
        subtree = await svc.get_subtree(node_id)
        store_nodes = [n for n in subtree if n.node_type == OrgNodeType.STORE.value]
        store_ids = [n.store_ref_id or n.id for n in store_nodes]

        # 聚合各数据源（每个子方法内部处理异常，失败降级为0）
        revenue, target = await self._aggregate_revenue(store_ids, period)
        cost_ratio = await self._aggregate_cost_ratio(store_ids, period)
        headcount = await self._aggregate_headcount(store_ids)
        kpi_score = await self._aggregate_kpi(store_ids, period)

        snapshot = OrgSnapshot(
            node_id=node_id,
            node_name=node.name,
            node_type=node.node_type,
            period=period,
            revenue_total_fen=revenue,
            revenue_target_fen=target,
            cost_ratio=cost_ratio,
            headcount=headcount,
            kpi_score=kpi_score,
            store_count=len(store_ids),
        )

        # 递归构建子节点快照（仅下一层）
        if include_children:
            direct_children = [n for n in subtree if n.parent_id == node_id]
            for child in direct_children:
                child_snap = await self.get_snapshot(
                    child.id, period, include_children=False
                )
                snapshot.children.append(child_snap)

        return snapshot

    async def _aggregate_revenue(
        self, store_ids: list[str], period: str
    ) -> tuple[int, int]:
        """从 daily_settlements 汇总营收（分）"""
        if not store_ids:
            return 0, 0
        try:
            from src.models.daily_settlement import StoreDailySettlement
            is_monthly = len(period) == 7  # "2026-03"
            if is_monthly:
                year, month = period.split("-")
                date_filter = and_(
                    func.extract("year", StoreDailySettlement.settlement_date)
                        == int(year),
                    func.extract("month", StoreDailySettlement.settlement_date)
                        == int(month),
                )
            else:
                date_filter = (
                    func.cast(StoreDailySettlement.settlement_date, sa.Date) == period
                )

            result = await self.db.execute(
                select(
                    func.coalesce(func.sum(StoreDailySettlement.actual_revenue_fen), 0),
                    func.coalesce(func.sum(StoreDailySettlement.target_revenue_fen), 0),
                ).where(
                    StoreDailySettlement.store_id.in_(store_ids),
                    date_filter,
                )
            )
            row = result.one()
            return int(row[0]), int(row[1])
        except Exception as e:
            logger.warning("revenue_aggregation_failed", error=str(e))
            return 0, 0

    async def _aggregate_cost_ratio(
        self, store_ids: list[str], period: str
    ) -> float:
        """从 cost_truth 汇总成本率（加权平均）"""
        if not store_ids:
            return 0.0
        try:
            from src.models.cost_truth import CostTruth
            result = await self.db.execute(
                select(
                    func.avg(CostTruth.food_cost_ratio)
                ).where(
                    CostTruth.store_id.in_(store_ids),
                    func.cast(CostTruth.snapshot_date, sa.String).like(f"{period}%"),
                )
            )
            val = result.scalar()
            return float(val) if val else 0.0
        except Exception as e:
            logger.warning("cost_ratio_aggregation_failed", error=str(e))
            return 0.0

    async def _aggregate_headcount(self, store_ids: list[str]) -> int:
        """从 employees 汇总在职人数"""
        if not store_ids:
            return 0
        try:
            from src.models.employee import Employee
            result = await self.db.execute(
                select(func.count(Employee.id)).where(
                    Employee.store_id.in_(store_ids),
                    Employee.is_active == True,
                )
            )
            return int(result.scalar() or 0)
        except Exception as e:
            logger.warning("headcount_aggregation_failed", error=str(e))
            return 0

    async def _aggregate_kpi(self, store_ids: list[str], period: str) -> float:
        """从 kpis 汇总 KPI 平均分"""
        if not store_ids:
            return 0.0
        try:
            from src.models.kpi import KPI
            result = await self.db.execute(
                select(func.avg(KPI.score)).where(
                    KPI.store_id.in_(store_ids),
                    KPI.period == period,
                )
            )
            val = result.scalar()
            return float(val) if val else 0.0
        except Exception as e:
            logger.warning("kpi_aggregation_failed", error=str(e))
            return 0.0
