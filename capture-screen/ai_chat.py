# ai_chat.py
# CLI chat interface with AI — captures screen and asks questions
# Usage:
#   python ai_chat.py                    # Interactive REPL
#   python ai_chat.py "question"        # Single question, print result, exit

import sys
import os
import time
import re
import mss
import base64
import httpx
import io
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_KEY = os.environ.get("OLAGON_API_KEY", "")
GATEWAY_URL = "https://gateway.olagon.site/anthropic/v1/messages"
MODEL = "claude-3-5-sonnet"

try:
    from overlay_drawer import show_rect, show_circle
    OVERLAY_AVAILABLE = True
except Exception:
    OVERLAY_AVAILABLE = False


def capture_screen():
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


def ask_ai(question: str, screen_b64: str, sw: int, sh: int) -> str:
    if not API_KEY:
        return "ERROR: OLAGON_API_KEY not set. Check capture-screen/.env"

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

VISUAL CLUES - Balatro (if asked about Balatro):
- Balatro game tile: RED/DARK-RED background with a JOKER/POKER CARD silhouette icon
- Balatro text label appears BELOW the icon in the game tile
- Game tiles are arranged in a GRID on a launcher/Steam-like screen
- Each tile = icon (top) + game name (bottom)

VISUAL CLUES - Folders:
- Folders look like yellow/blue folder icons in File Explorer
- Usually in a list or grid view

IMPORTANT RULES:
1. MARK THE EXACT ELEMENT, not a nearby area or containing box
2. For game tiles: mark the SPECIFIC tile (icon + text for that one game)
3. For folders: mark the FOLDER ICON ITSELF
4. Width/Height should tightly fit the element with 10-30px padding
5. If element is on RIGHT monitor: x will be 1920 or higher

RESPOND ONLY with this format (no other text):
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
```

Now analyze carefully and respond."""}
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


def parse_response(text: str):
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


def spawn_overlay(commands, duration=12):
    if not OVERLAY_AVAILABLE:
        return
    for cmd in commands:
        if cmd.get("shape") == "none":
            continue
        shape = cmd["shape"]
        # Pass hex string directly — show_rect/show_circle handle it
        color = str(cmd.get("color", "#00FF00"))
        label = cmd.get("label", "")
        dur = int(cmd.get("duration", duration))
        try:
            if shape == "rect":
                show_rect(cmd["x"], cmd["y"], cmd["w"], cmd["h"], label, color, dur)
                print(f"  [overlay] rect ({cmd['x']},{cmd['y']}) {cmd['w']}x{cmd['h']} '{label}'")
            elif shape == "circle":
                show_circle(cmd["cx"], cmd["cy"], cmd["r"], label, color, dur)
                print(f"  [overlay] circle ({cmd['cx']},{cmd['cy']}) r={cmd['r']} '{label}'")
        except Exception as e:
            print(f"  [overlay] error: {e}")


def save_screenshot(orig_b64, commands, vw, vh):
    """Save annotated screenshot."""
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


def run(question: str):
    print(f"\n[?] {question}")
    print("[...] Capturing screen...")
    orig_b64, ai_b64, vw, vh, iw, ih = capture_screen()
    print(f"[...] {vw}x{vh} -> resized to {iw}x{ih}")

    print("[...] Asking AI...")
    t0 = time.time()
    response = ask_ai(question, ai_b64, iw, ih)
    elapsed = time.time() - t0

    if response.startswith("ERROR:"):
        print(f"[!] {response}")
        return

    print(f"[OK] AI ({elapsed:.1f}s)")
    print("-" * 50)
    print(response)
    print("-" * 50)

    commands = parse_response(response)
    if commands:
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

        spawn_overlay(commands)
        path = save_screenshot(orig_b64, commands, vw, vh)
        print(f"[+] Screenshot: {path}")

    for cmd in commands:
        if cmd.get("reasoning"):
            print(f"[!] Reason: {cmd['reasoning']}")


def repl():
    print("=" * 50)
    print("  AI GAME ASSISTANT — CLI")
    print("=" * 50)
    print("  Type your question and press Enter")
    print("  Commands: quit, exit, clear")
    print("=" * 50)
    print()

    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[bye]")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("[bye]")
            break
        if question.lower() == "clear":
            os.system("cls" if os.name == "nt" else "clear")
            continue

        run(question)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run(" ".join(sys.argv[1:]))
    else:
        repl()
