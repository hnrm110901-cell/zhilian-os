"""
OpsMonitorService — 运维监控数据聚合服务

职责：
1. 写入接口：device_reading / network_health / sys_health / food_safety
2. 读取聚合：get_store_dashboard（L1+L2+L3 健康总览）
3. 告警收敛：converge_alerts（多信号→单根因事件）
4. 食安状态：get_food_safety_status
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select, func, text, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.ops import (
    OpsDeviceReading,
    OpsNetworkHealth,
    OpsSysHealthCheck,
    OpsFoodSafetyRecord,
    OpsEvent,
    OpsEventSeverity,
    OpsEventStatus,
)

logger = structlog.get_logger()

# ── 告警阈值常量（对应方案 第三章 3.1 表格）────────────────────────────────────

_COLD_CHAIN_MAX_C = 8.0          # 冷藏超过8°C告警
_FROZEN_MAX_C = -12.0            # 冷冻超过-12°C告警
_FRIDGE_POWER_DEVIATION = 0.20   # 功率偏离历史基线 20% 告警
_NETWORK_LATENCY_MS = 200.0      # 延迟超过 200ms 告警
_PACKET_LOSS_PCT = 2.0           # 丢包超过 2% 告警
_HTTP_TIMEOUT_MS = 3000.0        # HTTP 响应超过 3000ms 告警

# P0 系统连续失败阈值（次数）
_P0_FAIL_THRESHOLD = 1
_P1_FAIL_THRESHOLD = 2
_P2_FAIL_THRESHOLD = 3


class OpsMonitorService:
    """运维监控数据聚合服务（无状态，session 每次传入）"""

    # ── 写入接口 ─────────────────────────────────────────────────────────────

    async def record_device_reading(
        self,
        session: AsyncSession,
        store_id: str,
        device_name: str,
        metric_type: str,
        value_float: Optional[float] = None,
        value_bool: Optional[bool] = None,
        unit: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """写入一条IoT设备读数，并自动判断是否触发告警。"""
        is_alert, alert_msg = self._eval_device_alert(metric_type, value_float, value_bool)
        reading = OpsDeviceReading(
            id=uuid.uuid4(),
            store_id=store_id,
            asset_id=uuid.UUID(asset_id) if asset_id else None,
            device_name=device_name,
            metric_type=metric_type,
            value_float=value_float,
            value_bool=value_bool,
            unit=unit,
            is_alert=is_alert,
            alert_message=alert_msg,
            recorded_at=datetime.now(timezone.utc),
        )
        session.add(reading)
        await session.flush()
        if is_alert:
            await self._create_ops_event(
                session, store_id, "device_alert", OpsEventSeverity.HIGH,
                device_name, alert_msg or f"{metric_type} 异常",
                {"metric_type": metric_type, "value": value_float},
            )
        return {"reading_id": str(reading.id), "is_alert": is_alert, "alert_message": alert_msg}

    async def record_network_health(
        self,
        session: AsyncSession,
        store_id: str,
        probe_type: str,
        target: str,
        is_available: bool = True,
        latency_ms: Optional[float] = None,
        packet_loss_pct: Optional[float] = None,
        bandwidth_mbps: Optional[float] = None,
        status_code: Optional[int] = None,
        vlan: Optional[str] = None,
    ) -> Dict[str, Any]:
        """写入一条网络探针结果，并自动判断告警。"""
        is_alert, alert_msg = self._eval_network_alert(
            is_available, latency_ms, packet_loss_pct, status_code
        )
        record = OpsNetworkHealth(
            id=uuid.uuid4(),
            store_id=store_id,
            probe_type=probe_type,
            target=target,
            vlan=vlan,
            latency_ms=latency_ms,
            packet_loss_pct=packet_loss_pct,
            bandwidth_mbps=bandwidth_mbps,
            is_available=is_available,
            status_code=status_code,
            is_alert=is_alert,
            alert_message=alert_msg,
            recorded_at=datetime.now(timezone.utc),
        )
        session.add(record)
        await session.flush()
        if is_alert:
            severity = OpsEventSeverity.CRITICAL if not is_available else OpsEventSeverity.HIGH
            await self._create_ops_event(
                session, store_id, "network_alert", severity,
                f"{probe_type}:{target}", alert_msg or "网络异常",
                {"vlan": vlan, "latency_ms": latency_ms, "packet_loss_pct": packet_loss_pct},
            )
        return {"record_id": str(record.id), "is_alert": is_alert}

    async def record_sys_health(
        self,
        session: AsyncSession,
        store_id: str,
        system_name: str,
        priority: str,
        check_method: str,
        is_available: bool,
        response_ms: Optional[float] = None,
        http_status: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """写入一条系统心跳结果，并根据优先级和连续失败次数判断告警。"""
        # 查询连续失败次数
        consecutive = await self._get_consecutive_failures(session, store_id, system_name)
        if not is_available:
            consecutive += 1
        else:
            consecutive = 0

        fail_threshold = {
            "P0": _P0_FAIL_THRESHOLD, "P1": _P1_FAIL_THRESHOLD,
        }.get(priority, _P2_FAIL_THRESHOLD)
        is_alert = not is_available and consecutive >= fail_threshold

        record = OpsSysHealthCheck(
            id=uuid.uuid4(),
            store_id=store_id,
            system_name=system_name,
            priority=priority,
            check_method=check_method,
            is_available=is_available,
            response_ms=response_ms,
            http_status=http_status,
            error_message=error_message,
            is_alert=is_alert,
            consecutive_failures=consecutive,
            recorded_at=datetime.now(timezone.utc),
        )
        session.add(record)
        await session.flush()
        if is_alert:
            severity = (OpsEventSeverity.CRITICAL if priority == "P0"
                        else OpsEventSeverity.HIGH if priority == "P1"
                        else OpsEventSeverity.MEDIUM)
            await self._create_ops_event(
                session, store_id, "system_alert", severity,
                system_name,
                f"系统 {system_name}（{priority}）连续 {consecutive} 次检测失败",
                {"priority": priority, "consecutive": consecutive, "error": error_message},
            )
        return {"record_id": str(record.id), "is_alert": is_alert, "consecutive_failures": consecutive}

    async def record_food_safety(
        self,
        session: AsyncSession,
        store_id: str,
        record_type: str,
        device_name: Optional[str] = None,
        value_float: Optional[float] = None,
        threshold_min: Optional[float] = None,
        threshold_max: Optional[float] = None,
        unit: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """写入食安记录，自动判断是否合规。"""
        is_compliant = True
        if value_float is not None:
            if threshold_max is not None and value_float > threshold_max:
                is_compliant = False
            if threshold_min is not None and value_float < threshold_min:
                is_compliant = False

        record = OpsFoodSafetyRecord(
            id=uuid.uuid4(),
            store_id=store_id,
            record_type=record_type,
            device_name=device_name,
            is_compliant=is_compliant,
            value_float=value_float,
            threshold_min=threshold_min,
            threshold_max=threshold_max,
            unit=unit,
            notes=notes,
            requires_action=not is_compliant,
            recorded_at=datetime.now(timezone.utc),
        )
        session.add(record)
        await session.flush()
        if not is_compliant:
            await self._create_ops_event(
                session, store_id, "food_safety", OpsEventSeverity.HIGH,
                device_name or record_type,
                f"食安异常：{record_type} {value_float}{unit or ''} 超出阈值",
                {"type": record_type, "value": value_float,
                 "min": threshold_min, "max": threshold_max},
            )
        return {"record_id": str(record.id), "is_compliant": is_compliant}

    # ── 读取聚合 ─────────────────────────────────────────────────────────────

    async def get_store_dashboard(
        self,
        session: AsyncSession,
        store_id: str,
        window_minutes: int = 30,
    ) -> Dict[str, Any]:
        """
        门店健康总览（L1设备 + L2网络 + L3系统）。
        返回各层健康分、活跃告警数、及摘要列表。
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

        # L1 设备层
        l1 = await self._layer1_summary(session, store_id, since)
        # L2 网络层
        l2 = await self._layer2_summary(session, store_id, since)
        # L3 系统层
        l3 = await self._layer3_summary(session, store_id, since)
        # 食安
        fs = await self._food_safety_summary(session, store_id, since)

        overall_score = round((l1["score"] + l2["score"] + l3["score"]) / 3, 1)
        overall_status = _score_to_status(overall_score)

        return {
            "store_id": store_id,
            "overall_status": overall_status,
            "overall_score": overall_score,
            "window_minutes": window_minutes,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "layers": {
                "l1_device": l1,
                "l2_network": l2,
                "l3_system": l3,
            },
            "food_safety": fs,
            "active_alerts": l1["alert_count"] + l2["alert_count"] + l3["alert_count"],
        }

    async def converge_alerts(
        self,
        session: AsyncSession,
        store_id: str,
        window_minutes: int = 5,
    ) -> Dict[str, Any]:
        """
        告警收敛：把同一时间窗口内的多条告警归并为根因事件。

        收敛规则（对应方案 第五章 5.2 故障关联分析）：
        - 全部云服务同时不可用 → 外网故障
        - 特定 VLAN 下设备批量离线且外网正常 → 交换机/AP 故障
        - 网络正常但 POS 系统不可用 → POS 软件故障
        - 多系统数据同步延迟 → 队列积压
        """
        since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

        # 收集窗口内各类告警
        net_alerts = await self._count_alerts(session, store_id, "ops_network_health", since)
        sys_alerts = await self._count_alerts(session, store_id, "ops_sys_health_checks", since)
        dev_alerts = await self._count_alerts(session, store_id, "ops_device_readings", since)

        root_cause, severity, recommendation = _infer_root_cause(net_alerts, sys_alerts, dev_alerts)

        return {
            "store_id": store_id,
            "window_minutes": window_minutes,
            "alert_counts": {
                "network": net_alerts["total"],
                "system": sys_alerts["total"],
                "device": dev_alerts["total"],
            },
            "root_cause": root_cause,
            "severity": severity,
            "recommendation": recommendation,
            "converged_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_food_safety_status(
        self,
        session: AsyncSession,
        store_id: str,
        days: int = 7,
    ) -> Dict[str, Any]:
        """最近 N 天食安合规状态汇总。"""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(
                OpsFoodSafetyRecord.record_type,
                func.count().label("total"),
                func.sum(
                    func.cast(~OpsFoodSafetyRecord.is_compliant, type_=func.count().type)
                ).label("violations"),
            )
            .where(
                and_(
                    OpsFoodSafetyRecord.store_id == store_id,
                    OpsFoodSafetyRecord.recorded_at >= since,
                )
            )
            .group_by(OpsFoodSafetyRecord.record_type)
        )
        rows = (await session.execute(stmt)).fetchall()

        # 查非合规未解决记录
        open_stmt = (
            select(OpsFoodSafetyRecord)
            .where(
                and_(
                    OpsFoodSafetyRecord.store_id == store_id,
                    OpsFoodSafetyRecord.is_compliant.is_(False),
                    OpsFoodSafetyRecord.resolved_at.is_(None),
                )
            )
            .order_by(OpsFoodSafetyRecord.recorded_at.desc())
            .limit(10)
        )
        open_records = (await session.execute(open_stmt)).scalars().all()

        type_summary = []
        total_violations = 0
        for row in rows:
            violations = int(row.violations or 0)
            total_violations += violations
            compliance_rate = round((1 - violations / row.total) * 100, 1) if row.total else 100.0
            type_summary.append({
                "record_type": row.record_type,
                "total": row.total,
                "violations": violations,
                "compliance_rate_pct": compliance_rate,
            })

        return {
            "store_id": store_id,
            "days": days,
            "total_violations": total_violations,
            "overall_compliant": total_violations == 0,
            "by_type": type_summary,
            "open_issues": [
                {
                    "id": str(r.id),
                    "type": r.record_type,
                    "device": r.device_name,
                    "value": r.value_float,
                    "unit": r.unit,
                    "recorded_at": r.recorded_at.isoformat(),
                }
                for r in open_records
            ],
        }

    # ── 私有辅助方法 ──────────────────────────────────────────────────────────

    @staticmethod
    def _eval_device_alert(
        metric_type: str,
        value_float: Optional[float],
        value_bool: Optional[bool],
    ) -> tuple[bool, Optional[str]]:
        if metric_type == "temperature" and value_float is not None:
            if value_float > _COLD_CHAIN_MAX_C:
                return True, f"冷藏温度 {value_float}°C 超过阈值 {_COLD_CHAIN_MAX_C}°C"
            if value_float > _FROZEN_MAX_C and value_float < 0:
                # 冷冻区
                pass
        if metric_type == "online_status" and value_bool is False:
            return True, "设备离线"
        return False, None

    @staticmethod
    def _eval_network_alert(
        is_available: bool,
        latency_ms: Optional[float],
        packet_loss_pct: Optional[float],
        status_code: Optional[int],
    ) -> tuple[bool, Optional[str]]:
        if not is_available:
            return True, "目标不可达"
        if latency_ms is not None and latency_ms > _NETWORK_LATENCY_MS:
            return True, f"延迟 {latency_ms:.0f}ms 超过阈值 {_NETWORK_LATENCY_MS}ms"
        if packet_loss_pct is not None and packet_loss_pct > _PACKET_LOSS_PCT:
            return True, f"丢包率 {packet_loss_pct:.1f}% 超过阈值 {_PACKET_LOSS_PCT}%"
        if status_code is not None and status_code >= 500:
            return True, f"HTTP {status_code} 服务端错误"
        return False, None

    async def _get_consecutive_failures(
        self, session: AsyncSession, store_id: str, system_name: str
    ) -> int:
        """获取该系统最近一次连续失败次数。"""
        stmt = (
            select(OpsSysHealthCheck.consecutive_failures)
            .where(
                and_(
                    OpsSysHealthCheck.store_id == store_id,
                    OpsSysHealthCheck.system_name == system_name,
                )
            )
            .order_by(OpsSysHealthCheck.recorded_at.desc())
            .limit(1)
        )
        result = (await session.execute(stmt)).scalar_one_or_none()
        return result or 0

    async def _create_ops_event(
        self,
        session: AsyncSession,
        store_id: str,
        event_type: str,
        severity: OpsEventSeverity,
        component: str,
        description: str,
        raw_data: Optional[Dict] = None,
    ) -> None:
        event = OpsEvent(
            id=uuid.uuid4(),
            store_id=store_id,
            event_type=event_type,
            severity=severity.value,
            component=component,
            description=description,
            raw_data=raw_data,
            status=OpsEventStatus.OPEN.value,
            created_at=datetime.now(timezone.utc),
        )
        session.add(event)

    async def _layer1_summary(
        self, session: AsyncSession, store_id: str, since: datetime
    ) -> Dict[str, Any]:
        total_stmt = select(func.count()).select_from(
            select(OpsDeviceReading.id)
            .where(OpsDeviceReading.store_id == store_id,
                   OpsDeviceReading.recorded_at >= since)
            .subquery()
        )
        alert_stmt = select(func.count()).select_from(
            select(OpsDeviceReading.id)
            .where(OpsDeviceReading.store_id == store_id,
                   OpsDeviceReading.recorded_at >= since,
                   OpsDeviceReading.is_alert.is_(True))
            .subquery()
        )
        total = (await session.execute(total_stmt)).scalar() or 0
        alerts = (await session.execute(alert_stmt)).scalar() or 0
        score = 100.0 if total == 0 else round(max(0.0, (1 - alerts / total) * 100), 1)
        return {"total_readings": total, "alert_count": alerts,
                "score": score, "status": _score_to_status(score)}

    async def _layer2_summary(
        self, session: AsyncSession, store_id: str, since: datetime
    ) -> Dict[str, Any]:
        total_stmt = select(func.count()).select_from(
            select(OpsNetworkHealth.id)
            .where(OpsNetworkHealth.store_id == store_id,
                   OpsNetworkHealth.recorded_at >= since)
            .subquery()
        )
        unavail_stmt = select(func.count()).select_from(
            select(OpsNetworkHealth.id)
            .where(OpsNetworkHealth.store_id == store_id,
                   OpsNetworkHealth.recorded_at >= since,
                   OpsNetworkHealth.is_available.is_(False))
            .subquery()
        )
        alert_stmt = select(func.count()).select_from(
            select(OpsNetworkHealth.id)
            .where(OpsNetworkHealth.store_id == store_id,
                   OpsNetworkHealth.recorded_at >= since,
                   OpsNetworkHealth.is_alert.is_(True))
            .subquery()
        )
        total = (await session.execute(total_stmt)).scalar() or 0
        unavail = (await session.execute(unavail_stmt)).scalar() or 0
        alerts = (await session.execute(alert_stmt)).scalar() or 0
        availability = round((1 - unavail / total) * 100, 1) if total else 100.0
        score = availability
        return {"total_probes": total, "unavailable": unavail, "alert_count": alerts,
                "availability_pct": availability, "score": score,
                "status": _score_to_status(score)}

    async def _layer3_summary(
        self, session: AsyncSession, store_id: str, since: datetime
    ) -> Dict[str, Any]:
        # 每个系统取最新一条记录
        subq = (
            select(
                OpsSysHealthCheck.system_name,
                func.max(OpsSysHealthCheck.recorded_at).label("latest"),
            )
            .where(OpsSysHealthCheck.store_id == store_id,
                   OpsSysHealthCheck.recorded_at >= since)
            .group_by(OpsSysHealthCheck.system_name)
            .subquery()
        )
        stmt = (
            select(OpsSysHealthCheck)
            .join(subq, and_(
                OpsSysHealthCheck.system_name == subq.c.system_name,
                OpsSysHealthCheck.recorded_at == subq.c.latest,
            ))
            .where(OpsSysHealthCheck.store_id == store_id)
        )
        rows = (await session.execute(stmt)).scalars().all()
        total = len(rows)
        down = sum(1 for r in rows if not r.is_available)
        p0_down = sum(1 for r in rows if r.priority == "P0" and not r.is_available)
        alerts = sum(1 for r in rows if r.is_alert)
        uptime = round((1 - down / total) * 100, 1) if total else 100.0
        # P0 宕机直接拉到 0 分
        score = 0.0 if p0_down > 0 else uptime
        return {
            "total_systems": total,
            "down_systems": down,
            "p0_down": p0_down,
            "alert_count": alerts,
            "uptime_pct": uptime,
            "score": score,
            "status": _score_to_status(score),
            "down_list": [r.system_name for r in rows if not r.is_available],
        }

    async def _food_safety_summary(
        self, session: AsyncSession, store_id: str, since: datetime
    ) -> Dict[str, Any]:
        stmt = (
            select(func.count(), func.sum(
                func.cast(~OpsFoodSafetyRecord.is_compliant,
                          type_=func.count().type)
            ))
            .where(OpsFoodSafetyRecord.store_id == store_id,
                   OpsFoodSafetyRecord.recorded_at >= since)
        )
        row = (await session.execute(stmt)).one()
        total, violations = row[0] or 0, int(row[1] or 0)
        compliance_rate = round((1 - violations / total) * 100, 1) if total else 100.0
        return {
            "total_checks": total,
            "violations": violations,
            "compliance_rate_pct": compliance_rate,
            "status": "compliant" if violations == 0 else "violation",
        }

    async def _count_alerts(
        self, session: AsyncSession, store_id: str, table_name: str, since: datetime
    ) -> Dict[str, Any]:
        """通用告警计数（各表结构相同的 is_alert 字段）。"""
        model_map = {
            "ops_network_health": OpsNetworkHealth,
            "ops_sys_health_checks": OpsSysHealthCheck,
            "ops_device_readings": OpsDeviceReading,
        }
        model = model_map.get(table_name)
        if not model:
            return {"total": 0, "alerts": 0}
        total_stmt = select(func.count()).select_from(
            select(model.id)
            .where(model.store_id == store_id, model.recorded_at >= since)
            .subquery()
        )
        alert_stmt = select(func.count()).select_from(
            select(model.id)
            .where(model.store_id == store_id, model.recorded_at >= since,
                   model.is_alert.is_(True))
            .subquery()
        )
        total = (await session.execute(total_stmt)).scalar() or 0
        alerts = (await session.execute(alert_stmt)).scalar() or 0
        return {"total": total, "alerts": alerts}


