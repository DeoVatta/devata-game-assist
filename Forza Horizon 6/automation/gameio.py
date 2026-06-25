# ============================================================
#  automation/gameio.py — Window-aware capture + input wrapper
#
#  Central IO abstraction used by every automation module.
#  Mirrors FAFE gameio.py pattern exactly.
#
#  Dual-path:
#    Window found by title → PostMessage path (client-area capture + input)
#    Window not found     → SendInput path (whole-monitor capture)
#
#  Session crop: letterbox detected ONCE, cached for all chained steps.
# ============================================================

import os
import sys
import time
import threading
import ctypes
from ctypes import wintypes

from capture import (
    grab_frame, grab_window, grab_region,
    get_monitor_dims, get_client_rect, get_window_pid,
    find_game_window, set_window_active, set_process_muted,
    detect_content_rect, force_english_ime,
    post_key, post_click, post_client_click, post_scroll,
    mouse_click, mouse_scroll,
)
from detector import ScreenDetector, record_click


# ── Virtual key map ──────────────────────────────────────────
_VK_MAP = {
    "enter":    0x0D,
    "return":  0x0D,
    "esc":     0x1B,
    "escape":  0x1B,
    "space":   0x20,
    "backspace": 0x08,
    "back":    0x08,
    "x":       0x58,
    "y":       0x59,
    "w":       0x57,
    "a":       0x41,
    "s":       0x53,
    "d":       0x44,
    "up":      0x26,
    "down":    0x28,
    "left":    0x25,
    "right":   0x27,
}
_EXTENDED_VKS = frozenset({
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
    0x2D, 0x2E, 0xA3, 0xA5,
})
_KEEPALIVE_INTERVAL = 0.5  # seconds

# ── Input structures (foreground path) ───────────────────────

