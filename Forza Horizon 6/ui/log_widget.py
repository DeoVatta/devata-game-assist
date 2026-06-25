# ============================================================
#  ui/log_widget.py — Scrollable log area, 1000-line buffer
# ============================================================

import customtkinter as ctk
import queue
import threading

import theme


class LogWidget(ctk.CTkFrame):
    MAX_LINES    = 1000
    MAX_SECTIONS = 3      # keep only the last N loop sections

    def __init__(self, parent, placeholder="", warn_color="#ff4444",
                 title=None, title_color=None, loop_color=None,
                 sep_color=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._queue        = queue.Queue()
        self._lines        = []
        self._section_lens = []   # line count per live section (front = oldest)
        self._placeholder  = placeholder
        self._warn_color   = warn_color    # themed red for warning lines
        self._loop_color   = loop_color    # themed accent for "-- … --" headers

        # Optional card header ("Activity") + separator, like the mockup.
        if title:
            ctk.CTkLabel(self, text=title, anchor="w",
                         font=theme.H2_FONT,
                         text_color=title_color).pack(
                fill="x", padx=14, pady=(10, 4))
            ctk.CTkFrame(self, height=1,
                         fg_color=(sep_color or "gray40")).pack(
                fill="x", padx=14, pady=(0, 4))

        self._text = ctk.CTkTextbox(
            self,
            wrap="word",
            state="disabled",
            fg_color="transparent",   # card frame supplies bg/border
            font=theme.LABEL_FONT,
        )
        self._text.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        if placeholder:
            self._text.configure(state="normal")
            self._text.insert("1.0", placeholder)
            self._text.configure(state="disabled",
                                 text_color=("gray60", "gray50"))

        self._poll()

    def log(self, message: str):
        """Thread-safe: append a message to the log."""
        if self._placeholder and not self._lines:
            # Clear placeholder on first real message
            self._queue.put(None)   # clear
            self._placeholder = ""  # don't restore
        self._queue.put(("normal", message))

    def log_warning(self, message: str):
        """Thread-safe: append a red warning message."""
        if self._placeholder and not self._lines:
            self._queue.put(None)
            self._placeholder = ""
        self._queue.put(("warning", message))

    def log_section(self, message: str):
        """Thread-safe: start a new loop section with this header line.

        Only the last MAX_SECTIONS sections are retained; older ones are
        trimmed off the top so the log doesn't grow without bound.
        """
        if self._placeholder and not self._lines:
            self._queue.put(None)
            self._placeholder = ""
        self._queue.put(("section", message))

    def clear(self):
        self._queue.put(None)   # sentinel for clear

    def _delete_top_lines(self, n: int):
        """Remove the first n lines from buffer + widget (no section bookkeeping)."""
        n = min(n, len(self._lines))
        if n <= 0:
            return
        del self._lines[:n]
        self._text.configure(state="normal")
        self._text.delete("1.0", f"{n + 1}.0")
        self._text.configure(state="disabled")

    def _append_line(self, text: str, style: str):
        """Append a single line to the widget and the current section."""
        self._lines.append(text)
        if self._section_lens:
            self._section_lens[-1] += 1
        self._text.configure(state="normal")
        try:
            if style == "warning":
                # Use underlying tk Text widget for colored tag
                tk_text = self._text._textbox
                tk_text.tag_configure("warning", foreground=self._warn_color)
                tk_text.insert("end", text + "\n", "warning")
            elif self._loop_color and text.strip().startswith("--"):
                # Loop/section headers ("-- Loop #3 --") in the accent color.
                tk_text = self._text._textbox
                tk_text.tag_configure("loop", foreground=self._loop_color)
                tk_text.insert("end", text + "\n", "loop")
            else:
                self._text.insert("end", text + "\n")
        except Exception:
            self._text.insert("end", repr(text) + "\n")
        self._text.configure(state="disabled")

        # Hard safety cap, kept in sync with section counters.
        over = len(self._lines) - self.MAX_LINES
        if over > 0:
            self._delete_top_lines(over)
            while over > 0 and self._section_lens:
                if self._section_lens[0] <= over:
                    over -= self._section_lens.pop(0)
                else:
                    self._section_lens[0] -= over
                    over = 0
        self._text.see("end")

    def _poll(self):
        """Poll the queue and update the text widget."""
        try:
            while True:
                msg = self._queue.get_nowait()
                if msg is None:
                    self._lines.clear()
                    self._section_lens.clear()
                    self._text.configure(state="normal")
                    self._text.delete("1.0", "end")
                    self._text.configure(state="disabled")
                    continue

                style, text = msg
                if style == "section":
                    # Open a new section, dropping the oldest if over the cap.
                    self._section_lens.append(0)
                    while len(self._section_lens) > self.MAX_SECTIONS:
                        drop = self._section_lens.pop(0)
                        self._delete_top_lines(drop)
                    # Blank separator between sections (counts into the new one).
                    if self._lines:
                        self._append_line("", "normal")
                    self._append_line(text, "normal")
                else:
                    if not self._section_lens:
                        self._section_lens.append(0)   # implicit preamble section
                    self._append_line(text, style)
        except queue.Empty:
            pass
        self.after(50, self._poll)
