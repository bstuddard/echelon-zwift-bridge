import struct
from echelon_bridge.power import WATT_TABLE, estimated_watts
from echelon_bridge.cycling_power import PowerFrame
from echelon_bridge.state import BikeState


def test_table_matches_dimensions():
    assert len(WATT_TABLE) == 33
    assert all(len(row) == 11 for row in WATT_TABLE)


def test_interpolation_and_bounds():
    assert estimated_watts(0, 20) == 0
    assert estimated_watts(100, 20) == 185
    assert estimated_watts(90, 20) == 165
    assert estimated_watts(95, 20) == 175
    assert estimated_watts(110, 20) == int(1.1 * 185)
    assert estimated_watts(100, 100) == 625
    assert estimated_watts(90, -5) == 29


def test_cps_bytes():
    frame = PowerFrame()
    frame.last_update = 10.0
    payload = frame.encode(60, 140, now=11.0)
    flags, watts, crank_revs, event_time = struct.unpack("<HhHH", payload)
    assert (flags, watts, crank_revs) == (0x0020, 140, 1)


def test_state_has_no_power_until_both_packet_types():
    state = BikeState(connected=True)
    f = bytearray(13); f[:2] = b"\xf0\xd1"; f[10] = 90
    state.ingest(f)
    assert state.snapshot()["estimated_watts"] == 0
    state.ingest(bytes.fromhex("f0 d2 01 14 d7"))
    assert state.snapshot()["estimated_watts"] == 165
    state.connected = False
    assert state.snapshot()["estimated_watts"] == 0
