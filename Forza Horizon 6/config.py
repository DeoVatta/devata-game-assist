"""
Game configuration — single source of truth for Forza Horizon 6.
Extensible: add new games by copying this config file.
"""
from pathlib import Path

# ── Project ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
GAME_NAME = "Forza Horizon 6"
GAME_ID   = "FH6"
VERSION    = "0.1.0"

# ── Detection ─────────────────────────────────────────────
DETECTION_INTERVAL = 2  # seconds

# Process names to check (case-insensitive match)
FORZA_PROCESS_NAMES = [
    "ForzaHorizon6",
    "ForzaHorizon5",
    "ForzaHorizon4",
    "ForzaHorizon3",
    "ForzaHorizon2",
    "ForzaHorizon",
]

# Window titles to match
FORZA_WINDOW_TITLES = [
    "Forza Horizon 6",
    "Forza Horizon 5",
    "Forza Horizon 4",
    "Forza Horizon 3",
    "Forza Horizon 2",
    "Forza Horizon",
]

# Xbox App / Game Pass store IDs (leave empty until confirmed)
FORZA_XBOX_IDS: list[str] = []

# Stream / OBS settings
OBS_HOST     = "localhost"
OBS_PORT     = 4455
OBS_PASSWORD = None  # Set password if OBS WebSocket auth is enabled
