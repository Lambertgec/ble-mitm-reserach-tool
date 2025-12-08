# BLE MITM Security Research Tool
Python-based BLE MITM security research tool for academic purposes
**Authors:** Boldizsar Keszthelyi, Gergo Balaton
**Course:** Lab on Offensive Security (2IC80) 2025-2026 Q2
**Assignment:** Offensive Security - BLE MiTM Analysis on a device using "Just Works" pairing

## Overview
Python tool for analyzing BLE security, specifically testing "Just Works" pairing vulnerabilities on a specific fitness tracker - the OAT1040.

## Current Status 

- [x] Basic device scanning - Boldizsar (Lambertgec) 
- [x] GATT service enumeration - Boldizsar (Lambertgec)
- [x] Persistent connection and monitoring Gergo (Gergo Balaton)
- [ ] MITM proxy
- [ ] Packet modification
- [ ] Security analysis module

## Hardware 

- Target: OAT1040 Activity Tracker

## Testing environment: 
- OS: Windows 11 10.0.26100
- Python: 3.13.2
- BLE library: bleak 2.0.0
- Bluetooth adapter: Intel(R) Wireless Bluetooth(R)

- ## Installation

```bash
pip install bleak asyncio```
