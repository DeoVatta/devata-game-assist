# ask_assistant.py
# Ask AI about anything on screen -> AI marks location
# Workflow: capture screen -> AI analyzes -> annotated screenshot saved -> overlay drawn
#
# Usage:
#   python ask_assistant.py --once    # Ask once, save annotated screenshot
#   python ask_assistant.py --hotkey  # Register Ctrl+Shift+A, stay running

import sys
import os
import time
import re
import mss
import base64
import httpx
import io
import threading
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_KEY = os.environ.get("OLAGON_API_KEY", "")
GATEWAY_URL = "https://gateway.olagon.site/anthropic/v1/messages"
MODEL = "claude-3-5-sonnet"
HOTKEY = "ctrl+shift+a"
SCRIPT_DIR = Path(__file__).parent

# Try overlay_drawer
try:
    from overlay_drawer import show_rect, show_circle
    OVERLAY_AVAILABLE = True
except Exception:
    OVERLAY_AVAILABLE = False

try:
    import tkinter as tk
    TK_AVAILABLE = True
except Exception:
    TK_AVAILABLE = False

from PIL import Image, ImageDraw, ImageFont


def capture_screen() -> tuple[str, str, int, int, int, int]:
    """Capture virtual screen, resize copy for AI, return (orig_b64, ai_b64, vw, vh, iw, ih)."""
    with mss.MSS() as sct:
        monitor = sct.monitors[0]
        img = sct.grab(monitor)
        vw = sct.monitors[0]["width"]
        vh = sct.monitors[0]["height"]

        # Convert to PIL for resize
        pil_img = Image.frombytes("RGB", img.size, img.rgb)

        # Original as PNG
        buf_orig = io.BytesIO()
        pil_img.save(buf_orig, format="PNG")
        orig_b64 = base64.b64encode(buf_orig.getvalue()).decode("utf-8")

        # Resize copy for AI (max 1920px wide)
        max_w = 1920
        if vw > max_w:
            ratio = max_w / vw
            new_h = int(vh * ratio)
            ai_img = pil_img.resize((max_w, new_h), Image.LANCZOS)
        else:
            ai_img = pil_img
        buf_ai = io.BytesIO()
        ai_img.save(buf_ai, format="PNG", optimize=False)
        ai_b64 = base64.b64encode(buf_ai.getvalue()).decode("utf-8")
        iw, ih = ai_img.size
    return orig_b64, ai_b64, vw, vh, iw, ih


def ask_ai(question: str, screen_b64: str, sw: int, sh: int) -> str:
    if not API_KEY:
        return "ERROR: OLAGON_API_KEY not set"

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
Your task: find and MARK the SPECIFIC item/element the user is asking about.

VISUAL CLUES - Balatro (if asked about Balatro):
- Balatro game tile: RED/DARK-RED background with a JOKER/POKER CARD silhouette icon
- Balatro text label appears BELOW the icon in the game tile
- Game tiles are arranged in a GRID (typically 2-4 columns on a launcher/Steam-like screen)
- Each tile = icon (top) + game name (bottom)

VISUAL CLUES - Folders (if asked about folders):
- Folders look like yellow/blue folder icons in File Explorer
- They have a folder icon shape with a name label next to or below them
- Usually in a list or grid view

VISUAL CLUES - Generic items:
- Look for the element that BEST MATCHES what the user described
- Use distinctive colors, shapes, or text labels to identify

IMPORTANT RULES:
1. MARK THE EXACT ELEMENT, not a nearby area or containing box
2. For game tiles: mark the SPECIFIC tile (icon + text for that one game), not the whole grid
3. For folders: mark the FOLDER ICON ITSELF (or the list row), not the containing window
4. Width/Height should tightly fit the element with minimal padding (10-30px)
5. If element is on RIGHT monitor: x will be 1920 or higher
6. If element is on LEFT monitor: x will be below 1920

RESPOND ONLY with this format (no other text):
```
SHAPE: rect|circle
X: <pixel_x_of_top_left_corner>
Y: <pixel_y_of_top_left_corner>
WIDTH: <pixel_width>
HEIGHT: <pixel_height>
LABEL: <short_label_max_3_words>
COLOR: green|yellow|red|blue
REASONING: <1 sentence why you marked this>
```

