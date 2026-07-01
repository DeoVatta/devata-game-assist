# Task Bar Hero Helper

Automation tool for the Windows idle game [Task Bar Hero](https://store.steampowered.com/app/2194630/Task_Bar_Hero/).

> **Note:** The game itself is Chinese-language only. The helper UI has been translated to English for ease of use.

## What it does

- **Auto-Rotation** — Automatically cycles through game chapters/difficulties via portal navigation
- **Boss Box Detection** — Parses `Player.log` in real-time to detect Boss Box and Super Boss drops (ItemKey prefix 92/93)
- **Auto Open Chests** — Double-clicks at configurable screen coordinates to open blue/white boxes automatically
- **Warehouse Automation** — Manages item warehouse tabs with configurable positions
- **Mailbox Check** — Polls the in-game mailbox for new items
- **Mouse Automation** — Uses SendInput/mouse_event/PostMessage (auto-falls back to PostMessage when UIPI blocks input, e.g. game running as admin)
- **Statistics Tracking** — Logs box counts, boss drops, rotation cycles, and session time

## Project Structure

```
task-bar-hero/
├── helper/                   # Main Python GUI (tkinter)
│   ├── app.py                # Main window — translated to English
│   ├── tbh_helper/           # Core engine modules
│   │   ├── engine.py         # RotatorEngine — main loop thread
│   │   ├── rotator.py        # MapRotator — stage switching
│   │   ├── log_watcher.py    # LogTailWatcher — Player.log parser
│   │   ├── portal.py         # PortalNavigator — game UI navigation
│   │   ├── profile.py        # PortalProfile YAML config
│   │   ├── mouse.py          # click_at() — 3 fallback methods
│   │   ├── chest_open.py     # open_chest() — double-click automation
│   │   ├── window.py         # Game window detection + DPI awareness
│   │   ├── anchor.py         # AnchorRect — coordinate transform
│   │   └── scroll.py         # scroll_wheel_clicks()
│   ├── requirements.txt
│   └── profiles/
│       └── portal_profile.default.yaml
├── drop-tool/                # Frida-based drop prediction tool
│   ├── drop_items_gui.exe
│   └── drop_items_info_v4.js  # Reverses Unity ACTk ObscuredInt
└── reverse-engineering/       # Security research (IL2Cpp + ACTk bypass)
```

## Setup

### 1. Install Python dependencies

```powershell
cd helper
pip install -r requirements.txt
```

Required packages: `mss`, `pillow`, `pyautogui`, `pywin32`, `pyyaml`, `psutil`

### 2. Configure

Copy `config.default.yaml` to `config.yaml` and update paths:

```yaml
game:
  process_name: taskbarhero.exe
log:
  path: '%LOCALAPPDATA%/../LocalLow/TesseractStudio/TaskbarHero/Player.log'
```

### 3. Capture game window

1. Run `python app.py`
2. Click **Capture Window** (Setup tab)
3. Click the Task Bar Hero game window
4. Configure portal positions, chest coordinates, warehouse tabs as needed

### 4. Run rotation

1. Start the game and enter any portal/chapter
2. Set stage list in **Stage** tab (Normal 1-1 through Nightmare 1-9 available)
3. Click **Start** in **Control** tab
4. Use **Stop** to halt

## Stage Format

Stages are formatted as `{difficulty} {chapter}-{stage}`:
- Difficulties: `Normal`, `Hard`, `Expert`, `Nightmare`
- Examples: `Normal 1-1`, `Hard 2-3`, `Expert 5-7`, `Nightmare 1-9`

## Portal Profile

Positions are saved per profile in `profiles/portal_profile.yaml`. Default stages:

```
Normal 1-1 → Normal 1-9
Hard 1-1 → Hard 1-9
Expert 1-1 → Expert 1-9
Nightmare 1-1 → Nightmare 1-9
```

## Drop Tool (Frida)

The `drop-tool/` folder contains a Frida-based tool that predicts upcoming item drops by reading encrypted game memory (Unity ACTk `ObscuredInt`). Run `drop_items_gui.exe` alongside the game for a 30-item upcoming drop queue.

> The Frida script (`drop_items_info_v4.js`) is for security research purposes only.

## Requirements

- Windows 10/11
- Python 3.10+
- Game must be running (not minimized to tray)
- `Player.log` must be accessible (game must have been played at least once to generate the log file)
