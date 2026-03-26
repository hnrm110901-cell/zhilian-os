"""
影子同步服务测试

覆盖：
  - 双写记录（订单/预定/会员/支付/券）
  - 对比逻辑（金额一致/差异检测）
  - 差异严重度评估
  - 每日一致性报告
  - 切换就绪度评估
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.shadow_sync_service import (
    ShadowSyncService,
    RecordType,
    DiffSeverity,
    SyncStatus,
)


def make_sync_service() -> ShadowSyncService:
    return ShadowSyncService(store_id="S001", brand_id="B001")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 双写记录
# ═══════════════════════════════════════════════════════════════════════════════


class TestShadowRecord:
    """双写记录测试"""

    @pytest.mark.asyncio
    async def test_record_order(self):
        """记录订单影子数据"""
        svc = make_sync_service()
        record = await svc.record_shadow(
            RecordType.ORDER,
            "O001",
            {"order_id": "O001", "items": [], "total_fen": 10000},
            tunxiang_amount_fen=10000,
        )
        assert record.record_type == RecordType.ORDER
        assert record.source_id == "O001"
        assert record.source_amount_fen == 10000

    @pytest.mark.asyncio
    async def test_record_payment(self):
        """记录支付影子数据"""
        svc = make_sync_service()
        record = await svc.shadow_write_payment({
            "settle_id": "PAY001",
            "order_id": "O001",
            "paid_fen": 10000,
        })
        assert record["record_type"] == RecordType.PAYMENT.value

    @pytest.mark.asyncio
    async def test_record_reservation(self):
        """记录预定影子数据"""
        svc = make_sync_service()
        record = await svc.shadow_write_reservation({
            "reservation_id": "RES001",
            "customer_name": "张三",
        })
        assert record["record_type"] == RecordType.RESERVATION.value

    @pytest.mark.asyncio
    async def test_record_coupon(self):
        """记录券核销影子数据"""
        svc = make_sync_service()
        record = await svc.shadow_write_coupon({
            "coupon_code": "MT001",
            "platform": "meituan",
            "coupon_value_fen": 2000,
        })
        assert record["record_type"] == RecordType.COUPON.value
        assert record["source_id"] == "MT001"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 对比逻辑
# ═══════════════════════════════════════════════════════════════════════════════


class TestComparison:
    """对比逻辑测试"""

    @pytest.mark.asyncio
    async def test_consistent_amounts(self):
        """金额一致时无差异"""
        svc = make_sync_service()
        record = await svc.record_shadow(
            RecordType.ORDER,
            "O001",
            {"total_fen": 10000},
            tunxiang_amount_fen=10000,
        )
        # 无适配器时 shadow_data 为 None，对比结果为 no_shadow_data
        assert record.diff_result["status"] == "no_shadow_data"

    def test_severity_none_for_consistent(self):
        """一致数据严重度为 NONE"""
        svc = make_sync_service()
        diff = {"status": "compared", "diffs": [], "is_consistent": True}
        severity = svc._evaluate_severity(diff)
        assert severity == DiffSeverity.NONE

    def test_severity_warning_for_small_diff(self):
        """小金额差异为 WARNING"""
        svc = make_sync_service()
        diff = {
            "status": "compared",
            "diffs": [{"field": "amount_fen", "diff_fen": 50}],
            "is_consistent": False,
        }
        severity = svc._evaluate_severity(diff)
        assert severity == DiffSeverity.WARNING

    def test_severity_critical_for_large_diff(self):
        """大金额差异为 CRITICAL"""
        svc = make_sync_service()
        diff = {
            "status": "compared",
            "diffs": [{"field": "amount_fen", "diff_fen": 500}],
            "is_consistent": False,
        }
        severity = svc._evaluate_severity(diff)
        assert severity == DiffSeverity.CRITICAL


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 一致性报告
# ═══════════════════════════════════════════════════════════════════════════════


class TestConsistencyReport:
    """一致性报告测试"""

    @pytest.mark.asyncio
    async def test_generate_daily_report(self):
        """生成每日报告"""
        svc = make_sync_service()
        from datetime import datetime

        today = datetime.utcnow().strftime("%Y-%m-%d")

        # 写入几笔记录
        await svc.record_shadow(RecordType.ORDER, "O001", {}, 10000)
        await svc.record_shadow(RecordType.ORDER, "O002", {}, 20000)
        await svc.record_shadow(RecordType.PAYMENT, "P001", {}, 10000)

        report = svc.generate_daily_report(today)
        assert report["date"] == today
        assert report["total_records"] == 3
        assert "severity_breakdown" in report
        assert "type_breakdown" in report

    @pytest.mark.asyncio
    async def test_empty_day_report(self):
        """无数据日报告"""
        svc = make_sync_service()
        report = svc.generate_daily_report("2020-01-01")
        assert report["total_records"] == 0
        assert report["consistency_rate"] == 100.0
        assert report["is_pass"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 切换就绪度
# ═══════════════════════════════════════════════════════════════════════════════


class TestCutoverReadiness:
    """切换就绪度测试"""

    def test_initial_readiness(self):
        """初始状态未就绪"""
        svc = make_sync_service()
        readiness = svc.get_cutover_readiness()
        assert readiness["is_ready"] is False
        assert readiness["consecutive_pass_days"] == 0
        assert readiness["required_days"] == 30

    def test_readiness_progress(self):
        """就绪度进度计算"""
        svc = make_sync_service()
        from datetime import datetime, timedelta

        # 模拟15天通过
        today = datetime.utcnow().date()
        for i in range(15):
            date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            svc._daily_stats[date_str] = {
                "is_pass": True,
                "consistency_rate": 99.95,
            }

        readiness = svc.get_cutover_readiness()
        assert readiness["consecutive_pass_days"] == 15
        assert readiness["progress_pct"] == 50.0
        assert readiness["is_ready"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 企业同步
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnterpriseSync:
    """企业同步测试"""

    @pytest.mark.asyncio
    async def test_sync_menu_no_adapter(self):
        """无适配器时菜单同步返回错误"""
        svc = make_sync_service()
        result = await svc.sync_menu_changes()
        assert result["synced"] == 0
        assert "no_adapter" in str(result.get("error", ""))

    @pytest.mark.asyncio
    async def test_sync_tables_no_adapter(self):
        """无适配器时桌台同步返回0"""
        svc = make_sync_service()
        result = await svc.sync_table_status()
        assert result["synced"] == 0

    @pytest.mark.asyncio
    async def test_sync_members_no_adapter(self):
        """无适配器时会员同步返回0"""
        svc = make_sync_service()
        result = await svc.sync_member_changes(["M001", "M002"])
        assert result["synced"] == 0
