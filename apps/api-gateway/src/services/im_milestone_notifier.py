"""
IM 里程碑/技能认证通知服务 — 员工成长高光时刻推送

核心功能：
1. 技能升级时推送庆祝卡片
2. 培训结业推送证书通知
3. 各类里程碑（转正/全勤/销冠/周年等）推送
4. 定时扫描未通知的里程碑，批量推送

设计原则：
- 复用 IMMessageService 发送消息
- 复用 EmployeeMilestone.notified 字段避免重复推送
- 决策型推送：包含成就内容 + 奖励信息 + 查看详情入口
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.hr.person import Person
from ..models.employee_growth import EmployeeMilestone, EmployeeSkill, MilestoneType, SkillLevel
from ..models.store import Store
from ..services.im_message_service import IMMessageService

logger = structlog.get_logger()

# 里程碑类型 → 推送模板
MILESTONE_TEMPLATES = {
    MilestoneType.ONBOARD: {
        "emoji": "🎉",
        "title_prefix": "入职欢迎",
    },
    MilestoneType.TRIAL_PASS: {
        "emoji": "✅",
        "title_prefix": "试岗通过",
    },
    MilestoneType.PROBATION_PASS: {
        "emoji": "🎊",
        "title_prefix": "恭喜转正",
    },
    MilestoneType.FIRST_PRAISE: {
        "emoji": "⭐",
        "title_prefix": "首次顾客好评",
    },
    MilestoneType.SKILL_UP: {
        "emoji": "🏅",
        "title_prefix": "技能升级",
    },
    MilestoneType.ZERO_WASTE_MONTH: {
        "emoji": "🌿",
        "title_prefix": "零损耗月达成",
    },
    MilestoneType.SALES_CHAMPION: {
        "emoji": "🏆",
        "title_prefix": "月度销冠",
    },
    MilestoneType.ANNIVERSARY: {
        "emoji": "🎂",
        "title_prefix": "周年纪念",
    },
    MilestoneType.PROMOTION: {
        "emoji": "🚀",
        "title_prefix": "晋升",
    },
    MilestoneType.MENTOR_FIRST: {
        "emoji": "🤝",
        "title_prefix": "首次带徒",
    },
    MilestoneType.CULTURE_STAR: {
        "emoji": "💫",
        "title_prefix": "文化之星",
    },
    MilestoneType.TRAINING_COMPLETE: {
        "emoji": "📜",
        "title_prefix": "培训结业",
    },
    MilestoneType.PERFECT_ATTENDANCE: {
        "emoji": "💯",
        "title_prefix": "全勤达成",
    },
    MilestoneType.CUSTOM: {
        "emoji": "🎯",
        "title_prefix": "成就达成",
    },
}

# 技能等级 → 中文标签
SKILL_LEVEL_LABELS = {
    SkillLevel.NOVICE: "学徒",
    SkillLevel.APPRENTICE: "熟手",
    SkillLevel.JOURNEYMAN: "能手",
    SkillLevel.EXPERT: "高手",
    SkillLevel.MASTER: "匠人",
}


class IMMilestoneNotifier:
    """IM 里程碑/技能认证通知服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.msg_service = IMMessageService(db)

    async def notify_milestone(
        self,
        milestone_id: str,
    ) -> Dict[str, Any]:
        """
        推送单个里程碑通知。

        Returns:
            {"notified": True/False, "employee_name": ..., "milestone_type": ...}
        """
        import uuid as uuid_mod

        from sqlalchemy.dialects.postgresql import UUID as PGUUID

        milestone_uuid = uuid_mod.UUID(milestone_id) if isinstance(milestone_id, str) else milestone_id

        result = await self.db.execute(select(EmployeeMilestone).where(EmployeeMilestone.id == milestone_uuid))
        milestone = result.scalar_one_or_none()
        if not milestone:
            return {"error": f"里程碑 {milestone_id} 不存在"}

        if milestone.notified:
            return {"already_notified": True, "milestone_id": milestone_id}

        # 通过 legacy_employee_id 查 Person
        person_result = await self.db.execute(
            select(Person).where(Person.legacy_employee_id == str(milestone.employee_id))
        )
        person = person_result.scalar_one_or_none()
        if not person:
            return {"error": f"员工 {milestone.employee_id} 不存在"}

        im_userid = person.wechat_userid or person.dingtalk_userid
        if not im_userid:
            return {"error": "员工未绑定IM账号", "employee_id": milestone.employee_id}

        # 获取品牌ID
        store_result = await self.db.execute(select(Store.brand_id).where(Store.id == person.store_id))
        brand_id = store_result.scalar_one_or_none()

        # 构建推送内容
        template = MILESTONE_TEMPLATES.get(
            milestone.milestone_type,
            {"emoji": "🎯", "title_prefix": "成就达成"},
        )
        emoji = milestone.badge_icon or template["emoji"]
        title = f"{emoji} {template['title_prefix']}"

        content = self._build_milestone_content(
            milestone,
            person.name,
            emoji,
            template["title_prefix"],
        )

        # 发送
        try:
            send_result = await self.msg_service.send_markdown(
                brand_id,
                im_userid,
                title,
                content,
            )

            # 标记已通知
            milestone.notified = True
            milestone.notified_at = datetime.utcnow()
            await self.db.commit()

            logger.info(
                "milestone_notifier.sent",
                employee_id=milestone.employee_id,
                milestone_type=(
                    milestone.milestone_type.value
                    if hasattr(milestone.milestone_type, "value")
                    else str(milestone.milestone_type)
                ),
            )

            return {
                "notified": True,
                "employee_name": person.name,
                "milestone_type": str(milestone.milestone_type),
                "title": milestone.title,
            }
        except Exception as e:
            logger.warning("milestone_notifier.send_failed", milestone_id=str(milestone_id), error=str(e))
            return {"notified": False, "error": str(e)}

    async def notify_skill_upgrade(
        self,
        employee_id: str,
        skill_name: str,
        new_level: str,
        score: int = 0,
    ) -> Dict[str, Any]:
        """
        技能升级时推送庆祝消息。
        通常由 hr_growth API 在评估技能时调用。
        """
        person_result = await self.db.execute(
            select(Person).where(Person.legacy_employee_id == str(employee_id))
        )
        person = person_result.scalar_one_or_none()
        if not person:
            return {"error": f"员工 {employee_id} 不存在"}

        im_userid = person.wechat_userid or person.dingtalk_userid
        if not im_userid:
            return {"error": "员工未绑定IM账号"}

        store_result = await self.db.execute(select(Store.brand_id).where(Store.id == person.store_id))
        brand_id = store_result.scalar_one_or_none()

        # 技能等级中文
        try:
            level_enum = SkillLevel(new_level)
            level_label = SKILL_LEVEL_LABELS.get(level_enum, new_level)
        except ValueError:
            level_label = new_level

        content = (
            f"### 🏅 技能认证通过\n\n"
            f"**{person.name}** 恭喜！您的技能已升级：\n\n"
            f"- **技能**: {skill_name}\n"
            f"- **新等级**: {level_label}\n"
        )
        if score > 0:
            content += f"- **评估分数**: {score}/100\n"

        content += f"\n继续加油！下一个目标等着您。\n" f"💡 回复「个人信息」查看技能档案"

        try:
            result = await self.msg_service.send_markdown(
                brand_id,
                im_userid,
                "技能认证",
                content,
            )
            return {"notified": True, "skill": skill_name, "level": level_label}
        except Exception as e:
            logger.warning("skill_upgrade_notify.failed", employee_id=employee_id, error=str(e))
            return {"notified": False, "error": str(e)}

    async def sweep_unnotified_milestones(
        self,
        brand_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        扫描所有未推送的里程碑，批量推送。
        由 Celery Beat 定时调用。
        """
        query = select(EmployeeMilestone).where(EmployeeMilestone.notified.is_(False))

        result = await self.db.execute(query)
        milestones = result.scalars().all()

        notified = 0
        errors = 0

        for milestone in milestones:
            try:
                res = await self.notify_milestone(str(milestone.id))
                if res.get("notified"):
                    notified += 1
                elif res.get("error"):
                    errors += 1
            except Exception as e:
                errors += 1
                logger.warning("sweep_milestones.item_failed", milestone_id=str(milestone.id), error=str(e))

        logger.info(
            "sweep_milestones.done",
            total=len(milestones),
            notified=notified,
            errors=errors,
        )
        return {"total": len(milestones), "notified": notified, "errors": errors}

    def _build_milestone_content(
        self,
        milestone: EmployeeMilestone,
        employee_name: str,
        emoji: str,
        title_prefix: str,
    ) -> str:
        """构建里程碑推送 Markdown 内容"""
        content = f"### {emoji} {title_prefix}\n\n"
        content += f"**{employee_name}** 恭喜！\n\n"
        content += f"**{milestone.title}**\n\n"

        if milestone.description:
            content += f"{milestone.description}\n\n"

        if milestone.reward_fen and milestone.reward_fen > 0:
            reward_yuan = milestone.reward_fen / 100
            content += f"🎁 奖励: ¥{reward_yuan:.2f}\n\n"

        content += f"📅 达成日期: {milestone.achieved_at}\n"

        return content
