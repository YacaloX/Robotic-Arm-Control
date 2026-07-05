from __future__ import annotations
from typing import List
from queue import Queue


class ProtocolHandler:
    def __init__(self, log_queue: Queue):
        self._log_queue = log_queue
        self._firmware_ready = False
        self._detected_dof = 6
        self._detected_pins: List[int] = []

    @property
    def firmware_ready(self) -> bool:
        return self._firmware_ready

    @property
    def detected_dof(self) -> int:
        return self._detected_dof

    @property
    def detected_pins(self) -> List[int]:
        return list(self._detected_pins)

    def _parse_config_ok(self, line: str) -> None:
        try:
            parts = line.split()
            if len(parts) >= 4:
                self._detected_dof = int(parts[3])
                pins_part = line[line.index("pines:") + 6:].strip()
                self._detected_pins = [int(p) for p in pins_part.split()]
        except (ValueError, IndexError):
            pass

    def process_line(self, line: str, handshake_event=None) -> None:
        if line == "PONG":
            self._firmware_ready = True
            if handshake_event:
                handshake_event.set()
        elif line == "CHECKED":
            pass
        elif line.startswith("STATUS OK"):
            parts = line.split()
            if len(parts) >= 3:
                try:
                    self._detected_dof = int(parts[2])
                except (ValueError, IndexError):
                    pass
        elif line.startswith("CONFIG OK"):
            self._parse_config_ok(line)
        self._log_queue.put(f"ESP32 -> {line}")
