"""
Agent Memory Bus - Agent共享记忆总线

Redis Streams-based pub/sub so agents can share findings across a store
without direct coupling. Each finding is a lightweight JSON entry on a
per-store stream.

Stream key: agent:stream:{store_id}
Entry fields: agent, action, summary, confidence, data (JSON), ts

Usage:
    from src.services.agent_memory_bus import agent_memory_bus

    # publish a finding
    await agent_memory_bus.publish(
        store_id="store_001",
        agent_id="inventory",
        action="low_stock_alert",
        summary="辣椒库存不足，预计4小时内耗尽",
        confidence=0.92,
        data={"item": "chili", "remaining": 5},
    )

    # read recent findings from all agents for this store
    findings = await agent_memory_bus.subscribe(store_id="store_001", last_n=20)
"""
import json
import os
from typing import Any, Dict, List, Optional

import structlog

from ..core.clock import now_utc
from ..core.config import settings

logger = structlog.get_logger()

# Max entries kept per store stream (older entries auto-trimmed)
STREAM_MAX_LEN = int(os.getenv("AGENT_MEMORY_STREAM_MAX_LEN", "200"))
# Default TTL for the stream key (seconds) — 24 hours
STREAM_TTL = int(os.getenv("AGENT_MEMORY_STREAM_TTL", "86400"))


class AgentMemoryBus:
    """Redis Streams-based shared memory bus for agents."""

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _stream_key(self, store_id: str) -> str:
        return f"agent:stream:{store_id}"

    async def publish(
        self,
        store_id: str,
        agent_id: str,
        action: str,
        summary: str,
        confidence: float = 0.0,
        data: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Publish a finding to the store's agent stream.

        Returns the Redis stream entry ID, or None on failure.
        """
        try:
            r = await self._get_redis()
            key = self._stream_key(store_id)

            entry = {
                "agent": agent_id,
                "action": action,
                "summary": summary,
                "confidence": str(round(confidence, 4)),
                "data": json.dumps(data or {}, ensure_ascii=False),
                "ts": now_utc().isoformat(),
            }

            entry_id = await r.xadd(key, entry, maxlen=STREAM_MAX_LEN, approximate=True)
            # Refresh TTL so active stores keep their stream alive
            await r.expire(key, STREAM_TTL)

            logger.info(
                "agent_memory_published",
                store_id=store_id,
                agent_id=agent_id,
                action=action,
                entry_id=entry_id,
            )
            return entry_id

        except Exception as e:
            logger.warning("agent_memory_publish_failed", store_id=store_id, error=str(e))
            return None

    async def subscribe(
        self,
        store_id: str,
        last_n: int = 20,
        agent_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Read the last N findings from the store's agent stream.

        Args:
            store_id:     Store to read from.
            last_n:       How many recent entries to return (newest first).
            agent_filter: If set, only return findings from this agent.

        Returns:
            List of finding dicts, newest first.
        """
        try:
            r = await self._get_redis()
            key = self._stream_key(store_id)

            # xrevrange returns entries newest-first
            raw = await r.xrevrange(key, count=last_n * 3 if agent_filter else last_n)

            findings = []
            for entry_id, fields in raw:
                if agent_filter and fields.get("agent") != agent_filter:
                    continue
                try:
                    finding = {
                        "entry_id": entry_id,
                        "agent": fields.get("agent"),
                        "action": fields.get("action"),
                        "summary": fields.get("summary"),
                        "confidence": float(fields.get("confidence", 0)),
                        "data": json.loads(fields.get("data", "{}")),
                        "ts": fields.get("ts"),
                    }
                    findings.append(finding)
                    if len(findings) >= last_n:
                        break
                except Exception:
                    continue

            return findings

        except Exception as e:
            logger.warning("agent_memory_subscribe_failed", store_id=store_id, error=str(e))
            return []

    async def get_peer_context(
        self,
        store_id: str,
        requesting_agent: str,
        last_n: int = 10,
    ) -> str:
        """
        Return a formatted string of recent peer findings for LLM context injection.

        Excludes findings from the requesting agent itself.
        """
        findings = await self.subscribe(store_id, last_n=last_n * 2)
        peer_findings = [f for f in findings if f["agent"] != requesting_agent][:last_n]

        if not peer_findings:
            return ""

        lines = ["[同店其他Agent最新发现]"]
        for f in peer_findings:
            conf = f"{f['confidence']:.0%}" if f["confidence"] else ""
            lines.append(f"- [{f['agent']}] {f['action']}: {f['summary']}{' (' + conf + ')' if conf else ''}")

        return "\n".join(lines)

    async def stream_length(self, store_id: str) -> int:
        """Return current number of entries in the store's stream."""
        try:
            r = await self._get_redis()
            return await r.xlen(self._stream_key(store_id))
        except Exception:
            return 0


# Singleton
agent_memory_bus = AgentMemoryBus()
