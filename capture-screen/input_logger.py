# input_logger.py
# Threadsafe keyboard + mouse input logger
# Uses JSON file as shared state — write by logger, read by vision_monitor
# Run as: python input_logger.py --start

import threading
import time
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ============== CONFIG ==============
SCRIPT_DIR = Path(__file__).parent
LOG_FILE = SCRIPT_DIR / "input_log.json"
MAX_EVENTS = 1000
PERSIST_INTERVAL = 2  # seconds between file writes

# ============== KEYBOARD DETECTION ==============
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

# ============== MOUSE DETECTION ==============
try:
    from pynput import mouse
    MOUSE_AVAILABLE = True
except ImportError:
    MOUSE_AVAILABLE = False

# ============== FILE-BASED EVENT STORE ==============
# All state lives in the JSON file so vision_monitor can read it
# without importing this module.

_state = {
    "updated": None,
    "count": 0,
    "last_key": "",
    "last_mouse": [0, 0],
    "events": []
}
_state_lock = threading.Lock()
_last_persist = 0

def _load_state():
    global _state
    if not LOG_FILE.exists():
        return
    try:
        with open(LOG_FILE) as f:
            _state = json.load(f)
    except Exception:
        pass

def _save_state():
    global _state, _last_persist
    now = time.time()
    if now - _last_persist < PERSIST_INTERVAL:
        return
    _last_persist = now
    _state["updated"] = datetime.now().isoformat()
    try:
        with open(LOG_FILE, "w") as f:
            json.dump(_state, f)
    except Exception:
        pass

def _append_event(evt: dict):
    global _state
    with _state_lock:
        _state["events"].append(evt)
        if len(_state["events"]) > MAX_EVENTS:
            _state["events"].pop(0)
        _state["count"] = len(_state["events"])
        if evt["type"] == "key":
            _state["last_key"] = evt["key"]
        elif evt["type"] in ("click", "scroll"):
            _state["last_mouse"] = [evt["x"], evt["y"]]
        _save_state()

# ============== HOOK HANDLERS ==============
def _on_key(e):
    if e.event_type == "down":
        try:
            name = e.name
        except AttributeError:
            name = str(e)
        ts = datetime.now()
        _append_event({
            "type": "key",
            "key": name,
            "timestamp": ts.isoformat(),
            "epoch_ms": int(ts.timestamp() * 1000)
        })

_last_mouse_move_save = 0

def _on_mouse_move(x, y):
    global _last_mouse_move_save
    _state["last_mouse"] = [x, y]
    now = time.time()
    if now - _last_mouse_move_save >= PERSIST_INTERVAL:
        _last_mouse_move_save = now
        _save_state()

def _on_mouse_click(x, y, button, pressed):
    if not pressed:
        return
    btn = str(button).replace("Button.", "")
    ts = datetime.now()
    _append_event({
        "type": "click",
        "x": x,
        "y": y,
        "button": btn,
        "timestamp": ts.isoformat(),
        "epoch_ms": int(ts.timestamp() * 1000)
    })

def _on_mouse_scroll(x, y, dx, dy):
    if dy == 0:
        return
    ts = datetime.now()
    _append_event({
        "type": "scroll",
        "x": x,
        "y": y,
        "dx": dx,
        "dy": dy,
        "timestamp": ts.isoformat(),
        "epoch_ms": int(ts.timestamp() * 1000)
    })

