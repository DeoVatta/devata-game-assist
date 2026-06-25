# FAFE — Forza Automation Framework Extended

> Reverse engineering analysis of `C:/Forza Mod/FAFE/FAFE_dist/`

## Project Structure

```
FAFE_dist/
├── _internal/
│   ├── detector.py      # 982 lines — template matching engine
│   ├── capture.py       # 1339 lines — capture/input engine
│   ├── config.py        # 410 lines — settings + DPI scaling
│   ├── gameio.py        # 360 lines — window-aware dual-path IO
│   └── app_lang.py      # ~1000 lines — bilingual i18n (en/zh-tw)
├── automation/
│   ├── race.py          # AFK race loop
│   ├── mastery.py       # Keyboard-driven mastery tree unlock
│   ├── wheelspin.py     # Auto spin wheel
│   ├── buy.py           # Auto buy specific car
│   └── delete_cars.py   # Delete used cars
├── ui/
│   ├── main_window.py   # CTkTabview GUI
│   ├── overlay.py       # Always-on-top status overlay
│   ├── setup_panel.py   # Template capture UI
│   └── grid_widget.py   # 4x4 node picker
└── config.json          # User settings (60+ options)
```

## Core Architecture

### detector.py — Template Matching Engine

- **33 named UI states**: `start_menu`, `racing`, `wheelspin_duplicate`, `mastery_ride_car`, etc.
- **ROI system**: each state has `(x, y, w, h)` ratio tuples — search only 5-15% of screen
- **Multi-scale matching**:
  - Structural templates: 7 scales (0.50–1.20×)
  - Text templates: 3 scales (0.80–1.10×)
  - Score: `gray * 0.62 + edge * 0.28` (Canny edges)
- **OCR confirmation**: RapidOCR (onnxruntime, 1 thread) + pytesseract fallback
- **Stability filter**: N consecutive frames before confirming state
- **Bilingual hints**: Traditional Chinese + English substrings per state
- **Adaptive ROI**: geometry-derived from capture box metadata; full-screen fallback
- **Debug export**: `_draw_debug()` marks ROI (yellow), match center (green/red), last click (magenta)
- **Letterbox fix**: menu UI anchored to centered 16:9 box; in-game HUD anchored to screen edges

### capture.py — Capture & Input Engine

- **MSS singleton per thread** + GDI handle refresh every 400 grabs
- **PrintWindow + PW_RENDERFULLCONTENT** for occluded window capture → BGRA→BGR
- **Letterbox detection** via `detect_content_rect()`: dark + flat + symmetric edge analysis
- **Background input**: `PostMessage WM_KEYDOWN/WM_KEYUP` — no focus steal
- **AttachThreadInput** for foreground forcing when needed
- **Caps Lock capture session**: OpenCV `selectROI` drag-select → save with box metadata
- **6-click node session**: mastery grid node recorder
- **Per-app mute**: pycaw `SimpleAudioVolume.SetMute(pid)`
- **IME guard**: checks HKL before switching to English (prevents CJK IME eating keystrokes)
- **Content rect**: window client area minus letterbox/pillarbox bars

### gameio.py — Window-Aware Dual-Path IO

Central abstraction used by every automation module.

```
Window found by title?
├─ YES: PostMessage path
│   ├─ Capture: client-area (PrintWindow or GDI region)
│   ├─ Input: PostMessage WM_KEYDOWN/WM_KEYUP
│   ├─ Keep-alive: 0.5s tick (WM_ACTIVATEAPP + WM_NCACTIVATE + WM_SETFOCUS)
│   │             — prevents auto-pause while unfocused
│   └─ Letterbox: detected ONCE at start, session-cached
└─ NO:  SendInput path (legacy, whole-monitor capture)
```

**Input strategy — three modes:**
- `press()`: dual VK+scancode via SendInput (VK-path + DirectInput/RawInput compatible)
- `hold_press()`: scancode-only for sustained gameplay (held W)
- `release()`: keyup for both paths

**Session crop**: `_SESSION_CROP` global caches letterbox result across chained steps.

### config.py — Settings System

- Single 4K reference template set (`built-in/`)
- Traditional Chinese + English template languages
- 60+ configurable settings with DPI-aware UI scaling
- `load()` reads fresh from `config.json` at each automation run start

## Automation Modules

### race.py — AFK Race Loop

```
Loop per race:
1. detect(start_menu)       → Enter
2. wait(4s blind)           → hold W (scancode, ~33/sec)
3. wait_for(race_end)       → detector gates this transition
4. detect(restart_menu)     → X (confirm)
5. detect(start_menu)       → Enter  (loop)
```

