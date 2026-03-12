"""
OpsFlowAgent — Phase 13
运营流程体：订单异常 / 库存预警 / 菜品质检 / 出品链联动告警 / 综合优化

核心创新：ChainAlertAgent 实现「1个事件→3层联动」
OKR:
  - 库存预警命中率 >90%
  - 菜品质检覆盖率 >80%
  - 订单异常响应 <5分钟
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ops_flow_agent import (
    OpsChainEvent,
    OpsChainLinkage,
    OpsOrderAnomaly,
    OpsInventoryAlert,
    OpsQualityRecord,
    OpsFlowDecision,
    OpsFlowAgentLog,
)

logger = logging.getLogger(__name__)

_LLM_ENABLED: bool = os.getenv("LLM_ENABLED", "false").lower() == "true"

# ── 阈值配置 ──────────────────────────────────────────────────────────────────

QUALITY_FAIL_THRESHOLD = float(os.getenv("OPS_QUALITY_FAIL_THRESHOLD", "75.0"))
QUALITY_WARN_THRESHOLD = float(os.getenv("OPS_QUALITY_WARN_THRESHOLD", "85.0"))
INVENTORY_LOW_HOURS = float(os.getenv("OPS_INVENTORY_LOW_HOURS", "4.0"))
ORDER_ANOMALY_DEVIATION_PCT = float(os.getenv("OPS_ORDER_ANOMALY_DEVIATION_PCT", "20.0"))

# ── 订单异常阈值（类型 → {指标Key, 告警阈值, higher_is_bad}）─────────────────
ORDER_ANOMALY_CONFIG: Dict[str, Dict[str, Any]] = {
    "refund_spike":      {"metric": "refund_rate",    "threshold": 0.05,  "bad": True},
    "complaint_rate":    {"metric": "complaint_rate", "threshold": 0.03,  "bad": True},
    "delivery_timeout":  {"metric": "timeout_rate",   "threshold": 0.10,  "bad": True},
    "revenue_drop":      {"metric": "revenue_yuan",   "threshold": 0.20,  "bad": False},
    "cancel_surge":      {"metric": "cancel_rate",    "threshold": 0.08,  "bad": True},
    "avg_order_drop":    {"metric": "avg_order_yuan",  "threshold": 0.15, "bad": False},
}

# 库存风险级别阈值（预计售罄小时数 → risk_level）
INVENTORY_RISK_LEVELS = [
    (1.0,  "critical"),
    (2.0,  "high"),
    (4.0,  "medium"),
    (float("inf"), "low"),
]

# 联动规则：触发层 → [目标层动作]
CHAIN_LINKAGE_RULES: Dict[str, List[Dict[str, str]]] = {
    "order": [
        {"target_layer": "inventory", "action": "check_impacted_dishes"},
        {"target_layer": "quality",   "action": "flag_recent_quality"},
    ],
    "inventory": [
        {"target_layer": "order",     "action": "assess_revenue_risk"},
        {"target_layer": "quality",   "action": "check_supplier_quality"},
    ],
    "quality": [
        {"target_layer": "inventory", "action": "check_ingredient_batch"},
        {"target_layer": "order",     "action": "assess_complaint_risk"},
    ],
}

# 联动告警文案模板
LINKAGE_MESSAGES: Dict[str, str] = {
    "check_impacted_dishes":   "订单异常触发库存核查：检查相关菜品库存水位",
    "flag_recent_quality":     "订单异常触发质检复查：标记近期相关菜品质检记录",
    "assess_revenue_risk":     "库存告警触发营收风险评估：预估售罄对营收的¥影响",
    "check_supplier_quality":  "库存告警触发供应商质量检查：核查该批次食材质量",
    "check_ingredient_batch":  "质检失败触发食材批次核查：排查同批次其他菜品",
    "assess_complaint_risk":   "质检失败触发客诉风险预测：评估可能引发的差评影响",
}


# ════════════════════════════════════════════════════════════════════════════
# 纯函数层（无副作用，便于单元测试）
# ════════════════════════════════════════════════════════════════════════════

def classify_quality_status(score: float) -> str:
    """质量评分 → 状态"""
    if score >= QUALITY_WARN_THRESHOLD:
        return "pass"
    if score >= QUALITY_FAIL_THRESHOLD:
        return "warning"
    return "fail"


def classify_inventory_risk(predicted_stockout_hours: float) -> str:
    """预计售罄小时数 → 风险级别"""
    for threshold, level in INVENTORY_RISK_LEVELS:
        if predicted_stockout_hours <= threshold:
            return level
    return "low"


def compute_order_deviation(current: float, baseline: float) -> float:
    """计算订单指标偏差百分比（正数 = 高于基准）"""
    if baseline == 0:
        return 0.0
    return round((current - baseline) / baseline * 100, 2)


def detect_order_anomaly_type(metrics: Dict[str, float], baseline: Dict[str, float]) -> Optional[str]:
    """检测订单异常类型，返回最严重的异常类型或 None"""
    worst: Optional[Tuple[str, float]] = None
    for anomaly_type, cfg in ORDER_ANOMALY_CONFIG.items():
        metric_key = cfg["metric"]
        if metric_key not in metrics or metric_key not in baseline:
            continue
        current = metrics[metric_key]
        base = baseline[metric_key]
        if base == 0:
            continue
        deviation = abs(compute_order_deviation(current, base))
        if deviation >= ORDER_ANOMALY_DEVIATION_PCT:
            if worst is None or deviation > worst[1]:
                worst = (anomaly_type, deviation)
    return worst[0] if worst else None


def estimate_revenue_loss(
    anomaly_type: str,
    current_value: float,
    baseline_value: float,
    daily_revenue_yuan: float,
) -> float:
    """估算订单异常导致的¥营收损失"""
    if anomaly_type == "revenue_drop":
        return round(max(0, (baseline_value - current_value)), 2)
    if anomaly_type in ("refund_spike", "cancel_surge"):
        extra_rate = max(0, current_value - baseline_value)
        return round(daily_revenue_yuan * extra_rate, 2)
    if anomaly_type == "avg_order_drop":
        drop_rate = max(0, (baseline_value - current_value) / baseline_value)
        return round(daily_revenue_yuan * drop_rate * 0.5, 2)
    return 0.0


def estimate_inventory_loss(
    current_qty: int,
    safety_qty: int,
    unit_price_yuan: float = 50.0,
) -> float:
    """估算库存不足的¥损失（基于缺货数量 × 客单价）"""
    shortfall = max(0, safety_qty - current_qty)
    return round(shortfall * unit_price_yuan * 0.3, 2)


def build_chain_alert_title(event_type: str, store_id: str, severity: str) -> str:
    """构建联动告警标题"""
    prefix = {"critical": "🔴 紧急", "warning": "🟡 预警", "info": "🔵 提示"}.get(severity, "⚪")
    type_labels = {
        "order_anomaly":    "订单异常",
        "inventory_low":    "库存不足",
        "quality_fail":     "质检失败",
        "order_spike":      "订单突增",
        "inventory_expiry": "临期食材",
        "quality_pattern":  "质量趋势恶化",
    }
    label = type_labels.get(event_type, event_type)
    return f"{prefix} 门店{store_id} · {label}"


def build_ops_optimize_recommendations(
    order_anomalies: List[Dict],
    inventory_alerts: List[Dict],
    quality_fails: List[Dict],
) -> List[Dict[str, Any]]:
    """基于三层数据生成跨层优化建议（纯函数）"""
    recs: List[Dict[str, Any]] = []

    # 订单异常建议
    for a in order_anomalies[:3]:
        recs.append({
            "layer": "order",
            "action": f"处理{a.get('anomaly_type','订单')}异常",
            "expected_yuan": float(a.get("estimated_revenue_loss_yuan") or 0),
            "timeline": "今日",
            "priority": "P0" if float(a.get("estimated_revenue_loss_yuan") or 0) > 500 else "P1",
        })

    # 库存预警建议
    for alert in inventory_alerts[:3]:
        loss = float(alert.get("estimated_loss_yuan") or 0)
        recs.append({
            "layer": "inventory",
            "action": f"补货「{alert.get('dish_name','菜品')}」{alert.get('restock_qty_recommended',0)}份",
            "expected_yuan": loss,
            "timeline": "4小时内" if alert.get("risk_level") in ("critical", "high") else "今日",
            "priority": "P0" if alert.get("risk_level") == "critical" else "P1",
        })

    # 质检失败建议
    for q in quality_fails[:2]:
        recs.append({
            "layer": "quality",
            "action": f"整改「{q.get('dish_name','菜品')}」出品质量",
            "expected_yuan": 0.0,
            "timeline": "立即",
            "priority": "P0",
        })

    # 按 priority 排序
    recs.sort(key=lambda x: x.get("priority", "P3"))
    return recs


def compute_total_impact_yuan(recommendations: List[Dict]) -> float:
    """汇总优化建议的总¥影响"""
    return round(sum(r.get("expected_yuan", 0) for r in recommendations), 2)


def build_ai_insight_text(
    order_count: int,
    inventory_count: int,
    quality_fail_count: int,
    total_impact_yuan: float,
) -> str:
    """生成AI洞察文本（降级时使用规则模板）"""
    parts = []
    if order_count > 0:
        parts.append(f"发现{order_count}条订单异常")
    if inventory_count > 0:
        parts.append(f"{inventory_count}种食材库存不足")
    if quality_fail_count > 0:
        parts.append(f"{quality_fail_count}道菜品质检不合格")
    if not parts:
        return "出品链运营状态正常，无需特别干预。"
    summary = "、".join(parts)
    return (
        f"出品链综合分析：{summary}。"
        f"预计¥影响合计 {total_impact_yuan:.0f} 元。"
        f"建议按优先级处理，先解决订单层和质检层紧急问题。"
    )


# ════════════════════════════════════════════════════════════════════════════
# Agent 1: ChainAlertAgent — 出品链联动告警（核心创新）
# ════════════════════════════════════════════════════════════════════════════

class ChainAlertAgent:
    """
    出品链联动告警 Agent
    核心能力：任意层（订单/库存/质检）触发事件后，自动联动其他2层执行检查
    实现「1个事件→3层联动」
    """

    async def trigger_chain(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: str,
        source_layer: str,
        event_type: str,
        severity: str,
        source_record_id: str,
        title: str,
        description: str = "",
        impact_yuan: float = 0.0,
        event_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """触发出品链事件，并根据联动规则激活其他层的检查"""
        t0 = datetime.now()

        # 1. 写入链路事件
        event = OpsChainEvent(
            id=str(uuid.uuid4()),
            brand_id=brand_id,
            store_id=store_id,
            event_type=event_type,
            severity=severity,
            source_layer=source_layer,
            source_record_id=source_record_id,
            title=title,
            description=description,
            impact_yuan=Decimal(str(impact_yuan)) if impact_yuan else None,
            event_data=event_data or {},
        )
        db.add(event)

        # 2. 按联动规则触发其他层
        rules = CHAIN_LINKAGE_RULES.get(source_layer, [])
        linkage_records: List[OpsChainLinkage] = []
        linkage_summaries: List[Dict] = []

        for rule in rules:
            target_layer = rule["target_layer"]
            action = rule["action"]
            msg = LINKAGE_MESSAGES.get(action, action)

            linkage = OpsChainLinkage(
                id=str(uuid.uuid4()),
                trigger_event_id=event.id,
                trigger_layer=source_layer,
                target_layer=target_layer,
                target_action=action,
                result_summary=msg,
                impact_yuan=Decimal(str(impact_yuan * 0.3)) if impact_yuan else None,
            )
            db.add(linkage)
            linkage_records.append(linkage)
            linkage_summaries.append({
                "target_layer": target_layer,
                "action": action,
                "message": msg,
            })

        # 3. 更新事件联动状态
        event.linkage_triggered = True
        event.linkage_count = len(linkage_records)

        duration_ms = int((datetime.now() - t0).total_seconds() * 1000)
        _write_log(db, brand_id, "chain_alert", {"store_id": store_id, "source_layer": source_layer},
                   {"event_id": event.id, "linkage_count": len(linkage_records)},
                   impact_yuan, duration_ms)

        logger.info("chain_alert.triggered", store_id=store_id, source_layer=source_layer,
                    severity=severity, linkage_count=len(linkage_records))

        return {
            "event_id": event.id,
            "source_layer": source_layer,
            "severity": severity,
            "title": title,
            "linkage_count": len(linkage_records),
            "linkages": linkage_summaries,
            "impact_yuan": impact_yuan,
        }

    async def get_active_events(
        self,
        db: AsyncSession,
        store_id: str,
        severity_filter: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """获取未解决的出品链事件"""
        q = (
            select(OpsChainEvent)
            .where(
                and_(
                    OpsChainEvent.store_id == store_id,
                    OpsChainEvent.resolved_at.is_(None),
                )
            )
            .order_by(desc(OpsChainEvent.created_at))
            .limit(limit)
        )
        if severity_filter:
            q = q.where(OpsChainEvent.severity == severity_filter)
        result = await db.execute(q)
        events = result.scalars().all()
        return [_event_to_dict(e) for e in events]

    async def resolve_event(
        self,
        db: AsyncSession,
        event_id: str,
    ) -> Dict[str, Any]:
        """标记事件已解决"""
        result = await db.execute(select(OpsChainEvent).where(OpsChainEvent.id == event_id))
        event = result.scalar_one_or_none()
        if not event:
            return {"success": False, "message": f"事件 {event_id} 不存在"}
        event.resolved_at = datetime.now()
        return {"success": True, "event_id": event_id, "resolved_at": str(event.resolved_at)}


# ════════════════════════════════════════════════════════════════════════════
# Agent 2: OrderAnomalyAgent — 订单异常分析
# ════════════════════════════════════════════════════════════════════════════

class OrderAnomalyAgent:
    """
    订单异常分析 Agent
    整合现有 OrderAgent 能力，新增：出品链联动触发 + ¥损失量化
    """

    def __init__(self):
        self._chain_agent = ChainAlertAgent()

    async def detect_anomaly(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: str,
        metrics: Dict[str, float],
        baseline: Dict[str, float],
        daily_revenue_yuan: float = 10000.0,
        time_period: str = "today",
    ) -> Dict[str, Any]:
        """检测订单异常，若发现异常则触发出品链联动"""
        t0 = datetime.now()

        anomaly_type = detect_order_anomaly_type(metrics, baseline)
        if not anomaly_type:
            return {
                "anomaly_detected": False,
                "message": "订单指标正常，无异常",
                "metrics": metrics,
            }

        cfg = ORDER_ANOMALY_CONFIG[anomaly_type]
        metric_key = cfg["metric"]
        current_val = metrics.get(metric_key, 0.0)
        base_val = baseline.get(metric_key, 0.0)
        deviation = compute_order_deviation(current_val, base_val)
        loss_yuan = estimate_revenue_loss(anomaly_type, current_val, base_val, daily_revenue_yuan)

        severity = "critical" if abs(deviation) >= 50 else "warning"

        # 写入异常记录
        rec = OpsOrderAnomaly(
            id=str(uuid.uuid4()),
            brand_id=brand_id,
            store_id=store_id,
            anomaly_type=anomaly_type,
            time_period=time_period,
            current_value=current_val,
            baseline_value=base_val,
            deviation_pct=deviation,
            estimated_revenue_loss_yuan=Decimal(str(loss_yuan)),
            root_cause=_gen_root_cause(anomaly_type, deviation),
            recommendations=_gen_order_recommendations(anomaly_type, deviation, loss_yuan),
            ai_insight=f"检测到{anomaly_type}，偏差{deviation:.1f}%，预计损失¥{loss_yuan:.0f}",
            confidence=0.85,
        )
        db.add(rec)

        # 触发出品链联动
        title = build_chain_alert_title("order_anomaly", store_id, severity)
        chain_result = await self._chain_agent.trigger_chain(
            db=db, brand_id=brand_id, store_id=store_id,
            source_layer="order", event_type="order_anomaly",
            severity=severity, source_record_id=rec.id,
            title=title,
            description=f"{anomaly_type} 偏差{deviation:.1f}%，预计¥{loss_yuan:.0f}损失",
            impact_yuan=loss_yuan,
            event_data={"anomaly_type": anomaly_type, "deviation_pct": deviation},
        )
        rec.chain_event_id = chain_result["event_id"]

        duration_ms = int((datetime.now() - t0).total_seconds() * 1000)
        _write_log(db, brand_id, "order_anomaly", {"store_id": store_id, "time_period": time_period},
                   {"anomaly_type": anomaly_type, "deviation_pct": deviation},
                   loss_yuan, duration_ms)

        return {
            "anomaly_detected": True,
            "record_id": rec.id,
            "anomaly_type": anomaly_type,
            "deviation_pct": deviation,
            "estimated_revenue_loss_yuan": loss_yuan,
            "severity": severity,
            "chain_event_id": chain_result["event_id"],
            "chain_linkages": chain_result["linkages"],
            "recommendations": rec.recommendations,
            "ai_insight": rec.ai_insight,
            "confidence": 0.85,
        }

    async def list_anomalies(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        since = datetime.now() - timedelta(days=days)
        result = await db.execute(
            select(OpsOrderAnomaly)
            .where(and_(OpsOrderAnomaly.store_id == store_id,
                        OpsOrderAnomaly.created_at >= since))
            .order_by(desc(OpsOrderAnomaly.created_at))
            .limit(limit)
        )
        return [_anomaly_to_dict(r) for r in result.scalars().all()]


# ════════════════════════════════════════════════════════════════════════════
# Agent 3: InventoryIntelAgent — 库存智能预警
# ════════════════════════════════════════════════════════════════════════════

class InventoryIntelAgent:
    """
    库存智能预警 Agent
    整合现有 InventoryAgent 能力，新增：出品链联动 + 精准¥损失估算
    """

    def __init__(self):
        self._chain_agent = ChainAlertAgent()

    async def check_stock(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: str,
        dish_id: str,
        dish_name: str,
        current_qty: int,
        safety_qty: int,
        hourly_consumption: float,
        unit_price_yuan: float = 50.0,
    ) -> Dict[str, Any]:
        """检查单品库存状态，不足时触发告警和联动"""
        t0 = datetime.now()

        if hourly_consumption <= 0:
            return {"alert": False, "message": f"「{dish_name}」消耗率为0，无需预警"}

        # 预计售罄小时数
        stockout_hours = current_qty / hourly_consumption
        risk_level = classify_inventory_risk(stockout_hours)
        restock_qty = max(0, safety_qty - current_qty + int(hourly_consumption * 8))
        loss_yuan = estimate_inventory_loss(current_qty, safety_qty, unit_price_yuan)

        if risk_level == "low":
            return {"alert": False, "dish_id": dish_id, "dish_name": dish_name,
                    "risk_level": "low", "predicted_stockout_hours": round(stockout_hours, 1)}

        alert_type = "low_stock" if stockout_hours > 1 else "stockout_predicted"
        severity = "critical" if risk_level == "critical" else "warning"

        rec = OpsInventoryAlert(
            id=str(uuid.uuid4()),
            brand_id=brand_id,
            store_id=store_id,
            alert_type=alert_type,
            dish_id=dish_id,
            dish_name=dish_name,
            current_qty=current_qty,
            safety_qty=safety_qty,
            predicted_stockout_hours=round(stockout_hours, 1),
            restock_qty_recommended=restock_qty,
            estimated_loss_yuan=Decimal(str(loss_yuan)),
            risk_level=risk_level,
            recommendations=[
                f"建议立即备货「{dish_name}」{restock_qty}份",
                f"当前库存可维持约 {stockout_hours:.1f} 小时",
            ],
            ai_insight=(
                f"「{dish_name}」库存{current_qty}份，安全线{safety_qty}份，"
                f"按当前消耗速度约{stockout_hours:.1f}小时后售罄，"
                f"建议补货{restock_qty}份，预防¥{loss_yuan:.0f}损失。"
            ),
            confidence=0.90,
        )
        db.add(rec)

        # 触发出品链联动
        title = build_chain_alert_title("inventory_low", store_id, severity)
        chain_result = await self._chain_agent.trigger_chain(
            db=db, brand_id=brand_id, store_id=store_id,
            source_layer="inventory", event_type="inventory_low",
            severity=severity, source_record_id=rec.id,
            title=title,
            description=f"「{dish_name}」预计{stockout_hours:.1f}h后售罄",
            impact_yuan=loss_yuan,
            event_data={"dish_id": dish_id, "dish_name": dish_name, "stockout_hours": stockout_hours},
        )
        rec.chain_event_id = chain_result["event_id"]

        duration_ms = int((datetime.now() - t0).total_seconds() * 1000)
        _write_log(db, brand_id, "inventory_intel",
                   {"store_id": store_id, "dish_id": dish_id},
                   {"risk_level": risk_level, "stockout_hours": round(stockout_hours, 1)},
                   loss_yuan, duration_ms)

        return {
            "alert": True,
            "record_id": rec.id,
            "dish_id": dish_id,
            "dish_name": dish_name,
            "alert_type": alert_type,
            "risk_level": risk_level,
            "current_qty": current_qty,
            "safety_qty": safety_qty,
            "predicted_stockout_hours": round(stockout_hours, 1),
            "restock_qty_recommended": restock_qty,
            "estimated_loss_yuan": loss_yuan,
            "severity": severity,
            "chain_event_id": chain_result["event_id"],
            "chain_linkages": chain_result["linkages"],
            "recommendations": rec.recommendations,
            "ai_insight": rec.ai_insight,
            "confidence": 0.90,
        }

    async def batch_check(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: str,
        items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """批量检查多品库存状态"""
        alerts = []
        ok_count = 0
        total_loss = 0.0

        for item in items:
            result = await self.check_stock(
                db=db, brand_id=brand_id, store_id=store_id,
                dish_id=item["dish_id"],
                dish_name=item.get("dish_name", item["dish_id"]),
                current_qty=item["current_qty"],
                safety_qty=item.get("safety_qty", 20),
                hourly_consumption=item.get("hourly_consumption", 2.0),
                unit_price_yuan=item.get("unit_price_yuan", 50.0),
            )
            if result.get("alert"):
                alerts.append(result)
                total_loss += result.get("estimated_loss_yuan", 0)
            else:
                ok_count += 1

        critical = [a for a in alerts if a.get("risk_level") == "critical"]
        return {
            "total_checked": len(items),
            "alert_count": len(alerts),
            "ok_count": ok_count,
            "critical_count": len(critical),
            "total_estimated_loss_yuan": round(total_loss, 2),
            "alerts": alerts,
            "ai_insight": build_ai_insight_text(0, len(alerts), 0, total_loss),
        }

    async def list_alerts(
        self,
        db: AsyncSession,
        store_id: str,
        unresolved_only: bool = True,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        q = (
            select(OpsInventoryAlert)
            .where(OpsInventoryAlert.store_id == store_id)
            .order_by(desc(OpsInventoryAlert.created_at))
            .limit(limit)
        )
        if unresolved_only:
            q = q.where(OpsInventoryAlert.resolved == False)
        result = await db.execute(q)
        return [_inv_alert_to_dict(a) for a in result.scalars().all()]


# ════════════════════════════════════════════════════════════════════════════
# Agent 4: QualityInspectionAgent — 菜品质检（整合 QualityAgent）
# ════════════════════════════════════════════════════════════════════════════

class QualityInspectionAgent:
    """
    菜品质检 Agent
    整合现有 QualityAgent 能力，新增：出品链联动 + 品控趋势追踪
    """

    def __init__(self):
        self._chain_agent = ChainAlertAgent()

    async def inspect(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: str,
        dish_id: Optional[str],
        dish_name: str,
        quality_score: float,
        issues: Optional[List[Dict]] = None,
        image_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """记录质检结果，质检失败时触发出品链联动"""
        t0 = datetime.now()

        status = classify_quality_status(quality_score)
        suggestions = _gen_quality_suggestions(status, issues or [])

        rec = OpsQualityRecord(
            id=str(uuid.uuid4()),
            brand_id=brand_id,
            store_id=store_id,
            dish_id=dish_id,
            dish_name=dish_name,
            quality_score=quality_score,
            status=status,
            issues=issues or [],
            suggestions=suggestions,
            image_url=image_url,
            ai_insight=(
                f"「{dish_name}」质量评分{quality_score:.1f}，状态：{status}。"
                + (f"发现{len(issues)}个问题。" if issues else "出品质量良好。")
            ),
            confidence=min(quality_score / 100, 0.95),
        )
        db.add(rec)

        chain_event_id = None
        chain_linkages = []

        # 质检失败/警告 → 触发联动
        if status in ("fail", "warning"):
            event_type = "quality_fail" if status == "fail" else "quality_pattern"
            severity = "critical" if status == "fail" else "warning"
            title = build_chain_alert_title(event_type, store_id, severity)
            chain_result = await self._chain_agent.trigger_chain(
                db=db, brand_id=brand_id, store_id=store_id,
                source_layer="quality", event_type=event_type,
                severity=severity, source_record_id=rec.id,
                title=title,
                description=f"「{dish_name}」评分{quality_score:.1f}，{status}",
                impact_yuan=0.0,
                event_data={"dish_id": dish_id, "dish_name": dish_name,
                            "quality_score": quality_score, "status": status},
            )
            rec.chain_event_id = chain_result["event_id"]
            rec.alert_sent = True
            chain_event_id = chain_result["event_id"]
            chain_linkages = chain_result["linkages"]

        duration_ms = int((datetime.now() - t0).total_seconds() * 1000)
        _write_log(db, brand_id, "quality_inspection",
                   {"store_id": store_id, "dish_name": dish_name},
                   {"status": status, "quality_score": quality_score},
                   0.0, duration_ms)

        return {
            "record_id": rec.id,
            "dish_name": dish_name,
            "quality_score": quality_score,
            "status": status,
            "issues": issues or [],
            "suggestions": suggestions,
            "ai_insight": rec.ai_insight,
            "chain_event_id": chain_event_id,
            "chain_linkages": chain_linkages,
            "confidence": rec.confidence,
        }

    async def get_store_quality_summary(
        self,
        db: AsyncSession,
        store_id: str,
        days: int = 7,
    ) -> Dict[str, Any]:
        """获取门店质检汇总"""
        since = datetime.now() - timedelta(days=days)
        result = await db.execute(
            select(OpsQualityRecord)
            .where(and_(OpsQualityRecord.store_id == store_id,
                        OpsQualityRecord.created_at >= since))
        )
        records = result.scalars().all()
        if not records:
            return {"total": 0, "pass_rate_pct": 100.0, "avg_score": 0.0, "fail_count": 0}

        total = len(records)
        pass_count = sum(1 for r in records if r.status == "pass")
        fail_count = sum(1 for r in records if r.status == "fail")
        avg_score = sum(r.quality_score for r in records) / total

        return {
            "total": total,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "pass_rate_pct": round(pass_count / total * 100, 1),
            "avg_score": round(avg_score, 1),
            "recent_fails": [
                {"dish_name": r.dish_name, "score": r.quality_score, "created_at": str(r.created_at)}
                for r in records if r.status == "fail"
            ][:5],
        }

    async def list_records(
        self,
        db: AsyncSession,
        store_id: str,
        status_filter: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        q = (
            select(OpsQualityRecord)
            .where(OpsQualityRecord.store_id == store_id)
            .order_by(desc(OpsQualityRecord.created_at))
            .limit(limit)
        )
        if status_filter:
            q = q.where(OpsQualityRecord.status == status_filter)
        result = await db.execute(q)
        return [_quality_to_dict(r) for r in result.scalars().all()]


# ════════════════════════════════════════════════════════════════════════════
# Agent 5: OpsOptimizeAgent — 出品链综合优化
# ════════════════════════════════════════════════════════════════════════════

class OpsOptimizeAgent:
    """
    出品链综合优化 Agent
    汇聚三层数据，生成跨层优化决策建议（含¥量化）
    """

    async def generate_decision(
        self,
        db: AsyncSession,
        brand_id: str,
        store_id: str,
        lookback_hours: int = 24,
    ) -> Dict[str, Any]:
        """基于近期三层数据生成综合优化决策"""
        t0 = datetime.now()
        since = datetime.now() - timedelta(hours=lookback_hours)

        # 收集三层数据
        order_result = await db.execute(
            select(OpsOrderAnomaly)
            .where(and_(OpsOrderAnomaly.store_id == store_id,
                        OpsOrderAnomaly.created_at >= since))
            .order_by(desc(OpsOrderAnomaly.created_at)).limit(5)
        )
        order_anomalies = [_anomaly_to_dict(r) for r in order_result.scalars().all()]

        inv_result = await db.execute(
            select(OpsInventoryAlert)
            .where(and_(OpsInventoryAlert.store_id == store_id,
                        OpsInventoryAlert.resolved == False))
            .order_by(desc(OpsInventoryAlert.created_at)).limit(5)
        )
        inventory_alerts = [_inv_alert_to_dict(a) for a in inv_result.scalars().all()]

        from sqlalchemy import or_
        q_result = await db.execute(
            select(OpsQualityRecord)
            .where(and_(OpsQualityRecord.store_id == store_id,
                        or_(OpsQualityRecord.status == "fail",
                            OpsQualityRecord.status == "warning"),
                        OpsQualityRecord.created_at >= since))
            .order_by(desc(OpsQualityRecord.created_at)).limit(5)
        )
        quality_fails = [_quality_to_dict(r) for r in q_result.scalars().all()]

        # 生成建议
        recommendations = build_ops_optimize_recommendations(
            order_anomalies, inventory_alerts, quality_fails
        )
        total_impact = compute_total_impact_yuan(recommendations)
        ai_insight = build_ai_insight_text(
            len(order_anomalies), len(inventory_alerts), len(quality_fails), total_impact
        )

        priority = "P0" if total_impact > 1000 else ("P1" if total_impact > 300 else "P2")
        title = f"出品链综合优化建议 · {len(recommendations)}项 · 预计¥{total_impact:.0f}"

        decision = OpsFlowDecision(
            id=str(uuid.uuid4()),
            brand_id=brand_id,
            store_id=store_id,
            decision_title=title,
            priority=priority,
            involves_order=len(order_anomalies) > 0,
            involves_inventory=len(inventory_alerts) > 0,
            involves_quality=len(quality_fails) > 0,
            estimated_revenue_impact_yuan=Decimal(str(total_impact)),
            estimated_cost_saving_yuan=Decimal(str(total_impact * 0.3)),
            recommendations=recommendations,
            reasoning=ai_insight,
            ai_insight=ai_insight,
            confidence=0.82,
        )
        db.add(decision)

        duration_ms = int((datetime.now() - t0).total_seconds() * 1000)
        _write_log(db, brand_id, "ops_optimize", {"store_id": store_id, "lookback_hours": lookback_hours},
                   {"priority": priority, "rec_count": len(recommendations)},
                   total_impact, duration_ms)

        return {
            "decision_id": decision.id,
            "priority": priority,
            "title": title,
            "order_anomaly_count": len(order_anomalies),
            "inventory_alert_count": len(inventory_alerts),
            "quality_fail_count": len(quality_fails),
            "recommendations": recommendations,
            "total_estimated_impact_yuan": total_impact,
            "ai_insight": ai_insight,
            "confidence": 0.82,
        }

    async def accept_decision(
        self,
        db: AsyncSession,
        decision_id: str,
    ) -> Dict[str, Any]:
        result = await db.execute(
            select(OpsFlowDecision).where(OpsFlowDecision.id == decision_id)
        )
        dec = result.scalar_one_or_none()
        if not dec:
            return {"success": False, "message": f"决策 {decision_id} 不存在"}
        dec.status = "accepted"
        dec.accepted_at = datetime.now()
        return {"success": True, "decision_id": decision_id, "accepted_at": str(dec.accepted_at)}

    async def list_decisions(
        self,
        db: AsyncSession,
        store_id: str,
        status_filter: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        q = (
            select(OpsFlowDecision)
            .where(OpsFlowDecision.store_id == store_id)
            .order_by(desc(OpsFlowDecision.created_at))
            .limit(limit)
        )
        if status_filter:
            q = q.where(OpsFlowDecision.status == status_filter)
        result = await db.execute(q)
        return [_decision_to_dict(d) for d in result.scalars().all()]


# ════════════════════════════════════════════════════════════════════════════
# 内部辅助函数
# ════════════════════════════════════════════════════════════════════════════

def _write_log(
    db: AsyncSession,
    brand_id: str,
    agent_type: str,
    input_params: dict,
    output_summary: dict,
    impact_yuan: float,
    duration_ms: int,
) -> None:
    log = OpsFlowAgentLog(
        id=str(uuid.uuid4()),
        brand_id=brand_id,
        agent_type=agent_type,
        input_params=input_params,
        output_summary=output_summary,
        impact_yuan=Decimal(str(impact_yuan)) if impact_yuan else None,
        duration_ms=duration_ms,
        success=True,
    )
    db.add(log)


def _gen_root_cause(anomaly_type: str, deviation: float) -> str:
    causes = {
        "refund_spike":     f"退单率偏高{abs(deviation):.1f}%，可能原因：菜品质量下滑、配送问题或服务投诉",
        "complaint_rate":   f"客诉率偏高{abs(deviation):.1f}%，建议检查近期出品和服务质量",
        "delivery_timeout": f"配送超时率偏高{abs(deviation):.1f}%，可能为厨房出品慢或配送力不足",
        "revenue_drop":     f"营收下降{abs(deviation):.1f}%，需排查客流量和客单价变化",
        "cancel_surge":     f"取消率突增{abs(deviation):.1f}%，建议检查等位时间和服务响应速度",
        "avg_order_drop":   f"客单价下降{abs(deviation):.1f}%，高毛利菜品点击率可能下降",
    }
    return causes.get(anomaly_type, f"指标偏差{abs(deviation):.1f}%，需进一步分析")


def _gen_order_recommendations(anomaly_type: str, deviation: float, loss_yuan: float) -> List[str]:
    base = [f"预计¥{loss_yuan:.0f}损失，需优先处理"]
    recs = {
        "refund_spike":     ["检查近期订单退单原因", "巡查厨房出品质量", "联系客服了解客户反馈"],
        "complaint_rate":   ["查看近期差评内容", "召开晨会传达质量要求", "重点菜品加强质检"],
        "delivery_timeout": ["检查厨房出品效率", "评估高峰期备菜充分性", "联系配送平台排查延误原因"],
        "revenue_drop":     ["分析当日客流与昨日对比", "检查周边竞争门店动态", "评估营销活动效果"],
        "cancel_surge":     ["检查等位时间是否过长", "核查备菜是否充足", "加强门口引导服务"],
        "avg_order_drop":   ["推荐员工加强高毛利菜品介绍", "检查套餐组合是否吸引力下降"],
    }
    return base + recs.get(anomaly_type, ["分析具体原因，制定针对性措施"])


def _gen_quality_suggestions(status: str, issues: List[Dict]) -> List[str]:
    if status == "pass":
        return ["出品质量合格，继续保持"]
    base = ["暂停该菜品出品，重新制作" if status == "fail" else "加强该菜品质量监控"]
    for issue in issues[:3]:
        severity = issue.get("severity", "medium")
        desc = issue.get("description", "")
        if severity == "high":
            base.append(f"紧急处理：{desc}")
        else:
            base.append(f"优化：{desc}")
    return base


def _event_to_dict(e: OpsChainEvent) -> Dict:
    return {
        "id": e.id, "store_id": e.store_id, "event_type": e.event_type,
        "severity": e.severity, "source_layer": e.source_layer,
        "title": e.title, "description": e.description,
        "impact_yuan": float(e.impact_yuan or 0),
        "linkage_count": e.linkage_count,
        "resolved": e.resolved_at is not None,
        "created_at": str(e.created_at),
    }


def _anomaly_to_dict(r: OpsOrderAnomaly) -> Dict:
    return {
        "id": r.id, "store_id": r.store_id, "anomaly_type": r.anomaly_type,
        "time_period": r.time_period,
        "current_value": r.current_value, "baseline_value": r.baseline_value,
        "deviation_pct": r.deviation_pct,
        "estimated_revenue_loss_yuan": float(r.estimated_revenue_loss_yuan or 0),
        "root_cause": r.root_cause, "recommendations": r.recommendations or [],
        "ai_insight": r.ai_insight, "confidence": r.confidence,
        "chain_event_id": r.chain_event_id,
        "created_at": str(r.created_at),
    }


def _inv_alert_to_dict(a: OpsInventoryAlert) -> Dict:
    return {
        "id": a.id, "store_id": a.store_id, "alert_type": a.alert_type,
        "dish_id": a.dish_id, "dish_name": a.dish_name,
        "current_qty": a.current_qty, "safety_qty": a.safety_qty,
        "predicted_stockout_hours": a.predicted_stockout_hours,
        "restock_qty_recommended": a.restock_qty_recommended,
        "estimated_loss_yuan": float(a.estimated_loss_yuan or 0),
        "risk_level": a.risk_level, "recommendations": a.recommendations or [],
        "ai_insight": a.ai_insight, "confidence": a.confidence,
        "chain_event_id": a.chain_event_id, "resolved": a.resolved,
        "created_at": str(a.created_at),
    }


def _quality_to_dict(r: OpsQualityRecord) -> Dict:
    return {
        "id": r.id, "store_id": r.store_id,
        "dish_id": r.dish_id, "dish_name": r.dish_name,
        "quality_score": r.quality_score, "status": r.status,
        "issues": r.issues or [], "suggestions": r.suggestions or [],
        "ai_insight": r.ai_insight, "confidence": r.confidence,
        "chain_event_id": r.chain_event_id, "alert_sent": r.alert_sent,
        "created_at": str(r.created_at),
    }


def _decision_to_dict(d: OpsFlowDecision) -> Dict:
    return {
        "id": d.id, "store_id": d.store_id,
        "decision_title": d.decision_title, "priority": d.priority,
        "involves_order": d.involves_order, "involves_inventory": d.involves_inventory,
        "involves_quality": d.involves_quality,
        "estimated_revenue_impact_yuan": float(d.estimated_revenue_impact_yuan or 0),
        "estimated_cost_saving_yuan": float(d.estimated_cost_saving_yuan or 0),
        "recommendations": d.recommendations or [],
        "ai_insight": d.ai_insight, "confidence": d.confidence,
        "status": d.status, "accepted_at": str(d.accepted_at) if d.accepted_at else None,
        "created_at": str(d.created_at),
    }
