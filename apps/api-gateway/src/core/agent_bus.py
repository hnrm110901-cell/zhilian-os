"""
Agent 间通信协议 — AgentBus

架构：
  AgentMessage   — 消息信封（请求）
  AgentReply     — 响应信封
  AgentBus       — 单例消息总线，负责路由和生命周期管理
  BusAwareMixin  — 让 Agent 子类获得 call_agent / broadcast_to 快捷方法

用法示例：
  # 1. 同步调用（OpsAgent 向 DecisionAgent 请求业务影响评估）
  reply = await bus.send(AgentMessage(
      from_agent="ops",
      to_agent="decision",
      action="analyze_revenue_anomaly",
      store_id="S001",
      payload={"current_revenue": "9800", "expected_revenue": "12000"},
      priority=MessagePriority.P0,
  ))

  # 2. 广播（DecisionAgent 向所有相关 Agent 通知库存告警）
  replies = await bus.broadcast(
      AgentMessage(from_agent="decision", to_agent="*", action="inventory_alert", ...),
      to_agents=["schedule", "inventory", "ops"],
  )

  # 3. 即发即忘（触发 Celery 异步任务）
  msg_id = await bus.fire_and_forget(msg)

优先级：
  P0 = 10  (critical, 运维故障 / 食安违规)
  P1 = 7   (high,     营收异常 / 库存告警)
  P2 = 5   (normal,   常规决策建议)
  P3 = 3   (low,      日常巡检 / 统计)
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Type

import structlog

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# 优先级常量
# ─────────────────────────────────────────────────────────────────────────────

class MessagePriority(IntEnum):
    P0 = 10   # critical — 运维故障、食安违规
    P1 = 7    # high     — 营收异常、库存短缺
    P2 = 5    # normal   — 常规决策、排班建议
    P3 = 3    # low      — 日常巡检、统计任务


# ─────────────────────────────────────────────────────────────────────────────
# 消息信封
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentMessage:
    """
    Agent 间通信的标准请求信封。

    字段说明：
      from_agent  — 发送方 Agent 类型（schedule/order/ops/decision/…）
      to_agent    — 目标 Agent 类型（或 "*" 广播用占位，由 broadcast 方法解析）
      action      — 目标 Agent 支持的操作名称
      payload     — 操作参数（等价于 execute(action, params) 中的 params）
      store_id    — 门店 ID，自动注入到 payload 中（如果 payload 未包含）
      priority    — 优先级（MessagePriority，影响超时与日志级别）
      timeout_s   — 本条消息的处理超时（秒），None 表示使用全局默认值
      msg_id      — 消息唯一 ID（UUID4，自动生成）
      trace_id    — 分布式追踪 ID；同一 request chain 共用同一个 trace_id
      reply_to    — 本消息是对哪个 msg_id 的回复（用于响应链路追踪）
      created_at  — ISO 8601 UTC 时间戳
    """
    from_agent: str
    to_agent: str
    action: str
    payload: Dict[str, Any]
    store_id: str = ""
    priority: int = MessagePriority.P2
    timeout_s: Optional[int] = None
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def enrich_payload(self) -> Dict[str, Any]:
        """返回注入了 store_id 的参数字典（不修改原 payload）。"""
        if self.store_id and "store_id" not in self.payload:
            return {**self.payload, "store_id": self.store_id}
        return self.payload


@dataclass
class AgentReply:
    """
    Agent 间通信的标准响应信封。

    字段说明：
      request_id      — 对应的 AgentMessage.msg_id
      from_agent      — 响应方 Agent 类型
      success         — 是否成功
      data            — 业务数据（AgentResponse.data）
      error           — 错误描述（失败时填充）
      execution_time  — Agent 实际执行耗时（秒）
      trace_id        — 与请求保持相同的 trace_id
      msg_id          — 本响应的唯一 ID
      created_at      — ISO 8601 UTC 时间戳
    """
    request_id: str
    from_agent: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    trace_id: str = ""
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def unwrap(self) -> Any:
        """成功时返回 data，失败时抛出 RuntimeError。"""
        if not self.success:
            raise RuntimeError(
                f"AgentReply error from {self.from_agent}: {self.error}"
            )
        return self.data


# ─────────────────────────────────────────────────────────────────────────────
# 默认超时配置（按优先级）
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_TIMEOUT: Dict[int, int] = {
    MessagePriority.P0: 10,   # P0 故障：10 秒内必须得到响应
    MessagePriority.P1: 20,   # P1 告警：20 秒
    MessagePriority.P2: 30,   # P2 常规：30 秒
    MessagePriority.P3: 60,   # P3 低优：60 秒
}


def _resolve_timeout(msg: AgentMessage) -> int:
    """解析消息的实际超时秒数。"""
    if msg.timeout_s is not None:
        return msg.timeout_s
    # 向下取最近优先级档
    for threshold in sorted(_DEFAULT_TIMEOUT.keys(), reverse=True):
        if msg.priority >= threshold:
            return _DEFAULT_TIMEOUT[threshold]
    return 30


# ─────────────────────────────────────────────────────────────────────────────
# Agent 工厂注册表
# ─────────────────────────────────────────────────────────────────────────────

def _default_agent_factories() -> Dict[str, Callable]:
    """
    返回默认 Agent 工厂函数字典。

    工厂函数采用懒加载（每次调用创建新实例），避免循环导入和共享状态。
    新增 Agent 只需在此注册，无需修改 AgentBus 核心逻辑。
    """
    def _make(module_path: str, class_name: str):
        def factory():
            import importlib
            mod = importlib.import_module(module_path)
            return getattr(mod, class_name)()
        return factory

    _base = "src.agents"
    return {
        "schedule":    _make(f"{_base}.schedule_agent",    "ScheduleAgent"),
        "order":       _make(f"{_base}.order_agent",       "OrderAgent"),
        "inventory":   _make(f"{_base}.inventory_agent",   "InventoryAgent"),
        "service":     _make(f"{_base}.schedule_agent",    "ScheduleAgent"),  # 兼容占位
        "training":    _make(f"{_base}.schedule_agent",    "ScheduleAgent"),  # 兼容占位
        "decision":    _make(f"{_base}.decision_agent",    "DecisionAgent"),
        "reservation": _make(f"{_base}.schedule_agent",    "ScheduleAgent"),  # 兼容占位
        "ops":         _make(f"{_base}.ops_agent",         "OpsAgent"),
        "performance": _make(f"{_base}.performance_agent", "PerformanceAgent"),
        "quality":     _make(f"{_base}.quality_agent",     "QualityAgent"),
        "kpi":         _make(f"{_base}.kpi_agent",         "KpiAgent"),
        "fct":         _make(f"{_base}.fct_agent",         "FctAgent"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# AgentBus — 单例消息总线
# ─────────────────────────────────────────────────────────────────────────────

class AgentBus:
    """
    Agent 间通信总线（单例）。

    线程安全：asyncio 单线程，无需加锁。
    Agent 实例：不缓存（各 Agent 无持久状态），每次调用按需实例化。

    使用：
        bus = AgentBus.get()
        reply = await bus.send(msg)
    """

    _instance: Optional["AgentBus"] = None

    def __init__(self) -> None:
        self._factories: Dict[str, Callable] = _default_agent_factories()

    @classmethod
    def get(cls) -> "AgentBus":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 注册 & 查询 ───────────────────────────────────────────────────────────

    def register(self, agent_type: str, factory: Callable) -> None:
        """
        注册（或覆盖）一个 Agent 工厂函数。

        factory: 无参可调用对象，返回 BaseAgent 实例。
        测试时可用此方法注入 Mock Agent。
        """
        self._factories[agent_type] = factory
        logger.info("agent_bus.registered", agent_type=agent_type)

    def registered_agents(self) -> List[str]:
        """返回已注册的 Agent 类型列表。"""
        return list(self._factories.keys())

    def _make_agent(self, agent_type: str):
        factory = self._factories.get(agent_type)
        if factory is None:
            raise KeyError(
                f"AgentBus: 未知 Agent 类型 '{agent_type}'。"
                f"已注册: {self.registered_agents()}"
            )
        return factory()

    # ── 核心通信方法 ──────────────────────────────────────────────────────────

    async def send(self, msg: AgentMessage) -> AgentReply:
        """
        同步请求-响应：向目标 Agent 发送消息并等待结果。

        - 自动注入 store_id 到 payload
        - 超时由优先级决定（可被 msg.timeout_s 覆盖）
        - P0 消息超时时返回 AgentReply(success=False) 而非抛出异常
        """
        timeout = _resolve_timeout(msg)
        log_ctx = dict(
            from_agent=msg.from_agent,
            to_agent=msg.to_agent,
            action=msg.action,
            store_id=msg.store_id,
            msg_id=msg.msg_id,
            trace_id=msg.trace_id,
            priority=msg.priority,
        )
        log_fn = logger.info if msg.priority >= MessagePriority.P1 else logger.debug
        log_fn("agent_bus.send", **log_ctx)

        agent = self._make_agent(msg.to_agent)
        params = msg.enrich_payload()

        try:
            response = await asyncio.wait_for(
                agent.execute(msg.action, params),
                timeout=float(timeout),
            )
            reply = AgentReply(
                request_id=msg.msg_id,
                from_agent=msg.to_agent,
                success=response.success,
                data=response.data,
                error=response.error,
                execution_time=getattr(response, "execution_time", 0.0),
                trace_id=msg.trace_id,
            )
            logger.debug(
                "agent_bus.reply",
                request_id=msg.msg_id,
                from_agent=msg.to_agent,
                success=reply.success,
                trace_id=msg.trace_id,
            )
            return reply

        except asyncio.TimeoutError:
            logger.error(
                "agent_bus.timeout",
                timeout_s=timeout,
                **log_ctx,
            )
            return AgentReply(
                request_id=msg.msg_id,
                from_agent=msg.to_agent,
                success=False,
                error=f"agent '{msg.to_agent}' timeout (>{timeout}s 超时)",
                trace_id=msg.trace_id,
            )

        except Exception as exc:
            logger.error("agent_bus.error", error=str(exc), **log_ctx)
            return AgentReply(
                request_id=msg.msg_id,
                from_agent=msg.to_agent,
                success=False,
                error=str(exc),
                trace_id=msg.trace_id,
            )

    async def broadcast(
        self,
        msg: AgentMessage,
        to_agents: List[str],
    ) -> List[AgentReply]:
        """
        并发广播：向多个 Agent 同时发送同一消息，收集所有回复。

        所有消息共用同一 trace_id，便于关联追踪。
        单个 Agent 失败不影响其他 Agent。
        """
        tasks = [
            self.send(
                AgentMessage(
                    from_agent=msg.from_agent,
                    to_agent=target,
                    action=msg.action,
                    payload=msg.payload,
                    store_id=msg.store_id,
                    priority=msg.priority,
                    timeout_s=msg.timeout_s,
                    trace_id=msg.trace_id,   # 共用 trace_id
                )
            )
            for target in to_agents
        ]
        replies = await asyncio.gather(*tasks, return_exceptions=False)
        logger.info(
            "agent_bus.broadcast.done",
            from_agent=msg.from_agent,
            targets=to_agents,
            succeeded=sum(1 for r in replies if r.success),
            trace_id=msg.trace_id,
        )
        return list(replies)

    async def fire_and_forget(self, msg: AgentMessage) -> str:
        """
        即发即忘：将消息投递到 Celery 异步任务队列，立即返回 msg_id。

        适合低优先级后台任务（P2/P3）。P0/P1 建议使用 send()。
        """
        queue = "high_priority" if msg.priority >= MessagePriority.P1 else "default"
        try:
            from .celery_tasks import celery_app
            celery_app.send_task(
                "src.core.celery_tasks.dispatch_agent_message",
                kwargs={
                    "from_agent": msg.from_agent,
                    "to_agent": msg.to_agent,
                    "action": msg.action,
                    "payload": msg.payload,
                    "store_id": msg.store_id,
                    "priority": msg.priority,
                    "trace_id": msg.trace_id,
                    "msg_id": msg.msg_id,
                },
                queue=queue,
                priority=msg.priority,
            )
            logger.info(
                "agent_bus.fire_and_forget",
                msg_id=msg.msg_id,
                to_agent=msg.to_agent,
                queue=queue,
            )
        except Exception as exc:
            logger.error("agent_bus.fire_and_forget.failed", error=str(exc), msg_id=msg.msg_id)
        return msg.msg_id


# ─────────────────────────────────────────────────────────────────────────────
# BusAwareMixin — 让 Agent 子类方便地调用总线
# ─────────────────────────────────────────────────────────────────────────────

class BusAwareMixin:
    """
    让 LLMEnhancedAgent 子类获得 call_agent / broadcast_to 快捷方法。

    用法：
        class OpsAgent(BusAwareMixin, LLMEnhancedAgent):
            async def _handle_critical_fault(self, store_id, fault_summary):
                reply = await self.call_agent(
                    to="decision",
                    action="analyze_revenue_anomaly",
                    payload={"current_revenue": "0", "expected_revenue": "15000"},
                    store_id=store_id,
                    priority=MessagePriority.P0,
                )
                return reply.data
    """

    # agent_type 由 LLMEnhancedAgent.__init__ 设置
    agent_type: str = "unknown"

    async def call_agent(
        self,
        to: str,
        action: str,
        payload: Dict[str, Any],
        store_id: str = "",
        priority: int = MessagePriority.P2,
        timeout_s: Optional[int] = None,
        trace_id: Optional[str] = None,
    ) -> AgentReply:
        """
        向另一个 Agent 发送同步请求并返回 AgentReply。
        """
        msg = AgentMessage(
            from_agent=self.agent_type,
            to_agent=to,
            action=action,
            payload=payload,
            store_id=store_id,
            priority=priority,
            timeout_s=timeout_s,
        )
        if trace_id:
            msg.trace_id = trace_id
        return await AgentBus.get().send(msg)

    async def broadcast_to(
        self,
        agents: List[str],
        action: str,
        payload: Dict[str, Any],
        store_id: str = "",
        priority: int = MessagePriority.P2,
    ) -> List[AgentReply]:
        """
        并发向多个 Agent 广播同一消息。
        """
        msg = AgentMessage(
            from_agent=self.agent_type,
            to_agent="*",
            action=action,
            payload=payload,
            store_id=store_id,
            priority=priority,
        )
        return await AgentBus.get().broadcast(msg, to_agents=agents)


# ─────────────────────────────────────────────────────────────────────────────
# 模块级便捷访问
# ─────────────────────────────────────────────────────────────────────────────

# 全局单例（可在任意模块直接 import 使用）
agent_bus = AgentBus.get()
