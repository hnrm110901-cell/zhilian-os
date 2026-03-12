"""
会员生命周期状态机
Member Lifecycle State Machine

状态（9个）：
  lead → registered / first_order_pending → repeat → high_frequency → vip
  任意活跃状态 → at_risk → dormant → lost

触发器（7个）：
  register / first_order / repeat_order / high_frequency_milestone /
  vip_upgrade / churn_warning / inactivity_long

纯函数（无副作用）：
  classify_lifecycle(recency_days, frequency_30d, total_orders, ...) → LifecycleState
  next_state(from_state, trigger) → LifecycleState | None

服务类（依赖 DB + Redis）：
  LifecycleStateMachine.detect_state(customer_id, store_id, db) → LifecycleState
  LifecycleStateMachine.apply_trigger(customer_id, store_id, trigger, db) → dict
"""

from __future__ import annotations

import inspect
import os
from datetime import datetime
from typing import Any, Dict, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.member_lifecycle import (
    LifecycleState,
    MemberLifecycleHistory,
    StateTransitionTrigger,
)

logger = structlog.get_logger()


async def _maybe_await(value: Any) -> Any:
    """Support AsyncMock returning coroutine for sync-style SQLAlchemy methods."""
    if inspect.isawaitable(value):
        return await value
    return value

# ── 阈值（环境变量可覆盖）─────────────────────────────────────────────────────
_CHURN_WARNING_DAYS = int(os.getenv("LC_CHURN_WARNING_DAYS", "45"))
_DORMANT_DAYS       = int(os.getenv("LC_DORMANT_DAYS",       "90"))
_HIGH_FREQ_ORDERS   = int(os.getenv("LC_HIGH_FREQ_ORDERS",   "5"))
_HIGH_FREQ_WINDOW   = int(os.getenv("LC_HIGH_FREQ_WINDOW",   "30"))
_VIP_MONETARY_FEN   = int(os.getenv("LC_VIP_MONETARY_FEN",   "100000"))  # ¥1000

# 合法状态转移表：from_state → {trigger → to_state}
TRANSITION_RULES: Dict[LifecycleState, Dict[StateTransitionTrigger, LifecycleState]] = {
    LifecycleState.LEAD: {
        StateTransitionTrigger.REGISTER: LifecycleState.REGISTERED,
    },
    LifecycleState.REGISTERED: {
        StateTransitionTrigger.FIRST_ORDER: LifecycleState.REPEAT,
    },
    LifecycleState.FIRST_ORDER_PENDING: {
        StateTransitionTrigger.FIRST_ORDER: LifecycleState.REPEAT,
    },
    LifecycleState.REPEAT: {
        StateTransitionTrigger.REPEAT_ORDER:             LifecycleState.REPEAT,
        StateTransitionTrigger.HIGH_FREQUENCY_MILESTONE: LifecycleState.HIGH_FREQUENCY,
        StateTransitionTrigger.CHURN_WARNING:            LifecycleState.AT_RISK,
    },
    LifecycleState.HIGH_FREQUENCY: {
        StateTransitionTrigger.VIP_UPGRADE:              LifecycleState.VIP,
        StateTransitionTrigger.CHURN_WARNING:            LifecycleState.AT_RISK,
        StateTransitionTrigger.INACTIVITY_LONG:          LifecycleState.DORMANT,
    },
    LifecycleState.VIP: {
        StateTransitionTrigger.CHURN_WARNING:            LifecycleState.AT_RISK,
        StateTransitionTrigger.INACTIVITY_LONG:          LifecycleState.AT_RISK,
    },
    LifecycleState.AT_RISK: {
        StateTransitionTrigger.REPEAT_ORDER:             LifecycleState.REPEAT,
        StateTransitionTrigger.INACTIVITY_LONG:          LifecycleState.DORMANT,
    },
    LifecycleState.DORMANT: {
        StateTransitionTrigger.REPEAT_ORDER:             LifecycleState.REPEAT,
        StateTransitionTrigger.INACTIVITY_LONG:          LifecycleState.LOST,
    },
    LifecycleState.LOST: {},  # terminal
}


