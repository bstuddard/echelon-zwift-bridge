from echelon_bridge.protocol import decode_packet, poll_command


def test_decode_cadence():
    frame = bytearray(13)
    frame[:2] = b"\xf0\xd1"
    frame[10] = 86
    result = decode_packet(frame)
    assert (result.kind, result.value) == ("cadence", 86)


def test_decode_resistance():
    assert (decode_packet(bytes.fromhex("f0 d2 01 17 da")).kind,
            decode_packet(bytes.fromhex("f0 d2 01 17 da")).value) == ("resistance", 23)


def test_bad_frame():
    assert decode_packet(bytes.fromhex("00 01 02")).kind == "other"


def test_firmware_auth():
    assert decode_packet(bytes.fromhex("f0 e0 01 02 03 04 05 06")).kind == "auth_required"


def test_poll_checksum():
    assert poll_command(1) == bytes.fromhex("f0 a0 01 01 92")
