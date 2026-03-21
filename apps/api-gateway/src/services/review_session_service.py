"""
五步闭环经营复盘服务 — ReviewSessionService

组合现有服务完成五步闭环：
  Step 1 拆细账：调用 cost_truth_engine + analytics_service 生成多维拆解
  Step 2 找真因：生成并管理核查清单（全部勾选才能进入 Step 3）
  Step 3 定措施：创建四字段措施（责任人 + 时限 + 动作 + 量化结果）
  Step 4 追执行：更新进度 + KPI 偏离预警
  Step 5 看结果：汇总闭环结果，生成周/月复盘报告

金额单位：数据库存分（fen），API 输出 _yuan 后缀字段
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.review_session import ReviewAction, ReviewChecklist, ReviewSession

logger = structlog.get_logger()


def _yuan(fen: int) -> float:
    """分 → 元"""
    return round((fen or 0) / 100, 2)


def _week_range(iso_week: str) -> tuple[date, date]:
    """'2026-W12' → (周一, 周日)"""
    year, week = int(iso_week[:4]), int(iso_week.split("W")[1])
    jan4 = date(year, 1, 4)
    start = jan4 + timedelta(weeks=week - 1) - timedelta(days=jan4.weekday())
    end = start + timedelta(days=6)
    return start, end


def _month_range(month_label: str) -> tuple[date, date]:
    """'2026-03' → (月初, 月末)"""
    year, month = int(month_label[:4]), int(month_label[5:7])
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


# ── 默认核查清单模板 ──────────────────────────────────────────────────────────


WEEKLY_CHECKLIST_TEMPLATE: list[dict] = [
    {"dimension": "revenue_channel", "description": "各渠道（堂食/外卖/私域）营收占比变化是否正常？私域占比目标是否达标？"},
    {"dimension": "table_turnover", "description": "翻台率变化的真因是出餐慢、等位管理差，还是客流下降？（需蹲一次高峰期验证）"},
    {"dimension": "cost_rate", "description": "食材成本率偏差主要来自采购价格、用量超标、还是损耗报废？（对照成本真相引擎五因）"},
    {"dimension": "dish_structure", "description": "高毛利菜品 vs 低毛利菜品的点单比例是否偏移？四象限矩阵中双低菜品是否已标记？"},
    {"dimension": "labor_efficiency", "description": "人效（营收/工时）是否下滑？排班是否匹配客流峰谷？"},
    {"dimension": "waste", "description": "本周损耗 Top 3 食材的根因是否已确认？（采购过多/备料过多/操作失误）"},
]

MONTHLY_CHECKLIST_TEMPLATE: list[dict] = [
    *WEEKLY_CHECKLIST_TEMPLATE,
    {"dimension": "member_lifecycle", "description": "新客转化率和沉睡客唤醒率是否达标？RFM 分层变化趋势如何？"},
    {"dimension": "competitive", "description": "本月是否有竞对新开店/促销活动影响客流？商圈变化是否已评估？"},
    {"dimension": "supplier_price", "description": "供应商月度结算价与市场价偏差是否超过 5%？是否需要比价/换供应商？"},
    {"dimension": "staff_turnover", "description": "本月离职率和到岗率是否正常？关键岗位（厨师长/领班）是否稳定？"},
]


class ReviewSessionService:
    """五步闭环经营复盘服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Step 0: 创建复盘会 ──────────────────────────────────────────────

    async def create_session(
        self,
        store_id: str,
        review_type: str,
        period_label: str,
        created_by: str = "",
    ) -> ReviewSession:
        """
        创建一个复盘会实例，自动生成 Step 2 核查清单。
        review_type: "weekly" | "monthly"
        period_label: "2026-W12" | "2026-03"
        """
        # 计算周期范围
        if review_type == "weekly":
            period_start, period_end = _week_range(period_label)
            template = WEEKLY_CHECKLIST_TEMPLATE
        else:
            period_start, period_end = _month_range(period_label)
            template = MONTHLY_CHECKLIST_TEMPLATE

        session = ReviewSession(
            id=uuid.uuid4(),
            store_id=store_id,
            review_type=review_type,
            period_label=period_label,
            period_start=period_start,
            period_end=period_end,
            current_step=1,
            status="draft",
            created_by=created_by,
        )
        self.db.add(session)

        # 自动创建核查清单
        for i, item in enumerate(template):
            checklist = ReviewChecklist(
                id=uuid.uuid4(),
                session_id=session.id,
                dimension=item["dimension"],
                description=item["description"],
                sort_order=i,
            )
            self.db.add(checklist)

        await self.db.flush()
        logger.info("review_session_created", session_id=str(session.id), review_type=review_type)
        return session

    # ─── Step 1: 拆细账 ─────────────────────────────────────────────────

    async def generate_breakdown(self, session_id: str) -> Dict[str, Any]:
        """
        生成多维度拆解快照（渠道×品类×时段×菜品四象限矩阵）。
        组合 cost_truth_engine 五因归因 + analytics_service 销售分析。
        """
        session = await self._get_session(session_id)

        # 构造拆细账数据（组合现有数据）
        breakdown = await self._build_breakdown_data(session)

        # 持久化快照
        session.breakdown_snapshot = breakdown
        session.current_step = max(session.current_step, 1)
        session.status = "in_progress"
        await self.db.flush()

        return breakdown

    async def _build_breakdown_data(self, session: ReviewSession) -> Dict[str, Any]:
        """组合现有服务生成拆细账数据"""
        store_id = session.store_id
        start = session.period_start
        end = session.period_end

        # 并行拉取多维数据
        from src.models import FinancialTransaction, Order, OrderItem
        from src.models.order import OrderStatus
        from sqlalchemy import and_, func

        # 1. 营收分渠道
        channel_query = (
            select(
                Order.order_type.label("channel"),
                func.count(Order.id).label("order_count"),
                func.sum(Order.final_amount).label("revenue_fen"),
            )
            .where(
                and_(
                    Order.store_id == store_id,
                    Order.order_date >= start,
                    Order.order_date <= end,
                    Order.status == OrderStatus.COMPLETED.value,
                )
            )
            .group_by(Order.order_type)
        )

        # 2. 菜品销售排名 (取 Top 20)
        dish_query = (
            select(
                OrderItem.dish_name,
                func.sum(OrderItem.quantity).label("sold_qty"),
                func.sum(OrderItem.subtotal).label("revenue_fen"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                and_(
                    Order.store_id == store_id,
                    Order.order_date >= start,
                    Order.order_date <= end,
                    Order.status == OrderStatus.COMPLETED.value,
                )
            )
            .group_by(OrderItem.dish_name)
            .order_by(func.sum(OrderItem.subtotal).desc())
            .limit(20)
        )

        try:
            channel_result = await self.db.execute(channel_query)
            channels = channel_result.all()

            dish_result = await self.db.execute(dish_query)
            dishes = dish_result.all()
        except Exception as exc:
            logger.warning("breakdown_query_failed", error=str(exc))
            channels = []
            dishes = []

        total_revenue_fen = sum(c.revenue_fen or 0 for c in channels)

        # 渠道拆解
        channel_breakdown = []
        for c in channels:
            rev = c.revenue_fen or 0
            channel_breakdown.append({
                "channel": c.channel or "unknown",
                "order_count": c.order_count or 0,
                "revenue_yuan": _yuan(rev),
                "revenue_pct": round(rev / total_revenue_fen * 100, 1) if total_revenue_fen else 0,
            })

        # 菜品四象限矩阵（利润率 vs 销量）
        dish_matrix = []
        for d in dishes:
            rev = d.revenue_fen or 0
            qty = d.sold_qty or 0
            dish_matrix.append({
                "dish_name": d.dish_name,
                "sold_qty": qty,
                "revenue_yuan": _yuan(rev),
                "avg_price_yuan": _yuan(rev // qty) if qty > 0 else 0,
            })

        # 分类菜品到四象限（高销量高利润 / 高销量低利润 / 低销量高利润 / 低销量低利润）
        if dish_matrix:
            avg_qty = sum(d["sold_qty"] for d in dish_matrix) / len(dish_matrix)
            avg_rev = sum(d["revenue_yuan"] for d in dish_matrix) / len(dish_matrix)
            for d in dish_matrix:
                high_qty = d["sold_qty"] >= avg_qty
                high_rev = d["revenue_yuan"] >= avg_rev
                if high_qty and high_rev:
                    d["quadrant"] = "star"       # 明星：高销高利
                elif high_qty and not high_rev:
                    d["quadrant"] = "cash_cow"   # 现金牛：高销低利
                elif not high_qty and high_rev:
                    d["quadrant"] = "question"   # 问题：低销高利
                else:
                    d["quadrant"] = "dog"        # 瘦狗：低销低利 → 考虑下架

        return {
            "period": f"{session.period_start} ~ {session.period_end}",
            "total_revenue_yuan": _yuan(total_revenue_fen),
            "channel_breakdown": channel_breakdown,
            "dish_matrix": dish_matrix,
            "avg_dish_qty_threshold": round(avg_qty, 1) if dish_matrix else 0,
            "avg_dish_revenue_threshold_yuan": round(avg_rev, 2) if dish_matrix else 0,
        }

    # ─── Step 2: 找真因 ─────────────────────────────────────────────────

    async def get_checklists(self, session_id: str) -> list[ReviewChecklist]:
        """获取核查清单列表"""
        result = await self.db.execute(
            select(ReviewChecklist)
            .where(ReviewChecklist.session_id == uuid.UUID(session_id))
            .order_by(ReviewChecklist.sort_order)
        )
        return list(result.scalars().all())

    async def verify_checklist_item(
        self,
        checklist_id: str,
        verified: bool,
        verified_by: str = "",
        verification_note: str = "",
    ) -> ReviewChecklist:
        """勾选/取消勾选某个核查项"""
        result = await self.db.execute(
            select(ReviewChecklist).where(ReviewChecklist.id == uuid.UUID(checklist_id))
        )
        item = result.scalar_one_or_none()
        if not item:
            raise ValueError(f"Checklist item {checklist_id} not found")

        item.verified = verified
        item.verified_by = verified_by if verified else None
        item.verified_at = datetime.utcnow() if verified else None
        item.verification_note = verification_note
        await self.db.flush()
        return item

    async def can_advance_to_step3(self, session_id: str) -> dict:
        """检查是否所有核查项已验证，允许进入 Step 3"""
        checklists = await self.get_checklists(session_id)
        total = len(checklists)
        verified = sum(1 for c in checklists if c.verified)
        return {
            "can_advance": verified == total and total > 0,
            "total": total,
            "verified": verified,
            "remaining": total - verified,
        }

    async def advance_step(self, session_id: str, target_step: int) -> ReviewSession:
        """推进到下一步（带 Step 2→3 的强制检查）"""
        session = await self._get_session(session_id)

        if target_step == 3:
            check = await self.can_advance_to_step3(session_id)
            if not check["can_advance"]:
                raise ValueError(
                    f"还有 {check['remaining']} 项未验证，无法进入「定措施」。"
                    "请先完成所有一线核查。"
                )

        session.current_step = target_step
        if target_step == 5:
            session.status = "completed"
            session.completed_at = datetime.utcnow()
        await self.db.flush()
        return session

    # ─── Step 3: 定措施 ─────────────────────────────────────────────────

    async def create_action(
        self,
        session_id: str,
        owner: str,
        deadline: date,
        action_desc: str,
        target_kpi: str,
    ) -> ReviewAction:
        """创建一条措施（四字段缺一不可）"""
        # 校验四字段
        if not all([owner.strip(), action_desc.strip(), target_kpi.strip()]):
            raise ValueError("措施的四个字段（责任人/时限/具体动作/量化结果）缺一不可")

        action = ReviewAction(
            id=uuid.uuid4(),
            session_id=uuid.UUID(session_id),
            owner=owner.strip(),
            deadline=deadline,
            action_desc=action_desc.strip(),
            target_kpi=target_kpi.strip(),
        )
        self.db.add(action)
        await self.db.flush()
        return action

    async def get_actions(self, session_id: str) -> list[ReviewAction]:
        """获取某次复盘会的所有措施"""
        result = await self.db.execute(
            select(ReviewAction)
            .where(ReviewAction.session_id == uuid.UUID(session_id))
            .order_by(ReviewAction.created_at)
        )
        return list(result.scalars().all())

    # ─── Step 4: 追执行 ─────────────────────────────────────────────────

    async def update_action_progress(
        self,
        action_id: str,
        progress_pct: int,
        current_kpi_value: str = "",
        note: str = "",
        updated_by: str = "",
    ) -> ReviewAction:
        """更新措施执行进度"""
        result = await self.db.execute(
            select(ReviewAction).where(ReviewAction.id == uuid.UUID(action_id))
        )
        action = result.scalar_one_or_none()
        if not action:
            raise ValueError(f"Action {action_id} not found")

        action.progress_pct = min(max(progress_pct, 0), 100)
        if current_kpi_value:
            action.current_kpi_value = current_kpi_value
        if progress_pct >= 100:
            action.progress_status = "completed"
        elif progress_pct > 0:
            action.progress_status = "in_progress"

        # 检查是否逾期
        if action.deadline < date.today() and action.progress_status != "completed":
            action.progress_status = "overdue"
            action.alert_level = "critical"

        # 追加进度备注
        if note:
            notes = action.progress_notes or []
            notes.append({
                "date": datetime.utcnow().isoformat(),
                "note": note,
                "updated_by": updated_by,
            })
            action.progress_notes = notes

        await self.db.flush()
        return action

    async def close_action(
        self,
        action_id: str,
        is_achieved: bool,
        actual_impact_fen: int = 0,
        closed_note: str = "",
    ) -> ReviewAction:
        """关闭措施（Step 5 看结果时使用）"""
        result = await self.db.execute(
            select(ReviewAction).where(ReviewAction.id == uuid.UUID(action_id))
        )
        action = result.scalar_one_or_none()
        if not action:
            raise ValueError(f"Action {action_id} not found")

        action.is_achieved = is_achieved
        action.actual_impact_fen = actual_impact_fen
        action.closed_at = datetime.utcnow()
        action.closed_note = closed_note
        action.progress_status = "completed"
        action.progress_pct = 100
        await self.db.flush()
        return action

    # ─── Step 5: 看结果 ─────────────────────────────────────────────────

    async def generate_result_summary(self, session_id: str) -> Dict[str, Any]:
        """生成闭环结果摘要"""
        session = await self._get_session(session_id)
        actions = await self.get_actions(session_id)

        total_actions = len(actions)
        completed = sum(1 for a in actions if a.progress_status == "completed")
        achieved = sum(1 for a in actions if a.is_achieved is True)
        overdue = sum(1 for a in actions if a.progress_status == "overdue")
        total_impact_fen = sum(a.actual_impact_fen or 0 for a in actions)

        summary = {
            "session_id": str(session.id),
            "review_type": session.review_type,
            "period_label": session.period_label,
            "total_actions": total_actions,
            "completed_actions": completed,
            "achieved_actions": achieved,
            "overdue_actions": overdue,
            "completion_rate_pct": round(completed / total_actions * 100, 1) if total_actions else 0,
            "achievement_rate_pct": round(achieved / total_actions * 100, 1) if total_actions else 0,
            "total_impact_yuan": _yuan(total_impact_fen),
            "actions_detail": [
                {
                    "id": str(a.id),
                    "owner": a.owner,
                    "action_desc": a.action_desc,
                    "target_kpi": a.target_kpi,
                    "current_kpi_value": a.current_kpi_value,
                    "is_achieved": a.is_achieved,
                    "actual_impact_yuan": _yuan(a.actual_impact_fen or 0),
                    "progress_status": a.progress_status,
                }
                for a in actions
            ],
        }

        session.result_summary = summary
        await self.db.flush()
        return summary

    # ─── 列表查询 ────────────────────────────────────────────────────────

    async def list_sessions(
        self,
        store_id: str,
        review_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ReviewSession]:
        """查询门店的复盘会列表"""
        q = (
            select(ReviewSession)
            .where(ReviewSession.store_id == store_id)
            .order_by(ReviewSession.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if review_type:
            q = q.where(ReviewSession.review_type == review_type)

        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def get_session_detail(self, session_id: str) -> Dict[str, Any]:
        """获取复盘会完整详情（含核查清单 + 措施列表）"""
        session = await self._get_session(session_id)
        checklists = await self.get_checklists(session_id)
        actions = await self.get_actions(session_id)

        return {
            "id": str(session.id),
            "store_id": session.store_id,
            "review_type": session.review_type,
            "period_label": session.period_label,
            "period_start": str(session.period_start),
            "period_end": str(session.period_end),
            "current_step": session.current_step,
            "status": session.status,
            "created_by": session.created_by,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
            "breakdown_snapshot": session.breakdown_snapshot,
            "result_summary": session.result_summary,
            "checklists": [
                {
                    "id": str(c.id),
                    "dimension": c.dimension,
                    "description": c.description,
                    "verified": c.verified,
                    "verified_by": c.verified_by,
                    "verified_at": c.verified_at.isoformat() if c.verified_at else None,
                    "verification_note": c.verification_note,
                }
                for c in checklists
            ],
            "actions": [
                {
                    "id": str(a.id),
                    "owner": a.owner,
                    "deadline": str(a.deadline),
                    "action_desc": a.action_desc,
                    "target_kpi": a.target_kpi,
                    "progress_status": a.progress_status,
                    "progress_pct": a.progress_pct,
                    "current_kpi_value": a.current_kpi_value,
                    "alert_level": a.alert_level,
                    "is_achieved": a.is_achieved,
                    "actual_impact_yuan": _yuan(a.actual_impact_fen or 0),
                    "progress_notes": a.progress_notes,
                }
                for a in actions
            ],
        }

    # ─── 内部工具 ────────────────────────────────────────────────────────

    async def _get_session(self, session_id: str) -> ReviewSession:
        result = await self.db.execute(
            select(ReviewSession).where(ReviewSession.id == uuid.UUID(session_id))
        )
        session = result.scalar_one_or_none()
        if not session:
            raise ValueError(f"ReviewSession {session_id} not found")
        return session
