# devata-game-assist

AI-powered gaming assistant for Windows — persistent overlay, screen capture, AI analysis, and on-screen answer pointing.

## Quick Start

```powershell
cd H:\Other computers\My Laptop\Documents\GitHub\devata-game-assist\capture-screen

# Install dependencies
py -m pip install mss pillow httpx keyboard pynput psutil wmi nvidia-ml-py python-dotenv

# Create .env file in capture-screen/ folder:
# OLAGON_API_KEY=your_api_key_here

# Start Game Assist (Gemini Live style) — RECOMMENDED
python game_assist.py

# Or use AI Chat CLI
python ai_chat.py
```

## Core: game_assist.py

**Gemini Live-style persistent game assistant** with floating bubble overlay.

```
python game_assist.py              # Start with overlay + global hotkey
python game_assist.py --once "Q"  # Single question
```

**Hotkey:** `Ctrl+Shift+G` (global — works while gaming)

| Command | Description |
|---------|-------------|
| `ask <Q>` | Ask anything about your current game |
| `item` | Identify the item you're looking at |
| `solve` | Analyze and solve current puzzle |
| `what` | What's happening on screen? (auto-describe) |
| `next` | What should I do next? |
| `game` | Detect what game is playing |
| `toggle` | Show/hide bubble overlay |
| `clear` | Clear conversation context |
| `quit` | Exit |

**How it works:**
1. Floating bubble overlay always visible (bottom-right corner)
2. Press `Ctrl+Shift+G` or type question in CLI
3. AI analyzes current screen + conversation context
4. Answer appears as speech bubble on overlay
5. Conversation history preserved for context-aware answers

## ai_chat.py — Unified CLI

All capture-screen tools in one CLI with ANSI styling.

```
python ai_chat.py                    # Interactive REPL
python ai_chat.py ask "question"    # Ask AI
python ai_chat.py capture            # Screenshot
python ai_chat.py vision            # AI single frame analysis
python ai_chat.py retro [min]      # Retrospective analysis
python ai_chat.py loop              # Screenshot every 10s
python ai_chat.py log start|stop   # Input logger
python ai_chat.py sys start|status  # System monitor
python ai_chat.py game             # Game detection
python ai_chat.py overlay X Y W H  # Draw rect overlay
```

## Architecture

```
capture-screen/
├── game_assist.py      # Gemini Live style — bubble overlay (MAIN)
├── ai_chist.py         # Unified CLI with all features
├── ask_assistant.py    # Ask AI + point overlay
├── overlay_drawer.py   # Transparent shape overlay
├── overlay_annotate.py # PIL screenshot annotation
├── vision_monitor.py   # AI retrospective analysis
├── capture_loop.py    # Screenshot every 10s, FIFO 180 files
├── input_logger.py     # Keyboard + mouse logging
├── system_monitor.py   # CPU/GPU/RAM monitoring
├── screen_capture.py   # One-shot screenshot
├── game_monitor.py     # Fast game detection
├── screenshots/        # Auto-cleaned FIFO (180 max)
├── .env               # API key (local only, not in git)
├── input_log.json      # Input events buffer
└── system_log.json     # System perf samples
```

## Multi-Monitor Support

All capture uses **virtual screen** (all monitors combined):
- `mss.monitors[0]` = virtual screen spanning all monitors
- Overlay spans full virtual screen
- Coordinates 0-indexed from virtual screen top-left

**Current setup:**
- Virtual screen: 3286x1080 (origin x=-1366)
- Monitor 1 (right, primary): 1920x1080 at x=0
- Monitor 2 (left, secondary): 1366x768 at x=-1366

## Dependencies

```powershell
py -m pip install mss pillow httpx keyboard pynput psutil wmi nvidia-ml-py python-dotenv
```

| Package | Purpose |
|---------|---------|
| `mss` | Screenshot capture (virtual screen / multi-monitor) |
| `Pillow` | Image resize for AI payloads |
| `httpx` | AI Gateway API calls |
| `keyboard` / `pynput` | Global hotkey detection |
| `psutil` | CPU/RAM/disk monitoring |
| `wmi` | GPU info via Windows API |
| `nvidia-ml-py` | NVIDIA GPU utilization/temp/VRAM |
| `python-dotenv` | Load API key from `.env` |

## Environment Setup

Create `.env` file in `capture-screen/` (NOT in project root):
```
OLAGON_API_KEY=your_api_key_here
```

Get your API key from Olagon Gateway.

## AI Gateway

Uses Olagon AI Gateway: `https://gateway.olagon.site/anthropic/v1/messages`
Model: `claude-3-5-sonnet`

## System Specs (Reference)

- CPU: AMD Ryzen 7 5800X (16c/16t) @ 3.8GHz
- RAM: 32GB DDR4 3200MHz
- GPU: NVIDIA RTX 3060 12GB VRAM
- OS: Windows 11 Pro
- GPU Driver: v32.0.16.1062

## License

Copyright (c) Devata. All Rights Reserved.
