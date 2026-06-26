# capture_loop.py
# Continuous screen capture - runs in background
# Auto-cleans old screenshots (FIFO, 30 min / 10 sec = 180 max)

import mss
import time
import sys
import os
from datetime import datetime
from pathlib import Path

# ============== CONFIG ==============
SCRIPT_DIR = Path(__file__).parent
CAPTURE_DIR = SCRIPT_DIR / "screenshots"
CAPTURE_DIR.mkdir(exist_ok=True)

INTERVAL = 10          # seconds between captures
MAX_CAPTURES = 180     # 180 x 10s = 30 minutes

# ============== FIFO CLEANUP ==============
def cleanup():
    files = sorted(
        [f for f in CAPTURE_DIR.iterdir() if f.suffix == '.png'],
        key=lambda f: f.stat().st_mtime
    )
    removed = 0
    while len(files) > MAX_CAPTURES:
        old = files.pop(0)
        old.unlink()
        removed += 1
    return removed

# ============== CAPTURE ==============
def capture():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = CAPTURE_DIR / f"{timestamp}.png"

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        img = sct.grab(monitor)
        mss.tools.to_png(img.rgb, img.size, output=str(filepath))

    return filepath, filepath.stat().st_size // 1024

# ============== MAIN LOOP ==============
def main():
    print("=" * 50)
    print("   CONTINUOUS CAPTURE - 10s interval")
    print("   History: 30 min (180 captures)")
    print("=" * 50)
    print(f"\nOutput: {CAPTURE_DIR}")
    print("Press Ctrl+C to stop.\n")

    capture_count = 0
    start_time = datetime.now()

    while True:
        try:
            path, size_kb = capture()
            capture_count += 1

            # Print every minute
            if capture_count % 6 == 0:
                elapsed = datetime.now() - start_time
                mins = int(elapsed.total_seconds() // 60)
                secs = int(elapsed.total_seconds() % 60)
                total = len(list(CAPTURE_DIR.glob('*.png')))
                print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                      f"OK | {mins}m | {capture_count} caps | {total} files | {size_kb}KB")

            removed = cleanup()

            time.sleep(INTERVAL)

        except KeyboardInterrupt:
            elapsed = datetime.now() - start_time
            mins = int(elapsed.total_seconds() // 60)
            secs = int(elapsed.total_seconds() % 60)
            total = len(list(CAPTURE_DIR.glob('*.png')))
            print(f"\nStopped. {capture_count} captures in {mins}m {secs}s | {total} files in history")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
