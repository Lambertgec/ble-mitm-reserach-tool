import asyncio
from dbus_next.aio import MessageBus

BUS_ADDR = "unix:path=/run/dbus/system_bus_socket"

async def main():
    print("[*] starting", flush=True)

    print(f"[*] connecting to system bus: {BUS_ADDR}", flush=True)
    bus = await MessageBus(bus_address=BUS_ADDR).connect()
    print("[+] connected", flush=True)

    print("[*] introspecting org.bluez /org/bluez/hci0 (timeout=5s)...", flush=True)
    node = await asyncio.wait_for(
        bus.introspect("org.bluez", "/org/bluez/hci0"),
        timeout=5.0
    )
    print("[+] introspection OK", flush=True)
    print(node, flush=True)

asyncio.run(main())
