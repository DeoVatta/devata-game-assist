# ============================================================
#  overlay.py — Translucent always-on-top status overlay that
#  hovers over the game (borderless/windowed). Draggable.
#
#  Never interferes with the automation:
#   • WS_EX_NOACTIVATE  → never steals focus from the game (input keeps working)
#   • topmost           → floats above a borderless game
#  OPAQUE (no -alpha / WS_EX_LAYERED): the layered/alpha path composited the
#  window background but NOT the child widgets on some setups → a featureless
#  black box. Opaque guarantees the labels render. Not click-through either
#  (that blocked dragging) — the user drags it off any click targets.
# ============================================================

import tkinter as tk
import ctypes

try:
    from PIL import Image, ImageTk
except Exception:
    Image = ImageTk = None


def _ui_family():
    """The locked UI font family (set by theme.init_fonts at startup), so the
    overlay's CJK text renders in the same known-good face as the main window
    rather than via Windows' font-linking fallback. Falls back to Segoe UI."""
    try:
        import theme
        return getattr(theme, "UI_FAMILY", "Segoe UI") or "Segoe UI"
    except Exception:
        return "Segoe UI"

_GWL_EXSTYLE      = -20
_WS_EX_NOACTIVATE = 0x08000000

_WIDTH = 300

# Palette
_BORDER    = "#3a4250"
_BORDER_LT = "#5b6678"   # lighter border for the dropdown / popup
_MENU_BG   = "#222b3a"
_BG        = "#12151c"
_HEADER_BG = "#1d2532"
_TITLE_FG  = "#e8edf4"
_STATUS_FG = "#46d369"
_LOG_FG    = "#b7c0cd"
_HINT_FG   = "#f2b441"


