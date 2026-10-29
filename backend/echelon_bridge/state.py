"""State shared by tasks on one event loop; freshness gates every power frame."""
from dataclasses import dataclass
from time import monotonic

from .power import estimated_watts
from .protocol import decode_packet

STALE_AFTER_SECONDS = 5.0


@dataclass
class BikeState:
    cadence: int = 0
    resistance: int | None = None
    connected: bool = False
    initialized: bool = False
    auth_required: bool = False
    simulated: bool = False
    reader_status: str = "disabled"
    packets_seen: int = 0
    last_packet_kind: str | None = None
    last_cadence_at: float | None = None
    last_resistance_at: float | None = None
    last_error: str | None = None
    reconnects: int = 0

    def reset_connection(self):
        self.connected = False
        self.initialized = False
        self.cadence = 0
        self.resistance = None
        self.last_cadence_at = None
        self.last_resistance_at = None

    def ingest(self, raw: bytes, *, now: float | None = None) -> None:
        packet = decode_packet(raw)
        self.packets_seen += 1
        self.last_packet_kind = packet.kind
        now = monotonic() if now is None else now
        if packet.kind == "cadence":
            self.cadence = int(packet.value or 0)
            self.last_cadence_at = now
        elif packet.kind == "resistance":
            # QZ documents resistance arriving only on changes. Keep the knob
            # setting for this connection; clear it when reconnecting.
            self.resistance = packet.value
            self.last_resistance_at = now
        elif packet.kind == "auth_required":
            self.auth_required = True
            self.last_error = "Firmware authentication required; see README compatibility notes"

    def stale(self, now: float | None = None) -> bool:
        now = monotonic() if now is None else now
        return self.last_cadence_at is None or now - self.last_cadence_at > STALE_AFTER_SECONDS

    def live_values(self, *, now: float | None = None) -> tuple[int, int]:
        if not self.connected or self.auth_required or self.stale(now):
            return 0, 0
        if self.resistance is None:
            return self.cadence, 0
        return self.cadence, estimated_watts(self.cadence, self.resistance)

    def snapshot(self) -> dict:
        now = monotonic()
        cadence, watts = self.live_values(now=now)
        return {
            "connected": self.connected, "initialized": self.initialized,
            "reader_status": self.reader_status, "simulated": self.simulated,
            "auth_required": self.auth_required, "stale": self.stale(now),
            "cadence_rpm": cadence, "resistance_level": self.resistance,
            "estimated_watts": watts,
            "power_available": self.connected and not self.auth_required and not self.stale(now) and self.resistance is not None,
            "power_source": "SIMULATION_BLE_SMOKE_TEST_ONLY" if self.simulated else "ESTIMATED_FROM_QZ_LOOKUP_TABLE",
            "last_cadence_age_seconds": round(now - self.last_cadence_at, 1) if self.last_cadence_at is not None else None,
            "last_resistance_age_seconds": round(now - self.last_resistance_at, 1) if self.last_resistance_at is not None else None,
            "packets_seen": self.packets_seen, "last_packet_kind": self.last_packet_kind,
            "last_error": self.last_error, "reconnects": self.reconnects,
        }


@dataclass
class PeripheralState:
    name: str = "EchelonPython"
    status: str = "disabled"
    gatt_started: bool = False
    advertisement_registered: bool = False
    adapter_advertising_active: bool = False
    client_subscribed: bool = False
    updates: int = 0
    last_error: str | None = None

    def snapshot(self):
        return {**vars(self), "external_discovery_verified": False,
                "note": "Subscription confirms a BLE client, not its identity or Zwift pairing"}
