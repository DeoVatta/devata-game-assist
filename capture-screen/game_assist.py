# game_assist.py
# Persistent AI game assistant — Gemini Live style for PC gaming
# Floating bubble overlay, conversational, screen-aware, context-preserving
#
# Usage:
#   python game_assist.py              # Start with overlay + REPL
#   python game_assist.py --once "Q"  # Single question

import sys, os, time, re, json, threading, subprocess, queue
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_KEY    = os.environ.get("OLAGON_API_KEY", "")
GATEWAY    = "https://gateway.olagon.site/anthropic/v1/messages"
MODEL      = "claude-3-5-sonnet"

# ──────────────────────────────────────────────
# ANSI helpers
# ──────────────────────────────────────────────
C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m", "green": "\033[32m",
    "yellow": "\033[33m", "blue": "\033[34m",
    "cyan": "\033[36m", "white": "\033[37m",
    "bgreen": "\033[92m", "byellow": "\033[93m",
    "bcyan": "\033[96m", "bwhite": "\033[97m",
    "mag": "\033[35m",
}

def _p(text):
    sys.stdout.write(text + "\n")
    sys.stdout.flush()

def _div():
    try:
        w = os.get_terminal_size().columns
    except Exception:
        w = 80
    _p(C["dim"] + "─" * w + C["reset"])

# ──────────────────────────────────────────────
# BUBBLE OVERLAY — inline Tk script
# ──────────────────────────────────────────────
_TK_BUBBLE = r'''
import sys, os, time, math, json, threading, struct, zlib

# ── screen bounds ──
try:
    import mss
    with mss.MSS() as sct:
        v = sct.monitors[0]
        SW, SH, VX, VY = v["width"], v["height"], v["left"], v["top"]
except:
    SW, SH, VX, VY = 1920, 1080, 0, 0

WW = 480   # window width
WH = 520   # window height
PX = 30    # padding X
PY = 30    # padding Y
GX = VX + SW - WW - PX
GY = VY + SH - WH - PY

import tkinter as tk
from tkinter import font as tkfont

root = tk.Tk()
root.title("Game Assist")
root.attributes("-alpha", 0.0, "-topmost", True,
               "-disabled", True, "-transparentcolor", "#000000")
root.overrideredirect(True)
root.geometry(f"{WW}x{WH}+{GX}+{GY}")
root.configure(bg="#000000", cursor="none")

F = tkfont.Font(family="Segoe UI", size=13)
FH = F.metrics("linespace") + 2

canvas = tk.Canvas(root, width=WW, height=WH, bg="#000000",
                   highlightthickness=0, bd=0)
canvas.pack(fill="both", expand=True)

BUBBLES = []
MAX_B = 8

def rr(c, x1, y1, x2, y2, r=14, **kw):
    pts = []
    r = min(r, (x2-x1)//2, (y2-y1)//2)
    pts += [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r]
    pts += [x2,y2-r, x2,y2, x2-r,y2, x1+r,y2]
    pts += [x1,y2, x1,y2-r, x1,y1+r, x1+r,y1]
    return c.create_polygon(pts, smooth=True, **kw)

ROLE_COLOR = {
    "user":    ("#10733a", "#ffffff"),
    "ai":      ("#0d3a6e", "#d8eeff"),
    "thinking":("#2a2a2a", "#888888"),
    "hint":    ("#1a1a2a", "#667788"),
}

def add(role, text):
    if not text:
        return
    bg, fg = ROLE_COLOR.get(role, ("#1a1a2a", "#aaaacc"))

    # Text wrap
    mw = WW - 36
    lines, cur = [], ""
    for ch in text:
        test = cur + ch
        if F.measure(test) > mw:
            lines.append(cur); cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)

    pad = 14
    bh = len(lines) * FH + pad * 2
    bw = max(90, min(mw, max(F.measure(l) for l in lines) + pad * 2))

    if role in ("user", "ai", "thinking"):
        bx = WW - 16 if role == "user" else 16
        anchor_x = bx - bw if role == "user" else bx
        anchor = "ne" if role == "user" else "nw"
    else:
        bx = 16; anchor_x = bx; anchor = "nw"

    # Stack
    if BUBBLES:
        ly = canvas.coords(BUBBLES[-1])[1] if canvas.coords(BUBBLES[-1]) else WH
    else:
        ly = WH
    by = ly - bh - 8
    if by < 8:
        while by < 8 and BUBBLES:
            canvas.delete(BUBBLES.pop(0))
            by = 8
            if BUBBLES:
                ly = canvas.coords(BUBBLES[-1])[1]
                by = ly - bh - 8

    x1 = bx - bw if role == "user" else bx
    rect = rr(canvas, x1, by, x1+bw, by+bh, r=16, fill=bg, outline="")
    canvas.lower(rect)

    for i, ln in enumerate(lines):
        tx = x1 + pad if anchor == "nw" else x1 + bw - pad
        ty = by + pad + i * FH
        canvas.create_text(tx, ty, text=ln, fill=fg, font=F, anchor=anchor)

    BUBBLES.append(rect)
    return rect

def clear_all():
    for b in BUBBLES:
        canvas.delete(b)
    BUBBLES.clear()

# Fade in + breathe
alpha_val = [0.0]
def fade_in(a=0.0):
    a = min(0.92, a + 0.1)
    alpha_val[0] = a
    try:
        root.attributes("-alpha", a)
    except: pass
    if a < 0.92:
        root.after(25, lambda: fade_in(a))
    else:
        breathe_start()

breath_phase = [0.0]
def breathe():
    a = 0.82 + 0.08 * math.sin(breath_phase[0])
    breath_phase[0] += 0.04
    try:
        cur = root.attributes("-alpha")
        root.attributes("-alpha", max(0.78, min(0.92, cur * 0.92 + a * 0.08)))
    except: pass
    root.after(60, breathe)

def breathe_start():
    root.after(300, breathe)

# Start
root.after(100, fade_in)
add("ai", "Game Assist ready. Press Ctrl+Shift+G!")
add("hint", "Press Ctrl+Shift+G to ask about your game...")

# ── stdin reader ──
def reader():
    buf = ""
    while True:
        try:
            ch = sys.stdin.read(1)
            if not ch:
                break
            buf += ch
            if ch == "\n":
                try:
                    msg = json.loads(buf.strip())
                    buf = ""
                    t = msg.get("type", "")
                    if t == "bubble":
                        add(msg.get("role", "ai"), str(msg.get("text", ""))[:600])
                    elif t == "thinking":
                        add("thinking", "analyzing...")
                    elif t == "clear":
                        clear_all()
                    elif t == "quit":
                        root.after(50, root.destroy)
                        break
                except Exception:
                    buf = ""
        except Exception:
            break

th = threading.Thread(target=reader, daemon=True)
th.start()
root.mainloop()
'''


