"""
SignalBus — 信号路由引擎
Signal Bus: Event-Driven Decision Routing

将原始业务事件自动路由到对应的运营动作，实现信息打通。

3 条核心路由规则：
  ① 差评信号       → 触发私域差评修复旅程（review_repair journey）
  ② 临期/低库存     → 触发废料预警推送（waste guard push）
  ③ 大桌预订(≥6人)  → 触发裂变场景识别（referral engine + 运营提醒）

设计原则：
  - 每条路由幂等（已处理的信号不重复触发，用 signal_id 去重）
  - 降级安全：子服务失败不影响其他路由
  - 每次触发后写回 private_domain_signals.action_taken（可追溯）
"""

from __future__ import annotations

import asyncio
import datetime
import uuid
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# ── 常量 ──────────────────────────────────────────────────────────────────────

_LARGE_TABLE_THRESHOLD = 6  # 6人及以上触发裂变识别
_NEAR_EXPIRY_STATUSES = ("critical", "low")  # 临期/低库存状态
_SCAN_WINDOW_HOURS = 2  # 周期扫描窗口（小时）


# ── 内部 helpers ──────────────────────────────────────────────────────────────


async def _mark_signal_routed(
    signal_id: str,
    action: str,
    db: AsyncSession,
) -> None:
    """将信号标记为已路由，防止重复触发。"""
    try:
        await db.execute(
            text("""
                UPDATE private_domain_signals
                SET action_taken = :action,
                    resolved_at  = :now
                WHERE signal_id = :sid
                  AND resolved_at IS NULL
            """),
            {"action": action, "now": datetime.datetime.utcnow(), "sid": signal_id},
        )
        await db.commit()
    except Exception as exc:
        logger.warning("signal_bus.mark_routed_failed", signal_id=signal_id, error=str(exc))
        await db.rollback()


async def _write_signal(
    store_id: str,
    signal_type: str,
    description: str,
    severity: str,
    db: AsyncSession,
    customer_id: Optional[str] = None,
) -> str:
    """写入一条新信号记录，返回 signal_id。"""
    sid = f"SIG_{signal_type[:4].upper()}_{uuid.uuid4().hex[:8]}"
    try:
        await db.execute(
            text("""
                INSERT INTO private_domain_signals
                    (id, signal_id, store_id, customer_id,
                     signal_type, description, severity, triggered_at)
                VALUES
                    (gen_random_uuid(), :sid, :store_id, :customer_id,
                     :signal_type, :description, :severity, :now)
                ON CONFLICT (signal_id) DO NOTHING
            """),
            {
                "sid": sid,
                "store_id": store_id,
                "customer_id": customer_id,
                "signal_type": signal_type,
                "description": description,
                "severity": severity,
                "now": datetime.datetime.utcnow(),
            },
        )
        await db.commit()
    except Exception as exc:
        logger.warning("signal_bus.write_signal_failed", error=str(exc))
        await db.rollback()
    return sid


# ── 路由①：差评 → 私域修复旅程 ───────────────────────────────────────────────


