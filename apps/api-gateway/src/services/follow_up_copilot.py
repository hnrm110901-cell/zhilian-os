"""
智能跟进话术生成 — Phase P4 (屯象独有)
根据客户画像、漏斗阶段、历史交互，AI生成个性化跟进话术
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

logger = structlog.get_logger()


class FollowUpCopilot:
    """AI跟进话术生成器"""

    async def generate_follow_up(
        self,
        session: AsyncSession,
        store_id: str,
        customer_name: str,
        customer_phone: str,
        current_stage: str,
        event_type: str = "wedding",
        target_date: Optional[str] = None,
        table_count: Optional[int] = None,
        estimated_value_yuan: float = 0,
        last_follow_up_days: int = 0,
        lost_reason: Optional[str] = None,
        competitor_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """生成个性化跟进话术"""
        # 根据阶段生成不同策略
        strategy = self._get_stage_strategy(current_stage)
        scripts = self._generate_scripts(
            customer_name=customer_name,
            stage=current_stage,
            event_type=event_type,
            target_date=target_date,
            table_count=table_count,
            estimated_value_yuan=estimated_value_yuan,
            last_follow_up_days=last_follow_up_days,
            lost_reason=lost_reason,
            competitor_name=competitor_name,
        )

        return {
            "customer_name": customer_name,
            "current_stage": current_stage,
            "strategy": strategy,
            "scripts": scripts,
            "recommended_channel": self._recommend_channel(current_stage, last_follow_up_days),
            "urgency": self._calculate_urgency(current_stage, last_follow_up_days, target_date),
            "generated_at": datetime.utcnow().isoformat(),
        }

    async def batch_generate(
        self,
        session: AsyncSession,
        store_id: str,
        leads: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """批量生成跟进话术（日报推送用）"""
        results = []
        for lead in leads:
            result = await self.generate_follow_up(
                session=session,
                store_id=store_id,
                **lead,
            )
            results.append(result)
        return results

    def _get_stage_strategy(self, stage: str) -> Dict[str, Any]:
        """各阶段跟进策略"""
        strategies = {
            "lead": {
                "goal": "建立联系，了解需求",
                "key_actions": ["确认宴会类型和日期", "了解预算范围", "邀请到店参观"],
                "tone": "热情专业",
                "max_follow_interval_days": 3,
            },
            "intent": {
                "goal": "深入需求，推荐方案",
                "key_actions": ["推荐合适的套餐方案", "提供厅位选择", "安排试菜"],
                "tone": "顾问式",
                "max_follow_interval_days": 2,
            },
            "room_lock": {
                "goal": "锁定厅位，推进签约",
                "key_actions": ["确认厅位细节", "沟通合同条款", "安排定金支付"],
                "tone": "促成交",
                "max_follow_interval_days": 1,
            },
            "negotiation": {
                "goal": "解决异议，达成共识",
                "key_actions": ["处理价格异议", "对比竞品优势", "提供限时优惠"],
                "tone": "灵活坚定",
                "max_follow_interval_days": 1,
            },
            "signed": {
                "goal": "服务交付，创造口碑",
                "key_actions": ["跟进EO单确认", "安排演职人员", "确认布场细节"],
                "tone": "服务管家",
                "max_follow_interval_days": 7,
            },
            "lost": {
                "goal": "了解原因，尝试挽回",
                "key_actions": ["了解真实流失原因", "提供特别优惠", "保持联系为未来铺路"],
                "tone": "真诚关心",
                "max_follow_interval_days": 14,
            },
        }
        return strategies.get(stage, strategies["lead"])

    def _generate_scripts(
        self,
        customer_name: str,
        stage: str,
        event_type: str,
        target_date: Optional[str],
        table_count: Optional[int],
        estimated_value_yuan: float,
        last_follow_up_days: int,
        lost_reason: Optional[str],
        competitor_name: Optional[str],
    ) -> List[Dict[str, str]]:
        """生成多个话术版本"""
        event_label = {"wedding": "婚宴", "birthday": "寿宴", "corporate": "商务宴请", "family": "家庭聚会"}.get(event_type, "宴会")
        surname = customer_name[0] if customer_name else "客户"

        scripts = []

        if stage == "lead":
            scripts = [
                {
                    "type": "首次电话",
                    "content": f"{surname}先生/女士您好，我是XX酒店宴会顾问小张。了解到您有{event_label}的需求"
                               + (f"，{target_date}是个好日子" if target_date else "")
                               + "，我们酒店专业承办宴会超过10年，想为您介绍一下我们的场地和服务，方便您参考。",
                },
                {
                    "type": "微信消息",
                    "content": f"{surname}先生/女士好！感谢您的关注~我们有多款{event_label}套餐可供选择"
                               + (f"，{table_count}桌的话推荐我们的大宴会厅" if table_count else "")
                               + "。这是我们最新的场地照片和菜单，您先看看有没有感兴趣的？随时欢迎到店实地参观！",
                },
            ]
        elif stage == "intent":
            scripts = [
                {
                    "type": "推荐方案",
                    "content": f"{surname}先生/女士，根据您{table_count or ''}桌{event_label}的需求，为您推荐以下方案：\n"
                               f"💎 尊享方案：含全套布场+摄影，¥{estimated_value_yuan * 1.2:.0f}\n"
                               f"🌟 精选方案：含基础布场，¥{estimated_value_yuan:.0f}\n"
                               f"方便这周末来试菜吗？",
                },
            ]
        elif stage == "room_lock":
            scripts = [
                {
                    "type": "促签约",
                    "content": f"{surname}先生/女士，您锁定的厅位目前还有另外2组客户在看"
                               + (f"，{target_date}这个档期很抢手" if target_date else "")
                               + "。建议您尽早确认，我们可以优先为您保留。本周内签约还有早鸟优惠哦！",
                },
            ]
        elif stage == "negotiation":
            if competitor_name:
                scripts.append({
                    "type": "竞品对比",
                    "content": f"{surname}先生/女士，了解到您在对比{competitor_name}。我们的优势在于：\n"
                               f"✅ 一站式服务（含布场+演职人员调度）\n"
                               f"✅ AI智能配餐，根据宾客口味定制\n"
                               f"✅ 履约时间线管理，确保当天零失误",
                })
            scripts.append({
                "type": "限时优惠",
                "content": f"{surname}先生/女士，经请示经理，可以为您争取到一个特别优惠："
                           f"本周签约赠送迎宾区花艺布置（价值¥2,000）+"
                           f"婚礼当天摄影跟拍。这个优惠仅限本周哦！",
            })
        elif stage == "lost":
            if lost_reason:
                scripts.append({
                    "type": "挽回",
                    "content": f"{surname}先生/女士，之前的沟通中了解到"
                               + f"（{lost_reason}），我们最近做了一些调整：\n"
                               + "新推出的性价比套餐可能更适合您的需求。"
                               + "如果还没有最终确定，欢迎再来看看，我们为老朋友准备了专属优惠。",
                })

        if not scripts:
            scripts = [{
                "type": "通用跟进",
                "content": f"{surname}先生/女士您好，距离上次沟通已经{last_follow_up_days}天了，"
                           f"不知道您{event_label}的筹备进展如何？有任何需要帮忙的随时联系我。",
            }]

        return scripts

    def _recommend_channel(self, stage: str, last_follow_up_days: int) -> str:
        """推荐跟进渠道"""
        if stage in ("room_lock", "negotiation") or last_follow_up_days > 7:
            return "phone"
        return "wechat"

    def _calculate_urgency(self, stage: str, last_follow_up_days: int, target_date: Optional[str]) -> str:
        """计算跟进紧急度"""
        if stage in ("room_lock", "negotiation"):
            return "high"
        if target_date:
            try:
                days_to_event = (date.fromisoformat(target_date) - date.today()).days
                if days_to_event <= 14:
                    return "high"
                if days_to_event <= 30:
                    return "medium"
            except (ValueError, TypeError):
                pass
        if last_follow_up_days > 5:
            return "medium"
        return "low"


follow_up_copilot = FollowUpCopilot()
