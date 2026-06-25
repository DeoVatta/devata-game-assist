# ============================================================
#  buy.py — Auto buy specific car
#
#  Buy macro: Space → Down → Enter → Enter → Enter
#  Optional entry nav: main menu → Collection Log → Discover Japan
#    → Car Collection → Subaru → target car
#  Optional exit nav: Esc×4 → main menu
#
#  Each nav step is detection-gated + time-boxed (12s/step).
# ============================================================

import os
import sys
import time
import threading

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(_SCRIPT_DIR)))
for p in [_PROJECT_ROOT, _SCRIPT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from automation import GameIO, set_session_crop, set_mute_held
from detector import ScreenDetector


# ── Template keys ────────────────────────────────────────────
NAV_KEYS = [
    "collection_log",
    "discover_japan",
    "car_collection",
    "subaru",
]
BUY_KEY = "buy_car"
CONFIRM_KEY = "confirm_buy"

# ── Timing constants ──────────────────────────────────────────
BUY_MACRO = ["space", "down", "enter", "enter", "enter"]
_NAV_STEP_WINDOW  = 12.0
_START_STATE_WINDOW = 8.0
_SCROLL_NOTCHES   = 12
_SCROLL_PAUSE     = 0.12
_TARGET_SETTLE    = 2.0
_EXIT_ESC_COUNT   = 4
_EXIT_ESC_GAP     = 0.5
_EXIT_CONFIRM_WIN = 10.0


# ── Main runner ──────────────────────────────────────────────

def run(cfg: dict, stop_event: threading.Event,
        log_cb=None, status_cb=None,
        max_loops: int = 0,
        target_car: str = "22b_sti"):
    """
    Auto-buy loop.

    Args:
        cfg: config dict
        stop_event: threading.Event — set() to stop
        log_cb / status_cb: callable
        max_loops: stop after this many purchases (0 = unlimited)
        target_car: which car to target (template key, e.g. "22b_sti")
    """
    log_cb    = log_cb  or (lambda m: print(m))
    status_cb = status_cb or (lambda m: None)

    import config as _cfg_mod
    _fresh = _cfg_mod.load() if hasattr(_cfg_mod, "load") else cfg

    lang = cfg.get("lang", "en")
    check_iv = cfg.get("buy_check_interval", 0.5)
    post_kw  = cfg.get("buy_post_key_wait", 1.0)

    io = GameIO(_fresh, log_cb)
    set_session_crop(True)
    io.mute(_fresh)
    set_mute_held(True)
    io.start_keepalive(lambda: stop_event.is_set(), _fresh)

    # Load templates from feature subfolder: templates/<lang>/buy/built-in/
    import config as _cfg_mod
    tpl_lang = _cfg_mod.resolve_template_lang(_fresh)
    tpl_base = _cfg_mod.get_templates_folder(_fresh)
    tpl_folder = os.path.join(tpl_base, "buy", "built-in")

    detector = ScreenDetector(_fresh)
    templates = {}

    all_keys = NAV_KEYS + [target_car]
    if BUY_KEY not in all_keys:
        all_keys.append(BUY_KEY)

    for key in all_keys:
        try:
            from capture import load_template
            img, scale, meta = load_template(
                tpl_folder, key, io.width, io.height,
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
                    meta.get("screen_width", io.width),
                    meta.get("screen_height", io.height),
                )
            log_cb(f"  Template: {key} (scale={scale:.2f})")
        except FileNotFoundError:
            pass

    nav_available = all(k in templates for k in NAV_KEYS)

    def stop():
        return stop_event.is_set()

    def wait_for(key, timeout=float("inf"), warn=True):
        status_cb(f"[Buy] Waiting: {key}")
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
        log_cb(f"  Timeout: {key}")
        return None

    def step_press(keys, gap=0.1):
        for k in keys:
            if stop():
                return
            io.press(k, post_wait=gap)

    def announce(msg):
        log_cb(msg)
        status_cb(msg)

    # ── Entry navigation ─────────────────────────────────────
    if nav_available:
        log_cb("[Buy] Starting entry navigation")
        announce("[Buy] Navigating to target car...")

        nav_steps = [
            ("collection_log",  "Collection Log"),
            ("discover_japan",  "Discover Japan"),
            ("car_collection",  "Car Collection"),
            ("subaru",          "Subaru brand"),
        ]

        for key, label in nav_steps:
            if stop():
                break
            announce(f"[Buy] {label}")
            result = wait_for(key, timeout=_NAV_STEP_WINDOW)
            if not result:
                log_cb(f"[Buy] Nav failed at {key} — falling back to macro only")
                break
            io.click(*result.location, post_wait=1.0)

            # After car_collection, scroll and click target car
            if key == "car_collection":
                announce("[Buy] Scrolling to target car...")
                io.scroll(-_SCROLL_NOTCHES, post_wait=_SCROLL_PAUSE)
                time.sleep(_TARGET_SETTLE)
                if target_car in templates:
                    r = wait_for(target_car, timeout=_NAV_STEP_WINDOW)
                    if r:
                        io.click(*r.location, post_wait=1.0)

    else:
        log_cb("[Buy] Nav templates missing — running macro where you are")

    # ── Buy loop ─────────────────────────────────────────────
    log_cb("[Buy] Starting buy loop")
    buy_count = 0

    while not stop():
        announce(f"[Buy] Purchase #{buy_count + 1}")

        # Run the buy macro
        for key_name in BUY_MACRO:
            if stop():
                break
            io.press(key_name, post_wait=post_kw)

        buy_count += 1
        log_cb(f"  Purchased #{buy_count}")

        if max_loops > 0 and buy_count >= max_loops:
            log_cb(f"[Buy] Limit reached: {max_loops} purchases")
            break

        time.sleep(0.5)

    # ── Exit navigation ──────────────────────────────────────
    if nav_available:
        log_cb("[Buy] Running exit navigation")
        announce("[Buy] Returning to main menu...")
        for _ in range(_EXIT_ESC_COUNT):
            if stop():
                break
            io.press("esc", post_wait=_EXIT_ESC_GAP)

        # Confirm back on main menu
        if "collection_log" in templates:
            result = wait_for("collection_log", timeout=_EXIT_CONFIRM_WIN)
            if result:
                log_cb("[Buy] Back on main menu")

    set_mute_held(False)
    io.cleanup()
    log_cb(f"[Buy] Stopped. Purchased {buy_count} car(s).")
    status_cb(f"[Buy] Done — {buy_count} car(s).")