# ============== FORMAT FOR AI ==============
def format_input_summary(events: list) -> str:
    """Format events into readable summary for AI."""
    if not events:
        return "No input recorded."

    key_events = [e for e in events if e["type"] == "key"]
    click_events = [e for e in events if e["type"] == "click"]
    scroll_events = [e for e in events if e["type"] == "scroll"]

    lines = []

    if key_events:
        keys = [e["key"] for e in key_events]
        cleaned = []
        prev = None
        for k in keys:
            if k != prev:
                cleaned.append(k)
                prev = k
        lines.append(f"Keys pressed ({len(key_events)} total): {' + '.join(cleaned[:30])}")
        if len(cleaned) > 30:
            lines[-1] += f" ... (+{len(cleaned)-30} more)"

    if click_events:
        clicks = [f"{e['button']}@({e['x']},{e['y']})" for e in click_events]
        lines.append(f"Mouse clicks ({len(click_events)}): {', '.join(clicks[:20])}")
        if len(click_events) > 20:
            lines[-1] += f" ... (+{len(click_events)-20} more)"

    if scroll_events:
        scrolls = [f"{e['dy']:+d}" for e in scroll_events if e["dy"] != 0]
        lines.append(f"Scrolls ({len(scroll_events)}): {', '.join(scrolls[:10])}")

    return "\n".join(lines) if lines else "No input recorded."

# ============== READ FROM FILE (for vision_monitor) ==============
def get_events_from_file(from_ms: int = 0, to_ms: int = None) -> list:
    """Read events from JSON file for given time range. Call without importing."""
    _load_state()
    if to_ms is None:
        to_ms = int(time.time() * 1000)
    return [e for e in _state["events"] if from_ms <= e["epoch_ms"] <= to_ms]

def get_latest_from_file() -> dict:
    """Get current state from JSON file."""
    _load_state()
    return _state.copy()

# ============== START/STOP ==============
_running = False

def start():
    global _running
    _running = True
    _load_state()

    threads = []

    if KEYBOARD_AVAILABLE:
        t = threading.Thread(target=_run_keyboard, daemon=True)
        t.start()
        threads.append(t)

    if MOUSE_AVAILABLE:
        t = threading.Thread(target=_run_mouse, daemon=True)
        t.start()
        threads.append(t)

    # Persist heartbeat every 30s even if no events
    def heartbeat():
        while _running:
            time.sleep(30)
            _save_state()
    ht = threading.Thread(target=heartbeat, daemon=True)
    ht.start()

    return (f"Input logger started. "
            f"Keyboard: {'ON' if KEYBOARD_AVAILABLE else 'OFF'}, "
            f"Mouse: {'ON' if MOUSE_AVAILABLE else 'OFF'}, "
            f"Log: {LOG_FILE.name}")

def _run_keyboard():
    try:
        keyboard.hook(_on_key)
        while _running:
            time.sleep(1)
    except Exception:
        pass

def _run_mouse():
    try:
        with mouse.Listener(
            on_move=_on_mouse_move,
            on_click=_on_mouse_click,
            on_scroll=_on_mouse_scroll
        ) as listener:
            while _running:
                time.sleep(1)
            listener.stop()
    except Exception:
        pass

def stop():
    global _running
    _running = False
    _save_state()
    try:
        keyboard.unhook_all()
    except Exception:
        pass
    return f"Stopped. {_state['count']} events logged."

# ============== CLI ==============
if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print("""Input Logger - Keyboard + Mouse recorder

Usage:
  python input_logger.py --start     Start logging in background
  python input_logger.py --status    Show current buffer status
  python input_logger.py --stop      Stop and save log
  python input_logger.py --dump      Dump events to JSON

Start once. vision_monitor reads from JSON file automatically.
""")
    elif "--start" in args:
        print(start())
        print("Input logger running. Press Ctrl+C to stop.")
        try:
            while _running:
                time.sleep(1)
        except KeyboardInterrupt:
            print(stop())
    elif "--status" in args:
        s = get_latest_from_file()
        print(f"Buffer: {s['count']} events")
        print(f"Last key: {s['last_key']}")
        print(f"Last mouse: {s['last_mouse']}")
    elif "--stop" in args:
        print(stop())
    elif "--dump" in args:
        _load_state()
        with open(LOG_FILE) as f:
            data = json.load(f)
        print(json.dumps(data, indent=2))
