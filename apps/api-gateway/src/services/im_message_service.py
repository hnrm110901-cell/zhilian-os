"""
统一 IM 消息推送服务 — 根据品牌 IM 配置自动选择企微或钉钉

核心功能：
- send_text() / send_markdown() / send_decision_card() — 统一接口
- 自动解析品牌所绑定的 IM 平台并调用对应 Service
- 无品牌配置时回退到全局企微 WeChatService
- 消息去重 + 失败重试由底层 Service 处理
"""

from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.brand_im_config import BrandIMConfig, IMPlatform

logger = structlog.get_logger()


class IMMessageService:
    """
    统一 IM 消息推送服务。

    用法：
        svc = IMMessageService(db)
        await svc.send_text(brand_id, user_id, "hello")
        await svc.send_decision_card(brand_id, user_id, title, desc, url)
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db

    async def _resolve_platform(self, brand_id: Optional[str]) -> str:
        """解析品牌 IM 平台类型"""
        if brand_id and self.db:
            try:
                result = await self.db.execute(
                    select(BrandIMConfig.im_platform).where(
                        and_(
                            BrandIMConfig.brand_id == brand_id,
                            BrandIMConfig.is_active.is_(True),
                        )
                    )
                )
                platform = result.scalar_one_or_none()
                if platform:
                    return platform.value if hasattr(platform, "value") else str(platform)
            except Exception as e:
                logger.warning("im_message.resolve_platform.failed", error=str(e))
        return "wechat_work"  # 默认企微

    async def _get_wechat(self):
        from .wechat_service import wechat_service

        return wechat_service

    async def _get_dingtalk(self, brand_id: Optional[str] = None):
        from .dingtalk_service import dingtalk_service

        # 尝试用品牌级配置覆盖
        if brand_id and self.db:
            try:
                result = await self.db.execute(
                    select(BrandIMConfig).where(
                        and_(
                            BrandIMConfig.brand_id == brand_id,
                            BrandIMConfig.is_active.is_(True),
                        )
                    )
                )
                config = result.scalar_one_or_none()
                if config and config.dingtalk_app_key:
                    dingtalk_service.configure(
                        app_key=config.dingtalk_app_key,
                        app_secret=config.dingtalk_app_secret,
                        agent_id=config.dingtalk_agent_id,
                    )
            except Exception as e:
                logger.warning("im_message.configure_dingtalk.failed", error=str(e))
        return dingtalk_service

    async def send_text(
        self,
        brand_id: Optional[str],
        to_user_id: str,
        content: str,
    ) -> Dict[str, Any]:
        """发送文本消息"""
        platform = await self._resolve_platform(brand_id)
        if platform == "dingtalk":
            dt = await self._get_dingtalk(brand_id)
            return await dt.send_text_message(content, userid_list=[to_user_id])
        else:
            wx = await self._get_wechat()
            return await wx.send_text_message(content, touser=to_user_id)

    async def send_markdown(
        self,
        brand_id: Optional[str],
        to_user_id: str,
        title: str,
        content: str,
    ) -> Dict[str, Any]:
        """发送 Markdown 消息"""
        platform = await self._resolve_platform(brand_id)
        if platform == "dingtalk":
            dt = await self._get_dingtalk(brand_id)
            return await dt.send_markdown_message(title, content, userid_list=[to_user_id])
        else:
            wx = await self._get_wechat()
            return await wx.send_markdown_message(content, touser=to_user_id)

    async def send_decision_card(
        self,
        brand_id: Optional[str],
        to_user_id: str,
        title: str,
        description: str,
        action_url: str,
        btntxt: str = "立即审批",
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """发送决策型卡片消息"""
        platform = await self._resolve_platform(brand_id)
        if platform == "dingtalk":
            dt = await self._get_dingtalk(brand_id)
            return await dt.send_decision_card(
                title=title,
                description=description,
                action_url=action_url,
                btntxt=btntxt,
                to_user_id=to_user_id,
                message_id=message_id,
            )
        else:
            wx = await self._get_wechat()
            return await wx.send_decision_card(
                title=title,
                description=description,
                action_url=action_url,
                btntxt=btntxt,
                to_user_id=to_user_id,
                message_id=message_id,
            )

    async def send_templated(
        self,
        brand_id: Optional[str],
        to_user_id: str,
        template: str,
        data: Dict[str, Any],
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """发送模板消息"""
        platform = await self._resolve_platform(brand_id)
        if platform == "dingtalk":
            dt = await self._get_dingtalk(brand_id)
            return await dt.send_templated_message(template, data, to_user_id, message_id)
        else:
            wx = await self._get_wechat()
            return await wx.send_templated_message(template, data, to_user_id, message_id)

    async def send_onboarding_welcome(
        self,
        brand_id: Optional[str],
        to_user_id: str,
        employee_name: str,
        store_name: str,
    ) -> Dict[str, Any]:
        """发送入职欢迎消息"""
        content = (
            f"### 欢迎加入 {store_name}！\n\n"
            f"**{employee_name}** 您好，\n\n"
            f"您的屯象OS系统账号已自动创建，"
            f"请使用企业IM登录系统完成以下入职事项：\n\n"
            f"1. 完善个人信息\n"
            f"2. 查看排班安排\n"
            f"3. 熟悉门店操作流程\n\n"
            f"如有任何问题，请联系您的店长。"
        )
        return await self.send_markdown(brand_id, to_user_id, "入职欢迎", content)

    async def send_schedule_notification(
        self,
        brand_id: Optional[str],
        to_user_id: str,
        employee_name: str,
        schedule_text: str,
    ) -> Dict[str, Any]:
        """发送排班通知"""
        content = (
            f"### 排班通知\n\n"
            f"**{employee_name}** 您好，您的排班已更新：\n\n"
            f"{schedule_text}\n\n"
            f"如需调班请在系统中申请。"
        )
        return await self.send_markdown(brand_id, to_user_id, "排班通知", content)

    async def send_payslip_notification(
        self,
        brand_id: Optional[str],
        to_user_id: str,
        employee_name: str,
        month: str,
        view_url: str,
    ) -> Dict[str, Any]:
        """发送工资条推送"""
        return await self.send_decision_card(
            brand_id=brand_id,
            to_user_id=to_user_id,
            title=f"【{month}工资条】{employee_name}",
            description=f"您的{month}工资条已生成，请点击查看详情。\n身份验证后可查看完整明细。",
            action_url=view_url,
            btntxt="查看",
        )
