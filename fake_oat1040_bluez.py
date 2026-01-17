#!/usr/bin/env python3
"""
Fake OAT1040 BLE Peripheral (BlueZ + D-Bus, dbus-next)

- Advertises as "OAT1040"
- Minimal GATT with JustWorks pairing (no user interaction)

Requirements:
  pip install dbus-next
  sudo apt install bluez bluetooth

Run:
  sudo -E $(which python) fake_oat1040_bluez.py --adapter hci1 --debug
"""

import argparse
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface, dbus_property, method, signal

LOG = logging.getLogger("fake_oat1040")

BLUEZ_SERVICE_NAME = "org.bluez"

# Standard interfaces
IFACE_OBJ_MANAGER = "org.freedesktop.DBus.ObjectManager"
IFACE_PROPERTIES = "org.freedesktop.DBus.Properties"

# BlueZ interfaces
IFACE_GATT_MANAGER = "org.bluez.GattManager1"
IFACE_LE_ADV_MGR = "org.bluez.LEAdvertisingManager1"
IFACE_GATT_SERVICE = "org.bluez.GattService1"
IFACE_GATT_CHAR = "org.bluez.GattCharacteristic1"
IFACE_LE_ADV = "org.bluez.LEAdvertisement1"
IFACE_AGENT_MANAGER = "org.bluez.AgentManager1"
IFACE_AGENT = "org.bluez.Agent1"


class PropertiesInterface(ServiceInterface):
    """org.freedesktop.DBus.Properties - for PropertiesChanged signals"""
    def __init__(self) -> None:
        super().__init__(IFACE_PROPERTIES)

    @signal(name="PropertiesChanged")
    def PropertiesChanged(self, interface: "s", changed: "a{sv}", invalidated: "as") -> None:  # type: ignore
        ...


class Advertisement(ServiceInterface):
    """org.bluez.LEAdvertisement1"""

    def __init__(self, path: str, local_name: str, service_uuids: List[str]) -> None:
        super().__init__(IFACE_LE_ADV)
        self.path = path
        self._type = "peripheral"
        self._local_name = local_name
        self._service_uuids = service_uuids
        self._discoverable = True

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "s":  # type: ignore
        return self._type

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> "s":  # type: ignore
        return self._local_name

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> "as":  # type: ignore
        return self._service_uuids

    @dbus_property(access=PropertyAccess.READ)
    def Discoverable(self) -> "b":  # type: ignore
        return self._discoverable

    @method()
    def Release(self) -> None:
        LOG.info("Advertisement released by BlueZ")


class PairingAgent(ServiceInterface):
    """org.bluez.Agent1 - Auto-accepts JustWorks pairing"""

    def __init__(self, path: str) -> None:
        super().__init__(IFACE_AGENT)
        self.path = path

    @method()
    def Release(self) -> None:
        LOG.info("Pairing agent released")

    @method()
    def RequestPinCode(self, device: "o") -> "s":  # type: ignore
        LOG.warning("RequestPinCode from %s - rejecting (use JustWorks)", device)
        raise DBusError("org.bluez.Error.Rejected", "No PIN capability")

    @method()
    def RequestPasskey(self, device: "o") -> "u":  # type: ignore
        LOG.warning("RequestPasskey from %s - rejecting (use JustWorks)", device)
        raise DBusError("org.bluez.Error.Rejected", "No passkey capability")

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "y") -> None:  # type: ignore
        LOG.debug("DisplayPasskey for %s: %d", device, passkey)

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s") -> None:  # type: ignore
        LOG.debug("DisplayPinCode for %s: %s", device, pincode)

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u") -> None:  # type: ignore
        """AUTO-ACCEPT for JustWorks - just return without error"""
        LOG.info("RequestConfirmation from %s (passkey %d) - AUTO-ACCEPTING", device, passkey)

    @method()
    def RequestAuthorization(self, device: "o") -> None:  # type: ignore
        """AUTO-ACCEPT authorization"""
        LOG.info("RequestAuthorization from %s - AUTO-ACCEPTING", device)

    @method()
    def AuthorizeService(self, device: "o", uuid: "s") -> None:  # type: ignore
        LOG.debug("AuthorizeService %s on %s - AUTO-ACCEPTING", uuid, device)

    @method()
    def Cancel(self) -> None:
        LOG.info("Cancel called")


