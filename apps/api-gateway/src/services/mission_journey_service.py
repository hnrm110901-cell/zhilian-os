"""
MissionJourneyService — 使命旅程引擎核心服务

职责：
1. 旅程模板管理（创建/查询品牌级旅程模板）
2. 员工旅程实例化（入职时自动创建旅程）
3. 阶段自动推进（满足条件自动进入下一阶段）
4. 里程碑触发与记录
5. 成长叙事生成（把事件转化为可读故事）
6. 旅程统计快照（每日生成门店级统计）
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.mission_journey import (
    EmployeeJourney,
    EmployeeStageProgress,
    GrowthNarrative,
    JourneyMilestone,
    JourneyStageDefinition,
    JourneyStats,
    JourneyStatus,
    JourneyTemplate,
    JourneyType,
    NarrativeType,
    StageStatus,
)

logger = structlog.get_logger()


class MissionJourneyService:
    """使命旅程引擎 — 让每位餐饮人的成长可见、可量化、可分享"""

    # ── 旅程模板管理 ──────────────────────────────────

    @staticmethod
    async def create_template(
        db: AsyncSession,
        *,
        name: str,
        journey_type: str = "career",
        brand_id: Optional[str] = None,
        store_id: Optional[str] = None,
        description: Optional[str] = None,
        applicable_positions: Optional[list] = None,
        estimated_months: Optional[int] = None,
        stages: Optional[list[dict]] = None,
    ) -> dict:
        """创建旅程模板及其阶段定义

        Args:
            stages: [{"name":"新人融入","min_days":7,"max_days":30,"tasks":[...]}]
        """
        template = JourneyTemplate(
            name=name,
            journey_type=journey_type,
            brand_id=brand_id,
            store_id=store_id,
            description=description,
            applicable_positions=applicable_positions or [],
            estimated_months=estimated_months,
            total_stages=len(stages) if stages else 0,
        )
        db.add(template)
        await db.flush()

        stage_defs = []
        for i, s in enumerate(stages or [], 1):
            stage_def = JourneyStageDefinition(
                template_id=template.id,
                sequence=i,
                name=s.get("name", f"阶段{i}"),
                description=s.get("description"),
                icon=s.get("icon"),
                min_days=s.get("min_days"),
                max_days=s.get("max_days"),
                target_days=s.get("target_days"),
                entry_conditions=s.get("entry_conditions"),
                completion_conditions=s.get("completion_conditions"),
                tasks=s.get("tasks"),
                milestone_types=s.get("milestone_types"),
                stage_reward_fen=s.get("stage_reward_fen", 0),
            )
            db.add(stage_def)
            stage_defs.append(stage_def)

        await db.commit()
        logger.info("旅程模板创建成功", template_name=name,
                    stages_count=len(stage_defs))

        return {
            "template_id": str(template.id),
            "name": name,
            "journey_type": journey_type,
            "total_stages": len(stage_defs),
        }

    @staticmethod
    async def get_templates(
        db: AsyncSession,
        brand_id: Optional[str] = None,
        journey_type: Optional[str] = None,
    ) -> list[dict]:
        """查询旅程模板列表"""
        q = select(JourneyTemplate).where(JourneyTemplate.is_active.is_(True))
        if brand_id:
            q = q.where(JourneyTemplate.brand_id == brand_id)
        if journey_type:
            q = q.where(JourneyTemplate.journey_type == journey_type)
        q = q.order_by(JourneyTemplate.created_at.desc())

        result = await db.execute(q)
        templates = result.scalars().all()
        return [
            {
                "id": str(t.id),
                "name": t.name,
                "journey_type": t.journey_type.value if t.journey_type else None,
                "total_stages": t.total_stages,
                "estimated_months": t.estimated_months,
                "applicable_positions": t.applicable_positions,
                "description": t.description,
            }
            for t in templates
        ]

    # ── 员工旅程实例化 ────────────────────────────────

    @staticmethod
    async def start_journey(
        db: AsyncSession,
        *,
        person_id: uuid.UUID,
        store_id: str,
        template_id: uuid.UUID,
        mentor_person_id: Optional[uuid.UUID] = None,
        mentor_name: Optional[str] = None,
    ) -> dict:
        """为员工开启一条旅程

        自动创建旅程实例 + 初始化所有阶段进度 + 激活第一阶段
        """
        # 查询模板和阶段
        tmpl = await db.get(JourneyTemplate, template_id)
        if not tmpl:
            return {"error": "旅程模板不存在"}

        stages_result = await db.execute(
            select(JourneyStageDefinition)
            .where(JourneyStageDefinition.template_id == template_id)
            .order_by(JourneyStageDefinition.sequence)
        )
        stage_defs = stages_result.scalars().all()

        if not stage_defs:
            return {"error": "旅程模板没有定义阶段"}

        # 创建旅程实例
        now = datetime.utcnow()
        journey = EmployeeJourney(
            person_id=person_id,
            store_id=store_id,
            template_id=template_id,
            status=JourneyStatus.IN_PROGRESS,
            current_stage_seq=1,
            current_stage_name=stage_defs[0].name,
            progress_pct=0,
            started_at=now,
            total_milestones=0,
            achieved_milestones=0,
            total_narratives=0,
            mentor_person_id=mentor_person_id,
            mentor_name=mentor_name,
        )
        db.add(journey)
        await db.flush()

        # 初始化所有阶段进度
        for sd in stage_defs:
            sp = EmployeeStageProgress(
                journey_id=journey.id,
                stage_def_id=sd.id,
                stage_seq=sd.sequence,
                status=(StageStatus.ACTIVE if sd.sequence == 1
                        else StageStatus.LOCKED),
                entered_at=now if sd.sequence == 1 else None,
                tasks_total=len(sd.tasks) if sd.tasks else 0,
                tasks_done=0,
            )
            db.add(sp)

        # 初始化里程碑
        milestone_count = 0
        for sd in stage_defs:
            for mt in (sd.milestone_types or []):
                jm = JourneyMilestone(
                    journey_id=journey.id,
                    stage_seq=sd.sequence,
                    person_id=person_id,
                    store_id=store_id,
                    milestone_code=mt,
                    title=_milestone_title(mt),
                    achieved=False,
                )
                db.add(jm)
                milestone_count += 1

        journey.total_milestones = milestone_count

        # 生成第一条叙事
        narrative = GrowthNarrative(
            person_id=person_id,
            store_id=store_id,
            journey_id=journey.id,
            narrative_type=NarrativeType.MILESTONE_ACHIEVED,
            title=f"开启了「{tmpl.name}」成长旅程",
            content=(
                f"今天，一段新的成长旅程正式开启！"
                f"旅程共{tmpl.total_stages}个阶段，"
                f"第一站：{stage_defs[0].name}。加油！"
            ),
            emoji="🚀",
            is_public=True,
            occurred_at=now,
        )
        db.add(narrative)
        journey.total_narratives = 1

        await db.commit()

        logger.info("员工旅程开启", person_id=str(person_id),
                    journey=tmpl.name, stages=len(stage_defs))

        return {
            "journey_id": str(journey.id),
            "template_name": tmpl.name,
            "current_stage": stage_defs[0].name,
            "total_stages": len(stage_defs),
            "total_milestones": milestone_count,
        }

    # ── 阶段推进 ──────────────────────────────────────

    @staticmethod
    async def advance_stage(
        db: AsyncSession,
        journey_id: uuid.UUID,
        *,
        evaluator_name: Optional[str] = None,
        evaluation_score: Optional[int] = None,
        evaluation_comment: Optional[str] = None,
    ) -> dict:
        """推进旅程到下一阶段

        1. 标记当前阶段完成
        2. 解锁并激活下一阶段
        3. 更新旅程进度
        4. 生成阶段完成叙事
        """
        journey = await db.get(EmployeeJourney, journey_id)
        if not journey:
            return {"error": "旅程不存在"}
        if journey.status != JourneyStatus.IN_PROGRESS:
            return {"error": f"旅程状态为{journey.status}，无法推进"}

        now = datetime.utcnow()
        current_seq = journey.current_stage_seq

        # 查询当前阶段进度
        cur_progress_result = await db.execute(
            select(EmployeeStageProgress).where(
                and_(
                    EmployeeStageProgress.journey_id == journey_id,
                    EmployeeStageProgress.stage_seq == current_seq,
                )
            )
        )
        cur_progress = cur_progress_result.scalar_one_or_none()
        if not cur_progress:
            return {"error": "当前阶段进度记录不存在"}

        # 完成当前阶段
        cur_progress.status = StageStatus.COMPLETED
        cur_progress.completed_at = now
        if cur_progress.entered_at:
            cur_progress.days_spent = (now - cur_progress.entered_at).days
        cur_progress.evaluator_name = evaluator_name
        cur_progress.evaluation_score = evaluation_score
        cur_progress.evaluation_comment = evaluation_comment

        # 查询下一阶段
        next_progress_result = await db.execute(
            select(EmployeeStageProgress).where(
                and_(
                    EmployeeStageProgress.journey_id == journey_id,
                    EmployeeStageProgress.stage_seq == current_seq + 1,
                )
            )
        )
        next_progress = next_progress_result.scalar_one_or_none()

        # 查询模板总阶段数
        tmpl = await db.get(JourneyTemplate, journey.template_id)
        total_stages = tmpl.total_stages if tmpl else current_seq

        if next_progress:
            # 激活下一阶段
            next_progress.status = StageStatus.ACTIVE
            next_progress.entered_at = now

            # 获取下一阶段名
            next_stage_def_result = await db.execute(
                select(JourneyStageDefinition).where(
                    JourneyStageDefinition.id == next_progress.stage_def_id
                )
            )
            next_stage_def = next_stage_def_result.scalar_one_or_none()

            journey.current_stage_seq = current_seq + 1
            journey.current_stage_name = (
                next_stage_def.name if next_stage_def else f"阶段{current_seq + 1}"
            )
            journey.progress_pct = round(
                (current_seq / total_stages) * 100, 1
            )

            stage_name = journey.current_stage_name
            msg = f"顺利完成了阶段「{cur_progress.stage_seq}」，进入新阶段「{stage_name}」！"
        else:
            # 没有下一阶段 → 旅程完成
            journey.status = JourneyStatus.COMPLETED
            journey.completed_at = now
            journey.progress_pct = 100
            msg = f"恭喜完成了整个旅程「{tmpl.name if tmpl else ''}」！"

        # 生成叙事
        narrative = GrowthNarrative(
            person_id=journey.person_id,
            store_id=journey.store_id,
            journey_id=journey_id,
            narrative_type=NarrativeType.STAGE_COMPLETED,
            title=msg,
            content=(
                f"阶段评分：{evaluation_score or '待评'}分。"
                f"{evaluation_comment or ''}"
                f"{'旅程进度：' + str(journey.progress_pct) + '%' if journey.status != JourneyStatus.COMPLETED else '🎉 旅程圆满完成！'}"
            ),
            emoji="🎯" if journey.status != JourneyStatus.COMPLETED else "🏆",
            is_public=True,
            occurred_at=now,
        )
        db.add(narrative)
        journey.total_narratives = (journey.total_narratives or 0) + 1

        await db.commit()

        logger.info("旅程阶段推进", journey_id=str(journey_id),
                    from_stage=current_seq,
                    to_stage=journey.current_stage_seq,
                    progress=float(journey.progress_pct))

        return {
            "journey_id": str(journey_id),
            "previous_stage": current_seq,
            "current_stage": journey.current_stage_seq,
            "current_stage_name": journey.current_stage_name,
            "progress_pct": float(journey.progress_pct),
            "status": journey.status.value,
            "message": msg,
        }

    # ── 里程碑达成 ────────────────────────────────────

    @staticmethod
    async def achieve_milestone(
        db: AsyncSession,
        journey_id: uuid.UUID,
        milestone_code: str,
        *,
        evidence: Optional[str] = None,
        reward_fen: int = 0,
        badge_name: Optional[str] = None,
    ) -> dict:
        """标记旅程里程碑达成"""
        result = await db.execute(
            select(JourneyMilestone).where(
                and_(
                    JourneyMilestone.journey_id == journey_id,
                    JourneyMilestone.milestone_code == milestone_code,
                    JourneyMilestone.achieved.is_(False),
                )
            )
        )
        milestone = result.scalar_one_or_none()
        if not milestone:
            return {"error": f"里程碑 {milestone_code} 不存在或已达成"}

        now = datetime.utcnow()
        milestone.achieved = True
        milestone.achieved_at = now
        milestone.evidence = evidence
        milestone.reward_fen = reward_fen
        milestone.badge_name = badge_name

        # 更新旅程统计
        journey = await db.get(EmployeeJourney, journey_id)
        if journey:
            journey.achieved_milestones = (journey.achieved_milestones or 0) + 1

            # 生成叙事
            narrative = GrowthNarrative(
                person_id=journey.person_id,
                store_id=journey.store_id,
                journey_id=journey_id,
                narrative_type=NarrativeType.MILESTONE_ACHIEVED,
                title=f"达成里程碑：{milestone.title}",
                content=(
                    f"{evidence or ''}。"
                    f"{'获得奖励 ¥' + str(reward_fen / 100) + '。' if reward_fen else ''}"
                    f"{'获得徽章「' + badge_name + '」！' if badge_name else ''}"
                ),
                emoji="⭐",
                value_fen=reward_fen if reward_fen else None,
                is_public=True,
                occurred_at=now,
            )
            db.add(narrative)
            journey.total_narratives = (journey.total_narratives or 0) + 1

        await db.commit()

        logger.info("里程碑达成", journey_id=str(journey_id),
                    code=milestone_code)

        return {
            "milestone_code": milestone_code,
            "title": milestone.title,
            "achieved_at": now.isoformat(),
            "reward_yuan": round(reward_fen / 100, 2) if reward_fen else 0,
            "badge_name": badge_name,
        }

    # ── 查询接口 ──────────────────────────────────────

    @staticmethod
    async def get_my_journey(
        db: AsyncSession,
        person_id: uuid.UUID,
    ) -> list[dict]:
        """获取员工的所有旅程"""
        result = await db.execute(
            select(EmployeeJourney)
            .where(EmployeeJourney.person_id == person_id)
            .order_by(EmployeeJourney.started_at.desc())
        )
        journeys = result.scalars().all()

        output = []
        for j in journeys:
            # 获取模板名
            tmpl = await db.get(JourneyTemplate, j.template_id)

            # 获取阶段进度
            stages_result = await db.execute(
                select(EmployeeStageProgress)
                .where(EmployeeStageProgress.journey_id == j.id)
                .order_by(EmployeeStageProgress.stage_seq)
            )
            stages = stages_result.scalars().all()

            output.append({
                "journey_id": str(j.id),
                "template_name": tmpl.name if tmpl else "未知",
                "journey_type": (tmpl.journey_type.value
                                 if tmpl and tmpl.journey_type else None),
                "status": j.status.value,
                "current_stage_seq": j.current_stage_seq,
                "current_stage_name": j.current_stage_name,
                "progress_pct": float(j.progress_pct or 0),
                "total_milestones": j.total_milestones,
                "achieved_milestones": j.achieved_milestones,
                "mentor_name": j.mentor_name,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "stages": [
                    {
                        "seq": s.stage_seq,
                        "status": s.status.value,
                        "tasks_done": s.tasks_done,
                        "tasks_total": s.tasks_total,
                        "days_spent": s.days_spent,
                        "score": s.evaluation_score,
                    }
                    for s in stages
                ],
            })

        return output

    @staticmethod
    async def get_narratives(
        db: AsyncSession,
        person_id: uuid.UUID,
        limit: int = 20,
    ) -> list[dict]:
        """获取员工的成长叙事时间线"""
        result = await db.execute(
            select(GrowthNarrative)
            .where(GrowthNarrative.person_id == person_id)
            .order_by(GrowthNarrative.occurred_at.desc())
            .limit(limit)
        )
        narratives = result.scalars().all()

        return [
            {
                "id": str(n.id),
                "type": n.narrative_type.value,
                "title": n.title,
                "content": n.content,
                "emoji": n.emoji,
                "value_yuan": round(n.value_fen / 100, 2) if n.value_fen else None,
                "likes": n.likes_count,
                "is_public": n.is_public,
                "occurred_at": n.occurred_at.isoformat() if n.occurred_at else None,
            }
            for n in narratives
        ]

    @staticmethod
    async def get_milestones(
        db: AsyncSession,
        journey_id: uuid.UUID,
    ) -> list[dict]:
        """获取旅程的所有里程碑"""
        result = await db.execute(
            select(JourneyMilestone)
            .where(JourneyMilestone.journey_id == journey_id)
            .order_by(JourneyMilestone.stage_seq, JourneyMilestone.milestone_code)
        )
        milestones = result.scalars().all()

        return [
            {
                "code": m.milestone_code,
                "title": m.title,
                "stage_seq": m.stage_seq,
                "achieved": m.achieved,
                "achieved_at": m.achieved_at.isoformat() if m.achieved_at else None,
                "badge_name": m.badge_name,
                "reward_yuan": round(m.reward_fen / 100, 2) if m.reward_fen else 0,
            }
            for m in milestones
        ]

    # ── 统计 ──────────────────────────────────────────

    @staticmethod
    async def get_store_journey_stats(
        db: AsyncSession,
        store_id: str,
    ) -> dict:
        """获取门店旅程统计"""
        # 活跃旅程数
        active_result = await db.execute(
            select(func.count(EmployeeJourney.id))
            .where(
                and_(
                    EmployeeJourney.store_id == store_id,
                    EmployeeJourney.status == JourneyStatus.IN_PROGRESS,
                )
            )
        )
        active_count = active_result.scalar() or 0

        # 已完成旅程数
        completed_result = await db.execute(
            select(func.count(EmployeeJourney.id))
            .where(
                and_(
                    EmployeeJourney.store_id == store_id,
                    EmployeeJourney.status == JourneyStatus.COMPLETED,
                )
            )
        )
        completed_count = completed_result.scalar() or 0

        # 平均进度
        avg_result = await db.execute(
            select(func.avg(EmployeeJourney.progress_pct))
            .where(
                and_(
                    EmployeeJourney.store_id == store_id,
                    EmployeeJourney.status == JourneyStatus.IN_PROGRESS,
                )
            )
        )
        avg_progress = avg_result.scalar() or 0

        # 本月里程碑
        month_start = date.today().replace(day=1)
        milestone_result = await db.execute(
            select(func.count(JourneyMilestone.id))
            .where(
                and_(
                    JourneyMilestone.store_id == store_id,
                    JourneyMilestone.achieved.is_(True),
                    JourneyMilestone.achieved_at >= month_start,
                )
            )
        )
        milestones_mtd = milestone_result.scalar() or 0

        return {
            "store_id": store_id,
            "active_journeys": active_count,
            "completed_journeys": completed_count,
            "avg_progress_pct": round(float(avg_progress), 1),
            "milestones_achieved_mtd": milestones_mtd,
            "snapshot_date": date.today().isoformat(),
        }

    # ── 文化墙 ────────────────────────────────────────

    @staticmethod
    async def get_culture_wall(
        db: AsyncSession,
        store_id: str,
        limit: int = 30,
    ) -> list[dict]:
        """获取门店文化墙（公开的成长叙事）"""
        result = await db.execute(
            select(GrowthNarrative)
            .where(
                and_(
                    GrowthNarrative.store_id == store_id,
                    GrowthNarrative.is_public.is_(True),
                )
            )
            .order_by(GrowthNarrative.occurred_at.desc())
            .limit(limit)
        )
        narratives = result.scalars().all()

        return [
            {
                "id": str(n.id),
                "person_id": str(n.person_id),
                "type": n.narrative_type.value,
                "title": n.title,
                "content": n.content,
                "emoji": n.emoji,
                "likes": n.likes_count,
                "occurred_at": n.occurred_at.isoformat() if n.occurred_at else None,
            }
            for n in narratives
        ]


# ── 辅助函数 ──────────────────────────────────────────


def _milestone_title(code: str) -> str:
    """里程碑代码 → 中文标题"""
    _MAP = {
        "onboard": "正式入职",
        "trial_pass": "试岗考核通过",
        "probation_pass": "转正",
        "first_praise": "首次获得顾客表扬",
        "skill_up": "技能等级提升",
        "zero_waste_month": "零损耗月达成",
        "sales_champion": "月度销冠",
        "anniversary": "入职周年纪念",
        "promotion": "晋升",
        "mentor_first": "首次担任导师",
        "culture_star": "文化之星",
        "training_complete": "培训结业",
        "perfect_attendance": "全勤达成",
        "first_solo": "首次独立操作",
        "cost_saved": "成本节省贡献",
    }
    return _MAP.get(code, code)
