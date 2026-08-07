import os
import asyncio
import threading
import flet as ft
from config_manager import load_config, save_config
from ble_manager import BLEState, BLEManager


VERSION = "1.0.2"



def main(page: ft.Page):
    # ── Page Setup ──────────────────────────────────────────────────────────
    page.title = f"SpyBLE v{VERSION} - BLE Sensor Dashboard"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0B0B0E"
    page.window.width = 1150
    page.window.height = 820
    page.window.resizable = True
    page.padding = 20


    main_thread_id = threading.get_ident()
    def safe_update():
        if threading.get_ident() == main_thread_id:
            page.update()
        else:
            async def _update():
                page.update()
            page.run_task(_update)

    # ── Config & State ───────────────────────────────────────────────────────
    config = load_config()
    state = BLEState()
    state.thermometer_mac = config.get("thermometer_mac", "")
    state.miflora_mac = config.get("miflora_mac", "")
    state.poll_interval = config.get("poll_interval", 30)

    # Load saved last readings if present
    last_readings = config.get("last_readings", {})
    therm_saved = last_readings.get("thermometer", {})
    if therm_saved.get("temp") is not None:
        state.thermometer_temp = therm_saved.get("temp")
        state.thermometer_humidity = therm_saved.get("humidity")
        state.thermometer_battery_v = therm_saved.get("battery_v")
        state.thermometer_battery_p = therm_saved.get("battery_p")
        state.thermometer_last_seen = f"{therm_saved.get('last_seen', '')} (αποθηκευμένο)"

    flora_saved = last_readings.get("miflora", {})
    if flora_saved.get("moisture") is not None:
        state.miflora_temp = flora_saved.get("temp")
        state.miflora_moisture = flora_saved.get("moisture")
        state.miflora_light = flora_saved.get("light")
        state.miflora_fertility = flora_saved.get("fertility")
        state.miflora_battery = flora_saved.get("battery")
        state.miflora_firmware = flora_saved.get("firmware", "")
        state.miflora_last_seen = f"{flora_saved.get('last_seen', '')} (αποθηκευμένο)"

    # ── Thermometer UI refs ───────────────────────────────────────────────────
    therm_temp   = ft.Text("--.- °C",     size=38, weight=ft.FontWeight.BOLD, color="#F0B429")
    therm_hum    = ft.Text("-- %",        size=38, weight=ft.FontWeight.BOLD, color="#4FC3F7")
    therm_batt   = ft.Text("-- V (--%)  ", size=13, color="#8F8F9F")
    therm_time   = ft.Text("Τελευταία: Ποτέ", size=12, color="#8F8F9F")
    therm_badge_text = ft.Text("DISCONNECTED", size=10, weight=ft.FontWeight.BOLD, color="#fff")
    therm_badge  = ft.Container(
        content=therm_badge_text,
        bgcolor="#374151",
        padding=ft.padding.Padding(12, 5, 12, 5),
        border_radius=10
    )
    therm_mac_input = ft.TextField(
        label="MAC Θερμομέτρου",
        value=state.thermometer_mac,
        border_color="#334155",
        bgcolor="#1C1C25",
        height=44,
        text_size=13,
        content_padding=10
    )

    # ── Mi Flora UI refs ──────────────────────────────────────────────────────
    flora_moist  = ft.Text("-- %",      size=28, weight=ft.FontWeight.BOLD, color="#34D399")
    flora_fert   = ft.Text("-- µS/cm", size=28, weight=ft.FontWeight.BOLD, color="#A78BFA")
    flora_temp   = ft.Text("--.- °C",   size=22, weight=ft.FontWeight.BOLD, color="#F0B429")
    flora_light  = ft.Text("-- Lux",    size=22, weight=ft.FontWeight.BOLD, color="#FCD34D")
    flora_batt   = ft.Text("-- %",      size=13, color="#8F8F9F")
    flora_time   = ft.Text("Τελευταία: Ποτέ", size=12, color="#8F8F9F")
    flora_badge_text = ft.Text("DISCONNECTED", size=10, weight=ft.FontWeight.BOLD, color="#fff")
    flora_badge  = ft.Container(
        content=flora_badge_text,
        bgcolor="#374151",
        padding=ft.padding.Padding(12, 5, 12, 5),
        border_radius=10
    )
    flora_mac_input = ft.TextField(
        label="MAC Mi Flora",
        value=state.miflora_mac,
        border_color="#334155",
        bgcolor="#1C1C25",
        height=44,
        text_size=13,
        content_padding=10
    )

    # ── Scanner UI ────────────────────────────────────────────────────────────
    scan_btn     = ft.Button(
        content=ft.Text("Σάρωση BLE", size=13, weight=ft.FontWeight.BOLD),
        bgcolor="#3B82F6", color="#fff", height=40,
        on_click=lambda e: page.run_task(do_scan)
    )
    scan_ring    = ft.ProgressRing(visible=False, width=18, height=18, stroke_width=2)
    device_list  = ft.ListView(spacing=8, expand=True)

    # ── Log Console (Multi-color ListView) ──────────────────────────────────
    log_list = ft.ListView(spacing=4, expand=True, auto_scroll=True)
    log_box  = ft.Container(
        content=log_list,
        bgcolor="#060609",
        border=ft.Border.all(1, "#1E293B"),
        border_radius=10,
        padding=12,
        height=160,
        expand=True
    )

    # ── Loop Controls ─────────────────────────────────────────────────────────
    loop_switch = ft.Switch(
        label="Ζωντανός Βρόγχος",
        value=False,
        on_change=lambda e: toggle_loop(e)
    )
    interval_dd = ft.Dropdown(
        label="Κάθε (δευτ.)",
        value=str(state.poll_interval),
        options=[
            ft.dropdown.Option("10"), ft.dropdown.Option("30"),
            ft.dropdown.Option("60"), ft.dropdown.Option("300"),
        ],
        border_color="#334155", bgcolor="#1C1C25",
        height=44, content_padding=10, width=130,
        on_select=lambda e: set_interval(e.control.value)
    )

    # ── UI Update ─────────────────────────────────────────────────────────────
    def update_ui():
        # Thermometer
        if state.thermometer_temp    is not None: therm_temp.value  = f"{state.thermometer_temp:.2f} °C"
        if state.thermometer_humidity is not None: therm_hum.value   = f"{state.thermometer_humidity} %"
        if state.thermometer_battery_v is not None:
            therm_batt.value = f"{state.thermometer_battery_v:.3f} V ({state.thermometer_battery_p}%)"
        therm_badge_text.value = state.thermometer_status.upper()
        therm_badge.bgcolor = {"Connected":"#064E3B","Connecting":"#78350F","Disconnected":"#7F1D1D"}.get(state.thermometer_status, "#374151")
        therm_time.value = f"Τελευταία: {state.thermometer_last_seen or 'Ποτέ'}"

        # Mi Flora
        if state.miflora_moisture  is not None: flora_moist.value = f"{state.miflora_moisture} %"
        if state.miflora_fertility is not None: flora_fert.value  = f"{state.miflora_fertility} µS/cm"
        if state.miflora_temp      is not None: flora_temp.value  = f"{state.miflora_temp:.1f} °C"
        if state.miflora_light     is not None: flora_light.value = f"{state.miflora_light} Lux"
        if state.miflora_battery   is not None: flora_batt.value  = f"{state.miflora_battery}%"
        flora_badge_text.value = state.miflora_status.upper()
        flora_badge.bgcolor = {"Connected":"#064E3B","Connecting":"#78350F","Disconnected":"#7F1D1D"}.get(state.miflora_status, "#374151")
        flora_time.value = f"Τελευταία: {state.miflora_last_seen or 'Ποτέ'}"

        # Scanner
        scan_btn.disabled = state.is_scanning
        scan_ring.visible = state.is_scanning
        device_list.controls.clear()
        for dev in state.discovered_devices:
            def mk_therm(a): return lambda e: assign_mac(a, "therm")
            def mk_flora(a): return lambda e: assign_mac(a, "flora")
            device_list.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(dev["name"], weight=ft.FontWeight.BOLD, size=13),
                            ft.Text(f"{dev['address']}  RSSI: {dev['rssi']} dBm", size=11, color="#8F8F9F")
                        ], expand=True),
                        ft.TextButton(content=ft.Text("Θερμ.", size=11, color="#F0B429"), on_click=mk_therm(dev["address"])),
                        ft.TextButton(content=ft.Text("Flora", size=11, color="#34D399"), on_click=mk_flora(dev["address"])),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    bgcolor="#1C1C25", padding=ft.padding.Padding(10, 8, 10, 8), border_radius=8
                )
            )

        # Multi-colored log entries
        log_list.controls.clear()
        for entry in state.logs[-60:]:
            log_list.controls.append(
                ft.Text(entry["text"], color=entry["color"], size=12, selectable=True)
            )

        therm_mac_input.value = state.thermometer_mac
        flora_mac_input.value = state.miflora_mac
        safe_update()

    def on_ble_update():
        page.run_task(_async_update)

    async def _async_update():
        update_ui()

    manager = BLEManager(state, on_ble_update)

    # Initial log entry
    manager.log(f"SpyBLE v{VERSION} initialized.", color="#34D399")

    # Populate controls with loaded values prior to layout build
    update_ui()

    # ── Event Handlers ────────────────────────────────────────────────────────
    async def do_scan():
        await manager.scan_devices()

    def toggle_loop(e):
        state.thermometer_mac = therm_mac_input.value.strip()
        state.miflora_mac     = flora_mac_input.value.strip()
        _save_cfg()
        if e.control.value:
            manager.start_monitoring()
        else:
            manager.stop_monitoring()

    def set_interval(val):
        try:
            state.poll_interval = int(val)
            _save_cfg()
        except ValueError:
            pass

    def assign_mac(mac, which):
        if which == "therm":
            state.thermometer_mac = mac
            therm_mac_input.value = mac
            manager.log(f"Thermometer MAC → {mac}")
        else:
            state.miflora_mac = mac
            flora_mac_input.value = mac
            manager.log(f"Mi Flora MAC → {mac}")
        _save_cfg()
        update_ui()

    def save_macs(e):
        state.thermometer_mac = therm_mac_input.value.strip()
        state.miflora_mac     = flora_mac_input.value.strip()
        _save_cfg()
        manager.log("MACs αποθηκεύτηκαν.")
        update_ui()

    def _save_cfg():
        save_config({
            "thermometer_mac": state.thermometer_mac,
            "miflora_mac": state.miflora_mac,
            "poll_interval": state.poll_interval,
            "live_mode": loop_switch.value
        })

    # ── Cards ─────────────────────────────────────────────────────────────────
    therm_card = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Row([ft.Icon(ft.Icons.THERMOSTAT, color="#F0B429", size=22),
                        ft.Text("Θερμόμετρο LYWSD03MMC", size=16, weight=ft.FontWeight.BOLD)]),
                therm_badge
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(height=8, color="#1E293B"),
            ft.Row([
                ft.Column([ft.Text("Θερμοκρασία", size=11, color="#8F8F9F"), therm_temp],
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.Column([ft.Text("Υγρασία", size=11, color="#8F8F9F"), therm_hum],
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
            ], alignment=ft.MainAxisAlignment.SPACE_EVENLY, spacing=16),
            ft.Divider(height=8, color="#1E293B"),
            ft.Row([
                ft.Row([ft.Icon(ft.Icons.BATTERY_FULL, size=14, color="#8F8F9F"), therm_batt]),
                therm_time
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ], spacing=10),
        bgcolor="#111827",
        border=ft.Border.all(1, "#1E293B"),
        border_radius=16,
        padding=20,
        width=520
    )

    flora_card = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Row([ft.Icon(ft.Icons.LOCAL_FLORIST, color="#34D399", size=22),
                        ft.Text("Αισθητήρας Mi Flora", size=16, weight=ft.FontWeight.BOLD)]),
                flora_badge
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(height=8, color="#1E293B"),
            ft.Row([
                ft.Column([ft.Text("Υγρασία", size=11, color="#8F8F9F"), flora_moist],
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.Column([ft.Text("Λίπασμα", size=11, color="#8F8F9F"), flora_fert],
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
            ], alignment=ft.MainAxisAlignment.SPACE_EVENLY, spacing=16),
            ft.Row([
                ft.Column([ft.Text("Θερμ.", size=11, color="#8F8F9F"), flora_temp],
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.Column([ft.Text("Φως", size=11, color="#8F8F9F"), flora_light],
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
            ], alignment=ft.MainAxisAlignment.SPACE_EVENLY, spacing=16),
            ft.Divider(height=8, color="#1E293B"),
            ft.Row([
                ft.Row([ft.Icon(ft.Icons.BATTERY_FULL, size=14, color="#8F8F9F"), flora_batt]),
                flora_time
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ], spacing=10),
        bgcolor="#111827",
        border=ft.Border.all(1, "#1E293B"),
        border_radius=16,
        padding=20,
        width=520
    )

    setup_panel = ft.Container(
        content=ft.Column([
            ft.Text("Ρύθμιση MAC", size=15, weight=ft.FontWeight.BOLD),
            therm_mac_input,
            flora_mac_input,
            ft.Button(
                content=ft.Text("Αποθήκευση", size=13, weight=ft.FontWeight.BOLD),
                bgcolor="#10B981", color="#fff", height=40,
                on_click=save_macs
            ),
            ft.Divider(height=12, color="#1E293B"),
            ft.Text("Σάρωση BLE", size=15, weight=ft.FontWeight.BOLD),
            ft.Row([scan_btn, scan_ring], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(
                content=device_list,
                height=140,
                bgcolor="#0D0D14",
                border=ft.Border.all(1, "#1E293B"),
                border_radius=8,
                padding=8
            )
        ], spacing=12),
        bgcolor="#111827",
        border=ft.Border.all(1, "#1E293B"),
        border_radius=16,
        padding=20,
        width=400
    )

    log_panel = ft.Container(
        content=ft.Column([
            ft.Text("Live Log", size=15, weight=ft.FontWeight.BOLD),
            log_box
        ], spacing=10, expand=True),
        bgcolor="#111827",
        border=ft.Border.all(1, "#1E293B"),
        border_radius=16,
        padding=20,
        expand=True
    )

    # ── Final Layout ──────────────────────────────────────────────────────────
    page.add(
        ft.Column([
            # Header
            ft.Row([
                ft.Row([
                    ft.Icon(ft.Icons.BLUETOOTH_CONNECTED, color="#3B82F6", size=30),
                    ft.Column([
                        ft.Text(f"SpyBLE v{VERSION}", size=28, weight=ft.FontWeight.BOLD),
                        ft.Text("Ζωντανός Έλεγχος BLE Αισθητήρων Xiaomi", size=13, color="#8F8F9F")
                    ], spacing=0)
                ]),
                ft.Row([loop_switch, interval_dd], spacing=12)
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(height=10, color="#1E293B"),
            # Sensor cards
            ft.Row([therm_card, flora_card], spacing=16, wrap=True),
            ft.Divider(height=10, color="#1E293B"),
            # Bottom row: setup + logs
            ft.Row([setup_panel, log_panel], spacing=16, expand=True)
        ], spacing=16, expand=True)
    )

    try:
        import pyi_splash
        pyi_splash.close()
    except ImportError:
        pass



    def handle_exit(e=None):
        try:
            manager.stop_monitoring()
        except Exception:
            pass
        os._exit(0)

    page.on_close = handle_exit
    page.on_disconnect = handle_exit
    page.window.on_event = lambda e: handle_exit(e) if getattr(e, "data", "") == "close" else None

    # Auto-start monitoring if live_mode was active
    if config.get("live_mode", True):
        loop_switch.value = True
        threading.Timer(0.5, manager.start_monitoring).start()

if __name__ == "__main__":
    ft.run(main)



