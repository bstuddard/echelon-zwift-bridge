"""Echelon central: discover, subscribe before init, poll, and reconnect."""
import asyncio
import logging
from time import monotonic

from .config import Settings
from .diagnostics import PacketCapture, safe_error
from .protocol import ECHELON_SERVICE, WRITE_UUID, NOTIFY_UUIDS, INIT_COMMANDS, poll_command
from .state import BikeState

log = logging.getLogger(__name__)


def is_bike(device, advertisement) -> bool:
    name = (advertisement.local_name or device.name or "").upper()
    services = {uuid.lower() for uuid in advertisement.service_uuids}
    if name in {"ECHELONPYTHON", "ECHELONSIM-TEST"}:
        return False
    return name.startswith("ECH") or "EX-15" in name or ECHELON_SERVICE in services


class BikeDiscovery:
    def __init__(self, settings: Settings, scanner_cls=None):
        if scanner_cls is None:
            from bleak import BleakScanner
            scanner_cls = BleakScanner
        self.scanner = scanner_cls
        self.settings = settings
        self.lock = asyncio.Lock()
        self.devices = []
        self.scanned_at = None

    async def scan(self, timeout=8.0):
        async with self.lock:
            kwargs = {"adapter": self.settings.adapter} if self.settings.adapter else {}
            found = await self.scanner.discover(timeout=timeout, return_adv=True, **kwargs)
            self.devices = list(found.values())
            self.scanned_at = monotonic()
            return self.devices

    async def find(self):
        if not self.settings.address:
            raise RuntimeError("No bike selected. Run echelon-bridge --scan and set ECHELON_ADDRESS in .env")
        devices = await self.scan()
        matches = [d for d, _ in devices if d.address.lower() == self.settings.address.lower()]
        if not matches:
            raise RuntimeError("Echelon not found; pedal to wake it, check power, and close other bike apps")
        return matches[0]

    def snapshot(self, identifiers=False):
        rows = []
        for device, adv in self.devices:
            if not is_bike(device, adv) and not (self.settings.address and device.address.lower() == self.settings.address.lower()):
                continue
            row = {"name": "Echelon candidate", "services": adv.service_uuids}
            if identifiers:
                row.update(name=adv.local_name or device.name, address=device.address)
            rows.append(row)
        return {"devices": rows, "scanning": self.lock.locked(),
                "age_seconds": round(monotonic() - self.scanned_at, 1) if self.scanned_at is not None else None}


class AuthenticationRequired(RuntimeError):
    pass


async def read_session(state, device, settings, client_factory, *, capture=None,
                       sleep=asyncio.sleep, init_timeout=0.3, poll_interval=2.0):
    wake = asyncio.Event()
    notification = asyncio.Event()

    def disconnected(_):
        state.reset_connection()
        state.reader_status = "reconnecting"
        wake.set()
        log.warning("event=bike_disconnected")

    kwargs = {"adapter": settings.adapter} if settings.adapter else {}
    async with client_factory(device, disconnected_callback=disconnected, timeout=20, **kwargs) as client:
        state.reset_connection()
        state.connected = True
        state.auth_required = False
        state.last_error = None
        state.reader_status = "initializing"
        service = client.services.get_service(ECHELON_SERVICE)
        if service is None:
            raise RuntimeError("Selected bike does not expose the Echelon GATT service")
        writer = service.get_characteristic(WRITE_UUID)
        if writer is None:
            raise RuntimeError("Echelon write characteristic missing")
        if "write" in writer.properties:
            response = True
        elif "write-without-response" in writer.properties:
            response = False
        else:
            raise RuntimeError("Echelon characteristic does not permit writes")

        def on_notification(_sender, data):
            if not state.connected:
                return
            raw = bytes(data)
            state.ingest(raw)
            if capture:
                capture.record("rx", raw)
            notification.set()
            if state.auth_required:
                wake.set()

        for uuid in NOTIFY_UUIDS:
            characteristic = service.get_characteristic(uuid)
            if characteristic is None or not {"notify", "indicate"}.intersection(characteristic.properties):
                raise RuntimeError("Echelon notification characteristic missing or lacks notify/indicate permission")
            # Bleak/BlueZ manage the CCCD. Do not manually write its descriptor.
            await client.start_notify(characteristic, on_notification)
        await sleep(0.3)
        for packet in INIT_COMMANDS:
            if state.auth_required:
                raise AuthenticationRequired(state.last_error)
            notification.clear()
            async with asyncio.timeout(10):
                await client.write_gatt_char(writer, packet, response=response)
            if capture:
                capture.record("tx", packet)
            # QZ waits for a notification or a 300 ms timeout for each init.
            try:
                await asyncio.wait_for(notification.wait(), timeout=init_timeout)
            except TimeoutError:
                pass
            await sleep(0.05)
        if state.auth_required:
            raise AuthenticationRequired(state.last_error)
        state.initialized = True
        state.reader_status = "reading"
        log.info("event=bike_initialized write_response=%s", response)
        counter = 1
        while client.is_connected and state.connected:
            if state.auth_required:
                raise AuthenticationRequired(state.last_error)
            async with asyncio.timeout(10):
                packet = poll_command(counter)
                await client.write_gatt_char(writer, packet, response=response)
            if capture:
                capture.record("tx", packet)
            counter = 1 if counter == 255 else counter + 1
            try:
                await asyncio.wait_for(wake.wait(), timeout=poll_interval)
            except TimeoutError:
                pass
        raise ConnectionError("Bike disconnected; reconnecting")


async def read_forever(state: BikeState, settings=None, discovery=None, *, client_factory=None,
                       sleep=asyncio.sleep, capture: PacketCapture | None = None):
    from bleak import BleakClient
    settings = settings or Settings.from_env()
    discovery = discovery or BikeDiscovery(settings)
    client_factory = client_factory or BleakClient
    delay = 2.0
    try:
        while True:
            try:
                state.reader_status = "scanning"
                device = await discovery.find()
                log.info("event=bike_found")
                await read_session(state, device, settings, client_factory, capture=capture, sleep=sleep)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                was_initialized = state.initialized
                state.reset_connection()
                state.last_error = safe_error(exc)
                state.reader_status = "auth_required" if state.auth_required else "retrying"
                state.reconnects += 1
                wait = 60 if state.auth_required else (2 if was_initialized else delay)
                log.warning("event=reader_retry seconds=%s error=%s", wait, state.last_error)
                await sleep(wait)
                delay = 2 if was_initialized else min(delay * 2, 30)
    finally:
        state.reset_connection()
        state.reader_status = "stopped"


async def simulate_forever(state: BikeState):
    """Fixed, explicitly named BLE smoke test. No HTTP controls or watt boosts."""
    state.simulated = True
    state.connected = True
    state.initialized = True
    state.reader_status = "simulation_smoke_test"
    log.warning("event=simulation_enabled purpose=BLE_SMOKE_TEST_ONLY")
    try:
        while True:
            cadence = bytearray(13)
            cadence[:2] = b"\xf0\xd1"
            cadence[10] = 60
            state.ingest(cadence)
            state.ingest(bytes.fromhex("f0 d2 01 01 c4"))
            await asyncio.sleep(1)
    finally:
        state.reset_connection()
        state.reader_status = "stopped"
