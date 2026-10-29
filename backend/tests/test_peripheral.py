import asyncio
import struct
from types import SimpleNamespace

import pytest

from echelon_bridge.config import Settings
from echelon_bridge.cycling_power import PowerFrame, serve_power, advertise_power_forever, CPS_SERVICE, CPS_MEASUREMENT, CPS_FEATURE
from echelon_bridge.state import BikeState, PeripheralState


def test_crank_event_time_fractional_revs_and_wrap():
    frame = PowerFrame(now=63)
    frame.revs = 65535
    frame.encode(90, 165, now=64)
    flags, watts, revs, event = struct.unpack("<HhHH", frame.encode(90, 165, now=65))
    assert (flags, watts, revs, event) == (32, 165, 2, 1024)
    frame.encode(0, 0, now=66)
    assert (frame.revs, frame.last_event_ticks) == (2, 1024)


def test_no_phantom_revolutions_after_long_scheduler_stall():
    frame = PowerFrame(now=0)
    payload = frame.encode(90, 165, now=100)
    assert struct.unpack("<HhHH", payload)[2:] == (0, 0)
    assert struct.unpack("<HhHH", frame.encode(0, 0, now=101))[1] == 0


def test_advertisement_preserves_dbus_interface_and_accepts_selected_tx_power():
    from echelon_bridge.linux_peripheral import PowerAdvertisement
    released = []
    advertisement = PowerAdvertisement("EchelonPython", "/test", CPS_SERVICE, lambda: released.append(True))
    # ServiceInterface.name must remain the D-Bus interface name, not the BLE
    # local name. Otherwise BlueZ can register an empty advertisement.
    assert advertisement.name == "org.bluez.LEAdvertisement1"
    assert advertisement.LocalName == "EchelonPython"
    assert advertisement.ServiceUUIDs == [CPS_SERVICE]
    assert advertisement.Discoverable is True
    advertisement.TxPower = 3
    assert advertisement.TxPower == 3


def test_linux_partial_registration_closes_bus_without_changing_adapter_alias():
    from unittest.mock import AsyncMock, Mock
    from echelon_bridge.linux_peripheral import LinuxPowerServer

    async def run():
        server = LinuxPowerServer.__new__(LinuxPowerServer)
        server.name = "EchelonPython"
        server.setup_task = asyncio.create_task(asyncio.sleep(0))
        server.registered = server.advertisement_registered = False
        server.advertisement = None
        server.bus = SimpleNamespace(export=Mock(), unexport=Mock(), disconnect=Mock())
        server.app = SimpleNamespace(path="/", base_path="/test", register=AsyncMock(), unregister=AsyncMock())
        manager = SimpleNamespace(call_register_advertisement=AsyncMock(side_effect=RuntimeError("no advertising slots")))
        server.adapter = SimpleNamespace(get_interface=Mock(return_value=manager))
        gatt = SimpleNamespace(_notifying=True, emit_properties_changed=Mock())
        server.services = {CPS_SERVICE: SimpleNamespace(characteristics=[SimpleNamespace(gatt=gatt)])}
        with pytest.raises(RuntimeError, match="slots"):
            await server.start()
        assert gatt._notifying is False
        server.app.StartNotify(None)
        assert gatt._notifying is True
        server.app.StopNotify(None)
        assert gatt._notifying is False
        await server.stop()
        server.app.unregister.assert_awaited_once()
        server.bus.disconnect.assert_called_once()
        server.adapter.get_interface.assert_called_once_with("org.bluez.LEAdvertisingManager1")
        assert not server.registered
    asyncio.run(run())


class FakeServer:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chars = {}
        self.advertisement_registered = True
        self.started = False
        self.stopped = False
        self.updated = []

    async def add_new_service(self, uuid):
        assert uuid == CPS_SERVICE

    async def add_new_characteristic(self, service, uuid, properties, value, permissions):
        self.chars[uuid] = SimpleNamespace(uuid=uuid, value=value, properties=properties)

    def get_characteristic(self, uuid):
        return self.chars[uuid]

    async def start(self):
        self.started = True
        return True

    async def is_advertising(self):
        return True

    async def is_connected(self):
        return False

    def update_value(self, service, uuid):
        self.updated.append(bytes(self.chars[uuid].value))
        return True

    async def stop(self):
        self.stopped = True


def test_gatt_read_callback_feature_flags_zero_power_and_cleanup():
    async def run():
        servers = []
        def factory(**kwargs):
            server = FakeServer(**kwargs)
            servers.append(server)
            return server
        status = PeripheralState()
        async def stop(_):
            assert status.gatt_started and status.advertisement_registered
            assert not status.client_subscribed
            raise asyncio.CancelledError
        with pytest.raises(asyncio.CancelledError):
            await serve_power(BikeState(), status, Settings(power_adapter="hci1"), factory, sleep=stop)
        server = servers[0]
        assert server.kwargs["adapter"] == "hci1"
        assert server.stopped and not status.gatt_started
        assert server.read_request_func(server.chars[CPS_FEATURE]) == bytearray(b"\x08\0\0\0")
        assert struct.unpack("<HhHH", server.updated[0]) == (32, 0, 0, 0)
        from bless import GATTCharacteristicProperties as Props
        assert server.chars[CPS_MEASUREMENT].properties & Props.notify
        assert not server.chars[CPS_MEASUREMENT].properties & Props.write
    asyncio.run(run())


def test_partial_start_failure_is_cleaned_up_and_retried():
    async def run():
        servers = []
        class FailingServer(FakeServer):
            async def start(self):
                raise RuntimeError("Registration failed")
        def factory(**kwargs):
            server = FailingServer(**kwargs)
            servers.append(server)
            return server
        status = PeripheralState()
        async def stop(seconds):
            assert seconds == 2
            assert servers[0].stopped
            assert status.status == "retrying"
            raise asyncio.CancelledError
        with pytest.raises(asyncio.CancelledError):
            await advertise_power_forever(BikeState(), status, Settings(), server_factory=factory, sleep=stop)
        assert status.status == "stopped"
        assert "Registration failed" in status.last_error
    asyncio.run(run())
