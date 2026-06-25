#!/usr/bin/env python3
"""
forza_app.py — GUI entry point for Forza Horizon 6 Game Assistant.
Requires: pip install customtkinter opencv-python numpy mss psutil pycaw
"""
import sys
import os

# Force UTF-8
if sys.platform == "win32":
    sys.stdout = open(os.sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
    sys.stderr = open(os.sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

try:
    import customtkinter as ctk
except ImportError:
    print("ERROR: customtkinter not installed. Run: pip install customtkinter")
    sys.exit(1)

import threading
import config
from ui.theme import init_fonts, UI_FAMILY
from ui.version import VERSION
from i18n import t as _at
from automation import GameIO, set_session_crop, set_mute_held
from automation.race import run as run_race
from automation.mastery import run as run_mastery
from automation.wheelspin import run as run_wheelspin
from automation.buy import run as run_buy

# Init fonts for CJK support
init_fonts()


class ForzaApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"Forza Horizon 6 Assistant v{VERSION}")
        self.geometry("900x700")

        # Load config
        self.cfg = config.load()

        # State
        self.stop_event = threading.Event()
        self.run_thread = None
        self.current_tab = None

        self._build_ui()

    def _build_ui(self):
        # Tab view
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_race      = self.tabview.add("Race Auto")
        self.tab_mastery   = self.tabview.add("Mastery")
        self.tab_wheelspin = self.tabview.add("Spin Wheel")
        self.tab_buy       = self.tabview.add("Auto Buy")

        self._build_race_tab(self.tab_race)
        self._build_mastery_tab(self.tab_mastery)
        self._build_wheelspin_tab(self.tab_wheelspin)
        self._build_buy_tab(self.tab_buy)

        # Log panel at bottom
        self.log_box = ctk.CTkTextbox(self, height=120, font=(UI_FAMILY, 11))
        self.log_box.pack(fill="x", padx=10, pady=(0, 10))
        self.log_box.insert("end", f"Forza Horizon 6 Assistant v{VERSION}\n")
        self.log_box.insert("end", "Ready. Start the game, then choose an automation tab.\n")

    def _build_race_tab(self, tab):
        lang = self.cfg.get("lang", "en")
        ctk.CTkLabel(tab, text=_at("race_description", lang),
                     font=(UI_FAMILY, 12), wraplength=600, justify="left").pack(
            anchor="w", padx=15, pady=(15, 5))
        frame = ctk.CTkFrame(tab)
        frame.pack(padx=15, pady=5, fill="x")
        ctk.CTkLabel(frame, text="Max races (0=unlimited):").pack(side="left", padx=5)
        self.race_max = ctk.CTkEntry(frame, width=80)
        self.race_max.insert("0", "0")
        self.race_max.pack(side="left", padx=5)
        self.race_btn = ctk.CTkButton(frame, text=_at("btn_start", lang), command=self._start_race)
        self.race_btn.pack(side="left", padx=5)

    def _build_mastery_tab(self, tab):
        lang = self.cfg.get("lang", "en")
        ctk.CTkLabel(tab, text=_at("mastery_description", lang),
                     font=(UI_FAMILY, 12), wraplength=600).pack(
            anchor="w", padx=15, pady=(15, 5))
        frame = ctk.CTkFrame(tab)
        frame.pack(padx=15, pady=5, fill="x")
        ctk.CTkLabel(frame, text="Max cars (0=unlimited):").pack(side="left", padx=5)
        self.mastery_max = ctk.CTkEntry(frame, width=80)
        self.mastery_max.insert("0", "0")
        self.mastery_max.pack(side="left", padx=5)
        self.mastery_btn = ctk.CTkButton(frame, text=_at("btn_start", lang), command=self._start_mastery)
        self.mastery_btn.pack(side="left", padx=5)

    def _build_wheelspin_tab(self, tab):
        lang = self.cfg.get("lang", "en")
        ctk.CTkLabel(tab, text=_at("wheelspin_description", lang),
                     font=(UI_FAMILY, 12), wraplength=600).pack(
            anchor="w", padx=15, pady=(15, 5))
        frame = ctk.CTkFrame(tab)
        frame.pack(padx=15, pady=5, fill="x")
        ctk.CTkLabel(frame, text="Type:").pack(side="left", padx=5)
        self.ws_type = ctk.CTkOptionMenu(frame, values=["super", "normal"], width=100)
        self.ws_type.set("super")
        self.ws_type.pack(side="left", padx=5)
        ctk.CTkLabel(frame, text="Max spins:").pack(side="left", padx=5)
        self.ws_max = ctk.CTkEntry(frame, width=80)
        self.ws_max.insert("0", "0")
        self.ws_max.pack(side="left", padx=5)
        self.ws_btn = ctk.CTkButton(frame, text=_at("btn_start", lang), command=self._start_wheelspin)
        self.ws_btn.pack(side="left", padx=5)

    def _build_buy_tab(self, tab):
        lang = self.cfg.get("lang", "en")
        ctk.CTkLabel(tab, text=_at("buy_description", lang),
                     font=(UI_FAMILY, 12), wraplength=600).pack(
            anchor="w", padx=15, pady=(15, 5))
        frame = ctk.CTkFrame(tab)
        frame.pack(padx=15, pady=5, fill="x")
        ctk.CTkLabel(frame, text="Max buys (0=unlimited):").pack(side="left", padx=5)
        self.buy_max = ctk.CTkEntry(frame, width=80)
        self.buy_max.insert("0", "0")
        self.buy_max.pack(side="left", padx=5)
        self.buy_btn = ctk.CTkButton(frame, text=_at("btn_start", lang), command=self._start_buy)
        self.buy_btn.pack(side="left", padx=5)

    def _log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

    def _stop_all(self):
        self.stop_event.set()
        if self.run_thread and self.run_thread.is_alive():
            self.run_thread.join(timeout=3)
        self.stop_event.clear()

    def _start_race(self):
        self._stop_all()
        self.run_thread = threading.Thread(target=run_race, args=(
            self.cfg, self.stop_event, self._log, self._log, int(self.race_max.get() or 0)
        ), daemon=True)
        self.run_thread.start()

    def _start_mastery(self):
        self._stop_all()
        self.run_thread = threading.Thread(target=run_mastery, args=(
            self.cfg, self.stop_event, self._log, self._log, int(self.mastery_max.get() or 0)
        ), daemon=True)
        self.run_thread.start()

    def _start_wheelspin(self):
        self._stop_all()
        self.run_thread = threading.Thread(target=run_wheelspin, args=(
            self.cfg, self.stop_event, self._log, self._log,
            self.ws_type.get(), int(self.ws_max.get() or 0)
        ), daemon=True)
        self.run_thread.start()

    def _start_buy(self):
        self._stop_all()
        self.run_thread = threading.Thread(target=run_buy, args=(
            self.cfg, self.stop_event, self._log, self._log, int(self.buy_max.get() or 0)
        ), daemon=True)
        self.run_thread.start()


if __name__ == "__main__":
    app = ForzaApp()
    app.mainloop()
