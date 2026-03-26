"""
海鲜新鲜度分级服务
根据到货时间、品类和存储方式，自动计算海鲜新鲜度等级，
提供折扣建议和下架判定。

等级体系：
  A(极鲜,0-6h) / B(新鲜,6-24h) / C(良好,24-48h) / D(临期,48-72h) / E(过期,>72h)

品类衰减速率：活鲜(最快) > 冰鲜 > 冷冻(最慢)
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


class FreshnessGrade(str, Enum):
    """新鲜度等级"""
    A = "A"  # 极鲜 0-6h（基准时间，按品类衰减系数调整）
    B = "B"  # 新鲜 6-24h
    C = "C"  # 良好 24-48h
    D = "D"  # 临期 48-72h
    E = "E"  # 过期 >72h


class SeafoodCategory(str, Enum):
    """海鲜品类"""
    LIVE = "live"        # 活鲜（衰减最快）
    CHILLED = "chilled"  # 冰鲜
    FROZEN = "frozen"    # 冷冻（衰减最慢）


class StorageType(str, Enum):
    """存储方式"""
    AMBIENT = "ambient"      # 常温
    CHILLED = "chilled"      # 冷藏 0-4°C
    FROZEN = "frozen"        # 冷冻 -18°C以下
    WATER_TANK = "water_tank"  # 水箱（活鲜专用）


# 品类衰减系数：系数越大，同等时间内衰减越快（等级阈值缩短）
# 例如活鲜系数2.0意味着基准6h的A级阈值变为3h
CATEGORY_DECAY_RATES: Dict[str, float] = {
    SeafoodCategory.LIVE: 2.0,     # 活鲜衰减最快
    SeafoodCategory.CHILLED: 1.0,  # 冰鲜为基准
    SeafoodCategory.FROZEN: 0.3,   # 冷冻衰减最慢
}

# 存储方式的衰减修正系数：合适的存储方式可减缓衰减
# 系数越小，保鲜效果越好
STORAGE_MODIFIERS: Dict[str, Dict[str, float]] = {
    SeafoodCategory.LIVE: {
        StorageType.WATER_TANK: 0.5,   # 活鲜在水箱中衰减减半
        StorageType.CHILLED: 0.8,
        StorageType.FROZEN: 1.5,       # 活鲜不宜冷冻，加速劣化
        StorageType.AMBIENT: 1.0,
    },
    SeafoodCategory.CHILLED: {
        StorageType.CHILLED: 0.6,      # 冰鲜在冷藏中保鲜效果好
        StorageType.FROZEN: 0.4,
        StorageType.WATER_TANK: 1.2,
        StorageType.AMBIENT: 1.5,      # 常温加速衰减
    },
    SeafoodCategory.FROZEN: {
        StorageType.FROZEN: 0.5,       # 冷冻品在冷冻柜保鲜最佳
        StorageType.CHILLED: 1.0,
        StorageType.WATER_TANK: 2.0,
        StorageType.AMBIENT: 2.5,      # 常温下冷冻品快速劣化
    },
}

# 基准等级阈值（小时），品类衰减系数=1.0时的标准
_BASE_THRESHOLDS: List[Tuple[FreshnessGrade, float]] = [
    (FreshnessGrade.A, 6.0),
    (FreshnessGrade.B, 24.0),
    (FreshnessGrade.C, 48.0),
    (FreshnessGrade.D, 72.0),
    # >72h 为 E 级
]

# 折扣建议（按等级），折扣比例为原价的百分比
_DISCOUNT_CONFIG: Dict[FreshnessGrade, Optional[int]] = {
    FreshnessGrade.A: None,   # 不打折
    FreshnessGrade.B: None,   # 不打折
    FreshnessGrade.C: 90,     # 9折
    FreshnessGrade.D: 70,     # 7折
    FreshnessGrade.E: None,   # 应下架，不售卖
}


def _get_effective_decay_rate(
    category: str,
    storage_type: str,
) -> float:
    """计算有效衰减速率（品类衰减 × 存储修正）"""
    cat = category if isinstance(category, str) else category.value
    stor = storage_type if isinstance(storage_type, str) else storage_type.value

    base_rate = CATEGORY_DECAY_RATES.get(cat, 1.0)
    modifier = STORAGE_MODIFIERS.get(cat, {}).get(stor, 1.0)
    return base_rate * modifier


def _elapsed_hours(arrival_time: datetime, now: Optional[datetime] = None) -> float:
    """计算从到货至今经过的小时数"""
    if now is None:
        now = datetime.now(timezone.utc)

    # 统一时区处理：如果 arrival_time 无时区信息，视为 UTC
    if arrival_time.tzinfo is None:
        arrival_time = arrival_time.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    delta = now - arrival_time
    elapsed = delta.total_seconds() / 3600.0
    return max(0.0, elapsed)


def calculate_grade(
    arrival_time: datetime,
    category: str,
    storage_type: str,
    now: Optional[datetime] = None,
) -> FreshnessGrade:
    """
    根据到货时间、品类和存储方式计算当前新鲜度等级。

    Args:
        arrival_time: 到货时间
        category: 海鲜品类（live/chilled/frozen）
        storage_type: 存储方式（ambient/chilled/frozen/water_tank）
        now: 当前时间，默认为 UTC now（方便测试注入）

    Returns:
        FreshnessGrade 枚举值
    """
    elapsed = _elapsed_hours(arrival_time, now)
    decay_rate = _get_effective_decay_rate(category, storage_type)

    # 有效经过时间 = 实际时间 × 衰减速率
    effective_hours = elapsed * decay_rate

    for grade, threshold in _BASE_THRESHOLDS:
        if effective_hours <= threshold:
            return grade

    return FreshnessGrade.E


def get_remaining_hours(
    arrival_time: datetime,
    category: str,
    storage_type: str,
    target_grade: Optional[FreshnessGrade] = None,
    now: Optional[datetime] = None,
) -> float:
    """
    计算距离降级还剩多少小时。

    如果未指定 target_grade，默认计算距离当前等级到期的剩余时间。
    如果已经是E级，返回0.0。

    Args:
        arrival_time: 到货时间
        category: 海鲜品类
        storage_type: 存储方式
        target_grade: 目标等级（默认为当前等级）
        now: 当前时间

    Returns:
        剩余小时数（保留2位小数），已过期返回0.0
    """
    elapsed = _elapsed_hours(arrival_time, now)
    decay_rate = _get_effective_decay_rate(category, storage_type)
    effective_hours = elapsed * decay_rate

    current_grade = calculate_grade(arrival_time, category, storage_type, now)

    if current_grade == FreshnessGrade.E:
        return 0.0

    # 找到当前等级的阈值上限
    if target_grade is None:
        target_grade = current_grade

    threshold = None
    for grade, t in _BASE_THRESHOLDS:
        if grade == target_grade:
            threshold = t
            break

    if threshold is None:
        return 0.0

    # 剩余有效时间 / 衰减速率 = 剩余实际时间
    remaining_effective = threshold - effective_hours
    if remaining_effective <= 0:
        return 0.0

    if decay_rate <= 0:
        return 0.0

    return round(remaining_effective / decay_rate, 2)


def should_discount(grade: FreshnessGrade) -> Tuple[bool, Optional[int]]:
    """
    判断是否应该打折，以及建议折扣比例。

    Args:
        grade: 当前新鲜度等级

    Returns:
        (是否打折, 折扣比例百分比)
        例如 (True, 70) 表示建议打7折
        E级返回 (False, None) 因为应下架而非打折
    """
    discount = _DISCOUNT_CONFIG.get(grade)
    if grade == FreshnessGrade.E:
        return False, None
    if discount is not None:
        return True, discount
    return False, None


def should_remove(grade: FreshnessGrade) -> bool:
    """
    判断是否应该下架。

    E级（过期）必须下架，D级（临期）建议重点关注但不强制下架。

    Args:
        grade: 当前新鲜度等级

    Returns:
        True 表示应立即下架
    """
    return grade == FreshnessGrade.E


def batch_grade_check(
    items: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    批量检查多个海鲜品的新鲜度。

    每个 item 需包含：
        - item_id: str 品项标识
        - arrival_time: datetime 到货时间
        - category: str 品类
        - storage_type: str 存储方式
        - unit_price_fen: int 单价（分）（可选，用于计算折扣后价格）

    Args:
        items: 品项列表
        now: 当前时间

    Returns:
        检查结果列表，每项包含：
        - item_id, grade, remaining_hours, should_discount, discount_pct,
          should_remove, discounted_price_fen（如有原价）
    """
    results = []
    for item in items:
        try:
            arrival_time = item["arrival_time"]
            category = item["category"]
            storage_type = item["storage_type"]
            item_id = item.get("item_id", "unknown")

            grade = calculate_grade(arrival_time, category, storage_type, now)
            remaining = get_remaining_hours(arrival_time, category, storage_type, now=now)
            disc, disc_pct = should_discount(grade)
            remove = should_remove(grade)

            result: Dict[str, Any] = {
                "item_id": item_id,
                "grade": grade.value,
                "remaining_hours": remaining,
                "should_discount": disc,
                "discount_pct": disc_pct,
                "should_remove": remove,
            }

            # 如果有单价，计算折后价（金额单位：分 fen）
            unit_price_fen = item.get("unit_price_fen")
            if unit_price_fen is not None and disc_pct is not None:
                result["discounted_price_fen"] = int(unit_price_fen * disc_pct / 100)

            results.append(result)

        except (KeyError, TypeError) as e:
            logger.warning(
                "batch_grade_check_item_error",
                item_id=item.get("item_id", "unknown"),
                error=str(e),
            )
            results.append({
                "item_id": item.get("item_id", "unknown"),
                "error": f"检查失败: {str(e)}",
            })

    return results


