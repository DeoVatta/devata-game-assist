# ai_chat.py
# Unified CLI — all capture-screen features in one interface
#
# Usage:
#   python ai_chat.py                    # Interactive REPL (ask AI about screen)
#   python ai_chat.py "question"        # Single question from CLI
#   python ai_chat.py ask "question"    # Ask AI
#   python ai_chat.py capture            # Screenshot
#   python ai_chat.py vision             # AI vision analysis
#   python ai_chat.py retro [min]       # Retrospective analysis
#   python ai_chat.py loop               # Start capture loop (10s interval)
#   python ai_chat.py log start|status|stop  # Input logger
#   python ai_chat.py sys start|status|report # System monitor
#   python ai_chat.py game               # Game monitor
#   python ai_chat.py overlay x y w h [label]  # Draw overlay
#   python ai_chat.py screenshots        # Open screenshots folder

import sys
import os
# Force UTF-8 output for Unicode art
if sys.platform == "win32":
    import subprocess
    subprocess.run(["chcp", "65001"], shell=True, capture_output=True)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import sys
import os
import time
import re
import argparse
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")


# ============================================================
# STYLE
# ============================================================

C_RESET  = "\033[0m"
C_BOLD   = "\033[1m"
C_DIM    = "\033[2m"
C_BLACK  = "\033[30m"
C_RED    = "\033[31m"
C_GREEN  = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE   = "\033[34m"
C_CYAN   = "\033[36m"
C_WHITE  = "\033[37m"
C_BRIGHT_BLACK  = "\033[90m"
C_BRIGHT_RED    = "\033[91m"
C_BRIGHT_GREEN  = "\033[92m"
C_BRIGHT_YELLOW = "\033[93m"
C_BRIGHT_BLUE   = "\033[94m"
C_BRIGHT_CYAN   = "\033[96m"
C_BRIGHT_WHITE  = "\033[97m"
C_MAGENTA = "\033[35m"

SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_sidx = 0
_spin_lock = threading.Lock()


def _spin():
    global _sidx
    with _spin_lock:
        _sidx = (_sidx + 1) % len(SPINNER)
        return SPINNER[_sidx]


def _clear_line():
    sys.stdout.write("\033[2K\r")
    sys.stdout.flush()


def _hide_cursor():
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def _show_cursor():
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def _print(text):
    print(text)


def _ok(text):
    print(f"  {C_BRIGHT_GREEN}✓{C_RESET} {text}")


def _err(text):
    print(f"  {C_BRIGHT_RED}✗{C_RESET} {text}")


def _info(text):
    print(f"  {C_BRIGHT_BLUE}▸{C_RESET} {text}")


def _warn(text):
    print(f"  {C_BRIGHT_YELLOW}!{C_RESET} {text}")


def _dim(text):
    print(f"  {C_DIM}{text}{C_RESET}")


def _div():
    cols = 80
    try:
        cols = os.get_terminal_size().columns
    except Exception:
        pass
    print(f"{C_DIM}{'─' * cols}{C_RESET}")


class Spinner:
    def __init__(self, msg=""):
        self.msg = msg
        self.running = False
        self.t = None

    def _loop(self):
        global _spin
        while self.running:
            sys.stdout.write(f"\r  {C_DIM}{_spin()} {C_RESET}{self.msg}... ")
            sys.stdout.flush()
            time.sleep(0.08)
        _clear_line()

    def start(self, msg=""):
        if msg:
            self.msg = msg
        self.running = True
        self.t = threading.Thread(target=self._loop, daemon=True)
        self.t.start()

    def stop(self, final="", ok=True):
        self.running = False
        if self.t:
            self.t.join(timeout=0.3)
        _clear_line()
        if final:
            icon = f"{C_BRIGHT_GREEN}✓{C_RESET}" if ok else f"{C_BRIGHT_RED}✗{C_RESET}"
            end = f" {C_DIM}(took {self._elapsed:.1f}s){C_RESET}" if ok else ""
            print(f"  {icon} {final}{end}")

    @property
    def _elapsed(self):
        return 0.0


# ============================================================
# BANNER
# ============================================================

def _banner():
    # Box drawing chars via \x escapes to avoid encoding issues
    horiz = "─"
    vert  = "│"
    tl = "┌"; tr = "┐"
    bl = "└"; br = "┘"
    b = f"""
\x1b[96m  {tl}{horiz*49}{tr}
  {vert}\x1b[95m  █████╗\x1b[96m  ██████╗ ██████╗ ██████╗ ██╗  ██╗ \x1b[96m  {vert}
  {vert}\x1b[95m ██╔══██╗\x1b[96m██╔════╝██╔════╝ ██╔══██╗╚██╗██╔╝\x1b[96m  {vert}
  {vert}\x1b[95m ███████║\x1b[96m╚█████╗  ██║  ███╗██████╔╝ ╚███╔╝ \x1b[96m {vert}
  {vert}\x1b[95m ██╔══██║\x1b[96m ╚═══██╗ ██║   ██║██╔══██╗ ██╔██╗ \x1b[96m {vert}
  {vert}\x1b[95m ██║  ██║\x1b[96m██████╔╝╚██████╔╝██║  ██║██╔╝ ██╗\x1b[96m  {vert}
  {vert}\x1b[95m ╚═╝  ╚═╝\x1b[96m╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝\x1b[96m  {vert}
  {bl}{horiz*49}{br}\x1b[0m
\x1b[2m   Unified CLI — all capture-screen features in one interface\x1b[0m
"""
    print(b)


