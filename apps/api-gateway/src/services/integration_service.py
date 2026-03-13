"""
Integration Service
外部系统集成服务
"""
from typing import List, Optional, Dict, Any, Callable, Tuple
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import os
import structlog
import httpx
import json

from ..models.integration import (
    ExternalSystem,
    SyncLog,
    POSTransaction,
    SupplierOrder,
    MemberSync,
    ReservationSync,
    IntegrationType,
    IntegrationStatus,
    SyncStatus,
)
from ..models.reservation import ReservationStatus

logger = structlog.get_logger()


class IntegrationService:
    """集成服务"""

    async def create_system(
        self,
        session: AsyncSession,
        name: str,
        type: IntegrationType,
        provider: str,
        config: Dict[str, Any],
        created_by: str,
        store_id: Optional[str] = None,
    ) -> ExternalSystem:
        """创建外部系统配置"""
        system = ExternalSystem(
            name=name,
            type=type,
            provider=provider,
            store_id=store_id,
            api_endpoint=config.get("api_endpoint"),
            api_key=config.get("api_key"),
            api_secret=config.get("api_secret"),
            webhook_url=config.get("webhook_url"),
            config=config,
            created_by=created_by,
        )

        session.add(system)
        await session.commit()
        await session.refresh(system)

        logger.info(
            "外部系统创建成功",
            system_id=str(system.id),
            name=name,
            type=type.value,
        )

        return system

    async def get_system(
        self, session: AsyncSession, system_id: str
    ) -> Optional[ExternalSystem]:
        """获取外部系统配置"""
        result = await session.execute(
            select(ExternalSystem).where(ExternalSystem.id == system_id)
        )
        return result.scalar_one_or_none()

    async def get_systems(
        self,
        session: AsyncSession,
        type: Optional[IntegrationType] = None,
        store_id: Optional[str] = None,
        status: Optional[IntegrationStatus] = None,
    ) -> List[ExternalSystem]:
        """获取外部系统列表"""
        query = select(ExternalSystem)

        conditions = []
        if type:
            conditions.append(ExternalSystem.type == type)
        if store_id:
            conditions.append(ExternalSystem.store_id == store_id)
        if status:
            conditions.append(ExternalSystem.status == status)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(desc(ExternalSystem.created_at))

        result = await session.execute(query)
        return list(result.scalars().all())

    async def update_system(
        self,
        session: AsyncSession,
        system_id: str,
        **kwargs,
    ) -> Optional[ExternalSystem]:
        """更新外部系统配置"""
        system = await self.get_system(session, system_id)
        if not system:
            return None

        for key, value in kwargs.items():
            if hasattr(system, key) and value is not None:
                setattr(system, key, value)

        # 若更新了 config，同步从 config 中提取独立字段
        new_config = kwargs.get("config")
        if new_config:
            for col in ("api_endpoint", "api_key", "api_secret", "webhook_url"):
                val = new_config.get(col)
                if val is not None:
                    setattr(system, col, val)

        system.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(system)

        logger.info("外部系统更新成功", system_id=system_id)
        return system

    async def delete_system(
        self, session: AsyncSession, system_id: str
    ) -> bool:
        """删除外部系统配置"""
        system = await self.get_system(session, system_id)
        if not system:
            return False

        await session.delete(system)
        await session.commit()

        logger.info("外部系统删除成功", system_id=system_id)
        return True

    async def test_connection(
        self, session: AsyncSession, system_id: str
    ) -> Dict[str, Any]:
        """测试外部系统连接"""
        system = await self.get_system(session, system_id)
        if not system:
            return {"success": False, "error": "系统不存在"}

        try:
            # 根据系统类型测试连接
            if system.type == IntegrationType.POS:
                result = await self._test_pos_connection(system)
            elif system.type == IntegrationType.SUPPLIER:
                result = await self._test_supplier_connection(system)
            elif system.type == IntegrationType.MEMBER:
                result = await self._test_member_connection(system)
            else:
                result = {"success": False, "error": "不支持的系统类型"}

            # 更新系统状态
            if result.get("success"):
                system.status = IntegrationStatus.ACTIVE
            else:
                system.status = IntegrationStatus.ERROR
                system.last_error = result.get("error")

            await session.commit()

            return result

        except Exception as e:
            logger.error("测试连接失败", system_id=system_id, error=str(e))
            system.status = IntegrationStatus.ERROR
            system.last_error = str(e)
            await session.commit()

            return {"success": False, "error": str(e)}

    async def _test_pos_connection(self, system: ExternalSystem) -> Dict[str, Any]:
        """测试POS系统连接"""
        if not system.api_endpoint:
            return {"success": False, "error": "未配置API端点"}

        try:
            # 品智POS使用token签名鉴权，单独处理
            if system.provider == "pinzhi":
                return await self._test_pinzhi_connection(system)

            async with httpx.AsyncClient(timeout=float(os.getenv("INTEGRATION_HTTP_TIMEOUT", "10.0"))) as client:
                response = await client.get(
                    f"{system.api_endpoint}/health",
                    headers={"Authorization": f"Bearer {system.api_key}"},
                )
                if response.status_code == 200:
                    return {"success": True, "message": "连接成功"}
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}",
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _test_pinzhi_connection(self, system: ExternalSystem) -> Dict[str, Any]:
        """测试品智POS连接（Bearer Token鉴权，REST API /api/v1）"""
        cfg = system.config or {}
        token = cfg.get("token") or system.api_key
        if not token:
            return {"success": False, "error": "未配置品智Token"}
        try:
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{system.api_endpoint}/stores",
                    headers=headers,
                )
                try:
                    body = resp.json()
                except Exception:
                    if resp.status_code < 400:
                        return {"success": True, "message": f"品智服务器可达（HTTP {resp.status_code}）"}
                    return {"success": False, "error": f"品智接口返回 HTTP {resp.status_code}"}
                # 品智 REST API: code=200 表示成功
                code = body.get("code", body.get("success", -1))
                if code in (200, 0, "200", "0"):
                    data = body.get("data", {})
                    total = data.get("total", "?") if isinstance(data, dict) else len(data)
                    return {"success": True, "message": f"品智POS连接成功，共{total}家门店"}
                else:
                    msg = body.get("message", body.get("msg", ""))
                    return {"success": True, "message": f"品智接口可达（{msg or code}）"}
        except httpx.ConnectError:
            return {"success": False, "error": "无法连接到品智服务器，请检查网络"}
        except httpx.TimeoutException:
            return {"success": False, "error": "品智API连接超时"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _test_supplier_connection(
        self, system: ExternalSystem
    ) -> Dict[str, Any]:
        """测试供应商系统连接"""
        if not system.api_endpoint:
            return {"success": False, "error": "未配置API端点"}

        try:
            headers = {}
            if system.api_key:
                headers["Authorization"] = f"Bearer {system.api_key}"
            if system.api_secret:
                headers["X-API-Secret"] = system.api_secret

            async with httpx.AsyncClient(timeout=float(os.getenv("INTEGRATION_HTTP_TIMEOUT", "10.0"))) as client:
                for path in ["/health", "/api/health", "/ping"]:
                    try:
                        response = await client.get(
                            f"{system.api_endpoint}{path}",
                            headers=headers,
                        )
                        if response.status_code < 500:
                            return {"success": True, "message": f"供应商系统连接成功 (HTTP {response.status_code})"}
                    except (httpx.ConnectError, httpx.TimeoutException):
                        continue
            return {"success": False, "error": "无法连接到供应商系统"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _test_member_connection(
        self, system: ExternalSystem
    ) -> Dict[str, Any]:
        """测试会员系统连接"""
        if not system.api_endpoint:
            return {"success": False, "error": "未配置API端点"}

        try:
            headers = {}
            if system.api_key:
                headers["Authorization"] = f"Bearer {system.api_key}"

            async with httpx.AsyncClient(timeout=float(os.getenv("INTEGRATION_HTTP_TIMEOUT", "10.0"))) as client:
                for path in ["/health", "/api/v1/health", "/ping"]:
                    try:
                        response = await client.get(
                            f"{system.api_endpoint}{path}",
                            headers=headers,
                        )
                        if response.status_code < 500:
                            return {"success": True, "message": f"会员系统连接成功 (HTTP {response.status_code})"}
                    except (httpx.ConnectError, httpx.TimeoutException):
                        continue
            return {"success": False, "error": "无法连接到会员系统"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # POS Transaction Methods
    async def create_pos_transaction(
        self,
        session: AsyncSession,
        system_id: str,
        store_id: str,
        transaction_data: Dict[str, Any],
    ) -> POSTransaction:
        """创建POS交易记录"""
        transaction = POSTransaction(
            system_id=system_id,
            store_id=store_id,
            pos_transaction_id=transaction_data["transaction_id"],
            pos_order_number=transaction_data.get("order_number"),
            transaction_type=transaction_data.get("type", "sale"),
            subtotal=transaction_data.get("subtotal", 0),
            tax=transaction_data.get("tax", 0),
            discount=transaction_data.get("discount", 0),
            total=transaction_data.get("total", 0),
            payment_method=transaction_data.get("payment_method"),
            items=transaction_data.get("items"),
            customer_info=transaction_data.get("customer"),
            transaction_time=datetime.fromisoformat(
                transaction_data.get("transaction_time", datetime.utcnow().isoformat())
            ),
            raw_data=transaction_data,
        )

        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)

        logger.info(
            "POS交易记录创建",
            transaction_id=transaction_data["transaction_id"],
            store_id=store_id,
        )

        return transaction

    async def get_pos_transactions(
        self,
        session: AsyncSession,
        store_id: Optional[str] = None,
        sync_status: Optional[SyncStatus] = None,
        limit: int = 100,
    ) -> List[POSTransaction]:
        """获取POS交易记录"""
        query = select(POSTransaction)

        conditions = []
        if store_id:
            conditions.append(POSTransaction.store_id == store_id)
        if sync_status:
            conditions.append(POSTransaction.sync_status == sync_status)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(desc(POSTransaction.transaction_time)).limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    # Supplier Order Methods
    async def create_supplier_order(
        self,
        session: AsyncSession,
        system_id: str,
        store_id: str,
        order_data: Dict[str, Any],
    ) -> SupplierOrder:
        """创建供应商订单"""
        order = SupplierOrder(
            system_id=system_id,
            store_id=store_id,
            order_number=order_data["order_number"],
            supplier_id=order_data.get("supplier_id"),
            supplier_name=order_data.get("supplier_name"),
            order_type=order_data.get("type", "purchase"),
            status=order_data.get("status", "pending"),
            subtotal=order_data.get("subtotal", 0),
            tax=order_data.get("tax", 0),
            shipping=order_data.get("shipping", 0),
            total=order_data.get("total", 0),
            items=order_data.get("items"),
            delivery_info=order_data.get("delivery"),
            order_date=datetime.fromisoformat(
                order_data.get("order_date", datetime.utcnow().isoformat())
            ),
            expected_delivery=datetime.fromisoformat(order_data["expected_delivery"])
            if order_data.get("expected_delivery")
            else None,
            raw_data=order_data,
        )

        session.add(order)
        await session.commit()
        await session.refresh(order)

        logger.info(
            "供应商订单创建",
            order_number=order_data["order_number"],
            store_id=store_id,
        )

        return order

    async def get_supplier_orders(
        self,
        session: AsyncSession,
        store_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[SupplierOrder]:
        """获取供应商订单"""
        query = select(SupplierOrder)

        conditions = []
        if store_id:
            conditions.append(SupplierOrder.store_id == store_id)
        if status:
            conditions.append(SupplierOrder.status == status)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(desc(SupplierOrder.order_date)).limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    # Member Sync Methods
    async def sync_member(
        self,
        session: AsyncSession,
        system_id: str,
        member_data: Dict[str, Any],
    ) -> MemberSync:
        """同步会员数据"""
        # 检查是否已存在
        result = await session.execute(
            select(MemberSync).where(
                and_(
                    MemberSync.system_id == system_id,
                    MemberSync.member_id == member_data["member_id"],
                )
            )
        )
        member = result.scalar_one_or_none()

        if member:
            # 更新现有记录
            member.external_member_id = member_data.get("external_id")
            member.phone = member_data.get("phone")
            member.name = member_data.get("name")
            member.email = member_data.get("email")
            member.level = member_data.get("level")
            member.points = member_data.get("points", 0)
            member.balance = member_data.get("balance", 0)
            member.sync_status = SyncStatus.SUCCESS
            member.synced_at = datetime.utcnow()
            member.raw_data = member_data
        else:
            # 创建新记录
            member = MemberSync(
                system_id=system_id,
                member_id=member_data["member_id"],
                external_member_id=member_data.get("external_id"),
                phone=member_data.get("phone"),
                name=member_data.get("name"),
                email=member_data.get("email"),
                level=member_data.get("level"),
                points=member_data.get("points", 0),
                balance=member_data.get("balance", 0),
                sync_status=SyncStatus.SUCCESS,
                synced_at=datetime.utcnow(),
                raw_data=member_data,
            )
            session.add(member)

        await session.commit()
        await session.refresh(member)

        logger.info("会员数据同步", member_id=member_data["member_id"])
        return member

    # Reservation Sync Methods
    async def sync_reservation(
        self,
        session: AsyncSession,
        system_id: str,
        store_id: str,
        reservation_data: Dict[str, Any],
    ) -> "ReservationSync":
        """同步预订数据"""
        from ..models.integration import ReservationSync

        # 检查是否已存在
        result = await session.execute(
            select(ReservationSync).where(
                and_(
                    ReservationSync.system_id == system_id,
                    ReservationSync.reservation_id == reservation_data["reservation_id"],
                )
            )
        )
        reservation = result.scalar_one_or_none()

        if reservation:
            # 更新现有记录
            reservation.external_reservation_id = reservation_data.get("external_id")
            reservation.reservation_number = reservation_data.get("reservation_number")
            reservation.customer_name = reservation_data["customer_name"]
            reservation.customer_phone = reservation_data["customer_phone"]
            reservation.customer_count = reservation_data["customer_count"]
            reservation.reservation_date = datetime.fromisoformat(reservation_data["reservation_date"])
            reservation.reservation_time = reservation_data["reservation_time"]
            reservation.table_type = reservation_data.get("table_type")
            reservation.table_number = reservation_data.get("table_number")
            reservation.area = reservation_data.get("area")
            reservation.status = reservation_data.get("status", "pending")
            reservation.special_requirements = reservation_data.get("special_requirements")
            reservation.notes = reservation_data.get("notes")
            reservation.deposit_required = reservation_data.get("deposit_required", False)
            reservation.deposit_amount = reservation_data.get("deposit_amount", 0)
            reservation.deposit_paid = reservation_data.get("deposit_paid", False)
            reservation.source = reservation_data.get("source", "yiding")
            reservation.channel = reservation_data.get("channel")
            reservation.sync_status = SyncStatus.SUCCESS
            reservation.synced_at = datetime.utcnow()
            reservation.raw_data = reservation_data

            if reservation_data.get("arrival_time"):
                reservation.arrival_time = datetime.fromisoformat(reservation_data["arrival_time"])
        else:
            # 创建新记录
            reservation = ReservationSync(
                system_id=system_id,
                store_id=store_id,
                reservation_id=reservation_data["reservation_id"],
                external_reservation_id=reservation_data.get("external_id"),
                reservation_number=reservation_data.get("reservation_number"),
                customer_name=reservation_data["customer_name"],
                customer_phone=reservation_data["customer_phone"],
                customer_count=reservation_data["customer_count"],
                reservation_date=datetime.fromisoformat(reservation_data["reservation_date"]),
                reservation_time=reservation_data["reservation_time"],
                arrival_time=datetime.fromisoformat(reservation_data["arrival_time"])
                    if reservation_data.get("arrival_time") else None,
                table_type=reservation_data.get("table_type"),
                table_number=reservation_data.get("table_number"),
                area=reservation_data.get("area"),
                status=reservation_data.get("status", "pending"),
                special_requirements=reservation_data.get("special_requirements"),
                notes=reservation_data.get("notes"),
                deposit_required=reservation_data.get("deposit_required", False),
                deposit_amount=reservation_data.get("deposit_amount", 0),
                deposit_paid=reservation_data.get("deposit_paid", False),
                source=reservation_data.get("source", "yiding"),
                channel=reservation_data.get("channel"),
                sync_status=SyncStatus.SUCCESS,
                synced_at=datetime.utcnow(),
                raw_data=reservation_data,
            )
            session.add(reservation)

        await session.commit()
        await session.refresh(reservation)

        logger.info("预订数据同步", reservation_id=reservation_data["reservation_id"], store_id=store_id)
        return reservation

    async def get_reservations(
        self,
        session: AsyncSession,
        store_id: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 100,
    ) -> List["ReservationSync"]:
        """获取预订列表"""
        from ..models.integration import ReservationSync

        query = select(ReservationSync)

        conditions = []
        if store_id:
            conditions.append(ReservationSync.store_id == store_id)
        if status:
            conditions.append(ReservationSync.status == status)
        if date_from:
            conditions.append(ReservationSync.reservation_date >= date_from)
        if date_to:
            conditions.append(ReservationSync.reservation_date <= date_to)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(desc(ReservationSync.reservation_date)).limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def update_reservation_status(
        self,
        session: AsyncSession,
        reservation_id: str,
        status: str,
        **kwargs,
    ) -> Optional["ReservationSync"]:
        """更新预订状态"""
        from ..models.integration import ReservationSync

        result = await session.execute(
            select(ReservationSync).where(ReservationSync.reservation_id == reservation_id)
        )
        reservation = result.scalar_one_or_none()

        if not reservation:
            return None

        reservation.status = status

        if status == ReservationStatus.ARRIVED.value and kwargs.get("arrival_time"):
            reservation.arrival_time = datetime.fromisoformat(kwargs["arrival_time"])

        if status == ReservationStatus.SEATED.value and kwargs.get("table_number"):
            reservation.table_number = kwargs["table_number"]

        if status == ReservationStatus.CANCELLED.value:
            reservation.cancelled_at = datetime.utcnow()

        reservation.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(reservation)

        logger.info("预订状态更新", reservation_id=reservation_id, status=status)
        return reservation

    # Sync Log Methods
    async def create_sync_log(
        self,
        session: AsyncSession,
        system_id: str,
        sync_type: str,
        status: SyncStatus,
        **kwargs,
    ) -> SyncLog:
        """创建同步日志"""
        log = SyncLog(
            system_id=system_id,
            sync_type=sync_type,
            status=status,
            started_at=kwargs.get("started_at", datetime.utcnow()),
            completed_at=kwargs.get("completed_at"),
            duration_seconds=kwargs.get("duration_seconds"),
            records_total=kwargs.get("records_total", 0),
            records_success=kwargs.get("records_success", 0),
            records_failed=kwargs.get("records_failed", 0),
            error_message=kwargs.get("error_message"),
            error_details=kwargs.get("error_details"),
            request_data=kwargs.get("request_data"),
            response_data=kwargs.get("response_data"),
        )

        session.add(log)
        await session.commit()
        await session.refresh(log)

        return log

    async def get_sync_logs(
        self,
        session: AsyncSession,
        system_id: Optional[str] = None,
        sync_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[SyncLog]:
        """获取同步日志"""
        query = select(SyncLog)

        conditions = []
        if system_id:
            conditions.append(SyncLog.system_id == system_id)
        if sync_type:
            conditions.append(SyncLog.sync_type == sync_type)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(desc(SyncLog.created_at)).limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())


    # ──────────────────────────────────────────────────────────────────────────
    # P1 增强功能 #1：自动重试机制
    # ──────────────────────────────────────────────────────────────────────────

    async def with_retry(
        self,
        func: Callable,
        *args,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        backoff: float = 2.0,
        retryable_exceptions: Tuple = (httpx.TimeoutException, httpx.ConnectError, ConnectionError),
        **kwargs,
    ) -> Any:
        """
        通用异步重试包装器（指数退避）

        Args:
            func: 被重试的异步函数
            max_attempts: 最大尝试次数（默认3）
            base_delay: 初始等待秒数（默认1s）
            backoff: 退避系数（默认2x）
            retryable_exceptions: 可重试的异常类型元组

        Returns:
            func 的返回值

        Raises:
            最后一次尝试的异常
        """
        last_exc: Exception = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await func(*args, **kwargs)
            except retryable_exceptions as e:
                last_exc = e
                if attempt == max_attempts:
                    break
                delay = base_delay * (backoff ** (attempt - 1))
                logger.warning(
                    "integration_retry",
                    func=getattr(func, "__name__", str(func)),
                    attempt=attempt,
                    max_attempts=max_attempts,
                    delay=delay,
                    error=str(e),
                )
                await asyncio.sleep(delay)
        raise last_exc

    async def test_connection_with_retry(
        self, session: AsyncSession, system_id: str, max_attempts: int = 3
    ) -> Dict[str, Any]:
        """带自动重试的连接测试"""
        return await self.with_retry(
            self.test_connection,
            session,
            system_id,
            max_attempts=max_attempts,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # P1 增强功能 #2：数据转换规则配置
    # ──────────────────────────────────────────────────────────────────────────

    _TRANSFORM_REGISTRY: Dict[str, Dict[str, Callable]] = {}

    def register_transform_rule(
        self,
        system_type: str,
        data_type: str,
        transform_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """
        注册数据转换规则

        Args:
            system_type: 系统类型（如 "meituan_pos", "tianchu"）
            data_type: 数据类型（如 "order", "inventory"）
            transform_fn: 接收原始 dict，返回标准化 dict 的纯函数
        """
        key = f"{system_type}:{data_type}"
        self._TRANSFORM_REGISTRY[key] = transform_fn
        logger.info("transform_rule_registered", key=key)

    def apply_transform(
        self,
        system_type: str,
        data_type: str,
        raw_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        应用数据转换规则

        Returns:
            转换后的标准字典；若无规则则原样返回
        """
        key = f"{system_type}:{data_type}"
        transform_fn = self._TRANSFORM_REGISTRY.get(key)
        if transform_fn is None:
            return raw_data
        try:
            return transform_fn(raw_data)
        except Exception as e:
            logger.error("transform_failed", key=key, error=str(e))
            return raw_data

    def get_registered_rules(self) -> List[str]:
        """返回所有已注册的转换规则 key 列表"""
        return list(self._TRANSFORM_REGISTRY.keys())

    # ──────────────────────────────────────────────────────────────────────────
    # P1 增强功能 #3：批量同步优化
    # ──────────────────────────────────────────────────────────────────────────

    async def batch_sync_members(
        self,
        session: AsyncSession,
        system_id: str,
        members: List[Dict[str, Any]],
        chunk_size: int = 50,
        system_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        批量同步会员数据（分块并发处理）

        Args:
            session: DB session
            system_id: 外部系统 ID
            members: 会员数据列表
            chunk_size: 每批大小（默认50）
            system_type: 用于查找转换规则的系统类型

        Returns:
            {"total": int, "success": int, "failed": int, "errors": list}
        """
        total = len(members)
        success = 0
        failed = 0
        errors: List[Dict[str, Any]] = []

        for i in range(0, total, chunk_size):
            chunk = members[i: i + chunk_size]
            tasks = []
            for member_data in chunk:
                if system_type:
                    member_data = self.apply_transform(system_type, "member", member_data)
                tasks.append(self._sync_member_safe(session, system_id, member_data, errors))

            results = await asyncio.gather(*tasks)
            success += sum(1 for r in results if r)
            failed += sum(1 for r in results if not r)

            logger.info(
                "batch_sync_progress",
                system_id=system_id,
                processed=min(i + chunk_size, total),
                total=total,
            )

        return {"total": total, "success": success, "failed": failed, "errors": errors[:10]}

    async def _sync_member_safe(
        self,
        session: AsyncSession,
        system_id: str,
        member_data: Dict[str, Any],
        errors: List,
    ) -> bool:
        """单条会员同步，异常不中断批处理"""
        try:
            await self.sync_member(session, system_id, member_data)
            return True
        except Exception as e:
            errors.append({"member_id": member_data.get("member_id"), "error": str(e)})
            logger.warning("member_sync_failed", member_id=member_data.get("member_id"), error=str(e))
            return False

    async def batch_sync_pos_transactions(
        self,
        session: AsyncSession,
        system_id: str,
        store_id: str,
        transactions: List[Dict[str, Any]],
        chunk_size: int = 100,
        system_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """批量同步 POS 交易记录（分块顺序处理，保证幂等）"""
        total = len(transactions)
        success = 0
        failed = 0
        errors: List[Dict[str, Any]] = []

        for i in range(0, total, chunk_size):
            chunk = transactions[i: i + chunk_size]
            for txn in chunk:
                if system_type:
                    txn = self.apply_transform(system_type, "order", txn)
                try:
                    await self.create_pos_transaction(session, system_id, store_id, txn)
                    success += 1
                except Exception as e:
                    failed += 1
                    errors.append({"transaction_id": txn.get("transaction_id"), "error": str(e)})

        return {"total": total, "success": success, "failed": failed, "errors": errors[:10]}

    # ──────────────────────────────────────────────────────────────────────────
    # P1 增强功能 #4：实时同步状态推送
    # ──────────────────────────────────────────────────────────────────────────

    async def get_realtime_sync_status(
        self,
        session: AsyncSession,
        system_id: str,
    ) -> Dict[str, Any]:
        """
        获取外部系统的实时同步状态快照

        Returns:
            {
              "system_id": str,
              "status": "active|error|idle",
              "last_sync_at": ISO str | None,
              "last_sync_type": str | None,
              "last_24h_success": int,
              "last_24h_failed": int,
              "health_score": float,
            }
        """
        system = await self.get_system(session, system_id)
        if not system:
            return {"error": "system_not_found"}

        since = datetime.utcnow() - timedelta(hours=24)
        result = await session.execute(
            select(SyncLog).where(
                and_(
                    SyncLog.system_id == system_id,
                    SyncLog.created_at >= since,
                )
            ).order_by(desc(SyncLog.created_at)).limit(200)
        )
        logs = list(result.scalars().all())

        success_count = sum(1 for l in logs if l.status == SyncStatus.SUCCESS)
        failed_count = sum(1 for l in logs if l.status == SyncStatus.FAILED)
        last_log = logs[0] if logs else None

        health = self._compute_health_score(success_count, failed_count, system)

        return {
            "system_id": system_id,
            "system_name": system.name,
            "status": system.status.value if system.status else "unknown",
            "last_sync_at": last_log.created_at.isoformat() if last_log else None,
            "last_sync_type": last_log.sync_type if last_log else None,
            "last_24h_success": success_count,
            "last_24h_failed": failed_count,
            "health_score": health,
            "snapshot_at": datetime.utcnow().isoformat(),
        }

    # ──────────────────────────────────────────────────────────────────────────
    # P1 增强功能 #5：集成健康度评分
    # ──────────────────────────────────────────────────────────────────────────

    def _compute_health_score(
        self,
        success_count: int,
        failed_count: int,
        system: "ExternalSystem",
    ) -> float:
        """
        计算集成健康度评分（0-100）

        维度权重：
          - 24h 同步成功率（50%）
          - 系统状态（30%）
          - 最近是否有错误（20%）
        """
        total = success_count + failed_count
        success_rate = (success_count / total) if total > 0 else 1.0

        from ..models.integration import IntegrationStatus
        status_score = {
            IntegrationStatus.ACTIVE: 1.0,
            IntegrationStatus.INACTIVE: 0.5,
            IntegrationStatus.ERROR: 0.0,
        }.get(system.status, 0.5)

        error_penalty = 0.0 if (system.last_error is None) else 0.5

        score = (
            success_rate * 50
            + status_score * 30
            + (1.0 - error_penalty) * 20
        )
        return round(min(max(score, 0.0), 100.0), 1)

    async def get_all_systems_health(
        self,
        session: AsyncSession,
        store_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取所有外部系统的健康度汇总

        Returns:
            按 health_score 降序排列的系统状态列表
        """
        systems = await self.get_systems(session, store_id=store_id)
        result = []
        for sys in systems:
            status = await self.get_realtime_sync_status(session, str(sys.id))
            result.append(status)
        result.sort(key=lambda x: x.get("health_score", 0), reverse=True)
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # P1 增强功能 #6：数据冲突解决策略
    # ──────────────────────────────────────────────────────────────────────────

    def resolve_conflict(
        self,
        local: Dict[str, Any],
        remote: Dict[str, Any],
        strategy: str = "last_write_wins",
        timestamp_field: str = "updated_at",
    ) -> Dict[str, Any]:
        """
        数据冲突解决

        Args:
            local: 本地数据
            remote: 远端数据
            strategy: 解决策略
                "last_write_wins"  — 时间戳较新的一方获胜（默认）
                "remote_wins"      — 始终用远端数据覆盖
                "local_wins"       — 始终保留本地数据
                "merge_remote"     — 以本地为基础，远端字段补充（不覆盖非空本地字段）
            timestamp_field: 用于比较时间戳的字段名

        Returns:
            合并后的数据字典
        """
        if strategy == "remote_wins":
            return {**local, **remote}

        if strategy == "local_wins":
            return local

        if strategy == "merge_remote":
            merged = {**remote}
            for k, v in local.items():
                if v is not None:
                    merged[k] = v
            return merged

        # last_write_wins（默认）
        local_ts = local.get(timestamp_field)
        remote_ts = remote.get(timestamp_field)

        if local_ts is None and remote_ts is None:
            return {**local, **remote}

        if local_ts is None:
            return {**local, **remote}

        if remote_ts is None:
            return local

        try:
            if isinstance(local_ts, str):
                local_ts = datetime.fromisoformat(local_ts)
            if isinstance(remote_ts, str):
                remote_ts = datetime.fromisoformat(remote_ts)
            return {**local, **remote} if remote_ts >= local_ts else local
        except (ValueError, TypeError):
            return {**local, **remote}

    async def sync_member_with_conflict_resolution(
        self,
        session: AsyncSession,
        system_id: str,
        remote_data: Dict[str, Any],
        strategy: str = "last_write_wins",
    ) -> "MemberSync":
        """
        带冲突解决的会员同步

        在写入前先查出本地记录，应用冲突解决策略后再同步
        """
        from sqlalchemy import select as _select
        from ..models.integration import MemberSync

        result = await session.execute(
            _select(MemberSync).where(
                and_(
                    MemberSync.system_id == system_id,
                    MemberSync.member_id == remote_data.get("member_id"),
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing and existing.raw_data:
            resolved = self.resolve_conflict(
                local=existing.raw_data,
                remote=remote_data,
                strategy=strategy,
            )
        else:
            resolved = remote_data

        return await self.sync_member(session, system_id, resolved)


# 创建全局服务实例
integration_service = IntegrationService()