If not visible:
```
SHAPE: none
LABEL: tidak terlihat
COLOR: red
REASONING: item not visible
```

Now analyze carefully. Find the SPECIFIC element. Mark it precisely."""}
            ]
        }]
    }

    headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    try:
        r = httpx.post(GATEWAY_URL, json=payload, headers=headers, timeout=60)
        r.raise_for_status()
        content = r.json().get("content", [])
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text":
                    return b["text"].strip()
        return str(r.json())
    except Exception as e:
        return f"ERROR: {e}"


def parse_response(text: str) -> list[dict]:
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


def _hex_to_bgr(c):
    c = c.lstrip('#')
    return (int(c[4:6], 16), int(c[2:4], 16), int(c[0:2], 16))


def spawn_overlay(commands: list, duration: int = 12):
    if not OVERLAY_AVAILABLE:
        print("[ask] Overlay not available.")
        return
    for cmd in commands:
        if cmd.get("shape") == "none":
            continue
        shape = cmd["shape"]
        color = _hex_to_bgr(cmd.get("color", "#00FF00"))
        label = cmd.get("label", "")
        dur = int(cmd.get("duration", duration))
        try:
            if shape == "rect":
                show_rect(cmd["x"], cmd["y"], cmd["w"], cmd["h"], label, color, dur)
                print(f"[overlay] rect ({cmd['x']},{cmd['y']}) {cmd['w']}x{cmd['h']} '{label}'")
            elif shape == "circle":
                show_circle(cmd["cx"], cmd["cy"], cmd["r"], label, color, dur)
                print(f"[overlay] circle ({cmd['cx']},{cmd['cy']}) r={cmd['r']} '{label}'")
        except Exception as e:
            print(f"[overlay] Error: {e}")


def annotate_and_save(b64_data: str, commands: list, vw: int, vh: int) -> Path:
    """Decode screenshot, draw shapes on it, save annotated PNG."""
    img_bytes = base64.b64decode(b64_data)
    img = Image.open(io.BytesIO(img_bytes))
    sw, sh = img.size
    scale_x = sw / vw
    scale_y = sh / vh

    draw = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype("arial.ttf", max(14, int(16 * scale_x)))
    except Exception:
        font = ImageFont.load_default()

    for cmd in commands:
        if cmd.get("shape") == "none":
            continue

        c = cmd.get("color", "#00FF00").lstrip('#')
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        line_color = (r, g, b)
        fill_color = (r, g, b, 80)

        s = dict(cmd)
        if cmd["shape"] == "rect":
            s["x"] = int(cmd["x"] * scale_x); s["y"] = int(cmd["y"] * scale_y)
            s["w"] = int(cmd["w"] * scale_x); s["h"] = int(cmd["h"] * scale_y)
            x, y, w, h = s["x"], s["y"], s["w"], s["h"]
            draw.rectangle([x, y, x+w, y+h], fill=fill_color, outline=line_color, width=3)
            if s.get("label"):
                lx = x + w//2 - len(s["label"]) * 5
                ly = y - 24 if y > 30 else y + h + 4
                draw.rectangle([lx-4, ly-4, lx+len(s["label"])*10+4, ly+16], fill=(0,0,0,200))
                draw.text((lx, ly), s["label"], fill=line_color, font=font)
        elif cmd["shape"] == "circle":
            s["cx"] = int(cmd["cx"] * scale_x); s["cy"] = int(cmd["cy"] * scale_y)
            s["r"] = int(cmd["r"] * scale_x)
            cx, cy, rad = s["cx"], s["cy"], s["r"]
            draw.ellipse([cx-rad, cy-rad, cx+rad, cy+rad], fill=fill_color, outline=line_color, width=3)
            if s.get("label"):
                lx = cx - len(s["label"]) * 5
                ly = cy - rad - 26 if cy - rad > 30 else cy + rad + 4
                draw.rectangle([lx-4, ly-4, lx+len(s["label"])*10+4, ly+16], fill=(0,0,0,200))
                draw.text((lx, ly), s["label"], fill=line_color, font=font)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = SCRIPT_DIR / "screenshots" / f"annotated_{ts}.png"
    out_path.parent.mkdir(exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


# ============== INPUT POPUP ==============
def show_input_popup() -> str:
    if not TK_AVAILABLE:
        return input("Question: ")

    result = []
    root = tk.Tk()
    root.title("Game Assistant")
    root.geometry("600x120")
    root.attributes("-topmost", True)
    sw2 = root.winfo_screenwidth()
    sh2 = root.winfo_screenheight()
    root.geometry(f"600x120+{(sw2-600)//2}+{(sh2-120)//2}")

    def submit():
        result.append(entry.get())
        root.quit()
        root.destroy()
    def on_key(e):
        if e.keysym == "Return": submit()
        elif e.keysym == "Escape":
            result.append("")
            root.quit()
            root.destroy()

    tk.Label(root, text="What do you want to ask? (Esc=cancel)", font=("Segoe UI", 12)).pack(pady=(12,4))
    entry = tk.Entry(root, font=("Segoe UI", 14), width=60)
    entry.pack(pady=(0,8), padx=16, fill="x")
    entry.focus(); entry.bind("<Key>", on_key)
    tk.Button(root, text="Ask AI  (Enter)", command=submit, font=("Segoe UI",10)).pack(pady=(0,8))
    root.mainloop()
    return result[0] if result else ""


# ============== MAIN ==============
def query_loop():
    print("\n" + "=" * 50)
    print("   ASK ASSISTANT")
    print("=" * 50)

    question = show_input_popup()
    if not question.strip():
        print("[ask] Cancelled.")
        return

    print(f"\n[ask] Q: {question}")
    print("[ask] Capturing screen...")
    orig_b64, ai_b64, vw, vh, iw, ih = capture_screen()
    print(f"[ask] Captured {vw}x{vh} -> resized to {iw}x{ih} ({len(ai_b64)} chars)")

    print("[ask] Asking AI...")
    t0 = time.time()
    response = ask_ai(question, ai_b64, iw, ih)
    print(f"[ask] AI responded in {time.time()-t0:.1f}s:")
    print("  " + response[:300].replace('\n', '\n  '))

    commands = parse_response(response)
    print(f"[ask] {len(commands)} shape(s) parsed")

    # Scale coordinates from image coords back to virtual screen coords
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
        print(f"[ask] Scaled coords by ({sx:.3f}, {sy:.3f}) -> {vw}x{vh}")

    # Annotate screenshot + save
    if commands:
        out_path = annotate_and_save(orig_b64, commands, vw, vh)
        print(f"\n[ask] ANNOTATED SCREENSHOT: {out_path}")
        print(f"[ask] Open this PNG to see the shape on your screen!")

    # Spawn overlay
    spawn_overlay(commands)

    for cmd in commands:
        if cmd.get("reasoning"):
            print(f"[ask] Reason: {cmd['reasoning']}")
    print("=" * 50)


_hotkey_running = False

def start_hotkey_listener():
    if not PYNPUT_AVAILABLE:
        print("pynput not available. Use --once mode.")
        return
    try:
        from pynput import keyboard
        def on_activate():
            global _hotkey_running
            if _hotkey_running: return
            _hotkey_running = True
            try: query_loop()
            finally:
                time.sleep(1)
                _hotkey_running = False
        hot = keyboard.HotKey(keyboard.HotKey.parse(HOTKEY), on_activate)
        with keyboard.Listener(on_press=hot.press, suppress=False) as l:
            l.join()
    except Exception as e:
        print(f"Hotkey error: {e}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--once" in args or "-o" in args:
        query_loop()
    elif "--hotkey" in args:
        start_hotkey_listener()
    else:
        print("""Game Assistant — Ask AI to point at things

Usage:
  python ask_assistant.py --once   Ask once, save annotated screenshot + draw overlay
  python ask_assistant.py --hotkey Register Ctrl+Shift+A hotkey, stay running

What happens:
1. Captures current screen
2. AI analyzes and returns shape + coordinates
3. Annotated screenshot saved to screenshots/ folder
4. Overlay shape drawn on screen

Examples:
  "mana Balatro game?" -> AI marks Balatro tile with green rect
  "dimana folder Minami Lane?" -> AI marks folder with green rect
  "item apa untuk build damage?" -> AI marks relevant items
""")
