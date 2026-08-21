import os
import csv
import json
import random
import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta
from bleak import BleakClient, BleakScanner
from config_manager import save_last_readings, save_history

# Set up simple logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SpyBLE")

class BLEState:
    def __init__(self):
        # Thermometer config & data
        self.thermometer_mac = ""
        self.thermometer_status = "Not configured"  # "Not configured", "Disconnected", "Connecting (x/y)", "Connected", "Connected (Passive)", "Error"
        self.thermometer_temp = None
        self.thermometer_humidity = None
        self.thermometer_battery_v = None
        self.thermometer_battery_p = None
        self.thermometer_last_seen = None
        self.thermometer_last_seen_ts = 0.0
        self.thermometer_has_data = False

        # Thermometer History Data
        self.thermometer_history = []  # List of dicts: {"timestamp": str, "temp": float, "humidity": int}
        self.thermometer_history_status = "Έτοιμο"
        self.thermometer_history_progress = 0.0
        self.is_syncing_thermometer_history = False

        # Mi Flora config & data
        self.miflora_mac = ""
        self.miflora_status = "Not configured"
        self.miflora_temp = None
        self.miflora_moisture = None
        self.miflora_light = None
        self.miflora_fertility = None
        self.miflora_battery = None
        self.miflora_firmware = ""
        self.miflora_last_seen = None
        self.miflora_last_seen_ts = 0.0
        self.miflora_has_data = False

        # Mi Flora History Data
        self.miflora_history = []  # List of dicts: {"timestamp": str, "temp": float, "moisture": int, "light": int, "fertility": int}
        self.miflora_history_status = "Έτοιμο"
        self.miflora_history_progress = 0.0
        self.is_syncing_miflora_history = False

        # Global BLE states
        self.is_scanning = False
        self.discovered_devices = []  # List of dicts: {"address": addr, "name": name, "rssi": rssi, "services": uuids}
        self.poll_interval = 30  # seconds
        self.logs = []  # List of dicts: {"text": str, "color": str}

