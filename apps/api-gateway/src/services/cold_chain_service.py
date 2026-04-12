"""
供应商冷链合规追踪服务
记录冷链运输温度数据，检测断链，评估供应商合规水平，
支持自动拒收判定和合规报告生成。

温度区间：
  FROZEN(-18°C以下) / CHILLED(0-4°C) / COOL(4-10°C) / AMBIENT(常温)

合规状态：
  PASS / WARNING / FAIL / REJECTED
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


class TemperatureZone(str, Enum):
    """温度区间"""
    FROZEN = "frozen"      # -18°C 以下
    CHILLED = "chilled"    # 0-4°C
    COOL = "cool"          # 4-10°C
    AMBIENT = "ambient"    # 常温 >10°C


class ComplianceStatus(str, Enum):
    """合规状态"""
    PASS = "pass"          # 完全合规
    WARNING = "warning"    # 有轻微偏差，可接受
    FAIL = "fail"          # 不合规
    REJECTED = "rejected"  # 自动拒收


# 每个温度区间的合规范围（最低温, 最高温）
_ZONE_TEMP_RANGES: Dict[TemperatureZone, Tuple[float, float]] = {
    TemperatureZone.FROZEN: (-40.0, -18.0),
    TemperatureZone.CHILLED: (0.0, 4.0),
    TemperatureZone.COOL: (4.0, 10.0),
    TemperatureZone.AMBIENT: (10.0, 35.0),
}

# 温度偏差容忍度（°C）— 超过合规范围但在容忍度内为 WARNING
_ZONE_TOLERANCE: Dict[TemperatureZone, float] = {
    TemperatureZone.FROZEN: 2.0,   # -18~-16°C 为 WARNING
    TemperatureZone.CHILLED: 1.0,  # 4~5°C 为 WARNING
    TemperatureZone.COOL: 2.0,     # 10~12°C 为 WARNING
    TemperatureZone.AMBIENT: 5.0,  # 35~40°C 为 WARNING
}

# 断链判定：连续超标读数达到此数量视为断链
_BREAK_THRESHOLD_COUNT = 3

# 自动拒收温度阈值（°C）：超过此温度直接拒收
_AUTO_REJECT_THRESHOLDS: Dict[TemperatureZone, float] = {
    TemperatureZone.FROZEN: -10.0,   # 冷冻品温度高于-10°C拒收
    TemperatureZone.CHILLED: 8.0,    # 冷藏品温度高于8°C拒收
    TemperatureZone.COOL: 15.0,      # 冷凉品温度高于15°C拒收
    TemperatureZone.AMBIENT: 45.0,   # 常温品温度高于45°C拒收
}


@dataclass
class ColdChainRecord:
    """冷链运输记录"""
    delivery_id: str
    supplier_id: str
    zone: str  # TemperatureZone value
    temperatures: List[float]  # 运输过程中的温度读数序列
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    compliance_status: str = ComplianceStatus.PASS.value
    break_detected: bool = False
    out_of_range_count: int = 0
    max_temp: float = 0.0
    min_temp: float = 0.0
    avg_temp: float = 0.0
    notes: str = ""


def _classify_single_temp(temp: float, zone: str) -> ComplianceStatus:
    """判断单个温度读数的合规状态"""
    z = TemperatureZone(zone)
    low, high = _ZONE_TEMP_RANGES[z]
    tolerance = _ZONE_TOLERANCE[z]

    if low <= temp <= high:
        return ComplianceStatus.PASS
    elif (low - tolerance) <= temp <= (high + tolerance):
        return ComplianceStatus.WARNING
    else:
        return ComplianceStatus.FAIL


def record_delivery_temperature(
    delivery_id: str,
    temps: List[float],
    zone: str,
    supplier_id: str = "",
) -> ColdChainRecord:
    """
    记录一次配送的温度数据并进行合规判定。

    Args:
        delivery_id: 配送单号
        temps: 温度读数列表（按时间顺序）
        zone: 要求的温度区间
        supplier_id: 供应商ID

    Returns:
        ColdChainRecord 包含合规判定结果
    """
    if not temps:
        logger.warning("record_delivery_empty_temps", delivery_id=delivery_id)
        return ColdChainRecord(
            delivery_id=delivery_id,
            supplier_id=supplier_id,
            zone=zone,
            temperatures=[],
            compliance_status=ComplianceStatus.FAIL.value,
            notes="无温度数据",
        )

    max_temp = max(temps)
    min_temp = min(temps)
    avg_temp = round(sum(temps) / len(temps), 2)

    # 逐点分类
    statuses = [_classify_single_temp(t, zone) for t in temps]

    fail_count = sum(1 for s in statuses if s == ComplianceStatus.FAIL)
    warn_count = sum(1 for s in statuses if s == ComplianceStatus.WARNING)
    out_of_range = fail_count + warn_count

    # 断链检测
    break_detected = check_cold_chain_break(temps, zone)

    # 自动拒收检测
    rejected = auto_reject_check(max_temp if zone != TemperatureZone.FROZEN.value else max_temp, zone)

    # 综合合规判定
    if rejected:
        overall_status = ComplianceStatus.REJECTED
    elif break_detected or fail_count > 0:
        overall_status = ComplianceStatus.FAIL
    elif warn_count > 0:
        overall_status = ComplianceStatus.WARNING
    else:
        overall_status = ComplianceStatus.PASS

    notes_parts = []
    if break_detected:
        notes_parts.append("检测到冷链断裂")
    if rejected:
        notes_parts.append("触发自动拒收")
    if fail_count > 0:
        notes_parts.append(f"{fail_count}个读数超标")
    if warn_count > 0:
        notes_parts.append(f"{warn_count}个读数偏差")

    record = ColdChainRecord(
        delivery_id=delivery_id,
        supplier_id=supplier_id,
        zone=zone,
        temperatures=temps,
        compliance_status=overall_status.value,
        break_detected=break_detected,
        out_of_range_count=out_of_range,
        max_temp=max_temp,
        min_temp=min_temp,
        avg_temp=avg_temp,
        notes="；".join(notes_parts) if notes_parts else "合规",
    )

    logger.info(
        "cold_chain_delivery_recorded",
        delivery_id=delivery_id,
        zone=zone,
        compliance=overall_status.value,
        avg_temp=avg_temp,
        break_detected=break_detected,
    )

    return record


def check_cold_chain_break(temps: List[float], zone: str) -> bool:
    """
    检测冷链是否断裂。

    断链定义：连续 ≥3 个温度读数超出合规范围（不含容忍区间）。

    Args:
        temps: 温度读数序列
        zone: 要求的温度区间

    Returns:
        True 表示检测到断链
    """
    if len(temps) < _BREAK_THRESHOLD_COUNT:
        return False

    z = TemperatureZone(zone)
    low, high = _ZONE_TEMP_RANGES[z]

    consecutive_fails = 0
    for temp in temps:
        if temp < low or temp > high:
            consecutive_fails += 1
            if consecutive_fails >= _BREAK_THRESHOLD_COUNT:
                return True
        else:
            consecutive_fails = 0

    return False


def evaluate_supplier_compliance(
    supplier_id: str,
    records: List[ColdChainRecord],
) -> Dict[str, Any]:
    """
    评估供应商冷链合规水平。

    Args:
        supplier_id: 供应商ID
        records: 该供应商的历史冷链记录列表

    Returns:
        合规评估报告：
        - supplier_id: 供应商ID
        - total_deliveries: 总配送次数
        - compliance_score: 合规评分（0-100）
        - pass_rate: 合格率（百分比）
        - risk_level: 风险等级（low/medium/high/critical）
        - breakdown: 各状态分布
        - recommendation: 建议
    """
    if not records:
        return {
            "supplier_id": supplier_id,
            "total_deliveries": 0,
            "compliance_score": 0,
            "pass_rate": 0.0,
            "risk_level": "unknown",
            "breakdown": {},
            "recommendation": "无历史记录，需首次验证",
        }

    total = len(records)

    # 各状态计数
    status_counts: Dict[str, int] = {
        ComplianceStatus.PASS.value: 0,
        ComplianceStatus.WARNING.value: 0,
        ComplianceStatus.FAIL.value: 0,
        ComplianceStatus.REJECTED.value: 0,
    }
    break_count = 0

    for r in records:
        status = r.compliance_status
        if status in status_counts:
            status_counts[status] += 1
        if r.break_detected:
            break_count += 1

    pass_count = status_counts[ComplianceStatus.PASS.value]
    warn_count = status_counts[ComplianceStatus.WARNING.value]
    fail_count = status_counts[ComplianceStatus.FAIL.value]
    reject_count = status_counts[ComplianceStatus.REJECTED.value]

    # 合规评分计算（满分100）
    # PASS=100分, WARNING=70分, FAIL=30分, REJECTED=0分
    score_sum = (pass_count * 100 + warn_count * 70 + fail_count * 30 + reject_count * 0)
    compliance_score = round(score_sum / total, 1)

    # 合格率（PASS + WARNING 视为合格）
    pass_rate = round((pass_count + warn_count) / total * 100, 1)

    # 风险等级
    if compliance_score >= 90:
        risk_level = "low"
    elif compliance_score >= 70:
        risk_level = "medium"
    elif compliance_score >= 50:
        risk_level = "high"
    else:
        risk_level = "critical"

    # 建议
    recommendations = []
    if reject_count > 0:
        recommendations.append(f"近期有{reject_count}次拒收记录，建议暂停合作并要求整改")
    if break_count > 0:
        recommendations.append(f"检测到{break_count}次冷链断裂，建议要求供应商升级运输设备")
    if fail_count > 0 and reject_count == 0:
        recommendations.append(f"{fail_count}次不合规配送，建议发出警告并加强抽检")
    if compliance_score >= 90:
        recommendations.append("合规表现优秀，建议维持当前合作")
    if not recommendations:
        recommendations.append("合规表现一般，建议持续监控")

    return {
        "supplier_id": supplier_id,
        "total_deliveries": total,
        "compliance_score": compliance_score,
        "pass_rate": pass_rate,
        "risk_level": risk_level,
        "break_count": break_count,
        "breakdown": status_counts,
        "recommendation": "；".join(recommendations),
    }


def auto_reject_check(delivery_temp: float, zone: str) -> bool:
    """
    判断是否应自动拒收。

    当配送温度超过对应区间的拒收阈值时，自动拒收。

    Args:
        delivery_temp: 配送到达时的温度（取最高温度）
        zone: 要求的温度区间

    Returns:
        True 表示应自动拒收
    """
    z = TemperatureZone(zone)
    threshold = _AUTO_REJECT_THRESHOLDS.get(z)

    if threshold is None:
        return False

    # 冷冻区间：温度高于阈值即拒收（越高越差）
    # 其他区间同理：温度高于阈值即拒收
    return delivery_temp > threshold


def generate_compliance_report(
    records: List[ColdChainRecord],
    period: str = "",
) -> Dict[str, Any]:
    """
    生成冷链合规报告。

    Args:
        records: 冷链记录列表（可跨供应商）
        period: 报告期间描述（如"2026年3月"）

    Returns:
        合规报告：
        - period: 报告期间
        - total_deliveries: 总配送次数
        - overall_compliance_rate: 整体合规率
        - by_supplier: 按供应商汇总
        - by_zone: 按温度区间汇总
        - critical_incidents: 严重事件列表
        - summary_text: 文字摘要
    """
    if not records:
        return {
            "period": period,
            "total_deliveries": 0,
            "overall_compliance_rate": 0.0,
            "by_supplier": {},
            "by_zone": {},
            "critical_incidents": [],
            "summary_text": f"{period}无配送记录",
        }

    total = len(records)

    # 整体合规率
    compliant = sum(
        1 for r in records
        if r.compliance_status in (ComplianceStatus.PASS.value, ComplianceStatus.WARNING.value)
    )
    overall_rate = round(compliant / total * 100, 1)

    # 按供应商分组
    supplier_records: Dict[str, List[ColdChainRecord]] = {}
    for r in records:
        sid = r.supplier_id or "unknown"
        if sid not in supplier_records:
            supplier_records[sid] = []
        supplier_records[sid].append(r)

    by_supplier = {}
    for sid, recs in supplier_records.items():
        by_supplier[sid] = evaluate_supplier_compliance(sid, recs)

    # 按温度区间分组
    zone_stats: Dict[str, Dict[str, int]] = {}
    for r in records:
        z = r.zone
        if z not in zone_stats:
            zone_stats[z] = {"total": 0, "pass": 0, "warning": 0, "fail": 0, "rejected": 0}
        zone_stats[z]["total"] += 1
        if r.compliance_status in zone_stats[z]:
            zone_stats[z][r.compliance_status] += 1

    # 严重事件（拒收 + 断链）
    critical_incidents = []
    for r in records:
        if r.compliance_status == ComplianceStatus.REJECTED.value or r.break_detected:
            critical_incidents.append({
                "delivery_id": r.delivery_id,
                "supplier_id": r.supplier_id,
                "zone": r.zone,
                "status": r.compliance_status,
                "break_detected": r.break_detected,
                "max_temp": r.max_temp,
                "min_temp": r.min_temp,
                "notes": r.notes,
                "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            })

    # 文字摘要
    reject_count = sum(1 for r in records if r.compliance_status == ComplianceStatus.REJECTED.value)
    break_count = sum(1 for r in records if r.break_detected)

    summary_parts = [
        f"{period}共{total}次配送",
        f"整体合规率{overall_rate}%",
    ]
    if reject_count > 0:
        summary_parts.append(f"{reject_count}次拒收")
    if break_count > 0:
        summary_parts.append(f"{break_count}次冷链断裂")
    if overall_rate >= 95:
        summary_parts.append("冷链管控表现优秀")
    elif overall_rate >= 80:
        summary_parts.append("冷链管控需加强")
    else:
        summary_parts.append("冷链管控存在严重问题，建议立即整改")

    return {
        "period": period,
        "total_deliveries": total,
        "overall_compliance_rate": overall_rate,
        "by_supplier": by_supplier,
        "by_zone": zone_stats,
        "critical_incidents": critical_incidents,
        "summary_text": "，".join(summary_parts),
    }
