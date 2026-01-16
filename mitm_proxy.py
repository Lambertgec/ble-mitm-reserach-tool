"""
Bluetooth LE Man-In-The-Middle proxy implementation.
Author: Boldizsar Keszthelyi
Date: 19/12/2025

Features:
- Acts as a central to the real peripheral (connect, subscribe, write)
- Maps services/characteristics and forwards/modifies packets
- Provides hooks for logging/analysis and packet modification
- Supports packet interception and modification

Notes:
- Peripheral emulation requires platform-specific implementation (BlueZ on Linux, 
  Windows.Devices.Bluetooth on Windows, or custom BLE stack)

Limitations:
- CANNOT emulate a BLE peripheral (no bidirectional MITM)
- CAN ONLY monitor peripheral -> central notifications
- CAN write to peripheral via public API
- Windows: No peripheral emulation support with Bleak
- For full MITM, use Linux with BlueZ
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, Tuple
from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

try:
    from .ble_peripheral_emulator import create_emulator
    EMULATOR_AVAILABLE = True
except ImportError:
    try:
        from ble_peripheral_emulator import create_emulator
        EMULATOR_AVAILABLE = True
    except ImportError:
        EMULATOR_AVAILABLE = False
        logger.warning("BLE peripheral emulator not available")

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
    advertise_name: Optional[str] = None      # name to advertise as emulated peripheral
    mapping: Dict[str, Any] = field(default_factory=dict)  # service/char mapping for emulator
    log_path: Optional[str] = None            # log file path (UNUSED - reserved for future)
    # Hooks for packet modification/analysis
    on_periph_notify: Optional[Callable] = None  # Called on notification from peripheral
    on_central_write: Optional[Callable] = None  # Called on write from central
    auto_subscribe: bool = True  # Auto-subscribe to all notifiable characteristics
    enable_emulator: bool = True  # Enable peripheral emulation (requires Linux/WSL)
    simple_emulator: bool = False  # Use simplified emulator for testing


class MITMProxy:
    """BLE MITM proxy that forwards and intercepts BLE traffic.

    Usage example:
        config = MITMProxyConfig(
            peripheral_address="AA:BB:CC:DD:EE:FF",
            advertise_name="MITM-Proxy",
            on_periph_notify=my_hook_func
        )
        proxy = MITMProxy(config)
        await proxy.start()
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await proxy.stop()
    """

    def __init__(self, config: MITMProxyConfig):
        self.config = config
        self.loop = asyncio.get_running_loop()
        self._running = False

        self._periph_client: Optional[BleakClient] = None  # connects to real peripheral
        self._emulator = None  # placeholder for peripheral-emulation component

        # Service and characteristic mappings
        self._services: Dict[str, Any] = {}
        self._notifiable_chars: set = set()
        self._writable_chars: set = set()
        self._subscribed_chars: set = set()  # Track successfully subscribed characteristics

        # Queues for internal forwarding
        self._periph_to_emulator_q: asyncio.Queue = asyncio.Queue()
        self._emulator_to_periph_q: asyncio.Queue = asyncio.Queue()

    async def start(self):
        """Start the proxy: connect to peripheral and start worker tasks.
        
        Raises:
            Exception: If connection to peripheral fails
        """
        logger.info("Starting MITM proxy")
        self._running = True

        # Connect to the real peripheral as a central
        if BleakClient is None:
            logger.warning("Bleak not available; peripheral connection will be disabled")
        else:
            if self.config.peripheral_address:
                try:
                    await self._connect_peripheral(self.config.peripheral_address)
                except Exception as e:
                    logger.exception(f"Failed to connect to peripheral: {e}")
                    self._running = False
                    raise

        # Start peripheral emulator if enabled and available
        if self.config.enable_emulator and EMULATOR_AVAILABLE:
            try:
                emulator_name = self.config.advertise_name or "MITM-Proxy"
                self._emulator = create_emulator(
                    advertise_name=emulator_name,
                    service_map=self._services,
                    on_write_callback=self._on_emulator_write,
                    simple=self.config.simple_emulator
                )
                await self._emulator.start()
                logger.info(f"Peripheral emulator started: {emulator_name}")
            except Exception as e:
                logger.error(f"Failed to start peripheral emulator: {e}")
                logger.warning("Continuing in monitoring-only mode")
                self._emulator = None
        elif self.config.enable_emulator and not EMULATOR_AVAILABLE:
            logger.warning("Peripheral emulator requested but not available")
            logger.warning("Install required packages: sudo apt install bluez bluetooth")
        else:
            logger.info("Peripheral emulator disabled - running in monitoring mode")

        # Worker tasks to forward messages
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
        
        Raises:
            Exception: If connection, discovery, or subscription fails
        """
        logger.info(f"Connecting to peripheral {address}")
        client = BleakClient(address)
        
        try:
            await client.connect()
            self._periph_client = client
            logger.info(f"Connected: {client.is_connected}")

            # Discover services and map characteristics
            await self._discover_services()

            # Subscribe to notifiable characteristics if enabled
            if self.config.auto_subscribe:
                await self._subscribe_to_notifications()

            # Start background task to flush writes from emulator->peripheral queue
            asyncio.create_task(self._periph_write_loop())
            
        except Exception as e:
            logger.error(f"Error during peripheral connection: {e}")
            if client and client.is_connected:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            self._periph_client = None
            raise

    async def _discover_services(self):
        """Discover services and characteristics from the real peripheral."""
        if not self._periph_client:
            logger.warning("No peripheral client for service discovery")
            return

        logger.info("Discovering services and characteristics...")
        
        for service in self._periph_client.services:
            service_uuid = str(service.uuid)
            self._services[service_uuid] = {
                'uuid': service_uuid,
                'characteristics': {}
            }
            logger.debug(f"Service: {service_uuid}")

            for char in service.characteristics:
                char_uuid = str(char.uuid)
                properties = char.properties
                
                self._services[service_uuid]['characteristics'][char_uuid] = {
                    'uuid': char_uuid,
                    'properties': properties,
                }

                # Track notifiable and writable characteristics
                if 'notify' in properties or 'indicate' in properties:
                    self._notifiable_chars.add(char_uuid)
                if 'write' in properties or 'write-without-response' in properties:
                    self._writable_chars.add(char_uuid)

                logger.debug(f"  Characteristic: {char_uuid} | Properties: {properties}")

        logger.info(f"Discovered {len(self._services)} services")
        logger.info(f"Notifiable characteristics: {len(self._notifiable_chars)}")
        logger.info(f"Writable characteristics: {len(self._writable_chars)}")

    def _make_notification_handler(self, char_uuid: str):
        """Create a notification handler for a specific characteristic.
        
        Uses a closure to avoid lambda late-binding issues.
        """
        def handler(sender: int, data: bytearray):
            self._on_peripheral_notification(char_uuid, sender, data)
        return handler
    
    async def _subscribe_to_notifications(self):
        """Subscribe to all notifiable characteristics on the real peripheral."""
        if not self._periph_client:
            logger.warning("No peripheral client for subscription")
            return

        logger.info(f"Subscribing to {len(self._notifiable_chars)} notifiable characteristics...")
        
        for char_uuid in self._notifiable_chars:
            try:
                handler = self._make_notification_handler(char_uuid)
                await self._periph_client.start_notify(char_uuid, handler)
                self._subscribed_chars.add(char_uuid)
                logger.debug(f"Subscribed to {char_uuid}")
            except Exception as e:
                logger.error(f"Failed to subscribe to {char_uuid}: {e}")
        
        logger.info(f"Successfully subscribed to {len(self._subscribed_chars)}/{len(self._notifiable_chars)} characteristics")

    def _on_peripheral_notification(self, char_uuid: str, sender: str, data: bytearray):
        """Handle notification from the real peripheral."""
        logger.debug(f"[PERIPH NOTIFY] {char_uuid}: {data.hex()}")
        
        # Call user hook if provided
        if self.config.on_periph_notify:
            try:
                modified_data = self.config.on_periph_notify(char_uuid, data)
                if modified_data is not None:
                    data = modified_data
                    logger.debug(f"[MODIFIED] {char_uuid}: {data.hex()}")
            except Exception as e:
                logger.exception(f"Error in on_periph_notify hook: {e}")
        
        # Enqueue for forwarding to emulator
        self._periph_to_emulator_q.put_nowait((char_uuid, data))

    async def _periph_write_loop(self):
        """Consume writes from emulator->peripheral queue and perform GATT writes."""
        if not self._periph_client:
            logger.warning("No peripheral client; write loop will exit")
            return
        
        while self._running:
            try:
                uuid, data = await self._emulator_to_periph_q.get()
                logger.debug(f"Forwarding write to peripheral {uuid} len={len(data)}")
                
                # Call user hook if provided
                if self.config.on_central_write:
                    try:
                        modified_data = self.config.on_central_write(uuid, data)
                        if modified_data is not None:
                            data = modified_data
                            logger.debug(f"[MODIFIED WRITE] {uuid}: {data.hex()}")
                    except Exception as e:
                        logger.exception(f"Error in on_central_write hook: {e}")
                
                # Determine if we should use write with response or without
                properties = None
                for service in self._periph_client.services:
                    for char in service.characteristics:
                        if str(char.uuid) == uuid:
                            properties = char.properties
                            break
                
                # Write to peripheral with appropriate response type
                if properties:
                    # Prefer write-without-response if available, otherwise use write-with-response
                    if 'write-without-response' in properties:
                        await self._periph_client.write_gatt_char(uuid, data, response=False)
                    elif 'write' in properties:
                        await self._periph_client.write_gatt_char(uuid, data, response=True)
                    else:
                        logger.warning(f"Characteristic {uuid} is not writable (properties: {properties})")
                        continue
                else:
                    # Default to write without response
                    logger.debug(f"No properties found for {uuid}, attempting write without response")
                    await self._periph_client.write_gatt_char(uuid, data, response=False)
                    
                logger.debug(f"Write successful to {uuid}")
                
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error forwarding write to peripheral")

    async def _periph_forward_loop(self):
        """Forward packets from peripheral -> emulator with optional modification.
        
        Forwards notifications from real peripheral to emulated peripheral.
        """
        while self._running:
            try:
                uuid, data = await self._periph_to_emulator_q.get()
                logger.debug(f"Periph -> Emulator: {uuid} ({data.hex()})")
                
                # Forward to emulated peripheral if available
                if self._emulator:
                    try:
                        await self._emulator.notify_characteristic(uuid, data)
                        logger.debug(f"Forwarded notification to emulator: {uuid}")
                    except Exception as e:
                        logger.error(f"Failed to forward to emulator: {e}")
                else:
                    # Just log if no emulator
                    logger.info(f"[NOTIFICATION] {uuid}: {data.hex()}")
                    
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in periph forward loop")
            finally:
                # Mark task as done to prevent queue buildup
                self._periph_to_emulator_q.task_done()

    async def _emulator_forward_loop(self):
        """Forward packets from emulator -> peripheral with optional modification.
        
        NOTE: This loop processes writes enqueued via write_to_peripheral().
        The _periph_write_loop() actually performs the writes to the peripheral.
        This loop is redundant in current implementation.
        """
        while self._running:
            try:
                # This queue is consumed by _periph_write_loop(), not here
                # This loop exists for symmetry but doesn't process the writes
                await asyncio.sleep(0.1)  # Prevent tight loop
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in emulator forward loop")

    async def write_to_peripheral(self, char_uuid: str, data: bytes):
        """Public API to write data to a characteristic on the real peripheral."""
        await self._emulator_to_periph_q.put((char_uuid, data))
        logger.info(f"Enqueued write to {char_uuid}: {data.hex()}")

    def get_service_map(self) -> Dict[str, Any]:
        """Get the discovered service and characteristic mapping."""
        return self._services
    
    def _on_emulator_write(self, char_uuid: str, data: bytes):
        """Handle write from central device to emulated peripheral.
        
        This is called when a central device writes to our emulated peripheral.
        We forward it to the real peripheral.
        """
        logger.info(f"[CENTRAL WRITE] {char_uuid}: {data.hex()}")
        
        # Enqueue write to real peripheral
        asyncio.create_task(self.write_to_peripheral(char_uuid, data))
    
    def get_subscription_status(self) -> dict:
        """Get subscription status information.
        
        Returns:
            dict with subscription statistics and lists of subscribed/failed characteristics
        """
        return {
            'total_notifiable': len(self._notifiable_chars),
            'successfully_subscribed': len(self._subscribed_chars),
            'failed': len(self._notifiable_chars - self._subscribed_chars),
            'subscribed_chars': list(self._subscribed_chars),
            'failed_chars': list(self._notifiable_chars - self._subscribed_chars)
        }


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

    p = argparse.ArgumentParser(description="BLE MITM Proxy - Forward and intercept BLE traffic")
    p.add_argument("--peripheral", required=True, help="Address of the real peripheral (MAC) to connect to")
    p.add_argument("--name", help="Advertise name for the emulated peripheral", default="MITM-Proxy")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = p.parse_args()

    logger.setLevel(args.log_level)

    cfg = MITMProxyConfig(peripheral_address=args.peripheral, advertise_name=args.name)
    try:
        asyncio.run(main_loop(cfg))
    except KeyboardInterrupt:
        logger.info("Interrupted")
