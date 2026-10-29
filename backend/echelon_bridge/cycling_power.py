"""Standard Cycling Power Service with estimated watts and crank timing."""
import asyncio
import logging
import struct
from time import monotonic

from .config import Settings
from .diagnostics import safe_error
from .state import BikeState, PeripheralState, STALE_AFTER_SECONDS

log = logging.getLogger(__name__)
CPS_SERVICE = "00001818-0000-1000-8000-00805f9b34fb"
CPS_MEASUREMENT = "00002a63-0000-1000-8000-00805f9b34fb"
CPS_FEATURE = "00002a65-0000-1000-8000-00805f9b34fb"
SENSOR_LOCATION = "00002a5d-0000-1000-8000-00805f9b34fb"


class PowerFrame:
    def __init__(self, *, now=None):
        self.revs = 0
        self.partial_revs = 0.0
        self.last_event_ticks = 0
        self.last_update = monotonic() if now is None else now

    def encode(self, cadence_rpm: int, watts: int, *, now: float | None = None) -> bytes:
        """LE: uint16 flags, int16 watts, uint16 crank count, uint16 1/1024s."""
        now = monotonic() if now is None else now
        dt = max(0.0, now - self.last_update)
        self.last_update = now
        if cadence_rpm > 0 and dt <= STALE_AFTER_SECONDS:
            revolutions = self.partial_revs + cadence_rpm / 60.0 * dt
            whole_revs = int(revolutions)
            self.partial_revs = revolutions - whole_revs
            if whole_revs:
                self.revs = (self.revs + whole_revs) & 0xFFFF
                since_event = self.partial_revs / (cadence_rpm / 60.0)
                self.last_event_ticks = int((now - since_event) * 1024) & 0xFFFF
        else:
            # Never extrapolate crank events through stops or long task stalls.
            self.partial_revs = 0.0
        return struct.pack("<HhHH", 0x0020, max(0, min(int(watts), 32767)), self.revs, self.last_event_ticks)


async def serve_power(state, status, settings, server_factory, *, sleep=asyncio.sleep):
    from bless import GATTCharacteristicProperties as Props, GATTAttributePermissions as Perms
    kwargs = {"adapter": settings.power_adapter} if settings.power_adapter else {}
    server = server_factory(name=settings.name, loop=asyncio.get_running_loop(), **kwargs)
    try:
        status.status = "starting"
        server.read_request_func = lambda characteristic, **_: characteristic.value
        await server.add_new_service(CPS_SERVICE)
        await server.add_new_characteristic(
            CPS_SERVICE, CPS_MEASUREMENT, Props.notify | Props.read,
            bytearray(struct.pack("<HhHH", 0x0020, 0, 0, 0)), Perms.readable)
        await server.add_new_characteristic(
            CPS_SERVICE, CPS_FEATURE, Props.read,
            bytearray(struct.pack("<I", 1 << 3)), Perms.readable)
        await server.add_new_characteristic(
            CPS_SERVICE, SENSOR_LOCATION, Props.read, bytearray((0x00,)), Perms.readable)
        # BlueZ creates the CCCD for the notify property. No writable power or
        # trainer control characteristic is exposed.
        if not await server.start():
            raise RuntimeError("Cycling Power GATT server failed to register")
        status.gatt_started = True
        status.last_error = None
        frame = PowerFrame()
        log.info("event=power_gatt_registered name=%s", settings.name)
        while True:
            status.advertisement_registered = server.advertisement_registered
            status.adapter_advertising_active = await server.is_advertising()
            status.client_subscribed = await server.is_connected()
            if not status.advertisement_registered:
                raise RuntimeError("BlueZ released the bridge advertisement; re-registering")
            if not status.adapter_advertising_active and not status.client_subscribed:
                raise RuntimeError("Adapter is no longer advertising; re-registering")
            next_status = "subscribed" if status.client_subscribed else "advertising"
            if status.status != next_status:
                log.info("event=peripheral_status status=%s", next_status)
            status.status = next_status
            cadence, watts = state.live_values()
            server.get_characteristic(CPS_MEASUREMENT).value = bytearray(frame.encode(cadence, watts))
            if not server.update_value(CPS_SERVICE, CPS_MEASUREMENT):
                raise RuntimeError("Cycling Power characteristic update failed")
            status.updates += 1
            await sleep(1.0)
    finally:
        status.gatt_started = False
        status.advertisement_registered = False
        status.adapter_advertising_active = False
        status.client_subscribed = False
        try:
            async with asyncio.timeout(5):
                await server.stop()
        except Exception as exc:
            log.warning("event=peripheral_cleanup error=%s", safe_error(exc))


async def advertise_power_forever(state: BikeState, status=None, settings=None, *, server_factory=None, sleep=asyncio.sleep):
    settings = settings or Settings.from_env()
    status = status or PeripheralState(name=settings.name)
    if server_factory is None:
        from .linux_peripheral import LinuxPowerServer
        server_factory = LinuxPowerServer
    delay = 2
    try:
        while True:
            try:
                await serve_power(state, status, settings, server_factory, sleep=sleep)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if status.updates:
                    delay = 2
                status.status = "retrying"
                status.last_error = safe_error(exc)
                log.warning("event=peripheral_retry seconds=%s error=%s", delay, status.last_error)
                await sleep(delay)
                delay = min(delay * 2, 30)
    finally:
        status.status = "stopped"
