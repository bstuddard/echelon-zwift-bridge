"""Small adapter for the pinned Bless 0.3.0 Linux backend.

Use standard BlueZ advertisement fields, avoid Bless's global adapter Alias
mutation, fix its initial Notifying flag, and close its D-Bus connection.
"""
import asyncio

from bless import BlessServer
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method


class PowerAdvertisement(ServiceInterface):
    def __init__(self, name, path, service, released):
        super().__init__("org.bluez.LEAdvertisement1")
        self.local_name, self.path, self.service = name, path, service
        self.tx_power = 0
        self.released = released

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> 's':
        return "peripheral"

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> 'as':
        return [self.service]

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> 's':
        return self.local_name

    @dbus_property(access=PropertyAccess.READ)
    def Discoverable(self) -> 'b':
        # Scoped to this LE advertisement, without enabling global discovery.
        return True

    @dbus_property()
    def TxPower(self) -> 'n':
        # BlueZ 5.87 probes this optional field separately. 0 dBm fits this
        # adapter's supported range and avoids Bless's hard-coded +20 dBm.
        return self.tx_power

    @TxPower.setter
    def TxPower(self, value: 'n'):
        # BlueZ writes back the controller's selected transmit power.
        self.tx_power = value

    @method()
    def Release(self):
        self.released()


class LinuxPowerServer(BlessServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registered = False
        self.advertisement_registered = False
        self.advertisement = None

    async def start(self, **kwargs):
        await self.setup_task
        measurement = next(iter(self.services.values())).characteristics[0]
        measurement.gatt._notifying = False

        def notifying(value):
            measurement.gatt._notifying = value
            measurement.gatt.emit_properties_changed({"Notifying": value})

        self.app.StartNotify = lambda _: notifying(True)
        self.app.StopNotify = lambda _: notifying(False)
        self.bus.export(self.app.path, self.app)
        await self.app.register(self.adapter)
        self.registered = True
        service = next(iter(self.services))
        self.advertisement = PowerAdvertisement(self.name, self.app.base_path + "/advertisement", service, self._released)
        self.bus.export(self.advertisement.path, self.advertisement)
        manager = self.adapter.get_interface("org.bluez.LEAdvertisingManager1")
        await manager.call_register_advertisement(self.advertisement.path, {})
        self.advertisement_registered = True
        return True

    def _released(self):
        self.advertisement_registered = False

    async def stop(self):
        if not self.setup_task.done():
            self.setup_task.cancel()
        await asyncio.gather(self.setup_task, return_exceptions=True)
        try:
            if self.advertisement_registered:
                self.advertisement_registered = False
                manager = self.adapter.get_interface("org.bluez.LEAdvertisingManager1")
                try:
                    await manager.call_unregister_advertisement(self.advertisement.path)
                finally:
                    self.bus.unexport(self.advertisement.path)
        finally:
            try:
                if self.registered:
                    self.registered = False
                    await self.app.unregister(self.adapter)
            finally:
                if hasattr(self, "bus"):
                    self.bus.disconnect()
        return True