class GattService(ServiceInterface):
    """org.bluez.GattService1"""

    def __init__(self, path: str, uuid: str, primary: bool = True) -> None:
        super().__init__(IFACE_GATT_SERVICE)
        self.path = path
        self._uuid = uuid
        self._primary = primary

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":  # type: ignore
        return self._uuid

    @dbus_property(access=PropertyAccess.READ)
    def Primary(self) -> "b":  # type: ignore
        return self._primary

    def get_properties(self) -> Dict[str, Any]:
        """Return all properties as a dict for GetManagedObjects"""
        return {
            IFACE_GATT_SERVICE: {
                "UUID": Variant("s", self._uuid),
                "Primary": Variant("b", self._primary),
            }
        }


class GattCharacteristic(ServiceInterface):
    """org.bluez.GattCharacteristic1"""

    def __init__(
        self,
        path: str,
        uuid: str,
        service_path: str,
        flags: List[str],
        props_iface: PropertiesInterface,
        on_write: Optional[Callable[[bytes], None]] = None,
        initial_value: bytes = b"",
    ) -> None:
        super().__init__(IFACE_GATT_CHAR)
        self.path = path
        self._uuid = uuid
        self._service_path = service_path
        self._flags = flags
        self._props = props_iface
        self._notifying = False
        self._value = initial_value
        self._on_write = on_write

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":  # type: ignore
        return self._uuid

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":  # type: ignore
        return self._service_path

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":  # type: ignore
        return self._flags

    @dbus_property(access=PropertyAccess.READ)
    def Notifying(self) -> "b":  # type: ignore
        return self._notifying

    @dbus_property(access=PropertyAccess.READ)
    def Value(self) -> "ay":  # type: ignore
        return self._value

    @method()
    def ReadValue(self, options: "a{sv}") -> "ay":  # type: ignore
        LOG.debug("ReadValue %s", self._uuid)
        return self._value

    @method()
    def WriteValue(self, value: "ay", options: "a{sv}") -> None:  # type: ignore
        data = bytes(value)
        LOG.info("WriteValue %s: %s", self._uuid, data.hex())
        if self._on_write:
            self._on_write(data)

    @method()
    def StartNotify(self) -> None:
        LOG.info("StartNotify %s", self._uuid)
        self._notifying = True
        self._props.PropertiesChanged(
            IFACE_GATT_CHAR,
            {"Notifying": Variant("b", True)},
            [],
        )

    @method()
    def StopNotify(self) -> None:
        LOG.info("StopNotify %s", self._uuid)
        self._notifying = False
        self._props.PropertiesChanged(
            IFACE_GATT_CHAR,
            {"Notifying": Variant("b", False)},
            [],
        )

    def push_notify(self, data: bytes) -> None:
        """Push notification to subscribed centrals"""
        self._value = data
        if not self._notifying:
            return
        self._props.PropertiesChanged(
            IFACE_GATT_CHAR,
            {"Value": Variant("ay", data)},
            [],
        )

    def get_properties(self) -> Dict[str, Any]:
        """Return all properties for GetManagedObjects"""
        return {
            IFACE_GATT_CHAR: {
                "UUID": Variant("s", self._uuid),
                "Service": Variant("o", self._service_path),
                "Flags": Variant("as", self._flags),
                "Notifying": Variant("b", self._notifying),
                "Value": Variant("ay", self._value),
            }
        }


class Application(ServiceInterface):
    """org.freedesktop.DBus.ObjectManager"""

    def __init__(self, path: str) -> None:
        super().__init__(IFACE_OBJ_MANAGER)
        self.path = path
        self.services: List[GattService] = []
        self.characteristics: List[GattCharacteristic] = []

    @method()
    def GetManagedObjects(self) -> "a{oa{sa{sv}}}":  # type: ignore
        """Build and return the managed objects tree"""
        response: Dict[str, Any] = {}
        
        LOG.debug("GetManagedObjects called")
        
        # Add all services
        for svc in self.services:
            response[svc.path] = svc.get_properties()
            LOG.debug("  Added service %s at %s", svc._uuid, svc.path)
        
        # Add all characteristics
        for char in self.characteristics:
            response[char.path] = char.get_properties()
            LOG.debug("  Added char %s at %s", char._uuid, char.path)
        
        LOG.debug("Returning %d managed objects", len(response))
        return response


