"""
供应商冷链合规追踪服务测试
覆盖温度记录、断链检测、合规评估、自动拒收、合规报告
"""

import pytest
from datetime import datetime, timezone

from src.services.cold_chain_service import (
    TemperatureZone,
    ComplianceStatus,
    ColdChainRecord,
    record_delivery_temperature,
    check_cold_chain_break,
    evaluate_supplier_compliance,
    auto_reject_check,
    generate_compliance_report,
    _classify_single_temp,
)


NOW = datetime(2026, 3, 26, 12, 0, 0, tzinfo=timezone.utc)


def _make_record(
    delivery_id: str = "D001",
    supplier_id: str = "SUP001",
    zone: str = TemperatureZone.CHILLED.value,
    status: str = ComplianceStatus.PASS.value,
    break_detected: bool = False,
    temps: list = None,
) -> ColdChainRecord:
    """构造测试用冷链记录"""
    return ColdChainRecord(
        delivery_id=delivery_id,
        supplier_id=supplier_id,
        zone=zone,
        temperatures=temps or [2.0, 2.5, 3.0],
        recorded_at=NOW,
        compliance_status=status,
        break_detected=break_detected,
        max_temp=max(temps) if temps else 3.0,
        min_temp=min(temps) if temps else 2.0,
        avg_temp=sum(temps) / len(temps) if temps else 2.5,
    )


# ──────────────────── record_delivery_temperature 测试 ────────────────────

class TestRecordDeliveryTemperature:
    """配送温度记录与合规判定"""

    def test_all_temps_in_range_passes(self):
        """所有温度在合规范围内 → PASS"""
        record = record_delivery_temperature("D001", [1.0, 2.0, 3.0, 2.5], "chilled", "SUP001")
        assert record.compliance_status == ComplianceStatus.PASS.value
        assert record.break_detected is False
        assert record.avg_temp == 2.12  # (1+2+3+2.5)/4 四舍五入

    def test_temps_in_tolerance_warns(self):
        """温度在容忍区间内 → WARNING"""
        # CHILLED 范围 0-4°C，容忍 +1°C，所以 4.5 是 WARNING
        record = record_delivery_temperature("D002", [2.0, 3.0, 4.5, 3.0], "chilled", "SUP001")
        assert record.compliance_status == ComplianceStatus.WARNING.value

    def test_temps_out_of_range_fails(self):
        """温度超出容忍范围 → FAIL"""
        # CHILLED 容忍到 5°C，7°C 明显超标
        record = record_delivery_temperature("D003", [2.0, 3.0, 7.0, 3.0], "chilled", "SUP001")
        assert record.compliance_status == ComplianceStatus.FAIL.value

    def test_frozen_zone_all_compliant(self):
        """冷冻区间全部合规"""
        record = record_delivery_temperature("D004", [-20.0, -22.0, -19.0], "frozen", "SUP001")
        assert record.compliance_status == ComplianceStatus.PASS.value

    def test_empty_temps_fails(self):
        """空温度列表 → FAIL"""
        record = record_delivery_temperature("D005", [], "chilled", "SUP001")
        assert record.compliance_status == ComplianceStatus.FAIL.value
        assert "无温度数据" in record.notes

    def test_auto_reject_triggered(self):
        """温度超过拒收阈值 → REJECTED"""
        # CHILLED 拒收阈值 8°C
        record = record_delivery_temperature("D006", [2.0, 3.0, 9.0], "chilled", "SUP001")
        assert record.compliance_status == ComplianceStatus.REJECTED.value
        assert "自动拒收" in record.notes


# ──────────────────── check_cold_chain_break 测试 ────────────────────

class TestCheckColdChainBreak:
    """断链检测测试"""

    def test_no_break_all_in_range(self):
        """所有温度在范围内 → 无断链"""
        assert check_cold_chain_break([1.0, 2.0, 3.0, 2.5], "chilled") is False

    def test_break_detected_3_consecutive_fails(self):
        """连续3个超标 → 断链"""
        # CHILLED 范围 0-4°C，7°C 超标
        assert check_cold_chain_break([2.0, 7.0, 7.0, 7.0, 2.0], "chilled") is True

    def test_no_break_with_2_consecutive_fails(self):
        """连续2个超标不算断链"""
        assert check_cold_chain_break([2.0, 7.0, 7.0, 2.0], "chilled") is False

    def test_no_break_non_consecutive_fails(self):
        """非连续超标不算断链"""
        assert check_cold_chain_break([7.0, 2.0, 7.0, 2.0, 7.0], "chilled") is False

    def test_too_few_readings_no_break(self):
        """读数不足3个 → 不判定断链"""
        assert check_cold_chain_break([7.0, 7.0], "chilled") is False

    def test_frozen_break_detection(self):
        """冷冻区间断链检测（温度高于-18°C超标）"""
        assert check_cold_chain_break([-20.0, -10.0, -10.0, -10.0], "frozen") is True


