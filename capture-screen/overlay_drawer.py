# overlay_drawer.py
# Full-screen transparent overlay via tkinter subprocess
# Spawns a separate process for each overlay — reliable and stable
#
# Usage:
#   python overlay_drawer.py --rect --x 500 --y 300 --w 200 --h 100 --label "Item" --dur 8
#   python overlay_drawer.py --circle --cx 960 --cy 540 --r 60 --label "Portal" --dur 8
#
# Python API:
#   from overlay_drawer import show_rect, show_circle, close_all
#   show_rect(x, y, w, h, label="", color="#00FF00", duration=5)
#   show_circle(cx, cy, r, label="", color="#00FF00", duration=5)
#   close_all()

import subprocess
import sys
import os
import time
import threading
import uuid

_lock = threading.Lock()
_active = {}   # uid -> proc


def show_rect(x, y, w, h, label="", color="#00FF00", duration=5):
    _spawn(shape="rect", x=x, y=y, w=w, h=h, cx=0, cy=0, r=0,
           label=label, color=color, duration=duration)

def show_circle(cx, cy, r, label="", color="#00FF00", duration=5):
    _spawn(shape="circle", x=0, y=0, w=0, h=0, cx=cx, cy=cy, r=r,
           label=label, color=color, duration=duration)

def show_rect_rel(x, y, w, h, label="", color="#00FF00", duration=5):
    sw, sh, *_ = _screen_size()
    show_rect(int(x*sw), int(y*sh), int(w*sw), int(h*sh),
              label, color, duration)

def show_circle_rel(cx, cy, r, label="", color="#00FF00", duration=5):
    sw, sh, *_ = _screen_size()
    show_circle(int(cx*sw), int(cy*sh), int(r*sw),
                label, color, duration)

def _spawn(shape, x, y, w, h, cx, cy, r, label, color, duration):
    script = os.path.abspath(__file__)
    uid = uuid.uuid4().hex[:8]
    args = [
        "--uid=" + uid,
        "--shape=" + shape,
        "--x=" + str(x), "--y=" + str(y),
        "--w=" + str(w), "--h=" + str(h),
        "--cx=" + str(cx), "--cy=" + str(cy), "--r=" + str(r),
        "--label=" + str(label),
        "--color=" + str(color),
        "--dur=" + str(duration),
    ]
    creation_flags = 0
    proc = subprocess.Popen(
        [sys.executable, script] + args,
        creationflags=creation_flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    with _lock:
        _active[uid] = proc

def _screen_size():
    try:
        import mss
        with mss.MSS() as sct:
            v = sct.monitors[0]
            return v["width"], v["height"], v["left"], v["top"]
    except Exception:
        return 1920, 1080, 0, 0

def close_all():
    with _lock:
        for uid, proc in list(_active.items()):
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        _active.clear()


# ================================================================
# OVERLAY WINDOW — standalone subprocess
# ================================================================
if __name__ == "__main__":
    import math
    import tkinter as tk
    import mss

    args = sys.argv[1:]

    def get(key, default=""):
        for arg in args:
            if arg.startswith(f"--{key}="):
                return arg.split("=", 1)[1]
        return default

    uid     = get("uid", "overlay")
    shape   = get("shape", "rect")
    x       = int(get("x", 500))
    y       = int(get("y", 300))
    w       = int(get("w", 200))
    h       = int(get("h", 100))
    cx      = int(get("cx", 960))
    cy      = int(get("cy", 540))
    r       = int(get("r", 60))
    label   = get("label", "")
    color   = get("color", "#00FF00")
    duration = max(1, int(get("dur", 8)))

    # Get VIRTUAL SCREEN dimensions (all monitors combined)
    with mss.MSS() as sct:
        vmon = sct.monitors[0]
        sw = vmon["width"]
        sh = vmon["height"]
        vx = vmon["left"]
        vy = vmon["top"]

    # Build overlay window spanning entire virtual screen
    root = tk.Tk()
    root.attributes("-alpha", 0, "-topmost", True,
                   "-disabled", True, "-transparentcolor", "#000000")
    root.overrideredirect(True)
    # Virtual screen origin may NOT be 0,0 — use actual vx,vy
    root.geometry(f"{sw}x{sh}+{vx}+{vy}")
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
