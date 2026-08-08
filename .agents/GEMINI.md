# SpyBLE Project Guidelines & BLE Learnings

## 1. BLE Communication Strategy
- **Rapid Shooting Mode (Method 2)**: Initial GATT data acquisition uses rapid connection retries (every 300ms with short timeouts) to handle BLE low-energy sleep cycles.
- **Passive BLE Scanner (Method 3)**: After initial data acquisition, the application transitions to a background `BleakScanner` listening for BLE Advertisements (MiBeacon `0xFE95`, ATC/PVVX `0x181A`, BTHome `0xFCD2`).
- **Single Connection Rule**: BLE peripherals can only connect to one master device at a time. If a mobile phone is connected to the thermometer, the thermometer stops broadcasting BLE advertisements until the phone disconnects.

## 2. Hardware MAC Resolution (Windows Compatibility)
- Windows OS Bluetooth stack assigns Random Advertising Addresses to BLE devices.
- The scanner parses the embedded hardware MAC address from the advertisement payload bytes and resolves `BLEDevice` handles using `_get_ble_device()` to ensure WinRT BLE compatibility.

## 3. Configuration & Persistence
- Application settings and last readings are persisted in `spyBLE.settings` in JSON format.

## 4. Flet UI Design Rules
- Page vertical scrolling uses `page.scroll = ft.ScrollMode.AUTO`.
- Do NOT use `expand=True` on `Container` or `Column` elements inside scrollable views, to prevent Flet gray box layout collapse.
- In `ListView` control loops, use explicit closure helper functions (e.g. `make_assign_click(mac, sensor_type)`) for `on_click` handlers to prevent Python late-binding scoping errors.
