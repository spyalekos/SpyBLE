import sys
import subprocess

# Prevent command prompt window from popping up for subprocesses on Windows
if sys.platform == "win32":
    _original_popen = subprocess.Popen
    class PatchedPopen(_original_popen):
        def __init__(self, *args, **kwargs):
            creationflags = kwargs.get("creationflags", 0)
            kwargs["creationflags"] = creationflags | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            super().__init__(*args, **kwargs)
    subprocess.Popen = PatchedPopen

import os
import time
import math
import threading
import datetime
import shutil
import re
import gc
import asyncio
import yt_dlp
import yt_dlp.utils
import flet as ft
import flet_audio as fta
from pydub import AudioSegment
from pydub.effects import normalize

VERSION = "1.2.7"

vlc_available = False
vlc_player = None
try:
    import vlc
    _vlc_instance = vlc.Instance("--no-video", "--quiet")
    vlc_player = _vlc_instance.media_player_new()
    vlc_available = True
except Exception as e:
    pass

class TrackMetadata:
    def __init__(self, title, video_id, original_duration_ms, cropped_duration_ms, start_time_ms):
        self.title = title
        self.video_id = video_id
        self.original_duration_ms = original_duration_ms
        self.cropped_duration_ms = cropped_duration_ms
        self.start_time_ms = start_time_ms

def format_time(ms):
    if ms is None or ms < 0:
        return "00:00"
    seconds = int(ms / 1000)
    minutes = seconds // 60
    seconds = seconds % 60
    hours = minutes // 60
    minutes = minutes % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

def clean_words(title):
    # Normalize title: remove punctuation, lowercase, split into words
    title = title.lower()
    # Strip common video indicators
    title = re.sub(r'\(official\s+video\)', '', title)
    title = re.sub(r'\[official\s+video\]', '', title)
    title = re.sub(r'\(official\s+audio\)', '', title)
    title = re.sub(r'\[official\s+audio\]', '', title)
    title = re.sub(r'\(lyrics\)', '', title)
    title = re.sub(r'\[lyrics\]', '', title)
    title = re.sub(r'\(hq\)', '', title)
    title = re.sub(r'\[hq\]', '', title)
    words = re.findall(r'\w+', title)
    return set(words)

def is_similar_title(words1, words2, threshold=0.8):
    if not words1 or not words2:
        return False
    intersection = words1.intersection(words2)
    max_size = max(len(words1), len(words2))
    if max_size == 0:
        return False
    return len(intersection) / max_size >= threshold

LOCALIZATION = {
    "en": {
        "title": "SpyMixer 🎵 - YouTube Playlist Crossfade Mixer",
        "app_title": "SpyMixer",
        "app_subtitle": "YouTube Playlist Crossfade Generator",
        "config_title": "Mix Configuration",
        "keywords_label": "Enter keywords (comma separated):",
        "keywords_hint": "e.g. greek classic rock, synthwave 80s",
        "songs_label": "Songs per keyword",
        "songs_slider_label": "{value} songs per keyword",
        "duration_label": "Max song duration",
        "duration_slider_label": "{value} minutes max per song",
        "crossfade_label": "Crossfade duration",
        "crossfade_slider_label": "{value} seconds crossfade",
        "normalize_label": "Normalize Volume",
        "clean_label": "Clean Download Cache",
        "generate_btn": "GENERATE MIX 🚀",
        "processing_btn": "PROCESSING... ⏳",
        "ready_to_mix": "Ready to mix",
        "logs_label": "Log Output",
        "duplicates_btn": "Duplicates",
        "no_active_mix_title": "No Active Mix",
        "no_active_mix_sub": "Specify keywords and generate a mix to start listening",
        "playlist_header": "Mix Playlist Timeline",
        "volume_tooltip": "Mute / Unmute",
        "play_tooltip": "Play / Pause",
        "prev_tooltip": "Previous Track",
        "next_tooltip": "Next Track",
        "dup_dialog_title": "Rejected Duplicates",
        "dup_col_song": "Rejected Song",
        "dup_col_reason": "Reason / Kept Version",
        "dup_close": "Close",
        "search_phase": "Phase 1/4: Searching YouTube...",
        "download_phase": "Phase 2/4: Downloading songs...",
        "download_song_phase": "Phase 2/4: Downloading song {current} of {total}...",
        "process_phase": "Phase 3/4: Processing and mixing audio...",
        "concat_phase": "Phase 4/4: Concatenating chunks into final MP3...",
        "cleanup_phase": "Cleaning up temporary cache...",
        "success_phase": "Mix generated successfully! Ready to play.",
        "fail_search": "Job failed: No videos found.",
        "fail_download": "Job failed: Download failure.",
        "fail_process": "Job failed: Audio processing failure.",
        "fail_export": "Job failed: Export failure.",
        "duration_prefix": "Duration",
        "songs_suffix": "songs",
        "curation_title": "Crate Curation - Preview & Approve Songs",
        "curation_subtitle": "Listen to and approve/exclude songs before generating the final mix",
        "curation_exclude": "Exclude from mix",
        "curation_start_mix": "START MIX 🚀",
        "curation_cancel": "Cancel Mix ❌",
        "curation_no_approved": "Validation Error: You must keep at least one song approved!",
        "open_mix_btn": "OPEN MIX 📂",
        "import_beatlist_btn": "IMPORT BEATS 🎧",
        "save_mix_tooltip": "Export mix as a single .spymix file (contains audio & metadata)",
        "edit_mix_tooltip": "Edit current mix playlist in BeatList Editor",
        "beatlist_action_title": "Choose Action",
        "beatlist_action_sub": "What would you like to do with the playlist '{name}'?",
        "beatlist_btn_mix": "Start Mixing 🚀",
        "beatlist_btn_edit": "Edit Playlist 📝",
        "beatlist_editor_title": "BeatList Editor 📝",
        "beatlist_editor_subtitle": "Edit the track list before mixing or saving",
        "beatlist_add_url_btn": "Add URL",
        "beatlist_url_hint": "Paste YouTube URL...",
        "beatlist_search_hint": "Search YouTube...",
        "beatlist_search_btn": "Search",
        "beatlist_save_btn": "SAVE 💾",
        "beatlist_delete_btn": "DELETE 🗑️",
        "beatlist_close_btn": "Close ❌",
        "beatlist_add_btn": "Add",
        "editor_tracks_label": "Tracks in Playlist:",
        "editor_deleted_success": "File '{path}' deleted successfully.",
        "editor_cleared_success": "Editor tracklist cleared.",
        "editor_by_artist": "By Artist 👤",
        "editor_by_song": "By Song 🎵",
        "editor_shuffle": "Shuffle 🔀",
        "editor_tooltip_play": "Play Preview",
        "editor_tooltip_delete": "Delete Track",
        "editor_tooltip_add": "Add to playlist",
        "editor_no_results": "No results found.",
        "editor_err_empty": "Cannot save an empty playlist.",
        "editor_saved_success": "BeatList saved successfully to {path}!",
        "editor_err_save": "Failed to save BeatList: {err}",
        "editor_track_exists": "Track is already in the list",
        "editor_err_retrieve": "Could not retrieve track info. Check URL.",
        "editor_err_add_url": "Failed to add URL: {err}",
        "editor_err_search": "Search failed: {err}",
        "editor_log_sorted_artist": "Sorted playlist by Artist name",
        "editor_log_sorted_song": "Sorted playlist by Song title",
        "editor_log_shuffled": "Shuffled playlist tracks randomly",
        "editor_log_fail_preview": "Failed to play preview: {err}",
        "editor_log_mix_editor": "Starting mix from Editor playlist '{name}' with {count} tracks...",
        "help_title": "Help & Instructions 📋",
        "help_close": "Close",
        "help_tooltip": "Help & Instructions",
        "help_text": """# SpyMixer Help & Instructions 🎵

SpyMixer helps you search, download, and crossfade YouTube audio tracks into a seamless playlist.

### How to Use:
1. **Enter Keywords**: Input search terms (e.g. `greek classic rock, synthwave 80s`) separated by commas in the configuration panel.
2. **Configure Settings**:
   * **Songs per keyword**: The number of matching songs to download.
   * **Max song duration**: The maximum time to play from each song.
   * **Crossfade duration**: The overlap transition time between songs.
   * **Normalize Volume**: Keeps track levels consistent.
   * **Clean Download Cache**: Automatically frees disk space after exporting.
3. **Crate Curation**: Click **GENERATE MIX 🚀**. A dialog will display the found tracks. You can preview (play), approve, or exclude tracks before generating.
4. **Mix & Play**: Once the mix is ready, it will load into the player, spin the vinyl, and play!

### Special Features:
* 📂 **Open Mix**: Load previously saved mixes (`.xsp` metadata or packaged `.spymix` archives) to replay them instantly.
* 💾 **Save Mix**: Export the currently loaded mix as a single `.spymix` package (containing both audio and metadata) using the save button in the player.
* 🎧 **Import Beats**: Import `.beatlist` playlists from the **SpyBeats** app and mix them.
* 🌐 **Language Toggle**: Switch between Greek and English.

---
Developed by: **[spyalekos](https://github.com/spyalekos)**
"""
    },
    "el": {
        "title": "SpyMixer 🎵 - Μιξάρισμα Λιστών YouTube με Crossfade",
        "app_title": "SpyMixer",
        "app_subtitle": "Δημιουργία Μίξης με Crossfade από το YouTube",
        "config_title": "Ρυθμίσεις Μίξης",
        "keywords_label": "Εισάγετε λέξεις-κλειδιά (διαχωρισμένες με κόμμα):",
        "keywords_hint": "π.χ. greek classic rock, synthwave 80s",
        "songs_label": "Τραγούδια ανά λέξη-κλειδί",
        "songs_slider_label": "{value} τραγούδια ανά λέξη-κλειδί",
        "duration_label": "Μέγιστη διάρκεια τραγουδιού",
        "duration_slider_label": "{value} λεπτά μέγιστο ανά τραγούδι",
        "crossfade_label": "Διάρκεια crossfade",
        "crossfade_slider_label": "{value} δευτερόλεπτα crossfade",
        "normalize_label": "Κανονικοποίηση έντασης",
        "clean_label": "Καθαρισμός προσωρινής μνήμης",
        "generate_btn": "ΔΗΜΙΟΥΡΓΙΑ ΜΙΞΗΣ 🚀",
        "processing_btn": "ΕΠΕΞΕΡΓΑΣΙΑ... ⏳",
        "ready_to_mix": "Έτοιμο για μίξη",
        "logs_label": "Έξοδος Καταγραφής (Logs)",
        "duplicates_btn": "Διπλότυπα",
        "no_active_mix_title": "Καμία Ενεργή Μίξη",
        "no_active_mix_sub": "Ορίστε λέξεις-κλειδιά και δημιουργήστε μία μίξη για να ξεκινήσετε την ακρόαση",
        "playlist_header": "Χρονολόγιο Λίστας Αναπαραγωγής",
        "volume_tooltip": "Σίγαση / Κατάργηση Σίγασης",
        "play_tooltip": "Αναπαραγωγή / Παύση",
        "prev_tooltip": "Προηγούμενο Τραγούδι",
        "next_tooltip": "Επόμενο Τραγούδι",
        "dup_dialog_title": "Απορριφθέντα Διπλότυπα",
        "dup_col_song": "Απορριφθέν Τραγούδι",
        "dup_col_reason": "Αιτία / Έκδοση που Κρατήθηκε",
        "dup_close": "Κλείσιμο",
        "search_phase": "Φάση 1/4: Αναζήτηση στο YouTube...",
        "download_phase": "Φάση 2/4: Λήψη τραγουδιών...",
        "download_song_phase": "Φάση 2/4: Λήψη τραγουδιού {current} από {total}...",
        "process_phase": "Φάση 3/4: Επεξεργασία και μίξη ήχου...",
        "concat_phase": "Φάση 4/4: Συνένωση κομματιών στο τελικό MP3...",
        "cleanup_phase": "Καθαρισμός προσωρινής μνήμης...",
        "success_phase": "Η μίξη δημιουργήθηκε επιτυχώς! Έτοιμοι για αναπαραγωγή.",
        "fail_search": "Η εργασία απέτυχε: Δεν βρέθηκαν βίντεο.",
        "fail_download": "Η εργασία απέτυχε: Αποτυχία λήψης.",
        "fail_process": "Η εργασία απέτυχε: Αποτυχία επεξεργασίας ήχου.",
        "fail_export": "Η εργασία απέτυχε: Αποτυχία εξαγωγής.",
        "duration_prefix": "Διάρκεια",
        "songs_suffix": "τραγούδια",
        "curation_title": "Επιλογή Κομματιών - Προεπισκόπηση & Έγκριση",
        "curation_subtitle": "Ακούστε και εγκρίνετε/απορρίψτε τραγούδια πριν τη δημιουργία της τελικής μίξης",
        "curation_exclude": "Απόρριψη από τη μίξη",
        "curation_start_mix": "ΕΝΑΡΞΗ ΜΙΞΗΣ 🚀",
        "curation_cancel": "Ακύρωση ❌",
        "curation_no_approved": "Σφάλμα: Πρέπει να εγκρίνετε τουλάχιστον ένα τραγούδι!",
        "open_mix_btn": "ΑΝΟΙΓΜΑ ΜΙΞΗΣ 📂",
        "import_beatlist_btn": "ΕΙΣΑΓΩΓΗ BEATS 🎧",
        "save_mix_tooltip": "Εξαγωγή μίξης σε ένα ενιαίο αρχείο .spymix (περιέχει ήχο & μεταδεδομένα)",
        "edit_mix_tooltip": "Επεξεργασία της τρέχουσας λίστας στον BeatList Editor",
        "beatlist_action_title": "Επιλογή Ενέργειας",
        "beatlist_action_sub": "Τι θέλετε να κάνετε με τη λίστα '{name}';",
        "beatlist_btn_mix": "Έναρξη Μίξης 🚀",
        "beatlist_btn_edit": "Επεξεργασία 📝",
        "beatlist_editor_title": "Επεξεργαστής BeatList 📝",
        "beatlist_editor_subtitle": "Επεξεργαστείτε τη λίστα τραγουδιών πριν τη μίξη ή την αποθήκευση",
        "beatlist_add_url_btn": "Προσθήκη URL",
        "beatlist_url_hint": "Επικολλήστε YouTube URL...",
        "beatlist_search_hint": "Αναζήτηση στο YouTube...",
        "beatlist_search_btn": "Αναζήτηση",
        "beatlist_save_btn": "ΑΠΟΘΗΚΕΥΣΗ 💾",
        "beatlist_delete_btn": "ΔΙΑΓΡΑΦΗ 🗑️",
        "beatlist_close_btn": "Κλείσιμο ❌",
        "beatlist_add_btn": "Προσθήκη",
        "editor_tracks_label": "Κομμάτια στη Λίστα:",
        "editor_deleted_success": "Το αρχείο '{path}' διαγράφηκε με επιτυχία.",
        "editor_cleared_success": "Η λίστα επεξεργασίας καθαρίστηκε.",
        "editor_by_artist": "Ανά Καλλιτέχνη 👤",
        "editor_by_song": "Ανά Τραγούδι 🎵",
        "editor_shuffle": "Ανακάτεμα 🔀",
        "editor_tooltip_play": "Προεπισκόπηση",
        "editor_tooltip_delete": "Διαγραφή Κομματιού",
        "editor_tooltip_add": "Προσθήκη στη λίστα",
        "editor_no_results": "Δεν βρέθηκαν αποτελέσματα.",
        "editor_err_empty": "Δεν μπορεί να αποθηκευτεί άδεια λίστα.",
        "editor_saved_success": "Η BeatList αποθηκεύτηκε επιτυχώς στο {path}!",
        "editor_err_save": "Αποτυχία αποθήκευσης BeatList: {err}",
        "editor_track_exists": "Το κομμάτι είναι ήδη στη λίστα",
        "editor_err_retrieve": "Αδυναμία ανάκτησης στοιχείων. Ελέγξτε το URL.",
        "editor_err_add_url": "Αποτυχία προσθήκης URL: {err}",
        "editor_err_search": "Η αναζήτηση απέτυχε: {err}",
        "editor_log_sorted_artist": "Η λίστα ταξινομήθηκε κατά όνομα καλλιτέχνη",
        "editor_log_sorted_song": "Η λίστα ταξινομήθηκε κατά τίτλο τραγουδιού",
        "editor_log_shuffled": "Τα κομμάτια της λίστας ανακατεύτηκαν τυχαία",
        "editor_log_fail_preview": "Αποτυχία αναπαραγωγής προεπισκόπησης: {err}",
        "editor_log_mix_editor": "Έναρξη μίξης από τον Editor για τη λίστα '{name}' με {count} κομμάτια...",
        "help_title": "Βοήθεια & Οδηγίες 📋",
        "help_close": "Κλείσιμο",
        "help_tooltip": "Βοήθεια & Οδηγίες",
        "help_text": """# SpyMixer Βοήθεια & Οδηγίες 🎵

Το SpyMixer σας επιτρέπει να αναζητάτε, να κατεβάζετε και να μιξάρετε τραγούδια από το YouTube με εφέ crossfade.

### Τρόπος Χρήσης:
1. **Λέξεις-Κλειδιά**: Εισάγετε όρους αναζήτησης (π.χ. `greek rock, synthwave 80s`) διαχωρισμένους με κόμμα.
2. **Ρυθμίσεις**:
   * **Τραγούδια ανά λέξη-κλειδί**: Πόσα τραγούδια θα αναζητηθούν ανά όρο.
   * **Μέγιστη διάρκεια**: Το μέγιστο όριο αναπαραγωγής ανά τραγούδι.
   * **Διάρκεια Crossfade**: Ο χρόνος επικάλυψης (μίξης) μεταξύ των τραγουδιών.
   * **Κανονικοποίηση έντασης**: Διατηρεί σταθερή την ένταση σε όλα τα κομμάτια.
   * **Καθαρισμός cache**: Διαγράφει αυτόματα τα προσωρινά αρχεία μετά τη μίξη.
3. **Επιλογή Κομματιών (Curation)**: Πατήστε **ΔΗΜΙΟΥΡΓΙΑ ΜΙΞΗΣ 🚀**. Θα εμφανιστεί λίστα με τα τραγούδια. Μπορείτε να ακούσετε προεπισκόπηση, να εγκρίνετε ή να απορρίψετε κομμάτια.
4. **Μίξη & Αναπαραγωγή**: Μετά την ολοκλήρωση, η μίξη φορτώνεται στον player και ξεκινά η αναπαραγωγή.

### Επιπλέον δυνατότητες:
* 📂 **Άνοιγμα Μίξης**: Φορτώστε προηγούμενες μίξεις (αρχεία `.xsp` ή πακεταρισμένα `.spymix`) για άμεση αναπαραγωγή.
* 💾 **Εξαγωγή Μίξης**: Αποθηκεύστε την τρέχουσα μίξη ως ενιαίο αρχείο `.spymix` (ήχος & δεδομένα) χρησιμοποιώντας το κουμπί αποθήκευσης στον player.
* 🎧 **Εισαγωγή Beats**: Εισάγετε λίστες αναπαραγωγής `.beatlist` από την εφαρμογή **SpyBeats** για μίξη.
* 🌐 **Αλλαγή Γλώσσας**: Εναλλαγή μεταξύ Ελληνικών και Αγγλικών.

---
Δημιουργός: **[spyalekos](https://github.com/spyalekos)**
"""
    }
}

