# ============================================================
#  race.py — AFK race automation
#
#  Loop: detect start_menu → Enter → hold W (blind, ~4s) →
#        detect restart_menu → X → Enter → loop
#
#  Optional 8-step menu navigation when all nav templates are captured.
#  Stop: GetAsyncKeyState(toggle_vk) polled at ~33Hz.
# ============================================================

import os
import sys
import time
import threading
import ctypes
from ctypes import wintypes

# Resolve paths for script/module execution
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(_SCRIPT_DIR)))
for p in [_PROJECT_ROOT, _SCRIPT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from capture import get_monitor_dims, load_template
from detector import ScreenDetector, MatchResult
from automation import GameIO, set_session_crop, set_mute_held
import config as _cfg_mod


# ── Template keys used ────────────────────────────────────────
# Minimal set: only start_menu and restart_menu are required.
# All others are optional navigation helpers.
TEMPLATE_KEYS = ["start_menu", "restart_menu"]
NAV_KEYS = [
    "creative_hub", "eventlab", "play_event", "events_arrow",
    "my_history", "choose_race_type", "car_select",
]
NAV_KEYS_OPTIONAL = ["next_activity"]  # exit: results → main menu
ALL_KEYS = TEMPLATE_KEYS + NAV_KEYS + NAV_KEYS_OPTIONAL

# ── Feature name for template subfolder ────────────────────────
_FEATURE = "race"

# ── Timing constants ──────────────────────────────────────────
_PRE_W_WAIT    = 4.0    # after Enter, wait before holding W
_CONFIRM_WAIT  = 1.25   # after X, wait before Enter
_NAV_SETTLE    = 0.3    # settle before each nav action
_NAV_STEP_WIN  = 12.0   # per-nav-step timeout before abort
_NAV_LOAD_WIN  = 45.0   # total window for MY_HISTORY load
_NAV_PRESS_CD  = 1.2    # cooldown between Enter re-presses in nav


# ── Virtual key helpers ──────────────────────────────────────

_VK_MAP = {
    "enter": 0x0D, "x": 0x58, "escape": 0x1B,
    "w": 0x57, "f9": 0x78,
}


def _vk_for_key(name):
    name = (name or "").strip().lower()
    if name in _VK_MAP:
        return _VK_MAP[name]
    if name.startswith("f") and name[1:].isdigit():
        n = int(name[1:])
        if 1 <= n <= 24:
            return 0x70 + (n - 1)
    if len(name) == 1:
        return ord(name.upper())
    return None


# ── Main runner ──────────────────────────────────────────────

def run(cfg: dict, stop_event: threading.Event,
        log_cb=None, status_cb=None,
        max_loops: int = 0):
    """
    Run the AFK race loop.

    Args:
        cfg: config dict (lang, monitor_index, race_check_interval, etc.)
        stop_event: threading.Event — set() to stop
        log_cb: callable — log line receiver
        status_cb: callable — status bar updater
        max_loops: stop after this many completed races (0 = unlimited)
    """
    log_cb  = log_cb  or (lambda m: print(m))
    status_cb = status_cb or (lambda m: None)

    lang   = cfg.get("lang", "en")
    mon_i  = cfg.get("monitor_index", 1)
    post_kw = cfg.get("race_post_key_wait", 0.75)
    check_iv = cfg.get("race_check_interval", 0.5)
    nav_enabled = cfg.get("race_menu_nav", True)
    exit_enabled = cfg.get("race_exit_nav", True)

    io = GameIO(_fresh, log_cb)
    current_w, current_h = io.width, io.height
    mon_left, mon_top = io.cap_left, io.cap_top

    # Session-level letterbox crop + mute
    set_session_crop(True)
    io.mute(_fresh)
    set_mute_held(True)

    # Load templates from feature subfolder: templates/<lang>/race/built-in/
    tpl_lang = _cfg_mod.resolve_template_lang(_fresh)
    tpl_base = _cfg_mod.get_templates_folder(_fresh)
    tpl_folder = os.path.join(tpl_base, _FEATURE, "built-in")

    detector = ScreenDetector(_fresh)
    templates = {}

    for key in ALL_KEYS:
        try:
            img, scale, meta = load_template(
                tpl_folder, key, current_w, current_h,
                grayscale=True,
                ref_folder="templates/built-in",
                prefer_ref=True,
            )
            templates[key] = img
            detector.register_template(key, img, threshold=0.80)
            box = meta.get("box")
            if box:
                detector.set_template_geometry(
                    key, box,
                    meta.get("screen_width", current_w),
                    meta.get("screen_height", current_h),
                )
            log_cb(f"  Template: {key} (scale={scale:.2f})")
        except FileNotFoundError:
            pass  # optional nav template missing — nav disabled below

    # Check nav coverage
    nav_tpls = {k: templates[k] for k in NAV_KEYS if k in templates}
    nav_available = all(k in nav_tpls for k in NAV_KEYS) and nav_enabled
    exit_tpl = templates.get("next_activity") and nav_tpls.get("creative_hub") and exit_enabled

    if not nav_available:
        log_cb("  [Race] Nav templates not available — waiting for start_menu directly")

    # Toggle hotkey VK for stop detection
    toggle_vk = _vk_for_key(_fresh.get("toggle_key", "f9"))

    io.start_keepalive(lambda: stop_event.is_set() or _check_toggle(toggle_vk), _fresh)

    if not io.bg and _fresh.get("auto_english_ime", True):
        from capture import force_english_ime
        force_english_ime()
        time.sleep(0.2)

    race_count = 0

    # ── Optional menu navigation ──────────────────────────────
    if nav_available:
        log_cb("[Race] Starting menu navigation to Start Race screen")
        status_cb("[Race] Navigating menus...")
        nav_success = _run_nav(io, detector, nav_tpls, stop_event, _fresh,
                                log_cb, check_iv)
        if nav_success is False:
            log_cb("[Race] Nav failed or stopped — aborting")
            io.cleanup()
            return

    # ── Main race loop ───────────────────────────────────────
    log_cb("[Race] Race loop started")
    status_cb("[Race] Running...")

    def stop():
        if stop_event.is_set():
            return True
        return _check_toggle(toggle_vk)

    def wait_for(key, timeout=float("inf"), warn=True):
        status_cb(f"[Race] Waiting for: {key}")
        result = detector.wait_for(
            frame_cb=io.grab,
            key=key,
            threshold=0.80,
            stop_cb=stop,
            interval=check_iv,
            timeout=timeout,
        )
        if result:
            log_cb(f"  Detected: {key} ({result.score:.0%})")
            return result
        log_cb(f"  Timeout / stopped waiting for: {key}")
        return None

    def tap(key, post_wait=None):
        io.press(key, post_wait=post_wait or post_kw)

    while not stop():
        # 1. Wait for start_menu
        log_cb(f"[Race] Waiting for start_menu ({race_count}/{max_loops if max_loops else '∞'})")
        if not wait_for("start_menu", timeout=120, warn=False):
            break

        # 2. Enter to start
        log_cb("  → Enter (start race)")
        tap("enter")

        # 3. Hold W — sustained keydown at ~33Hz
        log_cb("  → Holding W (driving blind)")
        _run_hold_w(io, stop, post_kw)

        # 4. Wait for restart_menu
        log_cb("  → Waiting for race to finish")
        if not wait_for("restart_menu", timeout=600, warn=False):
            break

        # 5. X to confirm restart
        log_cb("  → X (confirm restart)")
        tap("x", _CONFIRM_WAIT)

        race_count += 1
        log_cb(f"  Race #{race_count} complete")
        status_cb(f"[Race] #{race_count} done")

        if max_loops > 0 and race_count >= max_loops:
            log_cb(f"[Race] Reached limit: {max_loops} races")
            break

        # 6. Optional: detect next_activity → Esc → main menu
        if exit_enabled:
            # Short wait for results screen
            time.sleep(1.0)
            frame = io.grab()
            if frame is not None:
                result = detector.detect(frame, "next_activity", stable=False)
                if result:
                    log_cb("  → Next activity detected — pressing Enter")
                    tap("enter", 2.0)
                    io.press("escape", post_wait=1.0)
                    io.press("escape", post_wait=1.0)
                    io.press("escape", post_wait=1.0)
                    log_cb("  → Returned to main menu")

    set_mute_held(False)
    io.cleanup()
    log_cb(f"[Race] Stopped. Completed {race_count} race(s).")
    status_cb("[Race] Stopped.")


# ── Helpers ───────────────────────────────────────────────────

def _check_toggle(vk):
    if not vk:
        return False
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


def _run_hold_w(io: GameIO, stop_cb, post_kw):
    """Hold W at ~33Hz (30ms tick) until stop_cb returns True."""
    io.hold_press("w")
    try:
        while not stop_cb():
            time.sleep(0.03)
            io.hold_press("w")
    finally:
        io.release("w")


def _run_nav(io, detector, nav_tpls, stop_event, cfg,
             log_cb, check_iv):
    """Run the optional 8-step menu navigation. Returns True on success, False on abort."""
    steps = [
        ("creative_hub",    "→ Creative Hub"),
        ("eventlab",         "→ EventLab"),
        ("play_event",       "→ Play Event"),
        ("events_arrow",     "→ Events arrow"),
        ("my_history",       "→ My History"),
        ("choose_race_type", "→ Race type"),
        ("car_select",       "→ Car select"),
    ]

    for key, label in steps:
        if stop_event.is_set():
            return False
        if key not in nav_tpls:
            log_cb(f"  [Nav] Missing: {key} — skipping nav")
            return False

        log_cb(f"  [Nav] {label}")
        result = detector.wait_for(
            frame_cb=io.grab,
            key=key,
            threshold=0.80,
            stop_cb=stop_event.is_set,
            interval=check_iv,
            timeout=_NAV_STEP_WIN,
        )
        if not result:
            log_cb(f"  [Nav] Timed out: {key}")
            return False

        io.press("enter", post_wait=_NAV_SETTLE)

    return True
