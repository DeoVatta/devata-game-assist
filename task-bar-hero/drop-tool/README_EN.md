# TaskbarHero Drop Tool 🎮

A real-time box drop prediction tool for **TaskbarHero**. Uses **Frida** to read game process memory and display upcoming NORMAL/BOSS box rewards — no server interaction required.

---

## Features

- Real-time monitoring of NORMAL and BOSS box drop queues
- Displays the next ~30 items in the drop queue (ID + name)
- Two usage modes: GUI desktop app / CLI script
- Read-only — does NOT modify game memory

## Usage

### Option 1: GUI (Recommended)

Double-click `drop_items_gui.exe` to launch.

> ⚠️ Some antivirus software may flag this as a false positive (due to Frida memory reading).

### Option 2: CLI

Requires [Frida](https://frida.re):

```bash
# Start TaskbarHero first, then attach Frida
frida -n TaskbarHero.exe -l drop_items_info_v4.js
```

### When to Use

1. After entering the game, get the **first drop box** or **switch maps**
2. The tool displays the upcoming NORMAL/BOSS box reward queue
3. Switching to a map with a different box tier refreshes the drop table

## How It Works

```
Game Process (TaskbarHero.exe)
  │
  ├── Frida injects drop_items_info_v4.js
  │
  ├── Hooks vw.jsq → reads bexl dictionary (drop queue)
  │     └── bexl stores EBoxType → List<BoxData> pre-generated queue
  │
  ├── Decodes ObscuredInt (CodeStage AntiCheat)
  │     └── decoded = (hiddenValue - field_08) ^ field_08
  │
  └── Output: item IDs, box type, queue order (~30 items)
```

Core flow:
- Map load → bexl queue populated → jsq picks item[0] from queue
- NORMAL boxes are fully client-side synchronous (no server requests) → readable locally
- Weighted random selection (EachDropOneWeight / SelectOneByClass) determines drops

## Caveats

1. **Anti-cheat risk**: Frida memory reading may be detected by the game's anti-cheat system
2. **False positives**: The GUI exe uses Frida injection, which some antivirus software may flag
3. **Map switching**: Switching to maps with the same box tier won't refresh the table; different tiers will
4. **Read-only**: This tool only reads memory — it does NOT modify any game data

## File Structure

```
├── drop_items_gui.exe       # GUI application
├── drop_items_info_v4.js    # Frida injection script (CLI)
├── 使用指南.txt             # Original usage guide (Chinese)
├── README.md                # Chinese README
└── README_EN.md             # This file (English)
```

## Dependencies

- [Frida](https://frida.re) — Dynamic instrumentation framework
- [CodeStage AntiCheat](https://assetstore.unity.com/packages/tools/input-management/antichat-toolkit-3627) — ObscuredInt encoding (reverse-engineered and decoded)
- TaskbarHero game (Unity + IL2CPP)

## Disclaimer

This tool is for educational and research purposes only. Use may violate the game's terms of service — proceed at your own risk.
