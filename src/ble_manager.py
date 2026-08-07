import asyncio
import logging
import threading
from datetime import datetime
from bleak import BleakClient, BleakScanner
from config_manager import save_last_readings

# Set up simple logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SpyBLE")

class BLEState:

    def __init__(self):
        # Thermometer config & data
        self.thermometer_mac = ""
        self.thermometer_status = "Not configured"  # "Not configured", "Disconnected", "Connecting", "Connected", "Error"
        self.thermometer_temp = None
        self.thermometer_humidity = None
        self.thermometer_battery_v = None
        self.thermometer_battery_p = None
        self.thermometer_last_seen = None

        # Mi Flora config & data
        self.miflora_mac = ""
        self.miflora_status = "Not configured"  # "Not configured", "Disconnected", "Connecting", "Connected", "Error"
        self.miflora_temp = None
        self.miflora_moisture = None
        self.miflora_light = None
        self.miflora_fertility = None
        self.miflora_battery = None
        self.miflora_firmware = ""
        self.miflora_last_seen = None

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

    def log(self, message: str, color: str = None):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        logger.info(message)

        if not color:
            msg_lower = message.lower()
            if "error" in msg_lower or "failed" in msg_lower or "not found" in msg_lower:
                color = "#FF7675"  # Red
            elif "successful read" in msg_lower or "connected!" in msg_lower:
                color = "#55E6C1"  # Mint Green
            elif "connecting" in msg_lower or "starting" in msg_lower or "initializing" in msg_lower:
                color = "#74B9FF"  # Cyan Blue
            elif "scan complete" in msg_lower or "saved" in msg_lower:
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
        self.log("Starting BLE scan for 5 seconds...")
        self.state.discovered_devices = []
        self.trigger_ui_update()
        
        try:
            devices = await BleakScanner.discover(timeout=5.0, return_adv=True)
            discovered = []
            for address, (device, adv_data) in devices.items():
                name = device.name or "Unknown Device"
                rssi = adv_data.rssi
                uuids = adv_data.service_uuids
                discovered.append({
                    "address": address,
                    "name": name,
                    "rssi": rssi,
                    "services": uuids
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

    async def read_thermometer(self, mac: str):
        self.log(f"[Thermometer] Connecting to {mac}...")
        async with BleakClient(mac, timeout=8.0) as client:
            self.log(f"[Thermometer] Connected! Reading sensor characteristics...")
            char_uuid = "ebe0ccc1-7a0a-4b0c-8a1a-6ff2997da3a6"
            data = await client.read_gatt_char(char_uuid)
            
            if len(data) >= 5:
                temp = (data[0] | (data[1] << 8)) * 0.01
                humidity = data[2]
                battery_mv = (data[3] | (data[4] << 8))
                battery_v = battery_mv / 1000.0
                battery_p = max(0, min(100, int((battery_v - 2.2) / 0.8 * 100)))
                
                self.log(f"[Thermometer] Successful read. Temp: {temp:.2f}°C, Humidity: {humidity}%, Battery: {battery_v:.3f}V ({battery_p}%)")
                return temp, humidity, battery_v, battery_p
            else:
                raise ValueError(f"Incorrect data format, expected >= 5 bytes, got {len(data)} bytes.")

    async def read_miflora(self, mac: str):
        self.log(f"[Mi Flora] Connecting to {mac}...")
        async with BleakClient(mac, timeout=8.0) as client:
            self.log(f"[Mi Flora] Connected! Initializing sensor read mode...")
            mode_uuid = "00001a00-0000-1000-8000-00805f9b34fb"
            await client.write_gatt_char(mode_uuid, bytearray([0xA0, 0x1F]), response=True)
            
            self.log(f"[Mi Flora] Reading sensor data characteristic...")
            data_uuid = "00001a01-0000-1000-8000-00805f9b34fb"
            data = await client.read_gatt_char(data_uuid)
            
            self.log(f"[Mi Flora] Reading battery & firmware characteristic...")
            battery_uuid = "00001a02-0000-1000-8000-00805f9b34fb"
            battery_data = await client.read_gatt_char(battery_uuid)
            
            if len(data) >= 16:
                temp = int.from_bytes(data[0:2], byteorder='little') / 10.0
                light = int.from_bytes(data[3:7], byteorder='little')
                moisture = data[7]
                fertility = int.from_bytes(data[8:10], byteorder='little')
                
                battery = 0
                firmware = "Unknown"
                if len(battery_data) >= 1:
                    battery = battery_data[0]
                if len(battery_data) > 1:
                    firmware = battery_data[1:].decode('ascii', errors='ignore').strip()
                
                self.log(f"[Mi Flora] Successful read. Temp: {temp:.1f}°C, Moisture: {moisture}%, Light: {light} lux, Fertility: {fertility} uS/cm, Battery: {battery}%")
                return temp, moisture, light, fertility, battery, firmware
            else:
                raise ValueError(f"Incorrect data format, expected >= 16 bytes, got {len(data)} bytes.")

    def start_monitoring(self):
        if self._loop_running:
            return
        
        self._loop_running = True
        self.log("Starting BLE background monitoring thread...")
        
        # Start a dedicated background thread for BLE polling
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
        if self.state.thermometer_mac:
            self.state.thermometer_status = "Disconnected"
        else:
            self.state.thermometer_status = "Not configured"
            
        if self.state.miflora_mac:
            self.state.miflora_status = "Disconnected"
        else:
            self.state.miflora_status = "Not configured"
            
        self.trigger_ui_update()

    def _run_loop(self):
        # Create a private event loop for the background thread
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
        self.log("BLE monitoring thread loops initialized.")
        # Gather loops concurrently on the background thread loop
        await asyncio.gather(
            self._thermometer_loop(),
            self._miflora_loop()
        )

    async def _thermometer_loop(self):
        # Give Flet UI plenty of time to render before starting BLE connections
        await asyncio.sleep(1.0)
        while self._loop_running:
            mac = self.state.thermometer_mac
            if not mac:
                self.state.thermometer_status = "Not configured"
                self.trigger_ui_update()
                await asyncio.sleep(2.0)
                continue
            
            self.state.thermometer_status = "Connecting"
            self.trigger_ui_update()
            
            try:
                temp, humidity, battery_v, battery_p = await self.read_thermometer(mac)
                now_str = datetime.now().strftime("%H:%M:%S")
                self.state.thermometer_temp = temp
                self.state.thermometer_humidity = humidity
                self.state.thermometer_battery_v = battery_v
                self.state.thermometer_battery_p = battery_p
                self.state.thermometer_status = "Connected"
                self.state.thermometer_last_seen = now_str

                # Save reading for persistence across restarts
                save_last_readings("thermometer", {
                    "temp": temp,
                    "humidity": humidity,
                    "battery_v": battery_v,
                    "battery_p": battery_p,
                    "last_seen": now_str
                })
            except Exception as e:
                self.state.thermometer_status = "Disconnected"
                self.log(f"[Thermometer] Error: {str(e)}")
            
            self.trigger_ui_update()
            
            # Poll interval sleep
            for _ in range(int(self.state.poll_interval)):
                if not self._loop_running:
                    break
                await asyncio.sleep(1.0)

    async def _miflora_loop(self):
        await asyncio.sleep(1.0)
        while self._loop_running:
            mac = self.state.miflora_mac
            if not mac:
                self.state.miflora_status = "Not configured"
                self.trigger_ui_update()
                await asyncio.sleep(2.0)
                continue
            
            self.state.miflora_status = "Connecting"
            self.trigger_ui_update()
            
            try:
                temp, moisture, light, fertility, battery, firmware = await self.read_miflora(mac)
                now_str = datetime.now().strftime("%H:%M:%S")
                self.state.miflora_temp = temp
                self.state.miflora_moisture = moisture
                self.state.miflora_light = light
                self.state.miflora_fertility = fertility
                self.state.miflora_battery = battery
                self.state.miflora_firmware = firmware
                self.state.miflora_status = "Connected"
                self.state.miflora_last_seen = now_str

                # Save reading for persistence across restarts
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
                self.log(f"[Mi Flora] Error: {str(e)}")
            
            self.trigger_ui_update()
            
            # Poll interval sleep
            for _ in range(int(self.state.poll_interval)):
                if not self._loop_running:
                    break
                await asyncio.sleep(1.0)