# ──────────────────────────────────────────────
# Overlay manager
# ──────────────────────────────────────────────
_overlay = None


def _start_overlay():
    global _overlay
    if _overlay and _overlay.poll() is None:
        return
    tmp = SCRIPT_DIR / f"._bubble_{os.getpid()}.py"
    tmp.write_text(_TK_BUBBLE, encoding="utf-8")
    _overlay = subprocess.Popen(
        [sys.executable, str(tmp)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        text=True, bufsize=1
    )
    def cleanup():
        time.sleep(1)
        try:
            tmp.unlink(missing_ok=True)
        except: pass
    threading.Thread(target=cleanup, daemon=True).start()


def _send(msg: dict):
    global _overlay
    if _overlay is None or _overlay.poll() is not None:
        _start_overlay()
        time.sleep(0.8)
    try:
        _overlay.stdin.write(json.dumps(msg) + "\n")
        _overlay.stdin.flush()
    except Exception:
        _start_overlay()


def bubble(role, text):
    _send({"type": "bubble", "role": role, "text": text})


def thinking():
    _send({"type": "thinking"})


def clear_ov():
    _send({"type": "clear"})


def quit_ov():
    try:
        _send({"type": "quit"})
    except: pass


# ──────────────────────────────────────────────
# Screen capture
# ──────────────────────────────────────────────
def _capture():
    import base64, io, mss
    from PIL import Image

    with mss.MSS() as sct:
        mon = sct.monitors[0]
        img = sct.grab(mon)
        vw = mon["width"]
        vh = mon["height"]
        pil = Image.frombytes("RGB", img.size, img.rgb)

    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    orig = base64.b64encode(buf.getvalue()).decode()

    # Resize for AI
    mw = 1280
    if vw > mw:
        ai = pil.resize((mw, int(vh * mw / vw)), Image.LANCZOS)
    else:
        ai = pil
    buf2 = io.BytesIO()
    ai.save(buf2, format="PNG")
    aib64 = base64.b64encode(buf2.getvalue()).decode()
    return orig, aib64, vw, vh, ai.size[0], ai.size[1]


# ──────────────────────────────────────────────
# Conversation context
# ──────────────────────────────────────────────
class Conversation:
    def __init__(self):
        self.history = []   # list of (role, text)

    SYSTEM = """\
You are an expert game assistant (like Gemini Live).
The user is playing a game right now. Analyze the screen carefully and answer.

RULES:
- Identify the game, screen/mode, and current situation first
- Answer with SPECIFIC, ACTIONABLE advice
- Reference in-game elements by name
- Keep answers conversational but precise
- If item: name it, explain purpose, value, synergies
- If puzzle: analyze elements, give step-by-step solution
- If combat: suggest strategy, abilities, positioning
- If progression: prioritize next steps with reasons

Be conversational. Start with your key insight immediately."""

    def ask(self, question, aib64, iw, ih):
        import httpx
        msgs = [
            {"role": "system", "content": self.SYSTEM},
        ]
        for role, text in self.history[-8:]:
            msgs.append({"role": role, "content": text})

        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": aib64}},
            {"type": "text", "text": f"(Screen: {iw}x{ih} px)\n\nUser: {question}"}
        ]
        msgs.append({"role": "user", "content": content})

        payload = {
            "model": MODEL, "max_tokens": 1024, "stream": False,
            "messages": msgs
        }
        headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        r = httpx.post(GATEWAY, json=payload, headers=headers, timeout=60)
        r.raise_for_status()
        for b in r.json().get("content", []):
            if isinstance(b, dict) and b.get("type") == "text":
                return b["text"].strip()
        return "No response."

    def add(self, role, text):
        self.history.append((role, text))

    def clear(self):
        self.history.clear()


