# devata-game-assist

Modular game automation & detection system for Windows games.

## Projects

| Game | Status | Description |
|---|---|---|
| [Forza Horizon 6/](Forza%20Horizon%206/README.md) | Active | Game detection via process, window, Xbox App, OBS |

## Architecture

Each game project is self-contained with:

```
<game>/
├── config.py           # Game-specific settings (process names, window titles, IDs)
├── detection/          # Pluggable detection sources
│   ├── process.py      # psutil process scan
│   ├── window.py       # Win32 window enumeration
│   ├── xbox.py         # Xbox App / Game Pass PowerShell query
│   └── stream.py       # OBS WebSocket source detection
├── services/
│   └── detector.py      # Unified orchestrator
└── main.py             # CLI entry point
```

## Adding a New Game

1. Copy existing game folder and rename
2. Update `config.py` with game-specific values
3. All detection modules auto-pick up config — no code changes required
4. Future: GUI launcher to select active game
