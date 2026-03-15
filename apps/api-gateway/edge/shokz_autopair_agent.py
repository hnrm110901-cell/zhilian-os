#!/usr/bin/env python3
"""
Shokz headset auto pair/connect agent for Raspberry Pi.

This process periodically scans for a fixed list of headset MACs and
attempts to pair, trust and connect them through bluetoothctl.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from typing import Iterable, List


logging.basicConfig(
    level=os.getenv("EDGE_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("zhilian-shokz-autopair")

MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def _parse_target_macs(raw_value: str) -> List[str]:
    targets: List[str] = []
    for part in raw_value.split(","):
        mac = part.strip().upper()
        if not mac:
            continue
        if not MAC_PATTERN.match(mac):
            logger.warning("ignore invalid Shokz MAC: %s", mac)
            continue
        targets.append(mac)
    return targets


class ShokzAutopairAgent:
    def __init__(self) -> None:
        self.target_macs = _parse_target_macs(os.getenv("SHOKZ_TARGET_MACS", ""))
        self.interval_seconds = int(os.getenv("SHOKZ_AUTO_CONNECT_INTERVAL_SECONDS", "30"))
        self.scan_seconds = int(os.getenv("SHOKZ_SCAN_SECONDS", "15"))

        if not self.target_macs:
            raise RuntimeError("Missing SHOKZ_TARGET_MACS")

    def _run_bluetoothctl(self, commands: Iterable[str], timeout: int = 60) -> str:
        payload = "\n".join(commands) + "\n"
        proc = subprocess.run(
            ["bluetoothctl"],
            input=payload,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return output

    def _scan(self) -> None:
        logger.info("starting bluetooth scan for %ss", self.scan_seconds)
        subprocess.run(
            [
                "bash",
                "-lc",
                f"timeout {self.scan_seconds + 5} bluetoothctl --timeout {self.scan_seconds} scan on >/dev/null 2>&1 || true",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def _info(self, mac: str) -> str:
        return self._run_bluetoothctl([f"info {mac}"])

    def _is_known(self, mac: str) -> bool:
        return "not available" not in self._info(mac).lower()

    def _is_connected(self, mac: str) -> bool:
        return "Connected: yes" in self._info(mac)

    def _ensure_device(self, mac: str) -> None:
        if self._is_connected(mac):
            logger.info("Shokz %s already connected", mac)
            return

        if not self._is_known(mac):
            logger.info("Shokz %s not visible yet", mac)
            return

        logger.info("pair/trust/connect Shokz %s", mac)
        output = self._run_bluetoothctl(
            [
                "power on",
                "agent on",
                "default-agent",
                f"pair {mac}",
                f"trust {mac}",
                f"connect {mac}",
                f"info {mac}",
            ],
            timeout=90,
        )
        if "Connected: yes" in output:
            logger.info("Shokz %s connected", mac)
        else:
            logger.warning("Shokz %s not connected yet", mac)

    def run_once(self) -> None:
        self._scan()
        for mac in self.target_macs:
            try:
                self._ensure_device(mac)
            except Exception as exc:
                logger.warning("failed to process Shokz %s: %s", mac, exc)

    def run_forever(self) -> None:
        logger.info("autopair agent started for %s", ", ".join(self.target_macs))
        while True:
            self.run_once()
            time.sleep(self.interval_seconds)


def main() -> int:
    agent = ShokzAutopairAgent()
    if "--once" in os.sys.argv[1:]:
        agent.run_once()
        return 0
    agent.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