def _help():
    h = f"""
{C_BOLD}ASK — AI Vision + Overlay{C_RESET}
  {C_CYAN}ask "question"{C_RESET}        Ask AI about anything on screen
  {C_CYAN}ask "where is X?"{C_RESET}    Find and highlight item on screen
  {C_CYAN}where X{C_RESET}               Shortcut for: ask 'where is X?'

{C_BOLD}SCREEN CAPTURE{C_RESET}
  {C_CYAN}capture{C_RESET}                Take a screenshot now
  {C_CYAN}screenshots{C_RESET}            Open screenshots folder

{C_BOLD}AI ANALYSIS{C_RESET}
  {C_CYAN}vision{C_RESET}                  Single frame AI analysis
  {C_CYAN}retro [min]{C_RESET}            Retrospective analysis (default 5 min)
  {C_CYAN}retro --input{C_RESET}          + include input log
  {C_CYAN}retro --system{C_RESET}         + include system stats

{C_BOLD}BACKGROUND SERVICES{C_RESET}
  {C_CYAN}loop{C_RESET}                    Start screenshot loop (10s interval)
  {C_CYAN}log start{C_RESET}              Start input logger
  {C_CYAN}log status{C_RESET}             Check input log buffer
  {C_CYAN}log stop{C_RESET}               Stop input logger
  {C_CYAN}sys start{C_RESET}              Start system monitor
  {C_CYAN}sys status{C_RESET}             Check system stats
  {C_CYAN}sys report [min]{C_RESET}        Performance report
  {C_CYAN}sys stop{C_RESET}               Stop system monitor

{C_BOLD}GAME{C_RESET}
  {C_CYAN}game{C_RESET}                    Fast game detection + screenshot

{C_BOLD}OVERLAY{C_RESET}
  {C_CYAN}overlay X Y W H [label]{C_RESET}  Draw rect overlay on screen
  {C_CYAN}circle CX CY R [label]{C_RESET}    Draw circle overlay on screen

{C_BOLD}SYSTEM{C_RESET}
  {C_CYAN}help{C_RESET}                    Show this help
  {C_CYAN}clear{C_RESET}                   Clear screen
  {C_CYAN}quit{C_RESET}                    Exit

{C_BOLD}EXAMPLES{C_RESET}
  {C_GREEN}> where Balatro?{C_RESET}
  {C_GREEN}> ask mana folder Minami Lane?{C_RESET}
  {C_GREEN}> retro 5 --input --system{C_RESET}
  {C_GREEN}> loop{C_RESET}
  {C_GREEN}> overlay 2055 900 270 300 Balatro{C_RESET}
"""
    print(h)


# ============================================================
# SHARED: Capture
# ============================================================

def _capture_screen():
    import base64
    import io
    import mss
    from PIL import Image

    with mss.MSS() as sct:
        monitor = sct.monitors[0]
        img = sct.grab(monitor)
        vw = sct.monitors[0]["width"]
        vh = sct.monitors[0]["height"]

        pil_img = Image.frombytes("RGB", img.size, img.rgb)
        buf_orig = io.BytesIO()
        pil_img.save(buf_orig, format="PNG")
        orig_b64 = base64.b64encode(buf_orig.getvalue()).decode("utf-8")

        max_w = 1920
        if vw > max_w:
            ratio = max_w / vw
            new_h = int(vh * ratio)
            ai_img = pil_img.resize((max_w, new_h), Image.LANCZOS)
        else:
            ai_img = pil_img
        buf_ai = io.BytesIO()
        ai_img.save(buf_ai, format="PNG")
        ai_b64 = base64.b64encode(buf_ai.getvalue()).decode("utf-8")
        return orig_b64, ai_b64, vw, vh, ai_img.size[0], ai_img.size[1]


# ============================================================
# SHARED: AI
# ============================================================

API_KEY = os.environ.get("OLAGON_API_KEY", "")
GATEWAY_URL = "https://gateway.olagon.site/anthropic/v1/messages"
MODEL = "claude-3-5-sonnet"