# ── 纯函数辅助 ────────────────────────────────────────────────────────────────

def _score_to_status(score: float) -> str:
    if score >= 90:
        return "healthy"
    if score >= 70:
        return "warning"
    return "critical"


def _infer_root_cause(
    net: Dict[str, Any],
    sys: Dict[str, Any],
    dev: Dict[str, Any],
) -> tuple[str, str, str]:
    """
    根据三层告警数量推断根因（对应方案 5.2 故障关联分析）。
    返回 (root_cause, severity, recommendation)
    """
    net_alert = net["alerts"]
    sys_alert = sys["alerts"]
    dev_alert = dev["alerts"]

    # 规则1：网络大量告警 + 多系统告警 → 外网故障
    if net_alert >= 3 and sys_alert >= 2:
        return (
            "外网链路中断",
            "critical",
            "1. 检查运营商光猫状态；2. 切换至备用4G链路；3. 通知店长启用离线收银模式",
        )
    # 规则2：部分网络告警（同VLAN）+ 设备告警 → 交换机/AP故障
    if net_alert >= 2 and dev_alert >= 2 and sys_alert < 2:
        return (
            "内网交换机或AP故障",
            "high",
            "1. 检查核心交换机指示灯；2. 尝试重启交换机/AP；3. 检查网线连接",
        )
    # 规则3：POS系统告警但网络正常 → POS软件崩溃
    if sys_alert >= 1 and net_alert == 0:
        return (
            "业务系统软件异常",
            "high",
            "1. 重启对应服务进程；2. 检查服务器磁盘/内存；3. 联系SaaS厂商",
        )
    # 规则4：设备告警为主 → 设备层异常
    if dev_alert >= 2 and net_alert == 0:
        return (
            "IoT设备异常（温度/功率）",
            "medium",
            "1. 到现场确认设备状态；2. 检查冷链实际温度；3. 联系设备维护人员",
        )
    # 无明显规律
    total = net_alert + sys_alert + dev_alert
    if total == 0:
        return "无活跃告警", "none", "系统运行正常"
    return (
        "告警信号不足，无法自动收敛",
        "low",
        "请人工排查各层告警详情",
    )
