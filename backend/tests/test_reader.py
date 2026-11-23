import asyncio
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from echelon_bridge import config
from echelon_bridge.__main__ import main
from echelon_bridge.bike_ble import BikeDiscovery, read_session, read_forever, AuthenticationRequired
from echelon_bridge.config import Settings
from echelon_bridge.protocol import ECHELON_SERVICE, WRITE_UUID, NOTIFY_UUIDS, INIT_COMMANDS, poll_command
from echelon_bridge.state import BikeState


def device(address="AA:BB:CC:DD:EE:01", name="ECH-bike"):
    return SimpleNamespace(address=address, name=name)


def advertisement(name="ECH-bike"):
    return SimpleNamespace(local_name=name, service_uuids=[ECHELON_SERVICE])


class FakeScanner:
    found = {}
    kwargs = None

    @classmethod
    async def discover(cls, **kwargs):
        cls.kwargs = kwargs
        return cls.found


class FakeClient:
    def __init__(self, device, disconnected_callback, **kwargs):
        self.disconnected = disconnected_callback
        self.kwargs = kwargs
        self.is_connected = True
        self.calls = []
        self.notifications = []
        self.writer = SimpleNamespace(uuid=WRITE_UUID, properties=["write"])
        self.chars = {WRITE_UUID: self.writer}
        self.chars.update({uuid: SimpleNamespace(uuid=uuid, properties=["notify"]) for uuid in NOTIFY_UUIDS})
        self.service = SimpleNamespace(get_characteristic=self.chars.get)
        self.services = SimpleNamespace(get_service=lambda uuid: self.service if uuid == ECHELON_SERVICE else None)
        self.auth = False
        self.fail_write = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.is_connected = False
        self.disconnected(self)

    async def start_notify(self, char, callback):
        self.calls.append(("notify", char.uuid))
        self.notifications.append(callback)

    async def write_gatt_char(self, char, value, response):
        if self.fail_write:
            raise RuntimeError("write failed")
        self.calls.append(("write", bytes(value), response))
        if self.auth:
            self.notifications[0](None, bytes.fromhex("f0 e0 01 02 03 04 05 06"))
        if value == poll_command(1):
            self.is_connected = False
            self.disconnected(self)


async def no_sleep(_):
    pass


@pytest.mark.parametrize("response", [True, False])
def test_subscribe_before_init_and_poll_on_selected_adapter(response):
    async def run():
        created = []
        def factory(*args, **kwargs):
            client = FakeClient(*args, **kwargs)
            client.writer.properties = ["write"] if response else ["write-without-response"]
            created.append(client)
            return client
        state = BikeState()
        with pytest.raises(ConnectionError):
            await read_session(state, device(), Settings(adapter=None if config.WINDOWS else "hci1"), factory,
                               sleep=no_sleep, init_timeout=0, poll_interval=0)
        client = created[0]
        assert client.kwargs.get("adapter") == (None if config.WINDOWS else "hci1")
        assert client.calls[:2] == [("notify", uuid) for uuid in NOTIFY_UUIDS]
        writes = [c for c in client.calls if c[0] == "write"]
        assert [c[1] for c in writes] == [*INIT_COMMANDS, poll_command(1)]
        assert all(c[2] is response for c in writes)
        assert state.live_values() == (0, 0)
    asyncio.run(run())


def test_auth_stops_init_without_sending_more_commands():
    async def run():
        client = None
        def factory(*args, **kwargs):
            nonlocal client
            client = FakeClient(*args, **kwargs)
            client.auth = True
            return client
        state = BikeState()
        with pytest.raises(AuthenticationRequired):
            await read_session(state, device(), Settings(), factory, sleep=no_sleep, init_timeout=0)
        assert state.auth_required
        assert len([c for c in client.calls if c[0] == "write"]) == 1
        assert state.live_values() == (0, 0)
    asyncio.run(run())


