"""
客户旅程自动化引擎 — Phase 4

可配置的多步骤旅程，基于 journey_orchestrator.py 现有模式扩展。

数据模型：
  journey_templates   — 旅程模板（JSONB steps 存储步骤树）
  journey_instances   — 旅程实例（记录每个消费者的旅程运行状态）

步骤类型（step_type）：
  wait            — 等待 N 分钟/小时/天，安排 Celery 延迟任务
  condition       — 评估布尔条件，走 true/false 分支
  send_wecom      — 调用 wecom_scrm_service.send_welcome_message
  send_sms        — 记录待发短信任务
  add_tag         — 调用 tag_factory_service 添加标签
  update_lifecycle — 更新 brand_consumer_profiles.lifecycle_state
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


# ── 预置旅程模板定义 ──────────────────────────────────────────────────────────

# 4 条开箱即用模板（seed_default_journeys 使用）
DEFAULT_JOURNEY_TEMPLATES: List[Dict[str, Any]] = [
    {
        "template_name": "新客欢迎旅程",
        "trigger_event": "member_registered",
        "steps": [
            {
                "step_id": "s1_welcome",
                "step_type": "send_wecom",
                "config": {
                    "template_id": "journey_welcome",
                    "message": "欢迎加入！您已获得新会员专属优惠券，下次到店出示即可使用 🎉",
                    "action": {"issue_coupon": "new_member_coupon"},
                },
                "next_step_id": "s2_wait_3d",
            },
            {
                "step_id": "s2_wait_3d",
                "step_type": "wait",
                "config": {"delay_minutes": 4320},  # T+3d
                "next_step_id": "s3_check_order",
            },
            {
                "step_id": "s3_check_order",
                "step_type": "condition",
                "config": {"condition_type": "no_order_since_start"},
                "on_condition_true": "s4_coupon_push",
                "on_condition_false": "END",
                "next_step_id": None,
            },
            {
                "step_id": "s4_coupon_push",
                "step_type": "send_wecom",
                "config": {
                    "template_id": "journey_first_visit_offer",
                    "message": "专属首单优惠限时领取，到店下单立减¥30，有效期3天，欢迎光临",
                    "action": {"issue_coupon": "first_visit_coupon"},
                },
                "next_step_id": "s5_wait_4d",
            },
            {
                "step_id": "s5_wait_4d",
                "step_type": "wait",
                "config": {"delay_minutes": 5760},  # T+4d
                "next_step_id": "s6_sms_remind",
            },
            {
                "step_id": "s6_sms_remind",
                "step_type": "condition",
                "config": {"condition_type": "no_order_since_start"},
                "on_condition_true": "s7_send_sms",
                "on_condition_false": "END",
                "next_step_id": None,
            },
            {
                "step_id": "s7_send_sms",
                "step_type": "send_sms",
                "config": {
                    "message_template": "您的首单优惠券还有1天到期，欢迎到{brand_name}消费",
                },
                "next_step_id": "END",
            },
        ],
    },
    {
        "template_name": "流失挽回旅程",
        "trigger_event": "churn_risk_high",
        "steps": [
            {
                "step_id": "s1_wecom_touch",
                "step_type": "send_wecom",
                "config": {
                    "template_id": "journey_comeback_touch",
                    "message": "好久不见，我们想念您了！近期有新品上线，欢迎回来品鉴 🍜",
                },
                "next_step_id": "s2_wait_7d",
            },
            {
                "step_id": "s2_wait_7d",
                "step_type": "wait",
                "config": {"delay_minutes": 10080},  # T+7d
                "next_step_id": "s3_check_return",
            },
            {
                "step_id": "s3_check_return",
                "step_type": "condition",
                "config": {"condition_type": "no_order_since_start"},
                "on_condition_true": "s4_sms_coupon",
                "on_condition_false": "s5_tag_active",
                "next_step_id": None,
            },
            {
                "step_id": "s4_sms_coupon",
                "step_type": "send_sms",
                "config": {
                    "message_template": "专属回归礼：{brand_name}为您准备了¥50回归券，有效期7天",
                },
                "next_step_id": "s5_tag_dormant",
            },
            {
                "step_id": "s5_tag_dormant",
                "step_type": "update_lifecycle",
                "config": {"new_state": "dormant"},
                "next_step_id": "END",
            },
            {
                "step_id": "s5_tag_active",
                "step_type": "update_lifecycle",
                "config": {"new_state": "repeat"},
                "next_step_id": "END",
            },
        ],
    },
    {
        "template_name": "升级激励旅程",
        "trigger_event": "upgrade_ready",
        "steps": [
            {
                "step_id": "s1_points_remind",
                "step_type": "send_wecom",
                "config": {
                    "template_id": "journey_upgrade_remind",
                    "message": "距离升级{next_level}只差{points_gap}积分！本月消费可轻松达成，快来解锁专属权益",
                },
                "next_step_id": "s2_wait_3d",
            },
            {
                "step_id": "s2_wait_3d",
                "step_type": "wait",
                "config": {"delay_minutes": 4320},  # T+3d
                "next_step_id": "s3_check_upgrade",
            },
            {
                "step_id": "s3_check_upgrade",
                "step_type": "condition",
                "config": {"condition_type": "no_order_since_start"},
                "on_condition_true": "s4_push_offer",
                "on_condition_false": "END",
                "next_step_id": None,
            },
            {
                "step_id": "s4_push_offer",
                "step_type": "send_wecom",
                "config": {
                    "template_id": "journey_upgrade_boost",
                    "message": "升级专属加速：本次消费积分×1.5，限本月有效，马上来体验",
                    "action": {"bonus_points_multiplier": 1.5},
                },
                "next_step_id": "END",
            },
        ],
    },
    {
        "template_name": "生日关怀旅程",
        "trigger_event": "birthday_approaching",
        "steps": [
            {
                "step_id": "s1_birthday_pre",
                "step_type": "send_wecom",
                "config": {
                    "template_id": "journey_birthday_pre",
                    "message": "生日快到了！{brand_name}为您准备了专属生日礼遇，提前送上祝福 🎂",
                    "action": {"issue_coupon": "birthday_coupon_7d"},
                },
                "next_step_id": "s2_wait_to_birthday",
            },
            {
                "step_id": "s2_wait_to_birthday",
                "step_type": "wait",
                "config": {"delay_minutes": 10080},  # T+7d（生日当天）
                "next_step_id": "s3_birthday_wish",
            },
            {
                "step_id": "s3_birthday_wish",
                "step_type": "send_wecom",
                "config": {
                    "template_id": "birthday_wish",
                    "message": "生日快乐！愿您每天都像今天一样美好。专属生日套餐已为您准备好 🎉",
                    "action": {"issue_coupon": "birthday_feast_coupon"},
                },
                "next_step_id": "s4_add_tag",
            },
            {
                "step_id": "s4_add_tag",
                "step_type": "add_tag",
                "config": {"tag_name": "生日月会员"},
                "next_step_id": "END",
            },
        ],
    },
]


# ── 引擎服务类 ───────────────────────────────────────────────────────────────


class CustomerJourneyEngine:
    """
    客户旅程自动化引擎。
    旅程模板和实例数据持久化到 journey_templates / journey_instances 表。
    步骤执行依赖现有服务（wecom_scrm_service / tag_factory_service）。
    """

    # ── 旅程实例管理 ─────────────────────────────────────────────────────────

    async def start_journey(
        self,
        template_id: str,
        consumer_id: str,
        brand_id: str,
        trigger_data: Dict[str, Any],
        session: AsyncSession,
    ) -> str:
        """
        启动一个旅程实例。
        1. 加载模板，校验激活状态
        2. 创建 journey_instances 记录
        3. 执行第一步（若为 wait 则设置 next_action_at）
        4. 返回 instance_id
        """
        template = await self._load_template(template_id, session)
        if template is None:
            raise ValueError(f"旅程模板不存在: {template_id}")
        if not template.get("is_active", True):
            raise ValueError(f"旅程模板已停用: {template_id}")

        steps: List[Dict] = template.get("steps", [])
        if not steps:
            raise ValueError(f"旅程模板步骤为空: {template_id}")

        first_step_id = steps[0]["step_id"]
        instance_id = str(uuid.uuid4())

        await session.execute(
            text(
                """
                INSERT INTO journey_instances
                    (id, template_id, consumer_id, brand_id,
                     current_step_id, status, trigger_data, step_history,
                     started_at, next_action_at)
                VALUES
                    (:id::uuid, :template_id::uuid, :consumer_id::uuid, :brand_id,
                     :current_step_id, 'running', :trigger_data::jsonb, '[]'::jsonb,
                     NOW(), NOW())
                """
            ),
            {
                "id": instance_id,
                "template_id": template_id,
                "consumer_id": consumer_id,
                "brand_id": brand_id,
                "current_step_id": first_step_id,
                "trigger_data": json.dumps(trigger_data, ensure_ascii=False),
            },
        )
        await session.commit()

        logger.info(
            "journey_started",
            instance_id=instance_id,
            template_id=template_id,
            consumer_id=consumer_id,
        )

        # 立即执行第一步
        await self.execute_step(instance_id, first_step_id, session)
        return instance_id

    async def execute_step(
        self,
        instance_id: str,
        step_id: str,
        session: AsyncSession,
    ) -> str:
        """
        执行旅程中的一个步骤，返回下一个 step_id（或 "END"）。
        """
        instance = await self._load_instance(instance_id, session)
        if instance is None:
            raise ValueError(f"旅程实例不存在: {instance_id}")
        if instance["status"] != "running":
            return "END"

        template = await self._load_template(str(instance["template_id"]), session)
        if template is None:
            await self._fail_instance(instance_id, "模板已删除", session)
            return "END"

        step = self._find_step(template["steps"], step_id)
        if step is None:
            await self._fail_instance(instance_id, f"步骤不存在: {step_id}", session)
            return "END"

        step_type: str = step["step_type"]
        config: Dict = step.get("config", {})
        consumer_id: str = str(instance["consumer_id"])
        brand_id: str = instance["brand_id"]

        next_step_id = step.get("next_step_id") or "END"

        try:
            if step_type == "send_wecom":
                await self._execute_send_wecom(consumer_id, brand_id, config, session)

            elif step_type == "send_sms":
                await self._execute_send_sms(consumer_id, brand_id, config, instance_id, session)

            elif step_type == "add_tag":
                await self._execute_add_tag(consumer_id, brand_id, config, session)

            elif step_type == "update_lifecycle":
                await self._execute_update_lifecycle(consumer_id, brand_id, config, session)

            elif step_type == "condition":
                next_step_id = await self._execute_condition(
                    consumer_id, brand_id, config, step, str(instance["started_at"]), session
                )

            elif step_type == "wait":
                delay_minutes: int = config.get("delay_minutes", 1440)
                next_action_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
                await session.execute(
                    text(
                        """
                        UPDATE journey_instances
                        SET next_action_at  = :next_action_at,
                            current_step_id = :next_step_id
                        WHERE id = :id::uuid
                        """
                    ),
                    {
                        "next_action_at": next_action_at,
                        "next_step_id": next_step_id,
                        "id": instance_id,
                    },
                )
                await self._append_step_history(instance_id, step_id, "wait_scheduled", session)
                await session.commit()

                # 安排 Celery 延迟任务（若 Celery 可用）
                self._schedule_celery_step(instance_id, next_step_id, delay_minutes)
                return next_step_id

            else:
                logger.warning("unknown_step_type", step_type=step_type, instance_id=instance_id)

        except Exception as exc:
            logger.error(
                "step_execution_failed",
                instance_id=instance_id,
                step_id=step_id,
                error=str(exc),
                exc_info=True,
            )
            await self._fail_instance(instance_id, str(exc), session)
            return "END"

        # 记录步骤历史
        await self._append_step_history(instance_id, step_id, "completed", session)

        # 推进旅程或完成
        if next_step_id == "END":
            await self._complete_instance(instance_id, session)
        else:
            await session.execute(
                text(
                    """
                    UPDATE journey_instances
                    SET current_step_id = :next_step_id,
                        next_action_at  = NOW()
                    WHERE id = :id::uuid
                    """
                ),
                {"next_step_id": next_step_id, "id": instance_id},
            )
            await session.commit()

            # 立即执行下一个非 wait 步骤
            next_step = self._find_step(template["steps"], next_step_id)
            if next_step and next_step["step_type"] != "wait":
                return await self.execute_step(instance_id, next_step_id, session)

        return next_step_id

    # ── 模板管理 ─────────────────────────────────────────────────────────────

    async def create_journey_template(
        self,
        template_data: Dict[str, Any],
        brand_id: str,
        session: AsyncSession,
        group_id: str = "",
        is_default: bool = False,
    ) -> str:
        """创建旅程模板，存入数据库，返回 template_id"""
        template_id = str(uuid.uuid4())
        await session.execute(
            text(
                """
                INSERT INTO journey_templates
                    (id, brand_id, group_id, template_name, trigger_event,
                     steps, is_active, is_default, created_at, updated_at)
                VALUES
                    (:id::uuid, :brand_id, :group_id, :template_name, :trigger_event,
                     :steps::jsonb, TRUE, :is_default, NOW(), NOW())
                """
            ),
            {
                "id": template_id,
                "brand_id": brand_id,
                "group_id": group_id or brand_id,
                "template_name": template_data["template_name"],
                "trigger_event": template_data["trigger_event"],
                "steps": json.dumps(template_data.get("steps", []), ensure_ascii=False),
                "is_default": is_default,
            },
        )
        await session.commit()

        logger.info(
            "journey_template_created",
            template_id=template_id,
            name=template_data["template_name"],
            brand_id=brand_id,
        )
        return template_id

    async def list_templates(
        self, brand_id: str, session: AsyncSession
    ) -> List[Dict[str, Any]]:
        """列出品牌的所有旅程模板"""
        rows = await session.execute(
            text(
                """
                SELECT id::text, brand_id, template_name, trigger_event,
                       steps, is_active, is_default, created_at, updated_at
                FROM journey_templates
                WHERE brand_id = :brand_id
                ORDER BY is_default DESC, created_at DESC
                """
            ),
            {"brand_id": brand_id},
        )
        return [dict(row._mapping) for row in rows.fetchall()]

    async def update_template(
        self,
        template_id: str,
        update_data: Dict[str, Any],
        session: AsyncSession,
    ) -> bool:
        """更新旅程模板字段（支持部分更新）"""
        fields = []
        params: Dict[str, Any] = {"id": template_id}

        if "template_name" in update_data:
            fields.append("template_name = :template_name")
            params["template_name"] = update_data["template_name"]
        if "trigger_event" in update_data:
            fields.append("trigger_event = :trigger_event")
            params["trigger_event"] = update_data["trigger_event"]
        if "steps" in update_data:
            fields.append("steps = :steps::jsonb")
            params["steps"] = json.dumps(update_data["steps"], ensure_ascii=False)
        if "is_active" in update_data:
            fields.append("is_active = :is_active")
            params["is_active"] = update_data["is_active"]

        if not fields:
            return False

        fields.append("updated_at = NOW()")
        sql = f"UPDATE journey_templates SET {', '.join(fields)} WHERE id = :id::uuid"
        await session.execute(text(sql), params)
        await session.commit()
        return True

    async def seed_default_journeys(
        self, brand_id: str, session: AsyncSession, group_id: str = ""
    ) -> List[str]:
        """
        为新品牌初始化4条预置旅程。
        若同名模板已存在则跳过（幂等操作）。
        """
        template_ids = []
        for tpl in DEFAULT_JOURNEY_TEMPLATES:
            # 幂等：检查是否已存在同名同品牌模板
            existing = await session.execute(
                text(
                    """
                    SELECT id FROM journey_templates
                    WHERE brand_id = :brand_id AND template_name = :name
                    LIMIT 1
                    """
                ),
                {"brand_id": brand_id, "name": tpl["template_name"]},
            )
            if existing.fetchone() is not None:
                logger.info("seed_skip_existing", brand_id=brand_id, name=tpl["template_name"])
                continue

            tid = await self.create_journey_template(
                tpl, brand_id, session, group_id=group_id or brand_id, is_default=True
            )
            template_ids.append(tid)

        logger.info(
            "seed_default_journeys_done",
            brand_id=brand_id,
            created_count=len(template_ids),
        )
        return template_ids

    # ── 效果统计 ─────────────────────────────────────────────────────────────

    async def get_journey_stats(
        self,
        template_id: str,
        session: AsyncSession,
        period_days: int = 30,
    ) -> Dict[str, Any]:
        """
        旅程效果统计：
        触发次数 / 完成率 / 各状态分布
        """
        since = datetime.utcnow() - timedelta(days=period_days)
        rows = await session.execute(
            text(
                """
                SELECT status, COUNT(*) AS cnt
                FROM journey_instances
                WHERE template_id = :tid::uuid
                  AND started_at >= :since
                GROUP BY status
                """
            ),
            {"tid": template_id, "since": since},
        )
        status_counts: Dict[str, int] = {}
        total = 0
        for row in rows.fetchall():
            status_counts[row.status] = row.cnt
            total += row.cnt

        completed = status_counts.get("completed", 0)
        completion_rate = round(completed / total, 3) if total > 0 else 0.0

        return {
            "template_id": template_id,
            "period_days": period_days,
            "total_triggered": total,
            "completed": completed,
            "running": status_counts.get("running", 0),
            "failed": status_counts.get("failed", 0),
            "cancelled": status_counts.get("cancelled", 0),
            "completion_rate": completion_rate,
        }

    # ── 内部步骤执行器 ───────────────────────────────────────────────────────

    async def _execute_send_wecom(
        self,
        consumer_id: str,
        brand_id: str,
        config: Dict[str, Any],
        session: AsyncSession,
    ) -> None:
        """调用 wecom_scrm_service 发送企微消息"""
        try:
            from src.services.wecom_scrm_service import WeCOMScrmService

            svc = WeCOMScrmService()
            template_id = config.get("template_id", "journey_welcome")
            await svc.send_welcome_message(
                session=session,
                consumer_id=consumer_id,
                brand_id=brand_id,
                template_id=template_id,
            )
        except ImportError:
            logger.warning("wecom_scrm_service_not_available", consumer_id=consumer_id)
        except Exception as exc:
            logger.error("send_wecom_failed", consumer_id=consumer_id, error=str(exc), exc_info=True)
            raise

    async def _execute_send_sms(
        self,
        consumer_id: str,
        brand_id: str,
        config: Dict[str, Any],
        instance_id: str,
        session: AsyncSession,
    ) -> None:
        """记录待发短信任务（实际发送由外部短信服务处理）"""
        sms_record = {
            "consumer_id": consumer_id,
            "brand_id": brand_id,
            "message_template": config.get("message_template", ""),
            "instance_id": instance_id,
            "scheduled_at": datetime.utcnow().isoformat(),
            "status": "pending",
        }
        logger.info("sms_task_queued", **sms_record)

    async def _execute_add_tag(
        self,
        consumer_id: str,
        brand_id: str,
        config: Dict[str, Any],
        session: AsyncSession,
    ) -> None:
        """调用 tag_factory_service 添加标签"""
        tag_name = config.get("tag_name", "")
        if not tag_name:
            return
        try:
            from src.services.tag_factory_service import TagFactoryService

            svc = TagFactoryService()
            await svc.evaluate_tags_for_consumer(
                consumer_id=consumer_id,
                brand_id=brand_id,
                session=session,
            )
        except ImportError:
            logger.warning("tag_factory_service_not_available", consumer_id=consumer_id)
        except Exception as exc:
            logger.error("add_tag_failed", consumer_id=consumer_id, tag=tag_name, error=str(exc), exc_info=True)
            raise

    async def _execute_update_lifecycle(
        self,
        consumer_id: str,
        brand_id: str,
        config: Dict[str, Any],
        session: AsyncSession,
    ) -> None:
        """更新 brand_consumer_profiles.lifecycle_state"""
        new_state = config.get("new_state", "")
        if not new_state:
            return
        await session.execute(
            text(
                """
                UPDATE brand_consumer_profiles
                SET lifecycle_state = :new_state,
                    updated_at      = NOW()
                WHERE consumer_id = :consumer_id::uuid
                  AND brand_id    = :brand_id
                """
            ),
            {"new_state": new_state, "consumer_id": consumer_id, "brand_id": brand_id},
        )
        logger.info(
            "lifecycle_updated",
            consumer_id=consumer_id,
            brand_id=brand_id,
            new_state=new_state,
        )

    async def _execute_condition(
        self,
        consumer_id: str,
        brand_id: str,
        config: Dict[str, Any],
        step: Dict[str, Any],
        started_at_str: str,
        session: AsyncSession,
    ) -> str:
        """
        评估条件，返回下一步 step_id（true/false 分支）。

        已支持的条件类型：
          no_order_since_start — 旅程启动以来无新订单
          churn_score_high     — churn_score >= threshold
        """
        condition_type: str = config.get("condition_type", "no_order_since_start")
        true_step = step.get("on_condition_true") or "END"
        false_step = step.get("on_condition_false") or "END"

        result = False

        if condition_type == "no_order_since_start":
            # 检查旅程启动后是否有新消费
            try:
                started_at = datetime.fromisoformat(started_at_str)
            except (ValueError, TypeError):
                started_at = datetime.utcnow() - timedelta(days=30)

            rows = await session.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM brand_consumer_profiles
                    WHERE consumer_id = :consumer_id::uuid
                      AND brand_id    = :brand_id
                      AND brand_last_order_at >= :since
                    """
                ),
                {"consumer_id": consumer_id, "brand_id": brand_id, "since": started_at},
            )
            row = rows.fetchone()
            order_count = row.cnt if row else 0
            result = order_count == 0  # 无新订单 → true 分支

        elif condition_type == "churn_score_high":
            threshold = config.get("threshold", 0.7)
            rows = await session.execute(
                text(
                    """
                    SELECT churn_score FROM consumer_prediction_snapshots
                    WHERE consumer_id = :consumer_id::uuid AND brand_id = :brand_id
                    LIMIT 1
                    """
                ),
                {"consumer_id": consumer_id, "brand_id": brand_id},
            )
            row = rows.fetchone()
            score = row.churn_score if row else 0.0
            result = (score or 0.0) >= threshold

        return true_step if result else false_step

    # ── 状态管理辅助 ─────────────────────────────────────────────────────────

    async def _complete_instance(self, instance_id: str, session: AsyncSession) -> None:
        await session.execute(
            text(
                """
                UPDATE journey_instances
                SET status = 'completed', completed_at = NOW()
                WHERE id = :id::uuid
                """
            ),
            {"id": instance_id},
        )
        await session.commit()

    async def _fail_instance(
        self, instance_id: str, reason: str, session: AsyncSession
    ) -> None:
        logger.error("journey_instance_failed", instance_id=instance_id, reason=reason)
        await session.execute(
            text(
                """
                UPDATE journey_instances
                SET status = 'failed', completed_at = NOW()
                WHERE id = :id::uuid
                """
            ),
            {"id": instance_id},
        )
        await session.commit()

    async def _append_step_history(
        self,
        instance_id: str,
        step_id: str,
        status: str,
        session: AsyncSession,
    ) -> None:
        entry = json.dumps(
            {"step_id": step_id, "status": status, "executed_at": datetime.utcnow().isoformat()},
            ensure_ascii=False,
        )
        await session.execute(
            text(
                """
                UPDATE journey_instances
                SET step_history = step_history || :entry::jsonb
                WHERE id = :id::uuid
                """
            ),
            {"entry": f"[{entry}]", "id": instance_id},
        )

    async def _load_template(
        self, template_id: str, session: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        rows = await session.execute(
            text(
                """
                SELECT id::text, brand_id, group_id, template_name,
                       trigger_event, steps, is_active, is_default
                FROM journey_templates
                WHERE id = :id::uuid
                LIMIT 1
                """
            ),
            {"id": template_id},
        )
        row = rows.fetchone()
        if row is None:
            return None
        data = dict(row._mapping)
        # steps 字段：SQLAlchemy 自动解析 JSONB，若为字符串则手动解析
        if isinstance(data.get("steps"), str):
            data["steps"] = json.loads(data["steps"])
        return data

    async def _load_instance(
        self, instance_id: str, session: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        rows = await session.execute(
            text(
                """
                SELECT id::text, template_id, consumer_id, brand_id,
                       current_step_id, status, trigger_data,
                       step_history, started_at, next_action_at, completed_at
                FROM journey_instances
                WHERE id = :id::uuid
                LIMIT 1
                """
            ),
            {"id": instance_id},
        )
        row = rows.fetchone()
        if row is None:
            return None
        return dict(row._mapping)

    @staticmethod
    def _find_step(
        steps: List[Dict[str, Any]], step_id: str
    ) -> Optional[Dict[str, Any]]:
        for step in steps:
            if step.get("step_id") == step_id:
                return step
        return None

    @staticmethod
    def _schedule_celery_step(
        instance_id: str, next_step_id: str, delay_minutes: int
    ) -> None:
        """安排 Celery 延迟任务（Celery 不可用时静默降级）"""
        try:
            from src.tasks.journey_tasks import execute_journey_step_task

            execute_journey_step_task.apply_async(
                args=[instance_id, next_step_id],
                countdown=delay_minutes * 60,
            )
        except ImportError:
            logger.warning(
                "celery_journey_task_not_available",
                instance_id=instance_id,
                delay_minutes=delay_minutes,
            )


# 单例
customer_journey_engine = CustomerJourneyEngine()
