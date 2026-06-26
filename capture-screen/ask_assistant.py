# ask_assistant.py
# Global hotkey trigger -> ask AI a question -> AI marks location on screen
# Hotkey: Ctrl+Shift+A
# Usage:
#   python ask_assistant.py              # interactive mode
#   python ask_assistant.py --once       # single query then exit
#   python ask_assistant.py --hotkey     # register hotkey, stay running

import sys
import os
import time
import re
import mss
import base64
import httpx
import threading
import uuid
from datetime import datetime
from pathlib import Path

# dotenv
from dotenv import load_dotenv
load_dotenv(__file__ + "/../.env")

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============== CONFIG ==============
API_KEY = os.environ.get("OLAGON_API_KEY", "")
GATEWAY_URL = "https://gateway.olagon.site/anthropic/v1/messages"
MODEL = "claude-3-5-sonnet"
HOTKEY = "ctrl+shift+a"

SCRIPT_DIR = Path(__file__).parent

# ============== DEPENDENCIES ==============
try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

try:
    from overlay_drawer import show_rect, show_circle
    OVERLAY_AVAILABLE = True
except Exception:
    OVERLAY_AVAILABLE = False

try:
    import tkinter as tk
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False

# ============== SCREENSHOT ==============
def capture_screen() -> str:
    """Capture full screen, return base64 PNG."""
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        img = sct.grab(monitor)
        buf = mss.tools.to_png(img.rgb, img.size)
    return base64.b64encode(buf).decode("utf-8")

def get_screen_size():
    if TK_AVAILABLE:
        root = tk.Tk()
        root.withdraw()
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        root.destroy()
        return w, h
    return 1920, 1080

