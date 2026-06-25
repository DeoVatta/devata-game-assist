"""
Forza Horizon 6 — Game Assistant
Entry point for CLI and future GUI / overlay integration.
"""
import sys
import os
import argparse
import io
from datetime import datetime

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Allow running as script (path resolution) or as module (-m)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from services.detector import GameDetector

# Game config (shared across modules)
from config import FORZA_PROCESS_NAMES, FORZA_WINDOW_TITLES, FORZA_XBOX_IDS, GAME_NAME, DETECTION_INTERVAL


def main():
    parser = argparse.ArgumentParser(description="Forza Horizon 6 Game Assistant")
    parser.add_argument("--watch", "-w", action="store_true",
                        help="Continuous monitoring mode")
    parser.add_argument("--interval", "-i", type=float, default=2.0,
                        help="Detection interval in seconds (default: 2)")
    parser.add_argument("--quick", "-q", action="store_true",
                        help="Quick one-shot detection and exit")
    parser.add_argument("--sources", "-s", action="store_true",
                        help="Show individual source detection results")
    args = parser.parse_args()

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
