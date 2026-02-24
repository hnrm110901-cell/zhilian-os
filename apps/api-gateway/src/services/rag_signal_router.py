"""
RAG信号路由器 - 解决向量检索无法区分数值差异的问题

问题：MiniLM-384 对 "损耗率14%" 和 "损耗率3%" 的向量相似度极高，
      导致数值类查询的AI建议不准确。

解决方案：
  - 数值/结构化查询 → PostgreSQL 精确查询
  - 语义/案例查询   → Qdrant 向量检索（保持原有路径）
"""
import re
import os
from enum import Enum
from typing import Dict, Any, Optional
from datetime import date, timedelta

import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Query classification
# ---------------------------------------------------------------------------

class QuerySignal(str, Enum):
    NUMERICAL = "numerical"   # 数值类：损耗率、营收、KPI 指标
    SEMANTIC  = "semantic"    # 语义类：SOP 查询、历史案例


_NUMERICAL_PATTERNS = [
    r"损耗[率量]",
    r"浪费[率量]",
    r"waste.{0,5}rate",
    r"loss.{0,5}rate",
    r"营收|销售额|收入",
    r"revenue|sales",
    r"客单价|avg.{0,5}order",
    r"客流[量数]|customer.{0,5}count",
    r"订单[数量]|order.{0,5}count",
    r"任务完成率|completion.{0,5}rate",
    r"库存[量数]|inventory.{0,5}level",
    r"环比|同比|增长率|change.{0,5}rate",
    r"\d+\s*[%％]",
    r"kpi|指标",
]

_NUMERICAL_RE = re.compile("|".join(_NUMERICAL_PATTERNS), re.IGNORECASE)


def classify_query(query: str) -> QuerySignal:
    """判断查询类型：数值型 or 语义型"""
    if _NUMERICAL_RE.search(query):
        return QuerySignal.NUMERICAL
    return QuerySignal.SEMANTIC


# ---------------------------------------------------------------------------
# PostgreSQL numerical query handlers
# ---------------------------------------------------------------------------

_DATA_DAYS = int(os.getenv("RAG_DATA_DAYS", "30"))


async def _query_loss_rate(session, store_id: str) -> Dict[str, Any]:
    """计算近 N 天损耗率 = 损耗量 / (使用量 + 损耗量)"""
    from sqlalchemy import select, func
    from src.models.inventory import InventoryTransaction, TransactionType

    cutoff = date.today() - timedelta(days=_DATA_DAYS)
    result = await session.execute(
        select(
            InventoryTransaction.transaction_type,
            func.sum(func.abs(InventoryTransaction.quantity)).label("total_qty"),
        )
        .where(
            InventoryTransaction.store_id == store_id,
            InventoryTransaction.transaction_time >= cutoff,
            InventoryTransaction.transaction_type.in_(
                [TransactionType.WASTE, TransactionType.USAGE]
            ),
        )
        .group_by(InventoryTransaction.transaction_type)
    )
    rows = result.all()
    waste = sum(r.total_qty for r in rows if r.transaction_type == TransactionType.WASTE)
    usage = sum(r.total_qty for r in rows if r.transaction_type == TransactionType.USAGE)
    total = waste + usage
    loss_rate = round(waste / total * 100, 2) if total > 0 else 0.0
    return {
        "metric": "loss_rate",
        "period_days": _DATA_DAYS,
        "waste_qty": round(waste, 2),
        "usage_qty": round(usage, 2),
        "loss_rate_pct": loss_rate,
        "summary": f"近{_DATA_DAYS}天损耗率为 {loss_rate}%（损耗量 {waste:.1f}，使用量 {usage:.1f}）",
    }


async def _query_revenue(session, store_id: str) -> Dict[str, Any]:
    """查询近 N 天营收汇总"""
    from sqlalchemy import select, func
    from src.models.daily_report import DailyReport

    cutoff = date.today() - timedelta(days=_DATA_DAYS)
    result = await session.execute(
        select(
            func.sum(DailyReport.total_revenue).label("total"),
            func.avg(DailyReport.total_revenue).label("avg_daily"),
            func.sum(DailyReport.customer_count).label("customers"),
            func.avg(DailyReport.revenue_change_rate).label("avg_change"),
            func.count(DailyReport.id).label("days"),
        ).where(
            DailyReport.store_id == store_id,
            DailyReport.report_date >= cutoff,
        )
    )
    row = result.one()
    total_yuan = round((row.total or 0) / 100, 2)
    avg_yuan   = round((row.avg_daily or 0) / 100, 2)
    return {
        "metric": "revenue",
        "period_days": _DATA_DAYS,
        "total_revenue_yuan": total_yuan,
        "avg_daily_revenue_yuan": avg_yuan,
        "total_customers": row.customers or 0,
        "avg_revenue_change_rate_pct": round(row.avg_change or 0, 2),
        "data_days": row.days or 0,
        "summary": (
            f"近{_DATA_DAYS}天总营收 {total_yuan} 元，"
            f"日均 {avg_yuan} 元，"
            f"累计客流 {row.customers or 0} 人次"
        ),
    }


