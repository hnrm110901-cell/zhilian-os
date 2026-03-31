"""
Phase 3 测试套件 — 可配置标签工厂 + 集团BI大屏

覆盖：
- 标签规则条件评估（AND / OR / 各字段类型）
- 标签优先级逻辑
- 规则预览人数统计
- 集团总览聚合
- 会员生命周期漏斗分布
- 品牌对比时序数据格式
- 营销ROI计算（降级场景）

运行：
    cd apps/api-gateway && pytest tests/test_phase3_tag_bi.py -v
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.tag_factory_service import (
    ConditionValidationError,
    TagFactoryService,
    _eval_condition,
    _eval_rule,
    validate_conditions,
)
from src.services.group_bi_service import GroupBIService, _fen_to_yuan, _pct_change


# =========================================================================== #
# 辅助：构造虚拟 BrandConsumerProfile 字典
# =========================================================================== #

def _make_profile(
    brand_order_count: int = 5,
    brand_order_amount_fen: int = 100_000,
    days_since_last_order: int = 10,
    lifecycle_state: str = "repeat",
    brand_level: str = "金卡",
    brand_points: int = 500,
    cross_brand_count: int = 1,
    registration_channel: str = "wechat_mp",
) -> Dict[str, Any]:
    last_order_at = datetime.now(tz=timezone.utc) - timedelta(days=days_since_last_order)
    return {
        "brand_order_count": brand_order_count,
        "brand_order_amount_fen": brand_order_amount_fen,
        "brand_last_order_at": last_order_at,
        "lifecycle_state": lifecycle_state,
        "brand_level": brand_level,
        "brand_points": brand_points,
        "cross_brand_count": cross_brand_count,
        "registration_channel": registration_channel,
    }


# =========================================================================== #
# 步骤6-1：标签规则条件评估
# =========================================================================== #

class TestTagRuleAndConditionEvaluation:
    """test_tag_rule_and_condition_evaluation"""

    def test_int_gt_pass(self):
        profile = _make_profile(brand_order_count=10)
        cond = {"field": "brand_order_count", "op": "gt", "value": 5}
        assert _eval_condition(cond, profile) is True

    def test_int_gt_fail(self):
        profile = _make_profile(brand_order_count=3)
        cond = {"field": "brand_order_count", "op": "gt", "value": 5}
        assert _eval_condition(cond, profile) is False

    def test_int_gte_boundary(self):
        profile = _make_profile(brand_order_count=5)
        cond = {"field": "brand_order_count", "op": "gte", "value": 5}
        assert _eval_condition(cond, profile) is True

    def test_amount_lte(self):
        profile = _make_profile(brand_order_amount_fen=50_000)
        cond = {"field": "brand_order_amount_fen", "op": "lte", "value": 100_000}
        assert _eval_condition(cond, profile) is True

    def test_days_ago_within_pass(self):
        """最近7天内有消费"""
        profile = _make_profile(days_since_last_order=5)
        cond = {"field": "brand_last_order_at", "op": "within", "value": 7}
        assert _eval_condition(cond, profile) is True

    def test_days_ago_within_fail(self):
        """最近7天内无消费（超过7天）"""
        profile = _make_profile(days_since_last_order=15)
        cond = {"field": "brand_last_order_at", "op": "within", "value": 7}
        assert _eval_condition(cond, profile) is False

    def test_days_ago_not_within(self):
        """超过30天未消费 → 流失风险"""
        profile = _make_profile(days_since_last_order=45)
        cond = {"field": "brand_last_order_at", "op": "not_within", "value": 30}
        assert _eval_condition(cond, profile) is True

    def test_enum_lifecycle_in(self):
        profile = _make_profile(lifecycle_state="vip")
        cond = {"field": "lifecycle_state", "op": "in", "value": ["vip", "repeat"]}
        assert _eval_condition(cond, profile) is True

    def test_enum_lifecycle_not_in(self):
        profile = _make_profile(lifecycle_state="lost")
        cond = {"field": "lifecycle_state", "op": "not_in", "value": ["vip", "repeat"]}
        assert _eval_condition(cond, profile) is True

    def test_cross_brand_count_gte(self):
        profile = _make_profile(cross_brand_count=3)
        cond = {"field": "cross_brand_count", "op": "gte", "value": 2}
        assert _eval_condition(cond, profile) is True

    def test_and_logic_all_match(self):
        profile = _make_profile(brand_order_count=10, lifecycle_state="vip")
        conditions = [
            {"field": "brand_order_count", "op": "gte", "value": 5},
            {"field": "lifecycle_state", "op": "in", "value": ["vip"]},
        ]
        assert _eval_rule(conditions, "AND", profile) is True

    def test_and_logic_partial_fail(self):
        profile = _make_profile(brand_order_count=2, lifecycle_state="vip")
        conditions = [
            {"field": "brand_order_count", "op": "gte", "value": 5},
            {"field": "lifecycle_state", "op": "in", "value": ["vip"]},
        ]
        assert _eval_rule(conditions, "AND", profile) is False

    def test_or_logic_one_match(self):
        profile = _make_profile(brand_order_count=2, lifecycle_state="vip")
        conditions = [
            {"field": "brand_order_count", "op": "gte", "value": 5},  # 不满足
            {"field": "lifecycle_state", "op": "in", "value": ["vip"]},  # 满足
        ]
        assert _eval_rule(conditions, "OR", profile) is True

    def test_or_logic_none_match(self):
        profile = _make_profile(brand_order_count=1, lifecycle_state="registered")
        conditions = [
            {"field": "brand_order_count", "op": "gte", "value": 5},
            {"field": "lifecycle_state", "op": "in", "value": ["vip"]},
        ]
        assert _eval_rule(conditions, "OR", profile) is False

    def test_empty_conditions_returns_false(self):
        profile = _make_profile()
        assert _eval_rule([], "AND", profile) is False


# =========================================================================== #
# 步骤6-2：标签优先级覆盖
# =========================================================================== #

class TestTagRulePriorityOverride:
    """test_tag_rule_priority_override"""

    def test_high_priority_rule_evaluated_first(self):
        """高优先级规则应排在前面（已在 list_rules 中 ORDER BY priority DESC）"""
        rules = [
            {"priority": 200, "tag_code": "vip_gold", "conditions": [
                {"field": "brand_level", "op": "in", "value": ["金卡", "钻石"]}
            ], "logic": "AND"},
            {"priority": 100, "tag_code": "regular", "conditions": [
                {"field": "brand_order_count", "op": "gte", "value": 1}
            ], "logic": "AND"},
        ]
        profile = _make_profile(brand_level="金卡", brand_order_count=5)

        hit_tags = []
        for rule in rules:
            if _eval_rule(rule["conditions"], rule["logic"], profile):
                hit_tags.append(rule["tag_code"])

        # 两条规则都命中，高优先级 vip_gold 应在前
        assert hit_tags[0] == "vip_gold"
        assert "regular" in hit_tags

    def test_lower_priority_rule_still_evaluated(self):
        """低优先级规则不被跳过，只是在高优先级后面"""
        rules = [
            {"priority": 500, "tag_code": "high_value", "conditions": [
                {"field": "brand_order_amount_fen", "op": "gte", "value": 100_000}
            ], "logic": "AND"},
            {"priority": 50, "tag_code": "churning", "conditions": [
                {"field": "brand_last_order_at", "op": "not_within", "value": 60}
            ], "logic": "AND"},
        ]
        # 消费金额高但很久没来
        profile = _make_profile(brand_order_amount_fen=200_000, days_since_last_order=90)

        hit_tags = []
        for rule in rules:
            if _eval_rule(rule["conditions"], rule["logic"], profile):
                hit_tags.append(rule["tag_code"])

        assert "high_value" in hit_tags
        assert "churning" in hit_tags

    def test_invalid_field_raises_validation_error(self):
        """非法字段应被 validate_conditions 拒绝"""
        with pytest.raises(ConditionValidationError):
            validate_conditions([{"field": "hack_field; DROP TABLE", "op": "eq", "value": 1}])

    def test_invalid_op_raises_validation_error(self):
        """合法字段但非法操作符应被拒绝"""
        with pytest.raises(ConditionValidationError):
            validate_conditions([{"field": "brand_order_count", "op": "LIKE", "value": "%1%"}])

    def test_valid_conditions_pass(self):
        """合法条件不应抛出异常"""
        validate_conditions([
            {"field": "brand_order_count", "op": "gte", "value": 5},
            {"field": "lifecycle_state", "op": "in", "value": ["vip", "repeat"]},
        ])


# =========================================================================== #
# 步骤6-3：规则预览命中人数
# =========================================================================== #

class TestTagRulePreviewCount:
    """test_tag_rule_preview_count"""

    @pytest.mark.asyncio
    async def test_preview_returns_correct_hit_count(self):
        """预览应基于扫描的 profile 数据正确计数"""
        svc = TagFactoryService()

        # 构造虚拟 session，返回 5 条 profiles（3 条命中）
        mock_profiles = [
            _make_profile(brand_order_count=10),   # 命中 count >= 5
            _make_profile(brand_order_count=8),    # 命中
            _make_profile(brand_order_count=6),    # 命中
            _make_profile(brand_order_count=2),    # 不命中
            _make_profile(brand_order_count=1),    # 不命中
        ]

        mock_rows = []
        for p in mock_profiles:
            row = MagicMock()
            row._mapping = p
            mock_rows.append(row)

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter(mock_rows))

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        conditions = [{"field": "brand_order_count", "op": "gte", "value": 5}]
        result = await svc.preview_rule(
            conditions=conditions,
            logic="AND",
            brand_id="brand_test",
            group_id="group_test",
            limit=10,
            session=mock_session,
        )

        assert result["scanned_count"] == 5
        assert result["hit_count"] == 3
        assert result["hit_rate_pct"] == 60.0

    def test_preview_invalid_field_raises(self):
        """非法字段在校验阶段抛出，不进入 DB 查询"""
        svc = TagFactoryService()
        with pytest.raises(ConditionValidationError):
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                svc.preview_rule(
                    conditions=[{"field": "INVALID_FIELD", "op": "eq", "value": 1}],
                    logic="AND",
                    brand_id="b",
                    group_id="g",
                    session=AsyncMock(),
                )
            )


# =========================================================================== #
# 步骤6-4：集团总览聚合
# =========================================================================== #

class TestGroupOverviewAggregation:
    """test_group_overview_aggregation"""

    @pytest.mark.asyncio
    async def test_group_overview_structure(self):
        """总览接口应返回正确的数据结构和字段"""
        svc = GroupBIService()

        # 构造 mock session
        mock_session = AsyncMock()

        async def fake_execute(sql, params=None):
            mock_result = MagicMock()
            stmt_str = str(sql) if hasattr(sql, "__str__") else ""

            # 根据查询内容返回不同的 mock 数据
            if "gmv_fen" in stmt_str or "brand_order_amount_fen" in stmt_str:
                row1 = MagicMock()
                row1.brand_id = "brand_a"
                row1.gmv_fen = 1_000_000
                row1.member_count = 500
                mock_result.__iter__ = MagicMock(return_value=iter([row1]))
            elif "total_members" in stmt_str:
                row = MagicMock()
                row.total_members = 1000
                row.new_members_count = 50
                mock_result.first = MagicMock(return_value=row)
            elif "cross_count" in stmt_str:
                row = MagicMock()
                row.cross_count = 120
                mock_result.first = MagicMock(return_value=row)
            elif "repurchase_rate" in stmt_str:
                row = MagicMock()
                row.repurchase_rate = 0.35
                mock_result.first = MagicMock(return_value=row)
            elif "active_stores" in stmt_str:
                row = MagicMock()
                row.active_stores = 8
                mock_result.first = MagicMock(return_value=row)
            else:
                mock_result.__iter__ = MagicMock(return_value=iter([]))
                mock_result.first = MagicMock(return_value=None)

            return mock_result

        mock_session.execute = fake_execute

        start_dt = datetime(2026, 3, 1)
        end_dt = datetime(2026, 3, 30)

        result = await svc.get_group_overview(
            group_id="group_test",
            date_range=(start_dt, end_dt),
            session=mock_session,
        )

        # 验证必要字段存在
        assert "total_gmv_fen" in result
        assert "total_gmv_yuan" in result
        assert "gmv_by_brand" in result
        assert "total_members" in result
        assert "new_members_count" in result
        assert "cross_brand_consumers" in result
        assert "overall_repurchase_rate_pct" in result
        assert "active_stores" in result

        # 验证金额字段双重返回
        assert result["total_gmv_yuan"].startswith("¥")

    def test_fen_to_yuan_conversion(self):
        assert _fen_to_yuan(100_000) == "¥1,000.00"
        assert _fen_to_yuan(0) == "¥0.00"
        assert _fen_to_yuan(None) == "¥0.00"

    def test_pct_change_normal(self):
        assert _pct_change(110, 100) == 10.0

    def test_pct_change_zero_division(self):
        assert _pct_change(100, 0) is None


# =========================================================================== #
# 步骤6-5：会员生命周期漏斗
# =========================================================================== #

class TestMemberFunnelLifecycleDistribution:
    """test_member_funnel_lifecycle_distribution"""

    @pytest.mark.asyncio
    async def test_funnel_returns_all_stages(self):
        """漏斗应返回所有 7 个生命周期阶段"""
        svc = GroupBIService()
        mock_session = AsyncMock()

        mock_rows = [
            MagicMock(lifecycle_state="lead",       cnt=100),
            MagicMock(lifecycle_state="registered", cnt=800),
            MagicMock(lifecycle_state="repeat",     cnt=500),
            MagicMock(lifecycle_state="vip",        cnt=200),
            MagicMock(lifecycle_state="at_risk",    cnt=150),
            MagicMock(lifecycle_state="dormant",    cnt=80),
            MagicMock(lifecycle_state="lost",       cnt=50),
        ]
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter(mock_rows))
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await svc.get_member_funnel(
            brand_id="brand_test", group_id="group_test", session=mock_session
        )

        assert "funnel" in result
        assert "conversion_rates" in result
        assert "total_members" in result

        stage_names = [f["stage"] for f in result["funnel"]]
        expected_stages = ["lead", "registered", "repeat", "vip", "at_risk", "dormant", "lost"]
        assert stage_names == expected_stages

        # 验证转化率数量
        assert len(result["conversion_rates"]) == len(expected_stages) - 1

    @pytest.mark.asyncio
    async def test_funnel_conversion_rate_calculation(self):
        """registered→repeat 转化率应正确计算"""
        svc = GroupBIService()
        mock_session = AsyncMock()

        mock_rows = [
            MagicMock(lifecycle_state="lead",       cnt=0),
            MagicMock(lifecycle_state="registered", cnt=1000),
            MagicMock(lifecycle_state="repeat",     cnt=400),
            MagicMock(lifecycle_state="vip",        cnt=0),
            MagicMock(lifecycle_state="at_risk",    cnt=0),
            MagicMock(lifecycle_state="dormant",    cnt=0),
            MagicMock(lifecycle_state="lost",       cnt=0),
        ]
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter(mock_rows))
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await svc.get_member_funnel(
            brand_id="brand_test", group_id="group_test", session=mock_session
        )

        reg_to_repeat = next(
            (r for r in result["conversion_rates"]
             if r["from"] == "registered" and r["to"] == "repeat"),
            None,
        )
        assert reg_to_repeat is not None
        assert reg_to_repeat["conversion_rate_pct"] == 40.0


# =========================================================================== #
# 步骤6-6：品牌对比时序数据
# =========================================================================== #

class TestBrandComparisonReturnsTimeseries:
    """test_brand_comparison_returns_timeseries"""

    @pytest.mark.asyncio
    async def test_gmv_comparison_structure(self):
        """GMV 对比应返回正确的时序结构"""
        svc = GroupBIService()
        mock_session = AsyncMock()

        mock_rows = [
            MagicMock(date_label=datetime(2026, 3, 1), brand_id="brand_a", value_fen=500_000),
            MagicMock(date_label=datetime(2026, 3, 1), brand_id="brand_b", value_fen=300_000),
            MagicMock(date_label=datetime(2026, 3, 2), brand_id="brand_a", value_fen=600_000),
        ]
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter(mock_rows))
        mock_session.execute = AsyncMock(return_value=mock_result)

        data = await svc.get_brand_comparison(
            group_id="group_test",
            brand_ids=["brand_a", "brand_b"],
            metric="gmv",
            period="daily",
            session=mock_session,
        )

        assert isinstance(data, list)
        assert len(data) == 3
        for item in data:
            assert "date_label" in item
            assert "brand_id" in item
            assert "value_fen" in item
            assert "value_yuan" in item
            assert item["value_yuan"].startswith("¥")

    def test_invalid_metric_raises(self):
        """非法 metric 应抛出 ValueError"""
        svc = GroupBIService()
        import asyncio
        with pytest.raises(ValueError):
            asyncio.get_event_loop().run_until_complete(
                svc.get_brand_comparison(
                    group_id="g",
                    brand_ids=["b"],
                    metric="INVALID_METRIC",
                    period="daily",
                    session=AsyncMock(),
                )
            )

    def test_invalid_period_raises(self):
        """非法 period 应抛出 ValueError"""
        svc = GroupBIService()
        import asyncio
        with pytest.raises(ValueError):
            asyncio.get_event_loop().run_until_complete(
                svc.get_brand_comparison(
                    group_id="g",
                    brand_ids=["b"],
                    metric="gmv",
                    period="QUARTERLY",  # 非法
                    session=AsyncMock(),
                )
            )


# =========================================================================== #
# 步骤6-7：营销ROI计算
# =========================================================================== #

class TestMarketingRoiCalculation:
    """test_marketing_roi_calculation"""

    @pytest.mark.asyncio
    async def test_roi_calculation_correct(self):
        """ROI = GMV / Cost，应正确计算"""
        svc = GroupBIService()
        mock_session = AsyncMock()

        # 模拟有数据的场景
        mock_rows = [
            MagicMock(
                channel="sms",
                sent_count=1000,
                delivered_count=950,
                converted_count=100,
                gmv_fen=500_000,
                cost_fen=50_000,
            ),
            MagicMock(
                channel="wecom",
                sent_count=500,
                delivered_count=480,
                converted_count=80,
                gmv_fen=400_000,
                cost_fen=20_000,
            ),
        ]
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter(mock_rows))
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await svc.get_marketing_roi(
            brand_id="brand_test",
            group_id="group_test",
            period_days=30,
            session=mock_session,
        )

        assert "channels" in result
        assert "total_gmv_fen" in result
        assert "total_gmv_yuan" in result
        assert "overall_roi" in result

        sms_data = next((c for c in result["channels"] if c["channel"] == "sms"), None)
        assert sms_data is not None
        assert sms_data["roi"] == 10.0  # 500_000 / 50_000
        assert sms_data["delivery_rate_pct"] == 95.0
        assert sms_data["conversion_rate_pct"] == round(100 / 950 * 100, 2)
        assert sms_data["gmv_yuan"] == "¥5,000.00"
        assert sms_data["cost_yuan"] == "¥500.00"

    @pytest.mark.asyncio
    async def test_roi_graceful_degradation(self):
        """数据库无营销表时应降级返回空骨架，不抛异常"""
        svc = GroupBIService()
        mock_session = AsyncMock()

        # 模拟 marketing_campaigns 表不存在
        from sqlalchemy.exc import ProgrammingError
        mock_session.execute = AsyncMock(
            side_effect=ProgrammingError("relation not found", {}, None)
        )

        result = await svc.get_marketing_roi(
            brand_id="brand_test",
            group_id="group_test",
            period_days=30,
            session=mock_session,
        )

        # 降级应返回空骨架，不抛异常
        assert result["channels"] == []
        assert result["total_gmv_fen"] == 0
        assert "note" in result

    def test_fen_yuan_both_present_in_roi(self):
        """金额字段必须同时包含 _fen 和 _yuan"""
        # 这是通过 service 的 _fen_to_yuan 辅助函数保证的
        assert _fen_to_yuan(500_000) == "¥5,000.00"
        assert _fen_to_yuan(50_000) == "¥500.00"
