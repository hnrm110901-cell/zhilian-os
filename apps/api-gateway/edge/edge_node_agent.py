#!/usr/bin/env python3
"""
Minimal Raspberry Pi 5 edge node agent for Zhilian OS.

First version goals:
- bootstrap from environment
- register edge node to API Gateway
- periodically report health status
- persist node_id locally for restart survival
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional


logging.basicConfig(
    level=os.getenv("EDGE_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("zhilian-edge-agent")


class EdgeAgentConfig:
    def __init__(self) -> None:
        self.api_base_url = self._required("EDGE_API_BASE_URL").rstrip("/")
        self.api_token = self._required("EDGE_API_TOKEN")
        self.store_id = self._required("EDGE_STORE_ID")
        self.device_name = os.getenv("EDGE_DEVICE_NAME") or socket.gethostname()
        self.network_mode = os.getenv("EDGE_NETWORK_MODE", "cloud")
        self.status_interval = int(os.getenv("EDGE_STATUS_INTERVAL_SECONDS", "30"))
        self.state_dir = Path(os.getenv("EDGE_STATE_DIR", "/var/lib/zhilian-edge"))
        self.state_file = self.state_dir / "node_state.json"
        self.queue_db_file = self.state_dir / "status_queue.db"
        self.queue_flush_batch_size = int(os.getenv("EDGE_QUEUE_FLUSH_BATCH_SIZE", "20"))
        self.command_poll_batch_size = int(os.getenv("EDGE_COMMAND_POLL_BATCH_SIZE", "10"))
        self.shokz_callback_port = int(
            os.getenv("EDGE_SHOKZ_CALLBACK_PORT")
            or os.getenv("SHOKZ_CALLBACK_PORT")
            or "9781"
        )
        self.shokz_callback_secret = (
            os.getenv("EDGE_SHOKZ_CALLBACK_SECRET")
            or os.getenv("SHOKZ_CALLBACK_SECRET")
            or ""
        ).strip()

    @staticmethod
    def _required(name: str) -> str:
        value = os.getenv(name, "").strip()
        if not value:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return value


class EdgeNodeAgent:
    def __init__(self, config: EdgeAgentConfig) -> None:
        self.config = config
        self.node_id: Optional[str] = None
        self.device_secret: Optional[str] = None
        self.last_queue_error: Optional[str] = None
        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self._init_queue_db()
        self._load_state()

    def _init_queue_db(self) -> None:
        with sqlite3.connect(self.config.queue_db_file) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_status_updates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                )
                """
            )
            conn.commit()

    def _load_state(self) -> None:
        if not self.config.state_file.exists():
            return
        try:
            data = json.loads(self.config.state_file.read_text(encoding="utf-8"))
            self.node_id = data.get("node_id")
            self.device_secret = data.get("device_secret")
        except Exception as exc:
            logger.warning("failed to load local state: %s", exc)

    def _save_state(self) -> None:
        payload = {
            "node_id": self.node_id,
            "device_secret": self.device_secret,
            "updated_at": int(time.time()),
        }
        self.config.state_file.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _headers(self, use_device_secret: bool = True) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if use_device_secret and self.device_secret:
            headers["X-Edge-Node-Secret"] = self.device_secret
        else:
            headers["Authorization"] = f"Bearer {self.config.api_token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        use_device_secret: bool = True,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.config.api_base_url}{path}"
        if params:
            encoded = urllib.parse.urlencode(params)
            url = f"{url}?{encoded}"

        body: Optional[bytes] = None
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=True).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers=self._headers(use_device_secret=use_device_secret),
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"{method} {path} failed: {exc.code} {raw}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc}") from exc

    def _enqueue_status_update(self, payload: Dict[str, Any], error: str) -> None:
        self.last_queue_error = error[:500]
        with sqlite3.connect(self.config.queue_db_file) as conn:
            conn.execute(
                """
                INSERT INTO pending_status_updates (payload, created_at, attempts, last_error)
                VALUES (?, ?, ?, ?)
                """,
                (json.dumps(payload, ensure_ascii=True), int(time.time()), 1, error[:500]),
            )
            conn.commit()

    def _get_pending_updates(self, limit: Optional[int] = None) -> list[Dict[str, Any]]:
        batch_size = limit or self.config.queue_flush_batch_size
        with sqlite3.connect(self.config.queue_db_file) as conn:
            rows = conn.execute(
                """
                SELECT id, payload, attempts
                FROM pending_status_updates
                ORDER BY id ASC
                LIMIT ?
                """,
                (batch_size,),
            ).fetchall()
        return [
            {
                "id": row[0],
                "payload": json.loads(row[1]),
                "attempts": row[2],
            }
            for row in rows
        ]

    def _delete_pending_update(self, queue_id: int) -> None:
        with sqlite3.connect(self.config.queue_db_file) as conn:
            conn.execute("DELETE FROM pending_status_updates WHERE id = ?", (queue_id,))
            conn.commit()

    def _mark_pending_retry(self, queue_id: int, error: str) -> None:
        with sqlite3.connect(self.config.queue_db_file) as conn:
            conn.execute(
                """
                UPDATE pending_status_updates
                SET attempts = attempts + 1, last_error = ?
                WHERE id = ?
                """,
                (error[:500], queue_id),
            )
            conn.commit()

    def _pending_status_count(self) -> int:
        with sqlite3.connect(self.config.queue_db_file) as conn:
            row = conn.execute("SELECT COUNT(*) FROM pending_status_updates").fetchone()
        return int(row[0]) if row else 0

    def register(self) -> str:
        ip_address = self._get_ip_address()
        mac_address = self._get_mac_address()
        logger.info("registering edge node store_id=%s device_name=%s", self.config.store_id, self.config.device_name)
        payload = self._request(
            "POST",
            "/api/v1/hardware/edge-node/register",
            {
                "store_id": self.config.store_id,
                "device_name": self.config.device_name,
                "ip_address": ip_address,
                "mac_address": mac_address,
            },
            use_device_secret=False,
        )
        node = payload.get("node", {})
        node_id = node.get("node_id")
        if not node_id:
            raise RuntimeError(f"register response missing node_id: {payload}")
        self.node_id = node_id
        self.device_secret = payload.get("device_secret")
        self._save_state()
        logger.info("edge node registered node_id=%s", self.node_id)
        self.switch_network_mode()
        return node_id

    def ensure_registered(self) -> str:
        if self.node_id:
            return self.node_id
        return self.register()

    def switch_network_mode(self) -> None:
        if not self.node_id:
            return
        self._request(
            "POST",
            f"/api/v1/hardware/edge-node/{self.node_id}/network-mode",
            {"mode": self.config.network_mode},
        )

    def _post_status_payload(self, payload: Dict[str, Any]) -> None:
        node_id = self.ensure_registered()
        try:
            self._request(
                "POST",
                f"/api/v1/hardware/edge-node/{node_id}/status",
                payload,
            )
        except RuntimeError as exc:
            if "401" not in str(exc) and "403" not in str(exc):
                raise
            logger.warning("device secret rejected, re-registering edge node")
            self.node_id = None
            self.device_secret = None
            self._save_state()
            node_id = self.register()
            self._request(
                "POST",
                f"/api/v1/hardware/edge-node/{node_id}/status",
                payload,
            )

    def _local_shokz_request(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"http://127.0.0.1:{self.config.shokz_callback_port}/shokz/callback"
        body = json.dumps(
            {
                "action": action,
                "device_id": payload.get("device_id"),
                "store_id": self.config.store_id,
                "edge_node_id": self.node_id,
                "payload": payload,
            },
            ensure_ascii=True,
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.config.shokz_callback_secret:
            headers["X-Edge-Callback-Secret"] = self.config.shokz_callback_secret
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    def _execute_edge_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        command_type = command.get("command_type")
        payload = command.get("payload") or {}
        if command_type in {"connect_device", "disconnect_device", "voice_output"}:
            return self._local_shokz_request(command_type, payload)
        raise RuntimeError(f"unsupported edge command: {command_type}")

    def process_command_queue(self) -> int:
        node_id = self.ensure_registered()
        response = self._request(
            "GET",
            f"/api/v1/hardware/edge-node/{node_id}/commands",
            {"limit": self.config.command_poll_batch_size},
        )
        commands = response.get("commands", [])
        completed = 0

        for command in commands:
            command_id = command["command_id"]
            try:
                result = self._execute_edge_command(command)
                self._request(
                    "POST",
                    f"/api/v1/hardware/edge-node/{node_id}/commands/{command_id}/ack",
                    json_body={
                        "status": "completed",
                        "result": result,
                    },
                )
                completed += 1
            except Exception as exc:
                self._request(
                    "POST",
                    f"/api/v1/hardware/edge-node/{node_id}/commands/{command_id}/ack",
                    json_body={
                        "status": "failed",
                        "last_error": str(exc),
                    },
                )
                logger.warning("edge command failed command_id=%s error=%s", command_id, exc)
        return completed

    def flush_pending_statuses(self) -> int:
        flushed = 0
        for item in self._get_pending_updates():
            try:
                self._post_status_payload(item["payload"])
            except Exception as exc:
                self._mark_pending_retry(item["id"], str(exc))
                self.last_queue_error = str(exc)[:500]
                logger.warning("failed to flush queued status update: %s", exc)
                break
            self._delete_pending_update(item["id"])
            flushed += 1
        if flushed and self._pending_status_count() == 0:
            self.last_queue_error = None
        return flushed

    def update_status(self) -> None:
        self.ensure_registered()
        flushed = self.flush_pending_statuses()
        payload = self._collect_status()
        try:
            self._post_status_payload(payload)
            if self._pending_status_count() == 0:
                self.last_queue_error = None
            logger.info(
                "status updated node_id=%s flushed_pending=%s pending_queue=%s",
                self.node_id,
                flushed,
                self._pending_status_count(),
            )
        except Exception as exc:
            self._enqueue_status_update(payload, str(exc))
            logger.warning(
                "status update queued node_id=%s pending_queue=%s error=%s",
                self.node_id,
                self._pending_status_count(),
                exc,
            )

    def run_forever(self) -> None:
        self.ensure_registered()
        while True:
            try:
                self.update_status()
                self.process_command_queue()
            except Exception as exc:
                logger.error("status update failed: %s", exc)
            time.sleep(self.config.status_interval)

    def _collect_status(self) -> Dict[str, Any]:
        return {
            "cpu_usage": round(self._get_cpu_usage(), 2),
            "memory_usage": round(self._get_memory_usage(), 2),
            "disk_usage": round(self._get_disk_usage(), 2),
            "temperature": round(self._get_temperature(), 2),
            "uptime_seconds": int(self._get_uptime_seconds()),
            "pending_status_queue": self._pending_status_count(),
            "last_queue_error": self.last_queue_error,
        }

    @staticmethod
    def _get_ip_address() -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            sock.close()

    @staticmethod
    def _get_mac_address() -> str:
        mac = uuid.getnode()
        return ":".join(f"{(mac >> ele) & 0xFF:02x}" for ele in range(40, -1, -8))

    @staticmethod
    def _read_meminfo() -> Dict[str, int]:
        values: Dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            parts = raw.strip().split()
            values[key] = int(parts[0])
        return values

    def _get_memory_usage(self) -> float:
        try:
            info = self._read_meminfo()
            total = info.get("MemTotal", 0)
            available = info.get("MemAvailable", 0)
            if total <= 0:
                return 0.0
            used = total - available
            return used * 100.0 / total
        except Exception:
            return 0.0

    def _get_disk_usage(self) -> float:
        try:
            stats = os.statvfs("/")
            total = stats.f_blocks * stats.f_frsize
            free = stats.f_bavail * stats.f_frsize
            used = total - free
            return used * 100.0 / total if total else 0.0
        except Exception:
            return 0.0

    def _get_temperature(self) -> float:
        candidates = [
            Path("/sys/class/thermal/thermal_zone0/temp"),
            Path("/sys/class/hwmon/hwmon0/temp1_input"),
        ]
        for path in candidates:
            try:
                raw = path.read_text(encoding="utf-8").strip()
                return float(raw) / 1000.0
            except Exception:
                continue
        return 0.0

    def _get_uptime_seconds(self) -> float:
        try:
            return float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        except Exception:
            return 0.0

    def _get_cpu_usage(self) -> float:
        try:
            load1, _, _ = os.getloadavg()
            cpus = max(os.cpu_count() or 1, 1)
            return min((load1 / cpus) * 100.0, 100.0)
        except Exception:
            return 0.0


def main(argv: list[str]) -> int:
    once = "--once" in argv
    try:
        agent = EdgeNodeAgent(EdgeAgentConfig())
        if once:
            agent.ensure_registered()
            agent.update_status()
            agent.process_command_queue()
            return 0
        agent.run_forever()
        return 0
    except Exception as exc:
        logger.error("edge agent failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
