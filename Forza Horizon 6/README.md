# Forza Horizon 6 — Game Assistant

Modular game detection & automation system for Forza Horizon 6 (Game Pass / Xbox).

## Architecture

```
Forza Horizon 6/
├── config.py              # Game-specific config (process names, window titles, IDs)
├── detection/
│   ├── __init__.py
│   ├── process.py         # Process detection via psutil
│   ├── window.py          # Window detection via Win32 API
│   ├── xbox.py            # Xbox App / Game Pass library via PowerShell
│   └── stream.py          # OBS WebSocket scene source detection
├── services/
│   └── detector.py         # Unified orchestrator (priority-based)
└── main.py                # CLI entry point
```

## Detection Sources

| Source | Method | Confidence |
|---|---|---|
| `process` | `psutil.process_iter()` — checks `ForzaHorizon*.exe` | Highest |
| `window` | Win32 `EnumWindows` + `GetWindowText` | High |
| `xbox` | PowerShell `Get-StartApps` | Medium |
| `stream` | OBS WebSocket plugin (port 4455) | Setup-dependent |

## Setup

```bash
# Python 3.14+ with psutil pre-installed
# No additional dependencies required
python main.py --help
```

## Usage

```bash
# Quick one-shot detection (exit code 0 = running, 1 = not running)
python main.py --quick

# Full report with per-source results
python main.py --sources

# Continuous monitoring with callbacks
python main.py --watch --interval 2
```

## Sample Output (Game Running)

```
Forza Horizon 6 — Detection Report (08:39:10)
──────────────────────────────────────────────────
  ✓ Process (psutil): True | count=2
  ✓ Window (Win32 API): True | 2 window(s) found
  ✓ Xbox App Library: True
  ✗ OBS WebSocket: False
──────────────────────────────────────────────────
  Overall: RUNNING
```

## Adding a New Game

1. Copy `Forza Horizon 6/` folder → e.g. `Cyberpunk 2077/`
2. Update `config.py` with new game process names, window titles, Xbox IDs
3. Modules auto-use config — no code changes needed
4. Add to `main.py` switcher / GUI selector later

## Adding a New Detection Source

1. Create `detection/mysource.py` with `detect(config) -> bool`
2. Import game config in `services/detector.py`
3. Add call in `detect_all()` — results auto-aggregate into `GameState`
