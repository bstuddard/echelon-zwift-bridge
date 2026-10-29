import asyncio
import json
import os

import pytest
from httpx import AsyncClient, ASGITransport

from echelon_bridge.app import create_app
from echelon_bridge.config import Settings
from echelon_bridge.diagnostics import PacketCapture, safe_error
from echelon_bridge.protocol import INIT_COMMANDS, poll_command, decode_packet


def test_read_only_http_bounds_and_host_guard():
    async def run():
        app = create_app(Settings())
        async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app), base_url="http://127.0.0.1") as client:
            assert (await client.get("/health")).json()["reader_enabled"] is False
            assert (await client.get("/metrics")).json()["estimated_watts"] == 0
            assert (await client.get("/estimate?cadence=90&resistance=20")).json()["estimated_watts"] == 165
            assert (await client.get("/estimate?cadence=999999")).status_code == 422
            assert (await client.get("/metrics", headers={"host": "untrusted.example"})).status_code == 400
            assert (await client.post("/metrics", json={"watts": 999})).status_code == 405
    asyncio.run(run())


def test_tasks_are_cancelled_on_shutdown():
    async def run():
        stopped = []
        async def task(*args, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(True)
        app = create_app(Settings(reader=True, advertise=True), reader=task, advertiser=task)
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0)
        assert len(stopped) == 2
        assert all(task.done() for task in app.state.tasks.values())
    asyncio.run(run())


def test_simulation_cannot_mix_with_real_bike_and_uses_test_name():
    with pytest.raises(ValueError):
        Settings(reader=True, simulate=True)
    assert Settings(simulate=True).name == "EchelonSIM-TEST"
    async def run():
        app = create_app(Settings(simulate=True))
        async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app), base_url="http://localhost") as client:
            await asyncio.sleep(0)
            metrics = (await client.get("/metrics")).json()
            assert metrics["simulated"] and metrics["power_source"] == "SIMULATION_BLE_SMOKE_TEST_ONLY"
            assert metrics["peripheral"]["name"] == "EchelonSIM-TEST"
    asyncio.run(run())


def test_private_capture_redacts_auth_and_unknown_packets(tmp_path):
    path = tmp_path / "trace.jsonl"
    capture = PacketCapture(path)
    capture.record("rx", bytes.fromhex("f0 e0 01 02 03 04 05 06"))
    capture.record("rx", b"private identifier")
    capture.record("tx", INIT_COMMANDS[0])
    capture.close()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert "hex" not in rows[0] and "hex" not in rows[1]
    assert rows[2]["hex"] == "f0 a1 00 91"
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert "AA:BB" not in safe_error(RuntimeError("AA:BB:CC:DD:EE:FF"))


def test_init_and_all_poll_checksums():
    for packet in [*INIT_COMMANDS, *(poll_command(n) for n in range(1, 256))]:
        assert packet[-1] == sum(packet[:-1]) & 255
    for level in (0, 33, 255):
        assert decode_packet(bytes((0xf0, 0xd2, 1, level, 0))).kind == "other"
