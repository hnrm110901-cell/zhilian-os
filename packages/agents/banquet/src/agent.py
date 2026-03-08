"""
宴会管理 Agent — Phase 9
基于规则 + 模板 + 任务三层架构（V1），遵循 CLAUDE.md 渐进智能原则

Agent体系：
  1. FollowupAgent    — 跟进提醒（超N天未跟进 → 生成待办 + 企微通知）
  2. QuotationAgent   — 自动报价（人数+预算+类型 → 推荐套餐+价格区间）
  3. SchedulingAgent  — 排期推荐（日期+时段+人数 → 合适厅房列表）
  4. ExecutionAgent   — 执行任务（订单确认 / T-7/T-3/T-1 → 自动生成任务）
  5. ReviewAgent      — 宴会复盘（收入+成本+异常 → 复盘草稿）
"""
import uuid
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from src.models.banquet import (
    BanquetLead, BanquetOrder, BanquetHall, BanquetHallBooking,
    MenuPackage, ExecutionTask, ExecutionTemplate,
    BanquetProfitSnapshot, BanquetAgentActionLog,
    LeadStageEnum, OrderStatusEnum, TaskStatusEnum, TaskOwnerRoleEnum,
    BanquetAgentTypeEnum,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Agent 1: FollowupAgent — 跟进提醒
# ─────────────────────────────────────────────────────────────────────────────

class FollowupAgent:
    """
    触发条件：
      - 超过 stale_days 天未跟进的线索（非终态）
      - 看厅后超过 2 天未报价
    动作：生成企微提醒文本 + 记录 ActionLog
    """

    STALE_DAYS = 3          # 超过3天未跟进视为停滞
    VISIT_QUOTE_DAYS = 2    # 看厅后2天内应报价

    async def scan_stale_leads(
        self,
        store_id: str,
        db: AsyncSession,
        dry_run: bool = False,
    ) -> list[dict]:
        """扫描停滞线索，返回需要跟进的线索列表（含提醒文本）"""
        cutoff = datetime.utcnow() - timedelta(days=self.STALE_DAYS)
        terminal = {LeadStageEnum.WON, LeadStageEnum.LOST}

        stmt = select(BanquetLead).where(
            and_(
                BanquetLead.store_id == store_id,
                BanquetLead.current_stage.notin_(terminal),
                BanquetLead.last_followup_at < cutoff,
            )
        )
        result = await db.execute(stmt)
        stale_leads = result.scalars().all()

        actions = []
        for lead in stale_leads:
            days_since = (datetime.utcnow() - lead.last_followup_at).days if lead.last_followup_at else 99
            suggestion = (
                f"【跟进提醒】线索 {lead.id[:8]}… 已 {days_since} 天未跟进，"
                f"当前阶段：{lead.current_stage.value}，"
                f"预计宴会日期：{lead.expected_date or '未定'}，"
                f"预算约¥{(lead.expected_budget_fen or 0) / 100:.0f}。"
                f"建议今日联系确认意向。"
            )
            actions.append({
                "lead_id": lead.id,
                "days_stale": days_since,
                "stage": lead.current_stage.value,
                "suggestion": suggestion,
                "action_type": "followup_reminder",
            })

            if not dry_run:
                await self._log_action(
                    db=db,
                    agent_type=BanquetAgentTypeEnum.FOLLOWUP,
                    obj_type="lead",
                    obj_id=lead.id,
                    action_type="followup_reminder",
                    suggestion=suggestion,
                )

        if not dry_run and actions:
            await db.commit()

        logger.info(f"[FollowupAgent] store={store_id} stale_leads={len(actions)}")
        return actions

    @staticmethod
    async def _log_action(
        db: AsyncSession,
        agent_type: BanquetAgentTypeEnum,
        obj_type: str,
        obj_id: str,
        action_type: str,
        suggestion: str,
        result: Optional[dict] = None,
    ) -> None:
        log = BanquetAgentActionLog(
            id=str(uuid.uuid4()),
            agent_type=agent_type,
            related_object_type=obj_type,
            related_object_id=obj_id,
            action_type=action_type,
            action_result=result,
            suggestion_text=suggestion,
        )
        db.add(log)


# ─────────────────────────────────────────────────────────────────────────────
# Agent 2: QuotationAgent — 自动报价
# ─────────────────────────────────────────────────────────────────────────────

class QuotationAgent:
    """
    输入：people_count + budget_fen + banquet_type + store_id
    输出：候选套餐列表（含毛利预估¥）+ 推荐价格区间
    """

    async def recommend_packages(
        self,
        store_id: str,
        people_count: int,
        budget_fen: int,
        banquet_type: Optional[str],
        db: AsyncSession,
    ) -> dict:
        """返回满足人数和预算的套餐推荐，按毛利率降序"""
        stmt = select(MenuPackage).where(
            and_(
                MenuPackage.store_id == store_id,
                MenuPackage.is_active == True,
                MenuPackage.target_people_min <= people_count,
                MenuPackage.target_people_max >= people_count,
                MenuPackage.suggested_price_fen * people_count <= budget_fen * 120 // 100,  # 预算20%浮动
            )
        )
        if banquet_type:
            stmt = stmt.where(
                MenuPackage.banquet_type == banquet_type
            )
        result = await db.execute(stmt)
        packages = result.scalars().all()

        candidates = []
        for pkg in packages:
            total_price_fen = pkg.suggested_price_fen * people_count
            gross_profit_fen = total_price_fen - (pkg.cost_fen or 0) * people_count
            margin_pct = (gross_profit_fen / total_price_fen * 100) if total_price_fen > 0 else 0
            candidates.append({
                "package_id": pkg.id,
                "package_name": pkg.name,
                "suggested_price_per_person_yuan": pkg.suggested_price_fen / 100,
                "total_price_yuan": total_price_fen / 100,
                "estimated_gross_profit_yuan": gross_profit_fen / 100,   # Rule 6: ¥字段
                "gross_margin_pct": round(margin_pct, 1),
                "banquet_type": pkg.banquet_type.value if pkg.banquet_type else "通用",
            })

        # 按毛利率降序推荐
        candidates.sort(key=lambda x: x["gross_margin_pct"], reverse=True)

        price_low  = min((c["total_price_yuan"] for c in candidates), default=budget_fen / 100)
        price_high = max((c["total_price_yuan"] for c in candidates), default=budget_fen / 100)

        return {
            "store_id": store_id,
            "people_count": people_count,
            "budget_yuan": budget_fen / 100,
            "recommended_packages": candidates[:5],   # 最多5个候选
            "price_range_yuan": {"low": price_low, "high": price_high},
            "suggestion": (
                f"根据{people_count}人、预算¥{budget_fen/100:.0f}，"
                f"推荐{len(candidates[:5])}个套餐，"
                f"最高毛利率方案可创造¥{candidates[0]['estimated_gross_profit_yuan']:.0f}利润。"
                if candidates else "暂无符合条件的套餐，建议自定义菜单。"
            ),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Agent 3: SchedulingAgent — 排期推荐
# ─────────────────────────────────────────────────────────────────────────────

class SchedulingAgent:
    """
    输入：target_date + slot_name + people_count + store_id
    输出：可用厅房列表 + 冲突说明
    """

    async def recommend_halls(
        self,
        store_id: str,
        target_date: date,
        slot_name: str,           # lunch / dinner / all_day
        people_count: int,
        db: AsyncSession,
    ) -> dict:
        """推荐可用厅房，排除已预订档期"""
        # 查询该门店所有活跃厅房
        halls_stmt = select(BanquetHall).where(
            and_(
                BanquetHall.store_id == store_id,
                BanquetHall.is_active == True,
                BanquetHall.max_people >= people_count,
            )
        )
        result = await db.execute(halls_stmt)
        all_halls = result.scalars().all()

        # 查询当日当时段已占用的厅房
        booked_stmt = select(BanquetHallBooking.hall_id).where(
            and_(
                BanquetHallBooking.slot_date == target_date,
                BanquetHallBooking.slot_name == slot_name,
                BanquetHallBooking.is_locked == True,
            )
        )
        booked_result = await db.execute(booked_stmt)
        booked_hall_ids = {row[0] for row in booked_result.fetchall()}

        available, conflicted = [], []
        for hall in all_halls:
            entry = {
                "hall_id": hall.id,
                "hall_name": hall.name,
                "hall_type": hall.hall_type.value,
                "max_people": hall.max_people,
                "max_tables": hall.max_tables,
                "min_spend_yuan": hall.min_spend_fen / 100,
            }
            if hall.id in booked_hall_ids:
                entry["conflict"] = f"{target_date} {slot_name} 已被预订"
                conflicted.append(entry)
            else:
                available.append(entry)

        return {
            "store_id": store_id,
            "target_date": str(target_date),
            "slot_name": slot_name,
            "people_count": people_count,
            "available_halls": available,
            "conflicted_halls": conflicted,
            "suggestion": (
                f"{target_date} {slot_name} 可用{len(available)}个厅，"
                f"已占用{len(conflicted)}个厅。"
                if available else
                f"⚠️ {target_date} {slot_name} 所有厅房已满，请更换时段或日期。"
            ),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Agent 4: ExecutionAgent — 执行任务自动生成
# ─────────────────────────────────────────────────────────────────────────────

class ExecutionAgent:
    """
    触发条件：订单状态变更为 confirmed
    动作：从执行模板生成任务清单（T-7/T-3/T-1 三个节点）
    幂等：同一订单不重复生成（check existing tasks）
    """

    DEFAULT_TASK_DEFS = [
        {"days_before": 7, "task_type": "purchase",  "task_name": "确认食材采购清单",       "owner_role": "purchase"},
        {"days_before": 7, "task_type": "decor",     "task_name": "确认场地布置方案",       "owner_role": "decor"},
        {"days_before": 3, "task_type": "kitchen",   "task_name": "厨房确认菜单并预备食材", "owner_role": "kitchen"},
        {"days_before": 3, "task_type": "service",   "task_name": "服务人员排班确认",       "owner_role": "service"},
        {"days_before": 1, "task_type": "manager",   "task_name": "店长宴会前检查确认",     "owner_role": "manager"},
        {"days_before": 1, "task_type": "kitchen",   "task_name": "厨房最终备料完成",       "owner_role": "kitchen"},
        {"days_before": 0, "task_type": "service",   "task_name": "宴会开始前服务就位",     "owner_role": "service"},
    ]

    async def generate_tasks_for_order(
        self,
        order: BanquetOrder,
        db: AsyncSession,
    ) -> list[ExecutionTask]:
        """为已确认订单生成执行任务（幂等：已有任务则跳过）"""
        # 幂等检查
        existing = await db.execute(
            select(func.count()).where(ExecutionTask.banquet_order_id == order.id)
        )
        if existing.scalar() > 0:
            logger.info(f"[ExecutionAgent] order={order.id} tasks already exist, skip")
            return []

        # 加载门店模板（优先找匹配宴会类型的，否则用通用）
        template_stmt = select(ExecutionTemplate).where(
            and_(
                ExecutionTemplate.store_id == order.store_id,
                ExecutionTemplate.is_active == True,
            )
        ).order_by(
            # 精确匹配优先
            (ExecutionTemplate.banquet_type == order.banquet_type).desc()
        )
        tmpl_result = await db.execute(template_stmt)
        template = tmpl_result.scalars().first()

        task_defs = template.task_defs if template else self.DEFAULT_TASK_DEFS

        tasks = []
        banquet_dt = datetime.combine(order.banquet_date, datetime.min.time())
        for td in task_defs:
            due = banquet_dt - timedelta(days=td["days_before"])
            task = ExecutionTask(
                id=str(uuid.uuid4()),
                banquet_order_id=order.id,
                template_id=template.id if template else None,
                task_type=td["task_type"],
                task_name=td["task_name"],
                owner_role=TaskOwnerRoleEnum(td["owner_role"]),
                due_time=due,
                task_status=TaskStatusEnum.PENDING,
            )
            db.add(task)
            tasks.append(task)

        await db.commit()
        logger.info(f"[ExecutionAgent] order={order.id} generated {len(tasks)} tasks")
        return tasks


# ─────────────────────────────────────────────────────────────────────────────
# Agent 5: ReviewAgent — 宴会复盘
# ─────────────────────────────────────────────────────────────────────────────

class ReviewAgent:
    """
    触发条件：订单状态变更为 completed
    动作：汇总收入/成本/异常 → 生成复盘草稿（¥优先，见 Rule 6）
    """

    async def generate_review(
        self,
        order: BanquetOrder,
        db: AsyncSession,
    ) -> dict:
        """生成宴会复盘摘要"""
        # 利润快照
        snap_result = await db.execute(
            select(BanquetProfitSnapshot).where(
                BanquetProfitSnapshot.banquet_order_id == order.id
            )
        )
        snap = snap_result.scalars().first()

        # 逾期/异常任务数
        overdue_result = await db.execute(
            select(func.count()).where(
                and_(
                    ExecutionTask.banquet_order_id == order.id,
                    ExecutionTask.task_status == TaskStatusEnum.OVERDUE,
                )
            )
        )
        overdue_count = overdue_result.scalar() or 0

        revenue_yuan      = (snap.revenue_fen / 100) if snap else (order.paid_fen / 100)
        gross_profit_yuan = (snap.gross_profit_fen / 100) if snap else 0
        margin_pct        = (snap.gross_margin_pct) if snap else 0

        review = {
            "order_id": order.id,
            "banquet_date": str(order.banquet_date),
            "banquet_type": order.banquet_type.value,
            "people_count": order.people_count,
            "revenue_yuan": revenue_yuan,                    # Rule 6: ¥字段
            "gross_profit_yuan": gross_profit_yuan,          # Rule 6: ¥字段
            "gross_margin_pct": round(margin_pct, 1),
            "overdue_task_count": overdue_count,
            "review_text": self._build_review_text(
                order=order,
                revenue_yuan=revenue_yuan,
                gross_profit_yuan=gross_profit_yuan,
                margin_pct=margin_pct,
                overdue_count=overdue_count,
            ),
        }

        # 记录 Agent 日志
        log = BanquetAgentActionLog(
            id=str(uuid.uuid4()),
            agent_type=BanquetAgentTypeEnum.REVIEW,
            related_object_type="order",
            related_object_id=order.id,
            action_type="review_generated",
            action_result=review,
            suggestion_text=review["review_text"],
        )
        db.add(log)
        await db.commit()

        return review

    @staticmethod
    def _build_review_text(
        order: BanquetOrder,
        revenue_yuan: float,
        gross_profit_yuan: float,
        margin_pct: float,
        overdue_count: int,
    ) -> str:
        lines = [
            f"【宴会复盘】{order.banquet_date} {order.banquet_type.value}",
            f"到场人数：{order.people_count}人 / {order.table_count}桌",
            f"实收金额：¥{revenue_yuan:.0f}",
            f"毛利润：¥{gross_profit_yuan:.0f}（毛利率 {margin_pct:.1f}%）",
        ]
        if overdue_count > 0:
            lines.append(f"⚠️ 本次有 {overdue_count} 个执行任务逾期，建议复盘原因。")
        else:
            lines.append("✅ 所有执行任务按时完成。")
        lines.append("以上为系统自动生成草稿，请销售经理确认后发送给店长。")
        return "\n".join(lines)