class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",        wintypes.WORD),
        ("wScan",     wintypes.WORD),
        ("dwFlags",   wintypes.DWORD),
        ("time",      wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", _KEYBDINPUT),
        ("_pad", ctypes.c_byte * 28),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP       = 0x0002
_KEYEVENTF_SCANCODE    = 0x0008


def _vk(key):
    return _VK_MAP.get(str(key).lower())


def _send_vk(key, key_up=False):
    """Foreground tap via SendInput — dual VK + scancode (most compatible)."""
    vk = _vk(key)
    if vk is None:
        return
    scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
    flags = _KEYEVENTF_KEYUP if key_up else 0
    if vk in _EXTENDED_VKS:
        flags |= _KEYEVENTF_EXTENDEDKEY
    inp = _INPUT(type=1, union=_INPUT_UNION(
        ki=_KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
    ))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def _send_scancode(key, key_up=False):
    """Foreground scancode injection — DirectInput / Raw Input path.
    Used for held keys (gameplay W) and grid navigation (WASD)."""
    vk = _vk(key)
    if vk is None:
        return
    scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
    flags = _KEYEVENTF_SCANCODE | (_KEYEVENTF_KEYUP if key_up else 0)
    if vk in _EXTENDED_VKS:
        flags |= _KEYEVENTF_EXTENDEDKEY
    inp = _INPUT(type=1, union=_INPUT_UNION(
        ki=_KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
    ))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


# ── Session crop cache ─────────────────────────────────────
_UNSET = object()
_SESSION_CROP_ACTIVE = False
_SESSION_CROP = _UNSET


def set_session_crop(active: bool):
    global _SESSION_CROP_ACTIVE, _SESSION_CROP
    _SESSION_CROP_ACTIVE = bool(active)
    _SESSION_CROP = _UNSET


# ── Global mute holder ──────────────────────────────────────
_MUTE_HELD = False


def set_mute_held(held: bool):
    global _MUTE_HELD
    _MUTE_HELD = bool(held)


# ── GameIO ─────────────────────────────────────────────────

class GameIO:
    """
    Per-run capture + input context.

    Auto-adapts at construction:
      - Finds game window by title → PostMessage path
      - Falls back → whole-monitor + SendInput path

    Attributes:
      hwnd      : window HWND (or None)
      width     : capture width in px
      height    : capture height in px
      cap_left  : capture origin x (for foreground path)
      cap_top   : capture origin y
      bg        : True if PostMessage path active
      win_capture: True if using PrintWindow capture (vs. grab_region)

    Usage:
        io = GameIO(cfg, log_cb)
        frame = io.grab()
        io.press("w", post_wait=0.5)
        io.click(fx, fy)
        io.mute(cfg); io.start_keepalive(stop_cb, cfg)
        io.cleanup()
    """

    def __init__(self, cfg: dict, log_cb=None):
        self._log = log_cb or (lambda m: None)
        self._lang = cfg.get("lang", "en")
        self.monitor_index = cfg.get("monitor_index", 1)
        self._cap_method = cfg.get("background_capture", "window")
        self._ka_stop = threading.Event()
        self._held: dict = {}
        self._muted_pid: int = None

        # Defaults: legacy whole-monitor path
        mw, mh, ml, mt = get_monitor_dims(self.monitor_index)
        self.width, self.height = mw, mh
        self.cap_left, self.cap_top = ml, mt
        self.hwnd: int = None
        self.bg: bool = False
        self.win_capture: bool = False
        self._crop = None   # letterbox crop: (x, y, w, h) in client px
        self._crop_x = 0
        self._crop_y = 0

        if cfg.get("background_input", True):
            title = cfg.get("background_window_title", "Forza Horizon 6")
            hwnd = find_game_window(title)
            if hwnd:
                rect = get_client_rect(hwnd)
                if rect:
                    self.hwnd = hwnd
                    self.bg = True
                    self.cap_left, self.cap_top, self.width, self.height = rect
                    self.win_capture = (self._cap_method == "window")
                    self._log(f"[GameIO] Background input ON — {self.width}x{self.height}")
                    if self.win_capture:
                        self._log(f"[GameIO] Using PrintWindow capture")
                    if cfg.get("crop_letterbox", True):
                        self._detect_letterbox()

    # ── Capture ──────────────────────────────────────────────

    def _grab_raw(self):
        """Raw frame, BEFORE letterbox crop."""
        if self.win_capture:
            f = grab_window(self.hwnd)
            if f is not None:
                return f
        if self.bg:
            r = get_client_rect(self.hwnd)
            if r:
                return grab_region(*r)
        return grab_frame(self.monitor_index)

    def grab(self):
        """Current frame: client area (background) or whole monitor.
        Applies letterbox crop so detection sees only the content area."""
        f = self._grab_raw()
        if f is not None and self._crop is not None:
            cx, cy, cw, ch = self._crop
            fh, fw = f.shape[:2]
            if cy + ch <= fh and cx + cw <= fw:
                f = f[cy:cy + ch, cx:cx + cw]
        return f

    def _apply_crop(self, rect):
        if not rect:
            return False
        cx, cy, cw, ch = rect
        if cw <= 0 or ch <= 0:
            return False
        self._crop = rect
        self._crop_x, self._crop_y = cx, cy
        self.width, self.height = cw, ch
        return True

    def _detect_letterbox(self):
        """Detect black bars ONCE at start. Session-cached across chained steps."""
        global _SESSION_CROP
        if _SESSION_CROP_ACTIVE and _SESSION_CROP is not _UNSET:
            self._apply_crop(_SESSION_CROP)
            return
        try:
            raw = self._grab_raw()
        except Exception:
            raw = None
        rect = detect_content_rect(raw) if raw is not None else None
        if _SESSION_CROP_ACTIVE:
            _SESSION_CROP = rect
        if self._apply_crop(rect):
            self._log(f"[GameIO] Letterbox crop: {self.width}x{self.height}")

    # ── Keys ─────────────────────────────────────────────────

    def press(self, key, post_wait=0.0, scancode=False):
        """Tap a key. Background → PostMessage; foreground → SendInput (dual or scancode)."""
        if self.bg:
            vk = _vk(key)
            if vk is not None:
                ext = vk in _EXTENDED_VKS
                post_key(self.hwnd, vk, key_up=False, extended=ext)
                time.sleep(0.05)
                post_key(self.hwnd, vk, key_up=True, extended=ext)
        elif scancode:
            _send_scancode(key, False)
            time.sleep(0.05)
            _send_scancode(key, True)
        else:
            _send_vk(key, False)
            time.sleep(0.05)
            _send_vk(key, True)
        if post_wait:
            time.sleep(post_wait)

    def hold_press(self, key):
        """Keydown for sustained hold (~30ms repeat). Background uses PostMessage
        with auto-repeat bit; foreground uses scancode path."""
        if self.bg:
            vk = _vk(key)
            if vk is not None:
                post_key(self.hwnd, vk, key_up=False,
                         extended=vk in _EXTENDED_VKS,
                         repeat=self._held.get(key, False))
                self._held[key] = True
        else:
            _send_scancode(key, False)

    def release(self, key):
        """Release a held key."""
        if self.bg:
            vk = _vk(key)
            if vk is not None:
                post_key(self.hwnd, vk, key_up=True,
                         extended=vk in _EXTENDED_VKS)
        else:
            _send_vk(key, True)
            _send_scancode(key, True)
        self._held.pop(key, None)

    def hold_release_all(self):
        """Release all held keys. Call on stop."""
        for key in list(self._held.keys()):
            self.release(key)

    # ── Mouse ────────────────────────────────────────────────

    def click(self, fx, fy, post_wait=0.5):
        """Left-click at frame-local (fx, fy). Click coords are in the
        possibly-cropped detection frame — add crop origin back to land
        on the real client pixel."""
        # Record for debug overlay
        record_click(int(fx), int(fy))
        cx, cy = self._crop_x, self._crop_y
        if self.bg and self.win_capture:
            post_client_click(self.hwnd, int(fx) + cx, int(fy) + cy, post_wait)
        elif self.bg:
            r = get_client_rect(self.hwnd) or (self.cap_left, self.cap_top, self.width, self.height)
            post_click(self.hwnd, int(fx) + cx + r[0], int(fy) + cy + r[1], post_wait)
        else:
            mouse_click(fx, fy, self.cap_left, self.cap_top, post_wait)

    def scroll(self, notches, post_wait=0.1):
        if self.bg:
            post_scroll(self.hwnd, notches, post_wait)
        else:
            mouse_scroll(notches, post_wait)

    # ── Keep-alive / mute / cleanup ──────────────────────────

    def start_keepalive(self, stop_cb, cfg):
        """Re-assert 'active' to the window every 0.5s so it doesn't auto-pause
        while unfocused. No-op in foreground path."""
        if not self.bg or not cfg.get("background_fake_focus", True):
            return
        self._log("[GameIO] Keep-alive active")

        def _loop():
            while not self._ka_stop.is_set() and not stop_cb():
                set_window_active(self.hwnd)
                time.sleep(_KEEPALIVE_INTERVAL)

        threading.Thread(target=_loop, daemon=True).start()

    def stop_keepalive(self):
        self._ka_stop.set()

    def mute(self, cfg):
        """Mute game audio. Session-owned mute (set_mute_held) takes precedence."""
        global _MUTE_HELD
        if _MUTE_HELD:
            return False
        if cfg.get("mute_game", False) and self.hwnd:
            pid = get_window_pid(self.hwnd)
            if pid and set_process_muted(pid, True):
                self._muted_pid = pid
                self._log("[GameIO] Game muted")
                return True
        return False

    def unmute(self):
        global _MUTE_HELD
        if _MUTE_HELD:
            return
        if self._muted_pid:
            set_process_muted(self._muted_pid, False)
            self._muted_pid = None

    def cleanup(self):
        """Stop keep-alive, release keys, unmute. Call in finally/cleanup."""
        self.stop_keepalive()
        self.hold_release_all()
        self.unmute()