def _ask_ai(question, screen_b64, sw, sh):
    if not API_KEY:
        return "ERROR: OLAGON_API_KEY not set. Check capture-screen/.env"

    import httpx
    payload = {
        "model": MODEL,
        "max_tokens": 1024,
        "stream": False,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screen_b64}},
                {"type": "text",
                 "text": f"""You are a game assistant. The user asks: "{question}"

SCREENSHOT = FULL VIRTUAL SCREEN (all monitors combined), {sw}x{sh} pixels.
Coordinate origin is TOP-LEFT (0,0). Left monitor = small x, right monitor = large x.

VISUAL CLUES - Balatro:
- RED/DARK-RED background with JOKER/POKER CARD silhouette icon
- Game name label below the icon
- Arranged in a GRID on a launcher/Steam-like screen
- Each tile = icon (top) + game name (bottom)

VISUAL CLUES - Folders:
- Yellow/blue folder icons in File Explorer

IMPORTANT RULES:
1. MARK THE EXACT ELEMENT, not a nearby area
2. For game tiles: mark the SPECIFIC tile (icon + text)
3. Width/Height with 10-30px padding
4. If on RIGHT monitor: x will be 1920 or higher

RESPOND ONLY:
```
SHAPE: rect|circle
X: <pixel_x>
Y: <pixel_y>
WIDTH: <pixel_width>
HEIGHT: <pixel_height>
LABEL: <short_label>
COLOR: green|yellow|red|blue
REASONING: <1 sentence>
```

If not visible:
```
SHAPE: none
LABEL: tidak terlihat
COLOR: red
REASONING: item not visible
```"""}
            ]
        }]
    }
    headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    r = httpx.post(GATEWAY_URL, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    content = r.json().get("content", [])
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                return b["text"].strip()
    return str(r.json())


def _parse_response(text):
    commands = []
    blocks = re.split(r'```|SHAPE:', text)
    for block in blocks:
        block = block.strip()
        if not block or block.startswith('json') or block.startswith('yaml'):
            continue
        if block.startswith('none'):
            commands.append({"shape": "none", "label": "tidak terlihat", "color": "#FF4444"})
            continue
        shape = re.search(r'\b(rect|circle)\b', block, re.I)
        if not shape:
            continue
        st = shape.group(1).lower()
        cmd = {"shape": st}
        if st == "rect":
            x = re.search(r'X:\s*(\d+)', block)
            y = re.search(r'Y:\s*(\d+)', block)
            w = re.search(r'WIDTH:\s*(\d+)', block)
            h = re.search(r'HEIGHT:\s*(\d+)', block)
            if x and y:
                cmd["x"] = int(x.group(1)); cmd["y"] = int(y.group(1))
                cmd["w"] = int(w.group(1)) if w else 60
                cmd["h"] = int(h.group(1)) if h else 40
        else:
            cx = re.search(r'CX:\s*(\d+)', block)
            cy = re.search(r'CY:\s*(\d+)', block)
            rad = re.search(r'RADIUS:\s*(\d+)', block)
            if cx and cy:
                cmd["cx"] = int(cx.group(1)); cmd["cy"] = int(cy.group(1))
                cmd["r"] = int(rad.group(1)) if rad else 30
        lbl = re.search(r'LABEL:\s*(.+)', block)
        cmd["label"] = lbl.group(1).strip()[:40] if lbl else ""
        col = re.search(r'COLOR:\s*(\w+)', block)
        if col:
            m = {"green": "#00FF00", "yellow": "#FFFF00", "red": "#FF4444", "blue": "#4488FF"}
            cmd["color"] = m.get(col.group(1).lower(), "#00FF00")
        else:
            cmd["color"] = "#00FF00"
        reason = re.search(r'REASONING:\s*(.+)', block)
        if reason:
            cmd["reasoning"] = reason.group(1).strip()
        commands.append(cmd)
    return commands


# ============================================================
# OVERLAY
# ============================================================

OVERLAY_AVAILABLE = False


def _init_overlay():
    global OVERLAY_AVAILABLE
    try:
        from overlay_drawer import show_rect, show_circle
        OVERLAY_AVAILABLE = True
        return show_rect, show_circle
    except Exception:
        return None, None


show_rect, show_circle = _init_overlay()


def _spawn_overlay(commands, duration=12):
    if not OVERLAY_AVAILABLE or show_rect is None:
        return
    for cmd in commands:
        if cmd.get("shape") == "none":
            continue
        color = str(cmd.get("color", "#00FF00"))
        label = cmd.get("label", "")
        dur = int(cmd.get("duration", duration))
        try:
            if cmd["shape"] == "rect":
                show_rect(cmd["x"], cmd["y"], cmd["w"], cmd["h"], label, color, dur)
            elif cmd["shape"] == "circle":
                show_circle(cmd["cx"], cmd["cy"], cmd["r"], label, color, dur)
        except Exception:
            pass


def _save_annotated(orig_b64, commands, vw, vh):
    import base64
    import io
    from PIL import Image, ImageDraw, ImageFont

    img_bytes = base64.b64decode(orig_b64)
    img = Image.open(io.BytesIO(img_bytes))
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font = ImageFont.load_default()

    for cmd in commands:
        if cmd.get("shape") == "none":
            continue
        c = cmd.get("color", "#00FF00").lstrip('#')
        r_c, g_c, b_c = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        line = (r_c, g_c, b_c)
        fill = (r_c, g_c, b_c, 80)
        if cmd["shape"] == "rect":
            x, y, w, h = cmd["x"], cmd["y"], cmd["w"], cmd["h"]
            draw.rectangle([x, y, x+w, y+h], fill=fill, outline=line, width=3)
            if cmd.get("label"):
                lx = x + w // 2 - len(cmd["label"]) * 5
                ly = y - 24 if y > 30 else y + h + 4
                draw.rectangle([lx-4, ly-4, lx+len(cmd["label"])*10+4, ly+16], fill=(0,0,0,200))
                draw.text((lx, ly), cmd["label"], fill=line, font=font)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = SCRIPT_DIR / "screenshots" / f"annotated_{ts}.png"
    out.parent.mkdir(exist_ok=True)
    img.save(out, "PNG")
    return out


# ============================================================
# COMMAND: ask
# ============================================================

def cmd_ask(question: str):
    print(f"\n  {C_BRIGHT_YELLOW}?{C_RESET} {C_BOLD}{question}{C_RESET}")
    _div()

    sp = Spinner("Capturing screen")
    t0 = time.time()
    sp.start()
    try:
        orig_b64, ai_b64, vw, vh, iw, ih = _capture_screen()
        sp.stop(f"Captured {vw}x{vh} -> resized to {iw}x{ih}")
    except Exception as e:
        sp.stop(f"Capture failed: {e}", ok=False)
        return

    sp.start("Asking AI")
    try:
        response = _ask_ai(question, ai_b64, iw, ih)
        elapsed = time.time() - t0
        sp.stop(f"AI responded")
    except Exception as e:
        sp.stop(f"AI error: {e}", ok=False)
        return

    if response.startswith("ERROR:"):
        print(f"\n  {C_BRIGHT_RED}!{C_RESET} {response}")
        return

    # Parse and print response
    commands = _parse_response(response)
    shape_data = None
    for line in response.strip().split('\n'):
        line = line.strip().strip('`')
        if not line:
            continue
        if line.startswith('SHAPE:'):
            shape_data = {}
            print(f"  {C_CYAN}▸{C_RESET} {C_BRIGHT_CYAN}{line}{C_RESET}")
        elif shape_data is not None:
            key = line.split(':', 1)[0].strip().upper()
            val = line.split(':', 1)[1].strip()
            col = C_BRIGHT_WHITE
            if key == 'LABEL':
                col = C_BRIGHT_GREEN
                shape_data['label'] = val
            elif key == 'COLOR':
                cm = {"green": C_BRIGHT_GREEN, "yellow": C_BRIGHT_YELLOW, "red": C_BRIGHT_RED, "blue": C_BRIGHT_BLUE}
                col = cm.get(val.lower(), C_WHITE)
                shape_data['color'] = val
            elif key == 'X':
                shape_data['x'] = val
            elif key == 'Y':
                shape_data['y'] = val
            elif key == 'WIDTH':
                shape_data['w'] = val
            elif key == 'HEIGHT':
                shape_data['h'] = val
            elif key == 'REASONING':
                col = C_DIM
                shape_data['reasoning'] = val
                print(f"  {C_CYAN}▸{C_RESET} {col}{line}{C_RESET}")
                continue
            print(f"  {C_CYAN}▸{C_RESET} {C_BRIGHT_WHITE}{key}:{C_RESET} {col}{val}{C_RESET}")

    _div()

    if not commands:
        _warn("Could not parse AI response")
        return

    # Scale coords
    if iw != vw or ih != vh:
        sx = vw / iw
        sy = vh / ih
        for cmd in commands:
            if cmd.get("shape") == "rect":
                cmd["x"] = int(cmd["x"] * sx)
                cmd["y"] = int(cmd["y"] * sy)
                cmd["w"] = int(cmd["w"] * sx)
                cmd["h"] = int(cmd["h"] * sy)
            elif cmd.get("shape") == "circle":
                cmd["cx"] = int(cmd["cx"] * sx)
                cmd["cy"] = int(cmd["cy"] * sy)
                cmd["r"] = int(cmd["r"] * sx)

    _spawn_overlay(commands)
    path = _save_annotated(orig_b64, commands, vw, vh)

    for cmd in commands:
        if cmd.get("shape") == "none":
            print(f"\n  {C_BRIGHT_RED}○{C_RESET} {C_BRIGHT_RED}tidak terlihat{C_RESET} {C_DIM}— item tidak ada di layar{C_RESET}")
            break
        if cmd.get("shape") == "rect":
            print(f"\n  {C_BRIGHT_GREEN}●{C_RESET} {C_BRIGHT_GREEN}Overlay drawn{C_RESET}"
                  f" {C_DIM}@ ({cmd['x']},{cmd['y']}) {cmd['w']}x{cmd['h']}{C_RESET}"
                  f" {C_DIM}· {path.name}{C_RESET}")
            break
        if cmd.get("shape") == "circle":
            print(f"\n  {C_BRIGHT_GREEN}●{C_RESET} {C_BRIGHT_GREEN}Overlay drawn{C_RESET}"
                  f" {C_DIM}@ ({cmd['cx']},{cmd['cy']}) r={cmd['r']}{C_RESET}"
                  f" {C_DIM}· {path.name}{C_RESET}")
            break


# ============================================================
# COMMAND: capture
# ============================================================

def cmd_capture():
    import base64, io, mss
    from PIL import Image

    _info("Taking screenshot...")
    try:
        with mss.MSS() as sct:
            monitor = sct.monitors[0]
            img = sct.grab(monitor)
            vw = sct.monitors[0]["width"]
            vh = sct.monitors[0]["height"]
            pil_img = Image.frombytes("RGB", img.size, img.rgb)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = SCRIPT_DIR / "screenshots" / f"screen_{ts}.png"
        out.parent.mkdir(exist_ok=True)
        pil_img.save(out, "PNG")
        _ok(f"Saved: {out.name} ({vw}x{vh})")
    except Exception as e:
        _err(f"Failed: {e}")


# ============================================================
# COMMAND: screenshots
# ============================================================

def cmd_screenshots():
    try:
        path = (SCRIPT_DIR / "screenshots").resolve()
        os.startfile(path)
        _ok(f"Opened: {path}")
    except Exception as e:
        _err(f"Failed: {e}")


# ============================================================
# COMMAND: vision
# ============================================================

def cmd_vision():
    import base64, io, httpx, mss
    from PIL import Image

    if not API_KEY:
        _err("OLAGON_API_KEY not set. Check .env"); return

    sp = Spinner("Capturing")
    sp.start()
    try:
        with mss.MSS() as sct:
            monitor = sct.monitors[0]
            img = sct.grab(monitor)
            vw = sct.monitors[0]["width"]
            vh = sct.monitors[0]["height"]
            pil_img = Image.frombytes("RGB", img.size, img.rgb)
            max_w = 960
            if vw > max_w:
                ratio = max_w / vw
                pil_img = pil_img.resize((max_w, int(vh * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
        sp.stop("Captured")
    except Exception as e:
        sp.stop(f"Failed: {e}", ok=False); return

    prompt = "Describe what you see on screen in detail. Include any games, apps, text, UI elements, and notable content."

    sp = Spinner("Analyzing")
    sp.start()
    t0 = time.time()
    try:
        payload = {
            "model": MODEL, "max_tokens": 1024, "stream": False,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": prompt}
            ]}]
        }
        headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        r = httpx.post(GATEWAY_URL, json=payload, headers=headers, timeout=60)
        r.raise_for_status()
        content = r.json().get("content", [])
        result = ""
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                result = b["text"].strip()
        sp.stop(f"Done ({time.time()-t0:.1f}s)")
    except Exception as e:
        sp.stop(f"Error: {e}", ok=False); return

    _div()
    print(result)
    _div()


# ============================================================
# COMMAND: retro
# ============================================================

def cmd_retro(minutes=5, include_input=False, include_system=False):
    import json

    if not API_KEY:
        _err("OLAGON_API_KEY not set. Check .env"); return

    log_dir = SCRIPT_DIR
    input_log = log_dir / "input_log.json"
    system_log = log_dir / "system_log.json"

    # Load context
    context_parts = []
    if include_input and input_log.exists():
        try:
            data = json.loads(input_log.read_text("utf-8"))
            events = data.get("events", [])
            cutoff = datetime.now().timestamp() - minutes * 60
            recent = [e for e in events if e.get("ts", 0) > cutoff]
            keys = [e for e in recent if e.get("type") == "key"]
            clicks = [e for e in recent if e.get("type") == "click"]
            context_parts.append(f"INPUT LOG ({len(recent)} events in last {minutes} min): {len(keys)} keys, {len(clicks)} clicks")
        except Exception:
            context_parts.append("Input log: could not read")

    if include_system and system_log.exists():
        try:
            data = json.loads(system_log.read_text("utf-8"))
            samples = data.get("samples", [])
            cutoff = datetime.now().timestamp() - minutes * 60
            recent = [s for s in samples if s.get("ts", 0) > cutoff]
            if recent:
                avg_cpu = sum(s.get("cpu", 0) for s in recent) / len(recent)
                avg_ram = sum(s.get("ram", 0) for s in recent) / len(recent)
                context_parts.append(f"SYSTEM ({len(recent)} samples): avg CPU={avg_cpu:.1f}%, avg RAM={avg_ram:.1f}%")
        except Exception:
            context_parts.append("System log: could not read")

    # Load screenshots
    ss_dir = log_dir / "screenshots"
    screenshots = sorted(ss_dir.glob("screen_*.png")) if ss_dir.exists() else []
    cutoff = datetime.now().timestamp() - minutes * 60
    recent_screens = [s for s in screenshots if s.stat().st_mtime > cutoff]
    context_parts.append(f"SCREENSHOTS: {len(recent_screens)} captures in last {minutes} min")

    if not recent_screens:
        _warn(f"No screenshots in last {minutes} min. Run 'loop' first to capture.")
        return

    # Use up to 4 most recent
    use_screens = recent_screens[-4:]
    import base64, io, httpx
    from PIL import Image

    sp = Spinner("Loading screenshots")
    sp.start()
    images_content = []
    try:
        for i, sc in enumerate(use_screens):
            img = Image.open(sc)
            img.thumbnail((640, 400), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            images_content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}})
            context_parts.append(f"  Frame {i+1}: {sc.name}")
        sp.stop("Loaded")
    except Exception as e:
        sp.stop(f"Failed: {e}", ok=False); return

    context_str = "\n".join(context_parts)

    sp = Spinner("Analyzing")
    sp.start()
    t0 = time.time()
    try:
        prompt = f"""You are an AI game analyst. Review the screenshots and context below.

{context_str}

Provide a detailed analysis including:
1. What game/activity was happening
2. Notable inputs or gameplay decisions
3. Any mistakes or improvement opportunities
4. Correlation with system performance (if available)

Be specific and actionable."""
        payload = {
            "model": MODEL, "max_tokens": 1024, "stream": False,
            "messages": [{"role": "user", "content": images_content + [{"type": "text", "text": prompt}]}]
        }
        headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        r = httpx.post(GATEWAY_URL, json=payload, headers=headers, timeout=120)
        r.raise_for_status()
        content = r.json().get("content", [])
        result = ""
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                result = b["text"].strip()
        sp.stop(f"Done ({time.time()-t0:.1f}s)")
    except Exception as e:
        sp.stop(f"Error: {e}", ok=False); return

    _div()
    print(result)
    _div()


