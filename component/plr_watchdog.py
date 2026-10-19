# moonraker-plr: Moonraker component that brings a print back after the
# printer board (MCU) dropped off USB.
#
# When Klippy shuts down because it lost the connection to the MCU, this
# component waits until the MCU's serial device is present again, issues a
# FIRMWARE_RESTART, and as soon as Klippy is ready runs a "hold" macro that
# heats the bed back to the interrupted print's temperature, so the part stays
# stuck while somebody decides whether to resume.
#
# It deliberately does nothing for any other shutdown reason (thermal runaway,
# heater verification, ADC out of range, ...): those need a human.
#
# Copyright (C) 2026 JansenDevelopment
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import TYPE_CHECKING, List, Optional

from ..common import RequestType

if TYPE_CHECKING:
    from ..confighelper import ConfigHelper

DEFAULT_PATTERNS = [
    r"Lost communication with MCU",
    r"Unable to connect",
    r"Serial connection closed",
    r"Unable to open serial port",
    r"Timeout on connect",
]


class PlrWatchdog:
    def __init__(self, config: ConfigHelper) -> None:
        self.server = config.get_server()
        self.mcu_path: str = config.get("mcu_path")
        self.hold_gcode: str = config.get("hold_gcode", "PLR_HOLD_BED")
        self.settle_time: float = config.getfloat("settle_time", 3., above=0.)
        self.ready_timeout: float = config.getfloat(
            "ready_timeout", 30., above=0.)
        self.max_wait: float = config.getfloat("max_wait", 1800., above=0.)
        extra = config.getlist("extra_patterns", [], separator="\n")
        self.patterns: List[re.Pattern] = [
            re.compile(p, re.IGNORECASE) for p in DEFAULT_PATTERNS + extra]
        self.task: Optional[asyncio.Task] = None
        self.server.register_event_handler(
            "server:klippy_shutdown", self._on_shutdown)
        self.server.register_endpoint(
            "/server/plr_watchdog/status", RequestType.GET, self._handle_status)
        self.last_event: str = "idle"

    # -- helpers ----------------------------------------------------------
    @property
    def _klippy(self):
        return self.server.lookup_component("klippy_connection")

    def _state_name(self) -> str:
        return self._klippy.state.name

    def _message(self) -> str:
        return self._klippy.state_message or ""

    def _is_connection_problem(self, msg: str) -> bool:
        return any(p.search(msg) for p in self.patterns)

    def _log(self, msg: str) -> None:
        self.last_event = msg
        logging.info("plr_watchdog: " + msg)

    # -- events -----------------------------------------------------------
    async def _on_shutdown(self) -> None:
        msg = self._message()
        if not self._is_connection_problem(msg):
            self._log("shutdown that is not a connection problem, "
                      "leaving it alone: %s" % msg.strip().splitlines()[0]
                      if msg.strip() else "shutdown without message")
            return
        if self.task is not None and not self.task.done():
            return
        self._log("lost the MCU, waiting for %s" % self.mcu_path)
        self.task = asyncio.create_task(self._recover())

    async def _recover(self) -> None:
        deadline = time.monotonic() + self.max_wait
        attempt = 0
        while time.monotonic() < deadline:
            # wait for the board to be back on USB
            while not os.path.exists(self.mcu_path):
                if time.monotonic() >= deadline:
                    break
                await asyncio.sleep(1.)
            if not os.path.exists(self.mcu_path):
                break
            await asyncio.sleep(self.settle_time)
            attempt += 1
            self._log("MCU present, FIRMWARE_RESTART (attempt %d)" % attempt)
            try:
                await self.server.lookup_component("klippy_apis").do_restart(
                    "FIRMWARE_RESTART")
            except Exception:
                logging.exception("plr_watchdog: FIRMWARE_RESTART failed")
            # wait for Klippy to report ready
            t_end = time.monotonic() + self.ready_timeout
            while time.monotonic() < t_end:
                if self._state_name() == "READY":
                    break
                await asyncio.sleep(.5)
            if self._state_name() == "READY":
                self._log("Klippy ready again, running %s" % self.hold_gcode)
                try:
                    await self.server.lookup_component(
                        "klippy_apis").run_gcode(self.hold_gcode)
                except Exception:
                    logging.exception("plr_watchdog: %s failed"
                                      % self.hold_gcode)
                return
            msg = self._message()
            if not self._is_connection_problem(msg):
                self._log("Klippy not ready for another reason, stopping: "
                          + (msg.strip().splitlines() or ["?"])[0])
                return
            await asyncio.sleep(2.)
        self._log("gave up after %.0f s" % self.max_wait)

    async def _handle_status(self, web_request):
        return {
            "mcu_path": self.mcu_path,
            "mcu_present": os.path.exists(self.mcu_path),
            "recovering": self.task is not None and not self.task.done(),
            "last_event": self.last_event,
        }


def load_component(config: ConfigHelper) -> PlrWatchdog:
    return PlrWatchdog(config)