def get_freshness_dashboard(
    items: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    生成新鲜度看板数据：按等级分组统计。

    Args:
        items: 同 batch_grade_check 的输入格式
        now: 当前时间

    Returns:
        看板数据：
        - total: 总数
        - by_grade: 按等级分组 { "A": { count, items }, ... }
        - alerts: 需关注的告警列表（D级和E级）
        - summary: 摘要统计
    """
    graded = batch_grade_check(items, now)

    by_grade: Dict[str, Dict[str, Any]] = {}
    for g in FreshnessGrade:
        by_grade[g.value] = {"count": 0, "items": []}

    alerts: List[Dict[str, Any]] = []
    error_count = 0

    for result in graded:
        if "error" in result:
            error_count += 1
            continue

        grade_val = result["grade"]
        by_grade[grade_val]["count"] += 1
        by_grade[grade_val]["items"].append(result)

        # D级和E级产生告警
        if grade_val in (FreshnessGrade.D.value, FreshnessGrade.E.value):
            alert_type = "过期下架" if grade_val == FreshnessGrade.E.value else "临期预警"
            alerts.append({
                "item_id": result["item_id"],
                "grade": grade_val,
                "alert_type": alert_type,
                "remaining_hours": result["remaining_hours"],
                "action": "立即下架" if grade_val == FreshnessGrade.E.value else "建议打折促销",
                "expected_impact": f"¥{result.get('discounted_price_fen', 0) / 100:.2f}" if result.get("discounted_price_fen") else None,
            })

    valid_count = len(graded) - error_count
    fresh_count = by_grade["A"]["count"] + by_grade["B"]["count"]
    fresh_rate = round(fresh_count / valid_count * 100, 1) if valid_count > 0 else 0.0

    return {
        "total": len(items),
        "valid_count": valid_count,
        "error_count": error_count,
        "by_grade": by_grade,
        "alerts": alerts,
        "summary": {
            "fresh_rate": fresh_rate,
            "fresh_count": fresh_count,
            "expiring_count": by_grade["D"]["count"],
            "expired_count": by_grade["E"]["count"],
        },
    }
