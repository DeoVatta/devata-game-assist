"""全屏拖拽框选屏幕区域（支持多显示器）。"""

from __future__ import annotations

import tkinter as tk

import win32api

from .anchor import AnchorRect

# Windows virtual screen metrics constants
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def _virtual_screen_bounds() -> tuple[int, int, int, int]:
    """返回虚拟桌面边界 (left, top, width, height)，覆盖所有显示器。"""
    left = win32api.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = win32api.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = win32api.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = win32api.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return left, top, width, height


class RegionPicker:
    def pick_overlay(self, parent: tk.Misc, hint: str) -> AnchorRect | None:
        self._result: AnchorRect | None = None
        self._start: tuple[int, int] | None = None
        self._rect_id: int | None = None
        self._origin_x: int = 0
        self._origin_y: int = 0

        overlay = tk.Toplevel(parent)
        overlay.title("框选区域")
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.35)
        overlay.configure(cursor="crosshair", bg="black")
        overlay.grab_set()

        # 覆盖虚拟桌面（所有显示器）
        vx, vy, vw, vh = _virtual_screen_bounds()
        self._origin_x = vx
        self._origin_y = vy
        overlay.geometry(f"{vw}x{vh}+{vx}+{vy}")
        # 去掉标题栏
        overlay.overrideredirect(True)

        canvas = tk.Canvas(
            overlay,
            width=vw,
            height=vh,
            highlightthickness=0,
            bg="black",
        )
        canvas.pack(fill=tk.BOTH, expand=True)

        hint_id = canvas.create_text(
            vw // 2,
            40,
            text=hint,
            fill="yellow",
            font=("Microsoft YaHei UI", 16, "bold"),
        )

        def close_overlay():
            try:
                overlay.grab_release()
            except tk.TclError:
                pass
            overlay.destroy()

        def cancel(_event=None):
            self._result = None
            close_overlay()

        def on_press(event):
            self._start = (event.x_root, event.y_root)
            if self._rect_id is not None:
                canvas.delete(self._rect_id)
            self._rect_id = canvas.create_rectangle(
                event.x_root - vx,
                event.y_root - vy,
                event.x_root - vx,
                event.y_root - vy,
                outline="#00ff88",
                width=3,
            )

        def on_drag(event):
            if self._start is None or self._rect_id is None:
                return
            x0, y0 = self._start
            canvas.coords(
                self._rect_id,
                x0 - vx,
                y0 - vy,
                event.x_root - vx,
                event.y_root - vy,
            )

        def on_release(event):
            if self._start is None:
                return
            x0, y0 = self._start
            x1, y1 = event.x_root, event.y_root
            left = min(x0, x1)
            top = min(y0, y1)
            width = abs(x1 - x0)
            height = abs(y1 - y0)
            if width < 20 or height < 20:
                canvas.itemconfig(hint_id, text="区域太小，请重新拖拽")
                self._start = None
                if self._rect_id is not None:
                    canvas.delete(self._rect_id)
                    self._rect_id = None
                return
            self._result = AnchorRect(left=left, top=top, width=width, height=height)
            close_overlay()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        overlay.bind("<Escape>", cancel)

        parent.wait_window(overlay)
        return self._result


def _restore_parent(parent: tk.Misc) -> None:
    try:
        parent.deiconify()
        parent.lift()
        parent.focus_force()
        parent.update_idletasks()
    except tk.TclError:
        pass


def pick_region(hint: str | None = None, *, parent: tk.Misc | None = None) -> AnchorRect:
    hint = hint or "拖拽框选传送门面板，松开确认 | Esc 取消"
    picker = RegionPicker()

    if parent is not None:
        parent.withdraw()
        parent.update_idletasks()
        try:
            result = picker.pick_overlay(parent, hint)
            if result is None:
                raise RuntimeError("已取消框选")
            return result
        finally:
            _restore_parent(parent)

    # CLI 独立模式：临时根窗口，用完即毁
    root = tk.Tk()
    root.withdraw()
    try:
        result = picker.pick_overlay(root, hint)
        if result is None:
            raise RuntimeError("已取消框选")
        return result
    finally:
        root.destroy()


def pick_region_modal(parent: tk.Misc, hint: str | None = None) -> AnchorRect:
    """在已有 GUI 窗口上模态框选（不 hide 主窗口，仅盖一层 overlay）。"""
    hint = hint or "拖拽框选传送门面板，松开确认 | Esc 取消"
    result = RegionPicker().pick_overlay(parent, hint)
    if result is None:
        raise RuntimeError("已取消框选")
    parent.lift()
    parent.focus_force()
    return result
