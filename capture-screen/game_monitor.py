# game_monitor.py
# Fast game detection + screenshot in ONE command
# Usage: python game_monitor.py [game_name]

import mss
import os
import sys
import subprocess
import json
from datetime import datetime
from pathlib import Path

# Fix Unicode for Windows console
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = Path(__file__).parent
SCREENSHOT_DIR = SCRIPT_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

MAX_SCREENSHOTS = 20

GAME_KEYWORDS = {
    "descend": ["DescendTheWoods", "Descending The Woods", "descendingthewoods"],
    "taskbarhero": ["TaskBarHero", "taskbarhero", "TBH"],
    "diablo": ["Diablo", "diablo", "D2R"],
    "poe": ["Path of Exile", "pathofexile", "poe"],
    "stardew": ["Stardew", "stardew"],
    "elden": ["Elden Ring", "eldenring"],
    "cyberpunk": ["Cyberpunk", "cyberpunk"],
    "witcher": ["Witcher", "witcher"],
    "torchlight": ["Torchlight", "torchlight"],
    "grim": ["Grim Dawn", "grimdawn"],
    "genshin": ["Genshin", "genshin"],
    "genshin": ["Zenless", "zenless"],
    "roblox": ["Roblox", "roblox"],
}

def cleanup_fifo():
    files = sorted(
        [f for f in SCREENSHOT_DIR.iterdir() if f.suffix == '.png'],
        key=lambda f: f.stat().st_mtime
    )
    removed = 0
    while len(files) > MAX_SCREENSHOTS:
        old = files.pop(0)
        old.unlink()
        removed += 1
    return removed

def get_running_games():
    """Fast process check using tasklist"""
    try:
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

        active_games = []
        for p in processes:
            name = p.get('Name', '')
            title = p.get('MainWindowTitle', '')

            # Check if it's a known game
            for game_key, keywords in GAME_KEYWORDS.items():
                if any(k.lower() in (name + title).lower() for k in keywords):
                    active_games.append({
                        'name': name,
                        'title': title,
                        'game': game_key
                    })
                    break

        return active_games
    except Exception as e:
        return []

def take_screenshot():
    """Fast screenshot using mss"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{timestamp}.png"
    filepath = SCREENSHOT_DIR / filename

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        sct_img = sct.grab(monitor)
        mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(filepath))

    size_kb = filepath.stat().st_size // 1024
    return filepath, size_kb, sct_img.width, sct_img.height

def save_status(games, screenshot_path):
    """Save current status to JSON for fast reading"""
    status_file = SCRIPT_DIR / "status.json"
    status = {
        "timestamp": datetime.now().isoformat(),
        "games_running": games,
        "screenshot": str(screenshot_path),
        "screenshot_file": screenshot_path.name
    }
    with open(status_file, 'w') as f:
        json.dump(status, f, indent=2)
    return status_file

def main():
    print("=" * 50)
    print("   GAME MONITOR - Fast Detection")
    print("=" * 50)

    # Step 1: Fast process check
    print("\n[1] Scanning processes...")
    start = datetime.now()
    games = get_running_games()
    scan_time = (datetime.now() - start).total_seconds() * 1000

    if games:
        print(f"    Found {len(games)} game(s) in {scan_time:.0f}ms")
        for g in games:
            print(f"    | {g['title']} ({g['game']})")

        # Step 2: Auto screenshot if game detected
        print("\n[2] Taking screenshot...")
        path, size, w, h = take_screenshot()
        print(f"    {path.name} | {size}KB | {w}x{h}px")

        # Step 3: Cleanup old
        removed = cleanup_fifo()
        if removed > 0:
            print(f"    [-] Cleaned {removed} old screenshots")

        # Step 4: Save status
        status_file = save_status(games, path)
        print(f"\n[3] Status saved to: {status_file.name}")

        print(f"\n>>> DRAG TO CLAUDE: {path}")
    else:
        print(f"    No games detected ({scan_time:.0f}ms)")
        save_status([], None)
        print("\n    No screenshot taken.")

    print("\n" + "=" * 50)

if __name__ == "__main__":
    main()