def test_missing_notify_permission_prevents_init():
    async def run():
        def factory(*args, **kwargs):
            client = FakeClient(*args, **kwargs)
            client.chars[NOTIFY_UUIDS[0]].properties = ["read"]
            return client
        with pytest.raises(RuntimeError, match="notification characteristic"):
            await read_session(BikeState(), device(), Settings(), factory, sleep=no_sleep)
    asyncio.run(run())


def test_scan_selection_requires_an_explicit_pin():
    async def run():
        adapter = None if config.WINDOWS else "hci1"
        discovery = BikeDiscovery(Settings(adapter=adapter), FakeScanner)
        FakeScanner.found = {}
        with pytest.raises(RuntimeError, match="No bike selected"):
            await discovery.find()
        d1, d2 = device(), device("AA:BB:CC:DD:EE:02")
        FakeScanner.found = {"a": (d1, advertisement()), "b": (d2, advertisement())}
        with pytest.raises(RuntimeError, match="No bike selected"):
            await discovery.find()
        discovery.settings = Settings(adapter=adapter, address=d2.address)
        assert await discovery.find() is d2
        assert FakeScanner.kwargs.get("adapter") == adapter
        assert "address" not in discovery.snapshot()["devices"][0]
        assert discovery.snapshot(True)["devices"][0]["address"] == d1.address
    asyncio.run(run())


def test_windows_launcher_reads_pinned_bike_into_dashboard_without_advertising(monkeypatch, tmp_path):
    pinned = device()
    other = device("AA:BB:CC:DD:EE:02")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(f"ECHELON_ADDRESS={pinned.address}\n", encoding="utf-8-sig")
    monkeypatch.setattr(config, "WINDOWS", True)
    monkeypatch.delenv("ECHELON_ADDRESS", raising=False)
    monkeypatch.setenv("BLE_ADVERTISE", "1")
    monkeypatch.setattr("sys.argv", ["echelon-bridge"])
    received = asyncio.Event()

    async def discover(**kwargs):
        assert "adapter" not in kwargs
        return {bike.address: (bike, advertisement()) for bike in (other, pinned)}

    class Bike(FakeClient):
        def __init__(self, bike, **kwargs):
            assert bike is pinned and "adapter" not in kwargs
            super().__init__(bike, **kwargs)

        async def write_gatt_char(self, char, value, response):
            self.notifications[0](None, bytes.fromhex("f0 d2 01 14 d7"))
            if value == poll_command(1):
                cadence = bytearray(13)
                cadence[:2] = b"\xf0\xd1"
                cadence[10] = 90
                self.notifications[0](None, cadence)
                received.set()

    async def verify(app):
        async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app), base_url="http://localhost") as client:
            await asyncio.wait_for(received.wait(), timeout=8)
            health = (await client.get("/api/health")).json()
            metrics = (await client.get("/api/metrics")).json()
            assert health["host_platform"] == "windows" and health["status"] == "ready"
            assert health["reader_enabled"] and not health["ble_power_advertising_enabled"]
            assert set(app.state.tasks) == {"reader"}
            assert (metrics["cadence_rpm"], metrics["resistance_level"], metrics["estimated_watts"]) == (90, 20, 165)
            assert not (await client.get("/api/mirror/status")).json()["configured"]
        assert not app.state.bike.connected

    def run_server(server):
        assert server.config.host == "127.0.0.1"
        asyncio.run(verify(server.config.app))

    monkeypatch.setattr("bleak.BleakScanner.discover", discover)
    monkeypatch.setattr("bleak.BleakClient", Bike)
    monkeypatch.setattr("uvicorn.Server.run", run_server)
    monkeypatch.setattr("echelon_bridge.windows_control.StopControl",
                        lambda *args: nullcontext(SimpleNamespace(requested=lambda: False)))
    main()


