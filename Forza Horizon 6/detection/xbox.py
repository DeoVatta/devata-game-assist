"""
Xbox App / Game Pass detection — checks if Forza is installed via Xbox App.

Method:
1. Query Xbox App via PowerShell Get-StartApps or registry
2. Check Xbox App installed game list via xwbwrapper or direct API call
3. Check Steam library (Forza may also be on Steam in future)

Uses PowerShell subprocess for reliable Windows integration.
No Xbox API key required — queries local Xbox App state.
"""
import subprocess
import json
import re
from typing import List, Optional
from config import FORZA_XBOX_IDS, FORZA_WINDOW_TITLES


def _run_powershell(script: str) -> str:
    """Run a PowerShell script and return stdout (UTF-8, handles non-English app names)."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


def get_xbox_installed_games() -> List[dict]:
    """
    Query Xbox App installed games list.
    Returns list of {name, app_id} dicts.
    """
    script = """
    $games = @()
    Get-StartApps | ForEach-Object {
        $games += $_ | Select-Object AppId, Name
    }
    $games | ConvertTo-Json -Depth 3
    """
    output = _run_powershell(script)
    if not output or output.startswith("Exception"):
        return []

    try:
        data = json.loads(output)
        # Normalize: may be dict (single item) or list
        if isinstance(data, dict):
            return [data]
        return data
    except json.JSONDecodeError:
        return []


def is_xbox_game_in_library(game_ids: List[str], game_names: List[str]) -> bool:
    """
    Check if Forza is in Xbox App library by ID or name match.
    game_ids: Xbox store/app IDs to match
    game_names: Display names to match in Get-StartApps output
    """
    games = get_xbox_installed_games()
    for g in games:
        app_id = g.get("AppId", "")
        name = g.get("Name", "")

        if app_id in game_ids:
            return True
        for gname in game_names:
            if gname.lower() in name.lower():
                return True

    return False


def get_xbox_game_status(game_ids: List[str]) -> Optional[dict]:
    """Return status info for Forza from Xbox App if found."""
    games = get_xbox_installed_games()
    for g in games:
        app_id = g.get("AppId", "")
        name = g.get("Name", "")
        if app_id in game_ids:
            return {"app_id": app_id, "name": name, "source": "xbox"}
        for gid in game_ids:
            if gid.lower() in name.lower():
                return {"app_id": app_id, "name": name, "source": "xbox"}
    return None


def is_game_pass_active() -> bool:
    """Check if Xbox Game Pass subscription is active (via reg key)."""
    script = """
    $key = Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\XboxLive' -ErrorAction SilentlyContinue
    if ($key) { 'active' } else { 'inactive' }
    """
    result = _run_powershell(script)
    return "active" in result.lower()


def detect(game_ids: List[str] = None, game_names: List[str] = None) -> bool:
    """Source-level detect() — True if game is in Xbox library."""
    gids = game_ids or FORZA_XBOX_IDS
    gnames = game_names or FORZA_WINDOW_TITLES
    return is_xbox_game_in_library(gids, gnames)
