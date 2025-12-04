"""
GATT Service Enumerator
Author: Boldizsar Keszthelyi
Date: 04/12/2025

Connects to BLE device and enumerates all GATT services, characteristics,
and descriptors. Used to understand device structure before MITM attack. 

Usage: python GATT_enum.py <BLE_MAC_ADDRESS>

Inspired by gattacker's service enumeration approach
"""

import asyncio
from bleak import BleakClient
import json
from datetime import datetime

class GATTEnumerator:
    def __init__(self, address):
        self.address = address
        self.services = {}
        self.device_info = {}
    
    async def connect_and_enumerate(self):
        # Connect to device and enumerate all GATT services
        print(f"\n[*] Connecting to {self.address}...")
        
        try:
            async with BleakClient(self.address, timeout=20.0) as client:
                print(f"[+] Connected, MTU: {client.mtu_size}")
                
                # Get basic device info
                self.device_info = {
                    'address': self.address,
                    'mtu': client.mtu_size,
                    'connected': client.is_connected,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Enumerate services
                print(f"\n[*] Enumerating services...")
                await self._enumerate_services(client)
                
                print(f"\n[+] Found {len(self.services)} services")
                return self.services
                
        except Exception as e:
            print(f"[-] Connection failed: {e}")
            return None
    
    async def _enumerate_services(self, client):
        # Enumerate all services and their characteristics 
        
        for service in client.services:
            service_uuid = str(service.uuid)
            
            print(f"\n[+] Service: {service_uuid}")
            print(f"    Description: {service.description}")
            
            self.services[service_uuid] = {
                'uuid': service_uuid,
                'description': service.description,
                'characteristics': []
            }
            
            # Enumerate characteristics
            for char in service.characteristics:
                char_info = await self._analyze_characteristic(client, char)
                self.services[service_uuid]['characteristics'].append(char_info)
    
    async def _analyze_characteristic(self, client, char):
        # Analyze a single characteristic
        char_uuid = str(char.uuid)
        properties = char.properties
        
        print(f"    [*] Characteristic: {char_uuid}")
        print(f"        Properties: {properties}")
        
        char_info = {
            'uuid': char_uuid,
            'description': char.description,
            'properties': properties,
            'descriptors': [str(d.uuid) for d in char.descriptors],
            'value': None,
            'readable': False,
            'writable': False,
            'notifiable': False
        }
        
        # Check properties
        if 'read' in properties:
            char_info['readable'] = True
            # Try to read value
            try:
                value = await client.read_gatt_char(char_uuid)
                char_info['value'] = value.hex()
                print(f"        Value: {value.hex()} ({self._hex_to_ascii(value)})")
            except Exception as e:
                print(f"        Read failed: {e}")
        
        if 'write' in properties or 'write-without-response' in properties:
            char_info['writable'] = True
            print(f"        !!!!!  WRITABLE - attackable !!!!!")
        
        if 'notify' in properties or 'indicate' in properties:
            char_info['notifiable'] = True
            print(f"        !!!!! NOTIFIABLE - streams data !!!!!")
        
        return char_info
    
    def _hex_to_ascii(self, data):
        # Convert hex to readable ASCII 
        try:
            return ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
        except:
            return ''
    
    def save_profile(self, filename=None):
        # Save device profile to JSON 
        if not filename:
            filename = f"{self.address.replace(':', '_')}_profile.json"
        
        profile = {
            'device_info': self.device_info,
            'services': self.services
        }
        
        with open(filename, 'w') as f:
            json.dump(profile, f, indent=2)
        
        print(f"\n[*] Profile saved to {filename}")
        return filename
    
    def analyze_security(self):
        # Quick security analysis of discovered services
        print(f"\n SECURITY ANALYSIS \n")
        
        vulnerabilities = []
        
        for service_uuid, service in self.services.items():
            for char in service['characteristics']:
                
                # Check for unencrypted readable data
                if char['readable'] and char['value']:
                    vulnerabilities.append({
                        'type': 'UNENCRYPTED_READ',
                        'severity': 'MEDIUM',
                        'characteristic': char['uuid'],
                        'description': f"Readable characteristic without apparent encryption"
                    })
                    print(f"\n[!] Unencrypted readable data:")
                    print(f"    Characteristic: {char['uuid']}")
                    print(f"    Value: {char['value']}")
                
                # Check for writable characteristics (injection risk)
                if char['writable']:
                    vulnerabilities.append({
                        'type': 'WRITABLE_CHARACTERISTIC',
                        'severity': 'HIGH',
                        'characteristic': char['uuid'],
                        'description': f"Writable characteristic - command injection possible"
                    })
                    print(f"\n[!] Writable characteristic (injection risk):")
                    print(f"    Characteristic: {char['uuid']}")
                    print(f"    Properties: {char['properties']}")
        
        print(f"\n[*] Found {len(vulnerabilities)} potential vulnerabilities")
        return vulnerabilities


# Example usage
async def enumerate_device(address):
    # Helper function to enumerate a device 
    enumerator = GATTEnumerator(address)
    services = await enumerator.connect_and_enumerate()
    
    if services:
        enumerator.save_profile()
        enumerator.analyze_security()
    
    return enumerator


if __name__ == "__main__":
    import sys    
    target_address = sys.argv[1]
    asyncio.run(enumerate_device(target_address))