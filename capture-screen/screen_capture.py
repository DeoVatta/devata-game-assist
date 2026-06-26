# screen_capture.py
# Screenshot capture tool for Claude analysis
# Usage: python screen_capture.py [command]

import mss
import os
import sys
from datetime import datetime

OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
MAX_SCREENSHOTS = 20

def cleanup_old_screenshots():
    """Hapus screenshot tertua jika lebih dari MAX_SCREENSHOTS (FIFO)"""
    if not os.path.exists(OUTPUT_FOLDER):
        return

    files = sorted(
        [f for f in os.listdir(OUTPUT_FOLDER) if f.endswith('.png')],
        key=lambda f: os.path.getmtime(os.path.join(OUTPUT_FOLDER, f))
    )

    while len(files) > MAX_SCREENSHOTS:
        oldest = files.pop(0)
        filepath = os.path.join(OUTPUT_FOLDER, oldest)
        os.remove(filepath)
        print(f"    [-] Removed oldest: {oldest}")

def take_screenshot(filename=None):
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"

    filepath = os.path.join(OUTPUT_FOLDER, filename)

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        sct_img = sct.grab(monitor)
        mss.tools.to_png(sct_img.rgb, sct_img.size, output=filepath)

    size = os.path.getsize(filepath)
    print(f"[+] Saved: {filepath}")
    print(f"    {size/1024:.0f} KB | {sct_img.width}x{sct_img.height}px")
    cleanup_old_screenshots()
    return filepath

def take_monitor(monitor_num=1, filename=None):
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"monitor{monitor_num}_{timestamp}.png"

    filepath = os.path.join(OUTPUT_FOLDER, filename)

    with mss.mss() as sct:
        monitor = sct.monitors[monitor_num]
        sct_img = sct.grab(monitor)
        mss.tools.to_png(sct_img.rgb, sct_img.size, output=filepath)

    size = os.path.getsize(filepath)
    print(f"[+] Saved: {filepath}")
    print(f"    Monitor {monitor_num} | {size/1024:.0f} KB | {sct_img.width}x{sct_img.height}px")
    return filepath

def list_screenshots():
    if not os.path.exists(OUTPUT_FOLDER):
        print("[!] No screenshots folder yet")
        return

    files = sorted([f for f in os.listdir(OUTPUT_FOLDER) if f.endswith('.png')], reverse=True)
    if not files:
        print("[!] No screenshots found")
        return

    print(f"\n=== {OUTPUT_FOLDER} ===")
    for f in files[:10]:
        fp = os.path.join(OUTPUT_FOLDER, f)
        size = os.path.getsize(fp)
        mtime = datetime.fromtimestamp(os.path.getmtime(fp))
        print(f"  {f} | {size/1024:.0f} KB | {mtime.strftime('%H:%M:%S')}")

def main():
    print("=" * 40)
    print("   CLAUDE SCREEN CAPTURE")
    print("=" * 40)

    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else None

    if cmd == "list":
        list_screenshots()
    elif cmd == "mon1":
        take_monitor(1)
    elif cmd == "mon2":
        take_monitor(2)
    elif cmd == "mon3":
        take_monitor(3)
    elif cmd == "help":
        print("""
Usage: python screen_capture.py [command]

Commands:
  (none)  - Screenshot all monitors
  mon1    - Screenshot monitor 1
  mon2    - Screenshot monitor 2
  mon3    - Screenshot monitor 3
  list    - List recent screenshots
  help    - This help

After screenshot, drag PNG into Claude Code chat.
""")
    else:
        take_screenshot()
        print(f"\n[+] Drag the PNG from:")
        print(f"    {OUTPUT_FOLDER}")
        print(f"    into Claude Code chat to analyze")

if __name__ == "__main__":
    main()