async def _query_kpi(session, store_id: str) -> Dict[str, Any]:
    """查询近 N 天综合 KPI"""
    from sqlalchemy import select, func
    from src.models.daily_report import DailyReport

    cutoff = date.today() - timedelta(days=_DATA_DAYS)
    result = await session.execute(
        select(
            func.avg(DailyReport.task_completion_rate).label("avg_task"),
            func.avg(DailyReport.revenue_change_rate).label("avg_rev_change"),
            func.avg(DailyReport.order_change_rate).label("avg_ord_change"),
            func.avg(DailyReport.customer_change_rate).label("avg_cust_change"),
            func.sum(DailyReport.service_issue_count).label("total_issues"),
            func.sum(DailyReport.inventory_alert_count).label("total_alerts"),
            func.count(DailyReport.id).label("days"),
        ).where(
            DailyReport.store_id == store_id,
            DailyReport.report_date >= cutoff,
        )
    )
    row = result.one()
    return {
        "metric": "kpi",
        "period_days": _DATA_DAYS,
        "avg_task_completion_rate_pct": round(row.avg_task or 0, 2),
        "avg_revenue_change_rate_pct": round(row.avg_rev_change or 0, 2),
        "avg_order_change_rate_pct": round(row.avg_ord_change or 0, 2),
        "avg_customer_change_rate_pct": round(row.avg_cust_change or 0, 2),
        "total_service_issues": row.total_issues or 0,
        "total_inventory_alerts": row.total_alerts or 0,
        "data_days": row.days or 0,
        "summary": (
            f"近{_DATA_DAYS}天：任务完成率 {row.avg_task or 0:.1f}%，"
            f"营收环比 {row.avg_rev_change or 0:+.1f}%，"
            f"服务问题 {row.total_issues or 0} 次"
        ),
    }


async def _query_inventory(session, store_id: str) -> Dict[str, Any]:
    """查询当前库存状态"""
    from sqlalchemy import select, func
    from src.models.inventory import InventoryItem, InventoryStatus

    result = await session.execute(
        select(
            func.count(InventoryItem.id).label("total"),
            func.count(InventoryItem.id).filter(
                InventoryItem.status == InventoryStatus.LOW
            ).label("low"),
            func.count(InventoryItem.id).filter(
                InventoryItem.status == InventoryStatus.CRITICAL
            ).label("critical"),
            func.count(InventoryItem.id).filter(
                InventoryItem.status == InventoryStatus.OUT_OF_STOCK
            ).label("out"),
        ).where(InventoryItem.store_id == store_id)
    )
    row = result.one()
    return {
        "metric": "inventory",
        "total_items": row.total or 0,
        "low_stock_items": row.low or 0,
        "critical_items": row.critical or 0,
        "out_of_stock_items": row.out or 0,
        "summary": (
            f"库存共 {row.total or 0} 种，"
            f"低库存 {row.low or 0} 种，"
            f"严重不足 {row.critical or 0} 种，"
            f"缺货 {row.out or 0} 种"
        ),
    }


# ---------------------------------------------------------------------------
# Router entry point
# ---------------------------------------------------------------------------

_LOSS_RE    = re.compile(r"损耗[率量]|waste.{0,5}rate|loss.{0,5}rate", re.IGNORECASE)
_REVENUE_RE = re.compile(r"营收|销售额|收入|revenue|sales|客单价", re.IGNORECASE)
_KPI_RE     = re.compile(r"kpi|指标|完成率|环比|同比|增长率", re.IGNORECASE)
_INV_RE     = re.compile(r"库存[量数]|inventory.{0,5}level|缺货|低库存", re.IGNORECASE)


async def route_numerical_query(query: str, store_id: str) -> Optional[Dict[str, Any]]:
    """
    对数值类查询执行 PostgreSQL 精确查询。

    Returns:
        结构化数据字典（含 summary 字段），或 None（无法匹配具体指标时）
    """
    from src.core.database import get_db_session

    try:
        async with get_db_session() as session:
            if _LOSS_RE.search(query):
                data = await _query_loss_rate(session, store_id)
            elif _REVENUE_RE.search(query):
                data = await _query_revenue(session, store_id)
            elif _KPI_RE.search(query):
                data = await _query_kpi(session, store_id)
            elif _INV_RE.search(query):
                data = await _query_inventory(session, store_id)
            else:
                # 数值类但无法细分 → 返回 KPI 综合数据
                data = await _query_kpi(session, store_id)

        logger.info(
            "rag_router.numerical_query",
            store_id=store_id,
            metric=data.get("metric"),
            query_snippet=query[:60],
        )
        return data

    except Exception as exc:
        logger.error("rag_router.numerical_query_failed", error=str(exc), store_id=store_id)
        return None
