"""
Long-lived relay client (peripheral side of MITM)
Author: Gergo Balaton
Date: 05/12/2025
-------------------------------------------------
- Connects to the OAT1040, or other peripheral device, by MAC address
- Keeps the connection open
- Subscribes to notifiable characteristics and prints incoming data
- Lets us send writes to writable characteristics using a simple CLI

Usage: python relay_client.py 78:02:B7:2B:40:C9
"""

import asyncio
import json
import sys
from pathlib import Path
from bleak import BleakClient

PROFILE_PATH = "{mac_underscored}_profile.json"

# Load the JSON profile created by GATT_enum.py 
# Returns (profile, notifiable_uuids, writable_uuids).
def load_profile(address: str):

    mac_underscored = address.replace(":","_")
    profile_path = Path(PROFILE_PATH.format(mac_underscored = mac_underscored))

    if not profile_path.exists():
        print(f"[!] Profile file {profile_path} not found, "
              f"will derive notifiable/writable chars from live services.")
        return None, set(), set()
    
    with profile_path.open("r", encoding = "utf-8") as f:
        profile = json.load(f)
    
    notifiable = set()
    writable = set()

    for svc in profile.get("services", {}).values():
        for char in svc.get("characteristics",[]):
            uuid = char["uuid"]
            props = char.get("properties", [])
            if "notify" in props or "indicate" in props:
                notifiable.add(uuid)
            if "writable" in props or "write-without-response" in props:
                writable.add(uuid)

    print(f"[*] Loaded profile from {profile_path}")
    print(f"    Notifiable characteristics: {len(notifiable)}")
    print(f"    Writable characteristics: {len(writable)}")
    return profile, notifiable, writable

# Fallback: find notifiable and writable characteristics from Bleak's live services
def find_from_live(client: BleakClient):

    notifiable = set()
    writable = set()

    for service in client.services:
        for char in service.characteristics:
            props = char.properties
            if "notify" in props or "indicate" in props:
                notifiable.add(str(char.uuid))
            if "write" in props or "write-without-response" in props:
                writable.add(str(char.uuid))

    print(f"[*] Found from live services:")
    print(f"    Notifiable characteristics: {len(notifiable)}")
    print(f"    Writable characteristics: {len(writable)}")
    return notifiable, writable

# Called when a notifiable/indicatable characteristic sends data
def notification_handler(sender: str, data: bytearray):

    hex_val = data.hex()
    ascii_val = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    print(f"\n[NOTIFY] {sender} -> {hex_val} ({ascii_val})")


# Simple CLI loop
# Commands: list - show writable UUIDs
#           write <uuid> <hex bytes> - example: write 0000fea2-0000-1000-8000-00805f9b34fb 01020304
#           quit / exit - disconnect and stop
async def interactive_write_loop(client: BleakClient, writable_uuids: set[str]):
    if not writable_uuids:
        print("[!] No writable characteristics known. "
              "You can keep the connection open to observe notifications.")
    else:
        print("\n[*] Enter commands. Type 'list' to see writable UUIDs, "
              "'quit' to exit \n")
        
    loop = asyncio.get_running_loop()

    while True:
        cmd_line = await loop.run_in_executor(None, lambda: input("relay> ").strip())
        
        if not cmd_line:
            continue

        if cmd_line.lower() in {"quit", "exit"}:
            print("[*] Exiting interactive loop.")
            break

        if cmd_line.lower() in {"list"}:
            print("[*] Writable characteristics:")
            for u in sorted(writable_uuids):
                print(f"    {u}")
            continue

        if cmd_line.lower().startswith("write "):
            parts = cmd_line.split(None, 2)
            if len(parts) != 3:
                print("Usage: write <uuid> <hexbyes>")
                continue

            uuid, hexbytes = parts[1], parts[2].replace(" ","")
            if uuid not in writable_uuids:
                print(f"[!] {uuid} is not in the known writable set.")
            
            try:
                data = bytes.fromhex(hexbytes)
            except ValueError:
                print("[!] Invalid hex string.")
                continue

            try:
                print(f"[*] Writing to {uuid}: {hexbytes}")
                await client.write_gatt_char(uuid, data)
                print("[+] Write OK")
            except Exception as e:
                print(f"[-] Write failed: {e}")
            continue

        print("[!] Unknown command. Use 'list', 'write <uuid> <hexbytes>', 'quit'.")

async def run_relay_client(address: str):
    # Load profile
    profile, notifiable_from_profile, writable_from_profile = load_profile(address)

    client = BleakClient(address, timeout = 20.0)
    await client.connect()
    print(f"[+] Connected: {client.is_connected}, MTU={client.mtu_size}")

    # Wait to fetch services
    services = client.services

    # Get notifiable/writeable sets
    if not notifiable_from_profile and not writable_from_profile:
        notifiable, writable = find_from_live(client)
    else:
        notifiable = notifiable_from_profile
        writable = writable_from_profile

    # Start notifications on all notifiable characteristics
    if notifiable:
        print("[*] Subscribing to notifications/indications:")
        for uuid in notifiable:
            try:
                print(f"    -> {uuid}")
                await client.start_notify(uuid, notification_handler)
            except Exception as e:
                print(f"    [-] Failed to start notify on {uuid}: {e}")
    else:
        print("[!] No notifiable characteristics found.")

    print("\n[*] Relay client is running.")
    print("     - Notifications will be printes as they arrive.")
    print("     - Use the CLI to send writes or type 'quit' to exit. \n")

    try:
        await interactive_write_loop(client, writable)
    finally:
        print("[*] Disconnecting ...")
        await client.disconnect()
        print("[+] Disconnected.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {Path(__file__).name} <BLE_MAC_ADDRESS>")
        sys.exit(1)

    target_mac = sys.argv[1]
    asyncio.run(run_relay_client(target_mac))