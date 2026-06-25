# ============================================================
#  wheelspin.py — Auto spin wheel automation
#
#  Detection-gated at every transition.
#  Super Wheelspin: 3 wheels → 1 Enter collects all 3 prizes.
#
#  Per spin:
#    1. wait_for(skip)  → Enter (best-effort fast-forward)
#    2. wait_for(collect) → Enter (collect all + start next spin)
#    3. inner loop: detect duplicate → Enter (up to 3 dups/spin)
#  Final spin → detect(collect_final) → Enter → ends on main menu
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

from detector import ScreenDetector, MatchResult
from automation import GameIO, set_session_crop, set_mute_held


# ── Template keys ────────────────────────────────────────────
# my_horizon_tab: optional — lets us start from main menu
# super/normal wheelspin: the tile to click to start
# wheelspin_skip: best-effort fast-forward
# wheelspin_collect: collect prompt
# wheelspin_collect_final: last spin (no more spins left)
# wheelspin_duplicate: per-duplicate confirmation

TEMPLATE_KEYS = [
    "my_horizon_tab",
    "super_wheelspin",
    "normal_wheelspin",
    "wheelspin_skip",
    "wheelspin_collect",
    "wheelspin_collect_final",
    "wheelspin_duplicate",
]

# ── Timing constants ──────────────────────────────────────────
SUPER_FIND_WINDOW = 12.0  # max time to find the start tile
MH_TAB_WINDOW     = 8.0    # max time to find My Horizon tab
MAX_DUP_CHAIN     = 3      # hard cap — prevents runaway on mis-detect
_DETECT_IV        = 0.3    # polling interval


# ── Main runner ──────────────────────────────────────────────

def run(cfg: dict, stop_event: threading.Event,
        log_cb=None, status_cb=None,
        spin_type: str = "super",
        max_spins: int = 0,
        max_dup_chain: int = MAX_DUP_CHAIN):
    """
    Run the auto spin wheel loop.

    Args:
        cfg: config dict
        stop_event: threading.Event — set() to stop
        log_cb / status_cb: callable
        spin_type: "super" or "normal"
        max_spins: stop after this many spins (0 = unlimited)
        max_dup_chain: max duplicate confirmations per spin
    """
    log_cb    = log_cb  or (lambda m: print(m))
    status_cb = status_cb or (lambda m: None)

    import config as _cfg_mod
    _fresh = _cfg_mod.load() if hasattr(_cfg_mod, "load") else cfg

    lang = cfg.get("lang", "en")
    check_iv = cfg.get("wheelspin_check_interval", _DETECT_IV)
    post_kw = cfg.get("wheelspin_post_key_wait", 0.5)

    io = GameIO(_fresh, log_cb)
    set_session_crop(True)
    io.mute(_fresh)
    set_mute_held(True)
    io.start_keepalive(lambda: stop_event.is_set(), _fresh)

    # Load templates
    tpl_lang = _fresh.get("lang", "en")
    tpl_folder = _fresh.get("template_folder", "templates/en")
    detector = ScreenDetector(_fresh)
    templates = {}
    tile_key = f"{spin_type}_wheelspin"

    for key in TEMPLATE_KEYS:
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

    # Check tile availability
    if tile_key not in templates:
        log_cb(f"[Wheelspin] ERROR: {tile_key} template not found — cannot run")
        status_cb("[Wheelspin] Setup incomplete")
        io.cleanup()
        return

    tab_available = "my_horizon_tab" in templates

    def stop():
        return stop_event.is_set()

    def wait_for(key, timeout=float("inf"), warn=True):
        status_cb(f"[Wheelspin] Waiting: {key}")
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
        return None

    def tap(key, post_wait=None):
        io.press(key, post_wait=post_wait or post_kw)

    # ── Entry: navigate to My Horizon ───────────────────────
    if tab_available:
        log_cb("[Wheelspin] Finding My Horizon tab...")
        result = wait_for("my_horizon_tab", timeout=MH_TAB_WINDOW)
        if result:
            io.click(*result.location, post_wait=1.5)
        else:
            log_cb("[Wheelspin] My Horizon tab not found — assuming already there")

    # ── Find and click the wheel spin tile ──────────────────
    log_cb(f"[Wheelspin] Finding {spin_type} wheelspin tile...")
    status_cb(f"[Wheelspin] Locating {spin_type}...")
    result = wait_for(tile_key, timeout=SUPER_FIND_WINDOW)
    if result:
        io.click(*result.location, post_wait=0.5)
        log_cb("  Tile clicked — spin started")
    else:
        log_cb("[Wheelspin] Tile not found — aborting")
        io.cleanup()
        return

    # ── Spin loop ───────────────────────────────────────────
    log_cb("[Wheelspin] Spin loop started")
    spin_count = 0
    _dup_cap = max(1, min(3, max_dup_chain))

    while not stop():
        # 1. Best-effort skip fast-forward
        skip_tpl = templates.get("wheelspin_skip")
        if skip_tpl:
            time.sleep(0.2)
            frame = io.grab()
            if frame is not None:
                r = detector.detect(frame, "wheelspin_skip", stable=False)
                if r:
                    log_cb("  → Skip prompt detected — fast-forwarding")
                    tap("enter", 0.3)

        # 2. Wait for collect prompt
        log_cb(f"[Wheelspin] Spin #{spin_count + 1} — waiting for collect prompt")
        status_cb(f"[Wheelspin] Spin #{spin_count + 1}")
        result = wait_for("wheelspin_collect", timeout=60)
        if not result:
            log_cb("[Wheelspin] Collect prompt timed out — checking for final")
            # Check for final collect
            frame = io.grab()
            if frame is not None:
                r = detector.detect(frame, "wheelspin_collect_final", stable=False)
                if r:
                    io.click(*r.location, post_wait=1.0)
                    spin_count += 1
                    break
            break

        # 3. Enter to collect all 3 prizes + start next spin
        log_cb("  → Enter (collect + next spin)")
        io.click(*result.location, post_wait=0.5)
        spin_count += 1

        if max_spins > 0 and spin_count >= max_spins:
            log_cb(f"[Wheelspin] Limit reached: {max_spins} spins")
            break

        # 4. Handle duplicates
        dup_count = 0
        while dup_count < _dup_cap and not stop():
            frame = io.grab()
            if frame is None:
                break
            r = detector.detect(frame, "wheelspin_duplicate", stable=False)
            if r:
                log_cb(f"  → Duplicate detected (#{dup_count + 1}) — accepting")
                io.click(*r.location, post_wait=0.5)
                dup_count += 1
            else:
                break

        if stop():
            break

        # 5. Check for final spin (collect_final = no more spins)
        time.sleep(0.5)
        frame = io.grab()
        if frame is not None:
            r = detector.detect(frame, "wheelspin_collect_final", stable=False)
            if r:
                log_cb("[Wheelspin] Final spin detected — collecting and ending")
                io.click(*r.location, post_wait=1.0)
                spin_count += 1
                break

    set_mute_held(False)
    io.cleanup()
    log_cb(f"[Wheelspin] Stopped. Completed {spin_count} spin(s).")
    status_cb(f"[Wheelspin] Done — {spin_count} spin(s).")
