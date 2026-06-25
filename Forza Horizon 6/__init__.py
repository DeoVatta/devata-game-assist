# ============================================
# Forza Horizon 6 — Game Assistant
# ============================================
# Modular game detection & automation for Forza Horizon 6
# Supports: Process detection, Window detection,
#            Xbox App detection, OBS stream detection
# ============================================

GAME_NAME = "Forza Horizon 6"
GAME_ID = "FH6"
VERSION = "0.1.0"

# Detection polling interval (seconds)
DETECTION_INTERVAL = 2

# Known process names for FH6 and previous versions
FORZA_PROCESS_NAMES = [
    "ForzaHorizon6",
    "ForzaHorizon5",
    "ForzaHorizon4",
    "ForzaHorizon3",
    "ForzaHorizon2",
    "ForzaHorizon",
]

# Known window titles
FORZA_WINDOW_TITLES = [
    "Forza Horizon 6",
    "Forza Horizon 5",
    "Forza Horizon 4",
    "Forza Horizon 3",
    "Forza Horizon 2",
    "Forza Horizon",
]

# Xbox App / Game Pass store IDs (can be extended)
FORZA_XBOX_IDS = [
    "ForzaHorizon6",   # placeholder — to be confirmed
]