def main(page: ft.Page):
    # Ensure assets directory and dummy initialization file exist
    import os
    import datetime
    from pydub import AudioSegment
    os.makedirs("assets", exist_ok=True)
    
    # Initialize/clear debug log
    with open("assets/startup_debug.txt", "w", encoding="utf-8") as f:
        f.write(f"=== Startup Debug Log - {datetime.datetime.now()} ===\n")
        
    def debug_log(step_name):
        try:
            with open("assets/startup_debug.txt", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S.%f')}] {step_name}\n")
        except:
            pass
            
    debug_log("Step 1: main() entered")
    
    def cleanup_temp_extracted():
        def run_cleanup():
            temp_dir = os.path.join("assets", "temp_extracted")
            if os.path.exists(temp_dir):
                try:
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except:
                    pass
        import threading
        threading.Thread(target=run_cleanup, daemon=True).start()
                
    cleanup_temp_extracted()
    debug_log("Step 2: cleanup_temp_extracted called")

    if not os.path.exists("assets/test_mix.mp3"):
        try:
            AudioSegment.silent(duration=1000).export("assets/test_mix.mp3", format="mp3")
        except:
            pass
    debug_log("Step 3: test_mix.mp3 checked/created")

    # Page setup
    page.title = "SpyMixer 🎵 - YouTube Playlist Crossfade Mixer"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0B0B0E"
    page.window.width = 1200
    page.window.height = 850
    page.window.resizable = True
    page.padding = 20
    
    main_thread_id = threading.get_ident()
    def safe_update():
        if threading.get_ident() == main_thread_id:
            page.update()
        else:
            async def update_coro():
                page.update()
            page.run_task(update_coro)
    
    # Custom Fonts
    page.fonts = {
        "Outfit": "https://github.com/google/fonts/raw/main/ofl/outfit/Outfit-VariableFont_wght.ttf",
        "Consolas": "https://fonts.cdnfonts.com/s/14897/Consolas.woff"
    }
    page.theme = ft.Theme(font_family="Outfit")
    
    # State variables
    app_state = {
        "is_processing": False,
        "is_playing": False,
        "current_position_ms": 0,
        "total_duration_ms": 0,
        "tracks": [],            # List of TrackMetadata
        "rejected_tracks": [],    # List of (title, reason, matching_title)
        "active_track_idx": -1,
        "audio_path": "",
        "downloaded_files": [],
        "is_dragging_slider": False,
        "lang": "el"
    }
    
    # Load last search query
    last_query = ""
    if os.path.exists("assets/last_query.txt"):
        try:
            with open("assets/last_query.txt", "r", encoding="utf-8") as f:
                last_query = f.read().strip()
        except:
            pass

    debug_log("Step 5: State variables loaded")

    # References to UI elements
    keywords_input = ft.TextField(
        value=last_query,
        label="Keywords (comma separated)",
        hint_text="e.g. greek classic rock, synthwave 80s",
        bgcolor="#141419",
        border_color="#3F3F5F",
        focused_border_color="#8E2DE2",
        focused_color=ft.Colors.WHITE,
        border_radius=10,
        expand=True,
    )
    
    songs_slider = ft.Slider(
        min=1, max=25, value=25, divisions=24,
        label="{value} songs per keyword",
        active_color="#00CEC9",
        inactive_color="#2E2E3A"
    )
    
    duration_slider = ft.Slider(
        min=1, max=5, value=3, divisions=8,
        label="{value} minutes max per song",
        active_color="#8E2DE2",
        inactive_color="#2E2E3A"
    )
    
    crossfade_slider = ft.Slider(
        min=0, max=15, value=5, divisions=15,
        label="{value} seconds crossfade",
        active_color="#FF7675",
        inactive_color="#2E2E3A"
    )
    
    normalize_checkbox = ft.Checkbox(
        label="Normalize Volume",
        value=True,
        active_color="#8E2DE2"
    )
    
    cleanup_checkbox = ft.Checkbox(
        label="Clean Download Cache",
        value=True,
        active_color="#00CEC9"
    )
    
    generate_btn = ft.Button(
        content=ft.Container(
            content=ft.Text("GENERATE MIX 🚀", size=16, weight="bold", color=ft.Colors.WHITE),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.Padding.symmetric(vertical=15),
        ),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=10),
            bgcolor=ft.Colors.TRANSPARENT,
            shadow_color="#8E2DE2",
            elevation=5
        ),
        expand=True,
    )
    
    open_mix_btn = ft.Button(
        content=ft.Container(
            content=ft.Text("ΑΝΟΙΓΜΑ ΜΙΞ 📂", size=14, weight="bold", color=ft.Colors.RED),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.Padding.symmetric(vertical=15),
        ),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=10),
            bgcolor=ft.Colors.TRANSPARENT,
            shadow_color="#00CEC9",
            elevation=5
        ),
        expand=True,
    )
    
    import_beatlist_btn = ft.Button(
        content=ft.Container(
            content=ft.Text("ΕΙΣΑΓΩΓΗ BEATS 🎧", size=15, weight="bold", color=ft.Colors.WHITE),
            alignment=ft.Alignment(0, 0),
            padding=ft.padding.Padding.symmetric(vertical=15),
        ),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=10),
            bgcolor=ft.Colors.TRANSPARENT,
            shadow_color="#E84393",
            elevation=5
        ),
        expand=True,
    )
    
    # Progress indicator
    status_label = ft.Text("Ready to mix", color="#8F8F9F", size=14)
    progress_bar = ft.ProgressBar(value=0.0, color="#8E2DE2", bgcolor="#2E2E3A", height=6, border_radius=3)
    
    # Log Console
    log_list = ft.ListView(expand=True, spacing=4, auto_scroll=True)
    log_container = ft.Container(
        content=log_list,
        bgcolor="#070709",
        border=ft.Border.all(1, "#252535"),
        border_radius=10,
        padding=12,
        height=200,
        clip_behavior="antiAlias"
    )
    
    # Player UI Elements
    vinyl_img = ft.Image(
        src="/vinyl.png",
        width=180,
        height=180,
        border_radius=90,
        fit="cover",
        rotate=ft.Rotate(angle=0),
        animate_rotation=ft.Animation(3000, "linear")
    )
    
    vinyl_container = ft.Container(
        content=vinyl_img,
        alignment=ft.Alignment(0, 0),
        padding=10,
        shape=ft.BoxShape.CIRCLE,
        border=ft.Border.all(4, "#8E2DE2"),
        bgcolor="#101014",
        width=200,
        height=200,
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=15,
            color="#8E2DE2",
            offset=ft.Offset(0, 0)
        )
    )
    
    play_pause_btn = ft.IconButton(
        icon=ft.Icons.PLAY_CIRCLE_FILLED,
        icon_size=64,
        icon_color="#00CEC9",
        tooltip="Play/Pause",
        width=76,
        height=76
    )
    
    prev_btn = ft.IconButton(
        icon=ft.Icons.SKIP_PREVIOUS_ROUNDED,
        icon_size=36,
        icon_color=ft.Colors.WHITE,
        tooltip="Previous Track",
        width=48,
        height=48
    )
    
    next_btn = ft.IconButton(
        icon=ft.Icons.SKIP_NEXT_ROUNDED,
        icon_size=36,
        icon_color=ft.Colors.WHITE,
        tooltip="Next Track",
        width=48,
        height=48
    )
    
    current_time_text = ft.Text("00:00", size=13, color="#8F8F9F", weight="w500")
    total_time_text = ft.Text("00:00", size=13, color="#8F8F9F", weight="w500")
    
    player_slider = ft.Slider(
        min=0, max=100, value=0,
        active_color="#00CEC9",
        inactive_color="#2E2E3A",
        expand=True
    )
    
    volume_icon = ft.IconButton(
        icon=ft.Icons.VOLUME_UP_ROUNDED,
        icon_size=20,
        icon_color="#8F8F9F",
    )
    
    volume_slider = ft.Slider(
        min=0, max=100, value=80,
        active_color="#8E2DE2",
        inactive_color="#2E2E3A",
        width=100,
    )
    
    player_mix_title = ft.Text("No mix loaded", size=18, weight="bold", color=ft.Colors.WHITE)
    player_mix_subtitle = ft.Text("Enter keywords and hit generate", size=13, color="#8F8F9F")
    
    playlist_list = ft.ListView(expand=True, spacing=6)
    
    # Dialog for showing duplicates
    duplicates_list_view = ft.ListView(expand=True, spacing=6)
    
    def close_dialog(e):
        duplicates_dialog.open = False
        safe_update()
        
    dup_dialog_title_text = ft.Text("Rejected Duplicates")
    dup_dialog_close_btn = ft.TextButton("Close", on_click=close_dialog)
    
    duplicates_dialog = ft.AlertDialog(
        title=dup_dialog_title_text,
        content=ft.Container(
            width=500,
            height=300,
            content=duplicates_list_view
        ),
        actions=[
            dup_dialog_close_btn
        ]
    )
    page.dialog = duplicates_dialog
    
    # Curation Dialog variables & functions
    curation_done_event = threading.Event()
    curation_canceled = False
    
    curation_list_view = ft.ListView(expand=True, spacing=10)
    curation_title_text = ft.Text("Select Songs for your Mix", size=20, weight="bold")
    curation_subtitle_text = ft.Text("Preview and approve songs before generating the mix", size=13, color="#8F8F9F")
    
    async def proceed_curation_click(e):
        approved_count = len(app_state["curation_entries"]) - len(app_state["excluded_video_ids"])
        if approved_count == 0:
            lang = app_state["lang"]
            log(LOCALIZATION[lang]["curation_no_approved"], "error")
            return
        curation_done_event.set()
        
    async def cancel_curation_click(e):
        nonlocal curation_canceled
        curation_canceled = True
        curation_done_event.set()
        
    curation_proceed_text = ft.Text("START MIXING 🚀", size=14, weight="bold", color=ft.Colors.WHITE)
    curation_proceed_btn = ft.Button(
        content=curation_proceed_text,
        on_click=proceed_curation_click,
        style=ft.ButtonStyle(
            bgcolor="#00CEC9",
            color=ft.Colors.WHITE,
        )
    )
    
    curation_cancel_text = ft.Text("Cancel Mix ❌", color="#FF7675", weight="bold")
    curation_cancel_btn = ft.TextButton(
        content=curation_cancel_text,
        on_click=cancel_curation_click,
    )
    
    curation_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Column(
            [
                curation_title_text,
                curation_subtitle_text
            ],
            spacing=4
        ),
        content=ft.Container(
            width=650,
            height=450,
            content=curation_list_view,
            padding=ft.padding.Padding.symmetric(vertical=10)
        ),
        actions=[
            curation_cancel_btn,
            curation_proceed_btn
        ],
        actions_alignment="end"
    )
    page.overlay.append(curation_dialog)

    # ─────────────────────────── BEATLIST EDITOR ─────────────────────────────
    editor_title_text = ft.Text("BeatList Editor 📝", size=20, weight="bold")
    editor_subtitle_text = ft.Text("Edit the track list before mixing or saving", size=13, color="#8F8F9F")
    
    editor_url_field = ft.TextField(
        hint_text="Paste YouTube URL...",
        expand=True,
        text_size=13,
        height=40,
        border_color="#3E2B5C",
        focused_border_color="#00CEC9"
    )
    
    async def add_url_to_editor_list(e):
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        url = editor_url_field.value.strip()
        if not url:
            return
        
        editor_url_field.disabled = True
        editor_url_add_btn.disabled = True
        editor_url_add_btn.icon = ft.Icons.HOURGLASS_EMPTY_ROUNDED
        page.update()
        
        loop = asyncio.get_event_loop()
        try:
            def extract():
                ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'skip_download': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return {
                        "id": info.get("id"),
                        "title": info.get("title") or "Unknown Title",
                        "duration": info.get("duration") or 0
                    }
            info = await loop.run_in_executor(None, extract)
            if info and info["id"]:
                if any(t_item["id"] == info["id"] for t_item in app_state.setdefault("editor_tracks", [])):
                    log(t["editor_track_exists"], "warning")
                else:
                    app_state.setdefault("editor_tracks", []).append(info)
                    populate_editor_list()
                    editor_url_field.value = ""
            else:
                log(t["editor_err_retrieve"], "error")
        except Exception as ex:
            log(t["editor_err_add_url"].format(err=str(ex)), "error")
        finally:
            editor_url_field.disabled = False
            editor_url_add_btn.disabled = False
            editor_url_add_btn.icon = ft.Icons.ADD_LINK_ROUNDED
            page.update()

    editor_url_add_btn = ft.IconButton(
        icon=ft.Icons.ADD_LINK_ROUNDED,
        icon_color="#00CEC9",
        on_click=add_url_to_editor_list
    )
    
    editor_search_field = ft.TextField(
        hint_text="Search YouTube...",
        expand=True,
        text_size=13,
        height=40,
        border_color="#3E2B5C",
        focused_border_color="#E84393"
    )
    
    async def search_youtube_for_editor(e):
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        query = editor_search_field.value.strip()
        if not query:
            return
        
        editor_search_field.disabled = True
        editor_search_btn.disabled = True
        editor_search_btn.icon = ft.Icons.HOURGLASS_EMPTY_ROUNDED
        editor_search_results.controls.clear()
        editor_search_results_container.visible = True
        editor_search_results.controls.append(ft.ProgressRing(width=20, height=20, color="#E84393"))
        page.update()
        
        loop = asyncio.get_event_loop()
        try:
            def search():
                ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'skip_download': True, 'extract_flat': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    res = ydl.extract_info(f"ytsearch5:{query}", download=False)
                    return res.get('entries', [])
            
            entries = await loop.run_in_executor(None, search)
            editor_search_results.controls.clear()
            
            if not entries:
                editor_search_results.controls.append(ft.Text(t["editor_no_results"], size=12, color="#8F8F9F"))
            else:
                for entry in entries:
                    v_id = entry.get('id')
                    title = entry.get('title')
                    duration = entry.get('duration')
                    if not v_id or not title:
                        continue
                    
                    duration_str = format_time(duration * 1000) if duration else "00:00"
                    
                    add_btn = ft.IconButton(
                        icon=ft.Icons.ADD_ROUNDED,
                        icon_color="#00CEC9",
                        icon_size=20,
                        tooltip=t["editor_tooltip_add"]
                    )
                    
                    def make_add_handler(item):
                        def handler(e_add):
                            if any(t_item["id"] == item["id"] for t_item in app_state.setdefault("editor_tracks", [])):
                                log(t["editor_track_exists"], "warning")
                            else:
                                app_state.setdefault("editor_tracks", []).append({
                                    "id": item["id"],
                                    "title": item["title"],
                                    "duration": item["duration"] or 0
                                })
                                populate_editor_list()
                                page.update()
                        return handler
                        
                    add_btn.on_click = make_add_handler({"id": v_id, "title": title, "duration": duration})
                    
                    editor_search_results.controls.append(
                        ft.Row([
                            add_btn,
                            ft.Text(title, size=12, weight="bold", color=ft.Colors.WHITE, expand=True, max_lines=1, overflow="ellipsis"),
                            ft.Text(duration_str, size=11, color="#8F8F9F")
                        ], alignment="spaceBetween", vertical_alignment="center")
                    )
        except Exception as ex:
            err_msg = t["editor_err_search"].format(err=str(ex))
            log(err_msg, "error")
            editor_search_results.controls.clear()
            editor_search_results.controls.append(ft.Text(err_msg, size=12, color=ft.Colors.RED_400))
        finally:
            editor_search_field.disabled = False
            editor_search_btn.disabled = False
            editor_search_btn.icon = ft.Icons.SEARCH_ROUNDED
            page.update()

    editor_search_btn = ft.IconButton(
        icon=ft.Icons.SEARCH_ROUNDED,
        icon_color="#E84393",
        on_click=search_youtube_for_editor
    )
    
    editor_search_results = ft.Column(spacing=5, scroll=ft.ScrollMode.AUTO)
    editor_search_results_container = ft.Container(
        content=editor_search_results,
        visible=False,
        bgcolor="#13101F",
        border_radius=10,
        padding=10,
        border=ft.Border.all(1, "#3E2B5C"),
        height=120,
    )
    
    def editor_reorder_handler(e):
        old_idx = int(e.old_index)
        new_idx = int(e.new_index)
        
        if old_idx < new_idx:
            new_idx -= 1
            
        if old_idx < 0 or old_idx >= len(app_state.get("editor_tracks", [])):
            return
        if new_idx < 0 or new_idx >= len(app_state.get("editor_tracks", [])):
            return
            
        track = app_state["editor_tracks"].pop(old_idx)
        app_state["editor_tracks"].insert(new_idx, track)
        
        populate_editor_list()
        page.update()

    editor_tracks_view = ft.ReorderableListView(expand=True, spacing=6, on_reorder=editor_reorder_handler)
    
    def make_editor_preview_handler(track, btn):
        async def handler(e):
            video_id = track['id']
            
            # VLC-based playing/toggling logic
            if vlc_available:
                if app_state.get("previewing_video_id") == video_id and vlc_player.is_playing():
                    vlc_player.pause()
                    app_state["is_playing"] = False
                    populate_editor_list()
                    page.update()
                    return
                
                # Stop VLC or Flet player from playing anything else
                if vlc_player.is_playing():
                    vlc_player.stop()
                await audio_player.pause()
                
                # Set state to loading
                app_state["previewing_video_id"] = video_id
                app_state["is_playing"] = False
                app_state["is_loading_preview"] = True
                populate_editor_list()
                page.update()
                
                cached_url = app_state.get("curation_stream_urls", {}).get(video_id)
                if cached_url:
                    app_state["is_loading_preview"] = False
                    app_state["is_playing"] = True
                    vlc_player.set_mrl(cached_url)
                    vlc_player.play()
                    populate_editor_list()
                    page.update()
                    return
                
                loop = asyncio.get_event_loop()
                try:
                    def extract():
                        ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
                        url = video_id if video_id.startswith("http") else f"https://www.youtube.com/watch?v={video_id}"
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            return info.get('url')
                    stream_url = await loop.run_in_executor(None, extract)
                    if stream_url:
                        app_state.setdefault("curation_stream_urls", {})[video_id] = stream_url
                        app_state["previewing_video_id"] = video_id
                        app_state["is_loading_preview"] = False
                        app_state["is_playing"] = True
                        vlc_player.set_mrl(stream_url)
                        vlc_player.play()
                except Exception as ex:
                    lang = app_state["lang"]
                    t = LOCALIZATION[lang]
                    log(t["editor_log_fail_preview"].format(err=str(ex)), "error")
                    app_state["is_loading_preview"] = False
                    app_state["is_playing"] = False
                populate_editor_list()
                page.update()
                return

            # Fallback Flet-based playing/toggling logic
            if app_state.get("previewing_video_id") == video_id and app_state.get("is_playing"):
                await audio_player.pause()
                app_state["is_playing"] = False
                populate_editor_list()
                page.update()
                return
                
            await audio_player.pause()
            
            # Set state to loading
            app_state["previewing_video_id"] = video_id
            app_state["is_playing"] = False
            app_state["is_loading_preview"] = True
            populate_editor_list()
            page.update()
            
            cached_url = app_state.get("curation_stream_urls", {}).get(video_id)
            if cached_url:
                app_state["is_loading_preview"] = False
                app_state["is_playing"] = True
                audio_player.src = cached_url
                audio_player.update()
                await audio_player.play()
                populate_editor_list()
                page.update()
                return
                
            loop = asyncio.get_event_loop()
            try:
                def extract():
                    ydl_opts = {'format': 'bestaudio[ext=m4a]/best', 'quiet': True}
                    url = video_id if video_id.startswith("http") else f"https://www.youtube.com/watch?v={video_id}"
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        return info.get('url')
                stream_url = await loop.run_in_executor(None, extract)
                if stream_url:
                    app_state.setdefault("curation_stream_urls", {})[video_id] = stream_url
                    app_state["is_loading_preview"] = False
                    app_state["is_playing"] = True
                    audio_player.src = stream_url
                    audio_player.update()
                    await audio_player.play()
            except Exception as ex:
                lang = app_state["lang"]
                t = LOCALIZATION[lang]
                log(t["editor_log_fail_preview"].format(err=str(ex)), "error")
                app_state["is_loading_preview"] = False
                app_state["is_playing"] = False
            populate_editor_list()
            page.update()
        return handler

    def populate_editor_list():
        editor_tracks_view.controls.clear()
        app_state.setdefault("editor_play_buttons", {}).clear()
        
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        
        for idx, track in enumerate(app_state.setdefault("editor_tracks", [])):
            # Generate key if not present to support drag and drop without collisions
            if "key" not in track:
                track["key"] = f"{track['id']}_{idx}"
                
            video_id = track['id']
            title = track['title']
            duration = track.get('duration')
            duration_str = format_time(duration * 1000) if duration else "00:00"
            
            title_text = ft.Text(
                title,
                size=13,
                weight="bold",
                color=ft.Colors.WHITE,
                max_lines=2,
                overflow="ellipsis",
                expand=True
            )
            
            is_previewing_this = (app_state.get("previewing_video_id") == video_id)
            current_icon = ft.Icons.PLAY_ARROW_ROUNDED
            if is_previewing_this:
                if app_state.get("is_playing"):
                    current_icon = ft.Icons.PAUSE_ROUNDED
                elif app_state.get("is_loading_preview"):
                    current_icon = ft.Icons.HOURGLASS_EMPTY_ROUNDED

            play_btn = ft.IconButton(
                icon=current_icon,
                icon_color="#00CEC9",
                icon_size=24,
                tooltip="Play Preview",
            )
            app_state["editor_play_buttons"][video_id] = play_btn
            play_btn.on_click = make_editor_preview_handler(track, play_btn)
            
            delete_btn = ft.IconButton(
                icon=ft.Icons.DELETE_ROUNDED,
                icon_color="#FF7675",
                icon_size=20,
                tooltip="Delete Track"
            )
            
            def make_delete_handler(track_key, track_id):
                async def handler(e):
                    if app_state.get("previewing_video_id") == track_id:
                        if vlc_available:
                            vlc_player.stop()
                        await audio_player.pause()
                        app_state["previewing_video_id"] = None
                        app_state["is_playing"] = False
                        app_state["is_loading_preview"] = False
                    app_state["editor_tracks"] = [tr for tr in app_state["editor_tracks"] if tr.get("key") != track_key]
                    populate_editor_list()
                    page.update()
                return handler
                
            delete_btn.on_click = make_delete_handler(track["key"], video_id)
            
            editor_tracks_view.controls.append(
                ft.Container(
                    key=track["key"],
                    content=ft.Row(
                        [
                            play_btn,
                            title_text,
                            ft.Text(duration_str, size=12, color="#8F8F9F"),
                            delete_btn,
                            ft.Container(width=10)
                        ],
                        alignment="spaceBetween",
                        vertical_alignment="center"
                    ),
                    padding=ft.padding.Padding.symmetric(horizontal=10, vertical=6),
                    bgcolor="#1A1528",
                    border_radius=10,
                    border=ft.Border.all(1, "#3E2B5C")
                )
            )

    def show_beatlist_editor():
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        
        editor_title_text.value = t.get("beatlist_editor_title", "BeatList Editor 📝")
        editor_subtitle_text.value = t.get("beatlist_editor_subtitle", "Edit the track list before mixing or saving")
        editor_url_field.hint_text = t.get("beatlist_url_hint", "Paste YouTube URL...")
        editor_search_field.hint_text = t.get("beatlist_search_hint", "Search YouTube...")
        
        editor_tracks_label.value = t.get("editor_tracks_label", "Tracks in Playlist:")
        editor_sort_artist_btn.content.value = t.get("editor_by_artist", "By Artist 👤")
        editor_sort_song_btn.content.value = t.get("editor_by_song", "By Song 🎵")
        editor_sort_shuffle_btn.content.value = t.get("editor_shuffle", "Shuffle 🔀")
        
        beatlist_editor_dialog.actions[0].content.value = t.get("beatlist_close_btn", "Close ❌")
        beatlist_editor_dialog.actions[1].content.value = t.get("beatlist_delete_btn", "DELETE 🗑️")
        beatlist_editor_dialog.actions[2].content.value = t.get("beatlist_save_btn", "SAVE 💾")
        beatlist_editor_dialog.actions[3].content.value = t.get("beatlist_btn_mix", "START MIXING 🚀")
        
        editor_url_field.value = ""
        editor_search_field.value = ""
        editor_search_results.controls.clear()
        editor_search_results_container.visible = False
        
        app_state["editor_play_buttons"] = {}
        populate_editor_list()
        
        beatlist_editor_dialog.open = True
        page.update()

    async def save_editor_beatlist(e):
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        if not app_state.setdefault("editor_tracks", []):
            log(t["editor_err_empty"], "error")
            return
            
        default_name = f"{app_state.get('editor_keywords') or 'playlist'}.beatlist"
        
        file_picker = ft.FilePicker()
        save_path = await file_picker.save_file(
            dialog_title=t.get("beatlist_save_btn", "SAVE 💾"),
            file_name=default_name,
            allowed_extensions=["beatlist"],
            file_type=ft.FilePickerFileType.CUSTOM
        )
        if not save_path:
            return
            
        if not save_path.lower().endswith(".beatlist"):
            save_path += ".beatlist"
            
        try:
            import json
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(app_state["editor_tracks"], f, indent=2, ensure_ascii=False)
            app_state["editor_file_path"] = save_path
            playlist_name = os.path.basename(save_path).rsplit(".", 1)[0]
            app_state["editor_keywords"] = playlist_name
            log(t["editor_saved_success"].format(path=save_path), "success")
        except Exception as ex:
            log(t["editor_err_save"].format(err=str(ex)), "error")

    async def delete_editor_beatlist(e):
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        file_path = app_state.get("editor_file_path")
        
        # Stop any active previews
        if vlc_available:
            vlc_player.stop()
        if app_state.get("previewing_video_id"):
            await audio_player.pause()
            
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                log(t["editor_deleted_success"].format(path=os.path.basename(file_path)), "success")
            except Exception as ex:
                log(t["editor_err_save"].format(err=str(ex)), "error")
        else:
            log(t["editor_cleared_success"], "info_cyan")
            
        app_state["editor_tracks"] = []
        app_state["editor_file_path"] = None
        app_state["editor_keywords"] = ""
        
        beatlist_editor_dialog.open = False
        page.update()

    async def proceed_editor_mix(e):
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        if not app_state.setdefault("editor_tracks", []):
            log(t["editor_err_empty"], "error")
            return
            
        beatlist_editor_dialog.open = False
        page.update()
        if vlc_available:
            vlc_player.stop()
        if app_state.get("previewing_video_id"):
            await audio_player.pause()
            
        if app_state.get("is_processing"):
            curation_done_event.set()
        else:
            playlist_name = app_state.get("editor_keywords") or "EditorPlaylist"
            songs_per_kw = len(app_state["editor_tracks"])
            max_dur = int(duration_slider.value)
            crossfade = int(crossfade_slider.value)
            normalize_val = normalize_checkbox.value
            clean_cache = cleanup_checkbox.value
            
            log(t["editor_log_mix_editor"].format(name=playlist_name, count=songs_per_kw), "info_cyan")
            
            threading.Thread(
                target=process_mix_thread,
                args=([f"Editor: {playlist_name}"], songs_per_kw, max_dur, crossfade, normalize_val, clean_cache),
                kwargs={"imported_tracks": app_state["editor_tracks"]},
                daemon=True
            ).start()

    async def close_editor_click(e):
        beatlist_editor_dialog.open = False
        page.update()
        if vlc_available:
            vlc_player.stop()
        if app_state.get("previewing_video_id"):
            await audio_player.pause()
            
        if app_state.get("is_processing"):
            nonlocal curation_canceled
            curation_canceled = True
            curation_done_event.set()

    def sort_by_artist_click(e):
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        def parse_artist(t_item):
            parts = re.split(r'\s+[\-\–\—]\s+', t_item["title"], maxsplit=1)
            if len(parts) == 2:
                return parts[0].strip().lower()
            return t_item["title"].strip().lower()
            
        app_state.setdefault("editor_tracks", []).sort(key=parse_artist)
        populate_editor_list()
        page.update()
        log(t["editor_log_sorted_artist"], "info")
        
    def sort_by_song_click(e):
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        def parse_song(t_item):
            parts = re.split(r'\s+[\-\–\—]\s+', t_item["title"], maxsplit=1)
            if len(parts) == 2:
                return parts[1].strip().lower()
            return t_item["title"].strip().lower()
            
        app_state.setdefault("editor_tracks", []).sort(key=parse_song)
        populate_editor_list()
        page.update()
        log(t["editor_log_sorted_song"], "info")

    def shuffle_tracks_click(e):
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        import random
        random.shuffle(app_state.setdefault("editor_tracks", []))
        populate_editor_list()
        page.update()
        log(t["editor_log_shuffled"], "info")

    editor_tracks_label = ft.Text("Tracks in Playlist:", size=14, weight="bold", color="#8F8F9F")
    editor_sort_artist_btn = ft.TextButton(
        content=ft.Text("By Artist 👤", size=12, color="#00CEC9"),
        on_click=sort_by_artist_click
    )
    editor_sort_song_btn = ft.TextButton(
        content=ft.Text("By Song 🎵", size=12, color="#E84393"),
        on_click=sort_by_song_click
    )
    editor_sort_shuffle_btn = ft.TextButton(
        content=ft.Text("Shuffle 🔀", size=12, color="#FFEAA7"),
        on_click=shuffle_tracks_click
    )

    editor_content_column = ft.Column(
        [
            ft.Row([
                editor_url_field,
                editor_url_add_btn
            ], spacing=5),
            ft.Row([
                editor_search_field,
                editor_search_btn
            ], spacing=5),
            editor_search_results_container,
            ft.Row(
                [
                    editor_tracks_label,
                    ft.Row(
                        [
                            editor_sort_artist_btn,
                            editor_sort_song_btn,
                            editor_sort_shuffle_btn,
                        ],
                        spacing=5
                    )
                ],
                alignment="spaceBetween"
            ),
            ft.Container(
                content=editor_tracks_view,
                expand=True,
                border=ft.Border.all(1, "#252535"),
                border_radius=10,
                padding=5,
                bgcolor="#0B0914"
            )
        ],
        expand=True,
        spacing=10
    )
    
    beatlist_editor_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Column(
            [
                editor_title_text,
                editor_subtitle_text
            ],
            spacing=4
        ),
        content=ft.Container(
            width=700,
            height=600,
            content=editor_content_column,
            padding=ft.padding.Padding.symmetric(vertical=10)
        ),
        actions=[
            ft.TextButton(
                content=ft.Text("Close ❌", color="#FF7675", weight="bold"),
                on_click=close_editor_click
            ),
            ft.Button(
                content=ft.Text("DELETE 🗑️", color=ft.Colors.WHITE, weight="bold"),
                on_click=delete_editor_beatlist,
                style=ft.ButtonStyle(bgcolor="#D63031")
            ),
            ft.Button(
                content=ft.Text("SAVE 💾", color=ft.Colors.WHITE, weight="bold"),
                on_click=save_editor_beatlist,
                style=ft.ButtonStyle(bgcolor="#8E2DE2")
            ),
            ft.Button(
                content=ft.Text("START MIXING 🚀", color=ft.Colors.WHITE, weight="bold"),
                on_click=proceed_editor_mix,
                style=ft.ButtonStyle(bgcolor="#00CEC9")
            )
        ],
        actions_alignment="end"
    )
    page.overlay.append(beatlist_editor_dialog)

    def show_beatlist_action_dialog(file_path):
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        playlist_name = os.path.basename(file_path)
        
        action_dialog_title = ft.Text(t.get("beatlist_action_title", "Choose Action"), size=18, weight="bold")
        action_dialog_content = ft.Text(
            t.get("beatlist_action_sub", "What would you like to do with the playlist '{name}'?").format(name=playlist_name),
            size=14
        )
        
        async def on_mix_clicked(e):
            action_dialog.open = False
            page.update()
            load_mix_from_beatlist(file_path)
            
        async def on_edit_clicked(e):
            action_dialog.open = False
            page.update()
            await open_beatlist_in_editor(file_path)
            
        def on_cancel_clicked(e):
            action_dialog.open = False
            page.update()
            
        mix_btn = ft.Button(
            content=ft.Text(t.get("beatlist_btn_mix", "Start Mixing 🚀"), weight="bold", color=ft.Colors.WHITE),
            on_click=on_mix_clicked,
            style=ft.ButtonStyle(bgcolor="#00CEC9")
        )
        edit_btn = ft.Button(
            content=ft.Text(t.get("beatlist_btn_edit", "Edit Playlist 📝"), weight="bold", color=ft.Colors.WHITE),
            on_click=on_edit_clicked,
            style=ft.ButtonStyle(bgcolor="#E84393")
        )
        cancel_btn = ft.TextButton(
            content=ft.Text(t.get("beatlist_close_btn", "Cancel ❌"), color="#FF7675"),
            on_click=on_cancel_clicked
        )
        
        action_dialog = ft.AlertDialog(
            modal=True,
            title=action_dialog_title,
            content=ft.Container(content=action_dialog_content, padding=10),
            actions=[cancel_btn, edit_btn, mix_btn],
            actions_alignment="end"
        )
        page.overlay.append(action_dialog)
        action_dialog.open = True
        page.update()

    async def open_beatlist_in_editor(file_path):
        import json
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tracks_data = json.load(f)
            
            app_state["editor_tracks"] = []
            for track in tracks_data:
                v_id = track.get("id")
                title = track.get("title")
                duration = track.get("duration")
                if v_id:
                    app_state["editor_tracks"].append({
                        "id": v_id,
                        "title": title or "Unknown Title",
                        "duration": duration or 0
                    })
            app_state["editor_file_path"] = file_path
            app_state["editor_keywords"] = os.path.basename(file_path).rsplit(".", 1)[0]
            
            show_beatlist_editor()
        except Exception as e:
            log(f"Failed to load BeatList in editor: {str(e)}", "error")

    # Help Dialog & Button Definitions
    help_dialog_title = ft.Text("Help & Instructions 📋", size=20, weight="bold")
    
    async def open_url(e):
        await page.launch_url(e.data)
        
    help_dialog_content = ft.Markdown(
        "",
        selectable=True,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        on_tap_link=open_url
    )
    
    def close_help_dialog(e):
        help_dialog.open = False
        safe_update()
        
    help_dialog_close_btn = ft.TextButton("Close", on_click=close_help_dialog)
    
    help_dialog = ft.AlertDialog(
        title=help_dialog_title,
        content=ft.Container(
            width=600,
            height=400,
            content=ft.Column(
                [help_dialog_content],
                scroll=ft.ScrollMode.AUTO,
                expand=True
            ),
            padding=ft.padding.Padding.symmetric(vertical=10)
        ),
        actions=[
            help_dialog_close_btn
        ],
        actions_alignment="end"
    )
    page.overlay.append(help_dialog)
    
    def show_help_clicked(e):
        help_dialog.open = True
        safe_update()
        
    help_btn = ft.IconButton(
        icon=ft.Icons.HELP_OUTLINE_ROUNDED,
        icon_color="#00CEC9",
        tooltip="Help & Instructions",
        on_click=show_help_clicked,
    )
    
    async def show_curation_dialog_async():
        populate_curation_dialog()
        curation_dialog.open = True
        page.update()
        
    async def close_curation_dialog_async():
        curation_dialog.open = False
        page.update()
        if vlc_available:
            vlc_player.stop()
        if app_state["previewing_video_id"]:
            await audio_player.pause()
            
    def populate_curation_dialog():
        curation_list_view.controls.clear()
        app_state["curation_play_buttons"].clear()
        app_state["curation_title_texts"].clear()
        
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        
        curation_title_text.value = t["curation_title"]
        curation_subtitle_text.value = t["curation_subtitle"]
        curation_proceed_text.value = t["curation_start_mix"]
        curation_cancel_text.value = t["curation_cancel"]
        
        for idx, entry in enumerate(app_state["curation_entries"]):
            v_id = entry['id']
            title = entry['title']
            duration = entry.get('duration')
            duration_str = format_time(duration * 1000) if duration else "00:00"
            
            is_excluded = v_id in app_state["excluded_video_ids"]
            
            title_text = ft.Text(
                title,
                size=13,
                weight="bold" if not is_excluded else "normal",
                color=ft.Colors.WHITE if not is_excluded else "#5F5F7F",
                max_lines=2,
                overflow="ellipsis",
                expand=True,
                style=ft.TextStyle(
                    decoration=ft.TextDecoration.LINE_THROUGH if is_excluded else None
                )
            )
            app_state["curation_title_texts"][v_id] = title_text
            
            play_btn = ft.IconButton(
                icon=ft.Icons.PLAY_ARROW_ROUNDED,
                icon_color="#00CEC9",
                icon_size=24,
                tooltip="Play Preview",
            )
            app_state["curation_play_buttons"][v_id] = play_btn
            
            def make_preview_handler(item, btn):
                async def handler(e):
                    video_id = item['id']
                    
                    # VLC-based playing/toggling logic
                    if vlc_available:
                        if app_state.get("previewing_video_id") == video_id and vlc_player.is_playing():
                            vlc_player.pause()
                            app_state["is_playing"] = False
                            btn.icon = ft.Icons.PLAY_ARROW_ROUNDED
                            btn.update()
                            return
                        
                        if vlc_player.is_playing():
                            vlc_player.stop()
                        await audio_player.pause()
                        
                        for button in app_state["curation_play_buttons"].values():
                            if button != btn and button.icon == ft.Icons.PAUSE_ROUNDED:
                                button.icon = ft.Icons.PLAY_ARROW_ROUNDED
                                button.update()
                        
                        btn.icon = ft.Icons.HOURGLASS_EMPTY_ROUNDED
                        btn.update()
                        
                        cached_url = app_state.get("curation_stream_urls", {}).get(video_id)
                        if cached_url:
                            app_state["previewing_video_id"] = video_id
                            app_state["is_playing"] = True
                            vlc_player.set_mrl(cached_url)
                            vlc_player.play()
                            btn.icon = ft.Icons.PAUSE_ROUNDED
                            btn.update()
                            return
                        
                        loop = asyncio.get_event_loop()
                        try:
                            def extract():
                                ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
                                url = video_id if video_id.startswith("http") else f"https://www.youtube.com/watch?v={video_id}"
                                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                    info = ydl.extract_info(url, download=False)
                                    return info.get('url')
                            stream_url = await loop.run_in_executor(None, extract)
                            if stream_url:
                                app_state.setdefault("curation_stream_urls", {})[video_id] = stream_url
                                app_state["previewing_video_id"] = video_id
                                app_state["is_playing"] = True
                                vlc_player.set_mrl(stream_url)
                                vlc_player.play()
                                btn.icon = ft.Icons.PAUSE_ROUNDED
                                btn.update()
                        except Exception as ex:
                            log(f"Failed to play preview: {str(ex)}", "error")
                            btn.icon = ft.Icons.PLAY_ARROW_ROUNDED
                            btn.update()
                        return

                    # Fallback Flet Audio player logic
                    if app_state["previewing_video_id"] == video_id and app_state["is_playing"]:
                        await audio_player.pause()
                        return
                    for button in app_state["curation_play_buttons"].values():
                        if button != btn and button.icon == ft.Icons.PAUSE_ROUNDED:
                            button.icon = ft.Icons.PLAY_ARROW_ROUNDED
                            button.update()
                    btn.icon = ft.Icons.HOURGLASS_EMPTY_ROUNDED
                    btn.update()
                    
                    cached_url = app_state.get("curation_stream_urls", {}).get(video_id)
                    if cached_url:
                        app_state["previewing_video_id"] = video_id
                        audio_player.src = cached_url
                        audio_player.update()
                        await audio_player.play()
                        return
                        
                    loop = asyncio.get_event_loop()
                    try:
                        def extract():
                            ydl_opts = {'format': 'bestaudio[ext=m4a]/best', 'quiet': True}
                            url = video_id if video_id.startswith("http") else f"https://www.youtube.com/watch?v={video_id}"
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                info = ydl.extract_info(url, download=False)
                                return info.get('url')
                        stream_url = await loop.run_in_executor(None, extract)
                        if stream_url:
                            app_state.setdefault("curation_stream_urls", {})[video_id] = stream_url
                            app_state["previewing_video_id"] = video_id
                            audio_player.src = stream_url
                            audio_player.update()
                            await audio_player.play()
                    except Exception as ex:
                        log(f"Failed to play preview: {str(ex)}", "error")
                        btn.icon = ft.Icons.PLAY_ARROW_ROUNDED
                        btn.update()
                return handler
                
            play_btn.on_click = make_preview_handler(entry, play_btn)
            
            exclude_checkbox = ft.Checkbox(
                value=not is_excluded,
                active_color="#00CEC9",
                tooltip=t["curation_exclude"]
            )
            
            def make_exclude_handler(video_id, t_control, p_btn):
                def handler(e):
                    checkbox_val = e.control.value
                    if not checkbox_val:
                        app_state["excluded_video_ids"].add(video_id)
                        t_control.color = "#5F5F7F"
                        t_control.style.decoration = ft.TextDecoration.LINE_THROUGH
                        t_control.weight = "normal"
                    else:
                        app_state["excluded_video_ids"].discard(video_id)
                        t_control.color = ft.Colors.WHITE
                        t_control.style.decoration = None
                        t_control.weight = "bold"
                    t_control.update()
                return handler
                
            exclude_checkbox.on_change = make_exclude_handler(v_id, title_text, play_btn)
            
            curation_list_view.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            play_btn,
                            title_text,
                            ft.Text(duration_str, size=12, color="#8F8F9F"),
                            exclude_checkbox
                        ],
                        alignment="spaceBetween",
                        vertical_alignment="center"
                    ),
                    padding=ft.padding.Padding.symmetric(horizontal=10, vertical=6),
                    bgcolor="#1A1528" if not is_excluded else "#121217",
                    border_radius=10,
                    border=ft.Border.all(1, "#3E2B5C" if not is_excluded else "#252535")
                )
            )
    
    def show_duplicates_dialog(e):
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        duplicates_list_view.controls.clear()
        if not app_state["rejected_tracks"]:
            no_dup_text = "No duplicate tracks were rejected." if lang == "en" else "Δεν απορρίφθηκε κανένα διπλότυπο τραγούδι."
            duplicates_list_view.controls.append(ft.Text(no_dup_text, italic=True, color="#8F8F9F"))
        else:
            for title, reason, matching_title in app_state["rejected_tracks"]:
                reason_disp = reason
                if "Similar title and longer" in reason:
                    parts = re.findall(r'\d+', reason)
                    if len(parts) >= 2:
                        dur, acc_dur = parts[0], parts[1]
                        reason_disp = f"Similar title and longer ({dur}s vs {acc_dur}s)" if lang == "en" else f"Παρόμοιος τίτλος και μεγαλύτερη διάρκεια ({dur}s έναντι {acc_dur}s)"
                
                reason_label = f"Reason: {reason_disp}" if lang == "en" else f"Αιτία: {reason_disp}"
                matching_label = f"Matching accepted song: {matching_title}" if lang == "en" else f"Αντίστοιχο αποδεκτό τραγούδι: {matching_title}"
                
                duplicates_list_view.controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(title, size=13, weight="bold", color="#FF7675", max_lines=1, overflow="ellipsis"),
                                ft.Text(reason_label, size=11, color="#EAEAEA"),
                                ft.Text(matching_label, size=11, color="#8F8F9F", italic=True),
                            ],
                            spacing=2
                        ),
                        padding=10,
                        border_radius=8,
                        bgcolor="#1E1315",
                        border=ft.Border.all(1, "#3F1D21")
                    )
                )
        duplicates_dialog.open = True
        safe_update()
        
    duplicates_text = ft.Text("Duplicates (0)", color="#FF7675")
    duplicates_btn = ft.TextButton(
        content=duplicates_text,
        icon=ft.Icons.DELETE_SWEEP_ROUNDED,
        icon_color="#FF7675",
        visible=False,
        on_click=show_duplicates_dialog
    )
    
    async def save_mix_clicked(e):
        if not app_state["audio_path"]:
            log("No active mix to export.", "error")
            return
            
        # Get active keywords to generate a nice name
        active_kws = app_state.get("active_keywords", [])
        if not active_kws:
            kw_str = "my-mix"
        else:
            cleaned = []
            for kw in active_kws:
                # Keep alphanumeric and Greek/English letters
                k = re.sub(r'[^a-zA-Z0-9\sα-ωΑ-ΩίϊΐόάέύϋΰήώΊΪΌΆΈΎΫΉΏ]', '', kw).strip()
                k = re.sub(r'\s+', '-', k)
                if k:
                    cleaned.append(k)
            kw_str = "+".join(cleaned) if cleaned else "my-mix"
            
        default_name = f"{kw_str}-mix.spymix"
        
        # Open the Save File dialog
        file_picker = ft.FilePicker()
        save_path = await file_picker.save_file(
            dialog_title="Export Mix as .spymix / Εξαγωγή μίξης",
            file_name=default_name,
            allowed_extensions=["spymix"],
            file_type=ft.FilePickerFileType.CUSTOM
        )
        
        if not save_path:
            return
            
        # Make sure it has the extension
        if not save_path.lower().endswith(".spymix"):
            save_path += ".spymix"
            
        # Perform packaging in a background thread to prevent UI freezing
        def do_packaging():
            try:
                import zipfile
                import json
                
                log(f"Packaging mix into .spymix archive to {save_path}...", "info")
                
                # Get the source MP3 path
                audio_url = app_state["audio_path"]
                if audio_url.startswith("file:///"):
                    local_mp3_path = audio_url[8:]
                else:
                    local_mp3_path = audio_url
                
                # Replace slashes for python path compatibility
                local_mp3_path = os.path.normpath(local_mp3_path)
                
                if not os.path.exists(local_mp3_path):
                    # Check if the file is in assets or relative path
                    if local_mp3_path.startswith("/") or local_mp3_path.startswith("\\"):
                        check_path = os.path.join("assets", local_mp3_path.lstrip("/\\"))
                        if os.path.exists(check_path):
                            local_mp3_path = check_path
                
                if not os.path.exists(local_mp3_path):
                    log(f"Source MP3 file not found: {local_mp3_path}", "error")
                    return
                
                # Reconstruct metadata
                metadata = {
                    "keywords": app_state.get("active_keywords", []),
                    "total_duration_ms": app_state["total_duration_ms"],
                    "tracks": [
                        {
                            "title": track.title,
                            "video_id": track.video_id,
                            "original_duration_ms": track.original_duration_ms,
                            "cropped_duration_ms": track.cropped_duration_ms,
                            "start_time_ms": track.start_time_ms
                        }
                        for track in app_state["tracks"]
                    ]
                }
                
                with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # Write metadata.xsp as mix.xsp
                    metadata_json = json.dumps(metadata, indent=4, ensure_ascii=False)
                    zipf.writestr("mix.xsp", metadata_json)
                    # Write mp3 audio as mix.mp3
                    zipf.write(local_mp3_path, "mix.mp3")
                    
                log(f"Successfully exported mix to: {os.path.basename(save_path)}", "success")
            except Exception as ex:
                log(f"Failed to export mix package: {str(ex)}", "error")
                
        threading.Thread(target=do_packaging, daemon=True).start()

    async def edit_current_mix_clicked(e):
        if not app_state.get("tracks"):
            log("No active mix loaded to edit.", "error")
            return
            
        app_state["editor_tracks"] = []
        for track in app_state["tracks"]:
            app_state["editor_tracks"].append({
                "id": track.video_id,
                "title": track.title,
                "duration": track.cropped_duration_ms // 1000
            })
        app_state["editor_file_path"] = None
        app_state["editor_keywords"] = "current-mix"
        app_state["previewing_video_id"] = None
        
        show_beatlist_editor()

    edit_current_mix_btn = ft.IconButton(
        icon=ft.Icons.EDIT_ROUNDED,
        icon_color="#E84393",
        icon_size=26,
        tooltip="Edit Playlist / Επεξεργασία Λίστας",
        visible=False,
        on_click=edit_current_mix_clicked
    )

    save_mix_btn = ft.IconButton(
        icon=ft.Icons.SAVE_ALT_ROUNDED,
        icon_color="#00CEC9",
        icon_size=26,
        tooltip="Export Mix / Εξαγωγή Μίξης",
        visible=False,
        on_click=save_mix_clicked
    )
    
    # Layout panels
    player_card = ft.Container(
        content=ft.Column(
            [
                ft.Row([
                    ft.Column([
                        player_mix_title,
                        player_mix_subtitle
                    ], expand=True),
                    edit_current_mix_btn,
                    save_mix_btn
                ], alignment="spaceBetween"),
                ft.Container(height=10),
                ft.Row([vinyl_container], alignment="center"),
                ft.Container(height=10),
                # Progress Bar & Timestamps
                ft.Row([
                    current_time_text,
                    player_slider,
                    total_time_text
                ], alignment="center"),
                # Control Buttons
                ft.Row([
                    prev_btn,
                    play_pause_btn,
                    next_btn
                ], alignment="center", spacing=20),
                # Volume Control
                ft.Row([
                    volume_icon,
                    volume_slider
                ], alignment="center")
            ],
            alignment="center",
            horizontal_alignment="center"
        ),
        padding=24,
        border_radius=20,
        gradient=ft.LinearGradient(
            begin=ft.Alignment(-1, -1),
            end=ft.Alignment(1, 1),
            colors=["#1A102F", "#0E1C24"]
        ),
        border=ft.Border.all(1, "#2E2545"),
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=20,
            color=ft.Colors.with_opacity(0.3, "#000000")
        ),
        visible=False,
        expand=3
    )
    
    playlist_header_text = ft.Text("Mix Playlist Timeline", size=16, weight="bold")
    
    playlist_card = ft.Container(
        content=ft.Column(
            [
                ft.Row([
                    ft.Row([
                        ft.Icon(ft.Icons.QUEUE_MUSIC_ROUNDED, color="#00CEC9"),
                        playlist_header_text
                    ], spacing=10),
                    duplicates_btn
                ], alignment="spaceBetween"),
                ft.Divider(height=1, color="#252535"),
                ft.Container(content=playlist_list, expand=True)
            ]
        ),
        padding=20,
        border_radius=20,
        bgcolor="#121217",
        border=ft.Border.all(1, "#252535"),
        expand=2,
        visible=False
    )
    
    placeholder_title = ft.Text("No Active Mix", size=20, weight="bold", color="#5F5F7F")
    placeholder_sub = ft.Text("Specify keywords and generate a mix to start listening", size=14, color="#3F3F5F", text_align="center")
    
    right_panel_placeholder = ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.HEADPHONES_ROUNDED, size=64, color="#3F3F5F"),
                placeholder_title,
                placeholder_sub
            ],
            alignment="center",
            horizontal_alignment="center"
        ),
        alignment=ft.Alignment(0, 0),
        expand=True
    )
    
    right_panel = ft.Column(
        [
            player_card,
            ft.Container(height=10),
            playlist_card
        ],
        expand=True
    )
    
    def audio_state_changed(e):
        state = getattr(e, 'state', None) or e.data
        state_str = str(state).lower()
        if "playing" in state_str:
            app_state["is_playing"] = True
            play_pause_btn.icon = ft.Icons.PAUSE_CIRCLE_FILLED
            play_pause_btn.icon_color = "#FF7675"
            vinyl_container.border = ft.Border.all(4, "#00CEC9")
            vinyl_container.shadow.color = "#00CEC9"
            # Start rotation thread
            threading.Thread(target=spin_vinyl_record, daemon=True).start()
        else: # paused or stopped
            app_state["is_playing"] = False
            play_pause_btn.icon = ft.Icons.PLAY_CIRCLE_FILLED
            play_pause_btn.icon_color = "#00CEC9"
            vinyl_container.border = ft.Border.all(4, "#8E2DE2")
            vinyl_container.shadow.color = "#8E2DE2"
            
        try:
            play_pause_btn.update()
        except:
            pass
        try:
            vinyl_container.update()
        except:
            pass
            
        # Update curation play buttons if visible
        previewing_id = app_state.get("previewing_video_id")
        if previewing_id and app_state.get("curation_play_buttons"):
            for vid, btn in app_state["curation_play_buttons"].items():
                if vid == previewing_id and "playing" in state_str:
                    btn.icon = ft.Icons.PAUSE_ROUNDED
                else:
                    btn.icon = ft.Icons.PLAY_ARROW_ROUNDED
                try:
                    btn.update()
                except:
                    pass

        # Update editor play buttons if visible by rebuilding the list safely
        if previewing_id and beatlist_editor_dialog.open:
            try:
                populate_editor_list()
                safe_update()
            except:
                pass

    def audio_position_changed(e):
        pos_ms = getattr(e, 'position', None)
        if pos_ms is None:
            try:
                pos_ms = int(e.data)
            except:
                pos_ms = 0
                
        app_state["current_position_ms"] = pos_ms
        
        # Update slider if not currently dragging
        if not app_state["is_dragging_slider"]:
            player_slider.value = pos_ms
            try:
                player_slider.update()
            except:
                pass
            current_time_text.value = format_time(pos_ms)
            try:
                current_time_text.update()
            except:
                pass
            
        # Highlight playing track in playlist
        active_idx = -1
        tracks = app_state["tracks"]
        for i, track in enumerate(tracks):
            next_start = tracks[i+1].start_time_ms if i + 1 < len(tracks) else app_state["total_duration_ms"]
            if track.start_time_ms <= pos_ms < next_start:
                active_idx = i
                break
                
        if active_idx != app_state["active_track_idx"] and active_idx != -1:
            app_state["active_track_idx"] = active_idx
            update_playlist_ui()

    debug_log("Step 6: UI controls created, ready to initialize audio")

    # Audio player service initialization in the main thread
    # This ensures Flet registers the control and assigns the page context properly!
    audio_player = fta.Audio(
        src="/test_mix.mp3",
        autoplay=False,
        volume=volume_slider.value / 100.0,
        on_state_change=audio_state_changed,
        on_position_change=audio_position_changed
    )
    page.services.append(audio_player)
    debug_log("Step 7: Audio player service created")
    
    # Logging helper
    def log(message, level="info"):
        color = ft.Colors.WHITE
        if level == "success":
            color = "#00CEC9"
        elif level == "warning":
            color = "#FFEAA7"
        elif level == "error":
            color = "#FF7675"
        elif level == "info_cyan":
            color = "#81ECEC"
            
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_list.controls.append(
            ft.Text(
                f"[{timestamp}] {message}",
                color=color,
                font_family="Consolas",
                size=12,
            )
        )
        safe_update()
    
    # Spin vinyl thread function
    def spin_vinyl_record():
        while app_state["is_playing"]:
            vinyl_img.rotate.angle += math.pi * 2
            try:
                vinyl_img.update()
            except:
                break
            time.sleep(3)
            
    # Volume control change
    def volume_changed(e):
        vol_val = volume_slider.value / 100.0
        if audio_player:
            audio_player.volume = vol_val
            audio_player.update()
        if vol_val == 0:
            volume_icon.icon = ft.Icons.VOLUME_MUTE_ROUNDED
        elif vol_val < 0.4:
            volume_icon.icon = ft.Icons.VOLUME_DOWN_ROUNDED
        else:
            volume_icon.icon = ft.Icons.VOLUME_UP_ROUNDED
        volume_icon.update()
        
    volume_slider.on_change = volume_changed
    
    def toggle_mute(e):
        if audio_player:
            if audio_player.volume > 0:
                app_state["prev_volume"] = audio_player.volume
                audio_player.volume = 0
                volume_slider.value = 0
                volume_icon.icon = ft.Icons.VOLUME_MUTE_ROUNDED
            else:
                restored_vol = app_state.get("prev_volume", 0.8)
                audio_player.volume = restored_vol
                volume_slider.value = restored_vol * 100
                volume_icon.icon = ft.Icons.VOLUME_UP_ROUNDED if restored_vol >= 0.4 else ft.Icons.VOLUME_DOWN_ROUNDED
            audio_player.update()
            volume_slider.update()
            volume_icon.update()
            
    volume_icon.on_click = toggle_mute
    
    # Seek slider drag handler
    def player_slider_drag(e):
        app_state["is_dragging_slider"] = True
        current_time_text.value = format_time(e.control.value)
        current_time_text.update()
        
    async def player_slider_seek(e):
        if audio_player:
            await audio_player.seek(int(e.control.value))
        app_state["is_dragging_slider"] = False
        
    player_slider.on_change = player_slider_drag
    player_slider.on_change_end = player_slider_seek

    def update_playlist_ui():
        playlist_list.controls.clear()
        for i, track in enumerate(app_state["tracks"]):
            is_active = (i == app_state["active_track_idx"])
            
            def make_seek_handler(t_ms):
                async def handler(e):
                    await seek_to_ms(t_ms)
                return handler
                
            playlist_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.PLAY_ARROW_ROUNDED if not is_active else ft.Icons.VOLUME_UP_ROUNDED,
                                icon_color="#00CEC9" if is_active else "#8F8F9F",
                                on_click=make_seek_handler(track.start_time_ms)
                            ),
                            ft.Text(f"{i+1:02d}", size=13, color="#8F8F9F" if not is_active else "#00CEC9", weight="bold"),
                            ft.VerticalDivider(width=1, color="#252535"),
                            ft.Text(
                                track.title, 
                                size=14, 
                                color=ft.Colors.WHITE if not is_active else "#00CEC9", 
                                weight="w500" if not is_active else "bold",
                                max_lines=1,
                                overflow="ellipsis",
                                expand=True
                            ),
                            ft.Container(
                                content=ft.Text(format_time(track.start_time_ms), size=12, color="#00CEC9", weight="w600"),
                                bgcolor="#162E2E" if is_active else "#1A1A24",
                                padding=ft.padding.Padding.all(6),
                                border_radius=6
                            ),
                            ft.Text(format_time(track.cropped_duration_ms), size=13, color="#8F8F9F")
                        ],
                        alignment="spaceBetween"
                    ),
                    padding=ft.padding.Padding.symmetric(horizontal=10, vertical=4),
                    border_radius=10,
                    bgcolor="#1A1528" if is_active else ft.Colors.TRANSPARENT,
                    border=ft.Border.all(1, "#3E2B5C" if is_active else ft.Colors.TRANSPARENT),
                )
            )
        try:
            playlist_list.update()
        except:
            pass

    async def seek_to_ms(ms):
        if audio_player:
            await audio_player.seek(ms)
            if not app_state["is_playing"]:
                await audio_player.play()

    async def play_pause_clicked(e):
        if vlc_available and vlc_player.is_playing():
            vlc_player.stop()
            for other_btn in app_state.get("editor_play_buttons", {}).values():
                other_btn.icon = ft.Icons.PLAY_ARROW_ROUNDED
            for other_btn in app_state.get("curation_play_buttons", {}).values():
                other_btn.icon = ft.Icons.PLAY_ARROW_ROUNDED
            page.update()
        if audio_player:
            if app_state["is_playing"]:
                await audio_player.pause()
            else:
                await audio_player.play()

    play_pause_btn.on_click = play_pause_clicked

    async def prev_clicked(e):
        pos = app_state["current_position_ms"]
        tracks = app_state["tracks"]
        if not tracks:
            return
            
        current_idx = app_state["active_track_idx"]
        if pos - tracks[current_idx].start_time_ms > 3000:
            await seek_to_ms(tracks[current_idx].start_time_ms)
        else:
            prev_idx = max(0, current_idx - 1)
            await seek_to_ms(tracks[prev_idx].start_time_ms)
            
    prev_btn.on_click = prev_clicked

    async def next_clicked(e):
        tracks = app_state["tracks"]
        if not tracks:
            return
        current_idx = app_state["active_track_idx"]
        next_idx = min(len(tracks) - 1, current_idx + 1)
        await seek_to_ms(tracks[next_idx].start_time_ms)
        
    next_btn.on_click = next_clicked

    # Download & Mix Background Thread
    def process_mix_thread(keywords, songs_per_kw, max_dur_min, crossfade_sec, normalize_val, clean_cache, imported_tracks=None, skip_curation=False):
        nonlocal audio_player
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        
        # UI resets
        app_state["is_processing"] = True
        generate_btn.disabled = True
        generate_btn.content.content.value = t["processing_btn"]
        safe_update()
        time.sleep(0.05)
        
        log_list.controls.clear()
        app_state["tracks"] = []
        app_state["rejected_tracks"] = []
        
        log("Starting SpyMixer job...", "info_cyan")
        log(f"Keywords: {keywords}", "info")
        log(f"Config: {songs_per_kw} songs/kw | Max duration: {max_dur_min}m | Crossfade: {crossfade_sec}s", "info")
        
        # Temp directories
        download_dir = "downloads"
        assets_dir = "assets"
        os.makedirs(download_dir, exist_ok=True)
        os.makedirs(assets_dir, exist_ok=True)
        
        all_video_entries = []
        rejected_tracks = []
        
        if imported_tracks is None:
            # 1. Search YouTube
            status_label.value = t["search_phase"]
            progress_bar.value = None
            safe_update()
            time.sleep(0.05)
            
            seen_ids = set()
            for kw in keywords:
                kw = kw.strip()
                if not kw:
                    continue
                log(f"Searching for up to {songs_per_kw} matching songs for keyword: '{kw}'...", "info")
                
                ydl_opts_search = {
                    'format': 'bestaudio/best',
                    'extract_flat': True,
                    'skip_download': True,
                    'quiet': True,
                    'no_warnings': True,
                    'socket_timeout': 15,
                }
                
                try:
                    with yt_dlp.YoutubeDL(ydl_opts_search) as ydl:
                        search_query = f"ytsearch{songs_per_kw + 10}:{kw}"
                        res = ydl.extract_info(search_query, download=False)
                        entries = res.get('entries', [])
                        
                        added_for_kw = 0
                        for entry in entries:
                            if added_for_kw >= songs_per_kw:
                                break
                            v_id = entry.get('id')
                            title = entry.get('title')
                            duration = entry.get('duration') # in seconds
                            
                            if not v_id or not title:
                                continue
                            if v_id in seen_ids:
                                continue
                                
                            if duration:
                                if duration < 30 or duration > 1080:
                                    continue
                                    
                            seen_ids.add(v_id)
                            all_video_entries.append(entry)
                            added_for_kw += 1
                            
                        log(f"Found {added_for_kw} suitable videos for '{kw}'", "success")
                except Exception as e:
                    log(f"Error searching for '{kw}': {str(e)}", "error")
                    
            log("Running duplicate check on all gathered songs...", "info")
            
            all_video_entries.sort(key=lambda x: x.get('duration') or 0)
            
            accepted_entries = []
            for entry in all_video_entries:
                title = entry.get('title')
                duration = entry.get('duration')
                new_words = clean_words(title)
                
                is_duplicate = False
                matching_title = ""
                matching_duration = 0
                
                for acc_entry in accepted_entries:
                    acc_title = acc_entry.get('title')
                    acc_duration = acc_entry.get('duration')
                    acc_words = clean_words(acc_title)
                    
                    if is_similar_title(new_words, acc_words, threshold=0.8):
                        if duration and acc_duration:
                            if abs(duration - acc_duration) <= 20:
                                is_duplicate = True
                                matching_title = acc_title
                                matching_duration = acc_duration
                                break
                
                if is_duplicate:
                    rejected_tracks.append((
                        title,
                        f"Similar title and longer ({duration}s vs {matching_duration}s)",
                        matching_title
                    ))
                    log(f"Rejected duplicate: '{title}' (longer than '{matching_title}')", "warning")
                else:
                    accepted_entries.append(entry)
                    
            all_video_entries = accepted_entries
        else:
            # Use pre-loaded imported tracks from .beatlist
            all_video_entries = imported_tracks
            log(f"Skipped search. Using {len(all_video_entries)} tracks from imported playlist.", "success")
            
        total_videos = len(all_video_entries)
        app_state["rejected_tracks"] = rejected_tracks
        
        if rejected_tracks:
            duplicates_text.value = f"{t['duplicates_btn']} ({len(rejected_tracks)})"
            duplicates_btn.visible = True
        else:
            duplicates_btn.visible = False
        
        if total_videos == 0:
            log("No videos found to download. Aborting.", "error")
            status_label.value = t["fail_search"]
            progress_bar.value = 0
            generate_btn.disabled = False
            generate_btn.content.content.value = t["generate_btn"]
            app_state["is_processing"] = False
            safe_update()
            return
            
        # Open BeatList Editor if skip_curation is False
        if not skip_curation:
            app_state["editor_tracks"] = []
            for entry in all_video_entries:
                app_state["editor_tracks"].append({
                    "id": entry.get("id"),
                    "title": entry.get("title") or "Unknown Title",
                    "duration": entry.get("duration") or 0
                })
            app_state["editor_file_path"] = None
            app_state["editor_keywords"] = ", ".join(keywords)
            app_state["previewing_video_id"] = None
            
            nonlocal curation_canceled
            curation_canceled = False
            curation_done_event.clear()
            
            async def show_editor_async():
                show_beatlist_editor()
            page.run_task(show_editor_async)
            
            log("Waiting for user beatlist customization...", "info_cyan")
            curation_done_event.wait()
            
            if curation_canceled:
                log("Mix generation canceled by user in editor.", "warning")
                status_label.value = t["ready_to_mix"]
                progress_bar.value = 0
                generate_btn.disabled = False
                generate_btn.content.content.value = t["generate_btn"]
                app_state["is_processing"] = False
                safe_update()
                return
                
            all_video_entries = app_state["editor_tracks"]
            total_videos = len(all_video_entries)
            
            if total_videos == 0:
                log("No songs were approved for mixing. Aborting.", "error")
                status_label.value = t["fail_search"]
                progress_bar.value = 0
                generate_btn.disabled = False
                generate_btn.content.content.value = t["generate_btn"]
                app_state["is_processing"] = False
                safe_update()
                return
        else:
            total_videos = len(all_video_entries)
        log(f"Total songs to download: {total_videos}", "info_cyan")
        
        status_label.value = t["download_phase"]
        progress_bar.value = 0.05
        safe_update()
        time.sleep(0.05)
        
        downloaded_paths = []
        downloaded_metadata = []
        
        for idx, entry in enumerate(all_video_entries):
            v_id = entry['id']
            title = entry['title']
            video_url = f"https://www.youtube.com/watch?v={v_id}"
            
            log(f"[{idx+1}/{total_videos}] Downloading: {title}...", "info")
            progress_bar.value = 0.05 + 0.65 * (idx / total_videos)
            status_label.value = t["download_song_phase"].format(current=idx+1, total=total_videos)
            safe_update()
            time.sleep(0.05)
            
            max_dur_sec = max_dur_min * 60
            ydl_opts_dl = {
                'format': 'bestaudio/best',
                'outtmpl': f'{download_dir}/{v_id}.%(ext)s',
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'download_ranges': yt_dlp.utils.download_range_func(None, [(0, max_dur_sec)]),
                'force_keyframes_at_cuts': True,
                'socket_timeout': 15,
                'retries': 3,
                'fragment_retries': 5,
            }
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts_dl) as ydl:
                    info_dict = ydl.extract_info(video_url, download=True)
                    ext = info_dict.get('ext')
                    filepath = os.path.join(download_dir, f"{v_id}.{ext}")
                    
                    if os.path.exists(filepath):
                        downloaded_paths.append(filepath)
                        downloaded_metadata.append(info_dict)
                        app_state["downloaded_files"].append(filepath)
                        log(f"Successfully downloaded: {title}", "success")
                    else:
                        log(f"Download completed but file not found: {filepath}", "warning")
            except Exception as e:
                log(f"Failed to download {title}: {str(e)}", "error")
                
        if not downloaded_paths:
            log("All downloads failed. Aborting.", "error")
            status_label.value = t["fail_download"]
            progress_bar.value = 0
            generate_btn.disabled = False
            generate_btn.content.content.value = t["generate_btn"]
            app_state["is_processing"] = False
            safe_update()
            return
            
        log(f"Successfully downloaded {len(downloaded_paths)} of {total_videos} songs.", "success")
        
        status_label.value = t["process_phase"]
        progress_bar.value = None
        safe_update()
        time.sleep(0.05)
        
        temp_chunks_dir = os.path.join(download_dir, "temp_chunks")
        os.makedirs(temp_chunks_dir, exist_ok=True)
        
        current_chunk = None
        tracks_meta = []
        mix_duration_ms = 0
        
        max_dur_ms = max_dur_min * 60 * 1000
        crossfade_ms = crossfade_sec * 1000
        
        chunk_limit_ms = 30 * 60 * 1000
        buffer_ms = 30 * 1000
        
        temp_chunk_paths = []
        
        for idx, filepath in enumerate(downloaded_paths):
            info = downloaded_metadata[idx]
            title = info.get('title', 'Unknown Track')
            v_id = info.get('id', '')
            
            log(f"Processing audio [{idx+1}/{len(downloaded_paths)}]: {title}...", "info")
            time.sleep(0.05)  # Yield GIL to let Flet update the UI on Windows
            
            try:
                song = AudioSegment.from_file(filepath)
                orig_dur = len(song)
                time.sleep(0.05)  # Yield GIL
                
                if normalize_val:
                    log("Normalizing volume...", "info")
                    time.sleep(0.05)  # Yield GIL
                    song = normalize(song)
                    time.sleep(0.05)  # Yield GIL
                    
                cropped_dur = orig_dur
                if orig_dur > max_dur_ms:
                    song = song[:max_dur_ms]
                    cropped_dur = max_dur_ms
                    log(f"Cropped from {format_time(orig_dur)} to {format_time(cropped_dur)}", "info")
                    time.sleep(0.05)  # Yield GIL
                
                start_time_ms = 0
                if current_chunk is None:
                    current_chunk = song
                    start_time_ms = 0
                    mix_duration_ms = cropped_dur
                else:
                    actual_cf_ms = min(crossfade_ms, len(current_chunk), len(song))
                    start_time_ms = mix_duration_ms - actual_cf_ms
                    current_chunk = current_chunk.append(song, crossfade=actual_cf_ms)
                    mix_duration_ms = mix_duration_ms + cropped_dur - actual_cf_ms
                    log(f"Appended with {actual_cf_ms/1000:.1f}s crossfade", "info")
                    time.sleep(0.05)  # Yield GIL
                    
                tracks_meta.append(TrackMetadata(
                    title=title,
                    video_id=v_id,
                    original_duration_ms=orig_dur,
                    cropped_duration_ms=cropped_dur,
                    start_time_ms=start_time_ms
                ))
                
                del song
                import gc
                gc.collect()
                
                if len(current_chunk) > chunk_limit_ms + buffer_ms:
                    export_part = current_chunk[:-buffer_ms]
                    current_chunk = current_chunk[-buffer_ms:]
                    
                    chunk_path = os.path.join(temp_chunks_dir, f"part_{len(temp_chunk_paths)}.mp3")
                    log(f"Saving intermediate mix chunk {len(temp_chunk_paths)} to disk to free memory...", "info")
                    export_part.export(chunk_path, format="mp3", bitrate="192k")
                    temp_chunk_paths.append(chunk_path)
                    
                    del export_part
                    gc.collect()
                    
            except Exception as e:
                log(f"Failed to process {title}: {str(e)}", "error")
                
        if current_chunk is not None and len(current_chunk) > 0:
            chunk_path = os.path.join(temp_chunks_dir, f"part_{len(temp_chunk_paths)}.mp3")
            log(f"Saving final mix chunk {len(temp_chunk_paths)}...", "info")
            try:
                current_chunk.export(chunk_path, format="mp3", bitrate="192k")
                temp_chunk_paths.append(chunk_path)
            except Exception as e:
                log(f"Failed to export final chunk: {str(e)}", "error")
            
            del current_chunk
            import gc
            gc.collect()
            
        if not temp_chunk_paths:
            log("No audio files could be processed. Aborting.", "error")
            status_label.value = t["fail_process"]
            progress_bar.value = 0
            generate_btn.disabled = False
            generate_btn.content.content.value = t["generate_btn"]
            app_state["is_processing"] = False
            safe_update()
            return
            
        status_label.value = t["concat_phase"]
        progress_bar.value = None
        safe_update()
        time.sleep(0.05)
        
        timestamp = int(time.time())
        mix_filename = f"mix_{timestamp}.mp3"
        out_filepath = os.path.join(assets_dir, mix_filename)
        
        log(f"Creating final mix {out_filepath} (Duration: {format_time(mix_duration_ms)})...", "info")
        
        try:
            if len(temp_chunk_paths) == 1:
                shutil.copy(temp_chunk_paths[0], out_filepath)
                log("Final MP3 created successfully from single chunk!", "success")
            else:
                filelist_path = os.path.join(temp_chunks_dir, "filelist.txt")
                with open(filelist_path, "w", encoding="utf-8") as f:
                    for cp in temp_chunk_paths:
                        normalized_path = os.path.abspath(cp).replace("\\\\", "/")
                        f.write(f"file '{normalized_path}'\n")
                
                import subprocess
                ffmpeg_cmd = [
                    "ffmpeg", "-y",
                    "-nostdin",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", filelist_path,
                    "-c:a", "libmp3lame",
                    "-b:a", "192k",
                    out_filepath
                ]
                
                log("Running FFmpeg concat demuxer...", "info")
                time.sleep(0.05)  # Yield GIL to let Flet update the UI
                subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
                log("Final MP3 concatenated successfully using FFmpeg!", "success")
                
            # Save corresponding .xsp metadata file!
            metadata_filename = f"mix_{timestamp}.xsp"
            metadata_filepath = os.path.join(assets_dir, metadata_filename)
            import json
            metadata = {
                "keywords": keywords,
                "total_duration_ms": mix_duration_ms,
                "tracks": [
                    {
                        "title": track.title,
                        "video_id": track.video_id,
                        "original_duration_ms": track.original_duration_ms,
                        "cropped_duration_ms": track.cropped_duration_ms,
                        "start_time_ms": track.start_time_ms
                    }
                    for track in tracks_meta
                ]
            }
            with open(metadata_filepath, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4, ensure_ascii=False)
            log(f"Saved mix playlist metadata to: {metadata_filename}", "success")
        except Exception as e:
            log(f"Failed to export mix: {str(e)}", "error")
            status_label.value = t["fail_export"]
            progress_bar.value = 0
            generate_btn.disabled = False
            generate_btn.content.content.value = t["generate_btn"]
            app_state["is_processing"] = False
            safe_update()
            return
            
        if clean_cache:
            status_label.value = t["cleanup_phase"]
            safe_update()
            time.sleep(0.05)
            try:
                shutil.rmtree(download_dir)
                os.makedirs(download_dir, exist_ok=True)
                log("Temporary download cache cleaned.", "success")
            except Exception as e:
                log(f"Failed to clean cache: {str(e)}", "warning")
                
        app_state["tracks"] = tracks_meta
        app_state["total_duration_ms"] = mix_duration_ms
        app_state["audio_path"] = f"file:///{os.path.abspath(out_filepath).replace('\\', '/')}"
        app_state["active_track_idx"] = 0
        app_state["active_keywords"] = keywords
        
        status_label.value = t["success_phase"]
        progress_bar.value = 1.0
        
        player_mix_title.value = f"Mix: {', '.join(keywords)}" if lang == "en" else f"Μίξη: {', '.join(keywords)}"
        player_mix_subtitle.value = f"{t['duration_prefix']}: {format_time(mix_duration_ms)} | {len(tracks_meta)} {t['songs_suffix']}"
        
        player_slider.max = mix_duration_ms
        player_slider.value = 0
        current_time_text.value = "00:00"
        total_time_text.value = format_time(mix_duration_ms)
        
        async def pause_audio():
            await audio_player.pause()
        page.run_task(pause_audio)
        
        audio_player.src = app_state["audio_path"]
        
        update_playlist_ui()
        
        right_panel_placeholder.visible = False
        player_card.visible = True
        playlist_card.visible = True
        save_mix_btn.visible = True
        edit_current_mix_btn.visible = True
        
        generate_btn.disabled = False
        generate_btn.content.content.value = t["generate_btn"]
        
        app_state["is_processing"] = False
        log(f"Mix loaded into player! Path: {app_state['audio_path']}", "success")
        
        safe_update()
        
        time.sleep(0.5)
        async def play_audio():
            await audio_player.play()
        page.run_task(play_audio)

    def start_mixing(e):
        if app_state["is_processing"]:
            return
            
        kw_text = keywords_input.value.strip()
        if not kw_text:
            log("Validation Error: Please enter at least one keyword.", "error")
            return
            
        # Save last search query
        try:
            with open("assets/last_query.txt", "w", encoding="utf-8") as f:
                f.write(kw_text)
        except:
            pass
            
        # Parse keywords
        keywords = [k.strip() for k in kw_text.split(",") if k.strip()]
        if not keywords:
            log("Validation Error: Please enter valid keywords.", "error")
            return
            
        songs_per_kw = int(songs_slider.value)
        max_dur = int(duration_slider.value)
        crossfade = int(crossfade_slider.value)
        normalize_val = normalize_checkbox.value
        clean_cache = cleanup_checkbox.value
        
        # Run in thread
        threading.Thread(
            target=process_mix_thread,
            args=(keywords, songs_per_kw, max_dur, crossfade, normalize_val, clean_cache),
            daemon=True
        ).start()

    generate_btn.on_click = start_mixing

    # Load mix from metadata file (.xsp)
    def load_mix_from_metadata(file_path):
        import json
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                
            tracks_data = metadata.get("tracks", [])
            total_duration_ms = metadata.get("total_duration_ms", 0)
            keywords = metadata.get("keywords", [])
            
            # Find corresponding MP3 path (same directory)
            mp3_path = file_path.rsplit(".", 1)[0] + ".mp3"
            if not os.path.exists(mp3_path):
                # Try finding in assets folder
                filename_base = os.path.basename(file_path).rsplit(".", 1)[0]
                mp3_path = os.path.join("assets", filename_base + ".mp3")
                if not os.path.exists(mp3_path):
                    log(f"Associated MP3 file not found: {mp3_path}", "error")
                    return
            
            # Reconstruct app state
            app_state["tracks"] = [
                TrackMetadata(
                    title=t.get("title", "Unknown"),
                    video_id=t.get("video_id", ""),
                    original_duration_ms=t.get("original_duration_ms", 0),
                    cropped_duration_ms=t.get("cropped_duration_ms", 0),
                    start_time_ms=t.get("start_time_ms", 0)
                )
                for t in tracks_data
            ]
            app_state["total_duration_ms"] = total_duration_ms
            app_state["audio_path"] = f"file:///{os.path.abspath(mp3_path).replace('\\', '/')}"
            app_state["active_track_idx"] = 0
            app_state["active_keywords"] = keywords
            
            # Update UI controls
            lang = app_state["lang"]
            t = LOCALIZATION[lang]
            
            # Re-fill the keywords search input to remember/match what's loaded
            if keywords:
                keywords_input.value = ", ".join(keywords)
            
            player_mix_title.value = f"Mix: {', '.join(keywords)}" if lang == "en" else f"Μίξη: {', '.join(keywords)}"
            
            duration_text = format_time(total_duration_ms)
            songs_count = len(app_state["tracks"])
            player_mix_subtitle.value = f"{t['duration_prefix']}: {duration_text} | {songs_count} {t['songs_suffix']}"
            
            player_slider.max = total_duration_ms
            player_slider.value = 0
            current_time_text.value = "00:00"
            total_time_text.value = duration_text
            
            # Recreate success state for progress bar and status label
            status_label.value = t["success_phase"]
            progress_bar.value = 1.0
            
            # Reset duplicates button
            duplicates_btn.visible = False
            app_state["rejected_tracks"] = []
            
            # Update timeline playlist
            update_playlist_ui()
            
            # Show player & hide placeholder
            right_panel_placeholder.visible = False
            player_card.visible = True
            playlist_card.visible = True
            save_mix_btn.visible = True
            edit_current_mix_btn.visible = True
            
            # Set audio player src and start playing!
            async def load_and_play():
                await audio_player.pause()
                audio_player.src = app_state["audio_path"]
                audio_player.update()
                safe_update()
                await asyncio.sleep(0.5)
                await audio_player.play()
                
            page.run_task(load_and_play)
            
            log(f"Successfully loaded mix: {os.path.basename(mp3_path)}", "success")
            safe_update()
            
        except Exception as e:
            log(f"Failed to load mix from metadata: {str(e)}", "error")

    async def open_mix_clicked(e):
        file_picker = ft.FilePicker()
        files = await file_picker.pick_files(
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xsp", "spymix"],
            dialog_title="Select Mix File / Επιλογή αρχείου μίξης"
        )
        if not files:
            return
        file_path = files[0].path
        if not file_path or not (file_path.endswith(".xsp") or file_path.endswith(".spymix")):
            log("Invalid file selected. Please choose a .xsp or .spymix file.", "error")
            return
            
        if file_path.endswith(".spymix"):
            import zipfile
            import uuid
            # Clean up old extracted files first to save space
            cleanup_temp_extracted()
            
            # Create a unique folder for this extraction
            temp_id = str(uuid.uuid4())[:8]
            extract_dir = os.path.join("assets", "temp_extracted", f"mix_{temp_id}")
            os.makedirs(extract_dir, exist_ok=True)
            
            try:
                log("Extracting .spymix package...", "info")
                with zipfile.ZipFile(file_path, 'r') as zipf:
                    zipf.extractall(extract_dir)
                
                # Look for the .xsp file inside the extracted directory
                xsp_files = [f for f in os.listdir(extract_dir) if f.endswith(".xsp")]
                if not xsp_files:
                    log("Invalid .spymix package: no metadata file (.xsp) found inside.", "error")
                    return
                
                # Find corresponding .mp3
                mp3_files = [f for f in os.listdir(extract_dir) if f.endswith(".mp3")]
                if not mp3_files:
                    log("Invalid .spymix package: no audio file (.mp3) found inside.", "error")
                    return
                
                # Rename to standard mix.xsp and mix.mp3 to ensure they load properly
                xsp_old = os.path.join(extract_dir, xsp_files[0])
                mp3_old = os.path.join(extract_dir, mp3_files[0])
                
                xsp_new = os.path.join(extract_dir, "mix.xsp")
                mp3_new = os.path.join(extract_dir, "mix.mp3")
                
                if xsp_old != xsp_new:
                    if os.path.exists(xsp_new):
                        os.remove(xsp_new)
                    os.rename(xsp_old, xsp_new)
                if mp3_old != mp3_new:
                    if os.path.exists(mp3_new):
                        os.remove(mp3_new)
                    os.rename(mp3_old, mp3_new)
                
                load_mix_from_metadata(xsp_new)
            except Exception as ex:
                log(f"Failed to extract .spymix: {str(ex)}", "error")
        else:
            load_mix_from_metadata(file_path)
        
    open_mix_btn.on_click = open_mix_clicked

    # Load tracks from BeatList (.beatlist) and start mix thread
    def load_mix_from_beatlist(file_path):
        import json
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tracks_data = json.load(f)
                
            if not isinstance(tracks_data, list):
                log("Invalid BeatList format. Expected a JSON list of tracks.", "error")
                return
                
            imported_tracks = []
            for track in tracks_data:
                v_id = track.get("id")
                title = track.get("title")
                duration = track.get("duration")
                
                # Skip manual local additions or invalid IDs
                if not v_id or str(v_id).startswith("local:"):
                    continue
                
                imported_tracks.append({
                    "id": v_id,
                    "title": title,
                    "duration": duration
                })
                
            if not imported_tracks:
                log("No valid YouTube tracks found in the selected BeatList.", "error")
                return
                
            playlist_name = os.path.basename(file_path).rsplit(".", 1)[0]
            
            # Use current slider settings for mixing configuration
            songs_per_kw = len(imported_tracks)
            max_dur = int(duration_slider.value)
            crossfade = int(crossfade_slider.value)
            normalize_val = normalize_checkbox.value
            clean_cache = cleanup_checkbox.value
            
            log(f"Importing BeatList '{playlist_name}' with {len(imported_tracks)} tracks...", "info_cyan")
            
            # Start the mix thread directly with imported_tracks, skipping curation dialog/editor
            threading.Thread(
                target=process_mix_thread,
                args=([f"Import: {playlist_name}"], songs_per_kw, max_dur, crossfade, normalize_val, clean_cache),
                kwargs={"imported_tracks": imported_tracks, "skip_curation": True},
                daemon=True
            ).start()
            
        except Exception as e:
            log(f"Failed to import BeatList: {str(e)}", "error")

    async def import_beatlist_clicked(e):
        file_picker = ft.FilePicker()
        files = await file_picker.pick_files(
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["beatlist"],
            dialog_title="Select BeatList File / Επιλογή αρχείου BeatList"
        )
        if not files:
            return
        file_path = files[0].path
        if not file_path or not file_path.endswith(".beatlist"):
            log("Invalid file selected. Please choose a .beatlist file.", "error")
            return
        show_beatlist_action_dialog(file_path)
        
    import_beatlist_btn.on_click = import_beatlist_clicked

    # App Layout Construction
    app_title_text = ft.Text("SpyMixer", size=28, weight="bold", color=ft.Colors.WHITE)
    app_subtitle_text = ft.Text("YouTube Playlist Crossfade Generator", size=13, color="#8F8F9F")
    
    # Toggle language functions
    def update_ui_texts():
        lang = app_state["lang"]
        t = LOCALIZATION[lang]
        
        # Page Title
        page.title = f"{t['title']} v{VERSION}"
        
        # Header
        app_title_text.value = f"{t['app_title']} v{VERSION}"
        app_subtitle_text.value = t["app_subtitle"]
        lang_text.value = "EN" if lang == "el" else "EL"
        
        # Left Panel Controls
        left_panel_title.value = t["config_title"]
        keywords_input.label = t["keywords_label"]
        keywords_input.hint_text = t["keywords_hint"]
        songs_header.value = t["songs_label"]
        songs_slider.label = t["songs_slider_label"]
        duration_header.value = t["duration_label"]
        duration_slider.label = t["duration_slider_label"]
        crossfade_header.value = t["crossfade_label"]
        crossfade_slider.label = t["crossfade_slider_label"]
        normalize_checkbox.label = t["normalize_label"]
        cleanup_checkbox.label = t["clean_label"]
        
        # Generate Button
        if app_state["is_processing"]:
            generate_btn.content.content.value = t["processing_btn"]
        else:
            generate_btn.content.content.value = t["generate_btn"]
            
        # Open Mix Button
        open_mix_btn.content.content.value = t["open_mix_btn"]
        
        # Import Beatlist Button
        import_beatlist_btn.content.content.value = t["import_beatlist_btn"]
            
        # Log Title
        logs_header_text.value = t["logs_label"]
        
        # Status Label (if idle)
        if not app_state["is_processing"] and not app_state["tracks"]:
            status_label.value = t["ready_to_mix"]
            
        # Right Panel Placeholder
        placeholder_title.value = t["no_active_mix_title"]
        placeholder_sub.value = t["no_active_mix_sub"]
        
        # Player Details (if loaded)
        if app_state["tracks"]:
            active_kws = app_state.get("active_keywords", [])
            player_mix_title.value = f"Mix: {', '.join(active_kws)}" if lang == "en" else f"Μίξη: {', '.join(active_kws)}"
            
            duration_text = format_time(app_state["total_duration_ms"])
            songs_count = len(app_state["tracks"])
            player_mix_subtitle.value = f"{t['duration_prefix']}: {duration_text} | {songs_count} {t['songs_suffix']}"
            
        # Duplicates button badge
        if app_state["rejected_tracks"]:
            duplicates_text.value = f"{t['duplicates_btn']} ({len(app_state['rejected_tracks'])})"
            
        # Playlist Card Header
        playlist_header_text.value = t["playlist_header"]
        
        # Help Dialog and Button
        help_dialog_title.value = t["help_title"]
        help_dialog_close_btn.content = t["help_close"]
        help_dialog_content.value = t["help_text"] + f"\n\n*(Version {VERSION})*"
        help_btn.tooltip = t["help_tooltip"]
        
        # Dialog Title & Action Button
        dup_dialog_title_text.value = t["dup_dialog_title"]
        dup_dialog_close_btn.content = t["dup_close"]
        
        # Tooltips
        play_pause_btn.tooltip = t["play_tooltip"]
        prev_btn.tooltip = t["prev_tooltip"]
        next_btn.tooltip = t["next_tooltip"]
        volume_icon.tooltip = t["volume_tooltip"]
        save_mix_btn.tooltip = t["save_mix_tooltip"]
        edit_current_mix_btn.tooltip = t["edit_mix_tooltip"]
        
        # Curation Dialog
        if curation_dialog.open:
            populate_curation_dialog()
            
        safe_update()

    def toggle_language(e):
        app_state["lang"] = "el" if app_state["lang"] == "en" else "en"
        update_ui_texts()
        
    lang_text = ft.Text("EL", color="#00CEC9", weight="bold")
    lang_btn = ft.TextButton(
        content=lang_text,
        icon=ft.Icons.TRANSLATE_ROUNDED,
        icon_color="#00CEC9",
        on_click=toggle_language,
    )
    
    header = ft.Container(
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.MUSIC_VIDEO_ROUNDED, color="#8E2DE2", size=40),
                        ft.Column(
                            [
                                app_title_text,
                                app_subtitle_text
                            ],
                            spacing=0
                        )
                    ],
                    alignment="start",
                    vertical_alignment="center"
                ),
                ft.Row(
                    [
                        lang_btn,
                        help_btn
                    ],
                    spacing=10,
                    alignment="end",
                    vertical_alignment="center"
                )
            ],
            alignment="spaceBetween",
            vertical_alignment="center"
        ),
        margin=ft.margin.Margin.only(bottom=20)
    )

    left_panel_title = ft.Text("Mix Configuration", size=18, weight="bold")
    songs_header = ft.Text("Songs per keyword", size=14, weight="w500")
    duration_header = ft.Text("Max song duration", size=14, weight="w500")
    crossfade_header = ft.Text("Crossfade duration", size=14, weight="w500")
    logs_header_text = ft.Text("Log Output", size=14, weight="w500")

    left_panel = ft.Container(
        content=ft.Column(
            [
                left_panel_title,
                ft.Divider(height=1, color="#252535"),
                ft.Row([keywords_input]),
                
                songs_header,
                songs_slider,
                
                duration_header,
                duration_slider,
                
                crossfade_header,
                crossfade_slider,
                
                ft.Row([
                    normalize_checkbox,
                    cleanup_checkbox
                ], alignment="spaceBetween"),
                
                ft.Row([generate_btn]),
                ft.Row([
                    open_mix_btn,
                    import_beatlist_btn
                ], spacing=10),
                
                ft.Divider(height=1, color="#252535"),
                status_label,
                progress_bar,
                
                logs_header_text,
                log_container
            ],
            spacing=14,
            scroll="adaptive"
        ),
        width=450,
        bgcolor="#121217",
        border_radius=20,
        padding=24,
        border=ft.Border.all(1, "#252535"),
    )

    page.add(
        ft.Column(
            [
                header,
                ft.Row(
                    [
                        left_panel,
                        ft.VerticalDivider(width=10, color=ft.Colors.TRANSPARENT),
                        ft.Stack(
                            [
                                right_panel_placeholder,
                                right_panel
                            ],
                            expand=True
                        )
                    ],
                    expand=True
                )
            ],
            expand=True
        )
    )
    debug_log("Step 8: page.add completed")
    
    # Custom Gradient on Button container decoration
    generate_btn.style.bgcolor = ft.Colors.TRANSPARENT
    generate_btn.content = ft.Container(
        content=ft.Text("GENERATE MIX 🚀", size=16, weight="bold", color=ft.Colors.WHITE),
        alignment=ft.Alignment(0, 0),
        padding=ft.padding.Padding.symmetric(vertical=15),
        gradient=ft.LinearGradient(
            colors=["#8E2DE2", "#4A00E0"]
        ),
        border_radius=10
    )
    
    open_mix_btn.style.bgcolor = ft.Colors.TRANSPARENT
    open_mix_btn.content = ft.Container(
        content=ft.Text("ΑΝΟΙΓΜΑ ΜΙΞ 📂", size=14, weight="bold", color=ft.Colors.WHITE),
        alignment=ft.Alignment(0, 0),
        padding=ft.padding.Padding.symmetric(vertical=15),
        gradient=ft.LinearGradient(
            colors=["#00CEC9", "#008080"]
        ),
        border_radius=10
    )
    
    import_beatlist_btn.style.bgcolor = ft.Colors.TRANSPARENT
    import_beatlist_btn.content = ft.Container(
        content=ft.Text("ΕΙΣΑΓΩΓΗ BEATS 🎧", size=14, weight="bold", color=ft.Colors.WHITE),
        alignment=ft.Alignment(0, 0),
        padding=ft.padding.Padding.symmetric(vertical=15),
        gradient=ft.LinearGradient(
            colors=["#FD79A8", "#E84393"]
        ),
        border_radius=10
    )
    
    # Initialize UI texts
    update_ui_texts()
    debug_log("Step 9: update_ui_texts completed - startup finished")
    
    try:
        import pyi_splash
        pyi_splash.close()
    except ImportError:
        pass

if __name__ == "__main__":
    import sys
    import os
    if getattr(sys, 'frozen', False):
        assets_dir = os.path.join(sys._MEIPASS, "assets")
    else:
        assets_dir = "assets"
    ft.run(main, assets_dir=assets_dir)