# ──────────────────────────────────────────────
# Quick commands
# ──────────────────────────────────────────────
def cmd_ask(question, conv):
    import httpx
    bubble("user", question)
    thinking()

    t0 = time.time()
    try:
        _, aib64, vw, vh, iw, ih = _capture()
        resp = conv.ask(question, aib64, iw, ih)
        elapsed = time.time() - t0
    except Exception as e:
        resp = f"Error: {e}"
        elapsed = 0

    conv.add("assistant", resp)
    bubble("ai", resp)

    _p(f"\n  {C['cyan']}▸{C['reset']} {C['dim']}[{elapsed:.1f}s]{C['reset']}")
    for ln in resp.split("\n"):
        if ln.strip():
            _p(f"    {C['bwhite']}{ln.strip()}{C['reset']}")


def cmd_what(conv):
    cmd_ask("What's happening? Describe the game, situation, and notable elements.", conv)

def cmd_solve(conv):
    cmd_ask("Is there a puzzle? If yes, analyze and give step-by-step solution.", conv)

def cmd_item(conv):
    cmd_ask("Identify the item I'm looking at. Name it, explain what it does, and rate its value.", conv)

def cmd_next(conv):
    cmd_ask("What should I prioritize next? Be specific about the best strategy.", conv)

def cmd_game(conv):
    bubble("user", "What game is this?")
    thinking()
    try:
        _, aib64, _, _, _, _ = _capture()
        import httpx
        payload = {
            "model": MODEL, "max_tokens": 64, "stream": False,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": aib64}},
                {"type": "text", "text": "In 1 sentence: what game is this and what's happening? Format: GAME | SITUATION"}
            ]}]
        }
        headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        r = httpx.post(GATEWAY, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        for b in r.json().get("content", []):
            if isinstance(b, dict) and b.get("type") == "text":
                bubble("ai", b["text"].strip())
                _p(f"\n  {C['bgreen']}✓{C['reset']} {C['bcyan']}{b['text'].strip()}{C['reset']}")
                return
        bubble("ai", "Could not detect game")
    except Exception as e:
        bubble("ai", f"Error: {e}")
        _p(f"\n  {C['red']}✗{C['reset']} {e}")

def cmd_toggle():
    global _overlay
    if _overlay and _overlay.poll() is None:
        try:
            _overlay.terminate()
        except: pass
        _overlay = None
        _p(f"  {C['byellow']}Overlay hidden{C['reset']}")
    else:
        _start_overlay()
        time.sleep(0.5)
        _p(f"  {C['bgreen']}Overlay visible{C['reset']}")

def cmd_clear(conv):
    conv.clear()
    clear_ov()
    time.sleep(0.3)
    _send({"type": "bubble", "role": "hint", "text": "Context cleared. Ready for new topic!"})
    _p(f"  {C['bgreen']}Context cleared{C['reset']}")


# ──────────────────────────────────────────────
# Banner + help
# ──────────────────────────────────────────────
def _banner():
    _p(f"""
{C['bcyan']}
  ┌──────────────────────────────────────────┐
  │  █████╗  ██████╗ ██████╗ ██████╗ ██╗  ██╗ │
  │ ██╔══██╗██╔════╝██╔════╝ ██╔══██╗╚██╗██╔╝ │
  │ ███████║╚█████╗  ██║  ███╗██████╔╝ ╚███╔╝  │
  │ ██╔══██║ ╚═══██╗ ██║   ██║██╔══██╗ ██╔██╗  │
  │ ██║  ██║██████╔╝╚██████╔╝██║  ██║██╔╝ ██╗  │
  │ ╚═╝  ╚═╝╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  │
  └──────────────────────────────────────────┘{C['reset']}
{C['dim']}   Gemini Live-style assistant for PC gaming{C['reset']}
""")

def _help():
    _p(f"""
{C['bold']}COMMANDS{C['reset']}
  {C['cyan']}ask <question>{C['reset']}     Ask anything about your game
  {C['cyan']}item{C['reset']}                Identify item you're looking at
  {C['cyan']}solve{C['reset']}               Solve current puzzle
  {C['cyan']}what{C['reset']}                What is happening right now?
  {C['cyan']}next{C['reset']}                What should I do next?
  {C['cyan']}game{C['reset']}                Detect what game is playing
  {C['cyan']}toggle{C['reset']}              Show/hide bubble overlay
  {C['cyan']}clear{C['reset']}              Clear conversation context
  {C['cyan']}quit{C['reset']}               Exit

  {C['dim']}Hotkey: {C['mag']}Ctrl+Shift+G{C['dim']} — activate from anywhere while gaming{C['reset']}

{C['bold']}EXAMPLES{C['reset']}
  {C['bgreen']}  > item{C['reset']}
  {C['bgreen']}  > solve{C['reset']}
  {C['bgreen']}  > ask boss ini lemah element apa?{C['reset']}
  {C['bgreen']}  > what{C['reset']}
  {C['bgreen']}  > next{C['reset']}
""")


# ──────────────────────────────────────────────
# Hotkey — pynput global listener
# ──────────────────────────────────────────────
def _hotkey_loop(conv_ref, question_fn):
    try:
        from pynput import keyboard

        def on_activate():
            # Spawn question popup
            def popup():
                try:
                    import tkinter as tk
                    r = tk.Tk()
                    r.withdraw()
                    sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
                    r.deiconify()
                    r.title("Game Assist")
                    r.attributes("-topmost", True)
                    r.geometry(f"720x130+{(sw-720)//2}+{(sh-130)//2}")
                    r.configure(bg="#1a1a2e", bd=0)

                    res = [""]
                    def ok():
                        res[0] = e.get().strip()
                        r.quit()
                    def onkey(ev):
                        if ev.keysym == "Return": ok()
                        elif ev.keysym == "Escape": r.quit()
                    def onclose():
                        res[0] = ""
                        r.quit()

                    tk.Label(r, text="Game Assist — Ask your question:",
                            font=("Segoe UI",11), bg="#1a1a2e", fg="#d8eeff").pack(pady=(10,4))
                    e = tk.Entry(r, font=("Segoe UI",15), width=65,
                                bg="#0d3a6e", fg="white", insertbackground="white",
                                relief="flat", bd=8)
                    e.pack(padx=16, fill="x")
                    e.focus()
                    e.bind("<Key>", onkey)
                    tk.Button(r, text="Ask  (Enter)", command=ok,
                             font=("Segoe UI",10), bg="#10733a", fg="white",
                             relief="flat", padx=12, pady=4).pack(pady=(6,10))
                    r.protocol("WM_DELETE_WINDOW", onclose)
                    r.after(120_000, r.quit)   # 2min timeout
                    r.mainloop()
                    q = res[0]
                except Exception:
                    q = ""
                if q:
                    conv = conv_ref()
                    bubble("user", q)
                    thinking()
                    try:
                        _, aib64, vw, vh, iw, ih = _capture()
                        resp = conv.ask(q, aib64, iw, ih)
                        conv.add("assistant", resp)
                        bubble("ai", resp)
                    except Exception as ex:
                        bubble("ai", f"Error: {ex}")

            threading.Thread(target=popup, daemon=True).start()

        hk = keyboard.HotKey(keyboard.HotKey.parse("ctrl+shift+g"), on_activate)
        lnr = keyboard.Listener(on_press=hk.press, suppress=False)
        lnr.daemon = True
        lnr.start()
        _p(f"  {C['bgreen']}+{C['reset']} {C['cyan']}Ctrl+Shift+G{C['reset']} — global hotkey active")

    except Exception:
        _p(f"  {C['dim']}pynput not available — hotkey disabled{C['reset']}")


# ──────────────────────────────────────────────
# REPL
# ──────────────────────────────────────────────
def repl():
    conv = Conversation()
    conv_ref = lambda: conv

    _banner()
    _start_overlay()
    time.sleep(0.5)

    # Quick game detection on start
    try:
        _, aib64, _, _, _, _ = _capture()
        import httpx
        headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        r = httpx.post(GATEWAY, json={
            "model": MODEL, "max_tokens": 64, "stream": False,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": aib64}},
                {"type": "text", "text": "In 1 short sentence: what game is this? Reply just the game name."}
            ]}]
        }, headers=headers, timeout=20)
        for b in r.json().get("content", []):
            if isinstance(b, dict) and b.get("type") == "text":
                game_info = b["text"].strip()
                bubble("ai", f"Game: {game_info}")
                _p(f"  {C['cyan']}▸{C['reset']} {C['dim']}{game_info}{C['reset']}")
                break
    except Exception:
        bubble("ai", "Game Assist ready! Ask me anything about your game.")
        _p(f"  {C['dim']}Game detection skipped (API may not be ready){C['reset']}")

    _send({"type": "bubble", "role": "hint",
           "text": "Press Ctrl+Shift+G or type a question!"})

    _p(f"\n  {C['cyan']}Hotkey:{C['reset']} {C['mag']}Ctrl+Shift+G{C['reset']} "
           f"(global — works while gaming)")
    _p(f"  {C['cyan']}Overlay:{C['reset']} always-on in bottom-right corner")
    _p(f"  {C['dim']}Type 'help' or just ask a question{C['reset']}\n")
    _div()

    _hotkey_loop(conv_ref, None)

    while True:
        try:
            prompt = input(f"\n{C['bgreen']}>{C['reset']} ").strip()
        except (EOFError, KeyboardInterrupt):
            _p("\n\n  [bye]\n")
            break

        if not prompt:
            continue
        parts = prompt.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("quit", "exit", "q"):
            break
        if cmd in ("clear", "cls"):
            os.system("cls" if os.name == "nt" else "clear")
            _banner()
            continue
        if cmd == "help":
            _help(); continue
        if cmd == "toggle":
            cmd_toggle(); continue
        if cmd == "clear":
            cmd_clear(conv); continue
        if cmd == "game":
            cmd_game(conv); continue
        if cmd == "what":
            cmd_what(conv); continue
        if cmd == "solve":
            cmd_solve(conv); continue
        if cmd == "item":
            cmd_item(conv); continue
        if cmd == "next":
            cmd_next(conv); continue
        if cmd == "ask":
            if arg:
                cmd_ask(arg, conv)
            else:
                _p(f"  {C['byellow']}Usage: ask <question>{C['reset']}")
            continue

        # Default: ask
        cmd_ask(prompt, conv)

    quit_ov()


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        _start_overlay()
        time.sleep(0.5)
        question = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "What's on screen?"
        conv = Conversation()
        cmd_ask(question, conv)
        time.sleep(3)
        quit_ov()
    else:
        repl()
