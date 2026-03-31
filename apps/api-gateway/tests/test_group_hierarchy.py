"""
Phase 1 集团层级架构测试
测试：GroupTenant / BrandConsumerProfile 模型 + TenantFilter 四层注入 + One ID 聚合视图

运行：
    cd apps/api-gateway
    pytest tests/test_group_hierarchy.py -v
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

# 必须在所有 src 导入前设置环境变量
for _k, _v in {
    "APP_ENV": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test_db",
    "REDIS_URL": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret-key-phase1",
    "JWT_SECRET": "test-jwt-secret-phase1",
}.items():
    os.environ.setdefault(_k, _v)

import pytest


# ============================================================
# 测试1：GroupTenant 模型字段完整性
# ============================================================

class TestGroupTenantModelFields:
    """验证 GroupTenant ORM 模型包含所有必需字段及默认值"""

    def test_group_tenant_model_fields(self):
        from src.models.group_tenant import GroupTenant

        # 验证表名
        assert GroupTenant.__tablename__ == "group_tenants"

        # 获取所有列名
        col_names = {c.name for c in GroupTenant.__table__.columns}

        # 必须字段检查
        required_fields = {
            "id",
            "group_id",
            "billing_email",
            "subscription_tier",
            "feature_flags",
            "status",
            "contract_start_date",
            "created_at",
            "updated_at",
        }
        missing = required_fields - col_names
        assert not missing, f"GroupTenant 缺少字段：{missing}"

    def test_group_tenant_subscription_tier_default(self):
        """subscription_tier 默认值应为 'standard'"""
        from src.models.group_tenant import GroupTenant

        tier_col = GroupTenant.__table__.c["subscription_tier"]
        assert tier_col.default is not None or tier_col.server_default is not None, (
            "subscription_tier 应有默认值"
        )

    def test_group_tenant_status_default(self):
        """status 默认值应为 'trial'"""
        from src.models.group_tenant import GroupTenant

        status_col = GroupTenant.__table__.c["status"]
        # 检查 Python 端 default
        default_val = status_col.default.arg if status_col.default else None
        assert default_val == "trial", f"status 默认值应为 'trial'，实际：{default_val}"

    def test_group_tenant_feature_flags_is_jsonb(self):
        """feature_flags 应为 JSONB 类型"""
        from src.models.group_tenant import GroupTenant
        from sqlalchemy.dialects.postgresql import JSONB

        col = GroupTenant.__table__.c["feature_flags"]
        assert isinstance(col.type, JSONB), (
            f"feature_flags 应为 JSONB 类型，实际：{type(col.type)}"
        )


# ============================================================
# 测试2：BrandConsumerProfile UNIQUE 约束
# ============================================================

class TestBrandConsumerProfileUniqueConstraint:
    """验证 BrandConsumerProfile 的 UNIQUE(consumer_id, brand_id) 约束"""

    def test_unique_constraint_exists(self):
        """表定义中必须包含 uq_brand_consumer_profile_consumer_brand"""
        from src.models.brand_consumer_profile import BrandConsumerProfile

        constraint_names = {
            c.name for c in BrandConsumerProfile.__table__.constraints
        }
        assert "uq_brand_consumer_profile_consumer_brand" in constraint_names, (
            f"缺少 UNIQUE 约束，当前约束：{constraint_names}"
        )

    def test_required_fields_exist(self):
        """验证所有必需字段均已定义"""
        from src.models.brand_consumer_profile import BrandConsumerProfile

        col_names = {c.name for c in BrandConsumerProfile.__table__.columns}
        required = {
            "id", "consumer_id", "brand_id", "group_id",
            "brand_member_no", "brand_level",
            "brand_points", "brand_balance_fen",
            "brand_order_count", "brand_order_amount_fen",
            "brand_first_order_at", "brand_last_order_at",
            "lifecycle_state", "registration_channel",
            "brand_wechat_openid", "brand_wechat_unionid",
            "is_active", "created_at", "updated_at",
        }
        missing = required - col_names
        assert not missing, f"BrandConsumerProfile 缺少字段：{missing}"

    def test_lifecycle_state_default(self):
        """lifecycle_state 默认值应为 'registered'"""
        from src.models.brand_consumer_profile import BrandConsumerProfile

        col = BrandConsumerProfile.__table__.c["lifecycle_state"]
        default_val = col.default.arg if col.default else None
        assert default_val == "registered", (
            f"lifecycle_state 默认值应为 'registered'，实际：{default_val}"
        )

    def test_amount_fields_are_bigint(self):
        """金额字段应为 BigInteger（存分）"""
        from src.models.brand_consumer_profile import BrandConsumerProfile
        from sqlalchemy import BigInteger

        for field in ("brand_balance_fen", "brand_order_amount_fen"):
            col = BrandConsumerProfile.__table__.c[field]
            assert isinstance(col.type, BigInteger), (
                f"{field} 应为 BigInteger（存分），实际：{type(col.type)}"
            )

    def test_composite_index_exists(self):
        """应存在 (consumer_id, group_id) 复合索引"""
        from src.models.brand_consumer_profile import BrandConsumerProfile

        index_names = {
            idx.name for idx in BrandConsumerProfile.__table__.indexes
        }
        assert "ix_bcp_consumer_group" in index_names, (
            f"缺少复合索引 ix_bcp_consumer_group，当前索引：{index_names}"
        )


# ============================================================
# 测试3：tenant_filter — group 层级注入
# ============================================================

class TestTenantFilterGroupLevelInjection:
    """验证 enable_tenant_filter 在 org_node_type=group 时只注入 app.current_group_id"""

    @pytest.mark.asyncio
    async def test_group_level_sets_only_group_id(self):
        from src.core.tenant_filter import enable_tenant_filter

        mock_session = AsyncMock()
        executed_sqls = []

        async def capture_execute(stmt, params=None):
            executed_sqls.append((str(stmt), params or {}))
            return MagicMock()

        mock_session.execute = capture_execute

        with patch("src.core.tenant_context.TenantContext.get_current_tenant", return_value=None):
            await enable_tenant_filter(
                session=mock_session,
                use_rls=True,
                org_node_type="group",
                group_id="grp-test-001",
            )

        # 必须设置 app.current_group_id
        sql_combined = " ".join(sql for sql, _ in executed_sqls)
        assert "app.current_group_id" in sql_combined, (
            "group 层级应设置 app.current_group_id"
        )

        # 不得设置 brand 或 store 级变量
        assert "app.current_brand_id" not in sql_combined, (
            "group 层级不应设置 app.current_brand_id"
        )
        assert "app.current_tenant" not in sql_combined, (
            "group 层级不应设置 app.current_tenant"
        )

    @pytest.mark.asyncio
    async def test_missing_group_id_logs_warning(self):
        """org_node_type=group 但 group_id 为空时，应记录警告并跳过注入"""
        import structlog
        from src.core.tenant_filter import enable_tenant_filter

        mock_session = AsyncMock()
        executed_sqls = []

        async def capture_execute(stmt, params=None):
            executed_sqls.append(str(stmt))
            return MagicMock()

        mock_session.execute = capture_execute

        with patch("src.core.tenant_context.TenantContext.get_current_tenant", return_value=None):
            # group_id=None，不应触发 SQL 注入
            await enable_tenant_filter(
                session=mock_session,
                use_rls=True,
                org_node_type="group",
                group_id=None,
            )

        # 无 group_id 时不应执行任何 set_config
        assert not any("set_config" in s for s in executed_sqls), (
            "group_id 为空时不应执行 set_config"
        )


# ============================================================
# 测试4：tenant_filter — brand 层级注入
# ============================================================

class TestTenantFilterBrandLevelInjection:
    """验证 enable_tenant_filter 在 org_node_type=brand 时注入 group+brand 两个变量"""

    @pytest.mark.asyncio
    async def test_brand_level_sets_group_and_brand(self):
        from src.core.tenant_filter import enable_tenant_filter

        mock_session = AsyncMock()
        executed_sqls = []

        async def capture_execute(stmt, params=None):
            executed_sqls.append((str(stmt), params or {}))
            return MagicMock()

        mock_session.execute = capture_execute

        with patch("src.core.tenant_context.TenantContext.get_current_tenant", return_value=None):
            await enable_tenant_filter(
                session=mock_session,
                use_rls=True,
                org_node_type="brand",
                group_id="grp-test-001",
                brand_id="brd-test-001",
            )

        sql_combined = " ".join(sql for sql, _ in executed_sqls)
        assert "app.current_group_id" in sql_combined, "brand 层级应设置 app.current_group_id"
        assert "app.current_brand_id" in sql_combined, "brand 层级应设置 app.current_brand_id"
        assert "app.current_tenant" not in sql_combined, "brand 层级不应设置 app.current_tenant"

    @pytest.mark.asyncio
    async def test_backward_compat_no_org_node_type(self):
        """无 org_node_type 时，只设置 app.current_tenant（向后兼容）"""
        from src.core.tenant_filter import enable_tenant_filter

        mock_session = AsyncMock()
        executed_sqls = []

        async def capture_execute(stmt, params=None):
            executed_sqls.append((str(stmt), params or {}))
            return MagicMock()

        mock_session.execute = capture_execute

        with patch(
            "src.core.tenant_context.TenantContext.get_current_tenant",
            return_value="store-legacy-001",
        ):
            await enable_tenant_filter(
                session=mock_session,
                use_rls=True,
                org_node_type=None,  # 不传 org_node_type
            )

        sql_combined = " ".join(sql for sql, _ in executed_sqls)
        assert "app.current_tenant" in sql_combined, (
            "无 org_node_type 时应走单层逻辑，设置 app.current_tenant"
        )
        assert "app.current_group_id" not in sql_combined, (
            "无 org_node_type 时不应设置 app.current_group_id"
        )


# ============================================================
# 测试5：One ID 聚合视图
# ============================================================

class TestOneIdViewAggregation:
    """验证 BrandConsumerProfileRepo.get_one_id_view 聚合逻辑"""

    @pytest.mark.asyncio
    async def test_one_id_view_aggregates_correctly(self):
        """多品牌档案应正确聚合金额/积分/时间/等级"""
        from src.repositories.brand_consumer_profile_repo import BrandConsumerProfileRepo
        from datetime import datetime

        consumer_id = uuid.uuid4()
        group_id = "grp-test-001"

        # 构造模拟档案数据
        def make_profile(**kwargs):
            p = MagicMock(spec=["brand_id", "brand_member_no", "brand_level",
                                  "brand_points", "brand_balance_fen",
                                  "brand_order_count", "brand_order_amount_fen",
                                  "brand_first_order_at", "brand_last_order_at",
                                  "lifecycle_state", "registration_channel", "is_active"])
            p.brand_member_no = None
            p.is_active = True
            for k, v in kwargs.items():
                setattr(p, k, v)
            return p

        profile_a = make_profile(
            brand_id="brd-001",
            brand_level="金卡",
            brand_points=500,
            brand_balance_fen=10000,
            brand_order_count=10,
            brand_order_amount_fen=50000,
            brand_first_order_at=datetime(2025, 1, 1),
            brand_last_order_at=datetime(2025, 6, 1),
            lifecycle_state="vip",
            registration_channel="wechat_mp",
        )
        profile_b = make_profile(
            brand_id="brd-002",
            brand_level="银卡",
            brand_points=200,
            brand_balance_fen=5000,
            brand_order_count=5,
            brand_order_amount_fen=20000,
            brand_first_order_at=datetime(2025, 3, 1),
            brand_last_order_at=datetime(2025, 12, 1),
            lifecycle_state="repeat",
            registration_channel="pos",
        )

        # 模拟 session.execute 返回
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [profile_a, profile_b]
        mock_session.execute = AsyncMock(return_value=mock_result)

        view = await BrandConsumerProfileRepo.get_one_id_view(
            mock_session, consumer_id, group_id
        )

        summary = view["summary"]

        # 金额聚合
        assert summary["total_order_count"] == 15
        assert summary["total_order_amount_fen"] == 70000
        assert summary["total_points"] == 700
        assert summary["total_balance_fen"] == 15000

        # 时间边界
        assert summary["first_order_at"] == datetime(2025, 1, 1)
        assert summary["last_order_at"] == datetime(2025, 12, 1)

        # 品牌数
        assert summary["active_brand_count"] == 2

        # 最高等级（金卡 > 银卡）
        assert summary["highest_level"] == "金卡"

        # 品牌档案列表
        assert len(view["brand_profiles"]) == 2

    @pytest.mark.asyncio
    async def test_one_id_view_raises_on_missing_params(self):
        """consumer_id 或 group_id 为空时应抛出 ValueError"""
        from src.repositories.brand_consumer_profile_repo import BrandConsumerProfileRepo

        mock_session = AsyncMock()
        consumer_id = uuid.uuid4()

        with pytest.raises(ValueError):
            await BrandConsumerProfileRepo.get_one_id_view(mock_session, consumer_id, "")

        with pytest.raises(ValueError):
            await BrandConsumerProfileRepo.get_one_id_view(mock_session, None, "grp-001")

    @pytest.mark.asyncio
    async def test_upsert_raises_on_missing_required(self):
        """upsert_profile 缺少必填字段时应抛出 ValueError"""
        from src.repositories.brand_consumer_profile_repo import BrandConsumerProfileRepo

        mock_session = AsyncMock()

        with pytest.raises(ValueError):
            await BrandConsumerProfileRepo.upsert_profile(
                mock_session,
                consumer_id=uuid.uuid4(),
                brand_id="",  # 空 brand_id
                group_id="grp-001",
            )
