# BLE MITM Security Research Tool
Python-based BLE MITM security research tool for academic purposes
- **Authors:** Boldizsar Keszthelyi, Gergo Balaton
- **Course:** Lab on Offensive Security (2IC80) 2025-2026 Q2
- **Assignment:** Offensive Security - BLE MiTM Analysis on a device using "Just Works" pairing

## Overview
Python tool for analyzing BLE security, specifically testing "Just Works" pairing vulnerabilities on a specific fitness tracker - the OAT1040.

## Current Status 

- [x] Basic device scanning
- [x] GATT service enumeration 
- [x] Persistent connection and monitoring 
- [x] MITM proxy
- [x] Packet modification

## Usage Guide

### 1. Scanning (Windows & Linux)
Discover nearby BLE devices to find your target's MAC address.

```bash
> python scanner.py
```

*Output: Saves discovered devices to `scan_results.json`.*

### 2. Service Enumeration (Windows & Linux)
Once you have the target MAC address (e.g., \`78:02:B7:2B:40:C9\`), generate a device profile.

```bash
> python GATT_enum.py <TARGET_MAC_ADDRESS>
```

*Output: Generates a profile file like \`78_02_B7_2B_40_C9_profile.json\`.*

### 3. Relay / Inspection Client (Windows & Linux)
Connect to the device to monitor notifications and manually send commands.

```bash
> python relay_client.py <TARGET_MAC_ADDRESS>
```

### 4. MITM Attack (Linux Only)
This script acts as the Man-in-the-Middle. It advertises as the target device to the victim (e.g., phone) while simultaneously connecting to the real target device.

#### Stop default bluetoothd if it interferes (optional/depends on setup)
```bash
> sudo systemctl stop bluetooth
```

#### Run the MITM proxy
```bash
> sudo -E python fake_oat1040_bluez.py --adapter hci0 --target <TARGET_MAC_ADDRESS> --debug
```

## Hardware 

- Target: OAT1040 Activity Tracker

## Testing environment: 
- OS: Ubuntu 24.04.3 LTS
- Python: 3.13.2
- BLE libraries: bleak 2.1.1, dbus-fast 3.1.2, dbus-next 0.2.3, BlueZ 5.72
- Bluetooth adapter: Intel(R) Wireless Bluetooth(R), hama Bluetooth v4.0 00053313

- ## Installation

```bash
> pip install dbus-next bleak asyncio
> sudo apt install bluez bluetooth
> sudo apt install python3
