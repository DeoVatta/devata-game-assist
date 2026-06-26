# vision_monitor.py
# AI-powered screen capture & analysis
# Uses Olagon AI Gateway for vision analysis
#
# Modes:
#   python vision_monitor.py          - Single capture (default)
#   python vision_monitor.py --retro  - Retrospective 5 min analysis
#   python vision_monitor.py --retro 3 - Retrospective N min analysis

import mss
import base64
import json
import time
import sys
import os
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
import io

# Fix Unicode for Windows console
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============== CONFIG ==============
API_KEY = os.environ.get("OLAGON_API_KEY", "")
GATEWAY_URL = "https://gateway.olagon.site/anthropic/v1/messages"
MODEL = "claude-3-5-sonnet"

SCRIPT_DIR = Path(__file__).parent
SCREENSHOT_DIR = SCRIPT_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

# History source: use capture_loop screenshots (180 files / 30 min)
# as the historical record
RETRO_MAX_MINUTES = 5
RETRO_FRAME_INTERVAL = 30   # seconds between frames
RETRO_MAX_FRAMES = 4         # max frames per request (keep payload small)
RETRO_RESIZE_WIDTH = 1024    # resize width to reduce size

GAME_KEYWORDS = {
    "descend": ["DescendTheWoods", "Descending The Woods"],
    "taskbarhero": ["TaskBarHero", "TBH"],
    "diablo": ["Diablo"],
    "poe": ["Path of Exile", "pathofexile"],
    "stardew": ["Stardew"],
    "elden": ["Elden Ring"],
    "cyberpunk": ["Cyberpunk"],
    "genshin": ["Genshin", "Zenless"],
    "valorant": ["VALORANT", "valorant"],
    "forza": ["Forza", "forza"],
}

# ============== UTILS ==============

def get_running_games():
    try:
        import subprocess
        result = subprocess.run(
            ['powershell', '-Command',
             "Get-Process | Where-Object {$_.MainWindowTitle} | "
             "Select-Object Name,MainWindowTitle | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []

        processes = json.loads(result.stdout) if result.stdout.strip() else []
        if isinstance(processes, dict):
            processes = [processes]

        games = []
        for p in processes:
            name = p.get('Name', '')
            title = p.get('MainWindowTitle', '')
            for game_key, keywords in GAME_KEYWORDS.items():
                if any(k.lower() in (name + title).lower() for k in keywords):
                    games.append({'name': name, 'title': title, 'game': game_key})
                    break
        return games
    except Exception:
        return []

def take_screenshot() -> tuple[Path, int]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{timestamp}.png"
    filepath = SCREENSHOT_DIR / filename

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        img = sct.grab(monitor)
        mss.tools.to_png(img.rgb, img.size, output=str(filepath))

    size_kb = filepath.stat().st_size // 1024
    return filepath, size_kb

def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def get_history_frames(minutes: int = 5, interval: int = 30) -> list[dict]:
    """
    Read screenshot history and return key frames.
    interval = seconds between frames to analyze.
    Returns list of {path, timestamp, age_seconds} oldest-first.
    """
    now = datetime.now()
    cutoff = now - timedelta(minutes=minutes)

    # Get all PNG files sorted by mtime
    files = sorted(
        [f for f in SCREENSHOT_DIR.iterdir() if f.suffix == '.png'],
        key=lambda f: f.stat().st_mtime
    )

    frames = []
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            continue

        # Only include frames at ~interval seconds apart
        if not frames:
            frames.append({'path': f, 'timestamp': mtime, 'age_seconds': int((now - mtime).total_seconds())})
        else:
            last = frames[-1]['timestamp']
            gap = (mtime - last).total_seconds()
            if gap >= interval:
                frames.append({'path': f, 'timestamp': mtime, 'age_seconds': int((now - mtime).total_seconds())})

    return frames

def build_timeline(frames: list) -> str:
    """Build human-readable timeline from frame metadata."""
    if not frames:
        return "No screenshot history found."

    lines = []
    for f in frames:
        age = f['age_seconds']
        if age >= 60:
            mins = age // 60
            secs = age % 60
            label = f"{mins}m{secs}s ago"
        else:
            label = f"{age}s ago"
        lines.append(f"  - {label}: {f['path'].name}")
    return "\n".join(lines)

# ============== AI ANALYZERS ==============

def analyze_single(image_path: Path, games: list) -> str:
    """Single screenshot analysis -- 1 request."""
    try:
        image_b64 = encode_image(image_path)

        game_context = ""
        if games:
            game_names = [g['title'] for g in games]
            game_context = f"User is running: {', '.join(game_names)}."

        payload = {
            "model": MODEL,
            "max_tokens": 1024,
            "stream": False,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
                    {"type": "text", "text": f"""Analyze this screenshot and respond in Indonesian.

{game_context}

Answer in 1-2 short sentences:
1. What is on screen?
2. What stage/location if it's a game?
3. What is the user doing or should do next?

Be brief and direct. No markdown."""}
                ]
            }]
        }

        headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
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
        return f"Error: {e}"

