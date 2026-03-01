"""
ARCH-004: 可信执行层

TrustedExecutor 负责：
1. 权限校验（角色 + 指令级别）
2. 金额熔断（超额自动升级为 APPROVE）
3. 按级别路由（NOTIFY/AUTO → 直接执行；APPROVE → 发起审批流）
4. 写入审计日志（ExecutionRecord）
5. 30分钟窗口内支持回滚
"""
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import structlog

from .execution_registry import (
    COMMAND_REGISTRY, CommandDef, ExecutionLevel, get_command_def
)

logger = structlog.get_logger()

# 超级管理员角色（豁免所有权限校验）
SUPER_ADMIN_ROLES = {"super_admin", "system_admin"}

# 回滚窗口（分钟）
ROLLBACK_WINDOW_MINUTES = 30


class ExecutionError(Exception):
    """可信执行层错误"""
    def __init__(self, message: str, error_code: str = "EXECUTION_ERROR"):
        super().__init__(message)
        self.error_code = error_code


class PermissionDeniedError(ExecutionError):
    def __init__(self, actor_role: str, command_type: str):
        super().__init__(
            f"角色 '{actor_role}' 无权执行指令 '{command_type}'",
            error_code="PERMISSION_DENIED"
        )


class ApprovalRequiredError(ExecutionError):
    def __init__(self, command_type: str, reason: str):
        super().__init__(
            f"指令 '{command_type}' 需要审批: {reason}",
            error_code="APPROVAL_REQUIRED"
        )
        self.reason = reason


class RollbackWindowExpiredError(ExecutionError):
    def __init__(self, execution_id: str):
        super().__init__(
            f"执行记录 '{execution_id}' 已超过 {ROLLBACK_WINDOW_MINUTES} 分钟回滚窗口",
            error_code="ROLLBACK_WINDOW_EXPIRED"
        )


