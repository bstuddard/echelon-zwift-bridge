"""Logs and optional captures exclude Bluetooth addresses and auth payloads."""
import json
import logging
import os
from pathlib import Path
import re
from collections import deque
from datetime import datetime, timezone
from time import monotonic

from .protocol import decode_packet


def safe_error(exc: Exception) -> str:
    message = re.sub(r"(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}", "[device]", str(exc))
    message = re.sub(r"(?i)dev_(?:[0-9a-f]{2}_){5}[0-9a-f]{2}", "dev_[device]", message)
    return f"{type(exc).__name__}: {message}"[:400]


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for name in ("bleak", "bless", "dbus_next", "dbus_fast"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


class RecentEvents(logging.Handler):
    """Bounded, identifier-redacted application events for the local admin UI."""
    def __init__(self):
        super().__init__(logging.INFO)
        self.events = deque(maxlen=100)

    def emit(self, record):
        if not record.name.startswith("echelon_bridge."):
            return
        message = safe_error(RuntimeError(record.getMessage())).removeprefix("RuntimeError: ")
        self.events.append({"timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                            "level": record.levelname.lower(), "message": message})


class PacketCapture:
    def __init__(self, path: Path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        self.file = os.fdopen(fd, "a", buffering=1)
        self.started = monotonic()

    def record(self, direction: str, raw: bytes):
        packet = decode_packet(raw)
        row = {"seconds": round(monotonic() - self.started, 3), "direction": direction}
        if direction == "tx" or packet.kind in {"cadence", "resistance"}:
            row.update(kind=packet.kind if direction == "rx" else "command", hex=raw.hex(" "))
        else:
            row.update(kind=packet.kind, length=len(raw), payload="redacted")
        self.file.write(json.dumps(row) + "\n")

    def close(self):
        self.file.close()
