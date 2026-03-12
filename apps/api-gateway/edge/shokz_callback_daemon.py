#!/usr/bin/env python3
"""
Local Shokz callback daemon for Raspberry Pi edge nodes.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional


logging.basicConfig(
    level=os.getenv("EDGE_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("zhilian-edge-shokz")


class ShokzCallbackConfig:
    def __init__(self) -> None:
        self.bind_host = os.getenv("EDGE_SHOKZ_CALLBACK_BIND", "0.0.0.0")
        self.port = int(os.getenv("EDGE_SHOKZ_CALLBACK_PORT", "9781"))
        self.secret = os.getenv("EDGE_SHOKZ_CALLBACK_SECRET", "").strip()
        self.state_dir = Path(os.getenv("EDGE_STATE_DIR", "/var/lib/zhilian-edge"))
        self.state_file = self.state_dir / "shokz_state.json"


class ShokzCommandProcessor:
    def __init__(self, config: ShokzCallbackConfig) -> None:
        self.config = config
        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if not self.config.state_file.exists():
            return {"devices": {}, "history": []}
        try:
            return json.loads(self.config.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {"devices": {}, "history": []}

    def _save_state(self) -> None:
        self.config.state_file.write_text(
            json.dumps(self.state, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _append_history(self, record: Dict[str, Any]) -> None:
        history = self.state.setdefault("history", [])
        history.append(record)
        self.state["history"] = history[-200:]

    def _device_state(self, device_id: str) -> Dict[str, Any]:
        devices = self.state.setdefault("devices", {})
        return devices.setdefault(
            device_id,
            {
                "connected": False,
                "last_action": None,
                "last_text": None,
                "last_priority": None,
                "updated_at": None,
            },
        )

    def handle(self, action: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if action not in {"connect_device", "disconnect_device", "voice_output"}:
            raise ValueError(f"unsupported action: {action}")

        device_id = body.get("device_id")
        if not device_id:
            raise ValueError("missing device_id")

        payload = body.get("payload") or {}
        device = self._device_state(device_id)
        now = datetime.now().isoformat()

        if action == "connect_device":
            device["connected"] = True
        elif action == "disconnect_device":
            device["connected"] = False
        elif action == "voice_output":
            if not device["connected"]:
                raise ValueError(f"device not connected: {device_id}")
            device["last_text"] = payload.get("text")
            device["last_priority"] = payload.get("priority", "normal")

        device["last_action"] = action
        device["updated_at"] = now
        self._append_history(
            {
                "device_id": device_id,
                "action": action,
                "at": now,
                "store_id": body.get("store_id"),
                "edge_node_id": body.get("edge_node_id"),
                "payload": payload,
            }
        )
        self._save_state()

        return {
            "success": True,
            "action": action,
            "device_id": device_id,
            "device_state": device,
            "history_size": len(self.state.get("history", [])),
        }

    def health(self) -> Dict[str, Any]:
        return {
            "success": True,
            "service": "zhilian-edge-shokz",
            "devices": len(self.state.get("devices", {})),
            "history_size": len(self.state.get("history", [])),
            "state_file": str(self.config.state_file),
            "timestamp": int(time.time()),
        }


class ShokzCallbackHandler(BaseHTTPRequestHandler):
    processor: ShokzCommandProcessor
    config: ShokzCallbackConfig

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _write_json(self, status_code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorize(self) -> bool:
        if not self.config.secret:
            return True
        return self.headers.get("X-Edge-Callback-Secret", "") == self.config.secret

    def do_GET(self) -> None:
        if self.path != "/health":
            self._write_json(HTTPStatus.NOT_FOUND, {"success": False, "error": "not_found"})
            return
        self._write_json(HTTPStatus.OK, self.processor.health())

    def do_POST(self) -> None:
        if self.path != "/shokz/callback":
            self._write_json(HTTPStatus.NOT_FOUND, {"success": False, "error": "not_found"})
            return
        if not self._authorize():
            self._write_json(HTTPStatus.FORBIDDEN, {"success": False, "error": "forbidden"})
            return
        try:
            body = self._read_json()
            result = self.processor.handle(body.get("action", ""), body)
            self._write_json(HTTPStatus.OK, result)
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"success": False, "error": str(exc)})
        except Exception as exc:
            logger.error("shokz callback failed: %s", exc)
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"success": False, "error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), format % args)


def build_server(config: Optional[ShokzCallbackConfig] = None) -> ThreadingHTTPServer:
    daemon_config = config or ShokzCallbackConfig()
    processor = ShokzCommandProcessor(daemon_config)
    handler = type(
        "ConfiguredShokzCallbackHandler",
        (ShokzCallbackHandler,),
        {"processor": processor, "config": daemon_config},
    )
    return ThreadingHTTPServer((daemon_config.bind_host, daemon_config.port), handler)


def main(argv: list[str]) -> int:
    if "--once-health" in argv:
        processor = ShokzCommandProcessor(ShokzCallbackConfig())
        print(json.dumps(processor.health(), ensure_ascii=True))
        return 0

    server = build_server()
    logger.info(
        "starting shokz callback daemon host=%s port=%s",
        server.server_address[0],
        server.server_address[1],
    )
    try:
        server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
