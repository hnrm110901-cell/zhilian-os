"""
损耗监控服务（Waste Guard Service）

职责：
  1. Top5 损耗食材（按¥金额排序，含归因）
  2. 门店损耗率汇总（损耗¥ vs 营收¥）
  3. BOM 理论消耗 vs 实际损耗差异（找出偏差最大的菜品）

设计约定：
  - 主数据源：inventory_transactions（type='waste'）—— total_cost 字段已含¥金额（分）
  - 归因数据：waste_events.root_cause + event_type（由 WasteReasoningEngine 回写）
  - 所有 SQL 使用 text() 参数化绑定，禁止字符串拼接
  - 输出字段后缀 _yuan 表示已换算成元（÷100）
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 根因 → 建议行动映射 ─────────────────────────────────────────────────────
_ROOT_CAUSE_ACTIONS: Dict[str, str] = {
    "staff_error": "建议针对相关岗位开展操作规范培训（1周内）",
    "food_quality": "建议检查供应商批次质量，评估换供应商可行性",
    "over_prep": "建议根据近7天客流数据调整备餐量（上浮系数建议1.15）",
    "spoilage": "建议缩短该食材采购周期或改用每日采购模式",
    "bom_deviation": "建议更新 BOM 配方——实际用量已系统性超出标准",
    "transfer_loss": "建议优化称重/分拣流程，配置精准计量工具",
    "drop_damage": "建议在高损耗时段加强备货区巡查或调整摆放位置",
    "unknown": "建议开启损耗事件追踪，记录损耗发生原因",
}

_DEFAULT_ACTION = "建议启用损耗事件记录功能，逐步建立归因数据"


def _action_for_causes(root_causes: List[dict]) -> str:
    """根据主要根因返回建议行动"""
    if not root_causes:
        return _DEFAULT_ACTION
    top_cause = root_causes[0].get("root_cause") or root_causes[0].get("event_type") or "unknown"
    return _ROOT_CAUSE_ACTIONS.get(top_cause, _DEFAULT_ACTION)


class WasteGuardService:
    """损耗监控服务（全静态方法）"""

    # ── Top5 损耗食材（核心方法） ───────────────────────────────────────────────

    @staticmethod
    async def get_top5_waste(
        store_id: str,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> dict:
        """
        查询指定门店在日期区间内 Top 5 损耗食材，按¥金额降序排列。

        数据来源：
          - ¥ 金额：inventory_transactions (type='waste') 的 ABS(SUM(total_cost))
          - 归因：waste_events 的 root_cause / event_type 分布
        """
        end_exclusive = end_date + timedelta(days=1)

        # ── SQL 1：Top 5 损耗食材（含¥金额 & 数量） ───────────────────────────
        top5_result = await db.execute(
            text("""
                SELECT
                    it.item_id,
                    ii.name        AS item_name,
                    ii.category,
                    ii.unit,
                    ABS(SUM(it.total_cost))  AS waste_cost_fen,
                    ABS(SUM(it.quantity))    AS waste_qty
                FROM inventory_transactions it
                JOIN inventory_items ii ON it.item_id = ii.id
                WHERE it.store_id        = :sid
                  AND it.transaction_type = 'waste'
                  AND it.transaction_time >= :start
                  AND it.transaction_time  < :end
                GROUP BY it.item_id, ii.name, ii.category, ii.unit
                ORDER BY waste_cost_fen DESC
                LIMIT 5
            """),
            {"sid": store_id, "start": start_date, "end": end_exclusive},
        )
        top5_rows = top5_result.fetchall()

        # ── SQL 2：总损耗¥（用于计算占比） ─────────────────────────────────────
        total_result = await db.execute(
            text("""
                SELECT COALESCE(ABS(SUM(total_cost)), 0) AS total_waste_fen
                FROM inventory_transactions
                WHERE store_id        = :sid
                  AND transaction_type = 'waste'
                  AND transaction_time >= :start
                  AND transaction_time  < :end
            """),
            {"sid": store_id, "start": start_date, "end": end_exclusive},
        )
        total_waste_fen = int(total_result.scalar() or 0)

        # ── 收集 Top5 item_id 列表，批量查归因 ─────────────────────────────────
        top5_item_ids = [row.item_id for row in top5_rows]

        attribution_map: Dict[str, List[dict]] = {iid: [] for iid in top5_item_ids}
        if top5_item_ids:
            attr_result = await db.execute(
                text("""
                    SELECT
                        we.ingredient_id,
                        COALESCE(we.root_cause, 'unknown')  AS root_cause,
                        we.event_type,
                        COUNT(*)                             AS event_count
                    FROM waste_events we
                    WHERE we.store_id       = :sid
                      AND we.ingredient_id  = ANY(:ids)
                      AND we.occurred_at   >= :start
                      AND we.occurred_at    < :end
                    GROUP BY we.ingredient_id, we.root_cause, we.event_type
                    ORDER BY we.ingredient_id, event_count DESC
                """),
                {
                    "sid": store_id,
                    "ids": top5_item_ids,
                    "start": start_date,
                    "end": end_exclusive,
                },
            )
            for row in attr_result.fetchall():
                iid = str(row.ingredient_id)
                if iid in attribution_map:
                    attribution_map[iid].append(
                        {
                            "root_cause": row.root_cause,
                            "event_type": row.event_type,
                            "event_count": int(row.event_count),
                        }
                    )

        # ── 拼装 Top5 列表 ─────────────────────────────────────────────────────
        top5: List[dict] = []
        for rank, row in enumerate(top5_rows, start=1):
            waste_cost_fen = int(row.waste_cost_fen or 0)
            root_causes = attribution_map.get(str(row.item_id), [])
            top5.append(
                {
                    "rank": rank,
                    "item_id": str(row.item_id),
                    "item_name": row.item_name,
                    "category": row.category or "",
                    "unit": row.unit or "",
                    "waste_cost_fen": waste_cost_fen,
                    "waste_cost_yuan": round(waste_cost_fen / 100, 2),
                    "waste_qty": round(float(row.waste_qty or 0), 3),
                    "cost_share_pct": round(waste_cost_fen / total_waste_fen * 100, 1) if total_waste_fen > 0 else 0.0,
                    "root_causes": root_causes,
                    "action": _action_for_causes(root_causes),
                }
            )

        return {
            "store_id": store_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_waste_fen": total_waste_fen,
            "total_waste_yuan": round(total_waste_fen / 100, 2),
            "top5": top5,
        }

    # ── 门店损耗率汇总 ──────────────────────────────────────────────────────────

    @staticmethod
    async def get_waste_rate_summary(
        store_id: str,
        start_date: date,
        end_date: date,
        db: AsyncSession,
    ) -> dict:
        """
        计算门店损耗率：损耗¥ / 营收¥，及与上周期对比。

        返回：
          - waste_rate_pct：损耗率（%）
          - waste_rate_status：ok / warning / critical
          - period_comparison：本期 vs 上期损耗¥对比
        """
        end_exclusive = end_date + timedelta(days=1)
        days = (end_date - start_date).days + 1

        # 本期损耗¥
        waste_result = await db.execute(
            text("""
                SELECT COALESCE(ABS(SUM(total_cost)), 0) AS waste_fen
                FROM inventory_transactions
                WHERE store_id        = :sid
                  AND transaction_type = 'waste'
                  AND transaction_time >= :start
                  AND transaction_time  < :end
            """),
            {"sid": store_id, "start": start_date, "end": end_exclusive},
        )
        waste_fen = int(waste_result.scalar() or 0)

        # 本期营收¥
        revenue_result = await db.execute(
            text("""
                SELECT COALESCE(SUM(total_amount), 0) AS revenue_fen
                FROM orders
                WHERE store_id  = :sid
                  AND created_at >= :start
                  AND created_at  < :end
            """),
            {"sid": store_id, "start": start_date, "end": end_exclusive},
        )
        revenue_fen = int(revenue_result.scalar() or 0)

        # 上一期同长度窗口
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days - 1)
        prev_end_exclusive = prev_end + timedelta(days=1)

        prev_waste_result = await db.execute(
            text("""
                SELECT COALESCE(ABS(SUM(total_cost)), 0) AS waste_fen
                FROM inventory_transactions
                WHERE store_id        = :sid
                  AND transaction_type = 'waste'
                  AND transaction_time >= :start
                  AND transaction_time  < :end
            """),
            {"sid": store_id, "start": prev_start, "end": prev_end_exclusive},
        )
        prev_waste_fen = int(prev_waste_result.scalar() or 0)

        # 计算损耗率
        waste_rate_pct = round(waste_fen / revenue_fen * 100, 2) if revenue_fen > 0 else 0.0

        # 状态判定（行业通常要求损耗率 < 3%）
        if waste_rate_pct >= 5.0:
            waste_rate_status = "critical"
        elif waste_rate_pct >= 3.0:
            waste_rate_status = "warning"
        else:
            waste_rate_status = "ok"

        # 环比变化
        waste_change_fen = waste_fen - prev_waste_fen
        waste_change_pct = round(waste_change_fen / prev_waste_fen * 100, 1) if prev_waste_fen > 0 else None

        return {
            "store_id": store_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "waste_cost_fen": waste_fen,
            "waste_cost_yuan": round(waste_fen / 100, 2),
            "revenue_fen": revenue_fen,
            "revenue_yuan": round(revenue_fen / 100, 2),
            "waste_rate_pct": waste_rate_pct,
            "waste_rate_status": waste_rate_status,
            "prev_period": {
                "start_date": prev_start.isoformat(),
                "end_date": prev_end.isoformat(),
                "waste_cost_fen": prev_waste_fen,
                "waste_cost_yuan": round(prev_waste_fen / 100, 2),
            },
            "waste_change_yuan": round(waste_change_fen / 100, 2),
            "waste_change_pct": waste_change_pct,
        }

    # ── BOM 差异：理论 vs 实际损耗（菜品维度） ─────────────────────────────────

    @staticmethod
    async def get_bom_waste_deviation(
        store_id: str,
        start_date: date,
        end_date: date,
        db: AsyncSession,
        top_n: int = 5,
    ) -> dict:
        """
        从 waste_events 汇总 BOM 偏差最大的菜品（按 SUM(variance_qty × unit_cost) 排序）。

        要求 WasteEvent.variance_qty 和关联 InventoryItem.unit_cost 均有值。
        """
        end_exclusive = end_date + timedelta(days=1)

        result = await db.execute(
            text("""
                SELECT
                    we.ingredient_id,
                    ii.name               AS item_name,
                    ii.unit,
                    ii.unit_cost          AS unit_cost_fen,
                    SUM(we.variance_qty)  AS total_variance_qty,
                    ABS(SUM(we.variance_qty)) * COALESCE(ii.unit_cost, 0)
                                          AS variance_cost_fen,
                    AVG(we.variance_pct)  AS avg_variance_pct,
                    COUNT(*)              AS event_count
                FROM waste_events we
                JOIN inventory_items ii ON we.ingredient_id = ii.id
                WHERE we.store_id    = :sid
                  AND we.occurred_at >= :start
                  AND we.occurred_at  < :end
                  AND we.variance_qty IS NOT NULL
                GROUP BY we.ingredient_id, ii.name, ii.unit, ii.unit_cost
                ORDER BY variance_cost_fen DESC
                LIMIT :top_n
            """),
            {"sid": store_id, "start": start_date, "end": end_exclusive, "top_n": top_n},
        )
        rows = result.fetchall()

        items = []
        for rank, row in enumerate(rows, start=1):
            var_cost_fen = int(row.variance_cost_fen or 0)
            items.append(
                {
                    "rank": rank,
                    "ingredient_id": str(row.ingredient_id),
                    "item_name": row.item_name,
                    "unit": row.unit or "",
                    "unit_cost_fen": int(row.unit_cost_fen or 0),
                    "unit_cost_yuan": round(int(row.unit_cost_fen or 0) / 100, 2),
                    "total_variance_qty": round(float(row.total_variance_qty or 0), 3),
                    "variance_cost_fen": var_cost_fen,
                    "variance_cost_yuan": round(var_cost_fen / 100, 2),
                    "avg_variance_pct": round(float(row.avg_variance_pct or 0) * 100, 1),
                    "event_count": int(row.event_count),
                }
            )

        return {
            "store_id": store_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "top_n": top_n,
            "items": items,
        }

    # ── 便捷入口：综合损耗报告 ──────────────────────────────────────────────────

    @staticmethod
    async def get_full_waste_report(
        store_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        db: AsyncSession = None,
    ) -> dict:
        """
        综合损耗报告：Top5 + 损耗率汇总 + BOM偏差。

        默认分析过去7天。
        """
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=6)

        top5 = await WasteGuardService.get_top5_waste(store_id, start_date, end_date, db)
        summary = await WasteGuardService.get_waste_rate_summary(store_id, start_date, end_date, db)
        bom_dev = await WasteGuardService.get_bom_waste_deviation(store_id, start_date, end_date, db)

        return {
            "store_id": store_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "waste_rate_pct": summary["waste_rate_pct"],
            "waste_rate_status": summary["waste_rate_status"],
            "total_waste_yuan": summary["waste_cost_yuan"],
            "waste_change_yuan": summary["waste_change_yuan"],
            "top5": top5["top5"],
            "bom_deviation": bom_dev["items"],
        }

    # ── 实时告警：检测并推送偏差超阈值的食材 ──────────────────────────────────

    @staticmethod
    async def check_and_alert(
        session: Any,
        store_id: str,
        tenant_id: str,
        variances: List[Dict],
        threshold_pct: float = 10.0,
    ) -> List[str]:
        """
        检查 variances 中 |diff_rate_pct| > threshold_pct 的食材，推送告警并返回 event_id 列表。
        超时和企微失败均静默忽略。
        """
        event_ids: List[str] = []
        above = [v for v in variances if abs(v.get("diff_rate_pct", 0)) > threshold_pct]
        if not above:
            return []

        for v in above:
            event_id = f"WG-{uuid.uuid4().hex[:8].upper()}"
            try:
                from src.services import waste_reasoning_service as _wrs

                reasoning = await asyncio.wait_for(
                    _wrs.run_waste_reasoning(v.get("ingredient_id"), store_id, session),
                    timeout=10.0,
                )
                top3 = reasoning.get("top3_root_causes", [])
                action = _action_for_causes(top3)

                from src.services.wechat_work_message_service import wechat_work_message_service as _wms

                await asyncio.wait_for(
                    _wms.send_card_message(
                        user_id=tenant_id,
                        title=f"损耗预警：{v.get('ingredient_name', v.get('ingredient_id'))}",
                        description=f"偏差率 {v.get('diff_rate_pct', 0):.1f}%，建议：{action}",
                        url="",
                        btntxt="查看详情",
                    ),
                    timeout=5.0,
                )
                event_ids.append(event_id)
            except Exception:
                pass

        return event_ids

    # ── 月度损耗报告（四维：食材/员工/班次/渠道） ─────────────────────────────

    @staticmethod
    async def generate_monthly_report(
        session: Any,
        store_id: str,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        """生成月度四维损耗报告。"""
        try:
            from sqlalchemy import func, select
            from src.models.waste_event import WasteEvent

            start = date(year, month, 1)
            if month == 12:
                end = date(year + 1, 1, 1)
            else:
                end = date(year, month + 1, 1)

            # 按食材维度
            ing_stmt = (
                select(
                    WasteEvent.ingredient_id,
                    func.sum(WasteEvent.waste_amount).label("total_qty"),
                    func.count(WasteEvent.id).label("count"),
                )
                .where(WasteEvent.store_id == store_id)
                .where(WasteEvent.event_time >= start)
                .where(WasteEvent.event_time < end)
                .group_by(WasteEvent.ingredient_id)
                .order_by(func.sum(WasteEvent.waste_amount).desc())
            )
            by_ingredient = [
                {"ingredient_id": r.ingredient_id, "total_qty": float(r.total_qty or 0), "count": r.count}
                for r in (await session.execute(ing_stmt)).all()
            ]

            # 按员工维度
            staff_stmt = (
                select(
                    WasteEvent.staff_id,
                    func.count(WasteEvent.id).label("count"),
                    func.avg(WasteEvent.waste_amount).label("avg_qty"),
                )
                .where(WasteEvent.store_id == store_id)
                .where(WasteEvent.event_time >= start)
                .where(WasteEvent.event_time < end)
                .group_by(WasteEvent.staff_id)
            )
            by_staff = [
                {"staff_id": r.staff_id, "count": r.count, "avg_qty": float(r.avg_qty or 0)}
                for r in (await session.execute(staff_stmt)).all()
            ]

            by_shift: List[Dict] = []
            by_channel: List[Dict] = []

        except Exception:
            by_ingredient = []
            by_staff = []
            by_shift = []
            by_channel = []

        return {
            "period": {"year": year, "month": month},
            "by_ingredient": by_ingredient,
            "by_staff": by_staff,
            "by_shift": by_shift,
            "by_channel": by_channel,
        }

    # ── 跨店 BOM 漂移告警 ──────────────────────────────────────────────────────

    @staticmethod
    async def cross_store_bom_drift_alert(
        session: Any,
        tenant_id: str,
        threshold_pct: float = 20.0,
    ) -> List[Dict]:
        """
        检测同一菜品在不同门店的 BOM 用料偏差，超过阈值时触发告警。
        返回告警记录列表。
        """
        try:
            from sqlalchemy import func, select
            from src.models.bom import BOMItem, BOMTemplate

            stmt = (
                select(
                    BOMTemplate.dish_id,
                    BOMTemplate.store_id,
                    func.sum(BOMItem.standard_qty).label("total_qty"),
                )
                .join(BOMItem, BOMItem.bom_id == BOMTemplate.id)
                .where(BOMTemplate.scope_id == tenant_id)
                .group_by(BOMTemplate.dish_id, BOMTemplate.store_id)
            )
            rows = (await session.execute(stmt)).all()

        except Exception:
            return []

        if not rows:
            return []

        # 按菜品聚合各门店用量
        dish_store_qty: Dict[str, Dict[str, float]] = {}
        for r in rows:
            dish_store_qty.setdefault(r.dish_id, {})[r.store_id] = float(r.total_qty or 0)

        alerts: List[Dict] = []
        for dish_id, store_qtys in dish_store_qty.items():
            if len(store_qtys) < 2:
                continue
            values = list(store_qtys.values())
            avg_qty = sum(values) / len(values)
            if avg_qty == 0:
                continue
            for store_id, qty in store_qtys.items():
                drift_pct = abs(qty - avg_qty) / avg_qty * 100
                if drift_pct > threshold_pct:
                    alert = {
                        "dish_id": dish_id,
                        "store_id": store_id,
                        "qty": qty,
                        "avg_qty": avg_qty,
                        "drift_pct": round(drift_pct, 2),
                    }
                    alerts.append(alert)
                    try:
                        from src.services.wechat_work_message_service import wechat_work_message_service as _wms

                        await asyncio.wait_for(
                            _wms.send_card_message(
                                user_id=tenant_id,
                                title=f"BOM跨店偏差预警：{dish_id}",
                                description=f"门店{store_id}用量{qty:.1f}，均值{avg_qty:.1f}，偏差{drift_pct:.1f}%",
                                url="",
                                btntxt="查看详情",
                            ),
                            timeout=5.0,
                        )
                    except Exception:
                        pass

        return alerts
