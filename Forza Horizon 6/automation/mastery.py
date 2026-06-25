# ============================================================
#  mastery.py — Keyboard-driven mastery tree automation
#
#  Zero detection — fully keyboard-driven.
#  Navigates 4x4 mastery tree with WASD + Enter.
#
#  Per car:
#    Enter → Ride → cutscene → ESC → Down+Enter → Down+Enter
#    → unlock grid → ESC×2 → Up+Enter → X+sort → next car
# ============================================================

import os
import sys
import time
import threading
import json

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(_SCRIPT_DIR)))
for p in [_PROJECT_ROOT, _SCRIPT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from automation import GameIO, set_session_crop, set_mute_held


# ── Grid constants ────────────────────────────────────────────
_GRID_ROWS    = 4
_GRID_COLS    = 4
_GRID_START   = (_GRID_ROWS - 1, 0)  # bottom-left cell
_GARAGE_ROWS   = 3

# ── Timing constants ──────────────────────────────────────────
_POST_KEY_WAIT          = 1.25
_POST_CUTSCENE_ESC_WAIT = 1.75
_KEYS_CUTSCENE_WAIT     = 11.0   # default; overridable via cfg
_KEYS_SCREEN_WAIT       = 1.5
_TAP_WAIT               = 0.25   # between repeated Up/Down taps
_GRID_MOVE_WAIT         = 0.25
_GRID_UNLOCK_WAIT       = 1.25


# ── Garage cell calculator ───────────────────────────────────

def _cell_at(first_row: int, index: int):
    """(row, col) of the index-th car in a top→bottom column-major fill.
    first_row: starting row of column 0 (1-based, e.g. 1 or 2 or 3)."""
    first_col_count = _GARAGE_ROWS - first_row + 1
    if index < first_col_count:
        return (first_row + index, 0)
    rem = index - first_col_count
    return (1 + rem % _GARAGE_ROWS, 1 + rem // _GARAGE_ROWS)


def _moves_between(prev, cur):
    """WASD moves from prev (row,col) to cur for top→bottom traversal."""
    pr, pc = prev
    r, c = cur
    if c == pc:
        return ["s"] * (r - pr)
    return ["d"] * (c - pc) + ["w"] * (pr - r)


# ── Grid loader ──────────────────────────────────────────────

def _load_grid(path: str):
    """Load mastery tree path from JSON file. Returns list of (row, col)."""
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # Support both list of [row, col] and list of {"row": r, "col": c}
            result = []
            for item in data:
                if isinstance(item, (list, tuple)):
                    result.append((int(item[0]), int(item[1])))
                elif isinstance(item, dict):
                    result.append((int(item.get("row", 0)), int(item.get("col", 0))))
            return result
        except Exception:
            pass
    return []


# ── Main runner ──────────────────────────────────────────────

def run(cfg: dict, stop_event: threading.Event,
        log_cb=None, status_cb=None,
        max_cars: int = 0,
        grid_file: str = None,
        end_at_mycars: bool = False,
        start_loop: int = None):
    """
    Unlock mastery tree on every car in the garage, one at a time.

    Args:
        cfg: config dict
        stop_event: threading.Event — set() to stop
        log_cb: callable
        status_cb: callable
        max_cars: stop after this many cars (0 = unlimited)
        grid_file: path to JSON grid path spec
        end_at_mycars: on final car, stop in My Cars (for chaining into sell)
        start_loop: which garage row the FIRST car is on (1-based, 1-3)
    """
    log_cb   = log_cb  or (lambda m: print(m))
    status_cb = status_cb or (lambda m: None)

    import config as _cfg_mod
    _fresh = _cfg_mod.load() if hasattr(_cfg_mod, "load") else cfg

    lang = cfg.get("lang", "en")
    if start_loop is None:
        start_loop = max(1, min(3, int(_fresh.get("mastery_start_loop", 1))))
    else:
        start_loop = max(1, min(3, int(start_loop)))

    cut_wait    = max(_KEYS_CUTSCENE_WAIT,
                      float(_fresh.get("mastery_cutscene_wait", _KEYS_CUTSCENE_WAIT)))
    screen_wait = _KEYS_SCREEN_WAIT
    tap_wait    = max(0.1, min(0.5, float(_fresh.get("menu_tap_wait", _TAP_WAIT))))
    grid_unlock_wait = max(0.25,
                           float(_fresh.get("mastery_grid_unlock_wait", _GRID_UNLOCK_WAIT)))

    io = GameIO(_fresh, log_cb)
    set_session_crop(True)
    io.mute(_fresh)
    set_mute_held(True)
    io.start_keepalive(lambda: stop_event.is_set(), _fresh)

    if not io.bg and _fresh.get("auto_english_ime", True):
        from capture import force_english_ime
        force_english_ime()
        time.sleep(0.2)

    # Load grid path from mastery_full subfolder: templates/<lang>/mastery_full/mastery_grid.json
    import config as _cfg_mod
    tpl_lang = _cfg_mod.resolve_template_lang(_fresh)
    tpl_base = _cfg_mod.get_templates_folder(_fresh)
    grid_folder = os.path.join(tpl_base, "mastery_full")
    gfile = grid_file or os.path.join(grid_folder, "mastery_grid.json")
    grid_order = _load_grid(gfile)
    if not grid_order:
        log_cb("[Mastery] ERROR: mastery_grid.json not found — cannot run")
        status_cb("[Mastery] Setup incomplete")
        io.cleanup()
        return

    log_cb(f"[Mastery] Grid path: {len(grid_order)} nodes")

    def stop():
        return stop_event.is_set()

    def wait(seconds):
        end = time.time() + seconds
        while time.time() < end:
            if stop():
                return
            time.sleep(0.1)

    def taps(key, n):
        for _ in range(n):
            if stop():
                return
            io.press(key, post_wait=tap_wait)

    def announce(msg):
        log_cb(msg)
        status_cb(msg)

    announce("[Mastery] Started")
    car_num = 0

    while not stop():
        car_num += 1
        is_first = (car_num == 1)

        # ── 1. Navigate to car ──────────────────────────────
        idx = car_num - 1
        nav_keys = ([] if is_first
                    else _moves_between(_cell_at(start_loop, idx - 1),
                                        _cell_at(start_loop, idx)))

        if nav_keys:
            announce(f"[Mastery] Car {car_num}/{max_cars if max_cars else '∞'} — navigating")
            log_cb(f"  WASD: {' '.join(k.upper() for k in nav_keys)}")
            for key in nav_keys:
                if stop():
                    break
                io.press(key, scancode=True)
                time.sleep(0.4)
            time.sleep(0.3)
        else:
            announce(f"[Mastery] Car {car_num}/{max_cars if max_cars else '∞'} — start")

        if stop():
            break

        # ── 2. Enter → action menu ──────────────────────────
        announce(f"[Mastery] Car #{car_num}: action menu")
        io.press("enter", post_wait=_POST_KEY_WAIT)
        if stop():
            break

        # ── 3. Enter → Ride This Car ───────────────────────
        announce(f"[Mastery] Car #{car_num}: riding")
        io.press("enter", post_wait=0.0)

        # ── 4. Cutscene wait → ESC ──────────────────────────
        announce(f"[Mastery] Car #{car_num}: cutscene")
        wait(cut_wait)
        if stop():
            break
        io.press("esc", post_wait=_POST_CUTSCENE_ESC_WAIT)
        if stop():
            break

        # ── 5. Down×1 + Enter → Upgrade & Tuning ────────────
        announce(f"[Mastery] Car #{car_num}: upgrade menu")
        taps("down", 1)
        if stop():
            break
        io.press("enter", post_wait=_POST_KEY_WAIT)
        if stop():
            break

        # ── 6. Down×7 + Enter → Car Mastery ────────────────
        announce(f"[Mastery] Car #{car_num}: mastery tree")
        taps("down", 7)
        if stop():
            break
        io.press("enter", post_wait=0.0)

        # ── 7. Wait for Mastery screen ─────────────────────
        announce(f"[Mastery] Car #{car_num}: unlocking nodes")
        wait(screen_wait)
        if stop():
            break

        # ── 8. Unlock nodes via WASD + Enter ───────────────
        announce(f"[Mastery] Car #{car_num}: unlocking {len(grid_order)} nodes")
        cur = _GRID_START
        for i, (gr, gc) in enumerate(grid_order, start=1):
            if stop():
                break
            dr, dc = gr - cur[0], gc - cur[0]
            keys = []
            keys += ["w"] * (-dr) if dr < 0 else ["s"] * dr
            keys += ["a"] * (-dc) if dc < 0 else ["d"] * dc
            log_cb(f"  Node {i}/{len(grid_order)}: {' '.join(k.upper() for k in keys + ['ENTER'])}")
            for k in keys:
                if stop():
                    break
                io.press(k, scancode=True, post_wait=_GRID_MOVE_WAIT)
            if stop():
                break
            io.press("enter", post_wait=grid_unlock_wait)
            cur = (gr, gc)

        if stop():
            break

        # ── 9. ESC×2 → exit ────────────────────────────────
        announce(f"[Mastery] Car #{car_num}: exiting")
        io.press("esc", post_wait=_POST_KEY_WAIT)
        io.press("esc", post_wait=_POST_KEY_WAIT)
        if stop():
            break

        # ── 10. Up×1 + Enter → My Cars ────────────────────
        announce(f"[Mastery] Car #{car_num}: my cars")
        taps("up", 1)
        if stop():
            break
        io.press("enter", post_wait=_POST_KEY_WAIT)
        if stop():
            break

        is_last = max_cars > 0 and car_num >= max_cars
        if is_last and end_at_mycars:
            log_cb(f"[Mastery] Limit reached ({max_cars} cars) — stopped in My Cars")
            break

        # ── 11. X + Down×6 + Enter → sort by Recently Added ──
        announce(f"[Mastery] Car #{car_num}: sorting")
        io.press("x", post_wait=_POST_KEY_WAIT)
        taps("down", 6)
        if stop():
            break
        io.press("enter", post_wait=_POST_KEY_WAIT)

        if is_last:
            log_cb(f"[Mastery] Limit reached ({max_cars} cars)")
            break

    set_mute_held(False)
    io.cleanup()
    log_cb(f"[Mastery] Stopped. Processed {car_num - 1} car(s).")
    status_cb("[Mastery] Stopped.")