# ── 纯函数 ────────────────────────────────────────────────────────────────────

def classify_lifecycle(
    recency_days: int,
    frequency_30d: int,
    total_orders: int,
    is_registered: bool,
    monetary_fen: int = 0,
    is_vip: bool = False,
) -> LifecycleState:
    """
    根据可观测指标推断生命周期状态（无副作用）。

    Args:
        recency_days:  距上次下单天数（未下单过则取自注册日）
        frequency_30d: 近30天下单次数
        total_orders:  历史总订单数
        is_registered: 是否已注册会员
        monetary_fen:  累计消费金额（分）
        is_vip:        是否被明确标记为VIP
    """
    if not is_registered:
        return LifecycleState.LEAD

    if total_orders == 0:
        return LifecycleState.FIRST_ORDER_PENDING

    # 流失类（recency优先）
    if recency_days > _DORMANT_DAYS:
        return LifecycleState.LOST if recency_days > _DORMANT_DAYS * 2 else LifecycleState.DORMANT
    if recency_days > _CHURN_WARNING_DAYS:
        return LifecycleState.AT_RISK

    # 活跃类
    if is_vip or monetary_fen >= _VIP_MONETARY_FEN * 5:
        return LifecycleState.VIP
    if frequency_30d >= _HIGH_FREQ_ORDERS:
        return LifecycleState.HIGH_FREQUENCY

    return LifecycleState.REPEAT


def next_state(
    from_state: LifecycleState,
    trigger: StateTransitionTrigger,
) -> Optional[LifecycleState]:
    """
    查询状态转移表，返回目标状态；非法转移返回 None。

    >>> next_state(LifecycleState.LEAD, StateTransitionTrigger.REGISTER)
    <LifecycleState.REGISTERED: 'registered'>
    >>> next_state(LifecycleState.LOST, StateTransitionTrigger.REGISTER) is None
    True
    """
    return TRANSITION_RULES.get(from_state, {}).get(trigger)


def is_terminal(state: LifecycleState) -> bool:
    """LOST 是唯一 terminal 状态（不可再转移）。"""
    return state == LifecycleState.LOST


# ── 服务类 ────────────────────────────────────────────────────────────────────

