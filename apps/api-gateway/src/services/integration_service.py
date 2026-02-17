"""
Integration Service
外部系统集成服务
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import httpx
import json

from ..models.integration import (
    ExternalSystem,
    SyncLog,
    POSTransaction,
    SupplierOrder,
    MemberSync,
    IntegrationType,
    IntegrationStatus,
    SyncStatus,
)

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
            async with httpx.AsyncClient(timeout=10.0) as client:
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

    async def _test_supplier_connection(
        self, system: ExternalSystem
    ) -> Dict[str, Any]:
        """测试供应商系统连接"""
        # 占位符实现
        return {"success": True, "message": "供应商系统连接测试(占位符)"}

    async def _test_member_connection(
        self, system: ExternalSystem
    ) -> Dict[str, Any]:
        """测试会员系统连接"""
        # 占位符实现
        return {"success": True, "message": "会员系统连接测试(占位符)"}

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


# 创建全局服务实例
integration_service = IntegrationService()