# ============================================================
# COMMAND: loop
# ============================================================

_loop_running = False
_loop_thread = None


def _capture_loop_worker():
    global _loop_running
    import base64, io, mss
    from PIL import Image
    ss_dir = SCRIPT_DIR / "screenshots"
    ss_dir.mkdir(exist_ok=True)
    count = 0
    while _loop_running:
        try:
            with mss.MSS() as sct:
                monitor = sct.monitors[0]
                img = sct.grab(monitor)
                vw = sct.monitors[0]["width"]
                vh = sct.monitors[0]["height"]
                pil_img = Image.frombytes("RGB", img.size, img.rgb)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = ss_dir / f"screen_{ts}.png"
            pil_img.save(out, "PNG")
            count += 1
            if count % 6 == 0:
                sys.stdout.write(f"\r  {C_DIM}loop: {count} screenshots saved{C_RESET}")
                sys.stdout.flush()
        except Exception:
            pass
        for _ in range(10):
            if not _loop_running:
                break
            time.sleep(1)
    _clear_line()


def cmd_loop(action=""):
    global _loop_running, _loop_thread

    if action == "stop":
        if not _loop_running:
            _warn("Loop not running"); return
        _loop_running = False
        if _loop_thread:
            _loop_thread.join(timeout=2)
        _ok("Loop stopped"); return

    if _loop_running:
        _warn("Loop already running"); return

    _loop_running = True
    _loop_thread = threading.Thread(target=_capture_loop_worker, daemon=True)
    _loop_thread.start()
    _ok("Loop started — capturing every 10s. Press Ctrl+C to stop.")