class GameOverlay:
    """A small draggable, semi-transparent status box with a titled header.
    Create once, then update(...) / show() / hide(). `on_move(x, y)` fires when
    the user finishes dragging."""

    def __init__(self, master, on_move=None, icon_path=None,
                 tabs=None, on_tab=None):
        self._on_move = on_move
        self._on_tab = on_tab
        fam = _ui_family()
        self._win = tk.Toplevel(master)
        self._win.withdraw()
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.configure(bg=_BORDER, cursor="fleur")

        # 1px border = the border-coloured Toplevel showing around an inner frame
        outer = tk.Frame(self._win, bg=_BG)
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        # ── Header bar: logo + FAFE ──
        header = tk.Frame(outer, bg=_HEADER_BG)
        header.pack(fill="x")
        self._logo = None
        if icon_path and ImageTk is not None:
            try:
                im = Image.open(icon_path).convert("RGBA").resize(
                    (18, 18), Image.LANCZOS)
                self._logo = ImageTk.PhotoImage(im)
                tk.Label(header, image=self._logo, bg=_HEADER_BG).pack(
                    side="left", padx=(8, 5), pady=5)
            except Exception:
                self._logo = None
        tk.Label(header, text="FAFE", bg=_HEADER_BG, fg=_TITLE_FG,
                 font=(fam,10, "bold")).pack(
                     side="left", pady=5, padx=(0 if self._logo else 10, 0))

        # Function switcher dropdown (right of FAFE). tabs = [(key, label), ...]
        self._tab_var = None
        if tabs and on_tab:
            self._tab_key_by_label = {lbl: key for key, lbl in tabs}
            self._tab_label_by_key = {key: lbl for key, lbl in tabs}
            self._tab_var = tk.StringVar(value=tabs[0][1])
            om = tk.OptionMenu(header, self._tab_var,
                               *[lbl for _, lbl in tabs],
                               command=self._on_tab_select)
            # Bordered button so it reads as a clickable dropdown
            om.configure(bg=_HEADER_BG, fg=_TITLE_FG, activebackground="#2a3442",
                         activeforeground=_TITLE_FG, highlightthickness=1,
                         highlightbackground=_BORDER_LT, highlightcolor=_BORDER_LT,
                         bd=1, relief="solid",
                         font=(fam,9), cursor="hand2", width=7,
                         takefocus=0)
            # Bordered, slightly-lighter popup so it stands out over the game
            om["menu"].configure(bg=_MENU_BG, fg=_TITLE_FG,
                                  activebackground="#33405a",
                                  activeforeground=_TITLE_FG,
                                  borderwidth=2, relief="solid",
                                  activeborderwidth=0, font=(fam,9))
            om.pack(side="right", padx=(0, 8), pady=2)
            self._tab_om = om

        # ── Status ──
        self._status = tk.Label(
            outer, text="", bg=_BG, fg=_STATUS_FG,
            font=(fam,11, "bold"), anchor="w", justify="left",
            wraplength=_WIDTH - 20)
        self._status.pack(fill="x", padx=10, pady=(7, 2))

        # ── Last few log lines ──
        # height=5 reserves exactly 5 text lines so the window is sized for 5
        # from the start — otherwise it sizes to the initial (few) lines and
        # later/newest lines get clipped off the bottom.
        self._log = tk.Label(
            outer, text="", bg=_BG, fg=_LOG_FG,
            font=(fam, 9), anchor="nw", justify="left",
            height=5, width=1)
        self._log.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        # ── Footer: start/stop key hint ──
        self._hint = tk.Label(
            outer, text="", bg=_BG, fg=_HINT_FG,
            font=(fam,9), anchor="w")
        self._hint.pack(fill="x", padx=10, pady=(0, 8))

        # Whole box is a drag handle
        self._drag = (0, 0, 0, 0)
        for w in (self._win, outer, header, self._status, self._log,
                  self._hint):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)

        self._visible = False
        self._win.update_idletasks()
        self._apply_ex_styles()

    def _apply_ex_styles(self):
        try:
            hwnd = self._win.winfo_id()
            u = ctypes.windll.user32
            ex = u.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            u.SetWindowLongW(hwnd, _GWL_EXSTYLE, ex | _WS_EX_NOACTIVATE)
        except Exception:
            pass

    def bounds(self):
        """Absolute screen rect (x, y, w, h) of the overlay window, so the
        capture layer can blank it out of detection frames (anti self-detection
        without hiding the overlay from the user). None if not measurable."""
        try:
            self._win.update_idletasks()
            return (self._win.winfo_rootx(), self._win.winfo_rooty(),
                    self._win.winfo_width(), self._win.winfo_height())
        except Exception:
            return None

    def _drag_start(self, e):
        self._drag = (e.x_root, e.y_root,
                      self._win.winfo_x(), self._win.winfo_y())

    def _drag_move(self, e):
        ox, oy, wx, wy = self._drag
        self._win.geometry(f"+{wx + (e.x_root - ox)}+{wy + (e.y_root - oy)}")

    def _drag_end(self, e):
        if self._on_move:
            try:
                self._on_move(self._win.winfo_x(), self._win.winfo_y())
            except Exception:
                pass

    def _on_tab_select(self, label):
        key = getattr(self, "_tab_key_by_label", {}).get(label)
        if key and self._on_tab:
            try:
                self._on_tab(key)
            except Exception:
                pass

    def set_current_tab(self, key):
        """Sync the dropdown to the active tab (no callback re-trigger:
        StringVar.set doesn't fire the OptionMenu command)."""
        if self._tab_var is None:
            return
        lbl = getattr(self, "_tab_label_by_key", {}).get(key)
        if lbl and self._tab_var.get() != lbl:
            self._tab_var.set(lbl)

    def update(self, status: str, lines, hint: str = None):
        self._status.config(text=(status or "").strip() or "—")
        self._log.config(text="\n".join(lines) if lines else "")
        if hint is not None:
            self._hint.config(text=hint)

    def show(self, x: int, y: int):
        if not self._visible:
            self._win.deiconify()
            self._win.update_idletasks()    # compute content size
            h = max(90, self._win.winfo_reqheight())
            # Explicit WxH — an overrideredirect window given only +x+y can map
            # at 1x1 (invisible).
            self._win.geometry(f"{_WIDTH}x{h}+{int(x)}+{int(y)}")
            self._win.lift()
            self._win.attributes("-topmost", True)
            self._visible = True

    def hide(self):
        if self._visible:
            self._win.withdraw()
            self._visible = False

    def destroy(self):
        try:
            self._win.destroy()
        except Exception:
            pass
