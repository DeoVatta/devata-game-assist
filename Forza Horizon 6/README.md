# Forza Horizon 6 — Game Assistant

Modular game automation system for Forza Horizon 6 (Game Pass / Xbox).

> Architecture ported from FAFE (Forza Automation Framework Extended).
> Supports: detection, AFK race, auto mastery unlock, auto spin wheel, auto buy.

## Architecture

```
Forza Horizon 6/
├── config.py              # Game config + config.json persistence
├── main.py                # CLI entry point (detection + automation)
├── detection/             # Game detection sources
│   ├── process.py         # psutil process scan
│   ├── window.py          # Win32 window enumeration
│   ├── xbox.py           # Xbox App / Game Pass PowerShell query
│   └── stream.py          # OBS WebSocket scene source detection
├── capture/               # Screen capture engine
│   ├── capture.py         # MSS + PrintWindow + letterbox detection
│   └── __init__.py
├── detector/              # Template matching engine
│   ├── detector.py        # ROI + matchTemplate + OCR (33 UI states)
│   └── __init__.py
├── automation/            # Automation modules
│   ├── gameio.py          # Window-aware dual-path IO wrapper
│   ├── race.py           # AFK race loop
│   ├── mastery.py         # Keyboard-driven mastery tree
│   ├── wheelspin.py      # Auto spin wheel
│   ├── buy.py            # Auto buy car
│   └── __init__.py
├── services/
│   └── detector.py        # Unified detection orchestrator
└── templates/             # Template images + grid specs
    ├── built-in/          # Reference 4K templates (cross-resolution)
    ├── en/                # English UI templates
    │   ├── race/built-in/
    │   ├── wheelspin/built-in/
    │   ├── buy/built-in/
    │   └── mastery_full/
    └── cht/               # Traditional Chinese UI templates (same structure)
```

## Dependencies

```bash
pip install opencv-python numpy mss psutil
pip install pycaw                # per-app audio mute (optional)
pip install onnxruntime          # RapidOCR backend (optional)
pip install rapidocr_onnxruntime # OCR confirmation (optional)
```

Python 3.10+ required. Tested on Python 3.14-compatible code paths.

## Setup

1. **Capture templates** at your resolution (recommended: 1920×1080 or native):
   - Place PNG templates in `templates/en/` or `templates/cht/`
   - See `templates/built-in/` for required template names
   - Use OpenCV `selectROI` or FAFE's `CaptureSession` for interactive capture

2. **Configure** `config.json` (auto-created on first run):
   ```json
   {
     "lang": "en",
     "background_input": true,
     "background_window_title": "Forza Horizon 6",
     "toggle_key": "f9",
     "mute_game": true
   }
   ```

3. **Run detection first** to verify the game is found:
   ```bash
   python main.py --quick
   python main.py --sources
   ```

## Usage

### Detection

```bash
# Quick one-shot (exit code 0 = running, 1 = not running)
python main.py --quick

# Full per-source report
python main.py --sources

# Continuous monitoring
python main.py --watch --interval 2
```

### Automation Commands

```bash
# AFK race loop
python main.py race --max 10      # stop after 10 races
python main.py race                # unlimited

# Auto-unlock mastery tree (12B-STi or any car)
python main.py mastery --max 5    # process 5 cars
python main.py mastery             # unlimited (all cars in garage)

# Auto spin wheel
python main.py wheelspin --max 50          # 50 spins
python main.py wheelspin --type super       # super wheelspin (default)
python main.py wheelspin --type normal      # normal wheelspin
python main.py wheelspin --type super --max 100

# Auto buy specific car
python main.py buy --max 20     # buy 20 cars
python main.py buy               # unlimited
```

### Stop Automation

Press **F9** (default toggle key) — uses `GetAsyncKeyState` polling so it works even while holding W during race automation.

## Detection Sources

| Source | Method | Confidence |
|---|---|---|
| `process` | `psutil.process_iter()` | Highest |
| `window` | Win32 `EnumWindows` + `GetWindowText` | High |
| `xbox` | PowerShell `Get-StartApps` | Medium |
| `stream` | OBS WebSocket source scan | Setup-dependent |

## Automation Details

### Race Automation

Template-gated loop:
```
detect(start_menu) → Enter → wait(4s blind) → hold W → detect(restart) → X → Enter → loop
```

Optional 8-step menu navigation when templates are captured: main menu → Creative Hub → EventLab → Play Event → My History → Race Type → Car → Start screen.

### Mastery Automation

Fully keyboard-driven (zero detection). WASD navigates 4×4 mastery grid from saved path file. Resolution-independent.

```
Per car: Enter → Ride → cutscene ESC → Down+Enter × 2 → unlock grid (WASD+Enter) → ESC×2 → sort
```

### Wheelspin Automation

Detection-gated at every transition:
```
click tile → spin starts
  → best-effort skip fast-forward
  → wait_for(collect) → Enter (collect all 3 prizes)
  → inner loop: detect(duplicate) → Enter (up to 3 dups)
  → check for final spin
```

### Buy Automation

Macro: `Space → Down → Enter × 3` on Car Detail screen.

Optional entry/exit navigation with templates.

## Window-Aware IO (Background Mode)

When `background_input=true` and the game window is found:
- **Capture**: client-area via `PrintWindow` (works even if occluded)
- **Input**: `PostMessage` (no focus required)
- **Keep-alive**: 0.5s tick prevents auto-pause while unfocused
- **Letterbox**: detected once at start, session-cached

When the window is not found → falls back to whole-monitor + `SendInput`.

## Dual-Input Compatibility

Every key press sends both VK and scancode via `SendInput`:
- Some games read VK path (`WM_KEYDOWN` / `GetAsyncKeyState`)
- Others read DirectInput scancode path
- Populating both is the most compatible approach.

## Adding a New Game

1. Copy `Forza Horizon 6/` → e.g. `Cyberpunk 2077/`
2. Update `config.py` with new process names, window titles, IDs
3. Update `templates/` with new game templates
4. (Optional) customize `detector/detector.py` with game-specific UI states

## Adding a New Automation Module

1. Create `automation/mymodule.py`:
   ```python
   from automation import GameIO, set_session_crop, set_mute_held
   def run(cfg, stop_event, log_cb, status_cb, **kwargs):
       io = GameIO(cfg, log_cb)
       set_session_crop(True)
       io.mute(cfg); set_mute_held(True)
       io.start_keepalive(lambda: stop_event.is_set(), cfg)
       # ... your automation logic ...
       io.cleanup()
   ```
2. Add to `main.py` CLI switcher
3. Capture templates for your game

## Sample Output

```
==================================================
  Forza Horizon 6 — Race Automation
==================================================
  Config: background_input=True
  Window: Forza Horizon 6
  Toggle key: f9
  Press f9 to stop
==================================================

  Template: start_menu (scale=0.50)
  Template: restart_menu (scale=0.50)
  [Race] Race loop started
  [Race] Waiting for start_menu
  Detected: start_menu (87%)
    → Enter (start race)
    → Holding W (driving blind)
    → Waiting for race to finish
  Race #1 complete
```
