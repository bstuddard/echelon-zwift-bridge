"""Documented Echelon Connect Sport legacy BLE packet parsing and commands."""
from dataclasses import dataclass
from typing import Literal

# Source: QZ src/devices/echelonconnectsport/echelonconnectsport.cpp (GPLv3).
ECHELON_SERVICE = "0bf669f1-45f2-11e7-9598-0800200c9a66"
WRITE_UUID = "0bf669f2-45f2-11e7-9598-0800200c9a66"
NOTIFY_UUIDS = (
    "0bf669f3-45f2-11e7-9598-0800200c9a66",
    "0bf669f4-45f2-11e7-9598-0800200c9a66",
)
INIT_COMMANDS = (
    bytes.fromhex("f0 a1 00 91"),
    bytes.fromhex("f0 a1 00 91"),
    bytes.fromhex("f0 a1 00 91"),
    bytes.fromhex("f0 a1 00 91"),
    bytes.fromhex("f0 a3 00 93"),
    bytes.fromhex("f0 a1 00 91"),
    bytes.fromhex("f0 b0 01 01 a2"),
)

@dataclass(frozen=True)
class Packet:
    kind: Literal["cadence", "resistance", "auth_required", "other"]
    value: int | None = None


def decode_packet(data: bytes | bytearray) -> Packet:
    data = bytes(data)
    if len(data) == 13 and data[:2] == b"\xf0\xd1":
        return Packet("cadence", data[10])
    if len(data) == 5 and data[:2] == b"\xf0\xd2" and 1 <= data[3] <= 32:
        return Packet("resistance", data[3])
    # Newer Echelon firmware may require authenticated unlock; out of scope.
    if len(data) == 8 and data[:2] == b"\xf0\xe0":
        return Packet("auth_required")
    return Packet("other")


def poll_command(counter: int) -> bytes:
    # QZ's f0 a0 01 counter checksum, checksum = sum(previous bytes) % 256.
    if not 1 <= counter <= 255:
        raise ValueError("poll counter must be 1..255")
    payload = bytes((0xF0, 0xA0, 0x01, counter))
    return payload + bytes((sum(payload) & 0xFF,))
