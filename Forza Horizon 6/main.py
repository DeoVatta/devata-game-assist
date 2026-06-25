"""
Forza Horizon 6 — Game Assistant
Entry point for CLI and future GUI / overlay integration.
"""
import sys
import os
import argparse
import io
import threading
from datetime import datetime

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Allow running as script (path resolution) or as module (-m)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = _SCRIPT_DIR
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config as _cfg
from services.detector import GameDetector
from config import FORZA_PROCESS_NAMES, FORZA_WINDOW_TITLES, FORZA_XBOX_IDS, GAME_NAME


# ── Automation runners ─────────────────────────────────────

def _run_automation(name: str, module_path: str, args, cfg: dict):
    """Load and run an automation module in a daemon thread."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_automation_module", module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    stop_event = threading.Event()

    # Hotkey thread: listen for toggle key to stop
    def _hotkey_listener():
        try:
            import ctypes
            vk = _cfg.TOGGLE_KEY
            if vk.startswith("f") and vk[1:].isdigit():
                vk_code = 0x70 + (int(vk[1:]) - 1)
            else:
                vk_map = {
                    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
                    "caps lock": 0x14,
                }
                vk_code = vk_map.get(vk.lower(), 0x78)
            while not stop_event.is_set():
                if ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000:
                    stop_event.set()
                    print(f"\n[STOP] {name} — toggle key pressed")
                    break
                ctypes.windll.user32.Sleep(50)
        except Exception:
            pass

    hotkey = threading.Thread(target=_hotkey_listener, daemon=True)
    hotkey.start()

    # Wrap callbacks
    def log(msg):
        print(f"  {msg}")
    def status(msg):
        print(f"  [{name}] {msg}")

    # Get the run function
    run_fn = getattr(mod, "run", None)
    if not run_fn:
        print(f"[ERROR] {module_path} has no run() function")
        return

    try:
        if name == "Race":
            run_fn(cfg, stop_event, log_cb=log, status_cb=status,
                   max_loops=args.max_loops)
        elif name == "Mastery":
            run_fn(cfg, stop_event, log_cb=log, status_cb=status,
                   max_cars=args.max_loops)
        elif name == "Wheelspin":
            run_fn(cfg, stop_event, log_cb=log, status_cb=status,
                   spin_type=args.type or "super",
                   max_spins=args.max_loops)
        elif name == "Buy":
            run_fn(cfg, stop_event, log_cb=log, status_cb=status,
                   max_loops=args.max_loops)
    except KeyboardInterrupt:
        stop_event.set()

    hotkey.join(timeout=1)


# ── CLI ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=f"{GAME_NAME} Game Assistant")
    parser.add_argument("--watch", "-w", action="store_true",
                        help="Continuous monitoring mode")
    parser.add_argument("--interval", "-i", type=float, default=2.0,
                        help="Detection interval in seconds (default: 2)")
    parser.add_argument("--quick", "-q", action="store_true",
                        help="Quick one-shot detection and exit")
    parser.add_argument("--sources", "-s", action="store_true",
                        help="Show individual source detection results")
    sub = parser.add_subparsers(dest="command", help="Automation commands")

    # Race automation
    p_race = sub.add_parser("race", help="AFK race automation")
    p_race.add_argument("--max", "-n", dest="max_loops", type=int, default=0,
                        help="Max races (0 = unlimited)")

    # Mastery automation
    p_mast = sub.add_parser("mastery", help="Auto-unlock mastery tree")
    p_mast.add_argument("--max", "-n", dest="max_loops", type=int, default=0,
                        help="Max cars (0 = unlimited)")
    p_mast.add_argument("--cars", action="store_true",
                        help="Stop at My Cars (for chaining)")

    # Wheelspin automation
    p_ws = sub.add_parser("wheelspin", help="Auto spin wheel")
    p_ws.add_argument("--max", "-n", dest="max_loops", type=int, default=0,
                      help="Max spins (0 = unlimited)")
    p_ws.add_argument("--type", "-t", dest="type", default="super",
                      choices=["super", "normal"],
                      help="Wheel type (default: super)")
    p_ws.add_argument("--dup", "-d", type=int, default=3,
                      help="Max dupes per spin (default: 3)")

    # Buy automation
    p_buy = sub.add_parser("buy", help="Auto buy car")
    p_buy.add_argument("--max", "-n", dest="max_loops", type=int, default=0,
                       help="Max purchases (0 = unlimited)")

    args = parser.parse_args()

    # ── Automation mode ─────────────────────────────────────
    if args.command in ("race", "mastery", "wheelspin", "buy"):
        cfg = _cfg.load()
        name_map = {
            "race": ("Race", "automation/race.py"),
            "mastery": ("Mastery", "automation/mastery.py"),
            "wheelspin": ("Wheelspin", "automation/wheelspin.py"),
            "buy": ("Buy", "automation/buy.py"),
        }
        name, mod_path = name_map[args.command]
        full_path = os.path.join(_PROJECT_ROOT, mod_path)

        print(f"\n{'='*50}")
        print(f"  {GAME_NAME} — {name} Automation")
        print(f"{'='*50}")
        print(f"  Config: background_input={cfg.get('background_input', True)}")
        print(f"  Window: {cfg.get('background_window_title', 'Forza Horizon 6')}")
        print(f"  Toggle key: {cfg.get('toggle_key', 'f9')}")
        if args.max_loops:
            print(f"  Max: {args.max_loops}")
        print(f"  Press {cfg.get('toggle_key', 'f9')} to stop")
        print(f"{'='*50}\n")

        _run_automation(name, full_path, args, cfg)
        return

    # ── Detection mode ──────────────────────────────────────
    detector = GameDetector(
        process_names=FORZA_PROCESS_NAMES,
        window_titles=FORZA_WINDOW_TITLES,
        xbox_ids=FORZA_XBOX_IDS,
    )

    if args.quick:
        result = detector.quick_detect()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {GAME_NAME} — Quick Detection:")
        for source, status in result.items():
            symbol = "✓" if status else "✗"
            print(f"  {symbol} {source}: {status}")
        sys.exit(0 if result["running"] else 1)

    if args.watch:
        def print_callback(state):
            if state.is_running:
                count = state.results[0].details.get("count", 0)
                print(f"[ALERT] {GAME_NAME} is running! ({count} process(es))")
            else:
                print(f"[INFO] {GAME_NAME} is not running.")

        detector.on_state_change(print_callback)
        detector.start_watch(interval=args.interval)
        return

    # Default: full detection once
    state = detector.detect_all()
    print(f"{GAME_NAME} — Detection Report ({state.last_updated.strftime('%H:%M:%S')})")
    print(f"{'─'*50}")

    source_labels = {
        "process": "Process (psutil)",
        "window":  "Window (Win32 API)",
        "xbox":    "Xbox App Library",
        "stream":  "OBS WebSocket",
    }

    for res in state.results:
        symbol = "✓" if res.detected else "✗"
        label = source_labels.get(res.source, res.source)
        detail = ""
        if res.details and res.source != "window":
            detail = " | " + ", ".join(f"{k}={v}" for k, v in res.details.items() if v)
        elif res.source == "window":
            wins = res.details.get("windows", [])
            detail = f" | {len(wins)} window(s) found" if wins else ""
        print(f"  {symbol} {label}: {res.detected}{detail}")

    print(f"{'─'*50}")
    overall = "RUNNING" if state.is_running else "NOT RUNNING"
    print(f"  Overall: {overall}")


if __name__ == "__main__":
    main()