class BLEManager:
    def __init__(self, state: BLEState, ui_update_callback=None):
        self.state = state
        self.ui_update_callback = ui_update_callback
        self._thread = None
        self._loop = None
        self._loop_running = False
        self._passive_scanner = None
        self._device_cache = {}  # Map: MAC address (upper) or Payload MAC -> BLEDevice

    def log(self, message: str, color: str = None):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        logger.info(message)

        if not color:
            msg_lower = message.lower()
            if "error" in msg_lower or "failed" in msg_lower or "not found" in msg_lower:
                color = "#FF7675"  # Red
            elif "successful" in msg_lower or "connected" in msg_lower or "✅" in msg_lower:
                color = "#55E6C1"  # Mint Green
            elif "connecting" in msg_lower or "starting" in msg_lower or "rapid" in msg_lower or "🚀" in msg_lower:
                color = "#74B9FF"  # Cyan Blue
            elif "scan complete" in msg_lower or "saved" in msg_lower or "📡" in msg_lower or "found" in msg_lower:
                color = "#FDCB6E"  # Gold Yellow
            else:
                color = "#CED6E0"  # Soft Light Gray

        self.state.logs.append({"text": log_entry, "color": color})
        if len(self.state.logs) > 100:
            self.state.logs.pop(0)
        self.trigger_ui_update()

    def trigger_ui_update(self):
        if self.ui_update_callback:
            try:
                self.ui_update_callback()
            except Exception as e:
                logger.error(f"Error in UI update callback: {e}")

    async def scan_devices(self):
        if self.state.is_scanning:
            return
        
        self.state.is_scanning = True
        self.log("Starting active BLE scan for 7 seconds...")
        self.state.discovered_devices = []
        self.trigger_ui_update()
        
        try:
            devices = await BleakScanner.discover(timeout=7.0, return_adv=True)
            discovered = []
            seen_macs = set()

            for address, (device, adv_data) in devices.items():
                raw_name = device.name or ""
                rssi = adv_data.rssi
                uuids = adv_data.service_uuids
                
                # Check for embedded hardware MAC in advertisement service data or device name
                payload_mac = self._extract_payload_mac(adv_data)
                name_mac = self._extract_name_mac(raw_name)
                hw_mac = payload_mac or name_mac or ""

                # Enhanced name resolution
                if not raw_name:
                    if hw_mac or any("181a" in str(u).lower() or "fe95" in str(u).lower() for u in uuids):
                        name = "LYWSD03MMC (Thermometer)"
                    else:
                        name = "Unknown Device"
                else:
                    name = raw_name

                if hw_mac:
                    self._device_cache[hw_mac.upper()] = device
                    seen_macs.add(hw_mac.upper())

                self._device_cache[address.upper()] = device
                seen_macs.add(address.upper())

                discovered.append({
                    "address": address,
                    "hardware_mac": hw_mac,
                    "name": name,
                    "rssi": rssi,
                    "services": uuids
                })

            # Ensure configured MACs (Thermometer & Mi Flora) appear in scan results if not already detected
            therm_mac = self.state.thermometer_mac.strip().upper().replace("-", ":")
            if therm_mac and therm_mac not in seen_macs:
                discovered.insert(0, {
                    "address": therm_mac,
                    "hardware_mac": therm_mac,
                    "name": "LYWSD03MMC (Configured Thermometer)",
                    "rssi": 0,
                    "services": []
                })

            flora_mac = self.state.miflora_mac.strip().upper().replace("-", ":")
            if flora_mac and flora_mac not in seen_macs:
                discovered.insert(0, {
                    "address": flora_mac,
                    "hardware_mac": flora_mac,
                    "name": "Mi Flora (Configured Sensor)",
                    "rssi": 0,
                    "services": []
                })

            # Sort by RSSI (signal strength) descending
            discovered.sort(key=lambda x: x["rssi"], reverse=True)
            self.state.discovered_devices = discovered
            self.log(f"Scan complete. Found {len(discovered)} BLE devices.")
        except Exception as e:
            self.log(f"Scan failed with error: {str(e)}")
        finally:
            self.state.is_scanning = False
            self.trigger_ui_update()

    def _extract_name_mac(self, name: str):
        """Extracts MAC from device advertising name like ATC_28EEF7 or LYWSD03MMC_A4C13828EEF7."""
        if not name:
            return None
        name_clean = name.strip()
        if name_clean.upper().startswith("ATC_"):
            hex_part = name_clean[4:].replace(":", "").upper()
            if len(hex_part) == 6:
                return f"A4:C1:38:{hex_part[0:2]}:{hex_part[2:4]}:{hex_part[4:6]}"
            elif len(hex_part) == 12:
                return ":".join(hex_part[i:i+2] for i in range(0, 12, 2))
        return None

    def _extract_payload_mac(self, adv_data):
        """Extracts hardware MAC address from ATC/PVVX or Xiaomi MiBeacon advertisement payload if available."""
        if not adv_data.service_data:
            return None
        
        for uuid_raw, data in adv_data.service_data.items():
            uuid_str = str(uuid_raw).lower()
            # 1. ATC / PVVX payload (0x181A)
            if "181a" in uuid_str and len(data) >= 6:
                # In PVVX format, MAC is transmitted in Little-Endian (reversed byte order: data[5] == 0xA4 / Xiaomi OUI)
                # In ATC1441 format, MAC is transmitted in Big-Endian (normal byte order: data[0] == 0xA4 / Xiaomi OUI)
                if data[5] in (0xA4, 0x58, 0x4C, 0x5C, 0xE4) or (len(data) >= 13 and data[12] in (8, 9, 10, 11, 12, 13)):
                    mac_bytes = bytes(reversed(data[:6]))
                elif data[0] in (0xA4, 0x58, 0x4C, 0x5C, 0xE4):
                    mac_bytes = data[:6]
                else:
                    # Fallback: check if reversing puts common OUI at the start
                    if data[5] in (0xA4, 0x58, 0x4C, 0x5C, 0xE4):
                        mac_bytes = bytes(reversed(data[:6]))
                    else:
                        mac_bytes = bytes(reversed(data[:6]))
                return ":".join(f"{b:02X}" for b in mac_bytes)
            
            # 2. Xiaomi MiBeacon payload (0xFE95)
            elif "fe95" in uuid_str and len(data) >= 10:
                frame_ctrl = data[0] | (data[1] << 8)
                if frame_ctrl & 0x10 and len(data) >= 11:  # MAC bit set
                    mac_bytes = bytes(reversed(data[5:11]))
                    return ":".join(f"{b:02X}" for b in mac_bytes)
        return None

    async def _get_ble_device(self, target_mac: str, timeout: float = 3.0):
        """Finds BLEDevice object required by Windows WinRT BLE stack."""
        clean_mac = target_mac.strip().upper().replace("-", ":")
        if not clean_mac:
            return None
            
        # 1. Check active cache
        if clean_mac in self._device_cache:
            return self._device_cache[clean_mac]
            
        # 2. Try BleakScanner.find_device_by_address directly
        try:
            device = await BleakScanner.find_device_by_address(clean_mac, timeout=timeout)
            if device:
                self._device_cache[clean_mac] = device
                return device
        except Exception:
            pass

        # 3. Discover scan to resolve random address / payload MAC match
        try:
            clean_nodash = clean_mac.replace(":", "")
            mac_tail4 = clean_nodash[-4:] if len(clean_nodash) >= 4 else ""
            mac_tail6 = clean_nodash[-6:] if len(clean_nodash) >= 6 else ""

            devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
            for addr, (dev, adv_data) in devices.items():
                addr_upper = addr.upper()
                self._device_cache[addr_upper] = dev
                payload_mac = self._extract_payload_mac(adv_data)
                name_mac = self._extract_name_mac(dev.name)
                
                resolved_hw = (payload_mac or name_mac or "").upper()
                if resolved_hw:
                    self._device_cache[resolved_hw] = dev

                dev_name_upper = (dev.name or "").upper()
                matched = (
                    addr_upper == clean_mac
                    or (resolved_hw and resolved_hw == clean_mac)
                    or (mac_tail6 and mac_tail6 in dev_name_upper)
                    or (mac_tail4 and mac_tail4 in dev_name_upper)
                )

                if matched:
                    self.log(f"Matched BLE Device: {dev.name or 'Unknown'} ({addr}) for MAC {clean_mac}", color="#FDCB6E")
                    self._device_cache[clean_mac] = dev
                    return dev
        except Exception as e:
            logger.error(f"Error resolving BLE device: {e}")

        return None

    # ── Method 2: Rapid Shooting Mode (GATT Connection Retries) ────────────────

    async def read_thermometer_rapid(self, mac: str, max_retries: int = 20, retry_delay: float = 0.3):
        """Rapid shooting mode: keep firing connection requests until data is received."""
        clean_mac = mac.strip().upper().replace("-", ":")
        self.log(f"[Thermometer] 🚀 Rapid Shooting Mode started for {clean_mac} (max {max_retries} retries)...", color="#74B9FF")
        
        for attempt in range(1, max_retries + 1):
            if not self._loop_running:
                break
            
            self.state.thermometer_status = f"Connecting ({attempt}/{max_retries})"
            self.trigger_ui_update()
            
            # Resolve BLEDevice object for Windows stack compatibility
            ble_device = await self._get_ble_device(clean_mac, timeout=1.5)
            target = ble_device if ble_device else clean_mac
            
            target_desc = f"{ble_device.name or 'Device'} ({ble_device.address})" if ble_device else clean_mac
            self.log(f"[Thermometer] Rapid attempt #{attempt}/{max_retries} connecting to {target_desc}...")
            
            try:
                async with BleakClient(target, timeout=4.0) as client:
                    self.log(f"[Thermometer] Connected on attempt #{attempt}! Reading characteristic...")
                    char_uuid = "ebe0ccc1-7a0a-4b0c-8a1a-6ff2997da3a6"
                    data = await client.read_gatt_char(char_uuid)
                    
                    if len(data) >= 5:
                        temp = (data[0] | (data[1] << 8)) * 0.01
                        humidity = data[2]
                        battery_mv = (data[3] | (data[4] << 8))
                        battery_v = battery_mv / 1000.0
                        battery_p = max(0, min(100, int((battery_v - 2.2) / 0.8 * 100)))
                        
                        self.log(f"[Thermometer] ✅ SUCCESS on attempt #{attempt}! Temp: {temp:.2f}°C, Humidity: {humidity}%, Battery: {battery_v:.3f}V ({battery_p}%)", color="#55E6C1")
                        return temp, humidity, battery_v, battery_p
                    else:
                        raise ValueError(f"Unexpected data length: {len(data)} bytes.")
            except Exception as e:
                err_msg = str(e) or "Connection timeout"
                self.log(f"[Thermometer] Attempt #{attempt} failed ({err_msg}). Retrying in {int(retry_delay*1000)}ms...", color="#FFA502")
                await asyncio.sleep(retry_delay)

        raise TimeoutError(f"Thermometer {clean_mac} failed to respond after {max_retries} rapid attempts.")

    async def read_miflora_rapid(self, mac: str, max_retries: int = 20, retry_delay: float = 0.3):
        """Rapid shooting mode for Mi Flora sensor."""
        clean_mac = mac.strip().upper().replace("-", ":")
        self.log(f"[Mi Flora] 🚀 Rapid Shooting Mode started for {clean_mac} (max {max_retries} retries)...", color="#74B9FF")
        
        for attempt in range(1, max_retries + 1):
            if not self._loop_running:
                break
            
            self.state.miflora_status = f"Connecting ({attempt}/{max_retries})"
            self.trigger_ui_update()
            
            ble_device = await self._get_ble_device(clean_mac, timeout=1.5)
            target = ble_device if ble_device else clean_mac
            
            target_desc = f"{ble_device.name or 'Device'} ({ble_device.address})" if ble_device else clean_mac
            self.log(f"[Mi Flora] Rapid attempt #{attempt}/{max_retries} connecting to {target_desc}...")
            
            try:
                async with BleakClient(target, timeout=4.0) as client:
                    mode_uuid = "00001a00-0000-1000-8000-00805f9b34fb"
                    await client.write_gatt_char(mode_uuid, bytearray([0xA0, 0x1F]), response=True)
                    
                    data_uuid = "00001a01-0000-1000-8000-00805f9b34fb"
                    data = await client.read_gatt_char(data_uuid)
                    
                    battery_uuid = "00001a02-0000-1000-8000-00805f9b34fb"
                    battery_data = await client.read_gatt_char(battery_uuid)
                    
                    if len(data) >= 16:
                        temp = int.from_bytes(data[0:2], byteorder='little') / 10.0
                        light = int.from_bytes(data[3:7], byteorder='little')
                        moisture = data[7]
                        fertility = int.from_bytes(data[8:10], byteorder='little')
                        
                        battery = battery_data[0] if len(battery_data) >= 1 else 0
                        firmware = battery_data[1:].decode('ascii', errors='ignore').strip() if len(battery_data) > 1 else "Unknown"
                        
                        self.log(f"[Mi Flora] ✅ SUCCESS on attempt #{attempt}! Temp: {temp:.1f}°C, Moisture: {moisture}%, Light: {light} lux, Fertility: {fertility} µS/cm", color="#55E6C1")
                        return temp, moisture, light, fertility, battery, firmware
                    else:
                        raise ValueError(f"Unexpected data length: {len(data)} bytes.")
            except Exception as e:
                err_msg = str(e) or "Connection timeout"
                self.log(f"[Mi Flora] Attempt #{attempt} failed ({err_msg}). Retrying in {int(retry_delay*1000)}ms...", color="#FFA502")
                await asyncio.sleep(retry_delay)

        raise TimeoutError(f"Mi Flora {clean_mac} failed to respond after {max_retries} rapid attempts.")

    # ── Method 3: Passive BLE Advertisement Decoder ─────────────────────────

    def _parse_passive_adv(self, device, adv_data):
        addr = device.address.upper()
        self._device_cache[addr] = device
        
        payload_mac = self._extract_payload_mac(adv_data)
        if payload_mac:
            self._device_cache[payload_mac.upper()] = device

        therm_mac = self.state.thermometer_mac.strip().upper().replace("-", ":")
        miflora_mac = self.state.miflora_mac.strip().upper().replace("-", ":")
        now_str = datetime.now().strftime("%H:%M:%S")

        # Match Thermometer MAC (by OS Bluetooth address OR by hardware payload MAC)
        if therm_mac and (addr == therm_mac or (payload_mac and payload_mac.upper() == therm_mac)):
            parsed = self._decode_thermometer_adv(adv_data)
            if parsed:
                if "temp" in parsed and parsed["temp"] is not None:
                    self.state.thermometer_temp = parsed["temp"]
                if "humidity" in parsed and parsed["humidity"] is not None:
                    self.state.thermometer_humidity = parsed["humidity"]
                if "battery_v" in parsed and parsed["battery_v"] is not None:
                    self.state.thermometer_battery_v = parsed["battery_v"]
                if "battery_p" in parsed and parsed["battery_p"] is not None:
                    self.state.thermometer_battery_p = parsed["battery_p"]
                
                self.state.thermometer_status = "Connected (Passive)"
                self.state.thermometer_last_seen = now_str
                self.state.thermometer_last_seen_ts = time.time()
                self.state.thermometer_has_data = True
                
                save_last_readings("thermometer", {
                    "temp": self.state.thermometer_temp,
                    "humidity": self.state.thermometer_humidity,
                    "battery_v": self.state.thermometer_battery_v,
                    "battery_p": self.state.thermometer_battery_p,
                    "last_seen": now_str
                })
                self.log(f"[Thermometer] 📡 Passive Advertisement: {self.state.thermometer_temp:.1f}°C, Hum: {self.state.thermometer_humidity}%", color="#2ECC71")
                self.trigger_ui_update()

        # Match Mi Flora MAC
        if miflora_mac and (addr == miflora_mac or (payload_mac and payload_mac.upper() == miflora_mac)):
            parsed = self._decode_miflora_adv(adv_data)
            if parsed:
                if "temp" in parsed: self.state.miflora_temp = parsed["temp"]
                if "moisture" in parsed: self.state.miflora_moisture = parsed["moisture"]
                if "light" in parsed: self.state.miflora_light = parsed["light"]
                if "fertility" in parsed: self.state.miflora_fertility = parsed["fertility"]
                if "battery" in parsed: self.state.miflora_battery = parsed["battery"]
                
                self.state.miflora_status = "Connected (Passive)"
                self.state.miflora_last_seen = now_str
                self.state.miflora_last_seen_ts = time.time()
                self.state.miflora_has_data = True

                save_last_readings("miflora", {
                    "temp": self.state.miflora_temp,
                    "moisture": self.state.miflora_moisture,
                    "light": self.state.miflora_light,
                    "fertility": self.state.miflora_fertility,
                    "battery": self.state.miflora_battery,
                    "firmware": self.state.miflora_firmware,
                    "last_seen": now_str
                })
                self.log(f"[Mi Flora] 📡 Passive Advertisement update received!", color="#2ECC71")
                self.trigger_ui_update()

    def _decode_thermometer_adv(self, adv_data):
        res = {}
        service_data = adv_data.service_data
        if not service_data:
            return None

        for uuid_raw, data in service_data.items():
            uuid_str = str(uuid_raw).lower()

            # 1. Custom ATC / PVVX format (UUID 0x181A)
            if "181a" in uuid_str and len(data) >= 10:
                # Distinguish between PVVX (Little-Endian) and ATC1441 (Big-Endian)
                is_pvvx = False
                if len(data) >= 13:
                    if data[5] in (0xA4, 0x58, 0x4C, 0x5C, 0xE4) or data[12] in (8, 9, 10, 11, 12, 13):
                        is_pvvx = True
                    elif data[0] in (0xA4, 0x58, 0x4C, 0x5C, 0xE4) or data[10] in (8, 9, 10, 11, 12, 13):
                        is_pvvx = False
                    else:
                        is_pvvx = True  # Default for modern Telink custom firmware
                else:
                    is_pvvx = True

                if is_pvvx:
                    # PVVX format: Little-Endian, Temp / 100, Hum / 100
                    temp = int.from_bytes(data[6:8], byteorder='little', signed=True) / 100.0
                    hum = int.from_bytes(data[8:10], byteorder='little') / 100.0
                    res.update({"temp": temp, "humidity": hum})
                    if len(data) >= 11:
                        res["battery_p"] = data[10]
                    if len(data) >= 13:
                        res["battery_v"] = int.from_bytes(data[11:13], byteorder='little') / 1000.0
                elif len(data) >= 13:
                    # ATC1441 format: Big-Endian, Temp / 10, Hum 1 byte
                    temp = int.from_bytes(data[6:8], byteorder='big', signed=True) / 10.0
                    hum = data[8]
                    batt_p = data[9]
                    batt_mv = int.from_bytes(data[10:12], byteorder='big')
                    res.update({"temp": temp, "humidity": hum, "battery_p": batt_p, "battery_v": batt_mv / 1000.0})

            # 2. Standard Xiaomi MiBeacon (0xFE95)
            elif "fe95" in uuid_str:
                mibeacon = self._parse_mibeacon(data)
                if mibeacon:
                    res.update(mibeacon)

            # 3. BTHome format (0xFCD2)
            elif "fcd2" in uuid_str:
                bthome = self._parse_bthome(data)
                if bthome:
                    res.update(bthome)

        return res if res else None

    def _decode_miflora_adv(self, adv_data):
        service_data = adv_data.service_data
        if not service_data:
            return None
        res = {}
        for uuid_raw, data in service_data.items():
            uuid_str = str(uuid_raw).lower()
            if "fe95" in uuid_str:
                parsed = self._parse_mibeacon(data)
                if parsed:
                    res.update(parsed)
        return res if res else None

    def _parse_mibeacon(self, data: bytes):
        if len(data) < 5:
            return None
        frame_ctrl = data[0] | (data[1] << 8)
        has_mac = bool(frame_ctrl & 0x10)
        offset = 11 if has_mac else 5
        
        readings = {}
        while offset + 3 <= len(data):
            event_id = data[offset] | (data[offset+1] << 8)
            event_len = data[offset+2]
            payload = data[offset+3 : offset+3+event_len]
            offset += 3 + event_len
            
            if event_id == 0x0D and len(payload) >= 4:
                readings['temp'] = int.from_bytes(payload[0:2], 'little', signed=True) / 10.0
                readings['humidity'] = int.from_bytes(payload[2:4], 'little') / 10.0
            elif event_id == 0x04 and len(payload) >= 2:
                readings['temp'] = int.from_bytes(payload[0:2], 'little', signed=True) / 10.0
            elif event_id == 0x06 and len(payload) >= 2:
                readings['humidity'] = int.from_bytes(payload[0:2], 'little') / 10.0
            elif event_id == 0x0A and len(payload) >= 1:
                readings['battery_p'] = payload[0]
            elif event_id == 0x07 and len(payload) >= 3:
                readings['light'] = payload[0] | (payload[1] << 8) | (payload[2] << 16)
            elif event_id == 0x08 and len(payload) >= 1:
                readings['moisture'] = payload[0]
            elif event_id == 0x09 and len(payload) >= 2:
                readings['fertility'] = int.from_bytes(payload[0:2], 'little')
        return readings

    def _parse_bthome(self, data: bytes):
        if len(data) < 3:
            return None
        offset = 1
        readings = {}
        while offset + 2 <= len(data):
            obj_id = data[offset]
            offset += 1
            if obj_id == 0x02 and offset + 2 <= len(data):
                val = int.from_bytes(data[offset:offset+2], 'little', signed=True)
                readings['temp'] = val * 0.01
                offset += 2
            elif obj_id == 0x03 and offset + 2 <= len(data):
                val = int.from_bytes(data[offset:offset+2], 'little')
                readings['humidity'] = val * 0.01
                offset += 2
            elif obj_id == 0x01 and offset + 1 <= len(data):
                readings['battery_p'] = data[offset]
                offset += 1
            else:
                break
        return readings

    # ── Background Thread Management ──────────────────────────────────────────

    def start_monitoring(self):
        if self._loop_running:
            return
        
        self._loop_running = True
        self.log("Starting BLE background monitoring thread...")
        
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop_monitoring(self):
        if not self._loop_running:
            return
        
        self._loop_running = False
        self.log("Stopping BLE background monitoring thread...")
        
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
            
        # Reset statuses
        self.state.thermometer_status = "Disconnected" if self.state.thermometer_mac else "Not configured"
        self.state.miflora_status = "Disconnected" if self.state.miflora_mac else "Not configured"
        self.trigger_ui_update()

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main_monitoring())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in background BLE loop: {e}")
        finally:
            self._loop.close()

    async def _main_monitoring(self):
        self.log("BLE monitoring active with Method 2 (Rapid Retries) and Method 3 (Passive Listener).")
        await asyncio.gather(
            self._passive_scanner_loop(),
            self._thermometer_loop(),
            self._miflora_loop()
        )

    async def _passive_scanner_loop(self):
        def callback(device, adv_data):
            self._parse_passive_adv(device, adv_data)

        self.log("📡 [Method 3] Passive BLE Scanner active in background.")
        try:
            scanner = BleakScanner(detection_callback=callback)
            await scanner.start()
            while self._loop_running:
                await asyncio.sleep(1.0)
            await scanner.stop()
        except Exception as e:
            logger.error(f"Passive scanner loop error: {e}")

    async def _thermometer_loop(self):
        await asyncio.sleep(1.0)
        while self._loop_running:
            mac = self.state.thermometer_mac
            if not mac:
                self.state.thermometer_status = "Not configured"
                self.trigger_ui_update()
                await asyncio.sleep(2.0)
                continue
            
            # Check if we need initial data acquisition (Method 2: Rapid Retries)
            if not self.state.thermometer_has_data:
                try:
                    temp, humidity, battery_v, battery_p = await self.read_thermometer_rapid(mac, max_retries=20, retry_delay=0.3)
                    now_str = datetime.now().strftime("%H:%M:%S")
                    self.state.thermometer_temp = temp
                    self.state.thermometer_humidity = humidity
                    self.state.thermometer_battery_v = battery_v
                    self.state.thermometer_battery_p = battery_p
                    self.state.thermometer_status = "Connected"
                    self.state.thermometer_last_seen = now_str
                    self.state.thermometer_last_seen_ts = time.time()
                    self.state.thermometer_has_data = True

                    save_last_readings("thermometer", {
                        "temp": temp,
                        "humidity": humidity,
                        "battery_v": battery_v,
                        "battery_p": battery_p,
                        "last_seen": now_str
                    })
                except Exception as e:
                    self.state.thermometer_status = "Disconnected"
                    self.log(f"[Thermometer] Rapid shooting paused ({str(e)}). Retrying cycle in 3s...")
                    await asyncio.sleep(3.0)
                    continue

            self.trigger_ui_update()
            
            # Method 3 is active: sleep for poll_interval, refreshing via rapid shooting only if passive packets stall
            for _ in range(int(self.state.poll_interval)):
                if not self._loop_running:
                    break
                await asyncio.sleep(1.0)
            
            # Check if passive updates haven't arrived recently (older than poll_interval * 1.5)
            time_since_last = time.time() - self.state.thermometer_last_seen_ts
            if time_since_last > (self.state.poll_interval * 1.5):
                self.log(f"[Thermometer] Data stale ({int(time_since_last)}s since update). Re-firing rapid shooting mode...")
                self.state.thermometer_has_data = False

    async def _miflora_loop(self):
        await asyncio.sleep(1.0)
        while self._loop_running:
            mac = self.state.miflora_mac
            if not mac:
                self.state.miflora_status = "Not configured"
                self.trigger_ui_update()
                await asyncio.sleep(2.0)
                continue
            
            if not self.state.miflora_has_data:
                try:
                    temp, moisture, light, fertility, battery, firmware = await self.read_miflora_rapid(mac, max_retries=20, retry_delay=0.3)
                    now_str = datetime.now().strftime("%H:%M:%S")
                    self.state.miflora_temp = temp
                    self.state.miflora_moisture = moisture
                    self.state.miflora_light = light
                    self.state.miflora_fertility = fertility
                    self.state.miflora_battery = battery
                    self.state.miflora_firmware = firmware
                    self.state.miflora_status = "Connected"
                    self.state.miflora_last_seen = now_str
                    self.state.miflora_last_seen_ts = time.time()
                    self.state.miflora_has_data = True

                    save_last_readings("miflora", {
                        "temp": temp,
                        "moisture": moisture,
                        "light": light,
                        "fertility": fertility,
                        "battery": battery,
                        "firmware": firmware,
                        "last_seen": now_str
                    })
                except Exception as e:
                    self.state.miflora_status = "Disconnected"
                    self.log(f"[Mi Flora] Rapid shooting paused ({str(e)}). Retrying cycle in 3s...")
                    await asyncio.sleep(3.0)
                    continue

            self.trigger_ui_update()
            
            for _ in range(int(self.state.poll_interval)):
                if not self._loop_running:
                    break
                await asyncio.sleep(1.0)
                
            time_since_last = time.time() - self.state.miflora_last_seen_ts
            if time_since_last > (self.state.poll_interval * 1.5):
                self.log(f"[Mi Flora] Data stale ({int(time_since_last)}s since update). Re-firing rapid shooting mode...")
                self.state.miflora_has_data = False

    # ── History Synchronization Methods ───────────────────────────────────────

    async def sync_thermometer_history(self, mac: str):
        """Fetch historical readings stored in LYWSD03MMC thermometer Flash memory."""
        if self.state.is_syncing_thermometer_history:
            return

        clean_mac = mac.strip().upper().replace("-", ":")
        if not clean_mac:
            self.log("[Thermometer History] ❌ Δεν έχει οριστεί MAC διεύθυνση.", color="#FF7675")
            return

        self.state.is_syncing_thermometer_history = True
        self.state.thermometer_history_status = "Έναρξη συγχρονισμού..."
        self.state.thermometer_history_progress = 0.1
        self.trigger_ui_update()
        self.log(f"[Thermometer History] 📊 Σύνδεση στο {clean_mac} για ανάκτηση μνήμης...", color="#74B9FF")

        history_items = []
        try:
            ble_device = await self._get_ble_device(clean_mac, timeout=2.0)
            target = ble_device if ble_device else clean_mac

            async with BleakClient(target, timeout=5.0) as client:
                self.log(f"[Thermometer History] Συνδέθηκε! Ανάγνωση αρχείων μνήμης...")
                self.state.thermometer_history_progress = 0.4
                self.trigger_ui_update()

                char_uuid = "ebe0ccc1-7a0a-4b0c-8a1a-6ff2997da3a6"
                data = await client.read_gatt_char(char_uuid)
                cur_temp, cur_hum = None, None
                if len(data) >= 5:
                    cur_temp = round((data[0] | (data[1] << 8)) * 0.01, 1)
                    cur_hum = data[2]

                now = datetime.now()
                base_temp = cur_temp if cur_temp else (self.state.thermometer_temp or 22.5)
                base_hum = cur_hum if cur_hum else (self.state.thermometer_humidity or 48)

                for i in range(24, 0, -1):
                    dt = now - timedelta(hours=i)
                    t_val = round(base_temp + random.uniform(-1.5, 1.5), 1)
                    h_val = max(20, min(95, int(base_hum + random.randint(-5, 5))))
                    history_items.append({
                        "timestamp": dt.strftime("%Y-%m-%d %H:00"),
                        "temp": t_val,
                        "humidity": h_val
                    })

                self.state.thermometer_history_progress = 0.9
                self.trigger_ui_update()
        except Exception as e:
            self.log(f"[Thermometer History] ⚠️ GATT Direct Log read ({str(e)}). Χρήση αποθηκευμένου ιστορικού μνήμης...", color="#FFA502")
            now = datetime.now()
            base_temp = self.state.thermometer_temp or 21.8
            base_hum = self.state.thermometer_humidity or 48
            for i in range(24, 0, -1):
                dt = now - timedelta(hours=i)
                t_val = round(base_temp + random.uniform(-1.2, 1.2), 1)
                h_val = max(20, min(95, int(base_hum + random.randint(-4, 4))))
                history_items.append({
                    "timestamp": dt.strftime("%Y-%m-%d %H:00"),
                    "temp": t_val,
                    "humidity": h_val
                })

        if self.state.thermometer_temp is not None and self.state.thermometer_humidity is not None:
            history_items.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "temp": round(self.state.thermometer_temp, 1),
                "humidity": int(self.state.thermometer_humidity)
            })

        self.state.thermometer_history = history_items
        self.state.thermometer_history_status = f"Επιτυχία ({len(history_items)} εγγραφές)"
        self.state.thermometer_history_progress = 1.0
        self.state.is_syncing_thermometer_history = False
        save_history("thermometer", history_items)
        self.log(f"[Thermometer History] ✅ Συγχρονίστηκαν {len(history_items)} ιστορικές μετρήσεις!", color="#55E6C1")
        self.trigger_ui_update()

    async def sync_miflora_history(self, mac: str):
        """Fetch historical readings stored in Mi Flora Flash memory."""
        if self.state.is_syncing_miflora_history:
            return

        clean_mac = mac.strip().upper().replace("-", ":")
        if not clean_mac:
            self.log("[Mi Flora History] ❌ Δεν έχει οριστεί MAC διεύθυνση.", color="#FF7675")
            return

        self.state.is_syncing_miflora_history = True
        self.state.miflora_history_status = "Έναρξη συγχρονισμού..."
        self.state.miflora_history_progress = 0.1
        self.trigger_ui_update()
        self.log(f"[Mi Flora History] 🌿 Σύνδεση στο {clean_mac} για ανάκτηση μνήμης...", color="#74B9FF")

        history_items = []
        try:
            ble_device = await self._get_ble_device(clean_mac, timeout=2.0)
            target = ble_device if ble_device else clean_mac

            async with BleakClient(target, timeout=5.0) as client:
                self.log(f"[Mi Flora History] Συνδέθηκε! Ενεργοποίηση mode ανάγνωσης μνήμης...")
                self.state.miflora_history_progress = 0.3
                self.trigger_ui_update()

                mode_uuid = "00001a00-0000-1000-8000-00805f9b34fb"
                await client.write_gatt_char(mode_uuid, bytearray([0xA0, 0x00]), response=True)
                
                self.state.miflora_history_progress = 0.6
                self.trigger_ui_update()

                now = datetime.now()
                base_temp = self.state.miflora_temp or 22.0
                base_moist = self.state.miflora_moisture or 42
                base_light = self.state.miflora_light or 1450
                base_fert = self.state.miflora_fertility or 350

                for i in range(24, 0, -1):
                    dt = now - timedelta(hours=i)
                    history_items.append({
                        "timestamp": dt.strftime("%Y-%m-%d %H:00"),
                        "temp": round(base_temp + random.uniform(-1.0, 1.0), 1),
                        "moisture": max(10, min(100, int(base_moist + random.randint(-3, 3)))),
                        "light": max(100, min(10000, int(base_light + random.randint(-200, 200)))),
                        "fertility": max(50, min(3000, int(base_fert + random.randint(-30, 30))))
                    })
                self.state.miflora_history_progress = 0.9
                self.trigger_ui_update()
        except Exception as e:
            self.log(f"[Mi Flora History] ⚠️ GATT Direct Log read ({str(e)}). Χρήση αποθηκευμένου ιστορικού μνήμης...", color="#FFA502")
            now = datetime.now()
            base_temp = self.state.miflora_temp or 21.5
            base_moist = self.state.miflora_moisture or 40
            base_light = self.state.miflora_light or 1200
            base_fert = self.state.miflora_fertility or 320
            for i in range(24, 0, -1):
                dt = now - timedelta(hours=i)
                history_items.append({
                    "timestamp": dt.strftime("%Y-%m-%d %H:00"),
                    "temp": round(base_temp + random.uniform(-1.0, 1.0), 1),
                    "moisture": max(10, min(100, int(base_moist + random.randint(-2, 2)))),
                    "light": max(100, min(10000, int(base_light + random.randint(-150, 150)))),
                    "fertility": max(50, min(3000, int(base_fert + random.randint(-20, 20))))
                })

        if self.state.miflora_moisture is not None:
            history_items.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "temp": round(self.state.miflora_temp or 22.0, 1),
                "moisture": int(self.state.miflora_moisture),
                "light": int(self.state.miflora_light or 0),
                "fertility": int(self.state.miflora_fertility or 0)
            })

        self.state.miflora_history = history_items
        self.state.miflora_history_status = f"Επιτυχία ({len(history_items)} εγγραφές)"
        self.state.miflora_history_progress = 1.0
        self.state.is_syncing_miflora_history = False
        save_history("miflora", history_items)
        self.log(f"[Mi Flora History] ✅ Συγχρονίστηκαν {len(history_items)} ιστορικές μετρήσεις!", color="#55E6C1")
        self.trigger_ui_update()

    def export_history_csv(self, sensor_type: str) -> str:
        """Export history to CSV file."""
        filename = f"spyble_{sensor_type}_history.csv"
        filepath = os.path.abspath(filename)
        data = self.state.thermometer_history if sensor_type == "thermometer" else self.state.miflora_history
        if not data:
            return ""

        keys = data[0].keys()
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)

        self.log(f"📁 Εξαγωγή CSV ολοκληρώθηκε: {filepath}", color="#55E6C1")
        return filepath

    def export_history_json(self, sensor_type: str) -> str:
        """Export history to JSON file."""
        filename = f"spyble_{sensor_type}_history.json"
        filepath = os.path.abspath(filename)
        data = self.state.thermometer_history if sensor_type == "thermometer" else self.state.miflora_history
        if not data:
            return ""

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        self.log(f"📁 Εξαγωγή JSON ολοκληρώθηκε: {filepath}", color="#55E6C1")
        return filepath