class LifecycleStateMachine:
    """
    会员生命周期状态机服务。

    依赖关系：
      - AsyncSession（读写 private_domain_members + member_lifecycle_histories）
    """

    async def detect_state(
        self,
        customer_id: str,
        store_id: str,
        db: AsyncSession,
    ) -> LifecycleState:
        """
        从 DB 查询可观测指标，推断当前生命周期状态。

        优先读取 private_domain_members.lifecycle_state（若已有记录）。
        若记录不存在，则从 orders 聚合 RFM 推断。
        """
        # 1. 先读已保存的 lifecycle_state
        row = await db.execute(
            text("""
                SELECT lifecycle_state, recency_days, frequency, monetary
                FROM private_domain_members
                WHERE store_id = :store_id AND customer_id = :customer_id
                LIMIT 1
            """),
            {"store_id": store_id, "customer_id": customer_id},
        )
        member = await _maybe_await(row.fetchone())

        if member and member.lifecycle_state:
            try:
                return LifecycleState(member.lifecycle_state)
            except ValueError:
                pass  # 未知状态值，继续从数据推断

        # 2. 从 orders 聚合 RFM
        stats_row = await db.execute(
            text("""
                SELECT
                    COUNT(*)                                          AS total_orders,
                    COALESCE(MIN(
                        EXTRACT(DAY FROM NOW() - MAX(created_at))
                    ), 9999)::int                                      AS recency_days,
                    COUNT(*) FILTER (
                        WHERE created_at >= NOW() - (:window * INTERVAL '1 day')
                    )                                                 AS frequency_30d,
                    COALESCE(SUM(total_amount), 0)::int               AS monetary_fen
                FROM orders
                WHERE store_id = :store_id
                  AND (customer_id = :customer_id OR customer_phone = :customer_id)
            """),
            {
                "store_id": store_id,
                "customer_id": customer_id,
                "window": _HIGH_FREQ_WINDOW,
            },
        )
        stats = await _maybe_await(stats_row.fetchone())

        total_orders  = int(stats.total_orders)  if stats else 0
        recency_days  = int(stats.recency_days)  if stats else 9999
        frequency_30d = int(stats.frequency_30d) if stats else 0
        monetary_fen  = int(stats.monetary_fen)  if stats else 0
        is_registered = member is not None

        return classify_lifecycle(
            recency_days=recency_days,
            frequency_30d=frequency_30d,
            total_orders=total_orders,
            is_registered=is_registered,
            monetary_fen=monetary_fen,
        )

    async def apply_trigger(
        self,
        customer_id: str,
        store_id: str,
        trigger: StateTransitionTrigger,
        db: AsyncSession,
        changed_by: str = "system",
        reason: Optional[str] = None,
    ) -> Dict:
        """
        应用状态转移触发器：
          1. 读取当前状态（detect_state）
          2. 查询 TRANSITION_RULES
          3. 更新 private_domain_members.lifecycle_state
          4. 写入 MemberLifecycleHistory 审计记录
          5. 返回转移结果

        Returns:
            {
                "from_state": str,
                "to_state": str,
                "trigger": str,
                "transitioned": bool,  # False = 非法转移（无副作用）
                "reason": str,
            }
        """
        current = await self.detect_state(customer_id, store_id, db)
        target  = next_state(current, trigger)

        if target is None:
            logger.info(
                "lifecycle.apply_trigger.illegal",
                customer_id=customer_id,
                store_id=store_id,
                from_state=current.value,
                trigger=trigger.value,
            )
            return {
                "from_state": current.value,
                "to_state": current.value,
                "trigger": trigger.value,
                "transitioned": False,
                "reason": f"非法转移：{current.value} + {trigger.value} 无对应规则",
            }

        # 更新 private_domain_members.lifecycle_state（upsert）
        await db.execute(
            text("""
                UPDATE private_domain_members
                SET lifecycle_state = :state, lifecycle_state_updated_at = NOW()
                WHERE store_id = :store_id AND customer_id = :customer_id
            """),
            {"state": target.value, "store_id": store_id, "customer_id": customer_id},
        )

        # 写入审计历史（只追加）
        history = MemberLifecycleHistory(
            store_id=store_id,
            customer_id=customer_id,
            from_state=current.value,
            to_state=target.value,
            trigger=trigger.value,
            changed_by=changed_by,
            changed_at=datetime.utcnow(),
            reason=reason,
        )
        await _maybe_await(db.add(history))
        await db.commit()

        logger.info(
            "lifecycle.apply_trigger.success",
            customer_id=customer_id,
            store_id=store_id,
            from_state=current.value,
            to_state=target.value,
            trigger=trigger.value,
        )
        return {
            "from_state": current.value,
            "to_state": target.value,
            "trigger": trigger.value,
            "transitioned": True,
            "reason": reason,
        }

    async def get_history(
        self,
        customer_id: str,
        store_id: str,
        db: AsyncSession,
        limit: int = 20,
    ) -> list:
        """返回会员最近的状态变更历史（按时间倒序）。"""
        rows = await db.execute(
            text("""
                SELECT from_state, to_state, trigger, changed_by, changed_at, reason
                FROM member_lifecycle_histories
                WHERE store_id = :store_id AND customer_id = :customer_id
                ORDER BY changed_at DESC
                LIMIT :limit
            """),
            {"store_id": store_id, "customer_id": customer_id, "limit": limit},
        )
        records = await _maybe_await(rows.fetchall())
        return [dict(r._mapping) for r in (records or [])]
