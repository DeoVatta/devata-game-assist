"""
Window detection — checks if Forza Horizon window is active/minimized.
Uses Win32 API via ctypes / pywin32.

Method: EnumWindows + GetWindowText matching known titles.
Works for any launch method (Steam, Xbox, Epic, direct exe).
"""
import ctypes
from ctypes import wintypes
from typing import List, Optional
from config import FORZA_WINDOW_TITLES


user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
)
GetWindowText = user32.GetWindowTextW
GetWindowTextLength = user32.GetWindowTextLengthW
IsWindowVisible = user32.IsWindowVisible
GetForegroundWindow = user32.GetForegroundWindow
GetWindowThreadProcessId = user32.GetWindowThreadProcessId


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


GetWindowRect = user32.GetWindowRect
GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]


def _get_window_text(hwnd: wintypes.HWND) -> str:
    length = GetWindowTextLength(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    GetWindowText(hwnd, buf, length + 1)
    return buf.value


def _is_visible(hwnd: wintypes.HWND) -> bool:
    return bool(IsWindowVisible(hwnd))


def find_forza_windows(titles: List[str]) -> List[dict]:
    """Find all visible windows matching known Forza titles."""
    results = []

    def _enum_callback(hwnd, _):
        if not _is_visible(hwnd):
            return True

        text = _get_window_text(hwnd)
        if not text:
            return True

        for title in titles:
            if title.lower() in text.lower():
                pid = wintypes.DWORD()
                GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                rect = RECT()
                GetWindowRect(hwnd, ctypes.byref(rect))

                results.append({
                    "hwnd": int(hwnd),
                    "title": text,
                    "pid": pid.value,
                    "visible": True,
                    "rect": {
                        "x": rect.left,
                        "y": rect.top,
                        "w": rect.right - rect.left,
                        "h": rect.bottom - rect.top,
                    }
                })
        return True

    EnumWindows(EnumWindowsProc(_enum_callback), 0)
    return results


def is_game_window_active(titles: List[str]) -> bool:
    """Return True if any Forza window is the foreground window."""
    hwnd = GetForegroundWindow()
    text = _get_window_text(hwnd)
    for title in titles:
        if title.lower() in text.lower():
            return True
    return False


def get_active_forza_window(titles: List[str]) -> Optional[dict]:
    """Return window info for active Forza window, or None."""
    wins = find_forza_windows(titles)
    if not wins:
        return None
    # Return the most recently found (largest hwnd usually = top window)
    return max(wins, key=lambda w: w["hwnd"])


def detect(titles: List[str] = None) -> bool:
    """Source-level detect() — True if any Forza window exists."""
    ts = titles or FORZA_WINDOW_TITLES
    return len(find_forza_windows(ts)) > 0
