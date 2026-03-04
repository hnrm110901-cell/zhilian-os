"""
Tests to cover missing lines in model to_dict() and __repr__ methods.

All models are instantiated via their normal SQLAlchemy constructor so that
_sa_instance_state is properly set up (Model.__new__ bypasses it and causes
AttributeError when column descriptors are accessed).
"""
import uuid
from datetime import datetime, date
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# competitor.py — CompetitorStore.to_dict() and CompetitorPrice.to_dict()
# ---------------------------------------------------------------------------

class TestCompetitorStore:
    def _make(self):
        from src.models.competitor import CompetitorStore
        return CompetitorStore(
            id=uuid.uuid4(),
            our_store_id="STORE001",
            name="竞品A",
            brand="某品牌",
            cuisine_type="川菜",
            address="北京市朝阳区XX路1号",
            distance_meters=500,
            avg_price_per_person=80.5,
            rating=4.2,
            monthly_customers=3000,
            is_active=True,
            notes=None,
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 6, 1),
        )

    def test_to_dict_returns_dict(self):
        obj = self._make()
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["name"] == "竞品A"
        assert result["avg_price_per_person"] == 80.5
        assert result["rating"] == 4.2

    def test_to_dict_none_optionals(self):
        from src.models.competitor import CompetitorStore
        obj = CompetitorStore(
            id=uuid.uuid4(),
            our_store_id="STORE001",
            name="竞品B",
            brand=None,
            cuisine_type=None,
            address=None,
            distance_meters=None,
            avg_price_per_person=None,
            rating=None,
            monthly_customers=None,
            is_active=False,
            notes=None,
            created_at=None,
            updated_at=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["avg_price_per_person"] is None
        assert result["rating"] is None


class TestCompetitorPrice:
    def _make(self):
        from src.models.competitor import CompetitorPrice
        return CompetitorPrice(
            id=uuid.uuid4(),
            competitor_id=uuid.uuid4(),
            dish_name="宫保鸡丁",
            category="热菜",
            price=38.0,
            record_date=date(2024, 3, 1),
            our_dish_id=uuid.uuid4(),
            created_at=datetime(2024, 3, 1),
        )

    def test_to_dict_returns_dict(self):
        obj = self._make()
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["dish_name"] == "宫保鸡丁"
        assert result["price"] == 38.0

    def test_to_dict_none_price_and_dish(self):
        from src.models.competitor import CompetitorPrice
        obj = CompetitorPrice(
            id=uuid.uuid4(),
            competitor_id=uuid.uuid4(),
            dish_name="无价格菜",
            category=None,
            price=None,
            record_date=None,
            our_dish_id=None,
            created_at=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["price"] is None
        assert result["our_dish_id"] is None


# ---------------------------------------------------------------------------
# notification.py — Notification.to_dict() / __repr__, NotificationPreference,
#                   NotificationRule
# ---------------------------------------------------------------------------

class TestNotification:
    def _make(self):
        from src.models.notification import Notification
        return Notification(
            id=uuid.uuid4(),
            title="测试通知",
            message="这是一条测试通知",
            type="info",
            priority="normal",
            user_id=uuid.uuid4(),
            role=None,
            store_id="STORE001",
            is_read=False,
            read_at=None,
            extra_data=None,
            source="test_agent",
            created_at=datetime(2024, 1, 15),
        )

    def test_to_dict_returns_dict(self):
        obj = self._make()
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["title"] == "测试通知"
        assert result["type"] == "info"

    def test_repr_returns_string(self):
        obj = self._make()
        r = repr(obj)
        assert isinstance(r, str)
        assert "Notification" in r

    def test_to_dict_no_user_id(self):
        from src.models.notification import Notification
        obj = Notification(
            id=uuid.uuid4(),
            title="广播通知",
            message="全体通知",
            type="warning",
            priority="high",
            user_id=None,
            role="manager",
            store_id=None,
            is_read=True,
            read_at="2024-01-16T10:00:00",
            extra_data={"link": "/dashboard"},
            source="scheduler",
            created_at=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["user_id"] is None
        assert result["created_at"] is None


class TestNotificationPreference:
    def test_to_dict_returns_dict(self):
        from src.models.notification import NotificationPreference
        obj = NotificationPreference(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            notification_type="warning",
            channels=["system", "email"],
            is_enabled=True,
            quiet_hours_start="22:00",
            quiet_hours_end="08:00",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 6, 1),
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["channels"] == ["system", "email"]


class TestNotificationRule:
    def test_to_dict_returns_dict(self):
        from src.models.notification import NotificationRule
        obj = NotificationRule(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            notification_type=None,
            max_count=10,
            time_window_minutes=60,
            is_active=True,
            description="全局限流规则",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 6, 1),
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["max_count"] == 10

    def test_to_dict_no_user(self):
        from src.models.notification import NotificationRule
        obj = NotificationRule(
            id=uuid.uuid4(),
            user_id=None,
            notification_type="alert",
            max_count=5,
            time_window_minutes=30,
            is_active=False,
            description=None,
            created_at=None,
            updated_at=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["user_id"] is None


# ---------------------------------------------------------------------------
# dish.py — Dish.__repr__, DishCategory.__repr__, DishIngredient.__repr__,
#           Dish.calculate_profit_margin
# ---------------------------------------------------------------------------

class TestDish:
    def _make(self):
        from src.models.dish import Dish
        return Dish(
            id=uuid.uuid4(),
            store_id="STORE001",
            name="宫保鸡丁",
            code="DISH001",
            price=38.0,
            cost=15.0,
            is_available=True,
        )

    def test_repr_returns_string(self):
        obj = self._make()
        r = repr(obj)
        assert isinstance(r, str)
        assert "Dish" in r

    def test_calculate_profit_margin(self):
        obj = self._make()
        result = obj.calculate_profit_margin()
        assert result is not None
        # (38 - 15) / 38 * 100 ≈ 60.53
        assert abs(result - 60.526315789) < 0.01

    def test_calculate_profit_margin_no_cost(self):
        obj = self._make()
        obj.cost = None
        result = obj.calculate_profit_margin()
        assert result is None


class TestDishCategory:
    def test_repr_returns_string(self):
        from src.models.dish import DishCategory
        obj = DishCategory(
            id=uuid.uuid4(),
            store_id="STORE001",
            name="热菜",
            code="HOT",
        )
        r = repr(obj)
        assert isinstance(r, str)
        assert "DishCategory" in r


class TestDishIngredient:
    def test_repr_returns_string(self):
        from src.models.dish import DishIngredient
        obj = DishIngredient(
            id=uuid.uuid4(),
            store_id="STORE001",
            dish_id=uuid.uuid4(),
            ingredient_id=uuid.uuid4(),
            quantity=150.0,
            unit="克",
        )
        r = repr(obj)
        assert isinstance(r, str)
        assert "DishIngredient" in r


# ---------------------------------------------------------------------------
# report_template.py — ReportTemplate.to_dict() and ScheduledReport.to_dict()
# ---------------------------------------------------------------------------

class TestReportTemplate:
    def _make(self):
        from src.models.report_template import ReportTemplate
        return ReportTemplate(
            id=uuid.uuid4(),
            name="月度营收报表",
            description="按门店汇总月度营收",
            data_source="transactions",
            columns=[{"field": "amount", "label": "金额"}],
            filters={"transaction_type": "income"},
            sort_by=[{"field": "created_at", "order": "desc"}],
            default_format="xlsx",
            is_public=True,
            created_by=uuid.uuid4(),
            store_id="STORE001",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 6, 1),
        )

    def test_to_dict_returns_dict(self):
        obj = self._make()
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["name"] == "月度营收报表"
        assert result["data_source"] == "transactions"

    def test_to_dict_no_timestamps(self):
        obj = self._make()
        obj.created_at = None
        obj.updated_at = None
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["created_at"] is None


class TestScheduledReport:
    def test_to_dict_returns_dict(self):
        from src.models.report_template import ScheduledReport
        obj = ScheduledReport(
            id=uuid.uuid4(),
            template_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            frequency="daily",
            run_at="06:00",
            day_of_week=None,
            day_of_month=None,
            channels=["email"],
            recipients=["admin@example.com"],
            format="xlsx",
            is_active=True,
            last_run_at=None,
            next_run_at="2024-07-01T06:00:00",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 6, 1),
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["frequency"] == "daily"


# ---------------------------------------------------------------------------
# backup_job.py — BackupJob.to_dict()
# ---------------------------------------------------------------------------

class TestBackupJob:
    def test_to_dict_returns_dict(self):
        from src.models.backup_job import BackupJob
        obj = BackupJob(
            id=uuid.uuid4(),
            backup_type="full",
            since_timestamp=None,
            tables=[],
            status="completed",
            celery_task_id="celery-123",
            progress=100,
            file_path="/backups/backup.tar.gz",
            file_size_bytes=1024000,
            checksum="abc123",
            row_counts={"users": 100},
            error_message=None,
            completed_at="2024-06-01T12:00:00",
            created_at=datetime(2024, 6, 1, 11, 0, 0),
            updated_at=datetime(2024, 6, 1, 12, 0, 0),
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["status"] == "completed"
        assert result["progress"] == 100

    def test_to_dict_no_timestamps(self):
        from src.models.backup_job import BackupJob
        obj = BackupJob(
            id=uuid.uuid4(),
            backup_type="incremental",
            since_timestamp="2024-05-31T00:00:00",
            tables=["orders", "transactions"],
            status="failed",
            celery_task_id=None,
            progress=50,
            file_path=None,
            file_size_bytes=None,
            checksum=None,
            row_counts=None,
            error_message="Connection timeout",
            completed_at=None,
            created_at=None,
            updated_at=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["created_at"] is None


# ---------------------------------------------------------------------------
# compliance.py — ComplianceLicense.to_dict()
# ---------------------------------------------------------------------------

class TestComplianceLicense:
    def _make(self):
        from src.models.compliance import ComplianceLicense, LicenseType, LicenseStatus
        return ComplianceLicense(
            id=str(uuid.uuid4()),
            store_id="STORE001",
            license_type=LicenseType.FOOD_OPERATION,
            license_name="食品经营许可证",
            license_number="JY20240001",
            holder_name=None,
            holder_employee_id=None,
            issue_date=date(2023, 1, 1),
            expiry_date=date(2025, 1, 1),
            status=LicenseStatus.VALID,
            remind_days_before=30,
            last_reminded_at=None,
            notes=None,
            created_at=datetime(2023, 1, 1),
            updated_at=datetime(2024, 6, 1),
        )

    def test_to_dict_returns_dict(self):
        obj = self._make()
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["license_name"] == "食品经营许可证"
        assert result["expiry_date"] == "2025-01-01"

    def test_to_dict_no_dates(self):
        from src.models.compliance import ComplianceLicense, LicenseType, LicenseStatus
        obj = ComplianceLicense(
            id=str(uuid.uuid4()),
            store_id="STORE002",
            license_type=LicenseType.HEALTH_CERT,
            license_name="健康证",
            license_number=None,
            holder_name="张三",
            holder_employee_id=str(uuid.uuid4()),
            issue_date=None,
            expiry_date=date(2025, 6, 1),
            status=LicenseStatus.EXPIRE_SOON,
            remind_days_before=30,
            last_reminded_at=datetime(2025, 5, 1),
            notes="需要尽快续期",
            created_at=None,
            updated_at=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["issue_date"] is None
        assert result["created_at"] is None


# ---------------------------------------------------------------------------
# export_job.py — ExportJob.to_dict()
# ---------------------------------------------------------------------------

class TestExportJob:
    def test_to_dict_returns_dict(self):
        from src.models.export_job import ExportJob
        obj = ExportJob(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            job_type="transactions",
            params={"store_id": "STORE001", "format": "csv"},
            format="csv",
            status="completed",
            celery_task_id="celery-456",
            progress=100,
            total_rows=5000,
            processed_rows=5000,
            file_path="/exports/transactions.csv",
            file_size_bytes=204800,
            error_message=None,
            completed_at="2024-06-01T15:00:00",
            created_at=datetime(2024, 6, 1, 14, 0, 0),
            updated_at=datetime(2024, 6, 1, 15, 0, 0),
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["job_type"] == "transactions"
        assert result["status"] == "completed"

    def test_to_dict_no_timestamps(self):
        from src.models.export_job import ExportJob
        obj = ExportJob(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            job_type="orders",
            params={},
            format="xlsx",
            status="pending",
            celery_task_id=None,
            progress=0,
            total_rows=None,
            processed_rows=0,
            file_path=None,
            file_size_bytes=None,
            error_message=None,
            completed_at=None,
            created_at=None,
            updated_at=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["created_at"] is None


# ---------------------------------------------------------------------------
# neural_event_log.py — NeuralEventLog.to_dict()
# ---------------------------------------------------------------------------

class TestNeuralEventLog:
    def _make(self):
        from src.models.neural_event_log import NeuralEventLog, EventProcessingStatus
        return NeuralEventLog(
            event_id=str(uuid.uuid4()),
            celery_task_id="celery-789",
            event_type="order.created",
            event_source="pos_webhook",
            store_id="STORE001",
            priority=1,
            data={"order_id": "O123"},
            processing_status=EventProcessingStatus.COMPLETED,
            vector_indexed=True,
            wechat_sent=False,
            downstream_tasks=[],
            actions_taken=["notify_manager"],
            queued_at=datetime(2024, 6, 1, 10, 0, 0),
            started_at=datetime(2024, 6, 1, 10, 0, 1),
            processed_at=datetime(2024, 6, 1, 10, 0, 2),
            error_message=None,
            retry_count=0,
        )

    def test_to_dict_returns_dict(self):
        obj = self._make()
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["event_type"] == "order.created"
        assert result["processing_status"] == "completed"

    def test_to_dict_no_timestamps(self):
        from src.models.neural_event_log import NeuralEventLog
        obj = NeuralEventLog(
            event_id=str(uuid.uuid4()),
            celery_task_id=None,
            event_type="revenue_anomaly",
            event_source="agent",
            store_id="STORE002",
            priority=0,
            data=None,
            processing_status=None,
            vector_indexed=False,
            wechat_sent=False,
            downstream_tasks=None,
            actions_taken=None,
            queued_at=None,
            started_at=None,
            processed_at=None,
            error_message="timeout",
            retry_count=3,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["processing_status"] is None
        assert result["queued_at"] is None


# ---------------------------------------------------------------------------
# queue.py — Queue.to_dict()
# ---------------------------------------------------------------------------

class TestQueue:
    def _make(self):
        from src.models.queue import Queue, QueueStatus
        return Queue(
            queue_id="Q001",
            queue_number=1,
            store_id="STORE001",
            customer_name="李四",
            customer_phone="13800138000",
            party_size=4,
            status=QueueStatus.WAITING,
            created_at=datetime(2024, 6, 1, 11, 30, 0),
            called_at=None,
            seated_at=None,
            cancelled_at=None,
            estimated_wait_time=20,
            actual_wait_time=None,
            table_number=None,
            table_type="中桌",
            special_requests=None,
            notes=None,
            notification_sent=False,
            notification_method=None,
            updated_at=datetime(2024, 6, 1, 11, 31, 0),
        )

    def test_to_dict_returns_dict(self):
        obj = self._make()
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["customer_name"] == "李四"
        assert result["status"] == "waiting"

    def test_to_dict_none_status(self):
        from src.models.queue import Queue
        obj = Queue(
            queue_id="Q002",
            queue_number=2,
            store_id="STORE001",
            customer_name="王五",
            customer_phone="13900139000",
            party_size=2,
            status=None,
            created_at=None,
            called_at=None,
            seated_at=None,
            cancelled_at=None,
            estimated_wait_time=None,
            actual_wait_time=None,
            table_number=None,
            table_type=None,
            special_requests=None,
            notes=None,
            notification_sent=False,
            notification_method=None,
            updated_at=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["status"] is None


# ---------------------------------------------------------------------------
# bom.py — BOMTemplate.total_cost property
# ---------------------------------------------------------------------------

class TestBOMTemplate:
    def _make_item(self, standard_qty, unit_cost):
        item = MagicMock()
        item.standard_qty = standard_qty
        item.unit_cost = unit_cost
        return item

    def test_total_cost_with_items(self):
        from src.models.bom import BOMTemplate
        obj = BOMTemplate(
            id=uuid.uuid4(),
            store_id="STORE001",
            dish_id=uuid.uuid4(),
            version="v1",
            effective_date=datetime(2024, 1, 1),
        )
        # Two items: 100g * 5分/g = 500分, 50g * 3分/g = 150分
        obj.items = [
            self._make_item(100, 5),
            self._make_item(50, 3),
        ]
        cost = obj.total_cost
        assert cost == 650  # 100*5 + 50*3

    def test_total_cost_empty_items(self):
        from src.models.bom import BOMTemplate
        obj = BOMTemplate(
            id=uuid.uuid4(),
            dish_id=uuid.uuid4(),
            version="v1",
        )
        obj.items = []
        assert obj.total_cost == 0

    def test_total_cost_none_unit_cost(self):
        from src.models.bom import BOMTemplate
        obj = BOMTemplate(
            id=uuid.uuid4(),
            dish_id=uuid.uuid4(),
            version="v1",
        )
        # item with no unit_cost (None → treated as 0)
        obj.items = [self._make_item(100, None)]
        assert obj.total_cost == 0

    def test_repr_returns_string(self):
        from src.models.bom import BOMTemplate
        obj = BOMTemplate(
            dish_id=uuid.uuid4(),
            version="v2",
            is_active=False,
        )
        r = repr(obj)
        assert isinstance(r, str)
        assert "BOMTemplate" in r


class TestBOMItem:
    def test_repr_returns_string(self):
        from src.models.bom import BOMItem
        obj = BOMItem(
            bom_id=uuid.uuid4(),
            ingredient_id="ING001",
            standard_qty=150.0,
        )
        r = repr(obj)
        assert isinstance(r, str)
        assert "BOMItem" in r


# ---------------------------------------------------------------------------
# decision_log.py — DecisionLog.to_dict()
# ---------------------------------------------------------------------------

class TestDecisionLog:
    def _make(self):
        from src.models.decision_log import DecisionLog, DecisionType, DecisionStatus, DecisionOutcome
        return DecisionLog(
            id=str(uuid.uuid4()),
            decision_type=DecisionType.REVENUE_ANOMALY,
            agent_type="RevenueAgent",
            agent_method="analyze_anomaly",
            store_id="STORE001",
            ai_suggestion={"action": "investigate"},
            ai_confidence=0.85,
            ai_reasoning="Revenue dropped 30%",
            ai_alternatives=[],
            manager_id=str(uuid.uuid4()),
            manager_decision={"action": "accepted"},
            manager_feedback="Good suggestion",
            decision_status=DecisionStatus.APPROVED,
            created_at=datetime(2024, 6, 1, 9, 0, 0),
            approved_at=datetime(2024, 6, 1, 10, 0, 0),
            executed_at=None,
            outcome=DecisionOutcome.SUCCESS,
            actual_result={"revenue": 50000},
            expected_result={"revenue": 48000},
            result_deviation=4.17,
            business_impact={"kpi": "improved"},
            cost_impact=0,
            revenue_impact=2000,
            is_training_data=1,
            trust_score=87.5,
            context_data={},
            rag_context={},
            approval_chain=[],
            notes=None,
        )

    def test_to_dict_returns_dict(self):
        obj = self._make()
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["decision_type"] == "revenue_anomaly"
        assert result["decision_status"] == "approved"
        assert result["outcome"] == "success"

    def test_to_dict_none_enums(self):
        from src.models.decision_log import DecisionLog
        obj = DecisionLog(
            id=str(uuid.uuid4()),
            decision_type=None,
            agent_type="TestAgent",
            agent_method="test_method",
            store_id="STORE001",
            ai_suggestion={},
            ai_confidence=None,
            ai_reasoning=None,
            ai_alternatives=None,
            manager_id=None,
            manager_decision=None,
            manager_feedback=None,
            decision_status=None,
            created_at=None,
            approved_at=None,
            executed_at=None,
            outcome=None,
            actual_result=None,
            expected_result=None,
            result_deviation=None,
            business_impact=None,
            cost_impact=None,
            revenue_impact=None,
            is_training_data=0,
            trust_score=None,
            context_data=None,
            rag_context=None,
            approval_chain=None,
            notes=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["decision_type"] is None
        assert result["outcome"] is None


# ---------------------------------------------------------------------------
# store.py — Store.to_dict()
# ---------------------------------------------------------------------------

class TestStore:
    def _make(self):
        from src.models.store import Store
        return Store(
            id="STORE001",
            name="测试门店",
            code="TST",
            address="北京市朝阳区XX路1号",
            city="北京",
            district="朝阳区",
            phone="010-12345678",
            email="store@example.com",
            latitude=39.9042,
            longitude=116.4074,
            brand_id="BRAND001",
            manager_id=uuid.uuid4(),
            region="华北",
            status="active",
            is_active=True,
            area=200.0,
            seats=80,
            floors=2,
            opening_date="2022-01-01",
            business_hours={"monday": "09:00-22:00"},
            config={},
            monthly_revenue_target=500000,
            daily_customer_target=300,
            cost_ratio_target=0.35,
            labor_cost_ratio_target=0.25,
            created_at=datetime(2022, 1, 1),
            updated_at=datetime(2024, 6, 1),
        )

    def test_to_dict_returns_dict(self):
        obj = self._make()
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["id"] == "STORE001"
        assert result["name"] == "测试门店"
        assert result["status"] == "active"

    def test_to_dict_no_manager(self):
        obj = self._make()
        obj.manager_id = None
        obj.created_at = None
        obj.updated_at = None
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["manager_id"] is None
        assert result["created_at"] is None


# ---------------------------------------------------------------------------
# audit_log.py — AuditLog.to_dict()
# ---------------------------------------------------------------------------

class TestAuditLog:
    def _make(self):
        from src.models.audit_log import AuditLog
        return AuditLog(
            id=str(uuid.uuid4()),
            action="login",
            resource_type="user",
            resource_id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            username="admin",
            user_role="admin",
            description="用户登录",
            changes=None,
            old_value=None,
            new_value=None,
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0",
            request_method="POST",
            request_path="/api/auth/login",
            status="success",
            error_message=None,
            store_id="STORE001",
            created_at=datetime(2024, 6, 1, 9, 0, 0),
        )

    def test_to_dict_returns_dict(self):
        obj = self._make()
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["action"] == "login"
        assert result["status"] == "success"
        assert result["ip_address"] == "127.0.0.1"

    def test_to_dict_no_created_at(self):
        obj = self._make()
        obj.created_at = None
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["created_at"] is None


# ---------------------------------------------------------------------------
# integration.py — ExternalSystem, SyncLog, POSTransaction, SupplierOrder,
#                  MemberSync, ReservationSync — all to_dict()
# ---------------------------------------------------------------------------

class TestExternalSystem:
    def _make(self):
        from src.models.integration import ExternalSystem, IntegrationType, IntegrationStatus, SyncStatus
        return ExternalSystem(
            id=uuid.uuid4(),
            name="美团POS",
            type=IntegrationType.POS,
            provider="美团",
            version="2.0",
            status=IntegrationStatus.ACTIVE,
            store_id="STORE001",
            api_endpoint="https://api.meituan.com/pos",
            webhook_url="https://api.zhilian.com/webhook/meituan",
            sync_enabled=True,
            sync_interval=300,
            last_sync_at=datetime(2024, 6, 1, 12, 0, 0),
            last_sync_status=SyncStatus.SUCCESS,
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 6, 1),
        )

    def test_to_dict_returns_dict(self):
        obj = self._make()
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["name"] == "美团POS"
        assert result["type"] == "pos"
        assert result["status"] == "active"
        assert result["last_sync_status"] == "success"

    def test_to_dict_none_enums_and_dates(self):
        from src.models.integration import ExternalSystem
        obj = ExternalSystem(
            id=uuid.uuid4(),
            name="未配置系统",
            type=None,
            provider=None,
            version=None,
            status=None,
            store_id=None,
            api_endpoint=None,
            webhook_url=None,
            sync_enabled=False,
            sync_interval=0,
            last_sync_at=None,
            last_sync_status=None,
            created_at=None,
            updated_at=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["type"] is None
        assert result["last_sync_at"] is None
        assert result["created_at"] is None


class TestSyncLog:
    def test_to_dict_returns_dict(self):
        from src.models.integration import SyncLog, SyncStatus
        obj = SyncLog(
            id=uuid.uuid4(),
            system_id=uuid.uuid4(),
            sync_type="orders",
            status=SyncStatus.SUCCESS,
            records_total=100,
            records_success=98,
            records_failed=2,
            started_at=datetime(2024, 6, 1, 11, 0, 0),
            completed_at=datetime(2024, 6, 1, 11, 5, 0),
            duration_seconds=300.5,
            error_message=None,
            error_details=None,
            request_data=None,
            response_data=None,
            created_at=datetime(2024, 6, 1, 11, 0, 0),
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["sync_type"] == "orders"
        assert result["status"] == "success"

    def test_to_dict_no_completed_at(self):
        from src.models.integration import SyncLog, SyncStatus
        obj = SyncLog(
            id=uuid.uuid4(),
            system_id=uuid.uuid4(),
            sync_type="members",
            status=SyncStatus.FAILED,
            records_total=0,
            records_success=0,
            records_failed=0,
            started_at=datetime(2024, 6, 1, 11, 0, 0),
            completed_at=None,
            duration_seconds=None,
            error_message="Network error",
            error_details={"code": 500},
            request_data=None,
            response_data=None,
            created_at=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["completed_at"] is None
        assert result["created_at"] is None


class TestPOSTransaction:
    def test_to_dict_returns_dict(self):
        from src.models.integration import POSTransaction, SyncStatus
        obj = POSTransaction(
            id=uuid.uuid4(),
            system_id=uuid.uuid4(),
            store_id="STORE001",
            pos_transaction_id="POS-TXN-001",
            pos_order_number="ORD-001",
            transaction_type="sale",
            subtotal=100.0,
            tax=6.0,
            discount=5.0,
            total=101.0,
            payment_method="wechat_pay",
            items=[{"name": "宫保鸡丁", "qty": 1, "price": 38}],
            customer_info=None,
            sync_status=SyncStatus.SUCCESS,
            synced_at=datetime(2024, 6, 1, 12, 5, 0),
            transaction_time=datetime(2024, 6, 1, 12, 0, 0),
            created_at=datetime(2024, 6, 1, 12, 0, 0),
            updated_at=datetime(2024, 6, 1, 12, 5, 0),
            raw_data=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["pos_transaction_id"] == "POS-TXN-001"
        assert result["sync_status"] == "success"


class TestSupplierOrder:
    def test_to_dict_returns_dict(self):
        from src.models.integration import SupplierOrder, SyncStatus
        obj = SupplierOrder(
            id=uuid.uuid4(),
            system_id=uuid.uuid4(),
            store_id="STORE001",
            order_number="SO-001",
            supplier_id="SUP001",
            supplier_name="新鲜蔬菜供应商",
            order_type="purchase",
            status="confirmed",
            subtotal=2000.0,
            tax=60.0,
            shipping=50.0,
            total=2110.0,
            items=[],
            delivery_info={},
            order_date=datetime(2024, 6, 1),
            expected_delivery=datetime(2024, 6, 3),
            actual_delivery=None,
            sync_status=SyncStatus.PENDING,
            synced_at=None,
            created_at=datetime(2024, 6, 1, 9, 0, 0),
            updated_at=datetime(2024, 6, 1, 9, 0, 0),
            raw_data=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["order_number"] == "SO-001"
        assert result["sync_status"] == "pending"
        assert result["actual_delivery"] is None


class TestMemberSync:
    def test_to_dict_returns_dict(self):
        from src.models.integration import MemberSync, SyncStatus
        obj = MemberSync(
            id=uuid.uuid4(),
            system_id=uuid.uuid4(),
            member_id="MEM001",
            external_member_id="EXT-MEM-001",
            phone="13800138001",
            name="张三",
            email="zhangsan@example.com",
            level="gold",
            points=1500,
            balance=200.0,
            sync_status=SyncStatus.SUCCESS,
            synced_at=datetime(2024, 6, 1, 10, 0, 0),
            last_activity=datetime(2024, 5, 31),
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 6, 1),
            raw_data=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["member_id"] == "MEM001"
        assert result["sync_status"] == "success"


class TestReservationSync:
    def test_to_dict_returns_dict(self):
        from src.models.integration import ReservationSync, SyncStatus
        obj = ReservationSync(
            id=uuid.uuid4(),
            system_id=uuid.uuid4(),
            store_id="STORE001",
            reservation_id="RES001",
            external_reservation_id="EXT-RES-001",
            reservation_number="RN-20240601-001",
            customer_name="李四",
            customer_phone="13900139001",
            customer_count=4,
            reservation_date=datetime(2024, 6, 15, 19, 0, 0),
            reservation_time="19:00-21:00",
            arrival_time=None,
            table_type="大桌",
            table_number="A08",
            area="大厅",
            status="confirmed",
            special_requirements="不要辣",
            notes=None,
            deposit_required=False,
            deposit_amount=0,
            deposit_paid=False,
            source="yiding",
            channel="app",
            sync_status=SyncStatus.SUCCESS,
            synced_at=datetime(2024, 6, 1, 10, 0, 0),
            created_at=datetime(2024, 6, 1),
            updated_at=datetime(2024, 6, 1),
            cancelled_at=None,
            raw_data=None,
        )
        result = obj.to_dict()
        assert isinstance(result, dict)
        assert result["reservation_id"] == "RES001"
        assert result["status"] == "confirmed"
        assert result["sync_status"] == "success"
        assert result["arrival_time"] is None


# ---------------------------------------------------------------------------
# action_plan.py — ActionPlan.__repr__
# ---------------------------------------------------------------------------

class TestActionPlan:
    def _make(self):
        from src.models.action_plan import ActionPlan, DispatchStatus, ActionOutcome
        from datetime import date
        return ActionPlan(
            store_id="STORE001",
            reasoning_report_id=uuid.uuid4(),
            report_date=date(2026, 3, 1),
            dimension="waste",
            severity="P1",
            root_cause="staff_error",
            confidence=0.85,
            dispatch_status=DispatchStatus.DISPATCHED.value,
            outcome=ActionOutcome.RESOLVED.value,
        )

    def test_repr_returns_string(self):
        obj = self._make()
        result = repr(obj)
        assert isinstance(result, str)
        assert "STORE001" in result
        assert "waste" in result

    def test_enum_values(self):
        from src.models.action_plan import DispatchStatus, ActionOutcome
        assert DispatchStatus.PENDING.value == "pending"
        assert ActionOutcome.RESOLVED.value == "resolved"


# ---------------------------------------------------------------------------
# cross_store.py — CrossStoreMetric, StoreSimilarityCache, StorePeerGroup
# ---------------------------------------------------------------------------

class TestCrossStoreMetric:
    def _make(self):
        from src.models.cross_store import CrossStoreMetric
        from datetime import date
        return CrossStoreMetric(
            store_id="STORE001",
            metric_date=date(2026, 3, 1),
            metric_name="waste_rate",
            value=0.12,
            peer_group="standard_华东",
            peer_count=10,
            peer_p25=0.05,
            peer_p50=0.08,
            peer_p75=0.14,
            peer_p90=0.20,
            percentile_in_peer=75.0,
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.store_id == "STORE001"
        assert obj.metric_name == "waste_rate"
        assert obj.value == 0.12


class TestStoreSimilarityCache:
    def _make(self):
        from src.models.cross_store import StoreSimilarityCache
        return StoreSimilarityCache(
            store_a_id="STORE001",
            store_b_id="STORE002",
            similarity_score=0.75,
            menu_overlap=0.60,
            region_match=True,
            tier_match=True,
            capacity_ratio=0.9,
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.store_a_id == "STORE001"
        assert obj.similarity_score == 0.75


class TestStorePeerGroup:
    def _make(self):
        from src.models.cross_store import StorePeerGroup
        return StorePeerGroup(
            group_key="standard_华东",
            tier="standard",
            region="华东",
            store_ids=["STORE001", "STORE002"],
            store_count=2,
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.group_key == "standard_华东"
        assert obj.store_count == 2


# ---------------------------------------------------------------------------
# customer_key.py — CustomerKey.__repr__, EncryptedField
# ---------------------------------------------------------------------------

class TestCustomerKey:
    def _make(self):
        from src.models.customer_key import CustomerKey, KeyStatus, KeyAlgorithm
        return CustomerKey(
            store_id="STORE001",
            key_version=1,
            key_alias="v1-2026-03",
            algorithm=KeyAlgorithm.AES_256_GCM,
            encrypted_dek="base64encodeddek==",
            status=KeyStatus.ACTIVE,
            is_active=True,
            purpose="data_encryption",
        )

    def test_repr_returns_string(self):
        obj = self._make()
        result = repr(obj)
        assert isinstance(result, str)
        assert "STORE001" in result

    def test_enum_values(self):
        from src.models.customer_key import KeyStatus, KeyAlgorithm
        assert KeyStatus.ACTIVE.value == "active"
        assert KeyAlgorithm.AES_256_GCM.value == "AES-256-GCM"


class TestEncryptedField:
    def _make(self):
        from src.models.customer_key import EncryptedField
        return EncryptedField(
            store_id="STORE001",
            key_id=uuid.uuid4(),
            table_name="waste_events",
            field_name="evidence",
            record_id="REC-001",
            algorithm="AES-256-GCM",
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.store_id == "STORE001"
        assert obj.table_name == "waste_events"


# ---------------------------------------------------------------------------
# forecast.py — ForecastResult.__repr__
# ---------------------------------------------------------------------------

class TestForecastResult:
    def _make(self):
        from src.models.forecast import ForecastResult
        from datetime import date
        return ForecastResult(
            store_id="STORE001",
            brand_id="BRAND001",
            target_date=date(2026, 3, 2),
            metric="revenue",
            predicted_value=15000.0,
            confidence="high",
            basis="statistical",
            estimated_revenue=15000.0,
        )

    def test_repr_returns_string(self):
        obj = self._make()
        result = repr(obj)
        assert isinstance(result, str)
        assert "STORE001" in result
        assert "high" in result

    def test_repr_contains_basis(self):
        obj = self._make()
        result = repr(obj)
        assert "statistical" in result


# ---------------------------------------------------------------------------
# ingredient_mapping.py — IngredientMapping, FusionAuditLog
# ---------------------------------------------------------------------------

class TestIngredientMapping:
    def _make(self):
        from src.models.ingredient_mapping import IngredientMapping, FusionMethod
        return IngredientMapping(
            canonical_id="ING-SEAFOOD-CAOY-001",
            canonical_name="草鱼片",
            aliases=["草鱼", "Grass Carp Slice"],
            category="seafood",
            unit="kg",
            external_ids={"pinzhi": "12345"},
            source_costs={"supplier_invoice": {"cost_fen": 3800}},
            canonical_cost_fen=3800,
            fusion_confidence=0.92,
            fusion_method=FusionMethod.EXACT_NAME.value,
            conflict_flag=False,
            merge_of=[],
            is_active=True,
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.canonical_id == "ING-SEAFOOD-CAOY-001"
        assert obj.canonical_name == "草鱼片"
        assert obj.fusion_confidence == 0.92

    def test_fusion_method_enum(self):
        from src.models.ingredient_mapping import FusionMethod
        assert FusionMethod.EXACT_ID.value == "exact_id"
        assert FusionMethod.MANUAL.value == "manual_merge"


class TestFusionAuditLog:
    def _make(self):
        from src.models.ingredient_mapping import FusionAuditLog
        return FusionAuditLog(
            entity_type="ingredient",
            canonical_id="ING-SEAFOOD-CAOY-001",
            action="create_canonical",
            source_system="pinzhi",
            raw_external_id="12345",
            raw_name="草鱼",
            confidence=0.90,
            fusion_method="exact_name",
            created_by="system",
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.entity_type == "ingredient"
        assert obj.action == "create_canonical"


# ---------------------------------------------------------------------------
# knowledge_rule.py — KnowledgeRule.__repr__, IndustryBenchmark.__repr__
# ---------------------------------------------------------------------------

class TestKnowledgeRule:
    def _make(self):
        from src.models.knowledge_rule import KnowledgeRule, RuleCategory, RuleType, RuleStatus
        return KnowledgeRule(
            rule_code="WASTE-001",
            name="损耗率超标规则",
            description="当损耗率连续3天超过15%时触发",
            category=RuleCategory.WASTE,
            rule_type=RuleType.THRESHOLD,
            condition={"metric": "waste_rate", "operator": ">", "threshold": 0.15},
            conclusion={"root_cause": "staff_error", "confidence": 0.72},
            base_confidence=0.72,
            weight=1.0,
            status=RuleStatus.ACTIVE,
            source="expert",
            is_public=False,
        )

    def test_repr_returns_string(self):
        obj = self._make()
        result = repr(obj)
        assert isinstance(result, str)
        assert "WASTE-001" in result

    def test_enum_values(self):
        from src.models.knowledge_rule import RuleCategory, RuleType, RuleStatus
        assert RuleCategory.WASTE.value == "waste"
        assert RuleType.THRESHOLD.value == "threshold"
        assert RuleStatus.ACTIVE.value == "active"


class TestRuleExecution:
    def _make(self):
        from src.models.knowledge_rule import RuleExecution
        return RuleExecution(
            rule_id=uuid.uuid4(),
            rule_code="WASTE-001",
            store_id="STORE001",
            event_id="EVT-001",
            condition_values={"waste_rate": 0.18},
            conclusion_output={"root_cause": "staff_error"},
            confidence_score=0.72,
            is_verified=False,
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.rule_code == "WASTE-001"
        assert obj.store_id == "STORE001"


class TestIndustryBenchmark:
    def _make(self):
        from src.models.knowledge_rule import IndustryBenchmark, RuleCategory
        return IndustryBenchmark(
            industry_type="seafood",
            metric_name="waste_rate",
            metric_category=RuleCategory.WASTE,
            p25_value=0.05,
            p50_value=0.08,
            p75_value=0.14,
            p90_value=0.20,
            unit="%",
            direction="lower_better",
            data_source="2025中国餐饮白皮书",
            sample_size=500,
        )

    def test_repr_returns_string(self):
        obj = self._make()
        result = repr(obj)
        assert isinstance(result, str)
        assert "seafood" in result
        assert "waste_rate" in result
        assert "0.08" in result


# ---------------------------------------------------------------------------
# ontology_action.py — OntologyAction (no repr)
# ---------------------------------------------------------------------------

class TestOntologyAction:
    def _make(self):
        from src.models.ontology_action import OntologyAction, ActionStatus, ActionPriority
        return OntologyAction(
            tenant_id="TENANT001",
            store_id="STORE001",
            action_type="waste_follow_up",
            assignee_staff_id="STAFF001",
            assignee_wechat_id="wx_staff001",
            status=ActionStatus.CREATED.value,
            priority=ActionPriority.P1.value,
            title="跟进损耗问题",
            body="请核查今日食材损耗情况",
            extra={},
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.tenant_id == "TENANT001"
        assert obj.store_id == "STORE001"
        assert obj.action_type == "waste_follow_up"

    def test_escalation_minutes_constant(self):
        from src.models.ontology_action import ESCALATION_MINUTES, ActionPriority
        assert ESCALATION_MINUTES[ActionPriority.P0.value] == 30
        assert ESCALATION_MINUTES[ActionPriority.P1.value] == 120


# ---------------------------------------------------------------------------
# ops.py — OpsEvent, OpsAsset, OpsMaintenancePlan (no repr)
# ---------------------------------------------------------------------------

class TestOpsEvent:
    def _make(self):
        from src.models.ops import OpsEvent, OpsEventSeverity, OpsEventStatus
        return OpsEvent(
            store_id="STORE001",
            event_type="health_check",
            severity=OpsEventSeverity.MEDIUM.value,
            component="pos",
            description="POS 心跳检测超时",
            raw_data={"latency_ms": 5000},
            status=OpsEventStatus.OPEN.value,
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.store_id == "STORE001"
        assert obj.event_type == "health_check"
        assert obj.severity == "medium"

    def test_enum_values(self):
        from src.models.ops import OpsEventSeverity, OpsEventStatus, OpsAssetType, OpsMaintenancePriority
        assert OpsEventSeverity.CRITICAL.value == "critical"
        assert OpsEventStatus.RESOLVED.value == "resolved"
        assert OpsAssetType.POS.value == "pos"
        assert OpsMaintenancePriority.URGENT.value == "urgent"


class TestOpsAsset:
    def _make(self):
        from src.models.ops import OpsAsset, OpsAssetType
        return OpsAsset(
            store_id="STORE001",
            asset_type=OpsAssetType.POS.value,
            name="收银台POS-01",
            ip_address="192.168.1.10",
            mac_address="AA:BB:CC:DD:EE:FF",
            firmware_version="v2.3.1",
            serial_number="SN-12345",
            status="online",
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.store_id == "STORE001"
        assert obj.asset_type == "pos"
        assert obj.status == "online"


class TestOpsMaintenancePlan:
    def _make(self):
        from src.models.ops import OpsMaintenancePlan, OpsMaintenancePriority
        return OpsMaintenancePlan(
            store_id="STORE001",
            asset_id=uuid.uuid4(),
            plan_type="preventive",
            description="定期检查打印机墨盒",
            priority=OpsMaintenancePriority.MEDIUM.value,
            status="pending",
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.plan_type == "preventive"
        assert obj.priority == "medium"
        assert obj.status == "pending"


# ---------------------------------------------------------------------------
# private_domain.py — PrivateDomainMember, PrivateDomainSignal,
#                      PrivateDomainJourney, StoreQuadrantRecord (no repr)
# ---------------------------------------------------------------------------

class TestPrivateDomainMember:
    def _make(self):
        from src.models.private_domain import PrivateDomainMember, RFMLevel, StoreQuadrant
        return PrivateDomainMember(
            store_id="STORE001",
            customer_id="CUST-001",
            rfm_level=RFMLevel.S2.value,
            store_quadrant=StoreQuadrant.BENCHMARK.value,
            dynamic_tags=["vip", "seafood_lover"],
            recency_days=5,
            frequency=12,
            monetary=150000,
            risk_score=0.1,
            channel_source="wechat",
            wechat_openid="oXXXXXXXXX",
            is_active=True,
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.store_id == "STORE001"
        assert obj.customer_id == "CUST-001"
        assert obj.rfm_level == "S2"

    def test_enum_values(self):
        from src.models.private_domain import RFMLevel, StoreQuadrant, SignalType, JourneyType, JourneyStatus
        assert RFMLevel.S1.value == "S1"
        assert StoreQuadrant.BENCHMARK.value == "benchmark"
        assert SignalType.CHURN_RISK.value == "churn_risk"
        assert JourneyType.VIP_RETENTION.value == "vip_retention"
        assert JourneyStatus.RUNNING.value == "running"


class TestPrivateDomainSignal:
    def _make(self):
        from src.models.private_domain import PrivateDomainSignal, SignalType
        return PrivateDomainSignal(
            signal_id="SIG-20260301-001",
            store_id="STORE001",
            customer_id="CUST-001",
            signal_type=SignalType.CHURN_RISK.value,
            description="客户30天未访问，存在流失风险",
            severity="high",
            action_taken="发送召回优惠券",
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.signal_id == "SIG-20260301-001"
        assert obj.signal_type == "churn_risk"


class TestPrivateDomainJourney:
    def _make(self):
        from src.models.private_domain import PrivateDomainJourney, JourneyType, JourneyStatus
        return PrivateDomainJourney(
            journey_id="JRNY-20260301-001",
            store_id="STORE001",
            customer_id="CUST-001",
            journey_type=JourneyType.REACTIVATION.value,
            status=JourneyStatus.RUNNING.value,
            current_step=2,
            total_steps=5,
            step_history=[{"step": 1, "action": "send_coupon", "done": True}],
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.journey_id == "JRNY-20260301-001"
        assert obj.total_steps == 5
        assert obj.status == "running"


class TestStoreQuadrantRecord:
    def _make(self):
        from src.models.private_domain import StoreQuadrantRecord, StoreQuadrant
        return StoreQuadrantRecord(
            store_id="STORE001",
            quadrant=StoreQuadrant.POTENTIAL.value,
            competition_density=0.65,
            member_penetration=0.30,
            untapped_potential=500,
            strategy="加强私域运营，提升会员渗透率",
        )

    def test_instantiation(self):
        obj = self._make()
        assert obj.store_id == "STORE001"
        assert obj.quadrant == "potential"
        assert obj.competition_density == 0.65


# ---------------------------------------------------------------------------
# reasoning.py — ReasoningReport.__repr__
# ---------------------------------------------------------------------------

class TestReasoningReport:
    def _make(self):
        from src.models.reasoning import ReasoningReport, SeverityLevel, ReasoningDimension
        from datetime import date
        return ReasoningReport(
            store_id="STORE001",
            report_date=date(2026, 3, 1),
            dimension=ReasoningDimension.WASTE.value,
            severity=SeverityLevel.P2.value,
            root_cause="staff_error",
            confidence=0.73,
            evidence_chain=["waste_rate > 0.15 for 3 days"],
            triggered_rule_codes=["WASTE-001"],
            recommended_actions=["联系门店长复核操作流程"],
            peer_group="standard_华东",
            peer_percentile=82.0,
            kpi_snapshot={"waste_rate": 0.15},
            is_actioned=False,
        )

    def test_repr_returns_string(self):
        obj = self._make()
        result = repr(obj)
        assert isinstance(result, str)
        assert "STORE001" in result
        assert "P2" in result

    def test_repr_contains_dimension(self):
        obj = self._make()
        result = repr(obj)
        assert "waste" in result

    def test_enum_values(self):
        from src.models.reasoning import SeverityLevel, ReasoningDimension
        assert SeverityLevel.P1.value == "P1"
        assert ReasoningDimension.WASTE.value == "waste"
        assert ReasoningDimension.CROSS_STORE.value == "cross_store"


# ---------------------------------------------------------------------------
# workflow.py — DailyWorkflow.__repr__, WorkflowPhase.__repr__,
#               DecisionVersion.__repr__
# ---------------------------------------------------------------------------

class TestDailyWorkflow:
    def _make(self):
        from src.models.workflow import DailyWorkflow, WorkflowStatus
        from datetime import date
        return DailyWorkflow(
            store_id="STORE001",
            plan_date=date(2026, 3, 2),
            trigger_date=date(2026, 3, 1),
            status=WorkflowStatus.PARTIAL_LOCKED.value,
            current_phase="scheduling",
        )

    def test_repr_returns_string(self):
        obj = self._make()
        result = repr(obj)
        assert isinstance(result, str)
        assert "STORE001" in result
        assert "partial_locked" in result

    def test_repr_contains_phase(self):
        obj = self._make()
        result = repr(obj)
        assert "scheduling" in result

    def test_enum_and_constants(self):
        from src.models.workflow import WorkflowStatus, PhaseStatus, GenerationMode
        from src.models.workflow import ALL_PHASES, PHASE_CONFIG, PHASE_INITIAL_PLAN
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert PhaseStatus.LOCKED.value == "locked"
        assert GenerationMode.FAST.value == "fast"
        assert PHASE_INITIAL_PLAN in ALL_PHASES
        assert len(ALL_PHASES) == 6
        assert "deadline_offset" in PHASE_CONFIG[PHASE_INITIAL_PLAN]


class TestWorkflowPhase:
    def _make(self):
        from src.models.workflow import WorkflowPhase, PhaseStatus
        return WorkflowPhase(
            workflow_id=uuid.uuid4(),
            phase_name="procurement",
            phase_order=2,
            deadline=datetime(2026, 3, 1, 18, 0, 0),
            status=PhaseStatus.LOCKED.value,
            locked_by="auto",
        )

    def test_repr_returns_string(self):
        obj = self._make()
        result = repr(obj)
        assert isinstance(result, str)
        assert "procurement" in result
        assert "locked" in result

    def test_repr_contains_deadline_time(self):
        obj = self._make()
        result = repr(obj)
        assert "18:00" in result

    def test_repr_no_deadline(self):
        from src.models.workflow import WorkflowPhase, PhaseStatus
        obj = WorkflowPhase(
            workflow_id=uuid.uuid4(),
            phase_name="menu",
            phase_order=4,
            deadline=None,
            status=PhaseStatus.PENDING.value,
        )
        result = repr(obj)
        assert "N/A" in result


class TestDecisionVersion:
    def _make(self, is_final=False):
        from src.models.workflow import DecisionVersion, GenerationMode
        from datetime import date
        return DecisionVersion(
            phase_id=uuid.uuid4(),
            store_id="STORE001",
            phase_name="procurement",
            plan_date=date(2026, 3, 2),
            version_number=1,
            content={"items": [], "total_cost": 5000},
            generation_mode=GenerationMode.FAST.value,
            generation_seconds=12.5,
            data_completeness=0.95,
            confidence=0.88,
            submitted_by="system",
            is_final=is_final,
        )

    def test_repr_returns_string(self):
        obj = self._make()
        result = repr(obj)
        assert isinstance(result, str)
        assert "procurement" in result
        assert "fast" in result

    def test_repr_final_marker(self):
        obj = self._make(is_final=True)
        result = repr(obj)
        assert "FINAL" in result

    def test_repr_not_final(self):
        obj = self._make(is_final=False)
        result = repr(obj)
        # is_final=False means the FINAL marker should not appear
        assert "FINAL" not in result