def test_reconnect_resets_stale_resistance_and_cancellation():
    async def run():
        state = BikeState(connected=True, cadence=90, resistance=20, last_cadence_at=10)
        attempts = 0
        class Discovery:
            async def find(self):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise RuntimeError("Device AA:BB:CC:DD:EE:FF unavailable")
                raise asyncio.CancelledError
        waits = []
        async def sleep(seconds):
            waits.append(seconds)
            assert state.resistance is None
            assert state.live_values() == (0, 0)
        with pytest.raises(asyncio.CancelledError):
            await read_forever(state, Settings(reader=True), Discovery(), sleep=sleep)
        assert attempts == 2 and waits == [2]
        assert state.reader_status == "stopped"
        assert "AA:BB" not in state.last_error
    asyncio.run(run())


def test_write_error_drops_live_values_and_retries():
    async def run():
        state = BikeState()
        class Discovery:
            attempts = 0
            async def find(self):
                self.attempts += 1
                if self.attempts > 1:
                    raise asyncio.CancelledError
                return device()
        class BrokenClient(FakeClient):
            async def start_notify(self, char, callback):
                await super().start_notify(char, callback)
                cadence = bytearray(13)
                cadence[:2] = b"\xf0\xd1"
                cadence[10] = 90
                callback(char, cadence)
                callback(char, bytes.fromhex("f0 d2 01 14 d7"))
                assert state.live_values() == (90, 165)
                self.fail_write = True
        retries = []
        async def sleep(seconds):
            if seconds >= 2:
                retries.append(seconds)
                assert state.live_values() == (0, 0)
                assert state.resistance is None
        with pytest.raises(asyncio.CancelledError):
            await read_forever(state, Settings(reader=True), Discovery(), client_factory=BrokenClient, sleep=sleep)
        assert retries == [2]
        assert "write failed" in state.last_error
    asyncio.run(run())


@pytest.mark.parametrize("disconnect_during_write", [False, True])
def test_successful_initialization_resets_backoff_before_disconnect_cleanup(disconnect_during_write):
    async def run():
        state = BikeState()

        class Discovery:
            attempts = 0

            async def find(self):
                self.attempts += 1
                if self.attempts <= 2:
                    raise RuntimeError("Bike not advertising yet")
                if self.attempts > 4:
                    raise asyncio.CancelledError
                return device()

        class InterruptedClient(FakeClient):
            async def write_gatt_char(self, char, value, response):
                if value == poll_command(1):
                    assert state.initialized
                    if disconnect_during_write:
                        self.is_connected = False
                        self.disconnected(self)
                    # A Windows cancellation can occur after the callback, or
                    # cleanup can trigger the callback while unwinding the write.
                    raise OSError(-2147023673, "The operation was canceled by the user")
                await super().write_gatt_char(char, value, response)
                self.notifications[0](None, bytes.fromhex("f0 d2 01 14 d7"))

        retries = []

        async def sleep(seconds):
            if seconds >= 2:
                assert not state.connected and not state.initialized
                assert state.resistance is None
                retries.append(seconds)

        with pytest.raises(asyncio.CancelledError):
            await read_forever(state, Settings(reader=True), Discovery(),
                               client_factory=InterruptedClient, sleep=sleep)
        assert retries == [2, 4, 2, 2]
        assert state.reader_status == "stopped"

    asyncio.run(run())


@pytest.mark.parametrize("auth", [False, True])
def test_failed_initialization_keeps_backoff_and_auth_wait(auth):
    async def run():
        class Discovery:
            attempts = 0

            async def find(self):
                self.attempts += 1
                if self.attempts > 6:
                    raise asyncio.CancelledError
                return device()

        def factory(*args, **kwargs):
            client = FakeClient(*args, **kwargs)
            client.auth = auth
            client.fail_write = not auth
            return client

        retries = []

        async def sleep(seconds):
            if seconds >= 2:
                retries.append(seconds)

        with pytest.raises(asyncio.CancelledError):
            await read_forever(BikeState(), Settings(reader=True), Discovery(),
                               client_factory=factory, sleep=sleep)
        assert retries == ([60] * 6 if auth else [2, 4, 8, 16, 30, 30])

    asyncio.run(run())
