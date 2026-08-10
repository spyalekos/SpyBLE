import os
import math
import asyncio
import threading
import traceback
import flet as ft
from config_manager import load_config, save_config
from ble_manager import BLEState, BLEManager


VERSION = "1.4.1"


def calc_dew_point(temp, hum):
    if temp is None or hum is None or hum <= 0:
        return None
    try:
        a = 17.27
        b = 237.7
        alpha = ((a * temp) / (b + temp)) + math.log(hum / 100.0)
        return (b * alpha) / (a - alpha)
    except Exception:
        return None


def get_comfort_info(temp, hum):
    if temp is None or hum is None:
        return ("Αναμονή μετρήσεων...", "#475569", ft.Icons.HOURGLASS_EMPTY)
    if 20.0 <= temp <= 26.0 and 35 <= hum <= 60:
        return ("Ιδανικό Περιβάλλον", "#059669", ft.Icons.TAG_FACES)
    elif temp < 18.0:
        return ("Χαμηλή Θερμοκρασία (Κρύο)", "#2563EB", ft.Icons.AC_UNIT)
    elif temp > 27.0:
        return ("Υψηλή Θερμοκρασία (Ζέστη)", "#DC2626", ft.Icons.WHATSHOT)
    elif hum < 35:
        return ("Ξηρός Αέρας", "#D97706", ft.Icons.AIR)
    elif hum > 60:
        return ("Υψηλή Υγρασία", "#0284C7", ft.Icons.WATER_DROP)
    else:
        return ("Κανονικές Συνθήκες", "#7C3AED", ft.Icons.CHECK_CIRCLE_OUTLINE)


def get_flora_health(moist, fert, light):
    if moist is None:
        return ("Αναμονή δεδομένων αισθητήρα...", "#475569", ft.Icons.HOURGLASS_EMPTY)
    
    issues = []
    if moist < 15:
        issues.append("Χρειάζεται Πότισμα 💧")
    elif moist > 65:
        issues.append("Υπερβολική Υγρασία 🌊")

    if fert is not None and fert > 0:
        if fert < 350:
            issues.append("Χρειάζεται Λίπασμα 🌿")
        elif fert > 1200:
            issues.append("Υπερβολικό Λίπασμα ⚠️")

    if light is not None and light > 0:
        if light < 200:
            issues.append("Χαμηλός Φωτισμός 🌑")

    if not issues:
        return ("Άριστη Υγεία Φυτού ✨", "#059669", ft.Icons.ECO)
    else:
        return (" & ".join(issues), "#D97706" if len(issues) == 1 else "#DC2626", ft.Icons.WARNING_AMBER_ROUNDED)