def resize_image(path: Path, max_width: int = RETRO_RESIZE_WIDTH) -> str:
    """Resize image and return base64 PNG."""
    img = Image.open(path)
    # Only resize if wider than max_width
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def analyze_retrospective(frames: list, games: list, minutes: int, input_summary: str = "", system_summary: str = "") -> str:
    """
    Retrospective multi-frame analysis -- 1 request.
    Sends up to 4 frames + timeline text + input data in a single request.
    Images resized to 1024px wide to keep payload small.
    """
    if not frames:
        return "Tidak ada screenshot history untuk dianalisa."

    try:
        # Limit to last N frames, evenly spaced
        selected = frames[-RETRO_MAX_FRAMES:]
        frame_contents = []

        for f in selected:
            b64 = resize_image(f['path'])
            age = f['age_seconds']
            age_label = f"{age//60}m{age%60}s ago" if age >= 60 else f"{age}s ago"
            frame_contents.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64},
                "alt": age_label
            })

        # Build timeline description
        timeline_desc = "\n".join([
            f"- {f['age_seconds']//60}m{f['age_seconds']%60}s ago: {f['path'].name}"
            if f['age_seconds'] >= 60 else f"- {f['age_seconds']}s ago: {f['path'].name}"
            for f in selected
        ])

        game_context = ""
        if games:
            game_names = [g['title'] for g in games]
            game_context = f"User is running: {', '.join(game_names)}."

        # Input section
        input_section = (f"\n\nUSER INPUT RECORDING (keyboard + mouse):\n{input_summary}" if input_summary else "")

        # System section
        system_section = f"\n\nPC PERFORMANCE DATA:\n{system_summary}" if system_summary else ""

        prompt_text = f"""Analyze ALL frames below -- sequential screenshots from the last {minutes} minutes.

{game_context}{input_section}{system_section}

Screenshots timeline (oldest â†’ newest):
{timeline_desc}

Your task -- answer in Indonesian:
1. Describe what the user was doing across these frames (game events, actions, locations).
2. If FPS/tactical shooter (Valorant, CS2, etc): Analyze weapon used, fire mode (tap/burst/spray), movement during fire, positioning. Be specific about mistakes.
3. If racing game: Analyze racing line, braking points, steering input, speed management.
4. Correlate PC performance data with gameplay: if high CPU/GPU usage detected, was the game lagging? Did performance affect gameplay?
5. Identify any mistakes, missed opportunities, or suboptimal decisions -- be specific.
6. Give concrete advice on what the user should have done differently.
7. For upgrade recommendations: use the PC performance data to suggest targeted improvements.

Respond in Indonesian. Be direct and specific -- this is for game review/learning.
Synthesize frames + input + PC data into a coherent narrative. No markdown formatting."""

        # Insert text at the end
        frame_contents.append({"type": "text", "text": prompt_text})

        payload = {
            "model": MODEL,
            "max_tokens": 2048,
            "stream": False,
            "messages": [{"role": "user", "content": frame_contents}]
        }

        headers = {"x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}

        start = time.time()
        response = httpx.post(GATEWAY_URL, json=payload, headers=headers, timeout=120)
        elapsed = time.time() - start
        response.raise_for_status()

        result = response.json()
        content = result.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block["text"].strip()
        return f"Response: {result}"

    except Exception as e:
        return f"Error: {e}"

# ============== MAIN ==============

def main():
    args = sys.argv[1:]
    retro = "--retro" in args or "-r" in args
    include_input = "--input" in args or "-i" in args
    include_system = "--system" in args or "-s" in args

    # Parse --retro N
    retro_minutes = 5
    for i, a in enumerate(args):
        if a in ("--retro", "-r") and i + 1 < len(args):
            try:
                retro_minutes = int(args[i + 1])
            except ValueError:
                pass

    print("=" * 60)
    print("   AI VISION MONITOR")
    mode_parts = []
    if retro:
        mode_parts.append("RETROSPECTIVE")
    if include_input:
        mode_parts.append("INPUT SYNC")
    if include_system:
        mode_parts.append("SYSTEM")
    print("   Mode:", " + ".join(mode_parts) if mode_parts else "SINGLE CAPTURE")
    if retro:
        print(f"   History: last {retro_minutes} minutes")
    if include_input:
        print("   Input:  ENABLED (keys + mouse)")
    print("=" * 60)

    # 1. Scan games
    print("\n[*] Scanning processes...")
    t0 = time.time()
    games = get_running_games()
    print(f"    Done in {time.time()-t0:.1f}s | Found: {len(games)} game(s)")
    for g in games:
        print(f"    | {g['title']}")

    if retro:
        # ==================== RETROSPECTIVE MODE ====================
        print(f"\n[*] Reading screenshot history (last {retro_minutes} min)...")
        t1 = time.time()
        frames = get_history_frames(minutes=retro_minutes, interval=RETRO_FRAME_INTERVAL)
        print(f"    Found {len(frames)} frames in {time.time()-t1:.1f}s")

        if frames:
            print(f"\n    Timeline ({len(frames)} frames):")
            for f in frames:
                age = f['age_seconds']
                label = f"{age//60}m{age%60}s ago" if age >= 60 else f"{age}s ago"
                print(f"      {label:>8} | {f['path'].name}")

        # Get input events in same time range
        input_summary = ""
        if include_input and frames:
            try:
                from input_logger import get_events_from_file, get_latest_from_file, format_input_summary
                from_ms = int(frames[0]['path'].stat().st_mtime * 1000)
                to_ms = int(time.time() * 1000)
                events = get_events_from_file(from_ms, to_ms)
                state = get_latest_from_file()
                input_summary = format_input_summary(events)
                print(f"\n[*] Input events: {len(events)} recorded")
                print(f"    Last key: {state['last_key']}")
                print(f"    Mouse: {state['last_mouse']}")
                print(f"\n    Summary:\n    {input_summary}")
            except Exception as e:
                input_summary = ""
                print(f"\n[!] Input logger unavailable: {e}")

        # Get system performance data
        system_summary = ""
        if include_system:
            try:
                from system_monitor import get_samples_from_file, analyze_samples, format_system_summary
                samples = get_samples_from_file(minutes=retro_minutes)
                if samples:
                    analysis = analyze_samples(samples)
                    system_summary = format_system_summary(analysis)
                    cpu_avg = analysis.get("cpu_avg", "?")
                    gpu_avg = analysis.get("gpu_avg", "?")
                    print(f"\n[*] System perf ({retro_minutes}min):")
                    print(f"    CPU avg: {cpu_avg}% | GPU avg: {gpu_avg}%")
                    print(f"    {system_summary}")
            except Exception as e:
                system_summary = ""
                print(f"\n[!] System monitor unavailable: {e}")

        # Send to AI
        print(f"\n[*] Sending to AI Gateway...")
        print("    (may take 10-30s)")
        t2 = time.time()
        result = analyze_retrospective(frames, games, retro_minutes, input_summary, system_summary)
        ai_time = time.time() - t2

        print(f"\n{'='*60}")
        print("   AI RESPONSE -- RETROSPECTIVE")
        print(f"   (AI: {ai_time:.1f}s | {len(frames)} frames)")
        print(f"{'='*60}")
        print()
        print(result)
        print()

    else:
        # ==================== SINGLE CAPTURE MODE ====================
        print("\n[*] Capturing screen...")
        t1 = time.time()
        path, size = take_screenshot()
        print(f"    {path.name} | {size}KB | {time.time()-t1:.1f}s")

        print("\n[*] Sending to AI Gateway...")
        print("    (may take 5-15s)")
        t2 = time.time()
        result = analyze_single(path, games)
        ai_time = time.time() - t2

        print(f"\n{'='*60}")
        print("   AI RESPONSE")
        print(f"   (AI: {ai_time:.1f}s)")
        print(f"{'='*60}")
        print()
        print(result)
        print()

if __name__ == "__main__":
    main()