class TrustedExecutor:
    """
    可信执行层

    所有涉及资金、权限、状态变更的操作必须通过此层执行，
    确保：权限校验 → 金额熔断 → 路由 → 审计留痕
    """

    def __init__(self, db_session=None, redis_client=None):
        """
        Args:
            db_session: SQLAlchemy 异步会话（可为 None，此时不写库）
            redis_client: Redis 客户端（可选，用于缓存审计记录）
        """
        self._db = db_session
        self._redis = redis_client

    async def execute(
        self,
        command_type: str,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        执行指令

        Args:
            command_type: 指令类型（见 COMMAND_REGISTRY）
            payload: 指令参数（包含 store_id, brand_id, amount 等）
            actor: 操作人信息（包含 user_id, role, store_id, brand_id）

        Returns:
            执行结果字典

        Raises:
            ExecutionError: 执行失败
            PermissionDeniedError: 权限不足
            ApprovalRequiredError: 需要审批
        """
        execution_id = str(uuid.uuid4())
        actor_role = actor.get("role", "")
        actor_id = str(actor.get("user_id", actor.get("id", "")))
        store_id = payload.get("store_id", actor.get("store_id", ""))
        brand_id = payload.get("brand_id", actor.get("brand_id", ""))
        amount = payload.get("amount")

        logger.info(
            "trusted_executor.execute",
            execution_id=execution_id,
            command_type=command_type,
            actor_id=actor_id,
            actor_role=actor_role,
            store_id=store_id,
            amount=amount,
        )

        # 1. 获取指令定义
        try:
            cmd_def = get_command_def(command_type)
        except ValueError as e:
            raise ExecutionError(str(e), error_code="UNKNOWN_COMMAND")

        # 2. 权限校验（super_admin 豁免）
        if actor_role not in SUPER_ADMIN_ROLES:
            if actor_role not in cmd_def.allowed_roles:
                raise PermissionDeniedError(actor_role, command_type)

        # 3. 金额熔断检测
        effective_level = cmd_def.level
        circuit_reason = None
        if (
            cmd_def.amount_circuit_breaker is not None
            and amount is not None
            and float(amount) > cmd_def.amount_circuit_breaker
        ):
            effective_level = ExecutionLevel.APPROVE
            circuit_reason = (
                f"金额 {amount} 超过熔断阈值 {cmd_def.amount_circuit_breaker} 元，"
                f"自动升级为 APPROVE"
            )
            logger.warning(
                "trusted_executor.circuit_breaker_triggered",
                execution_id=execution_id,
                amount=amount,
                threshold=cmd_def.amount_circuit_breaker,
            )

        # 4. 按级别路由
        if effective_level == ExecutionLevel.APPROVE:
            # 发起审批流程（写审计记录，状态 pending_approval）
            record = await self._write_audit(
                execution_id=execution_id,
                command_type=command_type,
                payload=payload,
                actor_id=actor_id,
                actor_role=actor_role,
                store_id=store_id,
                brand_id=brand_id,
                status="pending_approval",
                level=effective_level.value,
                amount=amount,
            )
            reason = circuit_reason or f"指令 '{command_type}' 需要审批"
            logger.info(
                "trusted_executor.approval_required",
                execution_id=execution_id,
                reason=reason,
            )
            raise ApprovalRequiredError(command_type, reason)

        elif effective_level in (ExecutionLevel.AUTO, ExecutionLevel.NOTIFY):
            # 直接执行
            result = await self._do_execute(command_type, payload, actor)
            status = "completed"

        else:
            result = {}
            status = "unknown"

        # 5. 写审计日志
        await self._write_audit(
            execution_id=execution_id,
            command_type=command_type,
            payload=payload,
            actor_id=actor_id,
            actor_role=actor_role,
            store_id=store_id,
            brand_id=brand_id,
            status=status,
            level=effective_level.value,
            amount=amount,
            result=result,
        )

        logger.info(
            "trusted_executor.completed",
            execution_id=execution_id,
            status=status,
        )

        return {
            "execution_id": execution_id,
            "command_type": command_type,
            "status": status,
            "level": effective_level.value,
            "result": result,
        }

    async def rollback(
        self,
        execution_id: str,
        operator: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        回滚已执行的指令（30分钟窗口）

        Args:
            execution_id: 执行记录ID
            operator: 操作人信息（需要审批权限）

        Returns:
            回滚结果
        """
        operator_role = operator.get("role", "")
        operator_id = str(operator.get("user_id", ""))

        # 从审计日志查询执行记录
        record = await self._get_audit_record(execution_id)
        if not record:
            raise ExecutionError(
                f"执行记录 '{execution_id}' 不存在",
                error_code="EXECUTION_NOT_FOUND"
            )

        # 检查回滚窗口
        executed_at = record.get("executed_at")
        if executed_at:
            if isinstance(executed_at, str):
                executed_at = datetime.fromisoformat(executed_at)
            if datetime.utcnow() - executed_at > timedelta(minutes=ROLLBACK_WINDOW_MINUTES):
                raise RollbackWindowExpiredError(execution_id)

        # 权限校验
        cmd_type = record.get("command_type", "")
        if cmd_type in COMMAND_REGISTRY:
            cmd_def = COMMAND_REGISTRY[cmd_type]
            if operator_role not in SUPER_ADMIN_ROLES and operator_role not in cmd_def.approver_roles:
                raise PermissionDeniedError(operator_role, f"rollback:{cmd_type}")

        # 写回滚审计记录
        rollback_id = str(uuid.uuid4())
        await self._write_audit(
            execution_id=rollback_id,
            command_type=f"rollback:{cmd_type}",
            payload={"original_execution_id": execution_id},
            actor_id=operator_id,
            actor_role=operator_role,
            store_id=record.get("store_id", ""),
            brand_id=record.get("brand_id", ""),
            status="rolled_back",
            level="rollback",
            amount=None,
        )

        # 标记原始记录为已回滚
        await self._mark_rolled_back(execution_id, operator_id, rollback_id)

        logger.info(
            "trusted_executor.rolled_back",
            execution_id=execution_id,
            rollback_id=rollback_id,
            operator_id=operator_id,
        )

        return {
            "rollback_id": rollback_id,
            "original_execution_id": execution_id,
            "status": "rolled_back",
            "operator_id": operator_id,
        }

    async def _do_execute(
        self,
        command_type: str,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
    ) -> Dict[str, Any]:
        """实际执行指令（由具体业务逻辑实现）"""
        # 此处为框架层，实际执行逻辑由各 handler 注册
        # 目前返回占位结果
        logger.info("trusted_executor._do_execute", command_type=command_type)
        return {
            "command_type": command_type,
            "executed": True,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _write_audit(
        self,
        execution_id: str,
        command_type: str,
        payload: Dict[str, Any],
        actor_id: str,
        actor_role: str,
        store_id: str,
        brand_id: str,
        status: str,
        level: str,
        amount=None,
        result: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """写入审计日志"""
        import json
        record = {
            "execution_id": execution_id,
            "command_type": command_type,
            "payload": payload,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "store_id": store_id,
            "brand_id": brand_id,
            "status": status,
            "level": level,
            "amount": str(amount) if amount is not None else None,
            "result": result or {},
            "executed_at": datetime.utcnow().isoformat(),
        }

        if self._db:
            try:
                from ..models.execution_audit import ExecutionRecord
                db_record = ExecutionRecord(
                    id=execution_id,
                    command_type=command_type,
                    payload=payload,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    store_id=store_id,
                    brand_id=brand_id,
                    status=status,
                    level=level,
                    amount=str(amount) if amount is not None else None,
                    result=result or {},
                )
                self._db.add(db_record)
                await self._db.flush()
            except Exception as e:
                logger.error("trusted_executor.audit_write_failed", error=str(e))

        return record

    async def _get_audit_record(self, execution_id: str) -> Optional[Dict]:
        """从数据库获取审计记录"""
        if self._db:
            try:
                from ..models.execution_audit import ExecutionRecord
                record = await self._db.get(ExecutionRecord, execution_id)
                if record:
                    return {
                        "execution_id": record.id,
                        "command_type": record.command_type,
                        "store_id": record.store_id,
                        "brand_id": record.brand_id,
                        "executed_at": record.created_at,
                        "status": record.status,
                        "actor_id": record.actor_id,
                    }
            except Exception as e:
                logger.error("trusted_executor.get_audit_failed", error=str(e))
        return None

    async def _mark_rolled_back(
        self,
        execution_id: str,
        operator_id: str,
        rollback_id: str,
    ) -> None:
        """标记原始记录为已回滚"""
        if self._db:
            try:
                from ..models.execution_audit import ExecutionRecord
                record = await self._db.get(ExecutionRecord, execution_id)
                if record:
                    record.status = "rolled_back"
                    record.rollback_id = rollback_id
                    record.rolled_back_by = operator_id
                    record.rolled_back_at = datetime.utcnow()
                    await self._db.flush()
            except Exception as e:
                logger.error("trusted_executor.mark_rollback_failed", error=str(e))