# ============== AI QUERY ==============
def ask_ai(question: str, screen_b64: str) -> str:
    """Send question + screenshot to AI, return text response."""
    if not API_KEY:
        return "ERROR: OLAGON_API_KEY not set in .env"

    sw, sh = get_screen_size()

    payload = {
        "model": MODEL,
        "max_tokens": 1024,
        "stream": False,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screen_b64}},
                {"type": "text", "text": f"""You are a game assistant. The user asks: "{question}"

Screen resolution: {sw}x{sh} pixels. The user wants you to mark/point to the answer on screen.

RESPOND ONLY with this EXACT format (no other text):
```
SHAPE: rect|circle
X: <pixel_x>
Y: <pixel_y>
WIDTH: <pixel_width>   (only for rect)
HEIGHT: <pixel_height> (only for rect)
CX: <center_x>          (only for circle)
CY: <center_y>         (only for circle)
RADIUS: <pixels>       (only for circle)
LABEL: <short_label>
COLOR: green|yellow|red|blue
REASONING: <1 sentence why this is the answer>
```

Rules:
- Use SHAPE=rect for items that are boxes/squares/cards/inventory slots
- Use SHAPE=circle for items that are circular (orbs, gems, icons, minimap markers)
- X,Y are top-left pixel coordinates (0-indexed from top-left)
- WIDTH/HEIGHT should be slightly larger than the item (10-30px padding)
- RADIUS should include the item with small padding
- LABEL: max 30 chars, use game item name or short description
- COLOR: green=correct/yes, yellow=warning/caution, red=wrong/danger, blue=info
- If the answer is NOT on screen (e.g. item is in another map area), respond:
```
SHAPE: none
LABEL: tidak terlihat
COLOR: red
REASONING: item is not visible on current screen
```
- If you are uncertain, use a larger area or circle to be safe
- Be precise but generous with padding

Now analyze the screen and respond with the format above."""}
            ]
        }]
    }

    headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}

    try:
        response = httpx.post(GATEWAY_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        result = response.json()
        content = result.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block["text"].strip()
        return str(result)
    except Exception as e:
        return f"ERROR: {e}"

# ============== PARSE RESPONSE ==============
def parse_ai_response(text: str) -> list[dict]:
    """Parse AI response into list of draw commands."""
    commands = []
    blocks = re.split(r'```|SHAPE:', text)
    for block in blocks:
        block = block.strip()
        if not block or block.startswith('json') or block.startswith('yaml'):
            continue
        if block.startswith('none'):
            commands.append({"shape": "none", "label": "tidak terlihat", "color": "red"})
            continue

        shape = re.search(r'\b(rect|circle)\b', block, re.I)
        if not shape:
            continue

        shape_type = shape.group(1).lower()
        cmd = {"shape": shape_type}

        if shape_type == "rect":
            x = re.search(r'X:\s*(\d+)', block)
            y = re.search(r'Y:\s*(\d+)', block)
            w = re.search(r'WIDTH:\s*(\d+)', block)
            h = re.search(r'HEIGHT:\s*(\d+)', block)
            if x and y:
                cmd["x"] = int(x.group(1))
                cmd["y"] = int(y.group(1))
                cmd["w"] = int(w.group(1)) if w else 60
                cmd["h"] = int(h.group(1)) if h else 40
        elif shape_type == "circle":
            cx = re.search(r'CX:\s*(\d+)', block)
            cy = re.search(r'CY:\s*(\d+)', block)
            r = re.search(r'RADIUS:\s*(\d+)', block)
            if cx and cy:
                cmd["cx"] = int(cx.group(1))
                cmd["cy"] = int(cy.group(1))
                cmd["r"] = int(r.group(1)) if r else 30

        label = re.search(r'LABEL:\s*(.+)', block)
        if label:
            cmd["label"] = label.group(1).strip()[:40]
        else:
            cmd["label"] = ""

        color = re.search(r'COLOR:\s*(\w+)', block)
        if color:
            col = color.group(1).lower()
            color_map = {"green": "#00FF00", "yellow": "#FFFF00", "red": "#FF4444", "blue": "#4488FF"}
            cmd["color"] = color_map.get(col, "#00FF00")
        else:
            cmd["color"] = "#00FF00"

        reasoning = re.search(r'REASONING:\s*(.+)', block)
        if reasoning:
            cmd["reasoning"] = reasoning.group(1).strip()

        commands.append(cmd)

    return commands

# ============== DRAW COMMANDS ==============
COLOR_HEX = {"green": "#00FF00", "yellow": "#FFFF00", "red": "#FF4444", "blue": "#4488FF"}

def apply_draw_commands(commands: list, duration: int = 8):
    """Draw shapes on screen based on parsed commands."""
    if not OVERLAY_AVAILABLE:
        print("[ask] Overlay not available. Draw commands:")
        for cmd in commands:
            print(f"  {cmd}")
        return

    for cmd in commands:
        if cmd.get("shape") == "none":
            print(f"[ask] AI: {cmd.get('reasoning', 'Item not on screen')}")
            continue

        shape = cmd["shape"]
        color = cmd.get("color", "#00FF00")
        label = cmd.get("label", "")
        duration = int(cmd.get("duration", duration))

        try:
            if shape == "rect":
                show_rect(cmd["x"], cmd["y"], cmd["w"], cmd["h"], label, color, duration)
                print(f"[overlay] rect: ({cmd['x']},{cmd['y']}) {cmd['w']}x{cmd['h']} '{label}' {color}")
            elif shape == "circle":
                show_circle(cmd["cx"], cmd["cy"], cmd["r"], label, color, duration)
                print(f"[overlay] circle: ({cmd['cx']},{cmd['cy']}) r={cmd['r']} '{label}' {color}")
        except Exception as e:
            print(f"[overlay] Error drawing {shape}: {e}")

# ============== INPUT PROMPT ==============
def show_input_popup(title="Ask AI", prompt="Question:") -> str:
    """Show a simple input popup and return user text."""
    if not TK_AVAILABLE:
        return input(f"{prompt} ")

    result = []

    def run_popup():
        root = tk.Tk()
        root.title(title)
        root.geometry("600x120")
        root.attributes("-topmost", True)

        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        rx = (sw - 600) // 2
        ry = (sh - 120) // 2
        root.geometry(f"600x120+{rx}+{ry}")

        def on_submit():
            result.append(entry.get())
            root.quit()
            root.destroy()

        def on_key(e):
            if e.keysym == "Return":
                on_submit()
            elif e.keysym == "Escape":
                result.append("")
                root.quit()
                root.destroy()

        lbl = tk.Label(root, text=prompt, font=("Segoe UI", 12))
        lbl.pack(pady=(12, 4))

        entry = tk.Entry(root, font=("Segoe UI", 14), width=60)
        entry.pack(pady=(0, 8), padx=16, fill="x")
        entry.focus()
        entry.bind("<Key>", on_key)

        btn = tk.Button(root, text="Ask AI  (Enter)", command=on_submit, font=("Segoe UI", 10))
        btn.pack(pady=(0, 8))

        root.mainloop()

    run_popup()
    return result[0] if result else ""

# ============== MAIN QUERY FLOW ==============
def query_loop():
    """Single query: prompt -> capture -> ask AI -> draw overlay."""
    print("\n" + "=" * 50)
    print("   ASK ASSISTANT")
    print("=" * 50)

    # 1. Get question
    question = show_input_popup(
        title="Game Assistant — Ask Question",
        prompt="What do you want to ask? (Esc to cancel)"
    )

    if not question.strip():
        print("[ask] Cancelled.")
        return

    print(f"\n[ask] Q: {question}")

    # 2. Capture screen
    print("[ask] Capturing screen...")
    t0 = time.time()
    screen_b64 = capture_screen()
    print(f"[ask] Captured ({len(screen_b64)} chars, {time.time()-t0:.1f}s)")

    # 3. Ask AI
    print("[ask] Sending to AI...")
    t1 = time.time()
    response = ask_ai(question, screen_b64)
    print(f"[ask] AI response ({time.time()-t1:.1f}s):")
    print("  " + response[:200].replace('\n', '\n  '))

    # 4. Parse and draw
    commands = parse_ai_response(response)
    print(f"[ask] Parsed {len(commands)} draw command(s)")
    apply_draw_commands(commands, duration=10)

    # Print reasoning
    for cmd in commands:
        if cmd.get("reasoning"):
            print(f"[ask] Reason: {cmd['reasoning']}")

    print("=" * 50)


# ============== HOTKEY LISTENER ==============
_hotkey_running = False

def start_hotkey_listener():
    """Register global hotkey. Ctrl+Shift+A triggers query_loop()."""
    if not PYNPUT_AVAILABLE:
        print("[ask] pynput not available. Run in --once mode instead.")
        return

    print(f"[ask] Hotkey registered: {HOTKEY.upper()}")
    print("[ask] Press Ctrl+Shift+A anywhere to ask a question.")
    print("[ask] Ctrl+C to exit.\n")

    def on_activate():
        global _hotkey_running
        if _hotkey_running:
            return  # debounce: ignore if already running
        _hotkey_running = True
        try:
            query_loop()
        finally:
            time.sleep(1)
            _hotkey_running = False

    # Use pynput hotkey
    try:
        hot = keyboard.HotKey(
            keyboard.HotKey.parse(HOTKEY),
            on_activate
        )
        with keyboard.Listener(on_press=hot.press, suppress=False) as listener:
            listener.join()
    except Exception as e:
        print(f"[ask] Hotkey error: {e}")


# ============== CLI ==============
if __name__ == "__main__":
    args = sys.argv[1:]

    if "--once" in args or "-o" in args:
        query_loop()
    elif "--hotkey" in args or "-h" in args:
        start_hotkey_listener()
    else:
        print("""Game Assistant — Ask AI to point at things on screen

Usage:
  python ask_assistant.py --once     # Ask once, show result, exit
  python ask_assistant.py --hotkey   # Register Ctrl+Shift+A, stay running

Examples:
  - Open inventory, ask "mana item bernama Shadow Dagger"
  - Open map, ask "dimana lokasi dungeon?"
  - Any screen, ask "item mana yang bisa meningkatkan damage"

The AI will mark the answer with a green rectangle or circle on screen.
""")
