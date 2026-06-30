"""Windows 原生鼠标滚轮，兼容 Unity 游戏窗口。"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Literal

import win32api
import win32con
import win32gui

ScrollMethod = Literal["auto", "sendinput", "mouse_event", "wm_mousewheel"]

WHEEL_DELTA = 120
WM_MOUSEWHEEL = 0x020A
INPUT_MOUSE = 0
MOUSEEVENTF_WHEEL = 0x0800


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _set_cursor(screen_x: int, screen_y: int) -> None:
    win32api.SetCursorPos((screen_x, screen_y))
    time.sleep(0.05)


def _pack_wheel_lparam(screen_x: int, screen_y: int) -> int:
    return win32api.MAKELONG(screen_x & 0xFFFF, screen_y & 0xFFFF)


def _scroll_sendinput(screen_x: int, screen_y: int, direction: int) -> None:
    """direction: +1 向上滚, -1 向下滚（单次刻度）。"""
    _set_cursor(screen_x, screen_y)
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = MOUSEINPUT(
        dx=0,
        dy=0,
        mouseData=ctypes.c_uint32(WHEEL_DELTA * direction).value,
        dwFlags=MOUSEEVENTF_WHEEL,
        time=0,
        dwExtraInfo=None,
    )
    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent != 1:
        raise OSError("SendInput 滚轮失败")


def _scroll_mouse_event(screen_x: int, screen_y: int, direction: int) -> None:
    _set_cursor(screen_x, screen_y)
    win32api.mouse_event(
        win32con.MOUSEEVENTF_WHEEL,
        screen_x,
        screen_y,
        WHEEL_DELTA * direction,
        0,
    )


def _scroll_wm_mousewheel(hwnd: int, screen_x: int, screen_y: int, direction: int) -> None:
    _set_cursor(screen_x, screen_y)
    target = win32gui.WindowFromPoint((screen_x, screen_y)) or hwnd
    wparam = win32api.MAKELONG(0, WHEEL_DELTA * direction)
    lparam = _pack_wheel_lparam(screen_x, screen_y)
    win32gui.SendMessage(target, WM_MOUSEWHEEL, wparam, lparam)


def _dispatch_once(
    method: ScrollMethod,
    hwnd: int,
    screen_x: int,
    screen_y: int,
    direction: int,
) -> None:
    if method == "sendinput":
        _scroll_sendinput(screen_x, screen_y, direction)
    elif method == "mouse_event":
        _scroll_mouse_event(screen_x, screen_y, direction)
    elif method == "wm_mousewheel":
        _scroll_wm_mousewheel(hwnd, screen_x, screen_y, direction)
    else:
        raise ValueError(f"未知滚轮方式: {method}")


def scroll_wheel_clicks(
    hwnd: int,
    screen_x: int,
    screen_y: int,
    clicks: int,
    *,
    method: ScrollMethod = "auto",
    interval: float = 0.06,
) -> str:
    """
    在屏幕坐标处滚动鼠标滚轮。

    clicks > 0 : 向上滚 |clicks| 次
    clicks < 0 : 向下滚 |clicks| 次

    返回实际使用的方式名。
    """
    if clicks == 0:
        return method if method != "auto" else "sendinput"

    direction = 1 if clicks > 0 else -1
    count = abs(clicks)
    methods: list[ScrollMethod] = (
        [method]
        if method != "auto"
        else ["sendinput", "mouse_event", "wm_mousewheel"]
    )

    last_error: Exception | None = None
    for candidate in methods:
        try:
            for _ in range(count):
                _dispatch_once(candidate, hwnd, screen_x, screen_y, direction)
                time.sleep(interval)
            return candidate
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"所有滚轮方式均失败: {last_error}")
