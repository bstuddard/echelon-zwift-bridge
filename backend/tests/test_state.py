from echelon_bridge.state import BikeState


def cadence(rpm):
    frame = bytearray(13)
    frame[:2] = b"\xf0\xd1"
    frame[10] = rpm
    return bytes(frame)


def test_freshness_stop_and_disconnect_gate_power():
    state = BikeState(connected=True)
    state.ingest(cadence(90), now=10)
    assert state.live_values(now=10) == (90, 0)
    state.ingest(bytes.fromhex("f0 d2 01 14 d7"), now=10)
    assert state.live_values(now=14.9) == (90, 165)
    assert state.live_values(now=15.1) == (0, 0)
    state.ingest(cadence(0), now=16)
    assert state.live_values(now=16) == (0, 0)
    state.ingest(cadence(90), now=17)
    state.connected = False
    assert state.live_values(now=17) == (0, 0)


def test_resistance_changes_only_on_knob_and_is_cleared_on_reconnect():
    state = BikeState(connected=True)
    state.ingest(bytes.fromhex("f0 d2 01 14 d7"), now=0)
    state.ingest(cadence(90), now=600)
    assert state.live_values(now=600) == (90, 165)
    state.reset_connection()
    state.connected = True
    state.ingest(cadence(90), now=601)
    assert state.live_values(now=601) == (90, 0)


def test_auth_immediately_blocks_power():
    state = BikeState(connected=True)
    state.ingest(bytes.fromhex("f0 d2 01 14 d7"), now=10)
    state.ingest(cadence(90), now=10)
    state.ingest(bytes.fromhex("f0 e0 01 02 03 04 05 06"), now=10)
    assert state.live_values(now=10) == (0, 0)
    assert state.snapshot()["auth_required"]
