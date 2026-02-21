"""
企业微信推送触发服务
WeChat Push Trigger Service

基于Neural System事件自动触发企业微信推送
"""
from typing import Dict, Any, Optional
import structlog
from datetime import datetime
from sqlalchemy import select

from ..services.wechat_service import WeChatService
from ..core.celery_tasks import celery_app
from ..core.database import get_db_session
from ..models.user import User, UserRole

logger = structlog.get_logger()


class WeChatTriggerService:
    """企业微信推送触发服务"""

    def __init__(self):
        self.wechat_service = WeChatService()
        self.trigger_rules = self._init_trigger_rules()

    def _init_trigger_rules(self) -> Dict[str, Dict[str, Any]]:
        """
        初始化触发规则

        定义哪些事件应该触发企微推送，以及推送的内容模板
        """
        return {
            # 订单相关触发
            "order.created": {
                "enabled": True,
                "template": "新订单提醒",
                "priority": "high",
                "target": "kitchen_staff",  # 后厨人员
                "message_template": "【新订单】\n订单号：{order_number}\n桌号：{table_number}\n金额：¥{total}\n时间：{order_time}",
            },
            "order.completed": {
                "enabled": True,
                "template": "订单完成通知",
                "priority": "normal",
                "target": "manager",  # 店长
                "message_template": "【订单完成】\n订单号：{order_number}\n金额：¥{total}\n完成时间：{completed_at}",
            },
            "order.cancelled": {
                "enabled": True,
                "template": "订单取消提醒",
                "priority": "high",
                "target": "manager",
                "message_template": "【订单取消】\n订单号：{order_number}\n原因：{cancel_reason}\n时间：{cancelled_at}",
            },

            # 预订相关触发
            "reservation.confirmed": {
                "enabled": True,
                "template": "预订确认通知",
                "priority": "normal",
                "target": "front_desk",  # 前台
                "message_template": "【预订确认】\n客户：{customer_name}\n电话：{customer_phone}\n人数：{party_size}人\n时间：{reservation_date}",
            },
            "reservation.cancelled": {
                "enabled": True,
                "template": "预订取消提醒",
                "priority": "high",
                "target": "front_desk",
                "message_template": "【预订取消】\n客户：{customer_name}\n电话：{customer_phone}\n原预订时间：{reservation_date}",
            },
            "reservation.arrived": {
                "enabled": True,
                "template": "客人到店通知",
                "priority": "high",
                "target": "service_staff",  # 服务员
                "message_template": "【客人到店】\n客户：{customer_name}\n预订人数：{party_size}人\n桌号：{table_number}",
            },

            # 会员相关触发
            "member.points_changed": {
                "enabled": True,
                "template": "会员积分变动",
                "priority": "low",
                "target": "member_manager",  # 会员管理员
                "message_template": "【积分变动】\n会员：{member_name}\n变动：{points_change}\n当前积分：{current_points}",
            },
            "member.level_upgraded": {
                "enabled": True,
                "template": "会员升级通知",
                "priority": "normal",
                "target": "member_manager",
                "message_template": "【会员升级】\n会员：{member_name}\n新等级：{new_level}\n恭喜升级！",
            },

            # 支付相关触发
            "payment.completed": {
                "enabled": True,
                "template": "支付完成通知",
                "priority": "normal",
                "target": "cashier",  # 收银员
                "message_template": "【支付完成】\n订单号：{order_number}\n金额：¥{amount}\n支付方式：{payment_method}",
            },
            "payment.failed": {
                "enabled": True,
                "template": "支付失败提醒",
                "priority": "high",
                "target": "cashier",
                "message_template": "【支付失败】\n订单号：{order_number}\n金额：¥{amount}\n失败原因：{failure_reason}",
            },

            # 库存相关触发
            "inventory.low_stock": {
                "enabled": True,
                "template": "库存不足预警",
                "priority": "high",
                "target": "inventory_manager",  # 库存管理员
                "message_template": "【库存预警】\n商品：{item_name}\n当前库存：{current_stock}\n预警阈值：{threshold}\n请及时补货！",
            },
            "inventory.out_of_stock": {
                "enabled": True,
                "template": "库存耗尽告警",
                "priority": "urgent",
                "target": "manager",
                "message_template": "【库存告警】\n商品：{item_name}\n当前库存：0\n已无法继续销售，请立即处理！",
            },

            # 异常事件触发
            "system.error": {
                "enabled": True,
                "template": "系统异常告警",
                "priority": "urgent",
                "target": "tech_support",  # 技术支持
                "message_template": "【系统异常】\n模块：{module}\n错误：{error_message}\n时间：{timestamp}",
            },
            "service.quality_issue": {
                "enabled": True,
                "template": "服务质量问题",
                "priority": "high",
                "target": "manager",
                "message_template": "【服务质量】\n问题类型：{issue_type}\n描述：{description}\n客户：{customer_name}\n请及时处理！",
            },

            # 任务相关触发
            "task.created": {
                "enabled": True,
                "template": "新任务分配",
                "priority": "high",
                "target": "assignee",  # 直接推送给指派人
                "message_template": "【新任务】\n任务：{title}\n内容：{content}\n优先级：{priority}\n截止时间：{due_at}\n请及时处理！",
            },
            "task.completed": {
                "enabled": True,
                "template": "任务完成通知",
                "priority": "normal",
                "target": "creator",  # 推送给创建人
                "message_template": "【任务完成】\n任务：{title}\n完成人：{assignee_name}\n完成时间：{completed_at}",
            },

            # 对账相关触发
            "reconcile.anomaly": {
                "enabled": True,
                "template": "对账异常预警",
                "priority": "urgent",
                "target": "manager",  # 推送给店长
                "message_template": "【对账异常】{reconciliation_date}\n⚠️ 发现账目差异\n\nPOS金额：¥{pos_amount:.2f}\n实际金额：¥{actual_amount:.2f}\n差异金额：¥{diff_amount:.2f}\n差异比例：{diff_ratio:.2f}%\n\n请及时核查处理！",
            },
        }

    async def should_trigger(
        self,
        event_type: str,
        event_data: Dict[str, Any],
    ) -> bool:
        """
        判断事件是否应该触发推送

        Args:
            event_type: 事件类型
            event_data: 事件数据

        Returns:
            是否应该触发
        """
        rule = self.trigger_rules.get(event_type)

        if not rule:
            return False

        if not rule.get("enabled", False):
            return False

        # 可以在这里添加更复杂的条件判断
        # 例如：只在营业时间推送、只推送给特定门店等

        return True

    async def trigger_push(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        触发企微推送

        Args:
            event_type: 事件类型
            event_data: 事件数据
            store_id: 门店ID

        Returns:
            推送结果
        """
        try:
            # 检查是否应该触发
            if not await self.should_trigger(event_type, event_data):
                logger.info(
                    "事件不满足触发条件",
                    event_type=event_type,
                )
                return {
                    "success": False,
                    "reason": "not_triggered",
                }

            # 获取触发规则
            rule = self.trigger_rules[event_type]

            # 生成消息内容
            message = self._generate_message(rule, event_data)

            # 获取推送目标
            target_users = await self._get_target_users(
                rule["target"],
                store_id,
                event_data  # 传递事件数据，用于处理特殊目标（如assignee、creator）
            )

            # 发送企微消息
            result = await self.wechat_service.send_text_message(
                content=message,
                touser=target_users,
            )

            logger.info(
                "企微推送触发成功",
                event_type=event_type,
                target=rule["target"],
                result=result,
            )

            return {
                "success": True,
                "event_type": event_type,
                "message": message,
                "target_users": target_users,
                "result": result,
            }

        except Exception as e:
            logger.error(
                "企微推送触发失败",
                event_type=event_type,
                error=str(e),
                exc_info=e,
            )
            return {
                "success": False,
                "error": str(e),
            }

    def _generate_message(
        self,
        rule: Dict[str, Any],
        event_data: Dict[str, Any],
    ) -> str:
        """
        生成推送消息内容

        Args:
            rule: 触发规则
            event_data: 事件数据

        Returns:
            消息内容
        """
        template = rule["message_template"]

        try:
            # 使用事件数据填充模板
            message = template.format(**event_data)
            return message
        except KeyError as e:
            logger.warning(
                "消息模板缺少字段",
                missing_field=str(e),
                event_data=event_data,
            )
            # 返回简化消息
            return f"{rule['template']}\n{event_data}"

    async def _get_target_users(
        self,
        target_role: str,
        store_id: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        获取推送目标用户

        Args:
            target_role: 目标角色或特殊标识（assignee、creator等）
            store_id: 门店ID
            event_data: 事件数据（用于获取特定用户ID）

        Returns:
            用户ID列表（用|分隔）
        """
        # 处理特殊目标：直接指定用户ID
        if target_role in ["assignee", "creator"] and event_data:
            user_id_key = f"{target_role}_id"
            user_id = event_data.get(user_id_key)

            if user_id:
                try:
                    # 查询用户的企微ID
                    async with get_db_session() as session:
                        result = await session.execute(
                            select(User).where(
                                User.id == uuid.UUID(user_id),
                                User.is_active == True,
                                User.wechat_user_id.isnot(None)
                            )
                        )
                        user = result.scalar_one_or_none()

                        if user and user.wechat_user_id:
                            return user.wechat_user_id

                except Exception as e:
                    logger.error(
                        "查询特定用户企微ID失败",
                        user_id=user_id,
                        error=str(e)
                    )

        # 映射触发规则中的角色名称到UserRole枚举
        role_mapping = {
            "kitchen_staff": [UserRole.HEAD_CHEF, UserRole.CHEF, UserRole.STATION_MANAGER],
            "manager": [UserRole.STORE_MANAGER, UserRole.ASSISTANT_MANAGER],
            "front_desk": [UserRole.TEAM_LEADER, UserRole.WAITER],
            "service_staff": [UserRole.WAITER, UserRole.TEAM_LEADER],
            "member_manager": [UserRole.CUSTOMER_MANAGER],
            "cashier": [UserRole.WAITER],  # 收银员通常由服务员兼任
            "inventory_manager": [UserRole.WAREHOUSE_MANAGER],
            "tech_support": [UserRole.ADMIN],
        }

        # 获取对应的UserRole枚举列表
        user_roles = role_mapping.get(target_role, [])

        if not user_roles:
            logger.warning(
                "未找到对应的用户角色映射",
                target_role=target_role
            )
            return "@all"

        try:
            async with get_db_session() as session:
                # 构建查询条件
                query = select(User).where(
                    User.is_active == True,
                    User.role.in_(user_roles),
                    User.wechat_user_id.isnot(None)
                )

                # 如果指定了门店，添加门店过滤
                if store_id:
                    query = query.where(User.store_id == store_id)

                # 执行查询
                result = await session.execute(query)
                users = result.scalars().all()

                # 提取企微用户ID
                wechat_user_ids = [
                    user.wechat_user_id
                    for user in users
                    if user.wechat_user_id
                ]

                if not wechat_user_ids:
                    logger.warning(
                        "未找到符合条件的用户",
                        target_role=target_role,
                        store_id=store_id,
                        user_roles=[role.value for role in user_roles]
                    )
                    return "@all"

                # 用|分隔多个用户ID
                user_id_str = "|".join(wechat_user_ids)

                logger.info(
                    "成功获取推送目标用户",
                    target_role=target_role,
                    store_id=store_id,
                    user_count=len(wechat_user_ids)
                )

                return user_id_str

        except Exception as e:
            logger.error(
                "查询推送目标用户失败",
                target_role=target_role,
                store_id=store_id,
                error=str(e),
                exc_info=e
            )
            # 出错时返回@all，确保消息能发送
            return "@all"


# Celery异步任务：处理企微推送
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
async def send_wechat_push_task(
    self,
    event_type: str,
    event_data: Dict[str, Any],
    store_id: Optional[str] = None,
):
    """
    异步发送企微推送

    Args:
        event_type: 事件类型
        event_data: 事件数据
        store_id: 门店ID
    """
    try:
        trigger_service = WeChatTriggerService()

        result = await trigger_service.trigger_push(
            event_type=event_type,
            event_data=event_data,
            store_id=store_id,
        )

        logger.info(
            "企微推送任务完成",
            event_type=event_type,
            result=result,
        )

        return result

    except Exception as e:
        logger.error(
            "企微推送任务失败",
            event_type=event_type,
            error=str(e),
            exc_info=e,
        )
        # 重试任务
        raise self.retry(exc=e)


# 全局服务实例
wechat_trigger_service = WeChatTriggerService()
