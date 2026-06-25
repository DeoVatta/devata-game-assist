# ============================================================
#  capture.py — Screen capture + background input engine
#
#  Dual-path architecture (mirrors FAFE gameio pattern):
#    Window found → client-area capture + PostMessage input
#    Window not found → whole-monitor capture + SendInput
#
#  Dependencies (install via pip):
#    pip install opencv-python numpy mss pycaw
#    pip install onnxruntime  # for RapidOCR backend (optional)
#    pip install rapidocrapi  # or rapidocr_onnxruntime
# ============================================================

import os
import sys
import time
import ctypes
import ctypes.wintypes as wintypes
from ctypes import windll, wintypes, POINTER, Structure, Union, c_bool, c_void_p

import cv2
import numpy as np

# ── MSS singleton per thread ─────────────────────────────────
_mss_instance = None
_mss_grab_count = 0
_MSS_REFRESH_INTERVAL = 400  # refresh GDI handle every N grabs


def _get_mss():
    """Per-thread MSS singleton. Refreshes GDI handle periodically to prevent
    black-frame leak on some GPUs (notably Intel integrated)."""
    global _mss_instance, _mss_grab_count
    _mss_grab_count += 1
    if _mss_instance is None or _mss_grab_count >= _MSS_REFRESH_INTERVAL:
        from mss import mss
        _mss_instance = mss()
        _mss_grab_count = 0
    return _mss_instance


# ── Win32 constants ───────────────────────────────────────────
_USER32 = windll.user32
_KERNEL32 = windll.kernel32

WM_KEYDOWN      = 0x0100
WM_KEYUP        = 0x0101
WM_MOUSEWHEEL   = 0x020A
WM_LBUTTONDOWN  = 0x0201
WM_LBUTTONUP    = 0x0202

MK_LBUTTON      = 0x0001
PW_RENDERFULLCONTENT = 0x0008

GWL_HWNDPARENT  = -8
GWL_STYLE       = -16
GWL_EXSTYLE     = -20
WS_VISIBLE      = 0x10000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

SWP_NOACTIVATE  = 0x0010
SWP_NOZORDER    = 0x0004
SWP_SHOWWINDOW  = 0x0040

WM_ACTIVATEAPP  = 0x001C
WM_NCACTIVATE   = 0x0086
WM_ACTIVATE     = 0x0006
WM_SETFOCUS     = 0x0007

MAPVK_VK_TO_VSC = 0

# Extended key flags — scancodes that collide with numpad without the flag
_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP       = 0x0002
_KEYEVENTF_SCANCODE    = 0x0008

_EXTENDED_VKS = frozenset({
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,  # arrows + PgUp/PgDn/End/Home
    0x2D, 0x2E,                                        # Insert/Delete
    0xA3, 0xA5,                                        # R-Ctrl/R-Alt
})


# ── ctypes helpers ───────────────────────────────────────────
def _BOOL(val):
    return bool(val)

BOOL = ctypes.WINFUNCTYPE(c_bool, c_void_p)(("AnimateWindow", _USER32))


