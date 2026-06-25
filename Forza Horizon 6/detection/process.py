"""
Process detection — checks if Forza Horizon process is running.
Uses psutil for cross-platform process scanning.

Method: psutil.process_iter() matching known process names.
No admin required for own process list visibility.
"""
import psutil
from typing import List, Optional
from config import FORZA_PROCESS_NAMES


def get_forza_processes(process_names: List[str]) -> List[psutil.Process]:
    """Return all running Forza processes matching given names."""
    matches = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = proc.info["name"]
            for fname in process_names:
                if fname.lower() in name.lower():
                    matches.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return matches


def is_game_running(process_names: List[str]) -> bool:
    """Return True if any Forza process is running."""
    return len(get_forza_processes(process_names)) > 0


def get_running_game_info(process_names: List[str]) -> Optional[dict]:
    """
    Return info dict for the first matching Forza process.
    Returns None if not running.
    """
    procs = get_forza_processes(process_names)
    if not procs:
        return None

    proc = procs[0]
    try:
        with proc.oneshot():
            return {
                "pid": proc.pid,
                "name": proc.name(),
                "status": proc.status(),
                "cpu_percent": proc.cpu_percent(),
                "memory_mb": proc.memory_info().rss / 1024 / 1024,
            }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def detect(process_names: List[str] = None) -> bool:
    """Source-level detect() — True if game is running."""
    names = process_names or FORZA_PROCESS_NAMES
    return is_game_running(names)