**Optional 7-step menu navigation** (template-gated): main menu → Creative Hub → EventLab → Play Event → My History → Solo → car → Start screen.

**Stop mechanism**: `GetAsyncKeyState(_toggle_vk) & 0x8000` polled at ~33Hz — bypasses keyboard hook entirely (hook fails under high-frequency input flood).

### mastery.py — Keyboard-Driven Mastery Tree

**Zero detection** — fully keyboard-driven. Navigates 4×4 mastery tree with WASD + Enter.

```
Columns filled TOP→BOTTOM, column-major:
col 0: row 1,2,3; col 1: row 1,2,3; …
Snake path: bottom-left cursor → grid_order cells via WASD
Grid path: saved as [[row, col], ...] — resolution-independent
```

Per car:
1. Navigate to car (WASD from previous position)
2. Enter → Ride This Car
3. Wait cutscene → ESC
4. Down×1 + Enter → Upgrade & Tuning
5. Down×7 + Enter → Car Mastery
6. Wait screen → unlock nodes (WASD + Enter)
7. ESC×2 → back
8. Up×1 + Enter → My Cars
9. X + Down×6 + Enter → sort by Recently Added

Tunable: `mastery_cutscene_wait`, `menu_tap_wait`, `mastery_grid_unlock_wait`

### wheelspin.py — Auto Spin Wheel

**Detection-gated at every transition:**

```
Stage 1: click tile → spin #1 starts
Stage 2: per spin loop:
  a) wait_for(wheelspin_skip)  → Enter (best-effort, ~200ms window)
  b) wait_for(wheelspin_collect) → Enter (collect 3 prizes + start next)
  c) inner loop: wheelspin_duplicate → Enter (up to 3 dups/spin)
Stage 3: detect(wheelspin_collect_final) → Enter → ends on main menu
```

### buy.py — Auto Buy Car

Macro: `Space → Down → Enter → Enter → Enter`

Optional 4-step entry + 4×Esc exit navigation (template-gated, best-effort).

### delete_cars.py — Delete Used Cars

Same snake grid nav as mastery. Per car: `Enter → Down×4 → Enter → Down×1 → Enter`

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Dual VK+scancode SendInput | Some games read VK path, others read DirectInput scancode path |
| GetAsyncKeyState for stop | Keyboard hook fails under 33Hz input flood from held-W thread |
| ROI-first + periodic full fallback | Full-screen matchTemplate on 5120×2160 costs ~680ms; ROI costs ~35ms |
| Template gating over timing | Critical transitions gated by detector; timing only for known-blind gaps |
| Session letterbox crop cache | First GameIO detects, later ones reuse — avoids re-detect on arbitrary screens |
| Optional nav templates | Missing template disables feature, doesn't break module |
| IME guard (HKL check) | Prevents CJK IME from eating keystrokes during layout switch |
| Keep-alive tick 0.5s | Frequent enough to prevent auto-pause; sparse enough not to interfere with menu input |
| Per-app audio mute | Mutes game process specifically, not whole system |

## Template Matching Pipeline

```
1. Grab frame (window client area or monitor)
2. Apply letterbox crop (content rect only)
3. Compute ROI from state geometry or custom override
4. ROI-only matchTemplate (TM_CCOEFF_NORMED)
   ├─ Structural: gray + Canny edge composite, 7 scales
   └─ Text: gray-only, 3 scales
5. If no custom ROI: periodic full-screen safety sweep
6. Stability filter: N consecutive frames above threshold
7. OCR confirmation (veto or confirm mode)
8. Return MatchResult or None
```

## UI System

- **main_window.py**: CustomTkinter CTkTabview with 4 tabs
- **overlay.py**: Tkinter always-on-top, WS_EX_NOACTIVATE (never steals focus), opaque rendering, draggable, dark theme
- **SetupPanel**: Template capture grid with per-key status
- **GridWidget**: 4×4 mastery node picker with 6-click recording
- **LogWidget**: Real-time scrollable log
- **app_lang.py**: Full bilingual i18n (English + Traditional Chinese)

## Adding New Automation (per FAFE pattern)

1. Add UI tab in `main_window.py` with CTk widgets
2. Create `automation/newmodule.py` using `GameIO` + `ScreenDetector`
3. Add template keys + OCR hints in `detector.py`
4. Add strings in `app_lang.py` (both en + zh-tw)
5. Capture templates via SetupPanel or manual save
