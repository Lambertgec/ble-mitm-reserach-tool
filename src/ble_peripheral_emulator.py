"""
BLE Peripheral Emulator for Linux/WSL using BlueZ
Author: Modified for WSL support
Date: 10/01/2026

This module provides peripheral emulation capabilities for the MITM proxy
using BlueZ on Linux systems (including WSL).

Requirements:
- BlueZ installed
- DBus Python bindings
- Root/sudo privileges may be needed for some operations
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable
import subprocess
import os

logger = logging.getLogger("ble_peripheral_emulator")

class BLEPeripheralEmulator:
    """
    BLE Peripheral Emulator using BlueZ on Linux.
    
    This class provides a simplified interface to advertise as a BLE peripheral
    and handle incoming connections/writes from central devices.
    """
    
    def __init__(self, 
                 advertise_name: str = "MITM-Device",
                 service_map: Optional[Dict[str, Any]] = None,
                 on_write_callback: Optional[Callable] = None):
        """
        Initialize the peripheral emulator.
        
        Args:
            advertise_name: Name to advertise (will be visible to scanning devices)
            service_map: Dictionary of services and characteristics to emulate
            on_write_callback: Callback function when data is written to a characteristic
        """
        self.advertise_name = advertise_name
        self.service_map = service_map or {}
        self.on_write_callback = on_write_callback
        self._running = False
        self._advertise_process = None
        
        # Store characteristic values
        self._char_values: Dict[str, bytearray] = {}
        
    async def start(self):
        """Start advertising as a BLE peripheral."""
        logger.info(f"Starting BLE peripheral emulator: {self.advertise_name}")
        self._running = True
        
        # Check if BlueZ is available
        if not self._check_bluez():
            logger.error("BlueZ not found. Please install: sudo apt install bluez")
            return False
            
        try:
            # Start advertising
            await self._start_advertising()
            logger.info("Peripheral emulator started successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to start peripheral emulator: {e}")
            return False
    
    async def stop(self):
        """Stop the peripheral emulator and advertising."""
        logger.info("Stopping BLE peripheral emulator")
        self._running = False
        
        if self._advertise_process:
            try:
                self._advertise_process.terminate()
                await asyncio.sleep(0.5)
                if self._advertise_process.poll() is None:
                    self._advertise_process.kill()
            except Exception as e:
                logger.error(f"Error stopping advertising: {e}")
        
        # Reset bluetooth adapter
        try:
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'down'], 
                          check=False, capture_output=True)
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'up'], 
                          check=False, capture_output=True)
        except Exception as e:
            logger.warning(f"Could not reset adapter: {e}")
    
    def _check_bluez(self) -> bool:
        """Check if BlueZ is installed and accessible."""
        try:
            result = subprocess.run(['which', 'bluetoothctl'], 
                                   capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False
    
    async def _start_advertising(self):
        """Start BLE advertising using hcitool."""
        try:
            # Enable the adapter
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'up'], check=True)
            
            # Set advertising parameters
            # This is a simplified advertising - for full MITM you'd need to
            # advertise the exact services/characteristics of the target device
            
            # Enable advertising
            cmd = [
                'sudo', 'hcitool', '-i', 'hci0', 'cmd',
                '0x08', '0x0008',  # Set advertising data
                '1e',  # Length
                '02', '01', '06',  # Flags
                f'{len(self.advertise_name)+1:02x}', '09',  # Complete local name
            ]
            
            # Add name in hex
            name_hex = ''.join(f'{ord(c):02x}' for c in self.advertise_name)
            cmd.extend(name_hex[i:i+2] for i in range(0, len(name_hex), 2))
            
            logger.debug(f"Advertising command: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=True)
            
            # Enable advertising
            subprocess.run([
                'sudo', 'hcitool', '-i', 'hci0', 'cmd',
                '0x08', '0x000a',  # Set advertising enable
                '01'  # Enable
            ], check=True, capture_output=True)
            
            logger.info(f"Advertising as '{self.advertise_name}'")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start advertising: {e.stderr if e.stderr else str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error starting advertising: {e}")
            raise
    
    async def notify_characteristic(self, char_uuid: str, data: bytes):
        """
        Send a notification for a characteristic.
        
        Args:
            char_uuid: UUID of the characteristic
            data: Data to send in the notification
        """
        logger.debug(f"Notifying {char_uuid}: {data.hex()}")
        self._char_values[char_uuid] = bytearray(data)
        
        # In a full implementation, this would send a GATT notification
        # For now, this is a placeholder
        # You would need to use BlueZ GATT API through D-Bus for full implementation
        
    def get_characteristic_value(self, char_uuid: str) -> Optional[bytearray]:
        """Get the current value of a characteristic."""
        return self._char_values.get(char_uuid)
    
    def set_characteristic_value(self, char_uuid: str, value: bytearray):
        """Set the value of a characteristic."""
        self._char_values[char_uuid] = value
        logger.debug(f"Set {char_uuid} = {value.hex()}")


class SimpleBLEPeripheralEmulator:
    """
    Simplified BLE peripheral emulator using Bleak's advertising capabilities.
    
    Note: Bleak primarily supports central role. For full peripheral emulation,
    consider using bless library or BlueZ D-Bus API directly.
    """
    
    def __init__(self, advertise_name: str = "MITM-Device"):
        self.advertise_name = advertise_name
        self._running = False
    
    async def start(self):
        """Start the emulator."""
        logger.info(f"SimpleBLEPeripheralEmulator: {self.advertise_name}")
        logger.warning("Note: Full peripheral emulation requires additional setup")
        logger.warning("Consider using 'bless' library for Python-based GATT server")
        self._running = True
        return True
    
    async def stop(self):
        """Stop the emulator."""
        logger.info("Stopping SimpleBLEPeripheralEmulator")
        self._running = False
    
    async def notify_characteristic(self, char_uuid: str, data: bytes):
        """Placeholder for notifications."""
        logger.debug(f"[EMULATOR] Would notify {char_uuid}: {data.hex()}")


# Factory function to create appropriate emulator
def create_emulator(advertise_name: str = "MITM-Device",
                   service_map: Optional[Dict[str, Any]] = None,
                   on_write_callback: Optional[Callable] = None,
                   simple: bool = False):
    """
    Create a BLE peripheral emulator appropriate for the platform.
    
    Args:
        advertise_name: Device name to advertise
        service_map: Services and characteristics to emulate
        on_write_callback: Callback for write events
        simple: If True, use simple emulator (for testing)
    
    Returns:
        BLEPeripheralEmulator instance
    """
    if simple or os.name != 'posix':
        logger.warning("Using simplified emulator - limited functionality")
        return SimpleBLEPeripheralEmulator(advertise_name)
    else:
        return BLEPeripheralEmulator(advertise_name, service_map, on_write_callback)
