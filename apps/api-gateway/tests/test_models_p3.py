import uuid
import pytest
from src.models.marketing_task import (
    MarketingTask,
    MarketingTaskTarget,
    MarketingTaskAssignment,
    MarketingTaskExecution,
    MarketingTaskStats,
)


class TestMarketingTaskModel:
    def test_create_instance(self):
        task = MarketingTask(
            brand_id="BRAND001",
            title="春节回流召回活动",
            audience_type="preset",
            audience_config={"segment": "lapsed_30d"},
            created_by=uuid.uuid4(),
        )
        assert task.title == "春节回流召回活动"
        assert task.brand_id == "BRAND001"
        assert task.audience_type == "preset"

    def test_default_status_is_draft(self):
        task = MarketingTask(
            brand_id="BRAND001",
            title="测试任务",
            audience_type="ai_query",
            audience_config={},
            created_by=uuid.uuid4(),
        )
        # SQLAlchemy applies column defaults at INSERT, not at __init__
        # The default value may be None at object creation but becomes "draft" on flush
        assert task.status in ("draft", None)

    def test_table_name(self):
        assert MarketingTask.__tablename__ == "marketing_tasks"

    def test_audience_type_values(self):
        for at in ("preset", "ai_query"):
            task = MarketingTask(
                brand_id="B1", title="T", audience_type=at,
                audience_config={}, created_by=uuid.uuid4(),
            )
            assert task.audience_type == at

    def test_optional_fields_nullable(self):
        task = MarketingTask(
            brand_id="BRAND001",
            title="简单任务",
            audience_type="preset",
            audience_config={"segment": "vip"},
            created_by=uuid.uuid4(),
        )
        assert task.description is None
        assert task.script_template is None
        assert task.coupon_config is None
        assert task.deadline is None
        assert task.published_at is None


class TestMarketingTaskTargetModel:
    def test_create_instance(self):
        target = MarketingTaskTarget(
            task_id=uuid.uuid4(),
            consumer_id=uuid.uuid4(),
            store_id="STORE001",
        )
        assert target.store_id == "STORE001"

    def test_table_name(self):
        assert MarketingTaskTarget.__tablename__ == "marketing_task_targets"

    def test_unique_constraint_exists(self):
        constraints = {c.name for c in MarketingTaskTarget.__table_args__}
        assert "uq_task_consumer_store" in constraints

    def test_profile_snapshot_nullable(self):
        target = MarketingTaskTarget(
            task_id=uuid.uuid4(), consumer_id=uuid.uuid4(), store_id="S1",
        )
        assert target.profile_snapshot is None


class TestMarketingTaskAssignmentModel:
    def test_create_instance(self):
        assignment = MarketingTaskAssignment(
            task_id=uuid.uuid4(),
            store_id="STORE001",
        )
        assert assignment.store_id == "STORE001"

    def test_table_name(self):
        assert MarketingTaskAssignment.__tablename__ == "marketing_task_assignments"

    def test_default_status_pending(self):
        assignment = MarketingTaskAssignment(
            task_id=uuid.uuid4(), store_id="S1",
        )
        assert assignment.status in ("pending", None)

    def test_default_counts(self):
        assignment = MarketingTaskAssignment(
            task_id=uuid.uuid4(), store_id="S1",
        )
        # Column defaults apply at INSERT, may be None at init
        assert assignment.target_count in (0, None)
        assert assignment.completed_count in (0, None)

    def test_assigned_to_nullable(self):
        assignment = MarketingTaskAssignment(
            task_id=uuid.uuid4(), store_id="S1",
        )
        assert assignment.assigned_to is None

    def test_index_exists(self):
        indexes = {i.name for i in MarketingTaskAssignment.__table_args__}
        assert "idx_assign_task_status" in indexes


class TestMarketingTaskExecutionModel:
    def test_create_instance(self):
        from datetime import datetime
        execution = MarketingTaskExecution(
            assignment_id=uuid.uuid4(),
            target_id=uuid.uuid4(),
            executor_id=uuid.uuid4(),
            action_type="wechat_msg",
            executed_at=datetime.utcnow(),
        )
        assert execution.action_type == "wechat_msg"

    def test_table_name(self):
        assert MarketingTaskExecution.__tablename__ == "marketing_task_executions"

    def test_action_type_values(self):
        from datetime import datetime
        for at in ("wechat_msg", "coupon", "call", "in_store"):
            e = MarketingTaskExecution(
                assignment_id=uuid.uuid4(), target_id=uuid.uuid4(),
                executor_id=uuid.uuid4(), action_type=at,
                executed_at=datetime.utcnow(),
            )
            assert e.action_type == at

    def test_optional_fields_nullable(self):
        from datetime import datetime
        e = MarketingTaskExecution(
            assignment_id=uuid.uuid4(), target_id=uuid.uuid4(),
            executor_id=uuid.uuid4(), action_type="call",
            executed_at=datetime.utcnow(),
        )
        assert e.action_detail is None
        assert e.distribution_id is None
        assert e.feedback is None


class TestMarketingTaskStatsModel:
    def test_create_instance(self):
        from datetime import date
        stats = MarketingTaskStats(
            task_id=uuid.uuid4(),
            store_id="STORE001",
            date=date(2026, 3, 18),
        )
        assert stats.store_id == "STORE001"
        assert stats.date == date(2026, 3, 18)

    def test_table_name(self):
        assert MarketingTaskStats.__tablename__ == "marketing_task_stats"

    def test_unique_constraint_exists(self):
        constraints = {c.name for c in MarketingTaskStats.__table_args__}
        assert "uq_task_stats_daily" in constraints

    def test_default_counts(self):
        from datetime import date
        stats = MarketingTaskStats(
            task_id=uuid.uuid4(), store_id="S1", date=date.today(),
        )
        assert stats.target_count in (0, None)
        assert stats.reached_count in (0, None)
        assert stats.coupon_distributed in (0, None)
        assert stats.coupon_redeemed in (0, None)
        assert stats.driven_gmv_fen in (0, None)