# ──────────────────── auto_reject_check 测试 ────────────────────

class TestAutoRejectCheck:
    """自动拒收判定测试"""

    def test_frozen_above_threshold_rejected(self):
        """冷冻品温度 > -10°C → 拒收"""
        assert auto_reject_check(-5.0, "frozen") is True

    def test_frozen_below_threshold_accepted(self):
        """冷冻品温度 < -10°C → 接受"""
        assert auto_reject_check(-15.0, "frozen") is False

    def test_chilled_above_threshold_rejected(self):
        """冷藏品温度 > 8°C → 拒收"""
        assert auto_reject_check(9.0, "chilled") is True

    def test_chilled_below_threshold_accepted(self):
        """冷藏品温度 ≤ 8°C → 接受"""
        assert auto_reject_check(5.0, "chilled") is False


# ──────────────────── evaluate_supplier_compliance 测试 ────────────────────

class TestEvaluateSupplierCompliance:
    """供应商合规评估测试"""

    def test_all_pass_high_score(self):
        """全部合格 → 评分100，risk low"""
        records = [_make_record(status=ComplianceStatus.PASS.value) for _ in range(10)]
        result = evaluate_supplier_compliance("SUP001", records)
        assert result["compliance_score"] == 100.0
        assert result["risk_level"] == "low"
        assert result["pass_rate"] == 100.0

    def test_mixed_results_medium_risk(self):
        """混合结果 → 中等风险"""
        records = [
            _make_record(status=ComplianceStatus.PASS.value),
            _make_record(status=ComplianceStatus.PASS.value),
            _make_record(status=ComplianceStatus.WARNING.value),
            _make_record(status=ComplianceStatus.FAIL.value),
        ]
        result = evaluate_supplier_compliance("SUP001", records)
        # (100+100+70+30)/4 = 75
        assert result["compliance_score"] == 75.0
        assert result["risk_level"] == "medium"

    def test_empty_records_returns_unknown(self):
        """无记录 → 评分0，risk unknown"""
        result = evaluate_supplier_compliance("SUP001", [])
        assert result["compliance_score"] == 0
        assert result["risk_level"] == "unknown"

    def test_rejected_records_critical_risk(self):
        """有拒收记录 → critical risk"""
        records = [
            _make_record(status=ComplianceStatus.REJECTED.value),
            _make_record(status=ComplianceStatus.REJECTED.value),
            _make_record(status=ComplianceStatus.FAIL.value),
        ]
        result = evaluate_supplier_compliance("SUP001", records)
        # (0+0+30)/3 = 10
        assert result["compliance_score"] == 10.0
        assert result["risk_level"] == "critical"
        assert "拒收" in result["recommendation"]


# ──────────────────── generate_compliance_report 测试 ────────────────────

class TestGenerateComplianceReport:
    """合规报告生成测试"""

    def test_report_with_records(self):
        """有记录时生成完整报告"""
        records = [
            _make_record(delivery_id="D001", supplier_id="SUP001", status=ComplianceStatus.PASS.value),
            _make_record(delivery_id="D002", supplier_id="SUP001", status=ComplianceStatus.WARNING.value),
            _make_record(delivery_id="D003", supplier_id="SUP002", status=ComplianceStatus.FAIL.value),
        ]
        report = generate_compliance_report(records, "2026年3月")
        assert report["total_deliveries"] == 3
        assert report["overall_compliance_rate"] == 66.7  # 2/3
        assert "SUP001" in report["by_supplier"]
        assert "SUP002" in report["by_supplier"]
        assert "2026年3月" in report["summary_text"]

    def test_empty_report(self):
        """空记录返回有效结构"""
        report = generate_compliance_report([], "2026年3月")
        assert report["total_deliveries"] == 0
        assert report["overall_compliance_rate"] == 0.0

    def test_critical_incidents_captured(self):
        """严重事件（拒收/断链）被捕获"""
        records = [
            _make_record(delivery_id="D001", status=ComplianceStatus.REJECTED.value),
            _make_record(delivery_id="D002", status=ComplianceStatus.PASS.value, break_detected=True),
        ]
        report = generate_compliance_report(records, "2026年3月")
        assert len(report["critical_incidents"]) == 2


# ──────────────────── 内部函数测试 ────────────────────

class TestInternalHelpers:
    """内部辅助函数测试"""

    def test_classify_chilled_in_range(self):
        assert _classify_single_temp(2.0, "chilled") == ComplianceStatus.PASS

    def test_classify_chilled_in_tolerance(self):
        assert _classify_single_temp(4.5, "chilled") == ComplianceStatus.WARNING

    def test_classify_chilled_out_of_range(self):
        assert _classify_single_temp(7.0, "chilled") == ComplianceStatus.FAIL
