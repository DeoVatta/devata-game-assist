# overlay_drawer.py
# Full-screen transparent overlay — draws rect/circle with breathing outline
# Architecture: subprocess-based (tkinter runs in its own process, clean and stable)
# Draw commands passed via command-line arguments.
#
# Usage:
#   python overlay_drawer.py --rect --x 500 --y 300 --w 200 --h 100 --label "Item" --dur 8
#   python overlay_drawer.py --circle --cx 960 --cy 540 --r 60 --label "Portal" --dur 8
#
# Python API (spawns subprocess):
#   from overlay_drawer import show_rect, show_circle, close_all
#   show_rect(x, y, w, h, label="", duration=5)
#   show_circle(cx, cy, r, label="", duration=5)
#   close_all()

import subprocess
import sys
import os
import time
import threading
import uuid

_lock = threading.Lock()
_active = {}   # pid -> proc


def show_rect(x, y, w, h, label="", color="#00FF00", duration=5):
    _spawn_proc(["--rect",
                 "--x", str(x), "--y", str(y),
                 "--w", str(w), "--h", str(h),
                 "--label", label,
                 "--color", color,
                 "--dur", str(duration)])

def show_circle(cx, cy, r, label="", color="#00FF00", duration=5):
    _spawn_proc(["--circle",
                 "--cx", str(cx), "--cy", str(cy),
                 "--r", str(r),
                 "--label", label,
                 "--color", color,
                 "--dur", str(duration)])

def show_rect_rel(x, y, w, h, label="", color="#00FF00", duration=5):
    sw, sh = _screen_size()
    show_rect(int(x*sw), int(y*sh), int(w*sw), int(h*sh),
              label, color, duration)

def show_circle_rel(cx, cy, r, label="", color="#00FF00", duration=5):
    sw, sh = _screen_size()
    show_circle(int(cx*sw), int(cy*sh), int(r*sw),
                label, color, duration)

def _spawn_proc(args):
    script = os.path.abspath(__file__)
    proc = subprocess.Popen(
        [sys.executable, script] + args,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL
    )
    with _lock:
        _active[proc.pid] = proc

def close_all():
    with _lock:
        for pid, proc in list(_active.items()):
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            except Exception:
                pass
        _active.clear()

def _screen_size():
    """Return virtual screen size (all monitors combined)."""
    try:
        with mss.mss() as sct:
            return sct.monitors[0]["width"], sct.monitors[0]["height"]
    except Exception:
        pass
    try:
        import tkinter as tk
        r = tk.Tk(); r.withdraw()
        w, h = r.winfo_screenwidth(), r.winfo_screenheight()
        r.destroy()
        return w, h
    except Exception:
        return 1920, 1080


# ================================================================
# OVERLAY WINDOW — runs as standalone subprocess
# ================================================================
if __name__ == "__main__":
    import math
    import tkinter as tk

    args = sys.argv[1:]

    def get(key, default=""):
        try:
            i = args.index(f"--{key}")
            return args[i + 1]
        except (ValueError, IndexError):
            return default

    shape = "--rect" in args and "rect" or "circle"
    duration = int(get("dur", 8))
    label = get("label", "")
    color = get("color", "#00FF00")

    if shape == "rect":
        x = int(get("x", 500))
        y = int(get("y", 300))
        w = int(get("w", 200))
        h = int(get("h", 100))
    else:
        cx = int(get("cx", 960))
        cy = int(get("cy", 540))
        r = int(get("r", 60))

    # Build overlay
    root = tk.Tk()
    root.attributes("-alpha", 0, "-topmost", True,
                   "-disabled", True, "-transparentcolor", "#000000")
    root.overrideredirect(True)

    # Use virtual screen (all monitors combined)
    try:
        with mss.mss() as sct:
            sw = sct.monitors[0]["width"]
            sh = sct.monitors[0]["height"]
    except Exception:
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
    root.geometry(f"{sw}x{sh}+0+0")
    root.configure(bg="#000000")

    cv = tk.Canvas(root, width=sw, height=sh,
                   bg="#000000", highlightthickness=0, bd=0)
    cv.pack(fill="both", expand=True)

    # Draw shape
    if shape == "rect":
        cv.create_rectangle(x, y, x+w, y+h,
                            outline=color, width=3, fill="")
    else:
        cv.create_oval(cx-r, cy-r, cx+r, cy+r,
                       outline=color, width=3, fill="")

    # Draw label
    if label:
        if shape == "rect":
            lx = x + w // 2
            ly = y - 22 if y > 40 else y + h + 22
            if ly < 0:
                ly = y + h + 22
        else:
            lx = cx
            ly = cy - r - 22 if cy - r > 40 else cy + r + 22
        chars = len(label)
        pad = 8
        cv.create_rectangle(lx - pad, ly - 13,
                            lx + chars * 8 + pad + 4, ly + 4,
                            fill="#000000", outline="")
        cv.create_text(lx + 4, ly, text=label, fill=color,
                       font=("Consolas", 13, "bold"), anchor="w")

    # Breathing + fade animation
    start = time.time()
    entry_dur = 0.5
    exit_dur = 0.5
    stable_start = entry_dur
    stable_end = entry_dur + duration

    phase = ["entry", "stable", "exit"]
    phase_idx = [0]

    def tick():
        elapsed = time.time() - start
        idx = phase_idx[0]

        if idx == 0:  # entry
            root.attributes("-alpha", min(1.0, elapsed / entry_dur))
            if elapsed >= entry_dur:
                phase_idx[0] = 1
                root.attributes("-alpha", 1.0)

        elif idx == 1:  # stable
            a = 0.65 + 0.35 * abs(math.sin((elapsed - stable_start) * 2.5))
            root.attributes("-alpha", a)
            if elapsed >= stable_end:
                phase_idx[0] = 2

        else:  # exit
            t = elapsed - stable_end
            root.attributes("-alpha", max(0, 1.0 - t / exit_dur))
            if elapsed >= stable_end + exit_dur:
                root.destroy()
                return

        root.after(50, tick)

    tick()
    root.mainloop()