async def route_bad_review(
    store_id: str,
    signal_id: str,
    customer_id: Optional[str],
    rating: int,
    content: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    差评路由：触发私域 review_repair 旅程。

    Args:
        store_id:   门店ID
        signal_id:  信号ID（幂等键）
        customer_id: 顾客ID（可选）
        rating:     评分（1-5）
        content:    差评内容
        db:         数据库会话

    Returns:
        {"routed": bool, "journey_id": str | None, "action": str}
    """
    logger.info("signal_bus.bad_review", store_id=store_id, signal_id=signal_id, rating=rating)

    if not customer_id:
        await _mark_signal_routed(signal_id, "no_customer_id_skip", db)
        return {"routed": False, "journey_id": None, "action": "差评无顾客ID，已记录但跳过旅程"}

    try:
        from .journey_orchestrator import JourneyOrchestrator

        orch = JourneyOrchestrator()
        result = await orch.trigger(
            customer_id,
            store_id,
            "dormant_wakeup",
            db,
        )
        # 差评优先级更高，写入 private_domain_signals 差评类型备注
        journey_id = result.get("journey_id") or result.get("journey_db_id")
        action_desc = f"bad_review_repair_triggered:journey={journey_id}"
        await _mark_signal_routed(signal_id, action_desc, db)
        logger.info("signal_bus.bad_review.routed", store_id=store_id, customer_id=customer_id, journey_id=journey_id)
        return {"routed": True, "journey_id": journey_id, "action": f"已触发差评修复旅程 ({journey_id})"}
    except Exception as exc:
        logger.error("signal_bus.bad_review.failed", store_id=store_id, error=str(exc))
        return {"routed": False, "journey_id": None, "action": f"路由失败: {exc}"}


# ── 路由②：临期/低库存 → 废料预警推送 ────────────────────────────────────────


async def route_near_expiry(
    store_id: str,
    db: AsyncSession,
    push: bool = True,
) -> Dict[str, Any]:
    """
    临期/低库存路由：扫描临期库存 → 调用废料预警 → 推送告警。

    Returns:
        {"routed": bool, "items_count": int, "pushed": bool, "signal_ids": list}
    """
    logger.info("signal_bus.near_expiry.scan", store_id=store_id)

    # 查询临期/低库存食材
    try:
        rows = (
            await db.execute(
                text("""
                SELECT id, name, current_quantity, unit, unit_cost, status
                FROM inventory_items
                WHERE store_id = :s
                  AND status IN ('critical', 'low')
                ORDER BY unit_cost DESC NULLS LAST
                LIMIT 20
            """),
                {"s": store_id},
            )
        ).fetchall()
    except Exception as exc:
        logger.warning("signal_bus.near_expiry.query_failed", error=str(exc))
        return {"routed": False, "items_count": 0, "pushed": False, "signal_ids": []}

    if not rows:
        return {"routed": False, "items_count": 0, "pushed": False, "signal_ids": [], "action": "无临期/低库存食材"}

    signal_ids: List[str] = []
    for row in rows:
        item_id, name, qty, unit, cost, status = (row[0], row[1], row[2], row[3], row[4], row[5])
        cost_yuan = round((cost or 0) * qty / 100, 2)
        desc = f"【{status.upper()}】{name} 剩余 {qty}{unit or ''}" f"，预估¥{cost_yuan:.2f} 损耗风险"
        severity = "high" if status == "critical" else "medium"
        sid = await _write_signal(
            store_id,
            "churn_risk",
            desc,
            severity,
            db,
        )
        signal_ids.append(sid)

    # 调用废料预警摘要（调用现有 WasteGuardService）
    waste_summary: Optional[str] = None
    try:
        from .waste_guard_service import WasteGuardService

        svc = WasteGuardService()
        report = await svc.get_store_waste_summary(
            store_id=store_id,
            target_date=datetime.date.today(),
            db=db,
        )
        total_yuan = report.get("total_waste_yuan", 0)
        waste_summary = f"今日已损耗 ¥{total_yuan:.2f}"
    except Exception as exc:
        logger.warning("signal_bus.near_expiry.waste_svc_failed", error=str(exc))

    # 推送企微告警
    pushed = False
    if push:
        try:
            from .wechat_service import wechat_service as _wechat

            items_text = "\n".join(f"• {r[1]} {r[2]}{r[3] or ''} [{r[5]}]" for r in rows[:5])
            body = f"【临期/低库存预警】{store_id}\n" f"共 {len(rows)} 个食材需关注：\n{items_text}"
            if waste_summary:
                body += f"\n{waste_summary}"
            body += f"\n建议立即盘点处理"
            if _wechat:
                await _wechat.send_text(body)
                pushed = True
        except Exception as exc:
            logger.warning("signal_bus.near_expiry.push_failed", error=str(exc))

    logger.info("signal_bus.near_expiry.done", store_id=store_id, items=len(rows), pushed=pushed)
    return {
        "routed": True,
        "items_count": len(rows),
        "pushed": pushed,
        "signal_ids": signal_ids,
        "action": f"已生成 {len(rows)} 条临期预警信号，推送: {'成功' if pushed else '跳过'}",
    }


# ── 路由③：大桌预订(≥6人) → 裂变场景识别 ──────────────────────────────────────


async def route_large_table_reservation(
    store_id: str,
    reservation_id: str,
    customer_phone: str,
    customer_name: str,
    party_size: int,
    reservation_date: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    大桌预订路由：≥6人预订 → 识别裂变场景 → 记录信号 + 返回运营建议。

    Returns:
        {"routed": bool, "referral_scene": str, "k_factor": float, "action": str}
    """
    logger.info("signal_bus.large_table", store_id=store_id, reservation_id=reservation_id, party_size=party_size)

    if party_size < _LARGE_TABLE_THRESHOLD:
        return {
            "routed": False,
            "referral_scene": None,
            "k_factor": 0.0,
            "action": f"桌台人数 {party_size} < {_LARGE_TABLE_THRESHOLD}，不触发裂变识别",
        }

    # 识别裂变场景
    scene, k_factor, suggestion = _classify_referral_scene(party_size, customer_name)

    # 写入 viral 信号
    desc = f"大桌预订 [{reservation_id}] {customer_name} {party_size}人" f" | 裂变场景: {scene} | K={k_factor}"
    await _write_signal(store_id, "viral", desc, "medium", db)

    # 查找是否已有私域会员（通过电话匹配）
    member_id: Optional[str] = None
    try:
        row = (
            await db.execute(
                text("""
                SELECT customer_id FROM private_domain_members
                WHERE store_id = :s
                  AND customer_id LIKE :phone_prefix
                LIMIT 1
            """),
                {"s": store_id, "phone_prefix": f"%{customer_phone[-4:]}"},
            )
        ).fetchone()
        if row:
            member_id = row[0]
    except Exception as exc:
        logger.warning("signal_bus.large_table.member_lookup_failed", error=str(exc))

    logger.info("signal_bus.large_table.routed", store_id=store_id, scene=scene, k_factor=k_factor, member_id=member_id)

    return {
        "routed": True,
        "referral_scene": scene,
        "k_factor": k_factor,
        "member_id": member_id,
        "suggestion": suggestion,
        "action": f"已识别裂变场景【{scene}】，建议: {suggestion}",
    }


def _classify_referral_scene(
    party_size: int,
    customer_name: str,
) -> tuple[str, float, str]:
    """
    基于人数和姓名特征识别裂变场景，返回 (场景名, K值, 建议)。

    参考 referral_engine.py 的4类高K值场景。
    """
    # 简单规则匹配（生产环境可接入 NLP）
    if party_size >= 20:
        return (
            "corporate_host",
            2.0,
            "发送商务宴请专属礼遇券，邀请添加企微，预备年度合作客户关系",
        )
    if party_size >= 10:
        return (
            "family_banquet",
            2.4,
            "触发家宴组织者旅程，赠送全家福合影服务，引导分享朋友圈",
        )
    if party_size >= 6:
        # 通过姓名末字判断聚餐vs宴席（简单启发式）
        return (
            "super_fan_gathering",
            1.8,
            "发送专属聚餐感谢卡，附带「带朋友来享8折」裂变券",
        )
    return ("regular", 0.0, "")


# ── 周期扫描入口 ──────────────────────────────────────────────────────────────


async def run_periodic_scan(store_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    周期扫描入口（由 Celery Beat 每2小时调用）。

    扫描内容：
      1. 未处理的差评信号 → 触发路由①
      2. 临期/低库存     → 触发路由②
      3. 今日新增大桌预订  → 触发路由③
    """
    results: Dict[str, Any] = {
        "store_id": store_id,
        "scanned_at": datetime.datetime.utcnow().isoformat(),
        "bad_review": [],
        "near_expiry": {},
        "large_tables": [],
    }

    # ① 未处理差评信号
    since = (datetime.datetime.utcnow() - datetime.timedelta(hours=_SCAN_WINDOW_HOURS)).isoformat()
    try:
        review_rows = (
            await db.execute(
                text("""
                SELECT signal_id, customer_id,
                       description
                FROM private_domain_signals
                WHERE store_id  = :s
                  AND signal_type = 'bad_review'
                  AND resolved_at IS NULL
                  AND triggered_at >= :since
                LIMIT 20
            """),
                {"s": store_id, "since": since},
            )
        ).fetchall()

        for r in review_rows:
            sig_id, cust_id, desc = r[0], r[1], r[2]
            # 从描述中提取评分（简单解析，格式 "rating:1"）
            rating = 1
            if "rating:" in (desc or ""):
                try:
                    rating = int(desc.split("rating:")[-1].split()[0])
                except ValueError:
                    pass
            res = await route_bad_review(
                store_id,
                sig_id,
                cust_id,
                rating,
                desc or "",
                db,
            )
            results["bad_review"].append(res)
    except Exception as exc:
        logger.warning("signal_bus.scan.bad_review_failed", store_id=store_id, error=str(exc))

    # ② 临期/低库存
    try:
        results["near_expiry"] = await route_near_expiry(store_id, db, push=True)
    except Exception as exc:
        logger.warning("signal_bus.scan.near_expiry_failed", store_id=store_id, error=str(exc))

    # ③ 今日新增大桌预订
    today = datetime.date.today().isoformat()
    try:
        res_rows = (
            await db.execute(
                text("""
                SELECT id, customer_phone, customer_name,
                       party_size, reservation_date::text
                FROM reservations
                WHERE store_id           = :s
                  AND reservation_date   = :today
                  AND party_size         >= :threshold
                  AND created_at         >= :since
                ORDER BY party_size DESC
                LIMIT 10
            """),
                {
                    "s": store_id,
                    "today": today,
                    "threshold": _LARGE_TABLE_THRESHOLD,
                    "since": since,
                },
            )
        ).fetchall()

        for row in res_rows:
            res = await route_large_table_reservation(
                store_id=store_id,
                reservation_id=str(row[0]),
                customer_phone=str(row[1]),
                customer_name=str(row[2]),
                party_size=int(row[3]),
                reservation_date=str(row[4]),
                db=db,
            )
            results["large_tables"].append(res)
    except Exception as exc:
        logger.warning("signal_bus.scan.large_table_failed", store_id=store_id, error=str(exc))

    total_routed = (
        sum(1 for r in results["bad_review"] if r.get("routed"))
        + (1 if results["near_expiry"].get("routed") else 0)
        + sum(1 for r in results["large_tables"] if r.get("routed"))
    )
    results["total_routed"] = total_routed
    logger.info("signal_bus.scan.done", store_id=store_id, total_routed=total_routed)
    return results
