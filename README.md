# devata-game-assist

AI-powered gaming assistant for Windows — screen capture, input logging, system monitoring, and AI analysis.

## Quick Start

```powershell
cd H:\Other\ computers\My\Laptop\Documents\GitHub\devata-game-assist\capture-screen

# Jalankan background services SEKALI saat boot:
python input_logger.py --start     # Keyboard + mouse logging
python system_monitor.py --start  # CPU/GPU/RAM monitoring
python capture_loop.py            # Screenshot every 10s

# Analyse gameplay on-demand:
python vision_monitor.py --retro 5 --input --system
```

## Architecture

```
capture-screen/
├── capture_loop.py      # Screenshot every 10s, FIFO 180 files (30 min)
├── input_logger.py     # Keyboard + mouse logging, shared via JSON
├── system_monitor.py   # CPU/GPU/RAM monitoring, shared via JSON
├── vision_monitor.py   # AI analysis via Olagon Gateway
├── screen_capture.py   # One-shot screenshot tool
├── game_monitor.py     # Fast game detection + screenshot
├── screenshots/        # Auto-cleaned by FIFO (180 max)
├── input_log.json      # Input events buffer
└── system_log.json     # System perf samples
```

## Commands

### Screen Capture
```powershell
python screen_capture.py          # Screenshot all monitors
python screen_capture.py mon1    # Monitor 1 only
python screen_capture.py list    # List recent screenshots
```

### Game Monitor
```powershell
python game_monitor.py            # Fast detect + screenshot
```

### Vision Monitor (AI Analysis)
```powershell
python vision_monitor.py                       # Single capture analysis
python vision_monitor.py --retro 5            # 5 min retrospective
python vision_monitor.py --retro --input     # + input sync
python vision_monitor.py --retro --system     # + system perf
python vision_monitor.py --retro 5 --input --system  # FULL
```

### Input Logger
```powershell
python input_logger.py --start    # Start (run once, stays in bg)
python input_logger.py --status   # Check buffer
python input_logger.py --stop     # Stop and save
```

### System Monitor
```powershell
python system_monitor.py --start       # Start (run once, stays in bg)
python system_monitor.py --status     # Latest readings
python system_monitor.py --report 5   # 5 min analysis report
python system_monitor.py --stop       # Stop
```

## Dependencies

```powershell
pip install mss pillow httpx keyboard pynput psutil wmi nvidia-ml-py
```

- `mss` — cross-platform screenshot
- `Pillow` — image resize for AI payloads
- `httpx` — AI Gateway API calls
- `keyboard` — global keypress detection
- `pynput` — mouse movement/clicks detection
- `psutil` — CPU/RAM/disk monitoring
- `wmi` — GPU info via Windows API
- `nvidia-ml-py` — NVIDIA GPU utilization/temp/VRAM

## What Gets Monitored

| Layer | Data | Interval |
|-------|------|---------|
| Screen | PNG screenshots | 10s |
| Input | Keys + mouse clicks + positions | realtime |
| System | CPU%, RAM%, GPU%, VRAM, temps | 2s |

All data stored locally. AI called on-demand only (1 request per analysis).

## Game Compatibility

Built-in game keywords:
- Forza Horizon 6 (detection, racing analysis)
- Valorant, CS2 (FPS/shooter analysis: tap/burst/spray, movement)
- Diablo, Path of Exile (ARPG analysis)
- Elden Ring, Cyberpunk, Genshin, Stardew, Descending The Woods

## AI Analysis Output

The AI receives in 1 request:
1. Up to 4 resized screenshot frames
2. Input summary (keys, clicks, mouse positions)
3. System performance summary (CPU/RAM/GPU usage, lag events, bottlenecks)

Output includes:
- Gameplay description
- Technical mistake analysis
- PC performance correlation with gameplay
- Upgrade recommendations
- Game-specific advice (racing line, fire mode, positioning)

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
