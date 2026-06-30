"""Capture TaskBarHero window for UI analysis."""
import sys
from ctypes import WINFUNCTYPE, windll, byref, c_int, Structure, sizeof, create_string_buffer, c_bool
from ctypes.wintypes import RECT, DWORD, HWND, LPARAM

import mss
from PIL import Image

user32 = windll.user32


class BITMAPINFOHEADER(Structure):
    _fields_ = [
        ("biSize", DWORD),
        ("biWidth", c_int),
        ("biHeight", c_int),
        ("biPlanes", c_int),
        ("biBitCount", c_int),
        ("biCompression", DWORD),
        ("biSizeImage", DWORD),
        ("biXPelsPerMeter", c_int),
        ("biYPelsPerMeter", c_int),
        ("biClrUsed", DWORD),
        ("biClrImportant", DWORD),
    ]


def find_window(title_substr: str) -> int:
    result = []

    WNDENUMPROC = WINFUNCTYPE(c_bool, HWND, LPARAM)

    def callback(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd) + 1
        buf = create_string_buffer(length * 2)
        user32.GetWindowTextW(hwnd, buf, length)
        text = buf.raw.decode("utf-16-le", errors="ignore").strip("\x00")
        if title_substr.lower() in text.lower() and user32.IsWindowVisible(hwnd):
            result.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return result[0] if result else 0


def capture_printwindow(hwnd: int, path: str) -> None:
    rect = RECT()
    user32.GetWindowRect(hwnd, byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        raise RuntimeError(f"Invalid window size: {w}x{h}")

    hdc_window = user32.GetDC(hwnd)
    hdc_mem = windll.gdi32.CreateCompatibleDC(hdc_window)
    hbmp = windll.gdi32.CreateCompatibleBitmap(hdc_window, w, h)
    windll.gdi32.SelectObject(hdc_mem, hbmp)
    user32.PrintWindow(hwnd, hdc_mem, 2)

    bmi = BITMAPINFOHEADER()
    bmi.biSize = sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0

    buf_size = w * h * 4
    buffer = create_string_buffer(buf_size)
    windll.gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buffer, byref(bmi), 0)

    img = Image.frombuffer("RGBA", (w, h), buffer.raw, "raw", "BGRA", 0, 1)
    img.save(path)

    windll.gdi32.DeleteObject(hbmp)
    windll.gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_window)
    print(f"Saved {path} ({w}x{h})")


def capture_mss(hwnd: int, path: str) -> None:
    rect = RECT()
    user32.GetWindowRect(hwnd, byref(rect))
    region = {
        "left": rect.left,
        "top": rect.top,
        "width": rect.right - rect.left,
        "height": rect.bottom - rect.top,
    }
    with mss.mss() as sct:
        shot = sct.grab(region)
        Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX").save(path)
    print(f"Saved {path} via mss {region}")


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 27468
    hwnd = find_window("TaskBarHero")
    if not hwnd:
        raise SystemExit("TaskBarHero window not found")
    print(f"HWND={hwnd}")
    capture_printwindow(hwnd, r"d:\Work\TBHhelper\game_printwindow.png")
    capture_mss(hwnd, r"d:\Work\TBHhelper\game_mss.png")
