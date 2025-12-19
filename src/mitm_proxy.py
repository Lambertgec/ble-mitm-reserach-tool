"""
Skeleton Bluetooth LE Man-In-The-Middle proxy.
Author: Boldizsar Keszthelyi
Date: 19/12/2025

Expected from a complete implementation:
- Act as a central to the real peripheral (connect, subscribe, write)
- Emulate a peripheral to the original central (advertise and accept connections)
- Map services/characteristics between the two sides and forward/modify packets
- Provide hooks for logging/analysis and for injecting/modifying traffic

Notes:
- For periphreal emulation we might need BlueZ D-Bus, hcitool/ATT tools, or platform
  specific libraries. This skeleton does not implement the emulation part.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from bleak import BleakClient

logger = logging.getLogger("mitm_proxy")
if not logger.handlers:
    h = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    h.setFormatter(fmt)
    logger.addHandler(h)
logger.setLevel(logging.INFO)


@dataclass
class MITMProxyConfig:
    peripheral_address: Optional[str] = None  # address of the real device
    advertise_name: Optional[str] = None      # name to advertise to the central
    mapping: Dict[str, Any] = field(default_factory=dict)  # service/char mapping
    log_path: Optional[str] = None


class MITMProxy:
    """Skeleton for a BLE MITM proxy.

    Usage example:
        proxy = MITMProxy(config)
        await proxy.start()
        # proxy is now running, use hooks to control/inspect traffic
        await proxy.stop()
    """

    def __init__(self, config: MITMProxyConfig):
        self.config = config
        self.loop = asyncio.get_running_loop()
        self._running = False

        self._periph_client: Optional[BleakClient] = None  # connects to real peripheral
        self._emulator = None  # placeholder for peripheral-emulation component

        # Queues for internal forwarding
        self._periph_to_emulator_q: asyncio.Queue = asyncio.Queue()
        self._emulator_to_periph_q: asyncio.Queue = asyncio.Queue()

    async def start(self):
        """Start the proxy: connect to peripheral and start emulator.

        This scaffold starts worker tasks that read from queues and call
        placeholder handlers. Real connection/emulation logic needs to be filled.
        """
        logger.info("Starting MITM proxy")
        self._running = True

        # TODO: connect to the real peripheral as a central
        if BleakClient is None:
            logger.warning("Bleak not available; peripheral connection will be disabled in scaffold")
        else:
            if self.config.peripheral_address:
                await self._connect_peripheral(self.config.peripheral_address)

        # TODO: start peripheral emulator here (platform-specific)
        # self._emulator = start_emulator(name=self.config.advertise_name, mapping=self.config.mapping)

        # Worker tasks to forward messages (placeholders)
        self._tasks = [
            asyncio.create_task(self._periph_forward_loop()),
            asyncio.create_task(self._emulator_forward_loop()),
        ]

    async def stop(self):
        """Stop the proxy, cancel tasks and disconnect clients."""
        logger.info("Stopping MITM proxy")
        self._running = False
        for t in getattr(self, "_tasks", []):
            t.cancel()
        # Stop emulator if present. Depending on emulator, this may have to be changed.
        if self._emulator:
            try:
                await self._emulator.stop()
            except Exception:
                logger.exception("Error stopping emulator")
            finally:
                self._emulator = None
        if self._periph_client:
            try:
                await self._periph_client.disconnect()
            except Exception:
                logger.exception("Error disconnecting from peripheral")

    async def _connect_peripheral(self, address: str):
        """Connect to the real peripheral and setup notifications/writes.

        TODO: subscribe to characteristics and enqueue incoming packets into
        `self._periph_to_emulator_q`. Also consume `self._emulator_to_periph_q`
        to perform writes to the real peripheral.
        """

        logger.info(f"Connecting to peripheral {address}")
        client = BleakClient(address)
        await client.connect()
        self._periph_client = client
        logger.info(f"Connected: {client.is_connected}")

        # TODO: discover services, subscribe to notifications and push to queue
        # Example:
        # await client.start_notify(some_uuid, lambda s, d: self._periph_to_emulator_q.put_nowait((s, d)))

        # Start background task to flush writes from emulator->peripheral queue
        asyncio.create_task(self._periph_write_loop())

    async def _periph_write_loop(self):
        """Consume writes from emulator->peripheral queue and perform GATT writes.

        TODO: implement write semantics and optional write-with-response handling.
        """
        if not self._periph_client:
            logger.warning("No peripheral client; write loop will exit")
            return
        while self._running:
            try:
                uuid, data = await self._emulator_to_periph_q.get()
                logger.debug(f"Forwarding write to peripheral {uuid} len={len(data)}")
                await self._periph_client.write_gatt_char(uuid, data)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error forwarding write to peripheral")

    async def _periph_forward_loop(self):
        """Placeholder loop to forward packets from peripheral -> emulator.

        In a real proxy this would take notifications from the BLE client and
        apply mapping/transformations before delivering them to the emulated
        peripheral/central connection.
        """
        while self._running:
            try:
                item = await self._periph_to_emulator_q.get()
                # TODO: transform/route the item
                logger.debug(f"Periph -> Emulator: {item}")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in periph forward loop")

    async def _emulator_forward_loop(self):
        """Placeholder loop to forward packets from emulator -> peripheral.

        This would accept writes/commands from the emulated side and enqueue
        them to `_emulator_to_periph_q` for delivery to the real peripheral.
        """
        while self._running:
            try:
                item = await self._emulator_to_periph_q.get()
                # TODO: transform/route the item
                logger.debug(f"Emulator -> Periph: {item}")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in emulator forward loop")


async def main_loop(config: MITMProxyConfig):
    proxy = MITMProxy(config)
    await proxy.start()
    try:
        # Run until cancelled
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await proxy.stop()


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--peripheral", help="Address of the real peripheral (MAC) to connect to")
    p.add_argument("--name", help="Advertise name for the emulated peripheral", default="MITM-Proxy")
    args = p.parse_args()

    cfg = MITMProxyConfig(peripheral_address=args.peripheral, advertise_name=args.name)
    try:
        asyncio.run(main_loop(cfg))
    except KeyboardInterrupt:
        logger.info("Interrupted")
