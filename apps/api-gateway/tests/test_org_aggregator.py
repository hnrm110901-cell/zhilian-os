import pytest
from src.services.org_aggregator import OrgAggregator, OrgSnapshot


def test_org_snapshot_structure():
    snap = OrgSnapshot(
        node_id="reg-south",
        node_name="华南区",
        node_type="region",
        period="2026-03",
        revenue_total_fen=10_000_000,    # 10万元
        revenue_target_fen=12_000_000,
        cost_ratio=0.34,
        headcount=45,
        kpi_score=88.5,
        store_count=2,
    )
    assert snap.revenue_achievement_rate == pytest.approx(10_000_000 / 12_000_000)
    assert snap.revenue_total_yuan == pytest.approx(100_000.0)


@pytest.mark.skip(reason="需要数据库，集成测试阶段")
async def test_aggregate_region():
    """集成测试占位符 — 聚合华南区数据"""
    pass
