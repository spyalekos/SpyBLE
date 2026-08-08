# SpyBLE 📶 - Xiaomi BLE Sensor Dashboard

![SpyBLE Icon](src/assets/icon.png)

> **SpyBLE** είναι μια σύγχρονη desktop εφαρμογή (Python / Flet / Bleak) για τον ζωντανό έλεγχο και την παρακολούθηση αισθητήρων Bluetooth Low Energy (BLE) της Xiaomi (Θερμόμετρα LYWSD03MMC και Αισθητήρες Φυτών Mi Flora / VegTrug).

---

## 🌟 Χαρακτηριστικά (Features v1.1.0)

* 🚀 **Rapid Shooting Mode (Μέθοδος 2)**: Ταχύτατες συνεχείς ριπές κλήσεων GATT (κάθε 300ms) για άμεση λήψη αρχικών δεδομένων ακόμη και αν η συσκευή BLE βρίσκεται σε κατάσταση εξοικονόμησης ενέργειας.
* 📡 **Passive BLE Scanner (Μέθοδος 3)**: Αυτόματη μετάβαση σε συνεχή παθητική ακρόαση διαφημιστικών πακέτων (BLE Advertisements) για ακαριαία ενημέρωση θερμοκρασίας & υγρασίας (MiBeacon 0xFE95, ATC/PVVX 0x181A, BTHome 0xFCD2).
* 🔍 **Hardware MAC Resolution**: Αυτόματος εντοπισμός και αντιστοίχιση της εσωτερικής Hardware MAC διεύθυνσης από τα διαφημιστικά πακέτα payload, ξεπερνώντας τους περιορισμούς των Random OS Addresses στα Windows.
* 🌡️ **Θερμόμετρο LYWSD03MMC**:
  * Ζωντανή μέτρηση Θερμοκρασίας (°C) και Υγρασίας (%).
  * Ένδειξη Τάσης (V) και Ποσοστού Μπαταρίας (%).
* 🌿 **Αισθητήρας Mi Flora (HHCCJCY01)**:
  * Μέτρηση Υγρασίας Χώματος (%).
  * Μέτρηση Αγωγιμότητας / Λιπάσματος (µS/cm).
  * Μέτρηση Θερμοκρασίας (°C) και Φωτεινότητας (Lux).
  * Ένδειξη Μπαταρίας (%).
* ⏱️ **Ρυθμιζόμενος Βρόγχος 5s**: Επιλογή ρυθμού ανανέωσης 5, 10, 30, 60 ή 300 δευτερολέπτων.
* 📜 **Προσαρμοστικό UI με Μπάρα Κύλισης**: Αυτόματη κάθετη κύλιση (Auto Scrollbar) και responsive στοίχιση πάνελ για τέλεια προβολή σε οποιαδήποτε ανάλυση οθόνης.
* 💾 **Μόνιμη Αποθήκευση στο `spyBLE.settings`**: Αυτόματη αποθήκευση ρυθμίσεων και τελευταίων μετρήσεων με αυτόματη μετάβαση από το παλιό `config.json`.
* 🎨 **Έγχρωμη Κονσόλα Logs (Multi-color Console)**:
  * 🔴 Κόκκινο για σφάλματα & αποσυνδέσεις.
  * 🟢 Πράσινο για επιτυχείς αναγνώσεις.
  * 🔵 Γαλάζιο για καταστάσεις σύνδεσης & Rapid Shooting.
  * 🟡 Χρυσό για ολοκλήρωση σάρωσης & παθητική λήψη.

---

## 🚀 Εγκατάσταση & Εκτέλεση (Setup & Run)

### Προαπαιτούμενα
* Python 3.10+
* [uv](https://github.com/astral-sh/uv) (Package manager)

### Εκτέλεση από τον πηγαίο κώδικα
```bash
# Εγκατάσταση εξαρτήσεων
uv sync

# Εκτέλεση εφαρμογής
uv run python src/main.py
```

---

## 📦 Μεταγλώττιση σε Standalone Executable (.exe)

Για τη δημιουργία αυτόνομου εκτελέσιμου αρχείου Windows:

```bash
uv run pyinstaller SpyBLE.spec --clean --noconfirm
```

Το εκτελέσιμο θα δημιουργηθεί στη διαδρομή: `dist/SpyBLE.exe`

---

## 📄 Δομή Project

```
SpyBLE/
├── src/
│   ├── main.py            # Κύριο UI & Flet Layout (v1.1.0)
│   ├── ble_manager.py     # BLE Polling, Rapid Shooting & Passive Scanner
│   ├── config_manager.py  # spyBLE.settings Config & Persistent Readings
│   └── assets/            # Εικονίδια & Splash Screen (.png/.jpg/.ico)
├── SpyBLE.spec            # PyInstaller Specification
├── pyproject.toml         # Dependencies & Versioning (uv)
└── README.md              # Τεκμηρίωση Εφαρμογής
```

---

## 👤 Δημιουργός
Ανάπτυξη από **spyalekos**