class RECT(Structure):
    _fields_ = [
        ("left",   wintypes.LONG),
        ("top",    wintypes.LONG),
        ("right",  wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]
    def width(self):
        return self.right - self.left
    def height(self):
        return self.bottom - self.top


class POINT(Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


# ── Screen dimensions ─────────────────────────────────────────

def get_monitor_dims(monitor_index: int = 1):
    """Return (width, height, left, top) for the given 1-based monitor index."""
    from mss import mss
    monitors = mss().monitors
    if monitor_index == 0:
        m = monitors[0]  # virtual combined
    elif 1 <= monitor_index <= len(monitors) - 1:
        m = monitors[monitor_index]
    else:
        m = monitors[-1]
    left   = m["left"]
    top    = m["top"]
    width  = m["width"]
    height = m["height"]
    return width, height, left, top


# ── Capture ──────────────────────────────────────────────────

def grab_frame(monitor_index: int = 1):
    """Grab the full monitor via MSS. Returns BGR numpy array or None."""
    try:
        sct = _get_mss()
        mon = sct.monitors[monitor_index]
        img = sct.grab(mon)
        frame = np.array(img)
        if frame is None or frame.size == 0:
            return None
        # BGRA → BGR
        if frame.shape[-1] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        return frame
    except Exception:
        return None


def grab_window(hwnd: int):
    """Capture window client area via PrintWindow (works for occluded windows).
    Returns BGR numpy array or None."""
    try:
        rect = RECT()
        _USER32.GetClientRect(hwnd, ctypes.byref(rect))
        w, h = rect.width(), rect.height()
        if w <= 0 or h <= 0:
            return None

        # Create compatible DC + bitmap
        hdc_screen = _USER32.GetDC(0)
        memdc = _USER32.CreateCompatibleDC(hdc_screen)
        hbitmap = _USER32.CreateCompatibleBitmap(hdc_screen, w, h)
        _USER32.SelectObject(memdc, hbitmap)

        # PrintWindow with PW_RENDERFULLCONTENT (works for DWM-composited windows)
        result = _USER32.PrintWindow(hwnd, memdc, PW_RENDERFULLCONTENT)
        if result == 0:
            # Fallback: basic PrintWindow
            _USER32.PrintWindow(hwnd, memdc, 0)

        # Copy bitmap to numpy
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize        = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth       = w
        bmi.bmiHeader.biHeight      = -h  # top-down
        bmi.bmiHeader.biPlanes      = 1
        bmi.bmiHeader.biBitCount    = 32
        bmi.bmiHeader.biCompression = 0   # BI_RGB

        buf = ctypes.create_string_buffer(w * h * 4)
        lines = _USER32.GetDIBits(
            memdc, hbitmap, 0, h, buf, ctypes.byref(bmi), 0)
        if not lines:
            # Cleanup and return None
            _USER32.DeleteObject(hbitmap)
            _USER32.DeleteDC(memdc)
            _USER32.ReleaseDC(0, hdc_screen)
            return None

        frame = np.frombuffer(buf, dtype=np.uint8).reshape((h, w, 4))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        # Cleanup
        _USER32.DeleteObject(hbitmap)
        _USER32.DeleteDC(memdc)
        _USER32.ReleaseDC(0, hdc_screen)
        return frame
    except Exception:
        return None


def grab_region(x: int, y: int, width: int, height: int):
    """Grab a specific screen region via MSS. Used as fallback when PrintWindow
    fails and for monitor-index capture."""
    try:
        sct = _get_mss()
        mon = {"left": x, "top": y, "width": width, "height": height}
        img = sct.grab(mon)
        frame = np.array(img)
        if frame.shape[-1] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        return frame
    except Exception:
        return None


class BITMAPINFOHEADER(Structure):
    _fields_ = [
        ("biSize",         wintypes.DWORD),
        ("biWidth",        wintypes.LONG),
        ("biHeight",       wintypes.LONG),
        ("biPlanes",       wintypes.WORD),
        ("biBitCount",     wintypes.WORD),
        ("biCompression",  wintypes.DWORD),
        ("biSizeImage",    wintypes.DWORD),
        ("biXPelsPerMeter",wintypes.LONG),
        ("biYPelsPerMeter",wintypes.LONG),
        ("biClrUsed",      wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER)]


# ── Window utilities ─────────────────────────────────────────

def find_game_window(title_substring: str):
    """Find a top-level window whose title contains the substring (case-insensitive).
    Returns HWND (int) or None."""
    result = {}

    @ctypes.WINFUNCTYPE(c_bool, wintypes.HWND, wintypes.LPARAM)
    def enum_cb(hwnd, lparam):
        length = _USER32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _USER32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if title_substring.lower() in title.lower():
            # Check it's a real window (visible, not tool window)
            style = _USER32.GetWindowLongW(hwnd, GWL_STYLE)
            exstyle = _USER32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if style & WS_VISIBLE and not (exstyle & WS_EX_TOOLWINDOW):
                # Prefer windows with WS_EX_APPWINDOW or normal title bar
                if exstyle & WS_EX_APPWINDOW or title:
                    result["hwnd"] = hwnd
                    return False
        return True

    _USER32.EnumWindows(enum_cb, 0)
    return result.get("hwnd")


def get_client_rect(hwnd: int):
    """Return (left, top, width, height) of window client area."""
    rect = RECT()
    _USER32.GetClientRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.width(), rect.height()


def get_window_pid(hwnd: int):
    """Return the PID that owns the given window."""
    pid = wintypes.DWORD()
    _USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def set_window_active(hwnd: int):
    """Re-assert 'active' to the window so it doesn't auto-pause while unfocused.
    Sends WM_ACTIVATEAPP + WM_NCACTIVATE + WM_ACTIVATE + WM_SETFOCUS."""
    try:
        # WM_ACTIVATEAPP: tell the window our thread is activating it
        _USER32.PostMessageW(hwnd, WM_ACTIVATEAPP, 1, 0)
        # WM_NCACTIVATE: deactivate the non-client area title bar (removes active look)
        _USER32.PostMessageW(hwnd, WM_NCACTIVATE, 0, 0)
        # WM_ACTIVATE: activate the window itself
        _USER32.PostMessageW(hwnd, WM_ACTIVATE, 1, 0)
        # WM_SETFOCUS: set keyboard focus
        _USER32.PostMessageW(hwnd, WM_SETFOCUS, 0, 0)
    except Exception:
        pass


# ── Letterbox / pillarbox detection ──────────────────────────

def detect_content_rect(frame):
    """Detect the game content area vs. black letterbox/pillarbox bars.
    Returns (x, y, w, h) in frame pixel coords, or None if no bars found.
    Algorithm: dark + flat + symmetric edge analysis."""
    if frame is None:
        return None
    h, w = frame.shape[:2]
    if h == 0 or w == 0:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame

    # Edge magnitude — edges at bar boundaries will be prominent
    edges = cv2.Canny(gray, 50, 150)
    edge_col_sum = np.sum(edges, axis=0)  # per-column edge energy
    edge_row_sum = np.sum(edges, axis=1)  # per-row edge energy

    # Pixel intensity — bars are near-black (< 15)
    mean_col = np.mean(gray, axis=0)
    mean_row = np.mean(gray, axis=1)

    def find_bar_boundaries(mean_arr, is_col):
        """Return (start, end) of content region, or (0, len-1) if none."""
        threshold = 15
        # Find first/last non-bar row/col
        mask = mean_arr > threshold
        if not np.any(mask):
            return (0, len(mean_arr) - 1)
        indices = np.where(mask)[0]
        start = max(0, indices[0] - 2)
        end = min(len(mean_arr) - 1, indices[-1] + 2)
        return (start, end)

    # Detect horizontal bars (letterbox — black bands top/bottom)
    h_start, h_end = find_bar_boundaries(mean_row, is_col=False)
    content_h = h_end - h_start + 1

    # Detect vertical bars (pillarbox — black bands left/right)
    v_start, v_end = find_bar_boundaries(mean_col, is_col=True)
    content_w = v_end - v_start + 1

    # Require bars to be > 3% of dimension to avoid noise
    min_bar = int(min(h, w) * 0.03)

    # Only apply crop if we found significant bars
    x = 0 if v_start < min_bar else v_start
    y = 0 if h_start < min_bar else h_start
    bw = w if v_end >= w - min_bar else v_end + 1
    bh = h if h_end >= h - min_bar else h_end + 1
    crop_w = bw - x
    crop_h = bh - y

    # Require meaningful content (> 80% of original and > 720p)
    if crop_w < w * 0.8 or crop_h < h * 0.8:
        return None
    if crop_w < 1280 or crop_h < 720:
        return None

    return (x, y, crop_w, crop_h)


# ── IME guard ────────────────────────────────────────────────

def force_english_ime():
    """Switch keyboard layout to English. Checks HKL first — if already English,
    does nothing (avoids clobbering CJK IME state when user is on an English-
    layout keyboard)."""
    try:
        # Get the current keyboard layout for the foreground thread
        hkl = _USER32.GetKeyboardLayout(0)
        # LOWORD is the language ID; 0x0409 = US English
        lang_id = LOWORD = hkl & 0xFFFF
        if lang_id == 0x0409:
            return  # Already English

        # Load US English keyboard layout
        us_english = 0x04090409  # en-US
        _USER32.ActivateKeyboardLayout(us_english, 0)
    except Exception:
        pass


# ── Background input (PostMessage) ────────────────────────────

def post_key(hwnd: int, vk: int, key_up: bool = False,
             extended: bool = False, repeat: bool = False):
    """Send a key event via PostMessage (no focus required)."""
    try:
        wm = WM_KEYUP if key_up else WM_KEYDOWN
        flags = 0
        if extended:
            flags |= 0x01   # KEYEVENTF_EXTENDEDKEY
        if key_up:
            flags |= 0x02   # KEYEVENTF_KEYUP
        if repeat:
            flags |= 0x04   # KEYEVENTF_EXTENDEDKEY is reused for repeat in some contexts
        scan = _KERNEL32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
        # PostMessage doesn't use scan codes the same way, but we include it
        # in lParam for compatibility
        lParam = (scan << 16) | (1 << 0) | (0 << 24) | (flags << 24)
        if key_up:
            lParam |= (1 << 30) | (1 << 31)   # previous key-down + key-up bit
        _USER32.PostMessageW(hwnd, wm, vk, lParam)
    except Exception:
        pass


def post_click(hwnd: int, screen_x: int, screen_y: int, post_wait: float = 0.5):
    """Send a left-click at absolute screen coordinates via PostMessage."""
    try:
        lparam = (screen_y << 16) | (screen_x & 0xFFFF)
        _USER32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        time.sleep(0.05)
        _USER32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
        time.sleep(post_wait)
    except Exception:
        pass


def post_client_click(hwnd: int, client_x: int, client_y: int, post_wait: float = 0.5):
    """Send a left-click at window-client coordinates via PostMessage.
    No screen-position calculation needed — coordinates are relative to client area."""
    try:
        # Convert client coords to lParam
        lparam = (client_y << 16) | (client_x & 0xFFFF)
        _USER32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        time.sleep(0.05)
        _USER32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
        time.sleep(post_wait)
    except Exception:
        pass


def post_scroll(hwnd: int, notches: int, post_wait: float = 0.1):
    """Send a vertical scroll via PostMessage WM_MOUSEWHEEL.
    notches: positive = scroll up, negative = scroll down."""
    try:
        delta = notches * 120   # WHEEL_DELTA = 120
        # Get cursor position for the message
        pt = POINT()
        _USER32.GetCursorPos(ctypes.byref(pt))
        lparam = (pt.y << 16) | (pt.x & 0xFFFF)
        wparam = delta << 16
        _USER32.PostMessageW(hwnd, WM_MOUSEWHEEL, wparam, lparam)
        time.sleep(post_wait)
    except Exception:
        pass


# ── Foreground input (SendInput) ──────────────────────────────

class KEYBDINPUT(Structure):
    _fields_ = [
        ("wVk",         wintypes.WORD),
        ("wScan",       wintypes.WORD),
        ("dwFlags",    wintypes.DWORD),
        ("time",       wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG),
    ]


class UNION_KEYBD(Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 28)]


class INPUT_KEYBD(Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", UNION_KEYBD)]


class MOUSEINPUT(Structure):
    _fields_ = [
        ("dx",         wintypes.LONG),
        ("dy",         wintypes.LONG),
        ("mouseData",  wintypes.DWORD),
        ("dwFlags",   wintypes.DWORD),
        ("time",      wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG),
    ]


class UNION_MOUSE(Union):
    _fields_ = [("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 28)]


class INPUT_MOUSE(Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", UNION_MOUSE)]


def _send_input_struct(inp):
    """Low-level SendInput wrapper."""
    n = _USER32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def mouse_click(screen_x: int, screen_y: int,
                mon_left: int = 0, mon_top: int = 0,
                post_wait: float = 0.5):
    """Move cursor to absolute screen position + click via SendInput."""
    try:
        _USER32.SetCursorPos(screen_x + mon_left, screen_y + mon_top)
        time.sleep(0.1)
        for flag in (0x0002, 0x0004):   # LBUTTONDOWN, LBUTTONUP
            inp = INPUT_MOUSE(
                type=0,
                union=UNION_MOUSE(
                    mi=MOUSEINPUT(dx=0, dy=0, mouseData=0,
                                  dwFlags=flag, time=0, dwExtraInfo=0)
                )
            )
            _send_input_struct(inp)
            time.sleep(0.05)
        time.sleep(post_wait)
    except Exception:
        pass


def mouse_scroll(notches: int, post_wait: float = 0.1):
    """Scroll via SendInput."""
    try:
        delta = notches * 120
        inp = INPUT_MOUSE(
            type=0,
            union=UNION_MOUSE(
                mi=MOUSEINPUT(dx=0, dy=0, mouseData=delta,
                              dwFlags=0x0800, time=0, dwExtraInfo=0)  # MOUSEEVENTF_WHEEL
            )
        )
        _send_input_struct(inp)
        time.sleep(post_wait)
    except Exception:
        pass


# ── Per-app audio mute (pycaw) ────────────────────────────────

def set_process_muted(pid: int, muted: bool):
    """Mute/unmute a specific process via pycaw SimpleAudioVolume."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioSessionManager, AudioSession, ISimpleAudioVolume

       Enumerator = ctypes.CoCreateInstance(
            AudioSessionManager.unsafe_clsid,
            None,
            CLSCTX_ALL,
            AudioSessionManager.iid,
        )
        mgr = cast(Enumerator, POINTER(AudioSessionManager))
        sessions = mgr.GetSessionEnumerator()
        for session in sessions:
            try:
                if session.GetProcessID() == pid:
                    vol = cast(session, POINTER(ISimpleAudioVolume))
                    vol.SetMute(1 if muted else 0, None)
                    return True
            except Exception:
                continue
    except ImportError:
        pass
    except Exception:
        pass
    return False


# ── Template loading ──────────────────────────────────────────

_TEMPLATE_GEOMETRY = {}  # key -> (box, screen_w, screen_h)


def load_template(folder: str, key: str,
                  current_w: int, current_h: int,
                  grayscale: bool = True,
                  ref_folder: str = None,
                  prefer_ref: bool = True) -> tuple:
    """
    Load a template image, auto-scaled to the current resolution.
    Returns (image, scale, metadata_dict).

    folder: language subfolder under templates/ (e.g. "en", "cht")
    key: template name (no extension)
    current_w / current_h: screen resolution to scale to
    grayscale: return grayscale template
    ref_folder: reference resolution folder (default = "built-in")
    prefer_ref: if True, look in ref_folder first
    """
    import os as _os

    if ref_folder is None:
        ref_folder = "built-in"

    # Try ref_folder first, then local folder
    candidates = []
    if prefer_ref and ref_folder != folder:
        candidates.append(_os.path.join(ref_folder, key + ".png"))
        candidates.append(_os.path.join(ref_folder, key + ".jpg"))
    candidates.append(_os.path.join(folder, key + ".png"))
    candidates.append(_os.path.join(folder, key + ".jpg"))
    if prefer_ref and ref_folder != folder:
        candidates.append(_os.path.join(ref_folder, key + ".png"))
        candidates.append(_os.path.join(ref_folder, key + ".jpg"))

    path = None
    for c in candidates:
        if _os.path.isfile(c):
            path = c
            break

    if path is None:
        raise FileNotFoundError(f"Template not found: {key}")

    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"Cannot read template: {path}")

    # Auto-scale: height-only ratio (preserves aspect)
    ref_meta = _TEMPLATE_GEOMETRY.get(f"__ref_{key}", {})
    ref_h = ref_meta.get("screen_height", 2160)
    scale = current_h / ref_h
    if scale != 1.0:
        new_w = int(img.shape[1] * scale)
        new_h = int(img.shape[0] * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    if grayscale:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    meta = _TEMPLATE_GEOMETRY.get(key, {})
    meta["scale"] = scale
    meta["path"] = path
    return img, scale, meta


def set_template_geometry(key: str, box: tuple, screen_w: int, screen_h: int):
    """Store template capture geometry (box + reference resolution).
    box: (x, y, w, h) in ratio form [0..1]"""
    _TEMPLATE_GEOMETRY[key] = {
        "box": box,
        "screen_width": screen_w,
        "screen_height": screen_h,
    }


def get_template_geometry(key: str) -> dict:
    """Return stored geometry dict for a template key."""
    return _TEMPLATE_GEOMETRY.get(key, {})


# ── Capture Session (Caps Lock ROI recorder) ──────────────────

class CaptureSession:
    """
    Interactive ROI recorder. Press Caps Lock to activate.
    Draws a drag-select rectangle on screen; on release saves the
    selected region with box metadata for the detector's adaptive ROI.

    Usage:
        session = CaptureSession()
        session.capture()  # blocks until ROI selected or ESC
        if session.roi:
            x, y, w, h = session.roi
    """

    def __init__(self, monitor_index: int = 1):
        self.monitor_index = monitor_index
        self.roi = None  # (x, y, w, h) in screen coords
        self.box = None  # (x_ratio, y_ratio, w_ratio, h_ratio)
        self._setup_opencv()

    def _setup_opencv(self):
        """Pull a full-screen frame for the selection overlay."""
        import platform
        mon_left, mon_top = 0, 0
        mw, mh, mon_left, mon_top = get_monitor_dims(self.monitor_index)
        self.monitor = {"left": mon_left, "top": mon_top, "width": mw, "height": mh}
        self.frame = grab_frame(self.monitor_index)
        if self.frame is None:
            raise RuntimeError("Cannot grab screen for capture session")

    def capture(self):
        """Run the interactive ROI selection. Returns True if ROI was selected."""
        if self.frame is None:
            return False
        clone = self.frame.copy()
        roi = cv2.selectROI("Select ROI — ESC to cancel", clone,
                            fromCenter=False, showCrosshair=True)
        cv2.destroyWindow("Select ROI — ESC to cancel")
        x, y, w, h = roi
        if w > 10 and h > 10:
            # Convert to ratios relative to frame dimensions
            fh, fw = self.frame.shape[:2]
            self.box = (x / fw, y / fh, w / fw, h / fh)
            # Also store pixel rect relative to monitor
            self.roi = (x + self.monitor["left"],
                        y + self.monitor["top"],
                        w, h)
            return True
        return False


# ── Node Session (Mastery grid node recorder) ─────────────────

class NodeSession:
    """
    Records 6 click positions for a mastery tree node row.
    Each click is stored in screen coords; stored as ratios for
    resolution independence.

    Usage:
        session = NodeSession()
        session.record()   # interactive 6-click recording
        nodes = session.nodes  # [(row, col, x_ratio, y_ratio), ...]
    """

    ROWS = 4
    COLS = 4

    def __init__(self, monitor_index: int = 1):
        self.monitor_index = monitor_index
        self.nodes = []   # [(row, col, x_ratio, y_ratio), ...]
        self._setup()

    def _setup(self):
        mw, mh, ml, mt = get_monitor_dims(self.monitor_index)
        self.monitor_rect = (ml, mt, mw, mh)
        self.frame = grab_frame(self.monitor_index)
        if self.frame is None:
            raise RuntimeError("Cannot grab screen for node session")

    def record(self):
        """Interactive 6-click node recording."""
        import math
        clone = self.frame.copy()
        clicks = []

        def mouse_cb(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                fh, fw = clone.shape[:2]
                clicks.append((x / fw, y / fh))
                label = f"Click {len(clicks)}/6"
                cv2.circle(clone, (x, y), 6, (0, 255, 0), 2)
                cv2.putText(clone, label, (x + 8, y - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow("Node Session — click 6 nodes (ESC to finish)", clone)

        win = "Node Session — click 6 nodes (ESC to finish)"
        cv2.namedWindow(win)
        cv2.setMouseCallback(win, mouse_cb)

        while len(clicks) < 6:
            cv2.imshow(win, clone)
            key = cv2.waitKey(100) & 0xFF
            if key == 27:  # ESC — stop early
                break

        cv2.destroyWindow(win)

        # Map 6 clicks to a 4-col row: evenly-spaced x positions
        n = len(clicks)
        if n == 0:
            return
        # Determine which row this is from the y position
        # For simplicity: store clicks with row=0 (caller fills in row)
        # Sort by x to get left-to-right order
        sorted_clicks = sorted(clicks, key=lambda c: c[0])
        cols_per_node = self.COLS  # assume 4 nodes per row
        for i, (xr, yr) in enumerate(sorted_clicks):
            col = min(i, self.COLS - 1)
            self.nodes.append((0, col, xr, yr))

    def save(self, path: str):
        """Save nodes to a JSON file."""
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.nodes, f, indent=2)

    @staticmethod
    def load(path: str) -> list:
        """Load nodes from a JSON file."""
        import json
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return []