# ============================================================
# COMMAND: log
# ============================================================

_log_proc = None


def cmd_log(action=""):
    global _log_proc
    script = SCRIPT_DIR / "input_logger.py"
    if not script.exists():
        _err("input_logger.py not found"); return

    if action == "start":
        if _log_proc is not None:
            _warn("Logger already running"); return
        _log_proc = subprocess.Popen(
            [sys.executable, str(script), "--start"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        _ok("Input logger started")

    elif action == "stop":
        if _log_proc is None:
            _warn("Logger not running"); return
        _log_proc.terminate()
        _log_proc = None
        _ok("Input logger stopped")

    elif action == "status":
        log_file = SCRIPT_DIR / "input_log.json"
        if not log_file.exists():
            _warn("No input log found"); return
        try:
            import json
            data = json.loads(log_file.read_text("utf-8"))
            events = data.get("events", [])
            now = datetime.now().timestamp()
            recent = [e for e in events if now - e.get("ts", 0) < 300]
            keys = [e for e in recent if e.get("type") == "key"]
            clicks = [e for e in recent if e.get("type") == "click"]
            print(f"\n  {C_BRIGHT_GREEN}Input Log Status{C_RESET}")
            print(f"  Total events: {len(events)}")
            print(f"  Last 5 min: {len(recent)} ({len(keys)} keys, {len(clicks)} clicks)")
            if events:
                last = events[-1]
                ts = datetime.fromtimestamp(last.get("ts", 0)).strftime("%H:%M:%S")
                print(f"  Last event: {last.get('type')} at {ts}")
        except Exception as e:
            _err(f"Failed: {e}")
    else:
        _warn("Usage: log start|status|stop")


# ============================================================
# COMMAND: sys
# ============================================================

_sys_proc = None


def cmd_sys(action=""):
    global _sys_proc
    script = SCRIPT_DIR / "system_monitor.py"
    if not script.exists():
        _err("system_monitor.py not found"); return

    if action == "start":
        if _sys_proc is not None:
            _warn("Monitor already running"); return
        _sys_proc = subprocess.Popen(
            [sys.executable, str(script), "--start"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        _ok("System monitor started")

    elif action == "stop":
        if _sys_proc is None:
            _warn("Monitor not running"); return
        _sys_proc.terminate()
        _sys_proc = None
        _ok("System monitor stopped")

    elif action == "status":
        log_file = SCRIPT_DIR / "system_log.json"
        if not log_file.exists():
            _warn("No system log found"); return
        try:
            import json
            data = json.loads(log_file.read_text("utf-8"))
            samples = data.get("samples", [])
            if not samples:
                _warn("No samples yet"); return
            latest = samples[-1]
            avg_cpu = sum(s.get("cpu", 0) for s in samples[-30:]) / min(30, len(samples))
            avg_ram = sum(s.get("ram", 0) for s in samples[-30:]) / min(30, len(samples))
            print(f"\n  {C_BRIGHT_CYAN}System Status{C_RESET}")
            print(f"  Latest sample: CPU={latest.get('cpu', 0):.1f}% | RAM={latest.get('ram', 0):.1f}%")
            if 'gpu' in latest:
                print(f"  GPU={latest.get('gpu', 0):.1f}% | VRAM={latest.get('vram', 0):.1f}%")
            print(f"  30-sample avg: CPU={avg_cpu:.1f}% | RAM={avg_ram:.1f}%")
            print(f"  Samples total: {len(samples)}")
        except Exception as e:
            _err(f"Failed: {e}")

    elif action.startswith("report"):
        parts = action.split()
        mins = 5
        if len(parts) > 1:
            try:
                mins = int(parts[1])
            except Exception:
                pass
        log_file = SCRIPT_DIR / "system_log.json"
        if not log_file.exists():
            _warn("No system log found"); return
        try:
            import json
            data = json.loads(log_file.read_text("utf-8"))
            samples = data.get("samples", [])
            now = datetime.now().timestamp()
            cutoff = now - mins * 60
            recent = [s for s in samples if s.get("ts", 0) > cutoff]
            if not recent:
                _warn(f"No samples in last {mins} min"); return
            print(f"\n  {C_BRIGHT_CYAN}System Report — Last {mins} min ({len(recent)} samples){C_RESET}")
            print(f"  CPU:   min={min(s.get('cpu',0) for s in recent):.1f}%  "
                  f"avg={sum(s.get('cpu',0) for s in recent)/len(recent):.1f}%  "
                  f"max={max(s.get('cpu',0) for s in recent):.1f}%")
            print(f"  RAM:   min={min(s.get('ram',0) for s in recent):.1f}%  "
                  f"avg={sum(s.get('ram',0) for s in recent)/len(recent):.1f}%  "
                  f"max={max(s.get('ram',0) for s in recent):.1f}%")
            if 'gpu' in recent[0]:
                print(f"  GPU:   min={min(s.get('gpu',0) for s in recent):.1f}%  "
                      f"avg={sum(s.get('gpu',0) for s in recent)/len(recent):.1f}%  "
                      f"max={max(s.get('gpu',0) for s in recent):.1f}%")
                print(f"  VRAM:  min={min(s.get('vram',0) for s in recent):.1f}%  "
                      f"avg={sum(s.get('vram',0) for s in recent)/len(recent):.1f}%  "
                      f"max={max(s.get('vram',0) for s in recent):.1f}%")
        except Exception as e:
            _err(f"Failed: {e}")
    else:
        _warn("Usage: sys start|status|report [min]|stop")


# ============================================================
# COMMAND: game
# ============================================================

def cmd_game():
    script = SCRIPT_DIR / "game_monitor.py"
    if not script.exists():
        _err("game_monitor.py not found"); return
    sp = Spinner("Detecting game")
    sp.start()
    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, timeout=30
        )
        sp.stop(f"Done ({time.time()-t0:.1f}s)")
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"{C_BRIGHT_RED}{result.stderr}{C_RESET}")
    except Exception as e:
        sp.stop(f"Error: {e}", ok=False)


# ============================================================
# COMMAND: overlay
# ============================================================

def cmd_overlay(args):
    if not OVERLAY_AVAILABLE:
        _err("Overlay not available"); return
    try:
        x, y, w, h = int(args[0]), int(args[1]), int(args[2]), int(args[3])
        label = " ".join(args[4:]) if len(args) > 4 else ""
        show_rect(x, y, w, h, label, "#00FF00", 8)
        _ok(f"Overlay rect ({x},{y}) {w}x{h} '{label}'")
    except Exception as e:
        _err(f"Invalid: {e}")


def cmd_circle(args):
    if not OVERLAY_AVAILABLE:
        _err("Overlay not available"); return
    try:
        cx, cy, r = int(args[0]), int(args[1]), int(args[2])
        label = " ".join(args[3:]) if len(args) > 3 else ""
        show_circle(cx, cy, r, label, "#00FF00", 8)
        _ok(f"Overlay circle ({cx},{cy}) r={r} '{label}'")
    except Exception as e:
        _err(f"Invalid: {e}")


# ============================================================
# REPL
# ============================================================

def repl():
    _hide_cursor()
    try:
        _banner()
        print(f"  {C_DIM}Type{C_RESET} {C_CYAN}help{C_RESET} {C_DIM}for all commands{C_RESET}")
        print(f"  {C_DIM}Press{C_RESET} {C_MAGENTA}Ctrl+C{C_RESET} {C_DIM}to quit{C_RESET}\n")
        _div()

        while True:
            try:
                prompt = input(f"\n{C_BRIGHT_GREEN}>{C_RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n\n  {C_DIM}Goodbye!{C_RESET}\n")
                break

            if not prompt:
                continue

            parts = prompt.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("quit", "exit", "q"):
                # Stop background services
                global _loop_running, _log_proc, _sys_proc
                if _loop_running:
                    _loop_running = False
                if _log_proc:
                    _log_proc.terminate()
                    _log_proc = None
                if _sys_proc:
                    _sys_proc.terminate()
                    _sys_proc = None
                print(f"\n  {C_DIM}Goodbye!{C_RESET}\n")
                break

            if cmd in ("clear", "cls"):
                os.system("cls" if os.name == "nt" else "clear")
                _banner()
                print(f"  {C_DIM}Type{C_RESET} {C_CYAN}help{C_RESET} {C_DIM}for all commands{C_RESET}")
                continue

            if cmd == "help":
                _help()
                continue

            # --- ask ---
            if cmd == "ask":
                if not args:
                    _warn("Usage: ask 'question'"); continue
                cmd_ask(" ".join(args))
                continue

            if cmd == "where":
                if not args:
                    _warn("Usage: where <item>"); continue
                cmd_ask(f"where is {' '.join(args)}?")
                continue

            # --- capture ---
            if cmd == "capture":
                cmd_capture(); continue

            if cmd == "screenshots":
                cmd_screenshots(); continue

            # --- vision ---
            if cmd == "vision":
                cmd_vision(); continue

            # --- retro ---
            if cmd == "retro":
                mins = 5
                include_input = "--input" in args
                include_system = "--system" in args
                for a in args:
                    if a.startswith("--"):
                        continue
                    try:
                        mins = int(a)
                    except Exception:
                        pass
                cmd_retro(mins, include_input, include_system)
                continue

            # --- loop ---
            if cmd == "loop":
                cmd_loop(args[0] if args else "")
                continue

            # --- log ---
            if cmd == "log":
                cmd_log(args[0] if args else "")
                continue

            # --- sys ---
            if cmd == "sys":
                cmd_sys(args[0] if args else "")
                continue

            # --- game ---
            if cmd == "game":
                cmd_game(); continue

            # --- overlay ---
            if cmd == "overlay":
                if len(args) < 4:
                    _warn("Usage: overlay X Y W H [label]"); continue
                cmd_overlay(args); continue

            if cmd == "circle":
                if len(args) < 3:
                    _warn("Usage: circle CX CY R [label]"); continue
                cmd_circle(args); continue

            # Default: treat as ask
            cmd_ask(prompt)

    finally:
        _show_cursor()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Non-interactive mode
        parts = sys.argv[1].split()
        cmd = parts[0].lower()
        args = sys.argv[2:]

        if cmd == "ask":
            cmd_ask(" ".join(sys.argv[2:]))
        elif cmd == "where":
            cmd_ask(f"where is {' '.join(sys.argv[2:])}?")
        elif cmd == "capture":
            cmd_capture()
        elif cmd == "screenshots":
            cmd_screenshots()
        elif cmd == "vision":
            cmd_vision()
        elif cmd == "retro":
            mins = 5
            include_input = "--input" in sys.argv[2:]
            include_system = "--system" in sys.argv[2:]
            for a in sys.argv[2:]:
                if a.startswith("--"):
                    continue
                try:
                    mins = int(a)
                except Exception:
                    pass
            cmd_retro(mins, include_input, include_system)
        elif cmd == "loop":
            cmd_loop(args[0] if args else "")
        elif cmd == "log":
            cmd_log(args[0] if args else "")
        elif cmd == "sys":
            cmd_sys(args[0] if args else "")
        elif cmd == "game":
            cmd_game()
        elif cmd == "overlay":
            cmd_overlay(args)
        elif cmd == "circle":
            cmd_circle(args)
        elif cmd == "help":
            _help()
        else:
            # Default: treat as question
            cmd_ask(sys.argv[1])
    else:
        repl()
