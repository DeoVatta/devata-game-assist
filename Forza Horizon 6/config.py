"""
Game configuration — single source of truth for Forza Horizon 6.
Mirrors FAFE config.json structure. Extensible for new games.
"""
import os
import json
from pathlib import Path

# ── Project ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
GAME_NAME = "Forza Horizon 6"
GAME_ID   = "FH6"
VERSION    = "0.2.0"

# ── Detection ─────────────────────────────────────────────
DETECTION_INTERVAL = 2  # seconds

# Process names to check (case-insensitive match)
FORZA_PROCESS_NAMES = [
    "ForzaHorizon6",
    "ForzaHorizon5",
    "ForzaHorizon4",
    "ForzaHorizon3",
    "ForzaHorizon2",
    "ForzaHorizon",
]

# Window titles to match
FORZA_WINDOW_TITLES = [
    "Forza Horizon 6",
    "Forza Horizon 5",
    "Forza Horizon 4",
    "Forza Horizon 3",
    "Forza Horizon 2",
    "Forza Horizon",
]

# Xbox App / Game Pass store IDs (leave empty until confirmed)
FORZA_XBOX_IDS: list[str] = []

# Stream / OBS settings
OBS_HOST     = "localhost"
OBS_PORT     = 4455
OBS_PASSWORD = None

# ── Background automation ─────────────────────────────────
# Set background_input=false to force foreground SendInput path
BACKGROUND_INPUT        = True
BACKGROUND_CAPTURE      = "window"   # "window" (PrintWindow) or "monitor"
BACKGROUND_FAKE_FOCUS   = True   # keep-alive tick to prevent auto-pause
BACKGROUND_WINDOW_TITLE = "Forza Horizon 6"
CROP_LETTERBOX         = True

# ── Templates ─────────────────────────────────────────────
TEMPLATE_FOLDER  = "templates/en"
REF_RES          = "built-in"   # single 4K reference set
TEMPLATE_LANGS   = ["en", "cht"]
TEMPLATE_PREFER_REF = True

# ── Timing (defaults — can be overridden in config.json) ───
RACE_CHECK_INTERVAL    = 0.5
RACE_POST_KEY_WAIT     = 0.75
RACE_MENU_NAV         = True
RACE_EXIT_NAV         = True

WHEELSPIN_CHECK_INTERVAL = 0.3
WHEELSPIN_POST_KEY_WAIT = 0.5

BUY_CHECK_INTERVAL    = 0.5
BUY_POST_KEY_WAIT    = 1.0

MASTERY_CUTSCENE_WAIT      = 11.0
MASTERY_GRID_UNLOCK_WAIT   = 1.25
MASTERY_START_LOOP         = 1
MENU_TAP_WAIT              = 0.25

# ── Audio ─────────────────────────────────────────────────
MUTE_GAME = True   # mute game during automation

# ── IME ───────────────────────────────────────────────────
AUTO_ENGLISH_IME = True   # auto-switch to English keyboard layout

# ── Language ─────────────────────────────────────────────
LANG = "en"   # UI language: "en" or "cht"

# ── Monitor ────────────────────────────────────────────────
MONITOR_INDEX = 1

# ── Hotkeys ────────────────────────────────────────────────
TOGGLE_KEY  = "f9"   # global stop hotkey
OVERLAY_KEY = "f10"  # overlay toggle
REPORT_KEY  = "f12"  # detection report hotkey
CAPTURE_KEY = "caps lock"

# ── Config file ─────────────────────────────────────────────

CONFIG_FILE = PROJECT_ROOT / "config.json"


def load() -> dict:
    """Load settings from config.json. Returns defaults if file missing."""
    if CONFIG_FILE.is_file():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return _defaults()


def save(cfg: dict):
    """Save settings to config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except Exception:
        pass


def _defaults() -> dict:
    """Return the default settings dict."""
    return {
        "lang": LANG,
        "monitor_index": MONITOR_INDEX,
        "background_input": BACKGROUND_INPUT,
        "background_capture": BACKGROUND_CAPTURE,
        "background_fake_focus": BACKGROUND_FAKE_FOCUS,
        "background_window_title": BACKGROUND_WINDOW_TITLE,
        "crop_letterbox": CROP_LETTERBOX,
        "template_folder": TEMPLATE_FOLDER,
        "template_prefer_reference": TEMPLATE_PREFER_REF,
        "toggle_key": TOGGLE_KEY,
        "overlay_key": OVERLAY_KEY,
        "report_key": REPORT_KEY,
        "capture_key": CAPTURE_KEY,
        "mute_game": MUTE_GAME,
        "auto_english_ime": AUTO_ENGLISH_IME,
        "race_check_interval": RACE_CHECK_INTERVAL,
        "race_post_key_wait": RACE_POST_KEY_WAIT,
        "race_menu_nav": RACE_MENU_NAV,
        "race_exit_nav": RACE_EXIT_NAV,
        "wheelspin_check_interval": WHEELSPIN_CHECK_INTERVAL,
        "wheelspin_post_key_wait": WHEELSPIN_POST_KEY_WAIT,
        "buy_check_interval": BUY_CHECK_INTERVAL,
        "buy_post_key_wait": BUY_POST_KEY_WAIT,
        "mastery_cutscene_wait": MASTERY_CUTSCENE_WAIT,
        "mastery_grid_unlock_wait": MASTERY_GRID_UNLOCK_WAIT,
        "mastery_start_loop": MASTERY_START_LOOP,
        "menu_tap_wait": MENU_TAP_WAIT,
    }


def resolve_template_lang(cfg: dict) -> str:
    """Return the template language folder for the current lang setting."""
    lang = cfg.get("lang", LANG)
    return f"templates/{lang}"


def get_templates_folder(cfg: dict) -> str:
    """Return full path to the templates folder."""
    lang = cfg.get("lang", LANG)
    return str(PROJECT_ROOT / "templates" / lang)
