"""
日报服务单元测试
"""
import pytest
import uuid
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal

from src.services.daily_report_service import DailyReportService
from src.models.daily_report import DailyReport
from src.models.user import User, UserRole
from src.models.order import Order, OrderStatus
from src.models.store import Store
from src.core.security import get_password_hash


@pytest.fixture
async def report_service(test_db):
    """创建日报服务实例"""
    return DailyReportService(test_db)


@pytest.fixture
async def test_store(test_db):
    """创建测试门店"""
    store = Store(
        id=uuid.uuid4(),
        name="测试门店",
        address="测试地址",
        phone="13800138000",
        is_active=True,
    )
    test_db.add(store)
    await test_db.commit()
    await test_db.refresh(store)
    return store


@pytest.fixture
async def test_orders(test_db, test_store):
    """创建测试订单"""
    orders = []
    today = date.today()

    for i in range(5):
        order = Order(
            id=uuid.uuid4(),
            store_id=test_store.id,
            order_number=f"ORD{i:04d}",
            total_amount=Decimal("100.00") * (i + 1),
            status=OrderStatus.COMPLETED,
            created_at=datetime.combine(today, datetime.min.time()),
        )
        orders.append(order)
        test_db.add(order)

    await test_db.commit()
    return orders


class TestDailyReportService:
    """日报服务测试类"""

    @pytest.mark.asyncio
    async def test_generate_daily_report(self, report_service, test_store, test_orders):
        """测试生成日报"""
        report_date = date.today()

        report = await report_service.generate_daily_report(
            store_id=test_store.id,
            report_date=report_date
        )

        assert report is not None
        assert report.store_id == test_store.id
        assert report.report_date == report_date
        assert report.total_orders == 5
        assert report.total_revenue == Decimal("1500.00")  # 100+200+300+400+500

    @pytest.mark.asyncio
    async def test_get_report(self, report_service, test_store):
        """测试获取日报"""
        report_date = date.today()

        # 先生成报告
        created_report = await report_service.generate_daily_report(
            store_id=test_store.id,
            report_date=report_date
        )

        # 再获取报告
        fetched_report = await report_service.get_report(
            store_id=test_store.id,
            report_date=report_date
        )

        assert fetched_report is not None
        assert fetched_report.id == created_report.id

    @pytest.mark.asyncio
    async def test_get_report_not_found(self, report_service, test_store):
        """测试获取不存在的日报"""
        report_date = date.today() - timedelta(days=30)

        report = await report_service.get_report(
            store_id=test_store.id,
            report_date=report_date
        )

        assert report is None

    @pytest.mark.asyncio
    async def test_list_reports(self, report_service, test_store):
        """测试列出日报"""
        # 生成多个日期的报告
        for i in range(3):
            report_date = date.today() - timedelta(days=i)
            await report_service.generate_daily_report(
                store_id=test_store.id,
                report_date=report_date
            )

        # 获取报告列表
        reports = await report_service.list_reports(
            store_id=test_store.id,
            limit=10
        )

        assert len(reports) == 3
        # 验证按日期降序排列
        assert reports[0].report_date > reports[1].report_date

    @pytest.mark.asyncio
    async def test_format_report_message(self, report_service, test_store, test_orders):
        """测试格式化报告消息"""
        report_date = date.today()

        report = await report_service.generate_daily_report(
            store_id=test_store.id,
            report_date=report_date
        )

        message = report_service.format_report_message(report)

        assert "测试门店" in message
        assert "5" in message  # 订单数
        assert "1500.00" in message  # 总收入

    @pytest.mark.asyncio
    async def test_report_with_no_orders(self, report_service, test_store):
        """测试无订单时生成日报"""
        # 使用未来日期，确保没有订单
        report_date = date.today() + timedelta(days=1)

        report = await report_service.generate_daily_report(
            store_id=test_store.id,
            report_date=report_date
        )

        assert report.total_orders == 0
        assert report.total_revenue == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_aggregate_data(self, report_service, test_store, test_orders):
        """测试数据聚合"""
        report_date = date.today()

        data = await report_service._aggregate_data(
            store_id=test_store.id,
            report_date=report_date
        )

        assert data["total_orders"] == 5
        assert data["total_revenue"] == Decimal("1500.00")
        assert data["avg_order_value"] == Decimal("300.00")