class FakeOAT1040Peripheral:
    """Fake OAT1040 peripheral wrapper"""

    def __init__(self, adapter: str = "hci0") -> None:
        self.adapter = adapter
        self.bus: Optional[MessageBus] = None
        self.app_path = "/com/mitm/app"
        self.adv_path = "/com/mitm/advertisement"
        self.agent_path = "/com/mitm/agent"
        self.on_phone_write: Optional[Callable[[str, bytes], None]] = None
        self._chars: Dict[str, GattCharacteristic] = {}
        self._app = Application(self.app_path)

    def set_write_callback(self, cb: Callable[[str, bytes], None]) -> None:
        self.on_phone_write = cb

    async def start(self) -> None:
        # Connect to system bus
        self.bus = await MessageBus(bus_address="unix:path=/run/dbus/system_bus_socket").connect()
        adapter_path = f"/org/bluez/{self.adapter}"

        # Configure adapter
        LOG.info("Configuring adapter %s...", self.adapter)
        try:
            node = await asyncio.wait_for(
                self.bus.introspect(BLUEZ_SERVICE_NAME, adapter_path),
                timeout=5.0,
            )
            proxy = self.bus.get_proxy_object(BLUEZ_SERVICE_NAME, adapter_path, node)
            adapter_props = proxy.get_interface(IFACE_PROPERTIES)
            
            await adapter_props.call_set("org.bluez.Adapter1", "Pairable", Variant("b", True))
            await adapter_props.call_set("org.bluez.Adapter1", "PairableTimeout", Variant("u", 0))
            await adapter_props.call_set("org.bluez.Adapter1", "Discoverable", Variant("b", True))
            LOG.info("Adapter configured")
        except Exception as e:
            LOG.warning("Could not configure adapter: %s", e)

        # Register pairing agent
        LOG.info("Registering pairing agent...")
        try:
            agent = PairingAgent(self.agent_path)
            self.bus.export(self.agent_path, agent)
            
            node = await asyncio.wait_for(
                self.bus.introspect(BLUEZ_SERVICE_NAME, "/org/bluez"),
                timeout=5.0,
            )
            proxy = self.bus.get_proxy_object(BLUEZ_SERVICE_NAME, "/org/bluez", node)
            agent_mgr = proxy.get_interface(IFACE_AGENT_MANAGER)
            
            await asyncio.wait_for(
                agent_mgr.call_register_agent(self.agent_path, "NoInputNoOutput"),
                timeout=5.0,
            )
            await asyncio.wait_for(
                agent_mgr.call_request_default_agent(self.agent_path),
                timeout=5.0,
            )
            LOG.info("Pairing agent registered")
        except Exception as e:
            LOG.warning("Could not register pairing agent: %s", e)

        # Create services
        svc_d0ff_path = f"{self.app_path}/service0"
        svc_55ff_path = f"{self.app_path}/service1"
        svc_fee7_path = f"{self.app_path}/service2"

        svc_d0ff = GattService(svc_d0ff_path, "0000d0ff-0000-1000-8000-00805f9b34fb")
        svc_55ff = GattService(svc_55ff_path, "000055ff-0000-1000-8000-00805f9b34fb")
        svc_fee7 = GattService(svc_fee7_path, "0000fee7-0000-1000-8000-00805f9b34fb")

        self._app.services = [svc_d0ff, svc_55ff, svc_fee7]

        # Create characteristics
        char_ffd1_path = f"{self.app_path}/service0/char0"
        char_fea1_path = f"{self.app_path}/service2/char0"
        char_33f2_path = f"{self.app_path}/service1/char0"

        props_ffd1 = PropertiesInterface()
        props_fea1 = PropertiesInterface()
        props_33f2 = PropertiesInterface()

        def _ffd1_written(data: bytes) -> None:
            if self.on_phone_write:
                self.on_phone_write("0000ffd1-0000-1000-8000-00805f9b34fb", data)

        char_ffd1 = GattCharacteristic(
            path=char_ffd1_path,
            uuid="0000ffd1-0000-1000-8000-00805f9b34fb",
            service_path=svc_d0ff_path,
            flags=["write", "write-without-response"],
            props_iface=props_ffd1,
            on_write=_ffd1_written,
        )

        char_fea1 = GattCharacteristic(
            path=char_fea1_path,
            uuid="0000fea1-0000-1000-8000-00805f9b34fb",
            service_path=svc_fee7_path,
            flags=["notify"],
            props_iface=props_fea1,
            initial_value=b"\x07" + b"\x00" * 9,
        )

        char_33f2 = GattCharacteristic(
            path=char_33f2_path,
            uuid="000033f2-0000-1000-8000-00805f9b34fb",
            service_path=svc_55ff_path,
            flags=["notify"],
            props_iface=props_33f2,
            initial_value=b"\x1c",
        )

        self._app.characteristics = [char_ffd1, char_fea1, char_33f2]
        self._chars[char_ffd1._uuid] = char_ffd1
        self._chars[char_fea1._uuid] = char_fea1
        self._chars[char_33f2._uuid] = char_33f2

        # Export everything
        self.bus.export(self.app_path, self._app)

        for svc in self._app.services:
            self.bus.export(svc.path, svc)

        for char in self._app.characteristics:
            self.bus.export(char.path, char)
            self.bus.export(char.path, char._props)

        # Small delay for D-Bus to settle
        await asyncio.sleep(0.2)

        # Register GATT application
        LOG.info("Registering GATT application on %s...", adapter_path)
        try:
            node = await asyncio.wait_for(
                self.bus.introspect(BLUEZ_SERVICE_NAME, adapter_path),
                timeout=5.0,
            )
            proxy = self.bus.get_proxy_object(BLUEZ_SERVICE_NAME, adapter_path, node)
            gatt_iface = proxy.get_interface(IFACE_GATT_MANAGER)
            
            await asyncio.wait_for(
                gatt_iface.call_register_application(self.app_path, {}),
                timeout=10.0,
            )
            LOG.info("GATT application registered successfully")
        except Exception as e:
            LOG.error("Failed to register GATT application: %s", e)
            raise

        # Register advertisement
        LOG.info("Registering advertisement...")
        try:
            adv = Advertisement(
                path=self.adv_path,
                local_name="OAT1040",
                service_uuids=[
                    "0000d0ff-0000-1000-8000-00805f9b34fb",
                    "000055ff-0000-1000-8000-00805f9b34fb",
                    "0000fee7-0000-1000-8000-00805f9b34fb",
                ],
            )
            self.bus.export(self.adv_path, adv)

            adv_iface = proxy.get_interface(IFACE_LE_ADV_MGR)
            await adv_iface.call_register_advertisement(self.adv_path, {})
            LOG.info("Advertisement registered successfully")
        except Exception as e:
            LOG.error("Failed to register advertisement: %s", e)
            raise

        LOG.info("Fake peripheral started. Phone should see 'OAT1040'.")

    def notify_characteristic(self, uuid: str, data: bytes) -> None:
        ch = self._chars.get(uuid)
        if not ch:
            LOG.debug("notify_characteristic: unknown uuid %s", uuid)
            return
        ch.push_notify(data)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default="hci0")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s:%(name)s:%(message)s")

    fake = FakeOAT1040Peripheral(adapter=args.adapter)

    def on_write(uuid: str, data: bytes) -> None:
        LOG.info("PHONE -> FAKE %s: %s", uuid, data.hex())

    fake.set_write_callback(on_write)

    try:
        await fake.start()
    except Exception as e:
        LOG.error("Failed to start peripheral: %s", e)
        return

    # Test loop
    try:
        i = 0
        while True:
            fake.notify_characteristic(
                "0000fea1-0000-1000-8000-00805f9b34fb",
                b"\x07" + b"\x00" * 9,
            )
            if i % 5 == 0:
                fake.notify_characteristic(
                    "000033f2-0000-1000-8000-00805f9b34fb",
                    b"\x1c",
                )
            i += 1
            await asyncio.sleep(1.0)
    except KeyboardInterrupt:
        LOG.info("Exiting...")


if __name__ == "__main__":
    asyncio.run(main())