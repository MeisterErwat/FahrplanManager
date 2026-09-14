import json
import os
import random
import sys
import time
import threading
import urllib.request
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta

APP_NAME = "Fahrplan Manager • MeisterErwat"
APP_VERSION = "6.0"
UPDATE_CONFIG_FILE = "update_config.json"


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = app_dir()
PLAN_FILE = os.path.join(BASE_DIR, "fahrplaene.json")
HISTORY_FILE = os.path.join(BASE_DIR, "fahrten_historie.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "einstellungen.json")

# Fiktive Streckenvorlagen. Keine echten Dienstpläne.
ROUTES = {
    "W2D": {
        "name": "Linie 2 • Wiesenhügel → Domplatz",
        "stops": [
            "Wiesenhügel", "Färberwaidweg", "Abzweig Wiesenhügel",
            "Blücherstraße", "Sozialversicherungszentrum", "Am Schwemmbach",
            "Stadion Ost", "Tschaikowskistraße", "Robert-Koch-Straße",
            "Hauptbahnhof", "Anger", "Fischmarkt/Rathaus", "Domplatz",
        ],
    },
    "D2W": {
        "name": "Linie 2 • Domplatz → Wiesenhügel",
        "stops": [
            "Domplatz", "Fischmarkt/Rathaus", "Anger", "Hauptbahnhof",
            "Robert-Koch-Straße", "Tschaikowskistraße", "Stadion Ost",
            "Am Schwemmbach", "Sozialversicherungszentrum", "Blücherstraße",
            "Abzweig Wiesenhügel", "Färberwaidweg", "Wiesenhügel",
        ],
    },
    "W2S": {
        "name": "Linie 2 • Wiesenhügel → Stadion Ost",
        "stops": [
            "Wiesenhügel", "Färberwaidweg", "Abzweig Wiesenhügel",
            "Blücherstraße", "Sozialversicherungszentrum", "Am Schwemmbach",
            "Stadion Ost",
        ],
    },
    "S2M": {
        "name": "Linie 2 • Stadion Ost → Melchendorf",
        "stops": [
            "Stadion Ost", "Am Schwemmbach", "Sozialversicherungszentrum",
            "Blücherstraße", "Abzweig Wiesenhügel", "Melchendorf",
        ],
    },
    "L3M2D": {
        "name": "Linie 3 • Melchendorf Betriebshof → Domplatz",
        "stops": [
            "Melchendorf Betriebshof", "Melchendorf", "Abzweig Wiesenhügel",
            "Blücherstraße", "Sozialversicherungszentrum", "Am Schwemmbach",
            "Stadion Ost", "Tschaikowskistraße", "Robert-Koch-Straße",
            "Hauptbahnhof", "Anger", "Fischmarkt/Rathaus", "Domplatz",
        ],
    },
    "L3D2M": {
        "name": "Linie 3 • Domplatz → Melchendorf Betriebshof",
        "stops": [
            "Domplatz", "Fischmarkt/Rathaus", "Anger", "Hauptbahnhof",
            "Robert-Koch-Straße", "Tschaikowskistraße", "Stadion Ost",
            "Am Schwemmbach", "Sozialversicherungszentrum", "Blücherstraße",
            "Abzweig Wiesenhügel", "Melchendorf", "Melchendorf Betriebshof",
        ],
    },
}


class FahrplanManager:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        start_w = max(760, min(1420, int(sw * 0.90)))
        start_h = max(500, min(860, int(sh * 0.90)))
        self.root.geometry(f"{start_w}x{start_h}")
        self.root.minsize(760, 500)
        self.root.configure(bg="#EDF2F4")
        self.root.bind("<Configure>", self.on_window_resize)

        self.c = {}

        self.plans = self.load_json(PLAN_FILE, {})
        self.history = self.load_json(HISTORY_FILE, [])
        self.settings = self.load_json(SETTINGS_FILE, {
            "dark_mode": False,
            "show_actual_time": False,
            "route_aliases": {code: code for code in ROUTES},
        })
        if not isinstance(self.plans, dict):
            self.plans = {}
        if not isinstance(self.history, list):
            self.history = []
        if not isinstance(self.settings, dict):
            self.settings = {}
        self.settings.setdefault("dark_mode", False)
        self.settings.setdefault("show_actual_time", False)
        aliases = self.settings.setdefault("route_aliases", {})
        if not isinstance(aliases, dict):
            aliases = {}
            self.settings["route_aliases"] = aliases
        for code in ROUTES:
            aliases.setdefault(code, code)

        self.apply_palette()

        self.code = None
        self.plan = None
        self.current_trip_index = 0

        # Laufender Fahrzustand
        self.running = False
        self.position = 0
        self.started_at = None
        self.elapsed_offset = 0.0
        self.pause_until = None
        self.pause_total = 0
        self.pause_start_deviation = 0
        self.paused = False
        self.emergency_dialog_open = False
        self.doors_open = False
        self.view_locked = False
        self.delay_adjustment = 0
        self.actual_times = {}
        self.arrival_deviations = {}
        self.last_pause_remaining = 0

        self.sidebar = None
        self.content = None
        self.clock_labels = []
        self.active_return_button = None

        # Widgets der Fahreransicht
        self.driver_clock = None
        self.stop_label = None
        self.plan_time_label = None
        self.actual_time_label = None
        self.time_label = None
        self.duration_label = None
        self.pause_label = None
        self.position_label = None
        self.progress = None
        self.back_button = None
        self.next_button = None
        self.door_status = None
        self.map_canvas = None

        self.setup_styles()
        self.build_shell()
        self.show_intro()
        self.root.after(300, self.main_tick)

    # ------------------ Speicher ------------------
    def load_json(self, filename, default):
        if not os.path.exists(filename):
            return default
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return default

    def save_json(self, filename, data):
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            messagebox.showerror("Speicherfehler", f"Datei konnte nicht gespeichert werden:\n{exc}")

    def load_update_config(self):
        default = {"enabled": True, "manifest_url": "https://raw.githubusercontent.com/DEIN-USERNAME/DEIN-REPO/main/update.json"}
        path = os.path.join(BASE_DIR, UPDATE_CONFIG_FILE)
        data = self.load_json(path, default)
        return data if isinstance(data, dict) else default

    @staticmethod
    def version_tuple(value):
        nums = []
        for part in str(value).split('.'):
            try: nums.append(int(part))
            except ValueError: nums.append(0)
        return tuple((nums + [0,0,0])[:3])

    def check_for_updates(self, manual=False):
        cfg = self.load_update_config()
        url = str(cfg.get("manifest_url", "")).strip()
        if not cfg.get("enabled", True) or not url or "DEIN-USERNAME" in url or "DEIN-REPO" in url:
            if manual: messagebox.showinfo("Updates", "Bitte zuerst die Manifest-URL in update_config.json eintragen.")
            return
        def worker():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "FahrplanManager-Updater"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = json.loads(r.read().decode("utf-8"))
                remote = str(data.get("version", "")).strip()
                download = str(data.get("download_url", "")).strip()
                notes = str(data.get("notes", "")).strip()
                if remote and download and self.version_tuple(remote) > self.version_tuple(APP_VERSION):
                    self.root.after(0, lambda: self.offer_update(remote, download, notes))
                elif manual:
                    self.root.after(0, lambda: messagebox.showinfo("Updates", f"Du verwendest bereits Version {APP_VERSION}."))
            except Exception as exc:
                if manual:
                    self.root.after(0, lambda: messagebox.showwarning("Updates", f"Updateprüfung fehlgeschlagen.\n\n{exc}"))
        threading.Thread(target=worker, daemon=True).start()

    def offer_update(self, remote, download, notes):
        text = f"Neue Version {remote} verfügbar (aktuell {APP_VERSION})."
        if notes: text += f"\n\n{notes}"
        if not messagebox.askyesno("Update verfügbar", text + "\n\nJetzt aktualisieren?"): return
        updater = os.path.join(BASE_DIR, "Updater.exe")
        if not os.path.exists(updater):
            messagebox.showerror("Updater fehlt", "Updater.exe wurde nicht gefunden. Baue die Windows-Version mit build_windows.bat erneut.")
            return
        if not getattr(sys, "frozen", False):
            messagebox.showinfo("Update", "Das automatische EXE-Update funktioniert erst in der gebauten Windows-Version. Erstelle dafür die EXE mit build_windows.bat.")
            return
        try:
            import subprocess
            subprocess.Popen([updater, sys.executable, download, remote], close_fds=True)
            self.root.destroy()
        except Exception as exc:
            messagebox.showerror("Update", f"Updater konnte nicht gestartet werden.\n\n{exc}")

    def unique_code(self):
        while True:
            code = str(random.randint(100000, 999999))
            if code not in self.plans:
                return code

    # ------------------ Theme / responsive window ------------------
    def apply_palette(self):
        if self.settings.get("dark_mode"):
            self.c.update({
                "bg": "#11181D", "panel": "#1A242A", "nav": "#071118", "nav2": "#183743",
                "text": "#EEF6F8", "muted": "#9DB0B8", "teal": "#39B9C7", "teal_dark": "#18828E",
                "coral": "#F0776D", "gold": "#E2B55A", "green": "#47C58E", "amber": "#E09A38",
                "red": "#F06A79", "line": "#34454E", "soft": "#223139",
            })
        else:
            self.c.update({
                "bg": "#EDF2F4", "panel": "#FFFFFF", "nav": "#102A36", "nav2": "#1B4150",
                "text": "#17262E", "muted": "#71818A", "teal": "#0A7280", "teal_dark": "#075560",
                "coral": "#E05D52", "gold": "#C48B31", "green": "#14845A", "amber": "#BF7808",
                "red": "#B72D3C", "line": "#D5E0E5", "soft": "#F6F9FA",
            })
        try:
            self.root.configure(bg=self.c["bg"])
        except tk.TclError:
            pass

    def on_window_resize(self, event):
        if event.widget is not self.root:
            return
        # Kleine Bildschirme bekommen automatisch eine schmalere Navigation.
        try:
            width = self.root.winfo_width()
            target = 195 if width < 1000 else 225 if width < 1200 else 245
            if self.sidebar and int(self.sidebar.cget("width")) != target:
                self.sidebar.config(width=target)
        except tk.TclError:
            pass

    def route_display_name(self, code):
        return str(self.settings.get("route_aliases", {}).get(code, code))

    def route_choices(self):
        return [f"{self.route_display_name(code)}  •  {code}" for code in ROUTES]

    def route_code_from_display(self, display):
        for code in ROUTES:
            if display == f"{self.route_display_name(code)}  •  {code}":
                return code
        return next(iter(ROUTES))

    def apply_theme_to_widget_tree(self, widget):
        try:
            cls = widget.winfo_class()
            if cls in ("Frame", "Labelframe"):
                widget.configure(bg=self.c["panel"] if widget is not self.content and widget is not self.sidebar else self.c["bg" if widget is self.content else "nav"])
            elif cls == "Label":
                widget.configure(bg=self.c["panel"] if widget.master is not self.content else self.c["bg"], fg=self.c["text"])
            elif cls == "Canvas":
                widget.configure(bg=self.c["soft"])
        except (tk.TclError, AttributeError):
            pass
        for child in widget.winfo_children():
            self.apply_theme_to_widget_tree(child)

    # ------------------ Styles / Shell ------------------
    def setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=(12, 8),
                        background=self.c["panel"], foreground=self.c["text"])
        style.map("TButton", background=[("active", self.c["soft"])])
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), foreground="white",
                        background=self.c["teal"], padding=(14, 9))
        style.map("Primary.TButton", background=[("active", self.c["teal_dark"]), ("disabled", "#78878D")])
        style.configure("Danger.TButton", font=("Segoe UI", 10, "bold"), foreground="white",
                        background=self.c["red"], padding=(14, 9))
        style.map("Danger.TButton", background=[("active", "#8F2130")])
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=34, background=self.c["panel"],
                        fieldbackground=self.c["panel"], foreground=self.c["text"])
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background=self.c["soft"], foreground=self.c["text"])
        style.configure("TEntry", fieldbackground=self.c["panel"], foreground=self.c["text"])
        style.configure("TCombobox", fieldbackground=self.c["panel"], background=self.c["panel"], foreground=self.c["text"])

    def build_shell(self):
        self.sidebar = tk.Frame(self.root, bg=self.c["nav"], width=245)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.content = tk.Frame(self.root, bg=self.c["bg"])
        self.content.pack(side="left", fill="both", expand=True)
        self.build_sidebar()

    def build_sidebar(self):
        tk.Label(self.sidebar, text="FAHRPLAN\nMANAGER", bg=self.c["nav"], fg="white",
                 font=("Segoe UI", 20, "bold"), justify="left").pack(anchor="w", padx=20, pady=(24, 2))
        tk.Label(self.sidebar, text="MEISTERERWAT • SIMULATION", bg=self.c["nav"], fg="#B5C7CE",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=21, pady=(0, 20))

        menu = [
            ("⌂   Startseite", self.show_home),
            ("＋   Neue Fahrt", self.show_new_trip),
            ("▣   Code öffnen", self.show_open_code),
            ("☰   Meine Fahrpläne", self.show_saved),
            ("◷   Fahrt-Historie", self.show_history),
        ]
        for text, command in menu:
            tk.Button(self.sidebar, text=text, command=command, anchor="w", bd=0,
                      bg=self.c["nav"], fg="white", activebackground=self.c["nav2"],
                      activeforeground="white", font=("Segoe UI", 10, "bold"),
                      padx=20, pady=12).pack(fill="x")

        self.active_return_button = tk.Button(
            self.sidebar, text="↩   Aktive Fahrt", command=self.return_to_active,
            anchor="w", bd=0, bg=self.c["nav"], fg="#7FD7DD", activebackground=self.c["nav2"],
            activeforeground="white", font=("Segoe UI", 10, "bold"), padx=20, pady=12,
        )
        self.active_return_button.pack(fill="x", pady=(8, 0))
        tk.Button(self.sidebar, text="↻   Nach Updates suchen", command=lambda: self.check_for_updates(manual=True), anchor="w", bd=0,
                  bg=self.c["nav"], fg="white", activebackground=self.c["nav2"], activeforeground="white",
                  font=("Segoe UI", 9, "bold"), padx=20, pady=9).pack(fill="x", side="bottom", pady=(0, 132))
        tk.Button(self.sidebar, text="⚙   Einstellungen", command=self.open_settings, anchor="w", bd=0,
                  bg=self.c["nav"], fg="white", activebackground=self.c["nav2"], activeforeground="white",
                  font=("Segoe UI", 10, "bold"), padx=20, pady=12).pack(fill="x", side="bottom", pady=(0, 80))

        tk.Label(self.sidebar,
                 text="Fiktive Simulation\nKeine echten Dienstpläne.\nKein offizielles EVAG-System.",
                 bg=self.c["nav"], fg="#8FA6AF", font=("Segoe UI", 8), justify="left")\
            .pack(side="bottom", anchor="w", padx=20, pady=20)
        self.update_active_nav()

    def update_active_nav(self):
        if not self.active_return_button:
            return
        if self.running:
            self.active_return_button.config(state="normal", bg=self.c["nav2"], fg="white")
        else:
            self.active_return_button.config(state="disabled", bg=self.c["nav"], fg="#57727D")

    def clear_content(self):
        # Der globale Timer läuft absichtlich weiter, damit eine aktive Fahrt auch
        # dann korrekt tickt, wenn man kurz die Startseite öffnet.
        for child in self.content.winfo_children():
            child.destroy()
        self.clock_labels = []
        self.driver_clock = None
        self.stop_label = None
        self.plan_time_label = None
        self.actual_time_label = None
        self.time_label = None
        self.duration_label = None
        self.pause_label = None
        self.position_label = None
        self.progress = None
        self.back_button = None
        self.next_button = None
        self.door_status = None
        self.map_canvas = None

    def card(self, parent):
        return tk.Frame(parent, bg=self.c["panel"], highlightbackground=self.c["line"], highlightthickness=1)

    def header(self, title, subtitle=""):
        top = tk.Frame(self.content, bg=self.c["bg"])
        top.pack(fill="x", padx=28, pady=(16, 4))
        brand = tk.Frame(top, bg=self.c["bg"])
        brand.pack(side="left")
        tk.Label(brand, text="SWE", bg=self.c["coral"], fg="white", font=("Segoe UI", 9, "bold"),
                 padx=7, pady=3).pack(side="left", padx=(0, 4))
        tk.Label(brand, text="EVAG", bg=self.c["teal"], fg="white", font=("Segoe UI", 9, "bold"),
                 padx=7, pady=3).pack(side="left", padx=(0, 12))
        tk.Label(brand, text=title, bg=self.c["bg"], fg=self.c["text"],
                 font=("Segoe UI", 23, "bold")).pack(side="left")
        settings_button = tk.Button(top, text="⚙", command=self.open_settings, bd=0,
                                     bg=self.c["bg"], fg=self.c["text"], activebackground=self.c["soft"],
                                     activeforeground=self.c["teal"], font=("Segoe UI", 14, "bold"), padx=6, pady=2)
        settings_button.pack(side="right", padx=(10, 0))
        clock = tk.Label(top, text=datetime.now().strftime("%H:%M:%S"), bg=self.c["bg"],
                         fg=self.c["text"], font=("Segoe UI", 16, "bold"))
        clock.pack(side="right")
        self.clock_labels.append(clock)
        if subtitle:
            tk.Label(self.content, text=subtitle, bg=self.c["bg"], fg=self.c["muted"],
                     font=("Segoe UI", 10)).pack(anchor="w", padx=30, pady=(0, 8))

    def main_tick(self):
        now_text = datetime.now().strftime("%H:%M:%S")
        for label in list(self.clock_labels):
            try:
                label.config(text=now_text)
            except tk.TclError:
                pass
        if self.running:
            self.tick_driver_state()
        self.root.after(500, self.main_tick)

    # ------------------ Intro / Home ------------------
    def show_intro(self):
        self.clear_content()
        tk.Frame(self.content, bg=self.c["coral"], height=8).pack(fill="x")
        area = tk.Frame(self.content, bg=self.c["bg"])
        area.pack(fill="both", expand=True, padx=50, pady=30)
        brand = tk.Frame(area, bg=self.c["bg"])
        brand.pack(pady=(18, 8))
        tk.Label(brand, text="SWE", bg=self.c["coral"], fg="white", font=("Segoe UI", 12, "bold"),
                 padx=12, pady=5).pack(side="left", padx=4)
        tk.Label(brand, text="EVAG", bg=self.c["teal"], fg="white", font=("Segoe UI", 12, "bold"),
                 padx=12, pady=5).pack(side="left", padx=4)
        tk.Label(area, text="FAHRPLAN MANAGER", bg=self.c["bg"], fg=self.c["text"],
                 font=("Segoe UI", 32, "bold")).pack(pady=(10, 3))
        tk.Label(area, text="ULTIMATE 6 • FIKTIVE STRASSENBAHN-SIMULATION", bg=self.c["bg"],
                 fg=self.c["teal"], font=("Segoe UI", 10, "bold")).pack(pady=(0, 22))
        panel = self.card(area)
        panel.pack(fill="x", padx=100)
        tk.Label(panel, text="© MeisterErwat", bg=self.c["panel"], fg=self.c["text"],
                 font=("Segoe UI", 17, "bold")).pack(pady=(24, 8))
        tk.Label(panel,
                 text=("Dieses Programm ist eine fiktive Simulation. Es werden keine echten Dienstpläne\n"
                       "bereitgestellt. Für Geräte, Daten oder Systeme wird – soweit gesetzlich zulässig –\n"
                       "keine Haftung übernommen."),
                 bg=self.c["panel"], fg=self.c["muted"], font=("Segoe UI", 10), justify="center").pack(padx=30, pady=(0, 24))
        tk.Label(area, text="Bereit für deine nächste Fahrt?", bg=self.c["bg"], fg=self.c["text"],
                 font=("Segoe UI", 13, "bold")).pack(pady=(22, 8))
        ttk.Button(area, text="AB GEHT'S, FAHRPLÄNE ERSTELLEN!", style="Primary.TButton",
                   command=self.show_home).pack(ipadx=20, ipady=7)
        tk.Label(area, text="Fiktives Programm • keine offizielle EVAG/SWE-Anwendung",
                 bg=self.c["bg"], fg=self.c["muted"], font=("Segoe UI", 8)).pack(side="bottom", pady=10)

    def show_home(self):
        self.clear_content()
        self.header("STARTSEITE", "Fahrpläne selbst erstellen, simulieren und auswerten.")
        body = tk.Frame(self.content, bg=self.c["bg"])
        body.pack(fill="both", expand=True, padx=28, pady=5)

        if self.running:
            active = self.card(body)
            active.pack(fill="x", pady=(0, 10))
            trip = self.current_trip()
            deviation = self.automatic_deviation()
            tk.Label(active, text="●  FAHRT LÄUFT WEITER", bg=self.c["panel"], fg=self.c["green"],
                     font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=20, pady=(17, 4))
            tk.Label(active, text=f"Linie {self.plan['linie']} • Tram {self.plan['tram']} • {trip['richtung']}",
                     bg=self.c["panel"], fg=self.c["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=20)
            tk.Label(active, text=f"Aktueller Halt: {trip['stops'][self.position]['name']}    •    "
                                 f"Abweichung: {deviation:+d} min",
                     bg=self.c["panel"], fg=self.c["muted"], font=("Segoe UI", 10)).pack(anchor="w", padx=20, pady=(4, 9))
            ttk.Button(active, text="↩  ZUR AKTUELLEN FAHRT", style="Primary.TButton",
                       command=self.return_to_active).pack(anchor="w", padx=20, pady=(0, 16))

        grid = tk.Frame(body, bg=self.c["bg"])
        grid.pack(fill="both", expand=True)
        left = self.card(grid); left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = self.card(grid); right.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="Fahrplan-Zentrale", bg=self.c["panel"], fg=self.c["text"],
                 font=("Segoe UI", 19, "bold")).pack(anchor="w", padx=22, pady=(20, 5))
        tk.Label(left, text="Linie, Fahrzeug, Abfahrt und die Zeiten bestimmst du selbst.",
                 bg=self.c["panel"], fg=self.c["muted"], font=("Segoe UI", 10), wraplength=510,
                 justify="left").pack(anchor="w", padx=22, pady=(0, 14))
        ttk.Button(left, text="＋   Neue Fahrt erstellen", style="Primary.TButton",
                   command=self.show_new_trip).pack(fill="x", padx=22, pady=6)
        ttk.Button(left, text="▣   Persönlichen Code öffnen", command=self.show_open_code).pack(fill="x", padx=22, pady=6)
        tk.Label(left, text="Strecken-Vorlagen", bg=self.c["panel"], fg=self.c["text"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=22, pady=(22, 7))
        for code, route in ROUTES.items():
            row = tk.Frame(left, bg=self.c["panel"]); row.pack(fill="x", padx=22, pady=3)
            tk.Label(row, text=self.route_display_name(code), bg=self.c["gold"], fg="white", font=("Consolas", 9, "bold"),
                     padx=7, pady=3).pack(side="left")
            tk.Label(row, text=route["name"], bg=self.c["panel"], fg=self.c["text"],
                     font=("Segoe UI", 9, "bold"), wraplength=450, justify="left").pack(side="left", padx=8)

        tk.Label(right, text="Systemstatus", bg=self.c["panel"], fg=self.c["text"],
                 font=("Segoe UI", 19, "bold")).pack(anchor="w", padx=22, pady=(20, 15))
        stats = [
            ("Streckenvorlagen", len(ROUTES), self.c["teal"]),
            ("Eigene Fahrpläne", len(self.plans), self.c["green"]),
            ("Gespeicherte Fahrten", sum(x.get("typ") == "FAHRT" for x in self.history), self.c["teal"]),
            ("Notfallmeldungen", sum(x.get("typ") == "NOTFALL" for x in self.history), self.c["red"]),
        ]
        for label, value, color in stats:
            row = tk.Frame(right, bg=self.c["panel"]); row.pack(fill="x", padx=22, pady=8)
            tk.Label(row, text=label, bg=self.c["panel"], fg=self.c["muted"]).pack(side="left")
            tk.Label(row, text=str(value), bg=self.c["panel"], fg=color,
                     font=("Segoe UI", 12, "bold")).pack(side="right")

    # ------------------ Neue Fahrt ------------------
    def show_new_trip(self):
        self.clear_content()
        self.header("NEUE FAHRT", "Strecke wählen – Linie, Tram/Fahrzeug und Abfahrt selbst festlegen.")
        outer = tk.Frame(self.content, bg=self.c["bg"])
        outer.pack(fill="both", expand=True, padx=28, pady=3)

        top = self.card(outer); top.pack(fill="x", pady=(0, 8))
        top.columnconfigure(5, weight=1)
        tk.Label(top, text="Strecke", bg=self.c["panel"], fg=self.c["muted"], font=("Segoe UI", 9, "bold")).grid(row=0, column=0, padx=10, pady=(11, 3), sticky="w")
        self.route_var = tk.StringVar(value=self.route_choices()[0])
        self.route_combo = ttk.Combobox(top, textvariable=self.route_var, values=self.route_choices(), state="readonly", width=22)
        self.route_combo.grid(row=1, column=0, padx=10, pady=(0, 11), sticky="w")
        self.route_combo.bind("<<ComboboxSelected>>", lambda _e: self.populate_new_rows())
        self.route_label = tk.Label(top, text=ROUTES["W2D"]["name"], bg=self.c["panel"], fg=self.c["text"],
                                    font=("Segoe UI", 11, "bold"), wraplength=360, justify="left")
        self.route_label.grid(row=1, column=1, padx=8, pady=(0, 11), sticky="w")

        self.line_var = tk.StringVar()
        self.vehicle_var = tk.StringVar()
        self.departure_var = tk.StringVar()
        for col, label, var, width in [
            (2, "Linie", self.line_var, 12),
            (3, "Tram / Fahrzeug", self.vehicle_var, 18),
            (4, "Abfahrt (HH:MM)", self.departure_var, 13),
        ]:
            tk.Label(top, text=label, bg=self.c["panel"], fg=self.c["muted"], font=("Segoe UI", 9, "bold")).grid(row=0, column=col, padx=8, pady=(11, 3), sticky="w")
            ttk.Entry(top, textvariable=var, width=width).grid(row=1, column=col, padx=8, pady=(0, 11), sticky="w")

        table_card = self.card(outer); table_card.pack(fill="both", expand=True)
        tk.Label(table_card, text="Haltestellen & Zeitplanung", bg=self.c["panel"], fg=self.c["text"],
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=15, pady=(13, 2))
        tk.Label(table_card,
                 text="Fahrzeit = Minuten bis zur nächsten Haltestelle. Pause = planmäßige Wartezeit nach Ankunft.",
                 bg=self.c["panel"], fg=self.c["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=15, pady=(0, 8))

        canvas = tk.Canvas(table_card, bg=self.c["panel"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(table_card, orient="vertical", command=canvas.yview)
        self.stop_form = tk.Frame(canvas, bg=self.c["panel"])
        self.stop_form.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.stop_form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=5)
        scrollbar.pack(side="right", fill="y", padx=(0, 12), pady=5)
        self.stop_form_canvas = canvas

        bar = tk.Frame(table_card, bg=self.c["panel"])
        bar.pack(fill="x", padx=15, pady=(5, 13))
        ttk.Button(bar, text="↻  Zeiten aktualisieren", command=self.preview_times).pack(side="left")
        ttk.Button(bar, text="Fahrplan speichern", style="Primary.TButton", command=self.save_new_trip).pack(side="right")
        self.stop_rows = []
        self.populate_new_rows()

    def populate_new_rows(self):
        route_code = self.route_code_from_display(self.route_var.get())
        route = ROUTES.get(route_code)
        if not route:
            return
        self.route_label.config(text=route["name"])
        for child in self.stop_form.winfo_children():
            child.destroy()
        self.stop_rows = []

        headers = [("#", 4), ("Haltestelle", 36), ("Fahrzeit", 12), ("Pause", 11), ("Soll Ankunft", 15)]
        for col, (text, width) in enumerate(headers):
            tk.Label(self.stop_form, text=text, bg=self.c["soft"], fg=self.c["muted"],
                     font=("Segoe UI", 9, "bold"), width=width, anchor="w").grid(row=0, column=col, padx=5, pady=5, sticky="ew")
        self.stop_form.columnconfigure(1, weight=1)

        for i, stop in enumerate(route["stops"]):
            travel = tk.StringVar(value="0" if i == 0 else "2")
            pause = tk.StringVar(value="0")
            time_label = tk.Label(self.stop_form, text="--:--", bg=self.c["panel"], fg=self.c["teal"],
                                  font=("Consolas", 10, "bold"), width=15, anchor="w")
            tk.Label(self.stop_form, text=str(i + 1), bg=self.c["panel"], fg=self.c["muted"],
                     font=("Segoe UI", 9, "bold"), width=4, anchor="w").grid(row=i + 1, column=0, padx=5, pady=4, sticky="w")
            tk.Label(self.stop_form, text=stop, bg=self.c["panel"], fg=self.c["text"],
                     font=("Segoe UI", 9), anchor="w", wraplength=450).grid(row=i + 1, column=1, padx=5, pady=4, sticky="ew")
            e1 = ttk.Entry(self.stop_form, textvariable=travel, width=10)
            e1.grid(row=i + 1, column=2, padx=5, pady=4, sticky="w")
            e2 = ttk.Entry(self.stop_form, textvariable=pause, width=10)
            e2.grid(row=i + 1, column=3, padx=5, pady=4, sticky="w")
            time_label.grid(row=i + 1, column=4, padx=5, pady=4, sticky="w")
            if i == 0:
                e1.state(["disabled"])
            self.stop_rows.append({"name": stop, "travel": travel, "pause": pause, "time": time_label})
        self.preview_times()

    def preview_times(self):
        try:
            current = datetime.strptime(self.departure_var.get().strip(), "%H:%M")
        except ValueError:
            for row in self.stop_rows:
                row["time"].config(text="--:--")
            return
        for i, row in enumerate(self.stop_rows):
            if i > 0:
                try:
                    current += timedelta(minutes=max(0, int(row["travel"].get())))
                except ValueError:
                    pass
            row["time"].config(text=current.strftime("%H:%M"))
            try:
                pause = max(0, int(row["pause"].get()))
            except ValueError:
                pause = 0
            if pause and i < len(self.stop_rows) - 1:
                current += timedelta(minutes=pause)

    def read_schedule_from_form(self):
        if not self.stop_rows:
            raise ValueError("Keine Haltestellen")
        current = datetime.strptime(self.departure_var.get().strip(), "%H:%M")
        schedule = []
        for i, row in enumerate(self.stop_rows):
            if i > 0:
                travel = int(row["travel"].get())
                if travel < 0:
                    raise ValueError
                current += timedelta(minutes=travel)
            pause = int(row["pause"].get())
            if pause < 0:
                raise ValueError
            schedule.append({"name": row["name"], "time": current.strftime("%H:%M"), "pause_min": pause})
            if pause and i < len(self.stop_rows) - 1:
                current += timedelta(minutes=pause)
        return schedule

    def save_new_trip(self):
        line = self.line_var.get().strip()
        vehicle = self.vehicle_var.get().strip()
        departure = self.departure_var.get().strip()
        if not line or not vehicle:
            messagebox.showerror("Angaben fehlen", "Bitte Linie und Tram/Fahrzeug eingeben.")
            return
        try:
            datetime.strptime(departure, "%H:%M")
            schedule = self.read_schedule_from_form()
        except (ValueError, TypeError):
            messagebox.showerror("Zeitfehler", "Abfahrt, Fahrzeit und Pause bitte korrekt eingeben.")
            return
        code = self.unique_code()
        route_code = self.route_code_from_display(self.route_var.get())
        route_name = ROUTES[route_code]["name"]
        self.plans[code] = {
            "route_code": route_code,
            "route_name": route_name,
            "linie": line,
            "tram": vehicle,
            "abfahrt": departure,
            "fahrten": [{
                "richtung": route_name,
                "start": schedule[0]["name"],
                "ziel": schedule[-1]["name"],
                "abfahrt": departure,
                "stops": schedule,
            }],
        }
        self.save_json(PLAN_FILE, self.plans)
        self.show_code_dialog(code, title="Fahrplan gespeichert")
        self.open_plan(code)

    # ------------------ Codes / Plan ------------------
    def show_code_dialog(self, code, title="Fahrplan gespeichert", callback=None, start_label="Schließen"):
        dialog = tk.Toplevel(self.root)
        dialog.title("Persönlicher Fahrplan-Code")
        dialog.geometry("520x310")
        dialog.resizable(False, False)
        dialog.configure(bg=self.c["panel"])
        dialog.transient(self.root)
        dialog.grab_set()
        tk.Frame(dialog, bg=self.c["teal"], height=8).pack(fill="x")
        tk.Label(dialog, text=title, bg=self.c["panel"], fg=self.c["text"], font=("Segoe UI", 20, "bold")).pack(pady=(22, 5))
        tk.Label(dialog, text="Dein persönlicher Code", bg=self.c["panel"], fg=self.c["muted"],
                 font=("Segoe UI", 10, "bold")).pack()
        entry = tk.Entry(dialog, font=("Consolas", 27, "bold"), justify="center", relief="solid", bd=1, width=10)
        entry.insert(0, code); entry.pack(pady=12); entry.select_range(0, "end")
        status = tk.Label(dialog, text="Code kann kopiert werden.", bg=self.c["panel"], fg=self.c["muted"], font=("Segoe UI", 9))
        status.pack()
        def copy():
            self.root.clipboard_clear(); self.root.clipboard_append(code); self.root.update()
            status.config(text="✓ Code kopiert", fg=self.c["green"])
        row = tk.Frame(dialog, bg=self.c["panel"]); row.pack(pady=14)
        ttk.Button(row, text="⧉  Code kopieren", style="Primary.TButton", command=copy).pack(side="left", padx=4)
        def close_and_callback():
            try: dialog.grab_release()
            except tk.TclError: pass
            dialog.destroy()
            if callback:
                callback()
        ttk.Button(row, text=start_label, command=close_and_callback).pack(side="left", padx=4)

    def show_open_code(self):
        self.clear_content(); self.header("FAHRPLAN ÖFFNEN", "Persönlichen sechsstelligen Code eingeben.")
        box = self.card(self.content); box.pack(fill="x", padx=260, pady=70)
        tk.Label(box, text="Persönlicher Fahrplan-Code", bg=self.c["panel"], fg=self.c["text"],
                 font=("Segoe UI", 15, "bold")).pack(pady=(26, 7))
        e = ttk.Entry(box, width=14, font=("Segoe UI", 20), justify="center"); e.pack(pady=10); e.focus()
        def go(_event=None):
            code = e.get().strip()
            if code in self.plans:
                self.open_plan(code)
            else:
                messagebox.showerror("Nicht gefunden", "Dieser persönliche Code existiert nicht.")
        e.bind("<Return>", go)
        ttk.Button(box, text="Fahrplan laden", style="Primary.TButton", command=go).pack(pady=(7, 25))

    def open_plan(self, code):
        if code not in self.plans:
            return
        self.code = code
        self.plan = self.plans[code]
        self.current_trip_index = 0
        if self.running:
            self.show_driver()
        else:
            self.show_plan()

    def current_trip(self):
        return self.plan["fahrten"][self.current_trip_index]

    def show_plan(self):
        self.clear_content(); trip = self.current_trip(); plan = self.plan
        self.header(f"LINIE {plan['linie']} • TRAM {plan['tram']}", f"Code {self.code} • {trip['richtung']}")
        body = tk.Frame(self.content, bg=self.c["bg"]); body.pack(fill="both", expand=True, padx=28, pady=5)
        left = self.card(body); left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = self.card(body); right.pack(side="right", fill="y", padx=(0, 0))
        tk.Label(left, text=f"{trip['start']}  →  {trip['ziel']}", bg=self.c["panel"], fg=self.c["teal"],
                 font=("Segoe UI", 19, "bold")).pack(anchor="w", padx=18, pady=(17, 5))
        tree = ttk.Treeview(left, columns=("n", "s", "t", "p"), show="headings", height=14)
        for col, head, width in [("n", "#", 45), ("s", "Haltestelle", 470), ("t", "Soll Ankunft", 105), ("p", "Pause", 90)]:
            tree.heading(col, text=head); tree.column(col, width=width, anchor="center" if col != "s" else "w")
        for i, s in enumerate(trip["stops"], 1):
            tree.insert("", "end", values=(i, s["name"], s["time"], f"{s.get('pause_min', 0)} min"))
        tree.pack(fill="both", expand=True, padx=15, pady=8)
        tk.Label(right, text="FAHRT BEREIT", bg=self.c["panel"], fg=self.c["green"],
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(19, 9))
        tk.Label(right, text=f"Abfahrt  {trip['abfahrt']}", bg=self.c["panel"], fg=self.c["text"],
                 font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=4)
        tk.Label(right, text=f"Ziel  {trip['ziel']}", bg=self.c["panel"], fg=self.c["text"],
                 font=("Segoe UI", 10, "bold"), wraplength=250).pack(anchor="w", padx=16, pady=4)
        ttk.Button(right, text="▶  FAHRT STARTEN", style="Primary.TButton", command=self.start_driver).pack(fill="x", padx=16, pady=(22, 6))
        ttk.Button(right, text="Streckenkarte", command=self.show_map).pack(fill="x", padx=16, pady=4)

    # ------------------ Zeitmodell ------------------
    @staticmethod
    def hhmm_to_minutes(text):
        dt = datetime.strptime(text, "%H:%M")
        return dt.hour * 60 + dt.minute

    def planned_elapsed_to(self, position):
        trip = self.current_trip()
        start = self.hhmm_to_minutes(trip["stops"][0]["time"])
        arr = self.hhmm_to_minutes(trip["stops"][position]["time"])
        delta = arr - start
        if delta < 0:
            delta += 24 * 60
        return delta * 60

    def elapsed_seconds(self):
        if self.started_at is None:
            return self.elapsed_offset
        return self.elapsed_offset + max(0.0, time.monotonic() - self.started_at)

    def automatic_deviation(self):
        if not self.plan:
            return 0
        elapsed = self.elapsed_seconds()
        arrival_ref = self.planned_elapsed_to(self.position)
        trip = self.current_trip()

        if self.paused and self.pause_until is not None and self.position < len(trip["stops"]):
            # Während einer geplanten Pause bleibt die Ankunftsabweichung stehen.
            return int(round(self.pause_start_deviation + self.delay_adjustment))

        pause = int(trip["stops"][self.position].get("pause_min", 0)) if self.position < len(trip["stops"]) - 1 else 0
        reference = arrival_ref + max(0, pause) * 60
        deviation = int(round((elapsed - reference) / 60.0)) + self.delay_adjustment
        return deviation

    def format_deviation(self, value):
        if value > 0:
            return f"+{value} min"
        if value < 0:
            return f"{value} min"
        return "±0 min"

    def planned_time_datetime(self, position):
        trip = self.current_trip()
        base = datetime.strptime(trip["stops"][0]["time"], "%H:%M")
        return base + timedelta(seconds=self.planned_elapsed_to(position))

    def estimated_time_for_stop(self, position):
        planned = self.planned_time_datetime(position)
        return planned + timedelta(minutes=self.automatic_deviation())

    def start_driver(self):
        if not self.plan:
            return
        if self.running:
            self.return_to_active(); return
        self.running = True
        self.position = 0
        self.elapsed_offset = 0.0
        self.started_at = time.monotonic()
        self.pause_until = None
        self.pause_total = 0
        self.paused = False
        self.emergency_dialog_open = False
        self.doors_open = False
        self.view_locked = False
        self.delay_adjustment = 0
        self.actual_times = {0: datetime.now().strftime("%H:%M:%S")}
        self.arrival_deviations = {0: 0}
        self.last_pause_remaining = 0
        self.update_active_nav()
        self.show_driver()

    def restore_running_state(self, state):
        self.position = int(state.get("position", 0))
        self.elapsed_offset = float(state.get("elapsed_seconds", 0))
        self.started_at = time.monotonic()
        self.delay_adjustment = int(state.get("delay_adjustment", 0))
        self.actual_times = {int(k): v for k, v in state.get("actual_times", {}).items()}
        self.arrival_deviations = {int(k): int(v) for k, v in state.get("arrival_deviations", {}).items()}
        self.paused = bool(state.get("paused", False))
        self.doors_open = False
        self.running = True
        self.emergency_dialog_open = False
        remaining = int(state.get("pause_remaining", 0))
        self.pause_total = int(state.get("pause_total", 0))
        if self.paused and remaining > 0:
            self.pause_until = time.monotonic() + remaining
        else:
            self.paused = False
            self.pause_until = None
        self.update_active_nav()
        self.show_driver()

    # ------------------ Fahreransicht ------------------
    def show_driver(self):
        self.clear_content()
        trip = self.current_trip(); plan = self.plan; stops = trip["stops"]
        self.header(f"FAHRER-MODUS • LINIE {plan['linie']}", f"TRAM {plan['tram']} • {trip['richtung']}")

        top = self.card(self.content); top.pack(fill="x", padx=28, pady=3)
        self.driver_clock = tk.Label(top, text=datetime.now().strftime("%H:%M:%S"), bg=self.c["panel"],
                                     fg=self.c["text"], font=("Segoe UI", 23, "bold"))
        self.driver_clock.pack(side="left", padx=15, pady=10)
        tk.Label(top, text=f"TRAM {plan['tram']}", bg=self.c["panel"], fg=self.c["teal"],
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=12)
        tk.Label(top, text="FAHRT AKTIV", bg=self.c["teal"], fg="white", font=("Segoe UI", 9, "bold"),
                 padx=10, pady=6).pack(side="right", padx=8)
        self.door_status = tk.Label(top, text="TÜREN GESCHLOSSEN", bg=self.c["green"], fg="white",
                                    font=("Segoe UI", 9, "bold"), padx=10, pady=6)
        self.door_status.pack(side="right", padx=15)

        body = tk.Frame(self.content, bg=self.c["bg"]); body.pack(fill="both", expand=True, padx=28, pady=8)
        center = self.card(body); center.pack(side="left", fill="both", expand=True, padx=(0, 10))
        side = self.card(body); side.pack(side="right", fill="both")

        tk.Label(center, text="AKTUELLER HALT", bg=self.c["panel"], fg=self.c["muted"],
                 font=("Segoe UI", 11, "bold")).pack(pady=(20, 4))
        self.stop_label = tk.Label(center, text=stops[self.position]["name"], bg=self.c["panel"], fg=self.c["text"],
                                   font=("Segoe UI", 28, "bold"), wraplength=650)
        self.stop_label.pack(pady=5)
        self.plan_time_label = tk.Label(center, text=stops[self.position]['time'], bg=self.c["panel"],
                                        fg=self.c["teal"], font=("Segoe UI", 16, "bold"))
        self.plan_time_label.pack(pady=2)
        if self.settings.get("show_actual_time", False):
            self.actual_time_label = tk.Label(center, text="--:--:--", bg=self.c["panel"], fg=self.c["text"],
                                              font=("Segoe UI", 15, "bold"))
            self.actual_time_label.pack(pady=2)
        else:
            self.actual_time_label = None
        self.time_label = tk.Label(center, text="PÜNKTLICH  ±0 MIN", bg="#DDF2F5", fg=self.c["teal"],
                                   font=("Segoe UI", 12, "bold"), padx=12, pady=7)
        self.time_label.pack(pady=7)
        self.duration_label = tk.Label(center, text="Fahrtdauer 00:00", bg=self.c["panel"], fg=self.c["muted"],
                                       font=("Segoe UI", 10))
        self.duration_label.pack()
        self.pause_label = tk.Label(center, text="", bg=self.c["panel"], fg=self.c["gold"],
                                     font=("Segoe UI", 11, "bold"))
        self.pause_label.pack(pady=2)
        self.progress = ttk.Progressbar(center, length=500, maximum=max(1, len(stops) - 1), value=self.position)
        self.progress.pack(fill="x", padx=25, pady=13)
        self.position_label = tk.Label(center, text=f"Haltestelle {self.position + 1} von {len(stops)}",
                                       bg=self.c["panel"], fg=self.c["muted"], font=("Segoe UI", 9))
        self.position_label.pack()

        nav = tk.Frame(center, bg=self.c["panel"]); nav.pack(pady=15)
        self.back_button = ttk.Button(nav, text="← Zurück", command=self.driver_previous); self.back_button.pack(side="left", padx=3)
        self.doors_button = ttk.Button(nav, text="Tür auf/zu", command=self.toggle_doors); self.doors_button.pack(side="left", padx=3)
        self.next_button = ttk.Button(nav, text="Nächster Halt →", style="Primary.TButton", command=self.next_stop); self.next_button.pack(side="left", padx=3)
        ttk.Button(center, text="⚠  NOTFALL", style="Danger.TButton", command=self.open_emergency).pack(pady=4)
        tools = tk.Frame(center, bg=self.c["panel"]); tools.pack(pady=4)
        ttk.Button(tools, text="🚧  STAU", command=self.open_traffic).pack(side="left", padx=3)
        ttk.Button(tools, text="Fahrt beenden & speichern", command=self.finish_driver).pack(side="left", padx=3)

        tk.Label(side, text="STRECKENVERLAUF", bg=self.c["panel"], fg=self.c["text"],
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(12, 2))
        map_caption = "ANKUNFT   •   ABWEICHUNG"
        if self.settings.get("show_actual_time", False):
            map_caption = "ANKUNFT   •   IST / ETA   •   ABWEICHUNG"
        tk.Label(side, text=map_caption, bg=self.c["panel"], fg=self.c["muted"],
                 font=("Segoe UI", 8)).pack(anchor="w", padx=12, pady=(0, 7))
        self.map_canvas = tk.Canvas(side, bg=self.c["soft"], width=455, highlightthickness=0)
        self.map_canvas.pack(fill="both", expand=True, padx=10, pady=7)
        self.render_map(stops)
        self.refresh_driver_view()

    def tick_driver_state(self):
        if not self.running:
            return
        # Pause automatisch beenden
        if self.paused and self.pause_until is not None:
            remaining = int(self.pause_until - time.monotonic())
            if remaining <= 0:
                self.paused = False
                self.pause_until = None
                self.last_pause_remaining = 0
                if self.next_button:
                    try: self.next_button.state(["!disabled"])
                    except tk.TclError: pass
            else:
                self.last_pause_remaining = remaining
        if self.driver_clock:
            try: self.driver_clock.config(text=datetime.now().strftime("%H:%M:%S"))
            except tk.TclError: pass
        self.update_driver_labels()

    def update_driver_labels(self):
        trip = self.current_trip()
        stops = trip["stops"]
        deviation = self.automatic_deviation()
        current = stops[self.position]
        try:
            if self.stop_label: self.stop_label.config(text=current["name"])
            if self.plan_time_label: self.plan_time_label.config(text=current['time'])
            if self.actual_time_label:
                if self.position in self.actual_times:
                    actual_text = self.actual_times[self.position]
                    suffix = ""
                else:
                    actual_text = self.estimated_time_for_stop(self.position).strftime("%H:%M")
                    suffix = " (ETA)"
                self.actual_time_label.config(text=f"{actual_text}{suffix}")
            if deviation > 0:
                self.time_label.config(text=f"VERSPÄTUNG  +{deviation} MIN", bg="#FBE3D3", fg=self.c["red"])
            elif deviation < 0:
                self.time_label.config(text=f"VERFRÜHUNG  {deviation} MIN", bg="#E1F1E9", fg=self.c["green"])
            else:
                self.time_label.config(text="PÜNKTLICH  ±0 MIN", bg="#DDF2F5", fg=self.c["teal"])
            elapsed = int(self.elapsed_seconds());
            if self.duration_label:
                self.duration_label.config(text=f"Fahrtdauer {elapsed // 60:02d}:{elapsed % 60:02d}")
            if self.pause_label:
                if self.paused and self.pause_until:
                    left = max(0, int(self.pause_until - time.monotonic()))
                    self.pause_label.config(text=f"PAUSE  •  noch {left // 60:02d}:{left % 60:02d}")
                else:
                    self.pause_label.config(text="")
            if self.position_label:
                self.position_label.config(text=f"Haltestelle {self.position + 1} von {len(stops)}")
            if self.progress:
                self.progress.config(value=self.position)
            if self.back_button:
                if self.position == 0 or self.paused: self.back_button.state(["disabled"])
                else: self.back_button.state(["!disabled"])
            if self.next_button:
                if self.paused or self.doors_open: self.next_button.state(["disabled"])
                else: self.next_button.state(["!disabled"])
            self.render_map(stops)
        except tk.TclError:
            pass

    def refresh_driver_view(self):
        self.update_driver_labels()

    def next_stop(self):
        if not self.running or self.paused or self.view_locked:
            return
        if self.doors_open:
            messagebox.showwarning("Türen offen", "Bitte zuerst die Türen schließen.")
            return
        trip = self.current_trip()
        if self.position >= len(trip["stops"]) - 1:
            self.finish_driver()
            return
        self.view_locked = True
        try:
            self.position += 1
            now = datetime.now()
            self.actual_times[self.position] = now.strftime("%H:%M:%S")
            # Abweichung direkt bei der Ankunft speichern.
            self.arrival_deviations[self.position] = self.automatic_deviation()
            pause = max(0, int(trip["stops"][self.position].get("pause_min", 0)))
            self.doors_open = False
            if self.door_status:
                self.door_status.config(text="TÜREN GESCHLOSSEN", bg=self.c["green"])
            self.pause_total = pause * 60
            if pause > 0:
                self.paused = True
                self.pause_start_deviation = self.arrival_deviations[self.position]
                self.pause_until = time.monotonic() + self.pause_total
                self.last_pause_remaining = self.pause_total
            else:
                self.paused = False
                self.pause_until = None
                self.last_pause_remaining = 0
            self.refresh_driver_view()
        finally:
            self.root.after(120, lambda: setattr(self, "view_locked", False))

    def driver_previous(self):
        if not self.running or self.paused or self.view_locked or self.position <= 0:
            return
        self.position -= 1
        self.refresh_driver_view()

    def toggle_doors(self):
        if not self.running or self.paused:
            return
        self.doors_open = not self.doors_open
        if self.door_status:
            self.door_status.config(
                text="TÜREN OFFEN" if self.doors_open else "TÜREN GESCHLOSSEN",
                bg=self.c["gold"] if self.doors_open else self.c["green"],
            )

    # ------------------ Stau ------------------
    def open_traffic(self):
        if not self.running:
            return
        dialog = tk.Toplevel(self.root); dialog.title("🚧 Stau"); dialog.geometry("490x330"); dialog.resizable(False, False)
        dialog.configure(bg=self.c["panel"]); dialog.transient(self.root); dialog.grab_set()
        tk.Frame(dialog, bg=self.c["amber"], height=8).pack(fill="x")
        tk.Label(dialog, text="🚧  STAU", bg=self.c["panel"], fg=self.c["amber"], font=("Segoe UI", 23, "bold")).pack(pady=(22, 4))
        tk.Label(dialog, text="Wie viele zusätzliche Minuten kommen hinzu?", bg=self.c["panel"], fg=self.c["text"], font=("Segoe UI", 10)).pack(pady=4)
        tk.Label(dialog, text=f"Uhrzeit: {datetime.now().strftime('%H:%M:%S')}   •   bisheriger Zusatz: +{self.delay_adjustment} min",
                 bg="#FFF5E6", fg=self.c["amber"], font=("Segoe UI", 9, "bold"), padx=10, pady=6).pack(pady=12)
        row = tk.Frame(dialog, bg=self.c["panel"]); row.pack(pady=5)
        for minutes in (1, 2, 5, 10):
            def add(value=minutes):
                self.delay_adjustment += value
                dialog.destroy()
                self.refresh_driver_view()
            ttk.Button(row, text=f"+{minutes} min", command=add).pack(side="left", padx=4)
        ttk.Button(dialog, text="Schließen", command=dialog.destroy).pack(pady=16)

    # ------------------ Notfall / Fortsetzen ------------------
    def open_emergency(self):
        if not self.running or self.emergency_dialog_open:
            return
        self.emergency_dialog_open = True
        before_elapsed = self.elapsed_seconds()
        pause_remaining = max(0, int(self.pause_until - time.monotonic())) if self.paused and self.pause_until else 0
        was_paused = self.paused and pause_remaining > 0
        frozen_deviation = self.automatic_deviation()
        # Uhr und Verspätung sofort einfrieren.
        self.elapsed_offset = before_elapsed
        self.started_at = None
        self.running = False
        self.update_active_nav()

        trip = self.current_trip()
        dialog = tk.Toplevel(self.root); dialog.title("⚠ NOTFALL • Standortmeldung"); dialog.geometry("690x560")
        dialog.resizable(False, False); dialog.configure(bg=self.c["panel"]); dialog.transient(self.root); dialog.grab_set()
        tk.Frame(dialog, bg=self.c["red"], height=9).pack(fill="x")
        tk.Label(dialog, text="⚠  NOTFALL", bg=self.c["panel"], fg=self.c["red"], font=("Segoe UI", 25, "bold")).pack(pady=(20, 3))
        tk.Label(dialog, text="Die laufende Fahrt wurde angehalten. Wähle den aktuellen Standort.",
                 bg=self.c["panel"], fg=self.c["text"], font=("Segoe UI", 10)).pack(pady=3)
        tk.Label(dialog, text=trip["richtung"], bg="#F8E5E7", fg=self.c["red"], font=("Segoe UI", 9, "bold"), padx=10, pady=6).pack(pady=11)
        tk.Label(dialog, text="AKTUELLER STANDORT", bg=self.c["panel"], fg=self.c["muted"], font=("Segoe UI", 9, "bold")).pack(pady=(3, 2))
        location = tk.StringVar(value=trip["stops"][self.position]["name"])
        ttk.Combobox(dialog, textvariable=location, values=[s["name"] for s in trip["stops"]], state="readonly", width=46).pack(pady=5)
        tk.Label(dialog, text="ZEITPUNKT", bg=self.c["panel"], fg=self.c["muted"], font=("Segoe UI", 9, "bold")).pack(pady=(12, 2))
        clock = tk.Label(dialog, text=datetime.now().strftime("%H:%M:%S"), bg=self.c["panel"], fg=self.c["text"], font=("Segoe UI", 18, "bold")); clock.pack()
        tk.Label(dialog, text=f"Zeitabweichung beim Auslösen: {frozen_deviation:+d} min", bg="#F8E5E7" if frozen_deviation > 0 else "#E1F1E9",
                 fg=self.c["red"] if frozen_deviation > 0 else self.c["green"], font=("Segoe UI", 9, "bold"), padx=10, pady=5).pack(pady=8)
        tk.Label(dialog, text="GRUND / NOTIZ (optional)", bg=self.c["panel"], fg=self.c["muted"], font=("Segoe UI", 9, "bold")).pack(pady=(7, 2))
        note = tk.Text(dialog, width=60, height=4, font=("Segoe UI", 10)); note.pack()

        def cancel():
            try: dialog.grab_release()
            except tk.TclError: pass
            dialog.destroy()
            self.running = True
            self.started_at = time.monotonic()
            self.paused = was_paused
            if was_paused:
                self.pause_until = time.monotonic() + pause_remaining
            else:
                self.pause_until = None
            self.emergency_dialog_open = False
            self.update_active_nav(); self.show_driver()

        def confirm():
            state = {
                "code": self.code,
                "position": self.position,
                "elapsed_seconds": self.elapsed_offset,
                "delay_adjustment": self.delay_adjustment,
                "actual_times": {str(k): v for k, v in self.actual_times.items()},
                "arrival_deviations": {str(k): v for k, v in self.arrival_deviations.items()},
                "paused": was_paused,
                "pause_remaining": pause_remaining,
                "pause_total": self.pause_total,
            }
            item = {
                "typ": "NOTFALL",
                "zeitpunkt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "fahrplan_code": self.code,
                "linie": self.plan["linie"],
                "tram": self.plan["tram"],
                "route": self.plan["route_name"],
                "haltestelle": location.get(),
                "zeitabweichung_min": frozen_deviation,
                "grund": note.get("1.0", "end").strip() or "Nicht angegeben",
                "fortsetzbar": True,
                "resume": state,
            }
            self.history.append(item); self.save_json(HISTORY_FILE, self.history)
            self.running = False; self.started_at = None; self.emergency_dialog_open = False
            self.update_active_nav()
            try: dialog.grab_release()
            except tk.TclError: pass
            dialog.destroy()
            self.show_history()

        ttk.Button(dialog, text="⚠  NOTFALL BESTÄTIGEN", style="Danger.TButton", command=confirm).pack(pady=11)
        ttk.Button(dialog, text="Abbrechen • Fahrt fortsetzen", command=cancel).pack()

    def resume_from_history(self, item):
        resume = item.get("resume")
        code = item.get("fahrplan_code")
        if not resume or code not in self.plans:
            messagebox.showerror("Nicht möglich", "Diese Notfallmeldung enthält keinen vollständigen Wiederaufnahme-Stand.")
            return
        self.code = code
        self.plan = self.plans[code]
        self.current_trip_index = 0
        self.restore_running_state(resume)

    # ------------------ Fahrt beenden / Rückfahrt ------------------
    def finish_driver(self):
        if not self.plan or (not self.running and self.started_at is None):
            return
        trip = self.current_trip()
        elapsed = max(0, int(self.elapsed_seconds()))
        mins, secs = divmod(elapsed, 60)
        deviation = self.automatic_deviation()
        state = "Ziel erreicht" if self.position == len(trip["stops"]) - 1 else "Vorzeitig beendet"
        item = {
            "typ": "FAHRT",
            "zeitpunkt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "fahrplan_code": self.code,
            "linie": self.plan["linie"],
            "tram": self.plan["tram"],
            "route": self.plan["route_name"],
            "fahrtdauer": f"{mins:02d}:{secs:02d}",
            "verspaetung_min": deviation,
            "letzte_haltestelle": trip["stops"][self.position]["name"],
            "status": state,
        }
        self.history.append(item); self.save_json(HISTORY_FILE, self.history)
        old_trip = json.loads(json.dumps(trip))
        self.running = False; self.started_at = None; self.pause_until = None; self.paused = False
        self.update_active_nav()
        self.show_plan()
        self.return_prompt(old_trip, deviation)

    def return_prompt(self, finished_trip, deviation):
        dialog = tk.Toplevel(self.root); dialog.title("Rückfahrt"); dialog.geometry("560x330"); dialog.resizable(False, False)
        dialog.configure(bg=self.c["panel"]); dialog.transient(self.root); dialog.grab_set()
        tk.Frame(dialog, bg=self.c["gold"], height=8).pack(fill="x")
        tk.Label(dialog, text="↔  RÜCKFAHRT", bg=self.c["panel"], fg=self.c["gold"], font=("Segoe UI", 24, "bold")).pack(pady=(22, 6))
        tk.Label(dialog, text=f"Die Fahrt nach {finished_trip['ziel']} ist beendet.", bg=self.c["panel"], fg=self.c["text"],
                 font=("Segoe UI", 10), wraplength=470).pack(pady=4)
        tk.Label(dialog, text=f"Möchtest du jetzt zurück zu {finished_trip['start']} fahren?",
                 bg=self.c["panel"], fg=self.c["text"], font=("Segoe UI", 12, "bold"), wraplength=470).pack(pady=8)
        tk.Label(dialog, text=f"Start der Rückfahrt: aktuelle Uhrzeit {datetime.now().strftime('%H:%M')}  •  bisherige Abweichung: {deviation:+d} min",
                 bg="#F6F1E7", fg=self.c["muted"], font=("Segoe UI", 9), padx=10, pady=6).pack(pady=8)
        row = tk.Frame(dialog, bg=self.c["panel"]); row.pack(pady=14)
        ttk.Button(row, text="Ja, Rückfahrt erstellen", style="Primary.TButton", command=lambda: self.create_return_trip(finished_trip, dialog)).pack(side="left", padx=4)
        ttk.Button(row, text="Nein", command=dialog.destroy).pack(side="left", padx=4)

    def create_return_trip(self, finished_trip, dialog):
        try:
            dialog.grab_release()
        except tk.TclError:
            pass
        dialog.destroy()
        old_stops = finished_trip["stops"]
        # Segmentfahrzeiten aus dem Originalplan ableiten.
        travel = []
        for i in range(1, len(old_stops)):
            a = self.hhmm_to_minutes(old_stops[i - 1]["time"])
            b = self.hhmm_to_minutes(old_stops[i]["time"])
            delta = b - a
            if delta < 0: delta += 1440
            delta -= int(old_stops[i - 1].get("pause_min", 0))
            travel.append(max(0, delta))

        reverse_stops = list(reversed(old_stops))
        start_now = datetime.now().replace(second=0, microsecond=0)
        schedule = [{"name": reverse_stops[0]["name"], "time": start_now.strftime("%H:%M"), "pause_min": 0}]
        current = start_now
        for idx in range(1, len(reverse_stops)):
            original_segment_index = len(travel) - idx
            current += timedelta(minutes=travel[original_segment_index])
            pause = int(reverse_stops[idx].get("pause_min", 0)) if idx < len(reverse_stops) - 1 else 0
            schedule.append({"name": reverse_stops[idx]["name"], "time": current.strftime("%H:%M"), "pause_min": pause})
            if pause:
                current += timedelta(minutes=pause)

        code = self.unique_code()
        route_name = f"Rückfahrt • {finished_trip['ziel']} → {finished_trip['start']}"
        self.plans[code] = {
            "route_code": "RETURN",
            "route_name": route_name,
            "linie": self.plan["linie"],
            "tram": self.plan["tram"],
            "abfahrt": start_now.strftime("%H:%M"),
            "fahrten": [{
                "richtung": route_name,
                "start": schedule[0]["name"],
                "ziel": schedule[-1]["name"],
                "abfahrt": start_now.strftime("%H:%M"),
                "stops": schedule,
            }],
        }
        self.save_json(PLAN_FILE, self.plans)
        self.code = code; self.plan = self.plans[code]; self.current_trip_index = 0
        self.show_code_dialog(code, title="Rückfahrt erstellt", callback=self.start_driver, start_label="Rückfahrt starten")

    # ------------------ Einstellungen ------------------
    def open_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Einstellungen")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(760, max(560, int(sw * 0.62))), min(700, max(480, int(sh * 0.75)))
        dialog.geometry(f"{w}x{h}")
        dialog.minsize(520, 430)
        dialog.configure(bg=self.c["bg"])
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="⚙  EINSTELLUNGEN", bg=self.c["bg"], fg=self.c["text"],
                 font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=24, pady=(20, 4))
        tk.Label(dialog, text="Darstellung, Zeit-Anzeige und eigene Linien-/Routencodes", bg=self.c["bg"],
                 fg=self.c["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=26, pady=(0, 14))

        canvas = tk.Canvas(dialog, bg=self.c["bg"], highlightthickness=0)
        bar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=self.c["bg"])
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(20,0), pady=5)
        bar.pack(side="right", fill="y", padx=(0,15), pady=5)

        def section(title):
            frame = self.card(inner); frame.pack(fill="x", pady=7)
            tk.Label(frame, text=title, bg=self.c["panel"], fg=self.c["text"],
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(13,8))
            return frame

        appearance = section("Darstellung")
        dark_var = tk.BooleanVar(value=bool(self.settings.get("dark_mode")))
        actual_var = tk.BooleanVar(value=bool(self.settings.get("show_actual_time")))
        ttk.Checkbutton(appearance, text="Darkmode aktivieren", variable=dark_var).pack(anchor="w", padx=16, pady=6)
        ttk.Checkbutton(appearance, text="IST-/ETA-Zeit zusätzlich anzeigen", variable=actual_var).pack(anchor="w", padx=16, pady=(0,14))

        names = section("Eigene Routencodes / Liniennamen")
        tk.Label(names, text="Du kannst z. B. aus W2D einen Namen wie L2D oder L3D machen. Die internen Strecken bleiben gleich.",
                 bg=self.c["panel"], fg=self.c["muted"], font=("Segoe UI", 9), wraplength=w-100, justify="left").pack(anchor="w", padx=16, pady=(0,10))
        alias_vars = {}
        for code in ROUTES:
            row = tk.Frame(names, bg=self.c["panel"]); row.pack(fill="x", padx=16, pady=4)
            tk.Label(row, text=code, bg=self.c["panel"], fg=self.c["teal"], width=12, anchor="w", font=("Consolas", 9, "bold")).pack(side="left")
            var = tk.StringVar(value=str(self.settings["route_aliases"].get(code, code)))
            ttk.Entry(row, textvariable=var, width=25).pack(side="left", padx=8)
            alias_vars[code] = var

        status = tk.Label(dialog, text="", bg=self.c["bg"], fg=self.c["green"], font=("Segoe UI", 9, "bold"))
        status.pack(pady=(2,0))

        def save_settings():
            aliases = {}
            used = set()
            for code, var in alias_vars.items():
                value = var.get().strip() or code
                if value in used:
                    messagebox.showerror("Doppelter Name", f"Der Name '{value}' wird bereits verwendet.", parent=dialog)
                    return
                used.add(value)
                aliases[code] = value
            self.settings["dark_mode"] = bool(dark_var.get())
            self.settings["show_actual_time"] = bool(actual_var.get())
            self.settings["route_aliases"] = aliases
            self.save_json(SETTINGS_FILE, self.settings)
            self.apply_palette()
            self.setup_styles()
            self.build_sidebar()
            self.apply_theme_to_widget_tree(self.root)
            status.config(text="✓ Einstellungen gespeichert")
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()
            # Aktuelle Ansicht neu aufbauen, ohne eine laufende Fahrt zu verlieren.
            if self.running and self.plan:
                self.show_driver()
            elif self.plan:
                self.show_plan()
            else:
                self.show_home()

        row = tk.Frame(dialog, bg=self.c["bg"]); row.pack(fill="x", padx=22, pady=12)
        ttk.Button(row, text="Speichern", style="Primary.TButton", command=save_settings).pack(side="right", padx=4)
        ttk.Button(row, text="Abbrechen", command=dialog.destroy).pack(side="right", padx=4)

    # ------------------ Streckenkarte ------------------
    def render_map(self, stops):
        if not self.map_canvas:
            return
        c = self.map_canvas
        try:
            c.delete("all")
        except tk.TclError:
            return
        count = len(stops)
        width = max(360, self.map_canvas.winfo_width())
        height = max(300, self.map_canvas.winfo_height())
        margin = 24
        gap = (height - margin * 2) / max(1, count - 1)
        x = 24
        right_x = width - 10
        actual_on = bool(self.settings.get("show_actual_time", False))
        for i, stop in enumerate(stops):
            y = margin + i * gap
            if i < count - 1:
                y2 = margin + (i + 1) * gap
                c.create_line(x, y, x, y2, fill=self.c["teal"], width=5)
            active = self.running and i == self.position
            passed = self.running and i < self.position
            c.create_oval(x - 7, y - 7, x + 7, y + 7,
                          fill=self.c["coral"] if active else (self.c["teal"] if passed else self.c["panel"]),
                          outline=self.c["teal"], width=2)
            c.create_text(x + 13, y - 8, text=stop["name"], anchor="w",
                          font=("Segoe UI", 8, "bold" if active else "normal"), fill=self.c["text"])
            # Die Fahrplanzeit bleibt die feste Referenz; Verspätung/Verfrühung wird daraus synchron berechnet.
            c.create_text(right_x - (85 if actual_on else 0), y - 8, text=stop["time"], anchor="e",
                          font=("Consolas", 8, "bold"), fill=self.c["text"] if active else self.c["muted"])
            if actual_on:
                if i in self.actual_times:
                    ist = self.actual_times[i]
                elif self.running:
                    ist = self.estimated_time_for_stop(i).strftime("%H:%M")
                else:
                    ist = "--:--"
                c.create_text(right_x - 30, y - 8, text=ist, anchor="e", font=("Consolas", 8), fill=self.c["muted"])
            if self.running:
                dev = self.arrival_deviations.get(i, self.automatic_deviation()) if i <= self.position else self.automatic_deviation()
            else:
                dev = 0
            dev_text = f"{dev:+d}" if dev else "±0"
            dev_color = self.c["red"] if dev > 0 else self.c["green"] if dev < 0 else self.c["teal"]
            c.create_text(right_x, y - 8, text=f"{dev_text} min", anchor="e",
                          font=("Segoe UI", 8, "bold"), fill=dev_color)

    def show_map(self):
        self.clear_content(); trip = self.current_trip()
        self.header("STRECKENKARTE", f"Linie {self.plan['linie']} • Tram {self.plan['tram']} • {trip['richtung']}")
        card = self.card(self.content); card.pack(fill="both", expand=True, padx=28, pady=8)
        self.map_canvas = tk.Canvas(card, bg=self.c["soft"], highlightthickness=0)
        self.map_canvas.pack(fill="both", expand=True, padx=12, pady=12)
        self.render_map(trip["stops"])
        ttk.Button(self.content, text="← Zurück", command=self.show_driver if self.running else self.show_plan).pack(pady=10)

    def return_to_active(self):
        if self.running and self.plan:
            self.show_driver()
        else:
            self.update_active_nav()

    # ------------------ Gespeicherte Fahrpläne ------------------
    def show_saved(self):
        self.clear_content(); self.header("MEINE FAHRPLÄNE", "Gespeicherte Fahrpläne einzeln öffnen oder löschen.")
        card = self.card(self.content); card.pack(fill="both", expand=True, padx=28, pady=8)
        tree = ttk.Treeview(card, columns=("code", "route", "line", "tram", "dep"), show="headings")
        for col, head, width in [("code", "Code", 110), ("route", "Strecke", 450), ("line", "Linie", 80), ("tram", "Tram", 120), ("dep", "Abfahrt", 100)]:
            tree.heading(col, text=head); tree.column(col, width=width, anchor="center" if col != "route" else "w")
        for code, p in self.plans.items():
            tree.insert("", "end", values=(code, p.get("route_name", ""), p.get("linie", ""), p.get("tram", ""), p.get("abfahrt", "")))
        tree.pack(fill="both", expand=True, padx=15, pady=15)

        def selected_code():
            s = tree.selection()
            return str(tree.item(s[0], "values")[0]) if s else None
        def open_selected():
            code = selected_code()
            if not code: messagebox.showwarning("Auswahl", "Bitte einen Fahrplan auswählen.")
            else: self.open_plan(code)
        def delete_selected():
            code = selected_code()
            if not code: messagebox.showwarning("Auswahl", "Bitte einen Fahrplan auswählen.")
            elif messagebox.askyesno("Fahrplan löschen", f"Fahrplan {code} wirklich löschen?"):
                self.plans.pop(code, None); self.save_json(PLAN_FILE, self.plans); self.show_saved()

        bar = tk.Frame(self.content, bg=self.c["bg"]); bar.pack(fill="x", padx=28, pady=8)
        ttk.Button(bar, text="Fahrplan öffnen", style="Primary.TButton", command=open_selected).pack(side="left")
        ttk.Button(bar, text="Fahrplan löschen", command=delete_selected).pack(side="left", padx=7)
        ttk.Button(bar, text="↻ Aktualisieren", command=self.show_saved).pack(side="right")

    # ------------------ Historie ------------------
    def show_history(self):
        self.clear_content(); self.header("FAHRT-HISTORIE", "Fahrtdauer, Verspätung, Verfrühung und Notfallmeldungen.")
        card = self.card(self.content); card.pack(fill="both", expand=True, padx=28, pady=8)
        cols = ("when", "type", "line", "tram", "route", "duration", "dev", "stop")
        tree = ttk.Treeview(card, columns=cols, show="headings")
        specs = [
            ("when", "Zeitpunkt", 145), ("type", "Typ", 75), ("line", "Linie", 60), ("tram", "Tram", 85),
            ("route", "Strecke", 310), ("duration", "Dauer", 90), ("dev", "Abweichung", 95), ("stop", "Haltestelle", 230)
        ]
        for col, head, width in specs:
            tree.heading(col, text=head); tree.column(col, width=width, anchor="center" if col != "route" else "w")
        for idx, item in reversed(list(enumerate(self.history))):
            if item.get("typ") == "NOTFALL":
                values = (item.get("zeitpunkt", ""), "NOTFALL", item.get("linie", ""), item.get("tram", ""),
                          "Notfallmeldung", "—", f"{int(item.get('zeitabweichung_min', 0)):+d} min", item.get("haltestelle", ""))
            else:
                values = (item.get("zeitpunkt", ""), "FAHRT", item.get("linie", ""), item.get("tram", ""),
                          item.get("route", ""), item.get("fahrtdauer", ""), f"{int(item.get('verspaetung_min', 0)):+d} min", item.get("letzte_haltestelle", ""))
            tree.insert("", "end", iid=str(idx), values=values)
        tree.pack(fill="both", expand=True, padx=12, pady=12)

        def selected_index():
            s = tree.selection()
            return int(tree.item(s[0], "values") is not None and s[0]) if s else None
        def delete_selected():
            s = tree.selection()
            if not s: messagebox.showwarning("Auswahl", "Bitte einen Historieneintrag auswählen."); return
            original_index = int(s[0])
            if messagebox.askyesno("Eintrag löschen", "Diesen Historieneintrag wirklich löschen?"):
                self.history.pop(original_index); self.save_json(HISTORY_FILE, self.history); self.show_history()
        def resume_selected():
            s = tree.selection()
            if not s: messagebox.showwarning("Auswahl", "Bitte einen Notfalleintrag auswählen."); return
            item = self.history[int(s[0])]
            if item.get("typ") != "NOTFALL" or not item.get("resume"):
                messagebox.showwarning("Nicht verfügbar", "Nur gespeicherte Notfallfahrten können fortgesetzt werden.")
            else:
                self.resume_from_history(item)
        def details_selected():
            s = tree.selection()
            if not s: messagebox.showwarning("Auswahl", "Bitte einen Eintrag auswählen."); return
            item = self.history[int(s[0])]
            details = "\n".join(f"{k}: {v}" for k, v in item.items() if k not in ("resume",))
            messagebox.showinfo("Historieneintrag", details)

        bar = tk.Frame(self.content, bg=self.c["bg"]); bar.pack(fill="x", padx=28, pady=8)
        ttk.Button(bar, text="Eintrag öffnen", command=details_selected).pack(side="left")
        ttk.Button(bar, text="Fahrt fortsetzen", style="Primary.TButton", command=resume_selected).pack(side="left", padx=7)
        ttk.Button(bar, text="Eintrag löschen", command=delete_selected).pack(side="left", padx=0)
        ttk.Button(bar, text="Historie komplett löschen", command=self.clear_history).pack(side="right")

    def clear_history(self):
        if messagebox.askyesno("Historie löschen", "Die gesamte Historie wirklich löschen?"):
            self.history = []
            self.save_json(HISTORY_FILE, self.history)
            self.show_history()


if __name__ == "__main__":
    root = tk.Tk()
    app = FahrplanManager(root)
    root.mainloop()
