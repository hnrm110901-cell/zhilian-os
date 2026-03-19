"""
通用审批流引擎 — 多级路由/委托/催办/超期升级
支持请假、薪资调整、入离调转、奖惩、合同续签等多种业务场景

用法：
    engine = ApprovalEngine()
    instance = await engine.submit(db, template_code="leave", ...)
    await engine.approve(db, instance_id, approver_id, approver_name)
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.approval import ApprovalDelegation, ApprovalInstance, ApprovalRecord, ApprovalStatus, ApprovalTemplate
from src.models.employee import Employee

logger = structlog.get_logger()


class ApprovalEngine:
    """通用审批流引擎"""

    # ──────────────────────────────────────────────────────────
    #  提交审批
    # ──────────────────────────────────────────────────────────

    async def submit(
        self,
        db: AsyncSession,
        template_code: str,
        business_type: str,
        business_id: str,
        applicant_id: str,
        applicant_name: str,
        store_id: str,
        brand_id: str,
        amount_fen: Optional[int] = None,
        summary: Optional[str] = None,
    ) -> ApprovalInstance:
        """发起审批"""
        # 1. 查找审批模板
        template = await self._get_template(db, template_code)
        if not template:
            raise ValueError(f"审批模板 {template_code} 不存在或未启用")

        chain = list(template.approval_chain or [])

        # 2. 根据 amount_fen 判断是否需要额外审批层级
        if amount_fen is not None and template.amount_thresholds:
            for threshold in sorted(template.amount_thresholds, key=lambda t: t.get("threshold_fen", 0)):
                thr = threshold.get("threshold_fen", 0)
                extra_role = threshold.get("extra_approver_role")
                if amount_fen >= thr and extra_role:
                    # 避免重复添加
                    existing_roles = {step.get("role") for step in chain}
                    if extra_role not in existing_roles:
                        new_level = max((s.get("level", 0) for s in chain), default=0) + 1
                        chain.append(
                            {
                                "level": new_level,
                                "role": extra_role,
                                "timeout_hours": 72,
                            }
                        )

        # 重新排序
        chain.sort(key=lambda s: s.get("level", 0))

        # 3. 计算第一级 deadline
        first_timeout = chain[0].get("timeout_hours", 24) if chain else 24
        deadline = datetime.utcnow() + timedelta(hours=first_timeout)

        # 4. 创建 ApprovalInstance
        instance = ApprovalInstance(
            brand_id=brand_id,
            store_id=store_id,
            template_code=template_code,
            business_type=business_type,
            business_id=business_id,
            applicant_id=applicant_id,
            applicant_name=applicant_name,
            status=ApprovalStatus.PENDING.value,
            current_level=chain[0].get("level", 1) if chain else 1,
            amount_fen=amount_fen,
            summary=summary,
            deadline=deadline,
        )
        db.add(instance)
        await db.flush()

        logger.info(
            "approval.submitted",
            instance_id=str(instance.id),
            template_code=template_code,
            business_type=business_type,
            applicant_id=applicant_id,
        )

        # 5. 通知第一级审批人
        if chain:
            first_role = chain[0].get("role", "store_manager")
            approver = await self._resolve_approver(db, first_role, store_id, brand_id)
            if approver:
                await self._notify_approver(db, instance, approver, brand_id)

        return instance

    # ──────────────────────────────────────────────────────────
    #  审批通过
    # ──────────────────────────────────────────────────────────

    async def approve(
        self,
        db: AsyncSession,
        instance_id: UUID,
        approver_id: str,
        approver_name: str,
        comment: Optional[str] = None,
    ) -> ApprovalInstance:
        """审批通过"""
        instance = await self._get_instance(db, instance_id)
        if not instance:
            raise ValueError(f"审批实例 {instance_id} 不存在")
        if instance.status != ApprovalStatus.PENDING.value:
            raise ValueError(f"审批实例状态为 {instance.status}，无法操作")

        template = await self._get_template(db, instance.template_code)
        chain = list(template.approval_chain) if template else []
        chain.sort(key=lambda s: s.get("level", 0))

        # 检查委托代理
        actual_approver_id = approver_id
        actual_approver_name = approver_name
        delegated_to_id = None
        delegated_to_name = None

        delegation = await self._check_delegation(db, approver_id, instance.template_code, instance.brand_id)
        if delegation:
            delegated_to_id = delegation.delegate_id
            delegated_to_name = delegation.delegate_name

        # 当前级别的角色
        current_step = self._find_step(chain, instance.current_level)
        current_role = current_step.get("role", "") if current_step else ""

        # 写入 ApprovalRecord
        record = ApprovalRecord(
            instance_id=instance.id,
            level=instance.current_level,
            approver_id=actual_approver_id,
            approver_name=actual_approver_name,
            approver_role=current_role,
            action="approve",
            comment=comment,
            acted_at=datetime.utcnow(),
            delegated_to_id=delegated_to_id,
            delegated_to_name=delegated_to_name,
        )
        db.add(record)

        # 判断是否最后一级
        next_step = self._find_next_step(chain, instance.current_level)
        if next_step is None:
            # 审批完成
            instance.status = ApprovalStatus.APPROVED.value
            instance.final_result = "approved"
            instance.completed_at = datetime.utcnow()
            instance.deadline = None
            logger.info(
                "approval.completed",
                instance_id=str(instance_id),
                result="approved",
            )
        else:
            # 推进到下一级
            instance.current_level = next_step.get("level", instance.current_level + 1)
            timeout_hours = next_step.get("timeout_hours", 48)
            instance.deadline = datetime.utcnow() + timedelta(hours=timeout_hours)

            # 通知下一级审批人
            next_role = next_step.get("role", "store_manager")
            approver = await self._resolve_approver(db, next_role, instance.store_id, instance.brand_id)
            if approver:
                await self._notify_approver(db, instance, approver, instance.brand_id)

            logger.info(
                "approval.advanced",
                instance_id=str(instance_id),
                next_level=instance.current_level,
            )

        await db.flush()
        return instance

    # ──────────────────────────────────────────────────────────
    #  审批驳回
    # ──────────────────────────────────────────────────────────

    async def reject(
        self,
        db: AsyncSession,
        instance_id: UUID,
        approver_id: str,
        approver_name: str,
        comment: Optional[str] = None,
    ) -> ApprovalInstance:
        """审批驳回"""
        instance = await self._get_instance(db, instance_id)
        if not instance:
            raise ValueError(f"审批实例 {instance_id} 不存在")
        if instance.status != ApprovalStatus.PENDING.value:
            raise ValueError(f"审批实例状态为 {instance.status}，无法操作")

        template = await self._get_template(db, instance.template_code)
        chain = list(template.approval_chain) if template else []
        current_step = self._find_step(chain, instance.current_level)
        current_role = current_step.get("role", "") if current_step else ""

        record = ApprovalRecord(
            instance_id=instance.id,
            level=instance.current_level,
            approver_id=approver_id,
            approver_name=approver_name,
            approver_role=current_role,
            action="reject",
            comment=comment,
            acted_at=datetime.utcnow(),
        )
        db.add(record)

        instance.status = ApprovalStatus.REJECTED.value
        instance.final_result = "rejected"
        instance.completed_at = datetime.utcnow()
        instance.deadline = None

        await db.flush()

        logger.info(
            "approval.rejected",
            instance_id=str(instance_id),
            approver_id=approver_id,
        )

        # 通知申请人
        await self._notify_applicant_result(db, instance, "rejected", instance.brand_id)

        return instance

    # ──────────────────────────────────────────────────────────
    #  转交审批
    # ──────────────────────────────────────────────────────────

    async def delegate(
        self,
        db: AsyncSession,
        instance_id: UUID,
        approver_id: str,
        delegate_to_id: str,
        delegate_to_name: str,
        comment: Optional[str] = None,
    ) -> ApprovalInstance:
        """转交审批给其他人"""
        instance = await self._get_instance(db, instance_id)
        if not instance:
            raise ValueError(f"审批实例 {instance_id} 不存在")
        if instance.status != ApprovalStatus.PENDING.value:
            raise ValueError(f"审批实例状态为 {instance.status}，无法转交")

        template = await self._get_template(db, instance.template_code)
        chain = list(template.approval_chain) if template else []
        current_step = self._find_step(chain, instance.current_level)
        current_role = current_step.get("role", "") if current_step else ""

        record = ApprovalRecord(
            instance_id=instance.id,
            level=instance.current_level,
            approver_id=approver_id,
            approver_name="",
            approver_role=current_role,
            action="delegate",
            comment=comment or f"转交给 {delegate_to_name}",
            acted_at=datetime.utcnow(),
            delegated_to_id=delegate_to_id,
            delegated_to_name=delegate_to_name,
        )
        db.add(record)
        await db.flush()

        logger.info(
            "approval.delegated",
            instance_id=str(instance_id),
            from_id=approver_id,
            to_id=delegate_to_id,
        )

        # 通知被委托人
        await self._notify_approver(db, instance, {"id": delegate_to_id, "name": delegate_to_name}, instance.brand_id)

        return instance

    # ──────────────────────────────────────────────────────────
    #  超期检查（Celery 定时调用）
    # ──────────────────────────────────────────────────────────

    async def check_timeouts(self, db: AsyncSession) -> Dict[str, Any]:
        """检查超期审批 — 自动升级到下一级审批人 / 推送催办通知"""
        now = datetime.utcnow()
        result = await db.execute(
            select(ApprovalInstance).where(
                and_(
                    ApprovalInstance.status == ApprovalStatus.PENDING.value,
                    ApprovalInstance.deadline.isnot(None),
                    ApprovalInstance.deadline < now,
                )
            )
        )
        timed_out = result.scalars().all()

        escalated_count = 0
        notified_count = 0

        for instance in timed_out:
            template = await self._get_template(db, instance.template_code)
            chain = list(template.approval_chain) if template else []
            chain.sort(key=lambda s: s.get("level", 0))

            next_step = self._find_next_step(chain, instance.current_level)

            if next_step:
                # 自动升级到下一级
                record = ApprovalRecord(
                    instance_id=instance.id,
                    level=instance.current_level,
                    approver_id="system",
                    approver_name="系统自动升级",
                    approver_role="system",
                    action="escalate",
                    comment=f"审批超期，自动升级至第{next_step.get('level')}级",
                    acted_at=now,
                )
                db.add(record)

                instance.current_level = next_step.get("level", instance.current_level + 1)
                instance.status = ApprovalStatus.ESCALATED.value
                timeout_hours = next_step.get("timeout_hours", 48)
                instance.deadline = now + timedelta(hours=timeout_hours)

                # 通知下一级审批人
                next_role = next_step.get("role", "store_manager")
                approver = await self._resolve_approver(db, next_role, instance.store_id, instance.brand_id)
                if approver:
                    await self._notify_approver(db, instance, approver, instance.brand_id)

                escalated_count += 1
                logger.info(
                    "approval.escalated",
                    instance_id=str(instance.id),
                    new_level=instance.current_level,
                )
            else:
                # 已是最后一级，推送催办
                current_step = self._find_step(chain, instance.current_level)
                if current_step:
                    role = current_step.get("role", "store_manager")
                    approver = await self._resolve_approver(db, role, instance.store_id, instance.brand_id)
                    if approver:
                        await self._send_reminder(db, instance, approver, instance.brand_id)
                # 延长 deadline 24h 避免反复催
                instance.deadline = now + timedelta(hours=24)
                notified_count += 1

        await db.flush()

        return {
            "total_timed_out": len(timed_out),
            "escalated": escalated_count,
            "reminded": notified_count,
        }

    # ──────────────────────────────────────────────────────────
    #  查询：待审批列表
    # ──────────────────────────────────────────────────────────

    async def get_pending_approvals(
        self,
        db: AsyncSession,
        approver_id: str,
        brand_id: Optional[str] = None,
    ) -> List[ApprovalInstance]:
        """获取待我审批列表（含委托代理）"""
        # 查询是否有人委托给我
        today = date.today()
        delegation_result = await db.execute(
            select(ApprovalDelegation.delegator_id).where(
                and_(
                    ApprovalDelegation.delegate_id == approver_id,
                    ApprovalDelegation.is_active.is_(True),
                    ApprovalDelegation.start_date <= today,
                    ApprovalDelegation.end_date >= today,
                )
            )
        )
        delegator_ids = [row[0] for row in delegation_result.all()]

        # 获取我负责角色对应的待审批
        # 先找出该审批人在组织中的角色
        emp_result = await db.execute(select(Employee.position, Employee.store_id).where(Employee.id == approver_id))
        emp_row = emp_result.first()
        approver_role = emp_row[0] if emp_row else None

        # 查找状态为 pending/escalated 的实例
        conditions = [
            ApprovalInstance.status.in_(
                [
                    ApprovalStatus.PENDING.value,
                    ApprovalStatus.ESCALATED.value,
                ]
            ),
        ]
        if brand_id:
            conditions.append(ApprovalInstance.brand_id == brand_id)

        result = await db.execute(select(ApprovalInstance).where(and_(*conditions)))
        all_pending = result.scalars().all()

        # 过滤：当前级别的角色匹配审批人角色
        matched: List[ApprovalInstance] = []
        role_map = self._position_to_role_map()

        for inst in all_pending:
            template = await self._get_template(db, inst.template_code)
            if not template:
                continue
            chain = list(template.approval_chain or [])
            current_step = self._find_step(chain, inst.current_level)
            if not current_step:
                continue

            step_role = current_step.get("role", "")
            # 直接匹配角色
            normalized_role = role_map.get(approver_role, approver_role)
            if normalized_role == step_role:
                matched.append(inst)
                continue
            # 检查委托人的角色是否匹配
            for did in delegator_ids:
                d_result = await db.execute(select(Employee.position).where(Employee.id == did))
                d_row = d_result.first()
                if d_row:
                    d_role = role_map.get(d_row[0], d_row[0])
                    if d_role == step_role:
                        matched.append(inst)
                        break

        return matched

    # ──────────────────────────────────────────────────────────
    #  查询：审批轨迹
    # ──────────────────────────────────────────────────────────

    async def get_approval_history(self, db: AsyncSession, instance_id: UUID) -> Dict[str, Any]:
        """获取审批轨迹"""
        instance = await self._get_instance(db, instance_id)
        if not instance:
            raise ValueError(f"审批实例 {instance_id} 不存在")

        result = await db.execute(
            select(ApprovalRecord).where(ApprovalRecord.instance_id == instance_id).order_by(ApprovalRecord.acted_at.asc())
        )
        records = result.scalars().all()

        return {
            "instance": {
                "id": str(instance.id),
                "template_code": instance.template_code,
                "business_type": instance.business_type,
                "business_id": instance.business_id,
                "applicant_id": instance.applicant_id,
                "applicant_name": instance.applicant_name,
                "status": instance.status,
                "current_level": instance.current_level,
                "amount_fen": instance.amount_fen,
                "summary": instance.summary,
                "final_result": instance.final_result,
                "completed_at": instance.completed_at.isoformat() if instance.completed_at else None,
                "deadline": instance.deadline.isoformat() if instance.deadline else None,
                "created_at": instance.created_at.isoformat() if instance.created_at else None,
            },
            "records": [
                {
                    "id": str(r.id),
                    "level": r.level,
                    "approver_id": r.approver_id,
                    "approver_name": r.approver_name,
                    "approver_role": r.approver_role,
                    "action": r.action,
                    "comment": r.comment,
                    "acted_at": r.acted_at.isoformat() if r.acted_at else None,
                    "delegated_to_id": r.delegated_to_id,
                    "delegated_to_name": r.delegated_to_name,
                }
                for r in records
            ],
        }

    # ──────────────────────────────────────────────────────────
    #  内部方法
    # ──────────────────────────────────────────────────────────

    async def _get_template(self, db: AsyncSession, template_code: str) -> Optional[ApprovalTemplate]:
        """获取审批模板"""
        result = await db.execute(
            select(ApprovalTemplate).where(
                and_(
                    ApprovalTemplate.template_code == template_code,
                    ApprovalTemplate.is_active.is_(True),
                )
            )
        )
        return result.scalars().first()

    async def _get_instance(self, db: AsyncSession, instance_id: UUID) -> Optional[ApprovalInstance]:
        """获取审批实例"""
        result = await db.execute(select(ApprovalInstance).where(ApprovalInstance.id == instance_id))
        return result.scalars().first()

    def _find_step(self, chain: List[Dict], level: int) -> Optional[Dict]:
        """在审批链中找到指定 level 的步骤"""
        for step in chain:
            if step.get("level") == level:
                return step
        return None

    def _find_next_step(self, chain: List[Dict], current_level: int) -> Optional[Dict]:
        """找到下一级审批步骤"""
        chain_sorted = sorted(chain, key=lambda s: s.get("level", 0))
        for step in chain_sorted:
            if step.get("level", 0) > current_level:
                return step
        return None

    async def _resolve_approver(
        self,
        db: AsyncSession,
        role: str,
        store_id: str,
        brand_id: str,
    ) -> Optional[Dict[str, str]]:
        """根据角色解析具体审批人"""
        role_map = self._role_to_position_map()
        positions = role_map.get(role, [role])

        # 先在门店内查找
        for pos in positions:
            result = await db.execute(
                select(Employee.id, Employee.name)
                .where(
                    and_(
                        Employee.store_id == store_id,
                        Employee.position == pos,
                        Employee.is_active.is_(True),
                    )
                )
                .limit(1)
            )
            row = result.first()
            if row:
                return {"id": row[0], "name": row[1]}

        # 跨门店查找（如 area_manager / hr_director / ceo 可能不在同一门店）
        for pos in positions:
            result = await db.execute(
                select(Employee.id, Employee.name)
                .where(
                    and_(
                        Employee.position == pos,
                        Employee.is_active.is_(True),
                    )
                )
                .limit(1)
            )
            row = result.first()
            if row:
                return {"id": row[0], "name": row[1]}

        logger.warning(
            "approval.approver_not_found",
            role=role,
            store_id=store_id,
            brand_id=brand_id,
        )
        return None

    async def _check_delegation(
        self,
        db: AsyncSession,
        approver_id: str,
        template_code: str,
        brand_id: str,
    ) -> Optional[ApprovalDelegation]:
        """检查审批人是否设置了委托代理"""
        today = date.today()
        result = await db.execute(
            select(ApprovalDelegation).where(
                and_(
                    ApprovalDelegation.delegator_id == approver_id,
                    ApprovalDelegation.is_active.is_(True),
                    ApprovalDelegation.start_date <= today,
                    ApprovalDelegation.end_date >= today,
                    ApprovalDelegation.brand_id == brand_id,
                )
            )
        )
        delegations = result.scalars().all()
        for d in delegations:
            codes = d.template_codes or []
            if not codes or template_code in codes:
                return d
        return None

    async def _notify_approver(
        self,
        db: AsyncSession,
        instance: ApprovalInstance,
        approver: Dict[str, str],
        brand_id: str,
    ) -> None:
        """通过 IM 通知审批人"""
        try:
            from src.services.im_message_service import IMMessageService

            im = IMMessageService(db)

            approver_id = approver.get("id", "")
            title = f"待审批: {instance.summary or instance.business_type}"
            description = (
                f"申请人: {instance.applicant_name}\n" f"类型: {instance.business_type}\n" f"摘要: {instance.summary or '无'}"
            )
            if instance.amount_fen:
                description += f"\n金额: {instance.amount_fen / 100:.2f} 元"

            action_url = f"/hr/approval/{instance.id}"

            await im.send_decision_card(
                brand_id=brand_id,
                to_user_id=approver_id,
                title=title,
                description=description,
                action_url=action_url,
                btntxt="立即审批",
            )
            logger.info(
                "approval.notified",
                approver_id=approver_id,
                instance_id=str(instance.id),
            )
        except Exception as e:
            logger.warning(
                "approval.notify_failed",
                approver_id=approver.get("id"),
                error=str(e),
            )

    async def _notify_applicant_result(
        self,
        db: AsyncSession,
        instance: ApprovalInstance,
        result_text: str,
        brand_id: str,
    ) -> None:
        """通知申请人审批结果"""
        try:
            from src.services.im_message_service import IMMessageService

            im = IMMessageService(db)

            status_label = "已通过" if result_text == "approved" else "已驳回"
            content = (
                f"您的{instance.business_type}申请{status_label}\n"
                f"审批编号: {str(instance.id)[:8]}\n"
                f"摘要: {instance.summary or '无'}"
            )

            await im.send_text(
                brand_id=brand_id,
                to_user_id=instance.applicant_id,
                content=content,
            )
        except Exception as e:
            logger.warning(
                "approval.notify_applicant_failed",
                applicant_id=instance.applicant_id,
                error=str(e),
            )

    async def _send_reminder(
        self,
        db: AsyncSession,
        instance: ApprovalInstance,
        approver: Dict[str, str],
        brand_id: str,
    ) -> None:
        """发送催办通知"""
        try:
            from src.services.im_message_service import IMMessageService

            im = IMMessageService(db)

            content = (
                f"[催办] 您有一条待审批事项已超期\n"
                f"类型: {instance.business_type}\n"
                f"申请人: {instance.applicant_name}\n"
                f"摘要: {instance.summary or '无'}\n"
                f"请尽快处理！"
            )

            await im.send_text(
                brand_id=brand_id,
                to_user_id=approver.get("id", ""),
                content=content,
            )
        except Exception as e:
            logger.warning(
                "approval.reminder_failed",
                approver_id=approver.get("id"),
                error=str(e),
            )

    @staticmethod
    def _role_to_position_map() -> Dict[str, List[str]]:
        """审批角色 → Employee.position 映射（一个角色可能对应多种职位名称）"""
        return {
            "store_manager": ["manager", "store_manager", "店长"],
            "area_manager": ["area_manager", "区域经理", "督导"],
            "hr_director": ["hr_director", "hr_manager", "人事总监", "人事经理"],
            "ceo": ["ceo", "boss", "总经理", "老板"],
            "finance_director": ["finance_director", "财务总监"],
            "chef_head": ["chef_head", "厨师长", "行政总厨"],
        }

    @staticmethod
    def _position_to_role_map() -> Dict[str, str]:
        """Employee.position → 审批角色（反向映射）"""
        mapping: Dict[str, str] = {}
        for role, positions in ApprovalEngine._role_to_position_map().items():
            for pos in positions:
                mapping[pos] = role
        return mapping


# 单例
approval_engine = ApprovalEngine()