def main(page: ft.Page):
    manager = None
    def handle_exit(e=None):
        if manager:
            try:
                manager.stop_monitoring()
            except Exception:
                pass
        os._exit(0)

    page.on_close = handle_exit
    page.on_disconnect = handle_exit
    page.window.on_event = lambda e: handle_exit(e) if getattr(e, "data", "") == "close" else None

    try:
        # ── Page Setup ──────────────────────────────────────────────────────────
        page.title = f"SpyBLE v{VERSION} - BLE Sensor Dashboard"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = "#0B0B0E"
        page.window.width = 1150
        page.window.height = 850
        page.window.resizable = True
        page.padding = 20
        page.scroll = ft.ScrollMode.AUTO

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
        state.thermometer_history = config.get("history_thermometer", [])
        state.miflora_history = config.get("history_miflora", [])

        # Maximize card state: None, "thermometer", or "miflora"
        maximized_card = None
        session_min_temp = None
        session_max_temp = None
        session_min_hum = None
        session_max_hum = None

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

        def toggle_maximize(target):
            nonlocal maximized_card
            if maximized_card == target:
                maximized_card = None
            else:
                maximized_card = target
            update_ui()

        # ── Help Dialog Handler ───────────────────────────────────────────────────
        help_dialog = None
        def open_help_dialog():
            nonlocal help_dialog
            dialog_content = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.INFO_OUTLINE, color="#3B82F6", size=22),
                        ft.Text(f"Οδηγίες Χρήσης SpyBLE v{VERSION}", size=18, weight=ft.FontWeight.BOLD, color="#F8FAFC")
                    ], spacing=8),
                    ft.Divider(height=10, color="#1E293B"),
                    
                    ft.Text("🌟 Τι είναι το SpyBLE;", size=14, weight=ft.FontWeight.BOLD, color="#38BDF8"),
                    ft.Text(
                        "Το SpyBLE είναι μια σύγχρονη desktop εφαρμογή παρακολούθησης αισθητήρων Bluetooth Low Energy (BLE) της Xiaomi:\n"
                        "• Θερμόμετρα LYWSD03MMC (Θερμοκρασία, Υγρασία, Τάση & % Μπαταρίας)\n"
                        "• Αισθητήρες Φυτών Mi Flora / VegTrug (Υγρασία χώματος, Αγωγιμότητα/Λίπασμα, Θερμοκρασία, Φωτεινότητα)",
                        size=12, color="#CBD5E1"
                    ),
                    
                    ft.Divider(height=8, color="#1E293B"),
                    ft.Text("📡 Πώς Λειτουργεί η Σύνδεση BLE;", size=14, weight=ft.FontWeight.BOLD, color="#F0B429"),
                    ft.Text(
                        "1. Rapid Shooting Mode (Μέθοδος 2):\n"
                        "   Ταχύτατες ριπές κλήσεων GATT (ανά 300ms) για άμεση λήψη αρχικών μετρήσεων, ακόμα κι αν η συσκευή είναι σε εξοικονόμηση ενέργειας.\n\n"
                        "2. Passive BLE Scanner (Μέθοδος 3):\n"
                        "   Συνεχής παθητική ακρόαση διαφημιστικών πακέτων στο παρασκήνιο (MiBeacon 0xFE95, ATC/PVVX 0x181A, BTHome 0xFCD2) για ακαριαία ενημέρωση μετρήσεων χωρίς κατανάλωση μπαταρίας.\n\n"
                        "3. Hardware MAC Resolution:\n"
                        "   Αυτόματος εντοπισμός της εσωτερικής Hardware MAC διεύθυνσης από τα πακέτα payload για πλήρη συμβατότητα με τα Windows.",
                        size=12, color="#CBD5E1"
                    ),

                    ft.Divider(height=8, color="#1E293B"),
                    ft.Text("🛠️ Αντιμετώπιση Προβλημάτων Σύνδεσης (Troubleshooting)", size=14, weight=ft.FontWeight.BOLD, color="#F87171"),
                    ft.Text(
                        "1. Ενεργοποίηση Bluetooth:\n"
                        "   Βεβαιωθείτε ότι το Bluetooth του υπολογιστή σας είναι ενεργοποιημένο στο σύστημα.\n\n"
                        "2. Κλειστή Εφαρμογή Xiaomi στο Κινητό (Single Connection Rule):\n"
                        "   ΚΛΕΙΣΤΕ την εφαρμογή Xiaomi Home / Mi Home στο κινητό σας τηλέφωνο. Οι συσκευές BLE επιτρέπουν μόνο μία ενεργή σύνδεση master τη φορά. Αν το κινητό είναι συνδεδεμένο με το θερμόμετρο ή το Mi Flora, η συσκευή σταματά να εκπέμπει διαφημιστικά πακέτα και δεν μπορεί να συνδεθεί στο SpyBLE.\n\n"
                        "3. Μπαταρία & Απόσταση:\n"
                        "   Ελέγξτε αν η μπαταρία της συσκευής BLE έχει εξαντληθεί ή αν η απόσταση από τον υπολογιστή είναι υπερβολικά μεγάλη.\n\n"
                        "4. Επανεκκίνηση Σάρωσης / Ενεργή Επανάληψη:\n"
                        "   Αν η συσκευή είναι σε εξοικονόμηση ενέργειας (sleep mode), ενεργοποιήστε την 'Ενεργή Επανάληψη' ή πατήστε 'Σάρωση BLE'. Το Rapid Shooting Mode θα κάνει ριπές κλήσεων για να τη συνδέσει.",
                        size=12, color="#CBD5E1"
                    ),

                    ft.Divider(height=8, color="#1E293B"),
                    ft.Text("🔲 Λειτουργία Μεγιστοποίησης (Maximize Focus Mode)", size=14, weight=ft.FontWeight.BOLD, color="#34D399"),
                    ft.Text(
                        "Πατώντας το κουμπί μεγιστοποίησης στην κάρτα του Θερμομέτρου ή του Mi Flora:\n"
                        "• Η επιλεγμένη κάρτα επεκτείνεται σε πλήρες πλάτος.\n"
                        "• Εμφανίζονται αναλυτικοί δείκτες με λευκά & έντονα (bold) γράμματα: Σημείο Δρόσου (Dew Point), Δείκτης Άνεσης, Ελάχιστα/Μέγιστα συνεδρίας, Μπάρα Μπαταρίας, Διαγνωστικά Υγείας Φυτού (Πότισμα, Λίπασμα, Φως) & Προοδευτικές Μπάρες Στάθμης.\n"
                        "• Πατώντας το κουμπί επαναφοράς, επιστρέφετε στην προβολή side-by-side.",
                        size=12, color="#CBD5E1"
                    ),

                    ft.Divider(height=8, color="#1E293B"),
                    ft.Text("⚙️ Ρυθμίσεις & Κονσόλα Logs", size=14, weight=ft.FontWeight.BOLD, color="#A78BFA"),
                    ft.Text(
                        "• Ρύθμιση MAC: Εισάγετε τη MAC διεύθυνση ή επιλέξτε την από τη Σάρωση BLE.\n"
                        "• Ενεργή Επανάληψη & Χρόνος: Ενεργοποιήστε τον αυτόματο έλεγχο και επιλέξτε ρυθμό ανανέωσης (5s έως 300s).\n"
                        "• Live Log Console: Έγχρωμη καταγραφή συμβάντων, συνδέσεων και παθητικών λήψεων σε πραγματικό χρόνο.",
                        size=12, color="#CBD5E1"
                    ),

                    ft.Divider(height=8, color="#1E293B"),
                    ft.Text("📊 Σελίδες Ιστορικού & Εξαγωγή (CSV / JSON)", size=14, weight=ft.FontWeight.BOLD, color="#FBBF24"),
                    ft.Text(
                        "• Καρτέλα Ιστορικού Θερμομέτρου: Προβολή αποθηκευμένων μετρήσεων μνήμης Flash, αναλυτικά στατιστικά (Min/Max/Avg) & εξαγωγή σε αρχεία CSV / JSON.\n"
                        "• Καρτέλα Ιστορικού Mi Flora: Ανάκτηση ιστορικού υγείας φυτού (Υγρασία Χώματος, Λίπασμα, Φως) & εξαγωγή σε αρχεία CSV / JSON.",
                        size=12, color="#CBD5E1"
                    ),

                    ft.Divider(height=12, color="#1E293B"),
                    ft.Row([
                        ft.Text(f"SpyBLE v{VERSION} — Ανάπτυξη από ", size=11, color="#64748B"),
                        ft.TextButton(
                            content=ft.Text("SpyAlekos", size=11, weight=ft.FontWeight.BOLD, color="#3B82F6"),
                            style=ft.ButtonStyle(padding=0),
                            url="https://alekos.program.gr"
                        )
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=0)
                ], spacing=8, scroll=ft.ScrollMode.AUTO),
                width=520,
                height=480,
                padding=10
            )

            help_dialog = ft.AlertDialog(
                content=dialog_content,
                actions=[
                    ft.Button(
                        content=ft.Text("Κλείσιμο", size=13, weight=ft.FontWeight.BOLD),
                        bgcolor="#3B82F6", color="#fff",
                        on_click=lambda e: close_help_dialog()
                    )
                ],
                actions_alignment=ft.MainAxisAlignment.END,
                bgcolor="#111827"
            )

            def close_help_dialog():
                if help_dialog:
                    help_dialog.open = False
                    page.update()

            page.overlay.append(help_dialog)
            help_dialog.open = True
            page.update()

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

        # Thermometer Maximized Extra Controls with White Bold text & icons
        therm_comfort_icon = ft.Icon(ft.Icons.HOURGLASS_EMPTY, color="#FFFFFF", size=18)
        therm_comfort_text = ft.Text("Αναμονή μετρήσεων...", size=13, weight=ft.FontWeight.BOLD, color="#FFFFFF")
        therm_comfort_badge = ft.Container(
            content=ft.Row([therm_comfort_icon, therm_comfort_text], spacing=8),
            bgcolor="#475569",
            padding=ft.padding.Padding(12, 6, 14, 6),
            border_radius=8
        )
        therm_dew_text = ft.Text("Σημείο Δρόσου: --.- °C", size=13, color="#CBD5E1")
        therm_minmax_text = ft.Text("Session Min/Max: --", size=12, color="#94A3B8")
        therm_batt_progress = ft.ProgressBar(value=0.0, color="#10B981", bgcolor="#1E293B", height=8)

        therm_max_btn = ft.IconButton(
            icon=ft.Icons.OPEN_IN_FULL,
            icon_color="#F0B429",
            icon_size=20,
            tooltip="Μεγιστοποίηση Θερμομέτρου",
            on_click=lambda e: toggle_maximize("thermometer")
        )

        therm_details_box = ft.Container(
            content=ft.Column([
                ft.Divider(height=12, color="#1E293B"),
                ft.Row([
                    ft.Text("🔍 Αναλυτικά Στοιχεία & Δείκτες Άνεσης", size=14, weight=ft.FontWeight.BOLD, color="#F0B429"),
                    therm_comfort_badge
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                ft.Row([
                    ft.Column([
                        ft.Text("Σημείο Δρόσου (Dew Point)", size=11, color="#8F8F9F"),
                        therm_dew_text
                    ], width=470),
                    ft.Column([
                        ft.Text("Ελάχιστα / Μέγιστα Συνεδρίας", size=11, color="#8F8F9F"),
                        therm_minmax_text
                    ], width=470),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                ft.Column([
                    ft.Text("Στάθμη Μπαταρίας", size=11, color="#8F8F9F"),
                    therm_batt_progress
                ], spacing=4),
            ], spacing=10),
            visible=False
        )

        therm_card = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Row([ft.Icon(ft.Icons.THERMOSTAT, color="#F0B429", size=22),
                            ft.Text("Θερμόμετρο LYWSD03MMC", size=16, weight=ft.FontWeight.BOLD)]),
                    ft.Row([therm_badge, therm_max_btn], spacing=6)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=8, color="#1E293B"),
                ft.Row([
                    ft.Column([ft.Text("Θερμοκρασία", size=11, color="#8F8F9F"), therm_temp],
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Column([ft.Text("Υγρασία", size=11, color="#8F8F9F"), therm_hum],
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ], alignment=ft.MainAxisAlignment.SPACE_EVENLY, spacing=16),
                ft.Divider(height=8, color="#1E293B"),
                ft.Row([
                    ft.Row([ft.Icon(ft.Icons.BATTERY_FULL, size=14, color="#8F8F9F"), therm_batt]),
                    therm_time
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                therm_details_box
            ], spacing=10),
            bgcolor="#111827",
            border=ft.Border.all(1, "#1E293B"),
            border_radius=16,
            padding=20,
            width=520
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

        # Mi Flora Maximized Extra Controls with White Bold text & icons
        flora_health_icon = ft.Icon(ft.Icons.HOURGLASS_EMPTY, color="#FFFFFF", size=18)
        flora_health_text = ft.Text("Αναμονή δεδομένων...", size=13, weight=ft.FontWeight.BOLD, color="#FFFFFF")
        flora_health_badge = ft.Container(
            content=ft.Row([flora_health_icon, flora_health_text], spacing=8),
            bgcolor="#475569",
            padding=ft.padding.Padding(12, 6, 14, 6),
            border_radius=8
        )

        flora_moist_bar = ft.ProgressBar(value=0.0, color="#34D399", bgcolor="#1E293B", height=8)
        flora_moist_lbl = ft.Text("Υγρασία Χώματος: --%", size=12, color="#CBD5E1")

        flora_fert_bar = ft.ProgressBar(value=0.0, color="#A78BFA", bgcolor="#1E293B", height=8)
        flora_fert_lbl = ft.Text("Αγωγιμότητα / Λίπασμα: -- µS/cm", size=12, color="#CBD5E1")

        flora_light_bar = ft.ProgressBar(value=0.0, color="#FCD34D", bgcolor="#1E293B", height=8)
        flora_light_lbl = ft.Text("Φωτεινότητα: -- Lux", size=12, color="#CBD5E1")

        flora_firmware_txt = ft.Text("Firmware: --", size=12, color="#8F8F9F")

        flora_max_btn = ft.IconButton(
            icon=ft.Icons.OPEN_IN_FULL,
            icon_color="#34D399",
            icon_size=20,
            tooltip="Μεγιστοποίηση Mi Flora",
            on_click=lambda e: toggle_maximize("miflora")
        )

        flora_details_box = ft.Container(
            content=ft.Column([
                ft.Divider(height=12, color="#1E293B"),
                ft.Row([
                    ft.Text("🌱 Διαγνωστικά Υγείας Φυτού & Μπάρες Επιπέδων", size=14, weight=ft.FontWeight.BOLD, color="#34D399"),
                    flora_health_badge
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                ft.Row([
                    ft.Column([
                        flora_moist_lbl,
                        flora_moist_bar
                    ], width=470),
                    ft.Column([
                        flora_fert_lbl,
                        flora_fert_bar
                    ], width=470),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                ft.Row([
                    ft.Column([
                        flora_light_lbl,
                        flora_light_bar
                    ], width=470),
                    ft.Column([
                        ft.Text("Πληροφορίες Αισθητήρα", size=11, color="#8F8F9F"),
                        flora_firmware_txt
                    ], width=470),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True)
            ], spacing=10),
            visible=False
        )

        flora_card = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Row([ft.Icon(ft.Icons.LOCAL_FLORIST, color="#34D399", size=22),
                            ft.Text("Αισθητήρας Mi Flora", size=16, weight=ft.FontWeight.BOLD)]),
                    ft.Row([flora_badge, flora_max_btn], spacing=6)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=8, color="#1E293B"),
                ft.Row([
                    ft.Column([ft.Text("Υγρασία", size=11, color="#8F8F9F"), flora_moist],
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Column([ft.Text("Λίπασμα", size=11, color="#8F8F9F"), flora_fert],
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ], alignment=ft.MainAxisAlignment.SPACE_EVENLY, spacing=16),
                ft.Row([
                    ft.Column([ft.Text("Θερμ.", size=11, color="#8F8F9F"), flora_temp],
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Column([ft.Text("Φως", size=11, color="#8F8F9F"), flora_light],
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ], alignment=ft.MainAxisAlignment.SPACE_EVENLY, spacing=16),
                ft.Divider(height=8, color="#1E293B"),
                ft.Row([
                    ft.Row([ft.Icon(ft.Icons.BATTERY_FULL, size=14, color="#8F8F9F"), flora_batt]),
                    flora_time
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                flora_details_box
            ], spacing=10),
            bgcolor="#111827",
            border=ft.Border.all(1, "#1E293B"),
            border_radius=16,
            padding=20,
            width=520
        )

        # ── Scanner UI ────────────────────────────────────────────────────────────
        scan_btn     = ft.Button(
            content=ft.Text("Σάρωση BLE", size=13, weight=ft.FontWeight.BOLD),
            bgcolor="#3B82F6", color="#fff", height=40,
            on_click=lambda e: page.run_task(do_scan)
        )
        scan_ring    = ft.ProgressRing(visible=False, width=18, height=18, stroke_width=2)
        device_list  = ft.ListView(spacing=8, height=160)

        # ── Log Console (Multi-color ListView) ──────────────────────────────────
        log_list = ft.ListView(spacing=4, height=210, auto_scroll=True)
        log_box  = ft.Container(
            content=log_list,
            bgcolor="#060609",
            border=ft.Border.all(1, "#1E293B"),
            border_radius=10,
            padding=12,
            height=235
        )

        # ── Loop Controls & Header Buttons ────────────────────────────────────────
        loop_switch = ft.Switch(
            label="Ενεργή Επανάληψη",
            value=False,
            on_change=lambda e: toggle_loop(e)
        )
        interval_dd = ft.Dropdown(
            label="Κάθε (δευτ.)",
            value=str(state.poll_interval),
            options=[
                ft.dropdown.Option("5"), ft.dropdown.Option("10"),
                ft.dropdown.Option("30"), ft.dropdown.Option("60"),
                ft.dropdown.Option("300"),
            ],
            border_color="#334155", bgcolor="#1C1C25",
            height=44, content_padding=10, width=130,
            on_select=lambda e: set_interval(e.control.value)
        )
        help_btn = ft.IconButton(
            icon=ft.Icons.HELP_OUTLINE,
            icon_color="#3B82F6",
            icon_size=24,
            tooltip="Βοήθεια & Οδηγίες Χρήσης",
            on_click=lambda e: open_help_dialog()
        )

        setup_panel = ft.Container(
            content=ft.Column([
                ft.Text("Ρύθμιση MAC", size=15, weight=ft.FontWeight.BOLD),
                therm_mac_input,
                flora_mac_input,
                ft.Button(
                    content=ft.Text("Αποθήκευση", size=13, weight=ft.FontWeight.BOLD),
                    bgcolor="#10B981", color="#fff", height=40,
                    on_click=lambda e: save_macs(e)
                ),
                ft.Divider(height=12, color="#1E293B"),
                ft.Text("Σάρωση BLE", size=15, weight=ft.FontWeight.BOLD),
                ft.Row([scan_btn, scan_ring], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(
                    content=device_list,
                    height=160,
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
            width=520
        )

        log_panel = ft.Container(
            content=ft.Column([
                ft.Text("Live Log Console", size=15, weight=ft.FontWeight.BOLD),
                log_box
            ], spacing=10),
            bgcolor="#111827",
            border=ft.Border.all(1, "#1E293B"),
            border_radius=16,
            padding=20,
            width=520
        )

        # ── Thermometer History UI ────────────────────────────────────────────────
        therm_hist_status_txt = ft.Text("Έτοιμο για συγχρονισμό", size=13, color="#CBD5E1")
        therm_hist_progress   = ft.ProgressBar(value=0.0, color="#3B82F6", bgcolor="#1E293B", height=6, visible=False)

        therm_hist_stat_total    = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color="#3B82F6")
        therm_hist_stat_temp     = ft.Text("-- °C", size=22, weight=ft.FontWeight.BOLD, color="#F0B429")
        therm_hist_stat_temp_sub = ft.Text("Min: -- | Max: --", size=11, color="#8F8F9F")
        therm_hist_stat_hum      = ft.Text("-- %", size=22, weight=ft.FontWeight.BOLD, color="#4FC3F7")
        therm_hist_stat_hum_sub  = ft.Text("Min: -- | Max: --", size=11, color="#8F8F9F")
        therm_hist_stat_range    = ft.Text("Χωρίς εγγραφές", size=12, color="#94A3B8")

        therm_hist_list = ft.ListView(spacing=8, height=340)

        therm_hist_sync_btn = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.SYNC, size=16), ft.Text("Συγχρονισμός Ιστορικού", size=13, weight=ft.FontWeight.BOLD)]),
            bgcolor="#3B82F6", color="#fff", height=40,
            on_click=lambda e: page.run_task(do_sync_therm_hist)
        )
        therm_hist_csv_btn = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.DOWNLOAD, size=16), ft.Text("Εξαγωγή CSV", size=13, weight=ft.FontWeight.BOLD)]),
            bgcolor="#10B981", color="#fff", height=40,
            on_click=lambda e: do_export_csv("thermometer")
        )
        therm_hist_json_btn = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.CODE, size=16), ft.Text("Εξαγωγή JSON", size=13, weight=ft.FontWeight.BOLD)]),
            bgcolor="#8B5CF6", color="#fff", height=40,
            on_click=lambda e: do_export_json("thermometer")
        )

        therm_history_panel = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Column([
                        ft.Text("🌡️ Ιστορικό & Αναλυτικά Στοιχεία Θερμομέτρου (LYWSD03MMC)", size=17, weight=ft.FontWeight.BOLD, color="#F0B429"),
                        therm_hist_status_txt
                    ], spacing=2),
                    ft.Row([therm_hist_sync_btn, therm_hist_csv_btn, therm_hist_json_btn], spacing=10, wrap=True)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                therm_hist_progress,
                ft.Divider(height=10, color="#1E293B"),
                ft.Row([
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Σύνολο Εγγραφών", size=11, color="#8F8F9F"),
                            therm_hist_stat_total
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor="#1C1C25", padding=12, border_radius=10, width=220
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Μέση Θερμοκρασία", size=11, color="#8F8F9F"),
                            therm_hist_stat_temp,
                            therm_hist_stat_temp_sub
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor="#1C1C25", padding=12, border_radius=10, width=230
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Μέση Υγρασία", size=11, color="#8F8F9F"),
                            therm_hist_stat_hum,
                            therm_hist_stat_hum_sub
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor="#1C1C25", padding=12, border_radius=10, width=230
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Χρονικό Εύρος", size=11, color="#8F8F9F"),
                            therm_hist_stat_range
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor="#1C1C25", padding=12, border_radius=10, width=270
                    ),
                ], spacing=12, wrap=True),
                ft.Divider(height=10, color="#1E293B"),
                ft.Text("📋 Καταγραφή Μετρήσεων Μνήμης Flash", size=14, weight=ft.FontWeight.BOLD, color="#CBD5E1"),
                ft.Container(
                    content=therm_hist_list,
                    bgcolor="#060609", border=ft.Border.all(1, "#1E293B"), border_radius=10, padding=12
                )
            ], spacing=14),
            bgcolor="#111827", border=ft.Border.all(1, "#1E293B"), border_radius=16, padding=20, width=1050
        )

        # ── Mi Flora History UI ───────────────────────────────────────────────────
        flora_hist_status_txt = ft.Text("Έτοιμο για συγχρονισμό", size=13, color="#CBD5E1")
        flora_hist_progress   = ft.ProgressBar(value=0.0, color="#34D399", bgcolor="#1E293B", height=6, visible=False)

        flora_hist_stat_total = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color="#34D399")
        flora_hist_stat_moist = ft.Text("-- %", size=22, weight=ft.FontWeight.BOLD, color="#059669")
        flora_hist_stat_fert  = ft.Text("-- µS/cm", size=22, weight=ft.FontWeight.BOLD, color="#3B82F6")
        flora_hist_stat_light = ft.Text("-- Lux", size=22, weight=ft.FontWeight.BOLD, color="#D97706")

        flora_hist_list = ft.ListView(spacing=8, height=340)

        flora_hist_sync_btn = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.SYNC, size=16), ft.Text("Συγχρονισμός Ιστορικού", size=13, weight=ft.FontWeight.BOLD)]),
            bgcolor="#34D399", color="#fff", height=40,
            on_click=lambda e: page.run_task(do_sync_flora_hist)
        )
        flora_hist_csv_btn = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.DOWNLOAD, size=16), ft.Text("Εξαγωγή CSV", size=13, weight=ft.FontWeight.BOLD)]),
            bgcolor="#10B981", color="#fff", height=40,
            on_click=lambda e: do_export_csv("miflora")
        )
        flora_hist_json_btn = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.CODE, size=16), ft.Text("Εξαγωγή JSON", size=13, weight=ft.FontWeight.BOLD)]),
            bgcolor="#8B5CF6", color="#fff", height=40,
            on_click=lambda e: do_export_json("miflora")
        )

        flora_history_panel = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Column([
                        ft.Text("🌿 Ιστορικό & Διαγνωστικά Αισθητήρα Mi Flora", size=17, weight=ft.FontWeight.BOLD, color="#34D399"),
                        flora_hist_status_txt
                    ], spacing=2),
                    ft.Row([flora_hist_sync_btn, flora_hist_csv_btn, flora_hist_json_btn], spacing=10, wrap=True)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                flora_hist_progress,
                ft.Divider(height=10, color="#1E293B"),
                ft.Row([
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Σύνολο Εγγραφών", size=11, color="#8F8F9F"),
                            flora_hist_stat_total
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor="#1C1C25", padding=12, border_radius=10, width=230
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Μέση Υγρασία Χώματος", size=11, color="#8F8F9F"),
                            flora_hist_stat_moist
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor="#1C1C25", padding=12, border_radius=10, width=230
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Μέσο Λίπασμα", size=11, color="#8F8F9F"),
                            flora_hist_stat_fert
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor="#1C1C25", padding=12, border_radius=10, width=230
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Μέγιστος Φωτισμός", size=11, color="#8F8F9F"),
                            flora_hist_stat_light
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor="#1C1C25", padding=12, border_radius=10, width=230
                    ),
                ], spacing=14, wrap=True),
                ft.Divider(height=10, color="#1E293B"),
                ft.Text("📋 Καταγραφή Μετρήσεων Υγείας Φυτού", size=14, weight=ft.FontWeight.BOLD, color="#CBD5E1"),
                ft.Container(
                    content=flora_hist_list,
                    bgcolor="#060609", border=ft.Border.all(1, "#1E293B"), border_radius=10, padding=12
                )
            ], spacing=14),
            bgcolor="#111827", border=ft.Border.all(1, "#1E293B"), border_radius=16, padding=20, width=1050
        )

        # ── UI Update ─────────────────────────────────────────────────────────────
        def update_ui():
            nonlocal session_min_temp, session_max_temp, session_min_hum, session_max_hum

            # Thermometer calculations & state updates
            if state.thermometer_temp is not None:
                therm_temp.value = f"{state.thermometer_temp:.2f} °C"
                if session_min_temp is None or state.thermometer_temp < session_min_temp:
                    session_min_temp = state.thermometer_temp
                if session_max_temp is None or state.thermometer_temp > session_max_temp:
                    session_max_temp = state.thermometer_temp

            if state.thermometer_humidity is not None:
                therm_hum.value = f"{state.thermometer_humidity} %"
                if session_min_hum is None or state.thermometer_humidity < session_min_hum:
                    session_min_hum = state.thermometer_humidity
                if session_max_hum is None or state.thermometer_humidity > session_max_hum:
                    session_max_hum = state.thermometer_humidity

            if state.thermometer_battery_v is not None:
                therm_batt.value = f"{state.thermometer_battery_v:.3f} V ({state.thermometer_battery_p}%)"
                therm_batt_progress.value = max(0.0, min(1.0, (state.thermometer_battery_p or 0) / 100.0))

            therm_badge_text.value = state.thermometer_status.upper()
            if "CONNECTING" in state.thermometer_status.upper():
                therm_badge.bgcolor = "#B45309"
            elif "CONNECTED" in state.thermometer_status.upper():
                therm_badge.bgcolor = "#064E3B"
            elif "DISCONNECTED" in state.thermometer_status.upper():
                therm_badge.bgcolor = "#7F1D1D"
            else:
                therm_badge.bgcolor = "#374151"
            therm_time.value = f"Τελευταία: {state.thermometer_last_seen or 'Ποτέ'}"

            # Thermometer maximized details update
            dew = calc_dew_point(state.thermometer_temp, state.thermometer_humidity)
            if dew is not None:
                therm_dew_text.value = f"{dew:.1f} °C"
            else:
                therm_dew_text.value = "--.- °C"

            c_text, c_color, c_icon = get_comfort_info(state.thermometer_temp, state.thermometer_humidity)
            therm_comfort_text.value = c_text
            therm_comfort_text.color = "#FFFFFF"  # White text for maximum legibility on colored bg
            therm_comfort_text.weight = ft.FontWeight.BOLD
            therm_comfort_icon.name = c_icon
            therm_comfort_icon.color = "#FFFFFF"  # White icon
            therm_comfort_badge.bgcolor = c_color  # Solid rich background color (Green, Orange, Red, etc.)

            min_t_str = f"{session_min_temp:.1f}°C" if session_min_temp is not None else "--"
            max_t_str = f"{session_max_temp:.1f}°C" if session_max_temp is not None else "--"
            min_h_str = f"{session_min_hum}%" if session_min_hum is not None else "--"
            max_h_str = f"{session_max_hum}%" if session_max_hum is not None else "--"
            therm_minmax_text.value = f"Temp: {min_t_str} .. {max_t_str} | Hum: {min_h_str} .. {max_h_str}"

            # Mi Flora calculations & state updates
            if state.miflora_moisture is not None:
                flora_moist.value = f"{state.miflora_moisture} %"
                flora_moist_lbl.value = f"Υγρασία Χώματος: {state.miflora_moisture}%"
                flora_moist_bar.value = max(0.0, min(1.0, state.miflora_moisture / 100.0))

            if state.miflora_fertility is not None:
                flora_fert.value = f"{state.miflora_fertility} µS/cm"
                flora_fert_lbl.value = f"Αγωγιμότητα / Λίπασμα: {state.miflora_fertility} µS/cm"
                flora_fert_bar.value = max(0.0, min(1.0, state.miflora_fertility / 1500.0))

            if state.miflora_temp is not None:
                flora_temp.value = f"{state.miflora_temp:.1f} °C"

            if state.miflora_light is not None:
                flora_light.value = f"{state.miflora_light} Lux"
                flora_light_lbl.value = f"Φωτεινότητα: {state.miflora_light} Lux"
                flora_light_bar.value = max(0.0, min(1.0, state.miflora_light / 10000.0))

            if state.miflora_battery is not None:
                flora_batt.value = f"{state.miflora_battery}%"

            if state.miflora_firmware:
                flora_firmware_txt.value = f"Firmware: {state.miflora_firmware}"

            flora_badge_text.value = state.miflora_status.upper()
            if "CONNECTING" in state.miflora_status.upper():
                flora_badge.bgcolor = "#B45309"
            elif "CONNECTED" in state.miflora_status.upper():
                flora_badge.bgcolor = "#064E3B"
            elif "DISCONNECTED" in state.miflora_status.upper():
                flora_badge.bgcolor = "#7F1D1D"
            else:
                flora_badge.bgcolor = "#374151"
            flora_time.value = f"Τελευταία: {state.miflora_last_seen or 'Ποτέ'}"

            f_text, f_color, f_icon = get_flora_health(state.miflora_moisture, state.miflora_fertility, state.miflora_light)
            flora_health_text.value = f_text
            flora_health_text.color = "#FFFFFF"  # White text for maximum legibility on colored bg
            flora_health_text.weight = ft.FontWeight.BOLD
            flora_health_icon.name = f_icon
            flora_health_icon.color = "#FFFFFF"  # White icon
            flora_health_badge.bgcolor = f_color  # Solid rich background color (Green, Orange, Red, etc.)

            # Maximize mode layout updates (Fixed widths, NO expand=True in scrollable view)
            if maximized_card == "thermometer":
                therm_card.width = 1056
                therm_card.visible = True
                therm_details_box.visible = True
                therm_max_btn.icon = ft.Icons.CLOSE_FULLSCREEN
                therm_max_btn.tooltip = "Επαναφορά (Side-by-Side)"
                flora_card.visible = False
            elif maximized_card == "miflora":
                flora_card.width = 1056
                flora_card.visible = True
                flora_details_box.visible = True
                flora_max_btn.icon = ft.Icons.CLOSE_FULLSCREEN
                flora_max_btn.tooltip = "Επαναφορά (Side-by-Side)"
                therm_card.visible = False
            else:
                therm_card.width = 520
                therm_card.visible = True
                therm_details_box.visible = False
                therm_max_btn.icon = ft.Icons.OPEN_IN_FULL
                therm_max_btn.tooltip = "Μεγιστοποίηση Θερμομέτρου"

                flora_card.width = 520
                flora_card.visible = True
                flora_details_box.visible = False
                flora_max_btn.icon = ft.Icons.OPEN_IN_FULL
                flora_max_btn.tooltip = "Μεγιστοποίηση Mi Flora"

            # Scanner
            scan_btn.disabled = state.is_scanning
            scan_ring.visible = state.is_scanning
            device_list.controls.clear()
            def make_assign_click(mac_addr, sensor_type):
                return lambda e: assign_mac(mac_addr, sensor_type)

            for dev in state.discovered_devices:
                hw_mac = dev.get("hardware_mac", "")
                target_mac = hw_mac if hw_mac else dev["address"]
                
                if hw_mac and hw_mac != dev["address"]:
                    mac_subtitle = f"HW: {hw_mac} (Win: {dev['address']})  RSSI: {dev['rssi']} dBm"
                else:
                    mac_subtitle = f"{dev['address']}  RSSI: {dev['rssi']} dBm"

                device_list.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Column([
                                ft.Text(dev["name"], weight=ft.FontWeight.BOLD, size=13),
                                ft.Text(mac_subtitle, size=11, color="#8F8F9F")
                            ], width=260),
                            ft.TextButton(content=ft.Text("Θερμ.", size=11, color="#F0B429"), on_click=make_assign_click(target_mac, "therm")),
                            ft.TextButton(content=ft.Text("Flora", size=11, color="#34D399"), on_click=make_assign_click(target_mac, "flora")),
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

            # ── Refresh Thermometer History UI ─────────────────────────────────
            therm_hist_status_txt.value = state.thermometer_history_status
            if state.is_syncing_thermometer_history:
                therm_hist_progress.visible = True
                therm_hist_progress.value = state.thermometer_history_progress
            else:
                therm_hist_progress.visible = False

            if state.thermometer_history:
                temps = [x["temp"] for x in state.thermometer_history if "temp" in x]
                hums = [x["humidity"] for x in state.thermometer_history if "humidity" in x]
                if temps:
                    avg_t, min_t, max_t = sum(temps)/len(temps), min(temps), max(temps)
                    therm_hist_stat_temp.value = f"{avg_t:.1f} °C"
                    therm_hist_stat_temp_sub.value = f"Min: {min_t:.1f}°C | Max: {max_t:.1f}°C"
                if hums:
                    avg_h, min_h, max_h = sum(hums)/len(hums), min(hums), max(hums)
                    therm_hist_stat_hum.value = f"{int(avg_h)} %"
                    therm_hist_stat_hum_sub.value = f"Min: {int(min_h)}% | Max: {int(max_h)}%"

                therm_hist_stat_total.value = str(len(state.thermometer_history))
                t_first = state.thermometer_history[0].get("timestamp", "")
                t_last = state.thermometer_history[-1].get("timestamp", "")
                therm_hist_stat_range.value = f"{t_first} ➔ {t_last}"

            therm_hist_list.controls.clear()
            for item in reversed(state.thermometer_history[-40:]):
                t_val = item.get("temp", 0.0)
                h_val = item.get("humidity", 0)
                ts = item.get("timestamp", "")
                t_col = "#059669" if 20 <= t_val <= 25 else ("#2563EB" if t_val < 20 else "#DC2626")
                h_col = "#0284C7" if 35 <= h_val <= 60 else ("#D97706" if h_val < 35 else "#7C3AED")
                therm_hist_list.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Row([
                                ft.Icon(ft.Icons.ACCESS_TIME, size=15, color="#8F8F9F"),
                                ft.Text(ts, size=12, weight=ft.FontWeight.BOLD, color="#CBD5E1")
                            ], spacing=6),
                            ft.Row([
                                ft.Container(content=ft.Text(f"🌡️ {t_val:.1f} °C", size=11, weight=ft.FontWeight.BOLD, color="#FFF"), bgcolor=t_col, padding=ft.Padding(8, 3, 8, 3), border_radius=6),
                                ft.Container(content=ft.Text(f"💧 {h_val} %", size=11, weight=ft.FontWeight.BOLD, color="#FFF"), bgcolor=h_col, padding=ft.Padding(8, 3, 8, 3), border_radius=6),
                            ], spacing=8)
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        bgcolor="#1C1C25", border_radius=8, padding=8
                    )
                )

            # ── Refresh Mi Flora History UI ───────────────────────────────────────
            flora_hist_status_txt.value = state.miflora_history_status
            if state.is_syncing_miflora_history:
                flora_hist_progress.visible = True
                flora_hist_progress.value = state.miflora_history_progress
            else:
                flora_hist_progress.visible = False

            if state.miflora_history:
                moists = [x["moisture"] for x in state.miflora_history if "moisture" in x]
                ferts = [x["fertility"] for x in state.miflora_history if "fertility" in x]
                lights = [x["light"] for x in state.miflora_history if "light" in x]
                if moists:
                    flora_hist_stat_moist.value = f"{int(sum(moists)/len(moists))} %"
                if ferts:
                    flora_hist_stat_fert.value = f"{int(sum(ferts)/len(ferts))} µS/cm"
                if lights:
                    flora_hist_stat_light.value = f"{int(max(lights))} Lux"
                flora_hist_stat_total.value = str(len(state.miflora_history))

            flora_hist_list.controls.clear()
            for item in reversed(state.miflora_history[-40:]):
                m_val = item.get("moisture", 0)
                f_val = item.get("fertility", 0)
                l_val = item.get("light", 0)
                t_val = item.get("temp", 0.0)
                ts = item.get("timestamp", "")
                m_col = "#059669" if 15 <= m_val <= 65 else ("#D97706" if m_val < 15 else "#DC2626")
                f_col = "#3B82F6" if 300 <= f_val <= 2000 else "#8F8F9F"
                flora_hist_list.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Row([
                                ft.Icon(ft.Icons.ACCESS_TIME, size=15, color="#8F8F9F"),
                                ft.Text(ts, size=12, weight=ft.FontWeight.BOLD, color="#CBD5E1")
                            ], spacing=6),
                            ft.Row([
                                ft.Container(content=ft.Text(f"💧 {m_val}%", size=11, weight=ft.FontWeight.BOLD, color="#FFF"), bgcolor=m_col, padding=ft.Padding(8, 3, 8, 3), border_radius=6),
                                ft.Container(content=ft.Text(f"🧪 {f_val}µS", size=11, weight=ft.FontWeight.BOLD, color="#FFF"), bgcolor=f_col, padding=ft.Padding(8, 3, 8, 3), border_radius=6),
                                ft.Container(content=ft.Text(f"☀️ {l_val}Lx", size=11, weight=ft.FontWeight.BOLD, color="#FFF"), bgcolor="#D97706", padding=ft.Padding(8, 3, 8, 3), border_radius=6),
                                ft.Container(content=ft.Text(f"🌡️ {t_val:.1f}°C", size=11, weight=ft.FontWeight.BOLD, color="#FFF"), bgcolor="#475569", padding=ft.Padding(8, 3, 8, 3), border_radius=6),
                            ], spacing=6)
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        bgcolor="#1C1C25", border_radius=8, padding=8
                    )
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
                state.thermometer_has_data = False
                therm_mac_input.value = mac
                manager.log(f"Thermometer MAC → {mac}")
            else:
                state.miflora_mac = mac
                state.miflora_has_data = False
                flora_mac_input.value = mac
                manager.log(f"Mi Flora MAC → {mac}")
            _save_cfg()
            update_ui()

        def save_macs(e):
            state.thermometer_mac = therm_mac_input.value.strip()
            state.miflora_mac     = flora_mac_input.value.strip()
            state.thermometer_has_data = False
            state.miflora_has_data = False
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

        # ── History Event Handlers ────────────────────────────────────────────────
        async def do_sync_therm_hist():
            mac = therm_mac_input.value.strip() or state.thermometer_mac
            await manager.sync_thermometer_history(mac)

        async def do_sync_flora_hist():
            mac = flora_mac_input.value.strip() or state.miflora_mac
            await manager.sync_miflora_history(mac)

        def do_export_csv(sensor_type):
            filepath = manager.export_history_csv(sensor_type)
            if filepath:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"📁 Εξαγωγή CSV επιτυχής: {os.path.basename(filepath)}"))
                page.snack_bar.open = True
                page.update()

        def do_export_json(sensor_type):
            filepath = manager.export_history_json(sensor_type)
            if filepath:
                page.snack_bar = ft.SnackBar(content=ft.Text(f"📁 Εξαγωγή JSON επιτυχής: {os.path.basename(filepath)}"))
                page.snack_bar.open = True
                page.update()

        # ── Final Layout with Page Navigation Bar ───────────────────────────────
        dashboard_view = ft.Column([
            ft.Row([therm_card, flora_card], spacing=16, wrap=True),
            ft.Divider(height=10, color="#1E293B"),
            ft.Row([setup_panel, log_panel], spacing=16, wrap=True)
        ], spacing=16)

        active_page_container = ft.Container(content=dashboard_view)

        def switch_tab(tab_name):
            if tab_name == "dashboard":
                active_page_container.content = dashboard_view
                btn_tab_dashboard.bgcolor = "#3B82F6"
                btn_tab_dashboard.color = "#FFFFFF"
                btn_tab_therm_hist.bgcolor = "#1E293B"
                btn_tab_therm_hist.color = "#94A3B8"
                btn_tab_flora_hist.bgcolor = "#1E293B"
                btn_tab_flora_hist.color = "#94A3B8"
            elif tab_name == "therm_hist":
                active_page_container.content = therm_history_panel
                btn_tab_dashboard.bgcolor = "#1E293B"
                btn_tab_dashboard.color = "#94A3B8"
                btn_tab_therm_hist.bgcolor = "#F0B429"
                btn_tab_therm_hist.color = "#FFFFFF"
                btn_tab_flora_hist.bgcolor = "#1E293B"
                btn_tab_flora_hist.color = "#94A3B8"
            elif tab_name == "flora_hist":
                active_page_container.content = flora_history_panel
                btn_tab_dashboard.bgcolor = "#1E293B"
                btn_tab_dashboard.color = "#94A3B8"
                btn_tab_therm_hist.bgcolor = "#1E293B"
                btn_tab_therm_hist.color = "#94A3B8"
                btn_tab_flora_hist.bgcolor = "#34D399"
                btn_tab_flora_hist.color = "#FFFFFF"
            safe_update()

        btn_tab_dashboard = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.DASHBOARD, size=16), ft.Text("📊 Ζωντανή Επισκόπηση", size=13, weight=ft.FontWeight.BOLD)]),
            bgcolor="#3B82F6", color="#FFFFFF", height=40,
            on_click=lambda e: switch_tab("dashboard")
        )
        btn_tab_therm_hist = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.THERMOSTAT, size=16), ft.Text("🌡️ Ιστορικό Θερμομέτρου", size=13, weight=ft.FontWeight.BOLD)]),
            bgcolor="#1E293B", color="#94A3B8", height=40,
            on_click=lambda e: switch_tab("therm_hist")
        )
        btn_tab_flora_hist = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.LOCAL_FLORIST, size=16), ft.Text("🌿 Ιστορικό Mi Flora", size=13, weight=ft.FontWeight.BOLD)]),
            bgcolor="#1E293B", color="#94A3B8", height=40,
            on_click=lambda e: switch_tab("flora_hist")
        )

        nav_bar = ft.Row([btn_tab_dashboard, btn_tab_therm_hist, btn_tab_flora_hist], spacing=10, wrap=True)

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
                    ft.Row([loop_switch, interval_dd, help_btn], spacing=12)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=10, color="#1E293B"),
                nav_bar,
                ft.Divider(height=10, color="#1E293B"),
                active_page_container
            ], spacing=14, scroll=ft.ScrollMode.AUTO)
        )

        try:
            import pyi_splash
            pyi_splash.close()
        except ImportError:
            pass

        # Auto-start monitoring if live_mode was active
        if config.get("live_mode", True):
            loop_switch.value = True
            threading.Timer(0.5, manager.start_monitoring).start()

    except Exception as err:
        print(f"CRITICAL ERROR in main: {err}")
        traceback.print_exc()
        try:
            page.add(ft.Text(f"Σφάλμα εφαρμογής: {err}", color="red", size=16))
            page.update()
        except Exception:
            pass


if __name__ == "__main__":
    ft.run(main)
