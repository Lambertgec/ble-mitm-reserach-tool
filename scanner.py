"""
BLE Scanner for Security Research
Author: Boldizsar Keszthelyi
Date: 02/12/2025

Basic scanner to discover BLE devices and analyze pairing methods. 
The scan results help in identifying potential vulnerable devices, allowing for further analysis.
Device fingerprinting is also possible via manufacturer data and service UUIDs.

Inspired by concepts from gattacker.

Need to test with our actual OAT1040 tracker device still, but seemed to be working fine. 
"""

import asyncio
from bleak import BleakScanner
import json
from datetime import datetime

class BLEScanner:
    def __init__(self):
        self.devices = {}
    
    async def scan(self, duration=10):
        # Scan for BLE devices
        print(f"Scanning for {duration} seconds...")
        
        devices = await BleakScanner.discover(
            timeout=duration,
            return_adv=True
        )
        
        for device, adv_data in devices.values():
            # Convert manufacturer_data bytes to hex strings for JSON serialization
            manufacturer_data_hex = {
                key: value.hex() for key, value in adv_data.manufacturer_data.items()
            }
            
            self.devices[device.address] = {
                'name': device.name or 'Unknown',
                'address': device.address,
                'rssi': adv_data.rssi,
                'services': adv_data.service_uuids,
                'manufacturer_data': manufacturer_data_hex,
                'timestamp': datetime.now().isoformat()
            }
            
            print(f"\nFound: {device.name} ({device.address})")
            print(f"RSSI: {adv_data.rssi} dBm")
            print(f"Services: {adv_data.service_uuids}")
        
        return self.devices
    
    def save_results(self, filename='scan_results.json'):
        # Save scan results to file
        with open(filename, 'w') as f:
            json.dump(self.devices, f, indent=2)
        print(f"\nResults saved to {filename}")

# Test
if __name__ == "__main__":
    scanner = BLEScanner()
    asyncio.run(scanner.scan(5))
    scanner.save_results()