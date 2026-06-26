# devata-game-assist

AI-powered gaming assistant for Windows — screen capture, input logging, system monitoring, AI analysis, and on-screen answer pointing.

## Quick Start

```powershell
cd H:\Other computers\My Laptop\Documents\GitHub\devata-game-assist\capture-screen

# Setup: install dependencies
py -m pip install mss pillow httpx keyboard pynput psutil wmi nvidia-ml-py python-dotenv

# Copy and configure .env
# copy .env.example .env  (then add your OLAGON_API_KEY)

# Jalankan background services SEKALI saat boot:
python input_logger.py --start     # Keyboard + mouse logging
python system_monitor.py --start    # CPU/GPU/RAM monitoring
python capture_loop.py             # Screenshot every 10s

# Analyse gameplay on-demand:
python vision_monitor.py --retro 5 --input --system

# Ask AI to point at things on screen (Ctrl+Shift+A hotkey):
python ask_assistant.py --hotkey
```

## Architecture

```
capture-screen/
├── capture_loop.py      # Screenshot every 10s, FIFO 180 files (30 min)
├── input_logger.py      # Keyboard + mouse logging, shared via JSON
├── system_monitor.py    # CPU/GPU/RAM monitoring, shared via JSON
├── vision_monitor.py    # AI retrospective analysis
├── ask_assistant.py     # Ask AI questions + point at things on screen
├── overlay_drawer.py    # Transparent overlay for drawing shapes
├── screen_capture.py    # One-shot screenshot tool
├── game_monitor.py      # Fast game detection + screenshot
├── screenshots/         # Auto-cleaned by FIFO (180 max)
├── .env                 # API key (local only, not in git)
├── input_log.json       # Input events buffer
└── system_log.json      # System perf samples
```

## Commands

### Screen Capture
```powershell
python screen_capture.py          # Screenshot all monitors
python screen_capture.py mon1     # Monitor 1 only
python screen_capture.py list     # List recent screenshots
```

### Game Monitor
```powershell
python game_monitor.py            # Fast detect + screenshot
```

### Vision Monitor (AI Retrospective Analysis)
```powershell
python vision_monitor.py                       # Single capture analysis
python vision_monitor.py --retro 5            # 5 min retrospective
python vision_monitor.py --retro --input     # + input sync
python vision_monitor.py --retro --system    # + system perf
python vision_monitor.py --retro 5 --input --system  # FULL
```

### Ask Assistant (Point at Things)
```powershell
python ask_assistant.py --once    # Ask once, show overlay, exit
python ask_assistant.py --hotkey  # Register Ctrl+Shift+A, stay running

# Hotkey mode:
# 1. Press Ctrl+Shift+A anywhere (game or desktop)
# 2. Type your question
# 3. AI marks the answer with a green rectangle or circle
```

### Input Logger
```powershell
python input_logger.py --start    # Start (run once, stays in bg)
python input_logger.py --status   # Check buffer
python input_logger.py --stop    # Stop and save
```

### System Monitor
```powershell
python system_monitor.py --start      # Start (run once, stays in bg)
python system_monitor.py --status    # Latest readings
python system_monitor.py --report 5   # 5 min analysis report
python system_monitor.py --stop      # Stop
```

## Dependencies

```powershell
py -m pip install mss pillow httpx keyboard pynput psutil wmi nvidia-ml-py python-dotenv
```

| Package | Purpose |
|---------|---------|
| `mss` | Cross-platform screenshot capture |
| `Pillow` | Image resize for AI payloads |
| `httpx` | AI Gateway API calls |
| `keyboard` | Global keypress detection |
| `pynput` | Mouse movement/clicks detection |
| `psutil` | CPU/RAM/disk monitoring |
| `wmi` | GPU info via Windows API |
| `nvidia-ml-py` | NVIDIA GPU utilization/temp/VRAM |
| `python-dotenv` | Load API key from `.env` file |

## Environment Setup

Create `.env` file in `capture-screen/`:
```
OLAGON_API_KEY=your_api_key_here
```

Get your API key from Olagon Gateway.

## What Gets Monitored

| Layer | Data | Interval |
|-------|------|----------|
| Screen | PNG screenshots | 10s |
| Input | Keys + mouse clicks + positions | realtime |
| System | CPU%, RAM%, GPU%, VRAM, temps | 2s |

All data stored locally. AI called on-demand only (1 request per analysis).

## Ask Assistant — Point at Things

The `ask_assistant.py` lets you ask questions about what's on screen and AI will **mark the answer directly on screen** with a breathing shape:

**Example use cases:**
- Open inventory → ask "mana item bernama Shadow Dagger?" → green rect appears on the item
- Open map → ask "dimana lokasi dungeon?" → green circle appears on the map marker
- Any screen → ask "item mana yang bisa meningkatkan damage?" → AI marks relevant items

**How it works:**
1. Press `Ctrl+Shift+A` or run with `--once`
2. Type your question
3. Screen is captured and sent to AI with coordinates instruction
4. AI returns structured response: shape type (rect/circle), pixel coordinates, label, color
5. Transparent overlay draws the shape with breathing animation for 8 seconds

**Shape rules:**
- `rect` — for boxes, cards, inventory slots, item icons
- `circle` — for orbs, gems, map markers, circular icons

**Color codes:**
- `green` — correct/yes/found
- `yellow` — warning/caution
- `red` — wrong/not found/off
- `blue` — info/neutral

## Game Compatibility

Built-in game keywords:
- Forza Horizon 6 (detection, racing analysis)
- Valorant, CS2 (FPS/shooter analysis: tap/burst/spray, movement)
- Diablo, Path of Exile (ARPG analysis)
- Elden Ring, Cyberpunk, Genshin, Stardew, Descending The Woods

## AI Analysis Output

Retrospective mode (`--retro`) sends in 1 request:
1. Up to 4 resized screenshot frames
2. Input summary (keys, clicks, mouse positions)
3. System performance summary (CPU/RAM/GPU usage, lag events, bottlenecks)

Output includes:
- Gameplay description
- Technical mistake analysis
- PC performance correlation with gameplay
- Upgrade recommendations
- Game-specific advice (racing line, fire mode, positioning)

Ask mode sends current screen + question:
- AI returns coordinates + shape of the answer
- Overlay draws the shape on screen

## AI Gateway

Uses Olagon AI Gateway: `https://gateway.olagon.site/anthropic/v1/messages`
Model: `claude-3-5-sonnet`

## System Specs (Reference)

- CPU: AMD Ryzen 7 5800X (16c/16t) @ 3.8GHz
- RAM: 32GB DDR4 3200MHz
- GPU: NVIDIA RTX 3060 12GB VRAM
- OS: Windows 11 Pro
- GPU Driver: v32.0.16.1062
- Storage: C: 236GB SSD | D: 684GB SSD

## License

Copyright (c) Devata. All Rights Reserved.
