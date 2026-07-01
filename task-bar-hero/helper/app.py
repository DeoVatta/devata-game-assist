"""TaskBarHero Auto Helper — GUI."""

from __future__ import annotations

import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from tbh_helper.config_loader import load_config, profile_path_from_cfg, save_config
from tbh_helper.portal import PortalNavigator, StageTarget
from tbh_helper.chest_open import ChestOpenConfig, open_chest
from tbh_helper.engine import RotatorEngine
from tbh_helper.gui_countdown import open_countdown_capture_dialog
from tbh_helper.profile import PortalProfile
from tbh_helper.statistics import StatisticsTracker
from tbh_helper.ui_theme import (
 ACCENT,
 BG,
 BORDER,
 BORDER_WINE,
 Card,
 FONT_BOLD,
 FONT_SUB,
 FONT_TITLE,
 FONT_UI,
 GOLD,
 GOLD_HOVER,
 RoundedButton,
 SegmentedControl,
 StatusPill,
 StepRow,
 StatusFlow,
 StyledScrollbar,
 StyledScrolledText,
 SURFACE,
 SURFACE2,
 TEXT,
 TEXT2,
 apply_root_style,
 style_entry,
 style_listbox,
 style_log,
 style_option_menu,
)
from tbh_helper.mouse import click_at
from tbh_helper.paths import app_dir, ensure_runtime_files, prompt_vc_runtime
from tbh_helper.window import (
 find_game_window,
 get_client_rect_screen,
 get_cursor_pos,
 is_process_elevated,
 is_self_elevated,
)

BASE_DIR = ensure_runtime_files()
CONFIG_PATH = app_dir() / "config.yaml"

PORTAL_UI_WIZARD = [
 ("chapter_1", "Chapter 1", "Move mouse to Chapter 1 tab"),
 ("chapter_2", "Chapter 2", "Move mouse to Chapter 2 tab"),
 ("chapter_3", "Chapter 3", "Move mouse to Chapter 3 tab"),
 ("diff_dropdown", "Difficulty Dropdown", "Move mouse to difficulty dropdown"),
 ("diff_normal", "Normal", "Move mouse to 'Normal' option"),
 ("diff_nightmare", "Nightmare", "Move mouse to 'Nightmare' option"),
 ("diff_hell", "Hell", "Move mouse to 'Hell' option"),
 ("diff_torment", "Torment", "Move mouse to 'Torment' option"),
 ("scroll_area", "Scroll Area", "Move mouse to map scroll area"),
]


class TBHApp(tk.Tk):
 def __init__(self) -> None:
  super().__init__()
  self.title("TaskBarHeroHelper")
  self.geometry("520x920")
  self.minsize(480, 800)
  apply_root_style(self)

  self.cfg = load_config(CONFIG_PATH)
  self.engine = RotatorEngine(
   self.cfg, BASE_DIR, on_log=self._enqueue_log, on_switch=self._on_switch, on_drop=self._on_drop,
   on_stats_update=self._mark_stats_dirty,
  )
  # on_status / on_manual_switch_done bound in _build_run_page (controls must exist first)
  self._log_queue: queue.Queue[str] = queue.Queue()
  self._anchor = None
  self._drop_count = 0
  self._wizard_idx = 0

  self._build_ui()
  # Auto-restore window anchor from config on startup
  self._restore_anchor()
  prompt_vc_runtime(self)
  self._check_elevation()
  self._refresh_status()
  self._refresh_setup_steps()
  self.after(100, self._drain_log_queue)

 # ── UI build ───────────────────────────────────────────

 def _build_ui(self) -> None:
  root = tk.Frame(self, bg=BG, padx=20, pady=16)
  root.pack(fill=tk.BOTH, expand=True)

  # Header
  header = tk.Frame(root, bg=BG)
  header.pack(fill=tk.X, pady=(0, 14))
  tk.Label(header, text="Auto Helper", font=FONT_TITLE, bg=BG, fg=TEXT).pack(side=tk.LEFT)

  right = tk.Frame(header, bg=BG)
  right.pack(side=tk.RIGHT)
  RoundedButton(
   right, "📁 Config", self._open_config_dir, width=76, height=26, radius=8, style="ghost"
  ).pack(side=tk.LEFT, padx=(0, 6))
  self.game_pill = StatusPill(right)
  self.game_pill.pack(side=tk.LEFT)

  # Tab switch
  self.page_run = tk.Frame(root, bg=BG)
  self.page_setup = tk.Frame(root, bg=BG)
  self.page_stats = tk.Frame(root, bg=BG)
  self.page_misc = tk.Frame(root, bg=BG)
  self._seg = SegmentedControl(
   root,
   [("Run", self._show_run), ("Settings", self._show_setup), ("Misc", self._show_misc), ("Stats", self._show_stats)],
  )
  self._seg.pack(pady=(0, 14))
  self._seg.select(0)

  self._build_run_page(self.page_run)
  self._build_setup_page(self.page_setup)
  self._build_stats_page(self.page_stats)
  self._build_misc_page(self.page_misc)
  self.page_run.pack(fill=tk.BOTH, expand=True)
  self._show_run()

  # Layout finalize
  self.update_idletasks()

 def _build_run_page(self, parent: tk.Frame) -> None:
  card = Card(parent)
  card.pack(fill=tk.X, pady=(0, 12))

  self.var_mode = tk.StringVar(value="Idle")
  self.var_stats = tk.StringVar(value="Boss Box 0 · Switches 0")
  self.var_next = tk.StringVar(value="")

  self.lbl_mode = tk.Label(card.inner, textvariable=self.var_mode, font=FONT_SUB, bg=SURFACE, fg=TEXT)
  self.lbl_mode.pack(anchor=tk.W)
  tk.Label(card.inner, textvariable=self.var_stats, font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(anchor=tk.W, pady=(4, 0))
  tk.Label(card.inner, textvariable=self.var_next, font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(anchor=tk.W, pady=(2, 0))

  btn_row = tk.Frame(parent, bg=BG)
  btn_row.pack(fill=tk.X, pady=(0, 12))

  inner_row = tk.Frame(btn_row, bg=BG)
  inner_row.pack()

  self.btn_start = RoundedButton(inner_row, "Start Auto", self._start, width=200, height=44, radius=14)
  self.btn_start.pack(side=tk.LEFT)

  self.btn_next = RoundedButton(
   inner_row, "Next Stage", self._next_stage, width=88, height=44, radius=14, style="secondary"
  )
  self.btn_next.pack(side=tk.LEFT, padx=(10, 0))
  self.btn_next.configure_state(tk.DISABLED)

  # Status flow bar
  self.status_flow = StatusFlow(parent)
  self.status_flow.pack(fill=tk.X, pady=(0, 8))
  self.engine.on_status = lambda **kw: self.status_flow.show(**kw)
  self.engine.on_manual_switch_done = lambda: self.after_idle(self._on_manual_switch_done)

  log_card = Card(parent, padding=0)
  log_card.pack(fill=tk.BOTH, expand=True)
  # Sub-widgets inside inner,avoid Card Empty inner frame spacingEmptyinterval
  tk.Label(log_card.inner, text=" Log", font=FONT_UI, bg=SURFACE, fg=GOLD, anchor=tk.W).pack(
   fill=tk.X, padx=12, pady=(10, 0)
  )
  self.log_text = StyledScrolledText(log_card.inner, height=10, state=tk.DISABLED, wrap=tk.WORD)
  self.log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
  style_log(self.log_text.text)

 def _build_setup_page(self, parent: tk.Frame) -> None:
  scroll_outer = tk.Frame(parent, bg=BG)
  scroll_outer.pack(fill=tk.BOTH, expand=True)

  # Step 1
  self.step_anchor = StepRow(scroll_outer, 1, "Capture Window", "Auto-detect game window client area as coordinate anchor")
  self.step_anchor.pack(fill=tk.X, pady=(0, 8))
  btn_frame1 = tk.Frame(self.step_anchor.action_slot, bg=SURFACE)
  btn_frame1.pack()
  self.btn_capture_win = RoundedButton(
   btn_frame1, "Capture Window", self._capture_window_anchor,
   width=88, height=32, radius=10, style="secondary",
  )
  self.btn_capture_win.pack(side=tk.LEFT)
  self.btn_show_overlay = RoundedButton(
   btn_frame1, "Show Area", self._toggle_overlay,
   width=72, height=32, radius=10, style="secondary",
  )
  self.btn_show_overlay.pack(side=tk.LEFT, padx=(4, 0))
  self._overlay = None

  # Step 2
  self.step_ui = StepRow(scroll_outer, 2, "Calibrate Portal UI", "Chapter, difficulty, scroll — wizard setup")
  self.step_ui.pack(fill=tk.X, pady=(0, 8))
  RoundedButton(
   self.step_ui.action_slot,
   "Wizard",
   self._run_portal_ui_wizard,
   width=72,
   height=32,
   radius=10,
   style="secondary",
  ).pack()

  # Step 3 — Rotation nodes
  stage_card = Card(scroll_outer, padding=12)
  stage_card.pack(fill=tk.X, pady=(0, 8))

  stage_head = tk.Frame(stage_card.inner, bg=SURFACE)
  stage_head.pack(fill=tk.X, pady=(0, 8))
  tk.Label(stage_head, text="Step 3 · Rotation Nodes", font=FONT_SUB, bg=SURFACE, fg=TEXT).pack(side=tk.LEFT)
  RoundedButton(
   stage_head, "+ Add", self._add_stage, width=72, height=28, radius=8, style="ghost"
  ).pack(side=tk.RIGHT)

  list_frame = tk.Frame(stage_card.inner, bg=SURFACE)
  list_frame.pack(fill=tk.X, pady=(0, 8))

  self.stage_list = tk.Listbox(list_frame, exportselection=False, height=4)
  self.stage_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
  style_listbox(self.stage_list)

  list_scroll = StyledScrollbar(
   list_frame, command=self.stage_list.yview,
  )
  list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
  self.stage_list.configure(yscrollcommand=list_scroll.set)
  self._load_stage_list()

  stage_btns = tk.Frame(stage_card.inner, bg=SURFACE)
  stage_btns.pack(fill=tk.X)
  for label, cmd, w in (
   ("Edit", self._edit_stage, 56),
   ("Re-mark", self._mark_stage_pos, 56),
   ("Test Click", self._test_stage_click, 72),
   ("Delete", self._delete_stage, 48),
   ("Up", lambda: self._move_stage(-1), 36),
   ("Down", lambda: self._move_stage(1), 36),
  ):
   RoundedButton(stage_btns, label, cmd, width=w, height=28, radius=8, style="secondary").pack(
    side=tk.LEFT, padx=(0, 4)
   )

  # Position hint
  hint_frame = tk.Frame(stage_card.inner, bg=SURFACE)
  hint_frame.pack(fill=tk.X, pady=(2, 0))
  tk.Label(
   hint_frame,
   text="Stages 1-7: drag to bottom edge. Stages 8-10: drag to top edge.",
   font=FONT_UI,
   bg=SURFACE,
   fg=TEXT2,
   wraplength=380,
   justify=tk.LEFT,
  ).pack(anchor=tk.W)

  # Step 3.5 — Stage timeout
  timeout_frame = tk.Frame(stage_card.inner, bg=SURFACE)
  timeout_frame.pack(fill=tk.X, pady=(8, 0))
  tk.Label(
   timeout_frame, text="Timeout switch (minutes)", font=FONT_UI, bg=SURFACE, fg=TEXT2
  ).pack(side=tk.LEFT)
  self.var_timeout_minutes = tk.StringVar(
   value=str(self.cfg.get("rotation", {}).get("stage_timeout_minutes", 0))
  )
  self.entry_timeout = tk.Entry(
   timeout_frame,
   textvariable=self.var_timeout_minutes,
   width=6,
   font=FONT_UI,
   bg=SURFACE2,
   fg=TEXT,
   relief=tk.FLAT,
   justify=tk.CENTER,
  )
  self.entry_timeout.pack(side=tk.RIGHT)
  self.entry_timeout.bind("<FocusOut>", self._on_timeout_focus_out)
  self.entry_timeout.bind("<Return>", self._on_timeout_focus_out)
  tk.Label(
   timeout_frame, text="0 = disabled", font=FONT_UI, bg=SURFACE, fg=TEXT2
  ).pack(side=tk.RIGHT, padx=(0, 6))

  # Step 4 — Auto chest
  chest_card = Card(scroll_outer, padding=12)
  chest_card.pack(fill=tk.X)

  chest_cfg = ChestOpenConfig.from_dict(self.cfg.get("chest_open"))
  self.var_chest_enabled = tk.BooleanVar(value=chest_cfg.enabled)

  row = tk.Frame(chest_card.inner, bg=SURFACE)
  row.pack(fill=tk.X)
  tk.Label(row, text="Step 4 · Auto Open Chest", font=FONT_SUB, bg=SURFACE, fg=TEXT).pack(side=tk.LEFT)

  chest_row = tk.Frame(chest_card.inner, bg=SURFACE)
  chest_row.pack(fill=tk.X, pady=(8, 0))
  self.var_chest_hint = tk.StringVar(value=self._chest_hint_text())
  tk.Label(chest_row, text="Blue Box", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT)
  tk.Label(chest_row, textvariable=self.var_chest_hint, font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(
   side=tk.LEFT, padx=(6, 0)
  )
  chest_toggle = tk.Checkbutton(
   chest_row,
   text="Enable",
   variable=self.var_chest_enabled,
   command=self._save_chest_enabled,
   bg=SURFACE,
   fg=GOLD,
   selectcolor=SURFACE2,
   activebackground=SURFACE,
   activeforeground=GOLD_HOVER,
   font=FONT_UI,
  )
  chest_toggle.pack(side=tk.RIGHT)
  RoundedButton(
   chest_row, "Mark Position", self._mark_chest, width=82, height=28, radius=8, style="secondary"
  ).pack(side=tk.RIGHT, padx=(0, 4))
  RoundedButton(
   chest_row, "Test Click", self._test_chest_click, width=64, height=28, radius=8, style="ghost"
  ).pack(side=tk.RIGHT)

  # Normal chest
  norm_row = tk.Frame(chest_card.inner, bg=SURFACE)
  norm_row.pack(fill=tk.X, pady=(4, 0))
  self.var_norm_hint = tk.StringVar(value=self._normal_chest_hint_text())
  tk.Label(norm_row, text="White Box", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT)
  tk.Label(norm_row, textvariable=self.var_norm_hint, font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(
   side=tk.LEFT, padx=(6, 0)
  )
  self.var_norm_chest_enabled = tk.BooleanVar(
   value=ChestOpenConfig.from_dict(self.cfg.get("normal_chest")).enabled
  )
  norm_toggle = tk.Checkbutton(
   norm_row,
   text="Enable",
   variable=self.var_norm_chest_enabled,
   command=self._save_norm_chest_enabled,
   bg=SURFACE,
   fg=GOLD,
   selectcolor=SURFACE2,
   activebackground=SURFACE,
   activeforeground=GOLD_HOVER,
   font=FONT_UI,
  )
  norm_toggle.pack(side=tk.RIGHT)
  RoundedButton(
   norm_row, "Mark Position", self._mark_normal_chest, width=82, height=28, radius=8, style="secondary"
  ).pack(side=tk.RIGHT, padx=(0, 4))
  RoundedButton(
   norm_row, "Test Click", self._test_normal_chest_click, width=64, height=28, radius=8, style="ghost"
  ).pack(side=tk.RIGHT)

  # Click method
  method_row2 = tk.Frame(chest_card.inner, bg=SURFACE)
  method_row2.pack(fill=tk.X, pady=(6, 0))
  tk.Label(method_row2, text="Click Method", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT)
  self.var_click_method = tk.StringVar(
   value=self.cfg.get("chest_open", {}).get("click_method", "auto")
  )
  method_combo = ttk.Combobox(
   method_row2,
   textvariable=self.var_click_method,
   values=("auto", "sendinput", "mouse_event", "postmessage"),
   state="readonly",
   width=14,
   font=FONT_UI,
  )
  method_combo.pack(side=tk.RIGHT)
  method_combo.bind("<<ComboboxSelected>>", self._save_click_method)

 def _build_misc_page(self, parent: tk.Frame) -> None:
  scroll_outer = tk.Frame(parent, bg=BG)
  scroll_outer.pack(fill=tk.BOTH, expand=True)

  # ── Auto Warehouse ──
  wh_card = Card(scroll_outer, padding=12)
  wh_card.pack(fill=tk.X, pady=(0, 8))

  tk.Label(wh_card.inner, text="Auto Warehouse", font=FONT_SUB, bg=SURFACE, fg=TEXT).pack(
   anchor=tk.W, pady=(0, 8)
  )

  # Warehouse tabs
  tab_head = tk.Frame(wh_card.inner, bg=SURFACE)
  tab_head.pack(fill=tk.X, pady=(0, 8))
  tk.Label(tab_head, text="Warehouse Tabs", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT)
  RoundedButton(
   tab_head, "+ Add", self._add_warehouse_page, width=72, height=28, radius=8, style="ghost"
  ).pack(side=tk.RIGHT)

  list_frame = tk.Frame(wh_card.inner, bg=SURFACE)
  list_frame.pack(fill=tk.X, pady=(0, 8))

  self.warehouse_list = tk.Listbox(list_frame, exportselection=False, height=4)
  self.warehouse_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
  style_listbox(self.warehouse_list)

  list_scroll = StyledScrollbar(
   list_frame, command=self.warehouse_list.yview,
  )
  list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
  self.warehouse_list.configure(yscrollcommand=list_scroll.set)
  self._adjust_warehouse_list_height(0)

  tab_btns = tk.Frame(wh_card.inner, bg=SURFACE)
  tab_btns.pack(fill=tk.X)
  RoundedButton(
   tab_btns, "DeletePage", self._delete_warehouse_page, width=80, height=28, radius=8, style="secondary"
  ).pack(side=tk.LEFT, padx=(0, 4))
  RoundedButton(
   tab_btns, "re-mark", self._remark_warehouse_page, width=56, height=28, radius=8, style="secondary"
  ).pack(side=tk.LEFT, padx=(0, 4))

  # Transferbutton
  transfer_section = tk.Frame(wh_card.inner, bg=SURFACE)
  transfer_section.pack(fill=tk.X, pady=(12, 0))
  tk.Label(transfer_section, text="Transfer Button", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT)
  RoundedButton(
   transfer_section, "Mark Position", self._mark_warehouse_transfer, width=88, height=28, radius=8, style="secondary"
  ).pack(side=tk.RIGHT)
  self.var_transfer_hint = tk.StringVar(value="Not marked")
  tk.Label(
   transfer_section, textvariable=self.var_transfer_hint, font=FONT_UI, bg=SURFACE, fg=TEXT2
  ).pack(side=tk.RIGHT, padx=(0, 8))

  # Timer settings
  timer_section = tk.Frame(wh_card.inner, bg=SURFACE)
  timer_section.pack(fill=tk.X, pady=(12, 0))

  wh_cfg = self.cfg.get("warehouse", {})
  self.var_warehouse_enabled = tk.BooleanVar(value=bool(wh_cfg.get("enabled", False)))
  self.var_warehouse_interval = tk.StringVar(
   value=str(wh_cfg.get("interval_minutes", 30))
  )

  row = tk.Frame(timer_section, bg=SURFACE)
  row.pack(fill=tk.X)

  tk.Label(row, text="Enable", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT)
  tk.Checkbutton(
   row, text="", variable=self.var_warehouse_enabled, command=self._save_warehouse_config,
   bg=SURFACE, fg=GOLD, selectcolor=SURFACE2, activebackground=SURFACE,
   activeforeground=GOLD_HOVER, font=FONT_UI,
  ).pack(side=tk.LEFT, padx=(4, 0))

  tk.Label(row, text="Interval", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT, padx=(12, 4))

  entry = tk.Entry(
   row, textvariable=self.var_warehouse_interval, width=6, font=FONT_UI,
   bg=SURFACE2, fg=TEXT, relief=tk.FLAT, justify=tk.CENTER,
  )
  entry.pack(side=tk.LEFT)
  entry.bind("<FocusOut>", self._save_warehouse_config)
  entry.bind("<Return>", self._save_warehouse_config)
  tk.Label(row, text="minutes", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT, padx=(4, 0))

  # ── Mailbox Timeout Check ──
  mail_card = Card(scroll_outer, padding=12)
  mail_card.pack(fill=tk.X, pady=(8, 0))

  tk.Label(mail_card.inner, text="Mailbox Timeout Check", font=FONT_SUB, bg=SURFACE, fg=TEXT).pack(
   anchor=tk.W, pady=(0, 8)
  )
  tk.Label(
   mail_card.inner,
   text="On timeout: open mailbox -> refresh -> receive all -> close, then wait one more drop cycle.",
   font=FONT_UI, bg=SURFACE, fg=TEXT2, wraplength=380, anchor=tk.W, justify=tk.LEFT,
  ).pack(anchor=tk.W, pady=(0, 6))

  mail_btn_names = [
   ("open", "Open"),
   ("refresh", "Refresh"),
   ("receive_all", "Receive All"),
   ("close", "Close"),
  ]
  self._mail_hint_vars: dict[str, tk.StringVar] = {}
  mail_row = tk.Frame(mail_card.inner, bg=SURFACE)
  mail_row.pack(fill=tk.X)

  for key, label in mail_btn_names:
   f = tk.Frame(mail_row, bg=SURFACE)
   f.pack(side=tk.LEFT, padx=(0, 6))
   var = tk.StringVar(value="✗")
   self._mail_hint_vars[key] = var
   btn = RoundedButton(
    f, label, lambda k=key: self._mark_mailbox_button(k),
    width=64, height=26, radius=8, style="secondary",
   )
   btn.pack()
   tk.Label(f, textvariable=var, font=FONT_UI, bg=SURFACE, fg=TEXT2).pack()

  mb_cfg = self.cfg.get("mailbox_check", {})
  self.var_mailbox_enabled = tk.BooleanVar(value=bool(mb_cfg.get("enabled", False)))

  mail_toggle_row = tk.Frame(mail_card.inner, bg=SURFACE)
  mail_toggle_row.pack(fill=tk.X, pady=(6, 0))
  tk.Label(
   mail_toggle_row, text="Enable mailbox check on timeout", font=FONT_UI, bg=SURFACE, fg=TEXT2
  ).pack(side=tk.LEFT)
  tk.Checkbutton(
   mail_toggle_row, text="", variable=self.var_mailbox_enabled,
   command=self._save_mailbox_config,
   bg=SURFACE, fg=GOLD, selectcolor=SURFACE2, activebackground=SURFACE,
   activeforeground=GOLD_HOVER, font=FONT_UI,
  ).pack(side=tk.RIGHT)

  tab_btns = tk.Frame(wh_card.inner, bg=SURFACE)
  tab_btns.pack(fill=tk.X)
  RoundedButton(
   tab_btns, "Delete Tab", self._delete_warehouse_page, width=80, height=28, radius=8, style="secondary"
  ).pack(side=tk.LEFT, padx=(0, 4))
  RoundedButton(
   tab_btns, "Re-mark", self._remark_warehouse_page, width=56, height=28, radius=8, style="secondary"
  ).pack(side=tk.LEFT, padx=(0, 4))

  # Transfer button
  transfer_section = tk.Frame(wh_card.inner, bg=SURFACE)
  transfer_section.pack(fill=tk.X, pady=(12, 0))
  tk.Label(transfer_section, text="Transfer Button", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT)
  RoundedButton(
   transfer_section, "Mark Position", self._mark_warehouse_transfer, width=88, height=28, radius=8, style="secondary"
  ).pack(side=tk.RIGHT)
  self.var_transfer_hint = tk.StringVar(value="Not marked")
  tk.Label(
   transfer_section, textvariable=self.var_transfer_hint, font=FONT_UI, bg=SURFACE, fg=TEXT2
  ).pack(side=tk.RIGHT, padx=(0, 8))

  # Timer settings
  timer_section = tk.Frame(wh_card.inner, bg=SURFACE)
  timer_section.pack(fill=tk.X, pady=(12, 0))

  wh_cfg = self.cfg.get("warehouse", {})
  self.var_warehouse_enabled = tk.BooleanVar(value=bool(wh_cfg.get("enabled", False)))
  self.var_warehouse_interval = tk.StringVar(
   value=str(wh_cfg.get("interval_minutes", 30))
  )

  row = tk.Frame(timer_section, bg=SURFACE)
  row.pack(fill=tk.X)

  tk.Label(row, text="Enable", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT)
  tk.Checkbutton(
   row, text="", variable=self.var_warehouse_enabled, command=self._save_warehouse_config,
   bg=SURFACE, fg=GOLD, selectcolor=SURFACE2, activebackground=SURFACE,
   activeforeground=GOLD_HOVER, font=FONT_UI,
  ).pack(side=tk.LEFT, padx=(4, 0))

  tk.Label(row, text="Interval", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT, padx=(12, 4))

  entry = tk.Entry(
   row, textvariable=self.var_warehouse_interval, width=6, font=FONT_UI,
   bg=SURFACE2, fg=TEXT, relief=tk.FLAT, justify=tk.CENTER,
  )
  entry.pack(side=tk.LEFT)
  entry.bind("<FocusOut>", self._save_warehouse_config)
  entry.bind("<Return>", self._save_warehouse_config)
  tk.Label(row, text="minutes", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT, padx=(4, 0))

  # ── Mailbox Timeout Check ──
  mail_card = Card(scroll_outer, padding=12)
  mail_card.pack(fill=tk.X, pady=(8, 0))

  tk.Label(mail_card.inner, text="Mailbox Timeout Check", font=FONT_SUB, bg=SURFACE, fg=TEXT).pack(
   anchor=tk.W, pady=(0, 8)
  )
  tk.Label(
   mail_card.inner,
   text="On timeout: auto open mailbox -> refresh -> receive all -> close, then wait for one more drop cycle.",
   font=FONT_UI, bg=SURFACE, fg=TEXT2, wraplength=380, anchor=tk.W, justify=tk.LEFT,
  ).pack(anchor=tk.W, pady=(0, 6))

  mail_btn_names = [
   ("open", "Open"),
   ("refresh", "Refresh"),
   ("receive_all", "Receive All"),
   ("close", "Close"),
  ]
  self._mail_hint_vars: dict[str, tk.StringVar] = {}
  mail_row = tk.Frame(mail_card.inner, bg=SURFACE)
  mail_row.pack(fill=tk.X)

  for key, label in mail_btn_names:
   f = tk.Frame(mail_row, bg=SURFACE)
   f.pack(side=tk.LEFT, padx=(0, 6))
   var = tk.StringVar(value="✗")
   self._mail_hint_vars[key] = var
   btn = RoundedButton(
    f, label, lambda k=key: self._mark_mailbox_button(k),
    width=64, height=26, radius=8, style="secondary",
   )
   btn.pack()
   tk.Label(f, textvariable=var, font=FONT_UI, bg=SURFACE, fg=TEXT2).pack()

  mb_cfg = self.cfg.get("mailbox_check", {})
  self.var_mailbox_enabled = tk.BooleanVar(value=bool(mb_cfg.get("enabled", False)))

  mail_toggle_row = tk.Frame(mail_card.inner, bg=SURFACE)
  mail_toggle_row.pack(fill=tk.X, pady=(6, 0))
  tk.Label(
   mail_toggle_row, text="Enable mailbox check on timeout", font=FONT_UI, bg=SURFACE, fg=TEXT2
  ).pack(side=tk.LEFT)
  tk.Checkbutton(
   mail_toggle_row, text="", variable=self.var_mailbox_enabled,
   command=self._save_mailbox_config,
   bg=SURFACE, fg=GOLD, selectcolor=SURFACE2, activebackground=SURFACE,
   activeforeground=GOLD_HOVER, font=FONT_UI,
  ).pack(side=tk.RIGHT)

  # ── Folded UI ──
  fold_card = Card(scroll_outer, padding=12)
  fold_card.pack(fill=tk.X, pady=(8, 0))

  tk.Label(fold_card.inner, text="Folded UI", font=FONT_SUB, bg=SURFACE, fg=TEXT).pack(
   anchor=tk.W, pady=(0, 8)
  )
  tk.Label(
   fold_card.inner,
   text="When enabled, automatically expand/fold the main menu before each operation.",
   font=FONT_UI, bg=SURFACE, fg=TEXT2, wraplength=380, anchor=tk.W, justify=tk.LEFT,
  ).pack(anchor=tk.W, pady=(0, 6))

  # Mode selection
  fp_cfg = self.cfg.get("fold_page", {})
  self.var_fold_mode = tk.StringVar(value=str(fp_cfg.get("mode", "always_expand")))

  mode_row = tk.Frame(fold_card.inner, bg=SURFACE)
  mode_row.pack(fill=tk.X, pady=(0, 8))
  tk.Label(mode_row, text="Mode", font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT)

  def _on_fold_mode_change() -> None:
   self.cfg.setdefault("fold_page", {})["mode"] = self.var_fold_mode.get()
   from tbh_helper.config_loader import save_config
   save_config(CONFIG_PATH, self.cfg)

  for val, label in (("always_expand", "Always Expand"), ("fold_before_use", "Fold Before Use")):
   rb = tk.Radiobutton(
    mode_row, text=label, variable=self.var_fold_mode, value=val,
    command=_on_fold_mode_change,
    bg=SURFACE, fg=TEXT, selectcolor=SURFACE2, activebackground=SURFACE,
    activeforeground=GOLD_HOVER, font=FONT_UI,
   )
   rb.pack(side=tk.LEFT, padx=(12, 0))

  # Four coordinate markers
  self._fold_hint_vars: dict[str, tk.StringVar] = {}
  fold_btn_configs = [
   ("fold_expand_btn", "Expand Button"),
   ("fold_portal_btn", "Portal Button"),
   ("fold_warehouse_btn", "Warehouse Button"),
   ("fold_confirm_btn", "Server Error Confirm Button"),
  ]
  for attr, label in fold_btn_configs:
   row = tk.Frame(fold_card.inner, bg=SURFACE)
   row.pack(fill=tk.X, pady=(2, 0))
   tk.Label(row, text=label, font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT)
   if attr == "fold_confirm_btn":
    tk.Label(
     row, text="(put between inventory and team)", font=FONT_UI, bg=SURFACE, fg=TEXT2
    ).pack(side=tk.LEFT, padx=(4, 0))

   var = tk.StringVar(value="✗")
   self._fold_hint_vars[attr] = var
   tk.Label(
    row, textvariable=var, font=FONT_UI, bg=SURFACE, fg=TEXT2
   ).pack(side=tk.RIGHT, padx=(0, 4))

   RoundedButton(
    row, "Mark Position",
    lambda a=attr, l=label: self._mark_fold_button(a, l),
    width=88, height=26, radius=8, style="secondary",
   ).pack(side=tk.RIGHT)

  self._refresh_fold_hints()

 def _mark_fold_button(self, attr: str, label: str) -> None:
  """Mark one folded UI button coordinate (relative to anchor)."""
  if not self._require_idle() or not self._require_anchor():
   return

  def capture() -> bool:
   rel = self._capture_cursor_in_anchor(warn_outside=False)
   if rel is None:
    return False
   profile = self._get_profile()
   setattr(profile, attr, [rel[0], rel[1]])
   self._save_profile(profile, capture_template=bool(self._anchor))
   self._append_log(f">>> {label} @ ({rel[0]}, {rel[1]})")
   self._refresh_fold_hints()
   return True

  self._run_countdown_capture(
   title=f"Mark {label}",
   prompt=f"cursor to Game inside \"{label}\" Position",
   capture_fn=capture,
  )

 def _refresh_fold_hints(self) -> None:
  if not hasattr(self, "_fold_hint_vars"):
   return
  profile = self._get_profile()
  for attr, var in self._fold_hint_vars.items():
   pos = getattr(profile, attr, None)
   if pos and len(pos) >= 2:
    var.set(f"({pos[0]:.3f}, {pos[1]:.3f})")
   else:
    var.set("✗")

 def _save_fold_config(self) -> None:
  """Save fold page mode to config.yaml."""
  self.cfg.setdefault("fold_page", {})["mode"] = self.var_fold_mode.get()
  from tbh_helper.config_loader import save_config
  save_config(CONFIG_PATH, self.cfg)

 def _show_run(self) -> None:
  if hasattr(self, "_seg"):
   self._seg.select(0)
  self.page_setup.pack_forget()
  self.page_stats.pack_forget()
  self.page_misc.pack_forget()
  self._stats_visible = False
  self.page_run.pack(fill=tk.BOTH, expand=True)

 def _show_setup(self) -> None:
  if hasattr(self, "_seg"):
   self._seg.select(1)
  self.page_run.pack_forget()
  self.page_stats.pack_forget()
  self.page_misc.pack_forget()
  self._stats_visible = False
  self.page_setup.pack(fill=tk.BOTH, expand=True)
  self._load_stage_list()
  self._refresh_setup_steps()

 def _show_stats(self) -> None:
  if hasattr(self, "_seg"):
   self._seg.select(3)
  self.page_run.pack_forget()
  self.page_setup.pack_forget()
  self.page_misc.pack_forget()
  self._stats_visible = True
  self.page_stats.pack(fill=tk.BOTH, expand=True)
  self._stats_dirty = True
  self._refresh_stats()
  self._poll_stats()

 def _show_misc(self) -> None:
  if hasattr(self, "_seg"):
   self._seg.select(2)
  self.page_run.pack_forget()
  self.page_setup.pack_forget()
  self.page_stats.pack_forget()
  self._stats_visible = False
  self.page_misc.pack(fill=tk.BOTH, expand=True)
  self._refresh_warehouse_ui()
  self._refresh_fold_hints()

 # ── Stats page (push update, no scrollbar, adaptive column width)───────

 def _mark_stats_dirty(self) -> None:
  """Engine callback (any thread), only set dirty flag."""
  self._stats_dirty = True

 def _reset_stats(self) -> None:
  """Manually reset statistics."""
  self.engine.stats.reset()
  self._stats_dirty = True
  self._refresh_stats()
  self._append_log(">>> Stats reset")

 def _poll_stats(self) -> None:
  if not self._stats_visible:
   return
  # Refresh elapsed time at least once per second
  self._update_elapsed()
  if self._stats_dirty:
   self._refresh_stats()
  self._stats_poll_id = self.after(1000, self._poll_stats)

 def _update_elapsed(self) -> None:
  """Refresh only elapsed time (lightweight, called every second)."""
  stats = self.engine.stats
  summary = stats.snapshot_summary()
  total = summary.elapsed_seconds
  h, m = int(total // 3600), int((total % 3600) // 60)
  s = int(total % 60)
  if h:
   self._sv_elapsed.set(f"{h}h {m}m")
  elif m:
   self._sv_elapsed.set(f"{m}m {s}s")
  else:
   self._sv_elapsed.set(f"{s}s")

 def _build_stats_page(self, parent: tk.Frame) -> None:
  container = tk.Frame(parent, bg=BG)
  container.pack(fill=tk.BOTH, expand=True)

  # Canvas without scrollbar
  self._stats_canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
  self._stats_canvas.pack(fill=tk.BOTH, expand=True)

  self._stats_inner = tk.Frame(self._stats_canvas, bg=BG)
  self._stats_cw = self._stats_canvas.create_window(
   (0, 0), window=self._stats_inner, anchor=tk.NW
  )

  def _on_cfg(_event):
   self._stats_canvas.itemconfig(self._stats_cw, width=_event.width)
  self._stats_canvas.bind("<Configure>", _on_cfg)

  def _on_inner(_event):
   self._stats_canvas.configure(scrollregion=self._stats_canvas.bbox("all"))
  self._stats_inner.bind("<Configure>", _on_inner)

  self._stats_canvas.bind(
   "<MouseWheel>",
   lambda e: self._stats_canvas.yview_scroll(-1 * (e.delta // 120), "units"),
  )

  # ── Session summary (persistent StringVar) ──
  sum_card = tk.Frame(self._stats_inner, bg=SURFACE, highlightbackground=BORDER_WINE, highlightthickness=1)
  sum_card.pack(fill=tk.X, pady=(0, 10))

  sum_title_row = tk.Frame(sum_card, bg=SURFACE)
  sum_title_row.pack(fill=tk.X, padx=14, pady=(12, 6))
  tk.Label(sum_title_row, text="Session Summary", font=FONT_SUB, bg=SURFACE, fg=GOLD).pack(side=tk.LEFT)
  RoundedButton(
   sum_title_row, "Reset Stats", self._reset_stats, width=80, height=26, radius=8, style="secondary"
  ).pack(side=tk.RIGHT)
  grid = tk.Frame(sum_card, bg=SURFACE)
  grid.pack(fill=tk.X, padx=14, pady=(0, 12))

  self._sv_elapsed = tk.StringVar(value="—")
  self._sv_drops = tk.StringVar(value="—")

  items = [
   ("Session Time", self._sv_elapsed),
   ("Boss Drops", self._sv_drops),
  ]
  for i, (label, sv) in enumerate(items):
   f = tk.Frame(grid, bg=SURFACE)
   f.grid(row=0, column=i, sticky=tk.W, padx=(0, 24), pady=2)
   tk.Label(f, text=label, font=FONT_UI, bg=SURFACE, fg=TEXT2).pack(side=tk.LEFT)
   tk.Label(f, textvariable=sv, font=FONT_BOLD, bg=SURFACE, fg=TEXT).pack(side=tk.LEFT, padx=(6, 0))

  # ── Stage details (persistent table header + row pool) ──
  self._stats_table_card = tk.Frame(
   self._stats_inner, bg=SURFACE, highlightbackground=BORDER_WINE, highlightthickness=1
  )
  self._stats_table_card.pack(fill=tk.X)

  tk.Label(self._stats_table_card, text="Stage Details", font=FONT_SUB, bg=SURFACE, fg=GOLD).pack(
   anchor=tk.W, padx=14, pady=(12, 4)
  )

  # tableheader — 4 equal columns grid
  head = tk.Frame(self._stats_table_card, bg=ACCENT)
  head.pack(fill=tk.X, padx=10, pady=(6, 0))
  head.grid_columnconfigure((0, 1, 2, 3), weight=1)

  hdrs = [("Stage", tk.W), ("Boss Drops", tk.CENTER), ("Avg Time", tk.CENTER), ("Cycle Interval", tk.CENTER)]
  for i, (text, anchor) in enumerate(hdrs):
   tk.Label(head, text=text, font=FONT_UI, bg=ACCENT, fg="#FFFFFF", anchor=anchor).grid(
    row=0, column=i, sticky=tk.EW, padx=2, pady=3
   )

  # row
  self._stats_rows_frame = tk.Frame(self._stats_table_card, bg=SURFACE)
  self._stats_rows_frame.pack(fill=tk.X, padx=10, pady=(2, 10))
  self._stats_rows: list[tk.Frame] = []
  self._stats_empty = tk.Label(
   self._stats_rows_frame,
   text="No data yet. Start auto-run to collect stats.",
   font=FONT_UI,
   bg=SURFACE,
   fg=TEXT2,
  )
  self._stats_empty.pack(pady=10)

  self._stats_dirty = False
  self._stats_visible = False

 def _refresh_stats(self) -> None:
  self._stats_dirty = False
  stats = self.engine.stats
  records = stats.snapshot()
  summary = stats.snapshot_summary()

  # summary
  self._update_elapsed()
  self._sv_drops.set(f"{summary.total_boss_drops} x")
  # table
  if not records:
   self._stats_empty.pack(pady=10)
   for row in self._stats_rows:
    row.pack_forget()
   return
  self._stats_empty.pack_forget()

  n = len(records)
  # adjustrowcount
  while len(self._stats_rows) < n:
   row = self._create_stats_row()
   row.pack(fill=tk.X, pady=1)
   self._stats_rows.append(row)
  while len(self._stats_rows) > n:
   self._stats_rows.pop().destroy()

  for i, r in enumerate(records):
   self._update_stats_row(self._stats_rows[i], r, i)

 def _create_stats_row(self) -> tk.Frame:
  row = tk.Frame(self._stats_rows_frame, bg=SURFACE)
  row.grid_columnconfigure((0, 1, 2, 3), weight=1)
  lbl_name = tk.Label(row, text="", font=FONT_UI, bg=SURFACE, fg=TEXT, anchor=tk.W)
  lbl_name.grid(row=0, column=0, sticky=tk.EW, padx=2, pady=2)
  cells: list[tk.Label] = []
  for i in range(1, 4):
   lbl = tk.Label(row, text="", font=FONT_UI, bg=SURFACE, fg=TEXT2, anchor=tk.CENTER)
   lbl.grid(row=0, column=i, sticky=tk.EW, padx=2, pady=2)
   cells.append(lbl)
  row._name = lbl_name
  row._cells = cells
  return row

 def _update_stats_row(self, row: tk.Frame, r, idx: int) -> None:
  bg = SURFACE2 if idx % 2 == 0 else SURFACE
  row.configure(bg=bg)
  row._name.configure(text=r.name, bg=bg)

  # Avgdrop time
  bt = int(r.avg_boss_time)
  boss_str = f"{bt // 60}m{bt % 60}s" if bt >= 60 else f"{bt}s" if bt > 0 else "—"

  # rotationInterval
  ct = int(r.avg_cycle_interval)
  cm, cs = ct // 60, ct % 60
  cycle_str = f"{cm}m{cs}s" if cm else f"{cs}s" if ct > 0 else "—"

  texts = [
   (str(r.boss_drops), GOLD),
   (boss_str, TEXT2),
   (cycle_str, TEXT2),
  ]
  for lbl, (text, fg) in zip(row._cells, texts):
   lbl.configure(text=text, fg=fg, bg=bg)

 def _chest_hint_text(self) -> str:
  c = ChestOpenConfig.from_dict(self.cfg.get("chest_open"))
  if c.enabled:
   return f"edMark ({c.rel_x:.2f}, {c.rel_y:.2f})"
  return "Auto-open before stage switch"

 # ── Config / Status ───────────────────────────────────────

 def _profile_path(self) -> Path:
  return profile_path_from_cfg(self.cfg, BASE_DIR)

 def _get_profile(self) -> PortalProfile:
  return PortalProfile.load_or_create(self._profile_path())

 def _save_profile(self, profile: PortalProfile, *, capture_template: bool = False) -> None:
  path = self._profile_path()
  if capture_template and self._anchor:
   profile.capture_template(self._anchor, path.parent / "portal_anchor.png")
  profile.save(path)
  self.cfg.setdefault("portal", {})
  self.cfg["portal"]["profile"] = str(path.relative_to(BASE_DIR)).replace("\\", "/")
  save_config(CONFIG_PATH, self.cfg)
  self.engine.cfg = self.cfg
  self._load_stage_list()
  self._refresh_warehouse_ui()
  self._refresh_status()
  self._refresh_setup_steps()

 def _refresh_setup_steps(self) -> None:
  profile = self._get_profile()
  ui_ok = bool(profile.chapter_tabs and profile.difficulty_options)
  self.step_anchor.set_status("done" if self._anchor else "active")
  self.step_ui.set_status("done" if ui_ok else ("active" if self._anchor else "pending"))
  chest = ChestOpenConfig.from_dict(self.cfg.get("chest_open"))

 def _refresh_status(self) -> None:
  hwnd = find_game_window(
   process_name=self.cfg.get("game", {}).get("process_name", "TaskBarHero"),
   pid=self.cfg.get("game", {}).get("pid"),
  )

  if hasattr(self, "var_chest_hint"):
   self.var_chest_hint.set(self._chest_hint_text())
  if hasattr(self, "var_norm_hint"):
   self.var_norm_hint.set(self._normal_chest_hint_text())

  # PermissionInfo
  if hwnd and is_process_elevated(hwnd) and not is_self_elevated():
   self.game_pill.set_ok(True, "Game running as admin - helper also needs Run as admin")
  elif hwnd:
   self.game_pill.set_ok(True, "Game online")
  else:
   self.game_pill.set_ok(False, "Game not detected")

 def _open_config_dir(self) -> None:
  """infileManageOpenConfigfolder."""
  try:
   import os
   os.startfile(str(BASE_DIR))
  except Exception as exc:
   messagebox.showerror("Error", f"noOpenConfigfolder\n{exc}", parent=self)

 def _check_elevation(self) -> None:
  """Check for elevation mismatch on startup and warn."""
  hwnd = find_game_window(
   process_name=self.cfg.get("game", {}).get("process_name", "TaskBarHero"),
   pid=self.cfg.get("game", {}).get("pid"),
  )
  if not hwnd:
   return
  if is_process_elevated(hwnd) and not is_self_elevated():
   self._append_log(
    "⚠ ChecktoGameasAdminPermissionRun,but helpernois."
    "edAutoSwitchas postmessage Mode."
    "alsoClosehelperafterRight-click bat → asAdminidentityRunas."
   )

 def _restore_anchor(self) -> None:
  """fromConfigRestorePreviousCaptureWindowanchor."""
  r = self.cfg.get("portal", {}).get("window_rect")
  if r and len(r) == 4:
   from tbh_helper.anchor import AnchorRect
   self._anchor = AnchorRect(left=r[0], top=r[1], width=r[2], height=r[3])
   self.engine.set_anchor(self._anchor)
   self._append_log(
    f">>> Window anchor restored: {r[2]}×{r[3]} @ ({r[0]},{r[1]})"
   )

 def _require_idle(self) -> bool:
  if self.engine.is_running:
   messagebox.showwarning("Info", "Stop auto-run first", parent=self)
   return False
  return True

 def _require_anchor(self) -> bool:
  if self._anchor is None:
   messagebox.showinfo("Info", "Capture window in Settings first", parent=self)
   return False
  return True

 def _capture_cursor_in_anchor(self, *, warn_outside: bool = True) -> tuple[float, float] | None:
  if not self._anchor:
   return None
  mx, my = get_cursor_pos()
  if warn_outside and not self._anchor.contains_screen(mx, my):
   # Diagnosis: check actual game window position
   diag = ""
   hwnd = find_game_window(
    process_name=self.cfg.get("game", {}).get("process_name", "TaskBarHero"),
    pid=self.cfg.get("game", {}).get("pid"),
   )
   if hwnd:
    try:
     from tbh_helper.window import get_window_rect, get_client_rect_screen
     wr = get_window_rect(hwnd)
     cr = get_client_rect_screen(hwnd)
     diag = (
      f"\n\nDiagnostic info:"
      f"\nCursor position: ({mx}, {my})"
      f"\nWindow rect: ({wr.left},{wr.top}) {wr.width}×{wr.height}"
      f"\nClient area : ({cr.left},{cr.top}) {cr.width}×{cr.height}"
      f"\nCaptured : ({self._anchor.left},{self._anchor.top}) "
      f"{self._anchor.width}×{self._anchor.height}"
     )
     if (cr.left, cr.top, cr.width, cr.height) != (
      self._anchor.left, self._anchor.top,
      self._anchor.width, self._anchor.height
     ):
      diag += "\n→ Window position changed, please re-capture window"
    except Exception:
     pass
   messagebox.showwarning("PositionWarning",
    f"cursornoinWindowClient areainside,pleasemove intoGameWindowinsidetry again.{diag}",
    parent=self)
   return None
  return self._anchor.screen_to_rel(mx, my)

 def _run_countdown_capture(self, *, title: str, prompt: str, capture_fn, seconds: int = 5, on_skip=None) -> None:
  open_countdown_capture_dialog(self, title=title, prompt=prompt, seconds=seconds, capture_fn=capture_fn, on_skip=on_skip)

 # ── Portal UI Wizard ─────────────────────────────────────

 def _apply_portal_ui_mark(self, kind: str, rel: tuple[float, float]) -> None:
  profile = self._get_profile()
  mapping = {
   "chapter_1": lambda: profile.chapter_tabs.__setitem__(1, rel),
   "chapter_2": lambda: profile.chapter_tabs.__setitem__(2, rel),
   "chapter_3": lambda: profile.chapter_tabs.__setitem__(3, rel),
   "diff_dropdown": lambda: setattr(profile, "difficulty_dropdown", rel),
   "diff_normal": lambda: profile.difficulty_options.__setitem__("normal", rel),
   "diff_nightmare": lambda: profile.difficulty_options.__setitem__("nightmare", rel),
   "diff_hell": lambda: profile.difficulty_options.__setitem__("hell", rel),
   "diff_torment": lambda: profile.difficulty_options.__setitem__("torment", rel),
   "scroll_area": lambda: setattr(profile, "map_scroll_area", rel),
  }
  mapping[kind]()
  self._save_profile(profile, capture_template=True)

 def _run_portal_ui_wizard(self) -> None:
  if not self._require_idle() or not self._require_anchor():
   return
  self._wizard_idx = 0
  self._append_log(">>> Starting Portal UI calibration wizard")
  self._wizard_next_step()

 def _wizard_next_step(self) -> None:
  if self._wizard_idx >= len(PORTAL_UI_WIZARD):
   self._append_log(">>> Portal UI calibration complete")
   self._refresh_setup_steps()
   messagebox.showinfo("Done", "Portal UI fully calibrated", parent=self)
   return

  kind, title, prompt = PORTAL_UI_WIZARD[self._wizard_idx]

  if kind.startswith("diff_") and kind != "diff_dropdown":
   self._append_log(f">>> Mark {title} (can skip)")

  def capture() -> bool:
   rel = self._capture_cursor_in_anchor()
   if rel is None:
    return False
   self._apply_portal_ui_mark(kind, rel)
   self._append_log(f">>> {title}: ({rel[0]}, {rel[1]})")
   self._wizard_idx += 1
   self.after(400, self._wizard_next_step)
   return True

  def skip_diff() -> None:
   self._append_log(f">>> Skip {title}")
   self._wizard_idx += 1
   self.after(200, self._wizard_next_step)

  is_difficulty_option = kind.startswith("diff_") and kind != "diff_dropdown"
  self._run_countdown_capture(
   title=f"Mark · {title}", prompt=prompt, capture_fn=capture,
   on_skip=skip_diff if is_difficulty_option else None,
  )

 def _mark_portal_ui(self, kind: str) -> None:
  if not self._require_idle() or not self._require_anchor():
   return
  labels = {k: (t, p) for k, t, p in PORTAL_UI_WIZARD}
  title, prompt = labels.get(kind, ("Mark", "Move mouse to target position"))

  def capture() -> bool:
   rel = self._capture_cursor_in_anchor()
   if rel is None:
    return False
   self._apply_portal_ui_mark(kind, rel)
   self._append_log(f">>> {title}: ({rel[0]}, {rel[1]})")
   return True

  self._run_countdown_capture(title=title, prompt=prompt, capture_fn=capture)

 # ── Rotation Nodes ───────────────────────────────────────────

 def _load_stage_list(self) -> None:
  if not hasattr(self, "stage_list"):
   return
  self.stage_list.delete(0, tk.END)
  profile = self._get_profile()
  if not profile.stages:
   self.stage_list.insert(tk.END, " No nodes yet. Click + Add")
   self._adjust_stage_list_height(0)
   return
  for i, s in enumerate(profile.stages, 1):
   self.stage_list.insert(tk.END, f" {i}. {s['name']}")
  self._adjust_stage_list_height(len(profile.stages))

 def _adjust_stage_list_height(self, n: int) -> None:
  """Dynamic Listbox row height adjustment:Empty=4row,1-6rowmatch,exceed6rowfixed6row+slider."""
  if n <= 0:
   rows = 4
  elif n <= 6:
   rows = n
  else:
   rows = 6
  self.stage_list.configure(height=rows)

 def _adjust_warehouse_list_height(self, n: int) -> None:
  """dynamic adjustWarehouseList Listbox rowcount:Empty=4row,1-6rowmatch,exceed6rowfixed6row."""
  if n <= 0:
   rows = 4
  elif n <= 6:
   rows = n
  else:
   rows = 6
  self.warehouse_list.configure(height=rows)

 def _selected_stage_index(self) -> int | None:
  sel = self.stage_list.curselection()
  profile = self._get_profile()
  if not sel or not profile.stages:
   return None
  idx = int(sel[0])
  return idx if idx < len(profile.stages) else None

 def _open_stage_meta_dialog(self, *, title: str, initial: dict | None = None, on_submit, auto_name: bool = True) -> None:
  initial = initial or {}
  dlg = tk.Toplevel(self)
  dlg.title(title)
  dlg.configure(bg=BG)
  dlg.transient(self)
  dlg.resizable(False, False)

  shell = tk.Frame(dlg, bg=SURFACE, highlightbackground=BORDER_WINE, highlightthickness=1)
  shell.pack(padx=16, pady=16)
  form = tk.Frame(shell, bg=SURFACE, padx=20, pady=16)
  form.pack()

  var_name = tk.StringVar(value=str(initial.get("name", "")))
  var_chapter = tk.StringVar(value=str(initial.get("chapter", 1)))
  var_diff = tk.StringVar(value=str(initial.get("difficulty", "normal")))
  var_num = tk.StringVar(value=str(initial.get("stage_num", 1)))

  fields = [
   ("Name", var_name, None),
   ("Chapter", var_chapter, ("1", "2", "3")),
   ("Difficulty", var_diff, ("normal", "nightmare", "hell", "torment")),
   ("Stage", var_num, tuple(str(i) for i in range(1, 11))),
  ]

  for row_i, (label, var, values) in enumerate(fields):
   tk.Label(form, text=label, bg=SURFACE, fg=TEXT2, font=FONT_UI).grid(
    row=row_i, column=0, sticky=tk.W, pady=6, padx=(0, 12)
   )
   if values:
    om = tk.OptionMenu(form, var, *values)
    style_option_menu(om)
    om.grid(row=row_i, column=1, sticky=tk.W, pady=6)
   else:
    ent = tk.Entry(form, textvariable=var, width=20)
    style_entry(ent)
    ent.grid(row=row_i, column=1, sticky=tk.W, pady=6)

  if auto_name:
   def sync_name(*_) -> None:
    try:
     var_name.set(PortalProfile.default_name(int(var_chapter.get()), var_diff.get(), int(var_num.get())))
    except (ValueError, tk.TclError):
     pass
   for v in (var_chapter, var_diff, var_num):
    v.trace_add("write", sync_name)
   sync_name()

  def close_dialog() -> None:
   if dlg.winfo_exists():
    dlg.destroy()

  def submit() -> None:
   try:
    meta = {
     "name": var_name.get().strip()
     or PortalProfile.default_name(int(var_chapter.get()), var_diff.get(), int(var_num.get())),
     "chapter": int(var_chapter.get()),
     "difficulty": var_diff.get(),
     "stage_num": int(var_num.get()),
    }
   except (ValueError, tk.TclError):
    messagebox.showerror("Error", "Fill in valid parameters", parent=dlg)
    return
   close_dialog()
   self.after(10, lambda m=meta: on_submit(m))

  btn_row = tk.Frame(form, bg=SURFACE)
  btn_row.grid(row=len(fields), column=0, columnspan=2, pady=(12, 0))
  RoundedButton(btn_row, "Mark Position", submit, width=100, height=34, radius=10).pack(side=tk.LEFT, padx=4)
  RoundedButton(btn_row, "Cancel", close_dialog, width=72, height=34, radius=10, style="secondary").pack(
   side=tk.LEFT, padx=4
  )
  dlg.protocol("WM_DELETE_WINDOW", close_dialog)
  dlg.update_idletasks()
  dlg.geometry(f"+{self.winfo_x() + 40}+{self.winfo_y() + 60}")
  dlg.lift()

 def _begin_stage_position_capture(self, meta: dict, *, edit_index: int | None = None) -> None:
  num = int(meta["stage_num"])
  view = "8-10" if num >= 8 else "1-7"
  prompt = f"Switchto {meta['name']}({view} view),cursortoStageNode"

  def capture() -> bool:
   rel = self._capture_cursor_in_anchor()
   if rel is None:
    return False
   profile = self._get_profile()
   stage = {**meta, "rel_x": rel[0], "rel_y": rel[1]}
   if edit_index is not None:
    profile.stages[edit_index] = stage
   else:
    profile.stages.append(stage)
   self._save_profile(profile, capture_template=bool(self._anchor))
   self._append_log(f">>> Node {stage['name']}")
   return True

  self._run_countdown_capture(title=meta["name"], prompt=prompt, capture_fn=capture)

 def _add_stage(self) -> None:
  if not self._require_idle():
   return

  def on_meta(meta: dict) -> None:
   if not self._require_anchor():
    return
   self._begin_stage_position_capture(meta)

  self._open_stage_meta_dialog(title="Add Node", on_submit=on_meta)

 def _edit_stage(self) -> None:
  if not self._require_idle():
   return
  idx = self._selected_stage_index()
  if idx is None:
   messagebox.showinfo("Info", "Select a node first", parent=self)
   return
  stage = self._get_profile().stages[idx]

  def on_meta(meta: dict) -> None:
   profile = self._get_profile()
   meta["rel_x"] = stage["rel_x"]
   meta["rel_y"] = stage["rel_y"]
   profile.stages[idx] = meta
   self._save_profile(profile)
   self._append_log(f">>> Updated {meta['name']}")

  self._open_stage_meta_dialog(title="Edit Node", initial=stage, on_submit=on_meta, auto_name=False)

 def _mark_stage_pos(self) -> None:
  if not self._require_idle() or not self._require_anchor():
   return
  idx = self._selected_stage_index()
  if idx is None:
   messagebox.showinfo("Info", "Select a node first", parent=self)
   return
  s = self._get_profile().stages[idx]
  meta = {"name": s["name"], "chapter": int(s["chapter"]), "difficulty": s["difficulty"], "stage_num": int(s["stage_num"])}
  self._begin_stage_position_capture(meta, edit_index=idx)

 def _test_stage_click(self) -> None:
  """Simulatesimulate full switch flow:selectDifficulty → selectChapter → scroll wheel → ClickNode."""
  if not self._require_idle() or not self._require_anchor():
   return
  idx = self._selected_stage_index()
  if idx is None:
   messagebox.showinfo("Info", "Select a node first", parent=self)
   return
  s = self._get_profile().stages[idx]
  anchor = self._anchor
  if not anchor:
   return
  hwnd = find_game_window(
   process_name=self.cfg.get("game", {}).get("process_name", "TaskBarHero"),
   pid=self.cfg.get("game", {}).get("pid"),
  )
  if not hwnd:
   messagebox.showerror("Error", "Game window not found", parent=self)
   return

  profile = self._get_profile()
  target = StageTarget(
   name=str(s["name"]),
   chapter=int(s["chapter"]),
   difficulty=str(s["difficulty"]),
   stage_num=int(s["stage_num"]),
   rel_x=float(s["rel_x"]),
   rel_y=float(s["rel_y"]),
  )
  navigator = PortalNavigator(
   profile.to_portal_ui(),
   anchor,
   hwnd=hwnd,
   helper_hwnd=self.winfo_id(),
  )
  try:
   self._append_log(f">>> Test {target.name}:Starting simulation…")
   navigator.reset_state()
   navigator.navigate_to_stage(target)
   self._append_log(f">>> Difficulty/Chapter/scroll wheel edDone")
   navigator.click_stage_node(target)
   self._append_log(f">>> Node click done")
  except Exception as exc:
   self._append_log(f">>> Test failed: {exc}")

 def _delete_stage(self) -> None:
  if not self._require_idle():
   return
  idx = self._selected_stage_index()
  if idx is None:
   self.after(1, lambda: messagebox.showinfo("Info", "Select a node to delete first", parent=self))
   return
  profile = self._get_profile()
  if idx >= len(profile.stages):
   return
  name = profile.stages[idx]["name"]

  def confirm() -> None:
   if not messagebox.askyesno("Delete", f'Delete "{name}"?', parent=self):
    return
   p = self._get_profile()
   if idx >= len(p.stages):
    return
   p.stages.pop(idx)
   self._save_profile(p)
   self._append_log(f">>> edDelete {name}")

  self.after(1, confirm)

 def _move_stage(self, delta: int) -> None:
  if not self._require_idle():
   return
  idx = self._selected_stage_index()
  if idx is None:
   return
  new_idx = idx + delta
  profile = self._get_profile()
  if new_idx < 0 or new_idx >= len(profile.stages):
   return
  profile.stages[idx], profile.stages[new_idx] = profile.stages[new_idx], profile.stages[idx]
  self._save_profile(profile)
  self.stage_list.selection_clear(0, tk.END)
  self.stage_list.selection_set(new_idx)

 # ── Auto Open Chest ─────────────────────────────────────────────

 def _update_chest_config(self, chest: ChestOpenConfig) -> None:
  self.cfg.setdefault("chest_open", {})
  self.cfg["chest_open"] = chest.to_dict()
  save_config(CONFIG_PATH, self.cfg)
  self.engine.cfg = self.cfg
  self.engine.chest = chest
  # Sync to profile(engineLaunchpriorityfirstread profile)
  try:
   profile = self._get_profile()
   profile.chest_open = chest.to_dict()
   self._save_profile(profile)
  except Exception:
   pass
  self.var_chest_enabled.set(chest.enabled)
  if hasattr(self, "var_chest_hint"):
   self.var_chest_hint.set(self._chest_hint_text())

 def _save_chest_enabled(self) -> None:
  chest = ChestOpenConfig.from_dict(self.cfg.get("chest_open"))
  chest.enabled = bool(self.var_chest_enabled.get())
  self._update_chest_config(chest)

 # ── Normal Chest ──────────────────────────────────────────

 def _normal_chest_hint_text(self) -> str:
  nc = ChestOpenConfig.from_dict(self.cfg.get("normal_chest"))
  if nc.enabled:
   return f"edMark ({nc.rel_x:.2f}, {nc.rel_y:.2f})"
  return "every15minAutoAuto Open Chest"

 def _update_normal_chest_config(self, nc: ChestOpenConfig) -> None:
  self.cfg.setdefault("normal_chest", {})
  self.cfg["normal_chest"] = nc.to_dict()
  save_config(CONFIG_PATH, self.cfg)
  self.engine.cfg = self.cfg
  self.engine.normal_chest = nc
  # Sync to profile
  try:
   profile = self._get_profile()
   profile.normal_chest = nc.to_dict()
   self._save_profile(profile)
  except Exception:
   pass
  self.var_norm_chest_enabled.set(nc.enabled)
  if hasattr(self, "var_norm_hint"):
   self.var_norm_hint.set(self._normal_chest_hint_text())

 def _save_norm_chest_enabled(self) -> None:
  nc = ChestOpenConfig.from_dict(self.cfg.get("normal_chest"))
  nc.enabled = bool(self.var_norm_chest_enabled.get())
  self._update_normal_chest_config(nc)

 def _mark_normal_chest(self) -> None:
  if not self._require_idle():
   return
  if not find_game_window(
   process_name=self.cfg.get("game", {}).get("process_name", "TaskBarHero"),
   pid=self.cfg.get("game", {}).get("pid"),
  ):
   messagebox.showerror("Error", "Game window not found", parent=self)
   return
  self._run_countdown_capture(
   title="Normal ChestPosition",
   prompt="cursortoNormal Chestbuttonorbox",
   capture_fn=self._capture_normal_chest_pos,
  )

 def _capture_normal_chest_pos(self) -> bool:
  if not self._anchor:
   messagebox.showerror("Error", "Capture window in Settings first", parent=self)
   return False
  mx, my = get_cursor_pos()
  rel_x, rel_y = self._anchor.screen_to_rel(mx, my)
  nc = ChestOpenConfig.from_dict(self.cfg.get("normal_chest"))
  nc.rel_x = round(rel_x, 4)
  nc.rel_y = round(rel_y, 4)
  nc.enabled = True
  nc.interval_seconds = 900
  self._update_normal_chest_config(nc)
  self._append_log(f">>> Normal Chest ({nc.rel_x}, {nc.rel_y})")
  return True

 def _save_click_method(self, _=None) -> None:
  method = self.var_click_method.get()
  # Write chest_open
  self.cfg.setdefault("chest_open", {})
  self.cfg["chest_open"]["click_method"] = method
  # Write portal.ui
  self.cfg.setdefault("portal", {}).setdefault("ui", {})
  self.cfg["portal"]["ui"]["click_method"] = method
  save_config(CONFIG_PATH, self.cfg)
  self.engine.cfg = self.cfg
  self._append_log(f">>> Click method switched to: {method}")

 def _mark_chest(self) -> None:
  if not self._require_idle():
   return
  if not find_game_window(
   process_name=self.cfg.get("game", {}).get("process_name", "TaskBarHero"),
   pid=self.cfg.get("game", {}).get("pid"),
  ):
   messagebox.showerror("Error", "Game window not found", parent=self)
   return
  self._run_countdown_capture(
   title="Auto Open ChestPosition",
   prompt="cursortoAuto Open Chestbuttonorbox",
   capture_fn=self._capture_chest_pos,
  )

 def _capture_chest_pos(self) -> bool:
  if not self._anchor:
   messagebox.showerror("Error", "Capture window in Settings first", parent=self)
   return False
  mx, my = get_cursor_pos()
  rel_x, rel_y = self._anchor.screen_to_rel(mx, my)
  chest = ChestOpenConfig.from_dict(self.cfg.get("chest_open"))
  chest.rel_x = round(rel_x, 4)
  chest.rel_y = round(rel_y, 4)
  chest.enabled = True
  self._update_chest_config(chest)
  self._append_log(f">>> Auto Open Chest ({chest.rel_x}, {chest.rel_y})")
  return True

 def _test_chest_click(self) -> None:
  """Test Boss chest position click."""
  self._test_click("chest_open", "Blue Box")

 def _test_normal_chest_click(self) -> None:
  """Test normal chest (white box) position click."""
  self._test_click("normal_chest", "White Box")

 def _test_click(self, cfg_key: str, label: str) -> None:
  """readConfigCoord,forGameWindowExecutexClick."""
  chest = ChestOpenConfig.from_dict(self.cfg.get(cfg_key))
  if not chest.enabled:
   messagebox.showinfo("Info", f"{label}unEnable,pleasefirstMark Position", parent=self)
   return
  hwnd = find_game_window(
   process_name=self.cfg.get("game", {}).get("process_name", "TaskBarHero"),
   pid=self.cfg.get("game", {}).get("pid"),
  )
  if not hwnd:
   messagebox.showerror("Error", "Game window not found", parent=self)
   return
  if not self._anchor:
   messagebox.showerror("Error", "pleasefirstCaptureWindowPosition", parent=self)
   return
  try:
   used = open_chest(
    hwnd, chest, helper_hwnd=self.winfo_id(), anchor=self._anchor,
   )
   if used:
    self._append_log(
     f">>> [{label} Test] Click @ ({used[0]},{used[1]}) success"
    )
   else:
    self._append_log(f">>> [{label} Test] position invalid, skipping")
  except Exception as exc:
   self._append_log(f">>> [{label} Test] failed: {exc}")
   messagebox.showerror("Clickfailed", str(exc), parent=self)

 # ── Run control ───────────────────────────────────────────

 def _enqueue_log(self, msg: str) -> None:
  self._log_queue.put(msg)

 def _append_log(self, msg: str) -> None:
  txt = self.log_text.text
  txt.configure(state=tk.NORMAL)
  txt.insert(tk.END, msg + "\n")
  txt.see(tk.END)
  txt.configure(state=tk.DISABLED)

 def _drain_log_queue(self) -> None:
  try:
   while True:
    self._append_log(self._log_queue.get_nowait())
  except queue.Empty:
   pass
  self.after(100, self._drain_log_queue)

 def _on_switch(self, stage_name: str, count: int) -> None:
  self.after(0, lambda: self.var_next.set(f"Next -> after {stage_name}"))
  self.after(0, lambda: self.var_stats.set(f"Boss Box {self._drop_count} · Switch {count}"))

 def _on_drop(self, tag: str, item_key: str, triggered: bool) -> None:
  if triggered or tag == "Boss Box":
   self._drop_count += 1
  self.after(
   0,
   lambda: self.var_stats.set(f"Boss Box {self._drop_count} · Switch {self.engine.switch_count}"),
  )

 def _set_running(self, running: bool) -> None:
  self.btn_capture_win.configure_state(tk.NORMAL if not running else tk.DISABLED)
  self.btn_next.configure_state(tk.NORMAL if running else tk.DISABLED)
  text = "Stop Auto" if running else "Startidle"
  self.btn_start.configure(text=text)
  self.btn_start.configure_state(tk.NORMAL)
  self.var_mode.set("Running" if running else "Idle")
  if hasattr(self, "lbl_mode"):
   self.lbl_mode.configure(fg=GOLD if running else TEXT)

 def _capture_window_anchor(self) -> None:
  """CaptureGameWindowClient areaas anchor."""
  if self.engine.is_running:
   messagebox.showwarning("Info", "Stop auto-run first", parent=self)
   return
  hwnd = find_game_window(
   process_name=self.cfg.get("game", {}).get("process_name", "TaskBarHero"),
   pid=self.cfg.get("game", {}).get("pid"),
  )
  if not hwnd:
   messagebox.showerror("unfindtoWindow", "Start TaskBarHero first", parent=self)
   return
  rect = get_client_rect_screen(hwnd)
  # diagnostic:CompareWindowfull rectandClient area,CheckOffsetamount
  try:
   from tbh_helper.window import get_window_rect
   wr = get_window_rect(hwnd)
   self._append_log(
    f" [diagnostic] Window: ({wr.left},{wr.top}) {wr.width}×{wr.height} "
    f"| Client area: ({rect.left},{rect.top}) {rect.width}×{rect.height} "
    f"| Offset: ({rect.left - wr.left},{rect.top - wr.top})"
   )
  except Exception:
   pass
  # Save to config
  self.cfg.setdefault("portal", {})
  self.cfg["portal"]["window_rect"] = [rect.left, rect.top, rect.width, rect.height]
  save_config(CONFIG_PATH, self.cfg)
  # Create anchor immediately
  from tbh_helper.anchor import AnchorRect
  self._anchor = AnchorRect(left=rect.left, top=rect.top, width=rect.width, height=rect.height)
  self.engine.set_anchor(self._anchor)
  self._append_log(
   f">>> WindowanchorCaptured: {rect.width}×{rect.height} @ ({rect.left},{rect.top})"
  )
  self._refresh_status()
  self._refresh_setup_steps()

 def _toggle_overlay(self) -> None:
  """toggle:inGameWindowshow/hide transparent green overlay,visualConfirmCaptureRange."""
  # If overlay exists, destroy it
  if self._overlay is not None:
   try:
    self._overlay.destroy()
   except Exception:
    pass
   self._overlay = None
   self.btn_show_overlay.configure(text="Show Area")
   self._append_log(">>> Area display closed")
   return

  # No overlay, create it
  if not self._anchor:
   if not self.cfg.get("portal", {}).get("window_rect"):
    messagebox.showinfo("Info", "please first Click \"CaptureWindow\"", parent=self)
    return
   r = self.cfg["portal"]["window_rect"]
   from tbh_helper.anchor import AnchorRect
   self._anchor = AnchorRect(left=r[0], top=r[1], width=r[2], height=r[3])
   self.engine.set_anchor(self._anchor)

  # CheckCurrentGameWindowPositionisnotwithanchor
  hwnd = find_game_window(
   process_name=self.cfg.get("game", {}).get("process_name", "TaskBarHero"),
   pid=self.cfg.get("game", {}).get("pid"),
  )
  if hwnd:
   try:
    from tbh_helper.window import get_window_rect
    wr = get_window_rect(hwnd)
    self._append_log(
     f" [Compare] CurrentWindow: ({wr.left},{wr.top}) {wr.width}×{wr.height} "
     f"| Captured: ({self._anchor.left},{self._anchor.top}) {self._anchor.width}×{self._anchor.height}"
    )
   except Exception:
    pass

  a = self._anchor
  self._append_log(
   f">>> WindowRange: ({a.left},{a.top}) ~ ({a.right},{a.bottom}) "
   f"→ {a.width}×{a.height} (Green overlay covers this area)"
  )

  overlay = tk.Toplevel(self)
  overlay.overrideredirect(True)
  overlay.attributes("-topmost", True)
  overlay.attributes("-alpha", 0.35)
  overlay.configure(bg="#00FF00")
  overlay.geometry(f"{a.width}x{a.height}+{a.left}+{a.top}")

  # Green border
  tk.Frame(overlay, bg="#00FF00", highlightthickness=0).place(
   x=0, y=0, width=a.width, height=2)
  tk.Frame(overlay, bg="#00FF00", highlightthickness=0).place(
   x=0, y=a.height - 2, width=a.width, height=2)
  tk.Frame(overlay, bg="#00FF00", highlightthickness=0).place(
   x=0, y=0, width=2, height=a.height)
  tk.Frame(overlay, bg="#00FF00", highlightthickness=0).place(
   x=a.width - 2, y=0, width=2, height=a.height)

  # Click overlay to close
  def _close(evt=None) -> None:
   self._toggle_overlay()

  overlay.bind("<Escape>", _close)
  overlay.bind("<Button-1>", _close)

  self._overlay = overlay
  self.btn_show_overlay.configure(text="Closeshow")
  self._append_log(">>> Area display open (Esc or click overlay to close)")

 def _start(self) -> None:
  self._start_engine(dry_run=False)

 def _start_watch(self) -> None:
  self._start_engine(dry_run=True)

 def _pick_start_stage(self, stages: list[dict]) -> int | None:
  """dialog to letUserSelectfromwhichStageStartswitch,returnIndex(0-based)."""
  if len(stages) <= 1:
   return 0

  names = [s.get("name", f"Stage {i + 1}") for i, s in enumerate(stages)]
  dialog = tk.Toplevel(self)
  dialog.title("SelectstartStage")
  dialog.configure(bg=BG)
  dialog.resizable(False, False)

  dialog.transient(self)
  dialog.grab_set()

  result: list[int | None] = [None]

  tk.Label(dialog, text="SelectidleStartStage:", font=FONT_UI,
     bg=BG, fg=TEXT, anchor=tk.W).pack(fill=tk.X, padx=16, pady=(14, 6))

  # Dynamic height:min 4 row,max 6 row,exceedScroll
  n = len(names)
  visible_rows = max(4, min(n, 6))
  row_h = 22 # approxrowheight
  list_h = visible_rows * row_h

  frame = tk.Frame(dialog, bg=BG)
  frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

  lb = tk.Listbox(frame, bg=SURFACE, fg=TEXT, selectbackground=ACCENT,
      selectforeground="#FFFFFF", font=FONT_UI,
      relief=tk.FLAT, borderwidth=0, highlightthickness=0,
      height=visible_rows)
  lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
  style_listbox(lb)

  scroll = StyledScrollbar(frame, command=lb.yview)
  scroll.pack(side=tk.RIGHT, fill=tk.Y)
  lb.configure(yscrollcommand=scroll.set)

  for name in names:
   lb.insert(tk.END, name)
  lb.selection_set(0) # defaultselectpage

  def _confirm() -> None:
   sel = lb.curselection()
   if sel:
    result[0] = sel[0]
   dialog.destroy()

  def _cancel() -> None:
   dialog.destroy()

  # Double-click to select
  lb.bind("<Double-Button-1>", lambda _: _confirm())

  btn_frame = tk.Frame(dialog, bg=BG)
  btn_frame.pack(fill=tk.X, padx=16, pady=(0, 14))

  btn_cancel = RoundedButton(btn_frame, "Cancel", _cancel, width=90, height=34, radius=10)
  btn_cancel.pack(side=tk.LEFT)

  btn_ok = RoundedButton(btn_frame, "Confirm", _confirm, width=90, height=34, radius=10)
  btn_ok.pack(side=tk.RIGHT)

  dialog.protocol("WM_DELETE_WINDOW", _cancel)

  # CalculateWindowsize:title + List + button + padding
  title_h = 32 # approx
  btn_h = 34
  pad_v = 14 + 6 + 8 + 14 # pady totaland
  win_h = title_h + list_h + btn_h + pad_v
  win_w = 360
  px = self.winfo_x() + (self.winfo_width() - win_w) // 2
  py = self.winfo_y() + (self.winfo_height() - win_h) // 2
  dialog.geometry(f"{win_w}x{win_h}+{px}+{py}")

  dialog.wait_window()
  return result[0]

 def _start_engine(self, *, dry_run: bool) -> None:
  if self.engine.is_running:
   self._stop()
   return

  # ── anchorsetup:useWindowClient areaas anchor ──
  portal_cfg = self.cfg.get("portal", {})
  saved_rect = portal_cfg.get("window_rect")
  if not saved_rect or len(saved_rect) != 4:
   messagebox.showinfo("Info", "please first in \"Setup\" Click \"CaptureWindow\"", parent=self)
   return

  hwnd = find_game_window(
   process_name=self.cfg.get("game", {}).get("process_name", "TaskBarHero"),
   pid=self.cfg.get("game", {}).get("pid"),
  )
  if not hwnd:
   messagebox.showerror("unfindtoWindow", "Start TaskBarHero first", parent=self)
   return

  cur_rect = get_client_rect_screen(hwnd)
  if [cur_rect.left, cur_rect.top, cur_rect.width, cur_rect.height] != saved_rect:
   msg = (
    f"GameWindowPositionedchanged!\n\n"
    f"Previous record: @ ({saved_rect[0]},{saved_rect[1]}) {saved_rect[2]}×{saved_rect[3]}\n"
    f"CurrentWindow: @ ({cur_rect.left},{cur_rect.top}) {cur_rect.width}×{cur_rect.height}\n\n"
    f"isnotReCaptureWindowPosition?"
   )
   if not messagebox.askyesno("WindowPositionchanged", msg, parent=self):
    return
   self.cfg["portal"]["window_rect"] = [
    cur_rect.left, cur_rect.top, cur_rect.width, cur_rect.height
   ]
   save_config(CONFIG_PATH, self.cfg)
   self._append_log(f">>> WindowPositionUpdated: {cur_rect.width}×{cur_rect.height}")

  from tbh_helper.anchor import AnchorRect
  self._anchor = AnchorRect(
   left=cur_rect.left, top=cur_rect.top,
   width=cur_rect.width, height=cur_rect.height,
  )
  self.engine.set_anchor(self._anchor)
  profile = self._get_profile()
  if not profile.stages:
   messagebox.showerror("Missing nodes", "pleasefirstinSetupAddRotation Nodes", parent=self)
   return
  if not profile.chapter_tabs or not profile.difficulty_options:
   if not messagebox.askyesno("unDoneMark", "Portal UI not yetunMark,Switchcancanfailed.Continue?", parent=self):
    return

  # SelectstartStage
  start_idx = self._pick_start_stage(profile.stages)
  if start_idx is None:
   return # UserCancel

  # VerifyandSaveTimeoutConfig
  raw = self.var_timeout_minutes.get().strip()
  if not self._validate_timeout_input(raw):
   return
  # VerifyafterReread(VerifycancanwillEmptyas "0")
  timeout_val = int(self.var_timeout_minutes.get().strip())
  self.cfg.setdefault("rotation", {})
  self.cfg["rotation"]["stage_timeout_minutes"] = timeout_val

  # SaveWarehouseTimedConfig
  wh_raw = self.var_warehouse_interval.get().strip()
  try:
   wh_val = int(wh_raw) if wh_raw else 30
   if wh_val < 0:
    wh_val = 30
  except (ValueError, TypeError):
   wh_val = 30
  self.cfg.setdefault("warehouse", {})
  self.cfg["warehouse"]["enabled"] = self.var_warehouse_enabled.get()
  self.cfg["warehouse"]["interval_minutes"] = wh_val

  self.cfg.setdefault("mailbox_check", {})["enabled"] = self.var_mailbox_enabled.get()

  self.cfg.setdefault("fold_page", {})["mode"] = self.var_fold_mode.get()

  save_config(CONFIG_PATH, self.cfg)

  self.engine.set_anchor(self._anchor)
  self._drop_count = 0
  self.engine.helper_hwnd = self.winfo_id()
  try:
   self.engine.start(dry_run=dry_run, start_index=start_idx)
  except Exception as exc:
   messagebox.showerror("Launchfailed", str(exc), parent=self)
   return

  self._set_running(True)
  self.var_mode.set("Monitor Only" if dry_run else "Running")
  self._append_log(">>> Started")

 def _stop(self) -> None:
  self.engine.stop()
  self._set_running(False)
  self._append_log(f">>> Stopped. Switches {self.engine.switch_count} x")

 def _next_stage(self) -> None:
  """Manual switch to next stage -- button grays out immediately, restores on completion."""
  if not self.engine.is_running:
   return
  self.btn_next.configure_state(tk.DISABLED)
  self.engine.switch_now()
  self._append_log(">>> Requesting switch to next stage")

 def _on_manual_switch_done(self) -> None:
  """Re-enable button after manual switch completes."""
  if self.engine.is_running:
   self.btn_next.configure_state(tk.NORMAL)

 def _validate_timeout_input(self, raw: str) -> bool:
  """Validate stage timeout minutes. Must be non-negative integer. 0=disabled.."""
  if not raw:
   self.var_timeout_minutes.set("0")
   return True
  try:
   val = int(raw)
  except ValueError:
   messagebox.showerror("Input error", "TimeoutSwitch stagemustinputcount(min)\ninput 0 Closethis featcan", parent=self)
   self.entry_timeout.focus_set()
   return False
  if val < 0:
   messagebox.showerror("Input error", "Stage timeout cannot be negative.", parent=self)
   self.entry_timeout.focus_set()
   return False
  return True

 def _on_timeout_focus_out(self, _=None) -> None:
  """Validate and save when focus leaves timeout input."""
  raw = self.var_timeout_minutes.get().strip()
  if self._validate_timeout_input(raw):
   # Reread(VerifycancanwillEmptyas "0")
   val = int(self.var_timeout_minutes.get().strip())
   self.var_timeout_minutes.set(str(val))
   self.cfg.setdefault("rotation", {})
   self.cfg["rotation"]["stage_timeout_minutes"] = val
   save_config(CONFIG_PATH, self.cfg)

 def on_close(self) -> None:
  if self.engine.is_running:
   if not messagebox.askyesno("Exit", "idlestillinRun,confirmExit?", parent=self):
    return
   self.engine.stop()
  self._stats_visible = False
  self.destroy()

 # ── Warehouse Tabs ──────────────────────────────────────────

 def _add_warehouse_page(self) -> None:
  if not self._require_idle() or not self._require_anchor():
   return
  profile = self._get_profile()
  idx = len(profile.warehouse_tab_pages) + 1
  default_name = f"page{idx}Page"

  def capture() -> bool:
   rel = self._capture_cursor_in_anchor(warn_outside=False)
   if rel is None:
    return False
   page = {"name": default_name, "rel_x": rel[0], "rel_y": rel[1]}
   profile = self._get_profile()
   profile.warehouse_tab_pages.append(page)
   self._save_profile(profile, capture_template=bool(self._anchor))
   self._append_log(f">>> AddWarehouse Tabs {default_name} @ ({rel[0]}, {rel[1]})")
   self._refresh_warehouse_ui()
   return True

  self._run_countdown_capture(
   title="AddWarehouse Tabs",
   prompt=f'Move cursor to "{default_name}" tab position',
   capture_fn=capture,
  )

 def _remark_warehouse_page(self) -> None:
  if not self._require_idle() or not self._require_anchor():
   return
  sel = self.warehouse_list.curselection()
  if not sel:
   messagebox.showinfo("Info", "Select a tab first", parent=self)
   return
  idx = sel[0]
  profile = self._get_profile()
  if idx >= len(profile.warehouse_tab_pages):
   return
  page = profile.warehouse_tab_pages[idx]
  name = page.get("name", f"page{idx + 1}Page")

  def capture() -> bool:
   rel = self._capture_cursor_in_anchor(warn_outside=False)
   if rel is None:
    return False
   profile = self._get_profile()
   profile.warehouse_tab_pages[idx]["rel_x"] = rel[0]
   profile.warehouse_tab_pages[idx]["rel_y"] = rel[1]
   self._save_profile(profile, capture_template=bool(self._anchor))
   self._append_log(f">>> re-markWarehouse Tabs {name} @ ({rel[0]}, {rel[1]})")
   self._refresh_warehouse_ui()
   return True

  self._run_countdown_capture(
   title=f"re-mark · {name}",
   prompt=f'Move cursor to "{name}" tab position',
   capture_fn=capture,
  )

 def _delete_warehouse_page(self) -> None:
  if not self._require_idle():
   return
  sel = self.warehouse_list.curselection()
  if not sel:
   self.after(1, lambda: messagebox.showinfo("Info", "pleasefirstselecttoDeleteTabPage", parent=self))
   return
  idx = sel[0]
  profile = self._get_profile()
  if idx >= len(profile.warehouse_tab_pages):
   return
  name = profile.warehouse_tab_pages[idx].get("name", f"page{idx + 1}Page")
  ok = messagebox.askyesno("Confirm Delete", f'Delete warehouse tab "{name}"?', parent=self)
  if not ok:
   return
  del profile.warehouse_tab_pages[idx]
  # Rename subsequent pages
  for i, p in enumerate(profile.warehouse_tab_pages):
   p["name"] = f"page{i + 1}Page"
  self._save_profile(profile, capture_template=bool(self._anchor))
  self._append_log(f">>> edDeleteWarehouse Tabs {name}")
  self._refresh_warehouse_ui()

 def _mark_warehouse_transfer(self) -> None:
  if not self._require_idle() or not self._require_anchor():
   return

  def capture() -> bool:
   rel = self._capture_cursor_in_anchor(warn_outside=False)
   if rel is None:
    return False
   profile = self._get_profile()
   profile.warehouse_transfer_btn = [rel[0], rel[1]]
   self._save_profile(profile, capture_template=bool(self._anchor))
   self._append_log(f">>> Transfer Button @ ({rel[0]}, {rel[1]})")
   self._refresh_warehouse_ui()
   return True

  self._run_countdown_capture(
   title="MarkTransfer Button",
   prompt="Move cursor to fromInventoryTransfertoWarehouse buttonPosition",
   capture_fn=capture,
  )

 def _refresh_warehouse_ui(self) -> None:
  """RefreshWarehouse TabsListandTransferbuttonInfo."""
  if not hasattr(self, "warehouse_list"):
   return
  profile = self._get_profile()

  # RefreshTabPageList
  self.warehouse_list.delete(0, tk.END)
  pages = profile.warehouse_tab_pages
  if not pages:
   self.warehouse_list.insert(tk.END, " No tabs yet. Click + Add")
   self._adjust_warehouse_list_height(0)
  else:
   for i, p in enumerate(pages, 1):
    name = p.get("name", f"page{i}Page")
    self.warehouse_list.insert(tk.END, f" {i}. {name}")
   self._adjust_warehouse_list_height(len(pages))

  # RefreshTransferbuttonInfo
  btn = profile.warehouse_transfer_btn
  if btn and len(btn) >= 2:
   self.var_transfer_hint.set(f"({btn[0]:.3f}, {btn[1]:.3f})")
  else:
   self.var_transfer_hint.set("Not marked")
  # RefreshbuttonInfo
  self._refresh_mailbox_hints()

 def _save_warehouse_config(self, _=None) -> None:
  """SaveWarehouseTimedConfig."""
  raw = self.var_warehouse_interval.get().strip()
  try:
   val = int(raw) if raw else 30
   if val < 0:
    raise ValueError
  except (ValueError, TypeError):
   messagebox.showerror("Input error", "Interval minutes must be a non-negative integer", parent=self)
   self.var_warehouse_interval.set("30")
   return
  self.cfg.setdefault("warehouse", {})["enabled"] = self.var_warehouse_enabled.get()
  self.cfg["warehouse"]["interval_minutes"] = val
  save_config(CONFIG_PATH, self.cfg)
  self.engine.cfg = self.cfg
  self._append_log(f">>> WarehouseConfigedSave({'Enable' if self.var_warehouse_enabled.get() else 'Close'},every {val} min)")

 # ── Mailbox check button markers ────────────────────────────────────

 MAILBOX_BUTTON_LABELS = {
  "open": "Open",
  "refresh": "Refresh",
  "receive_all": "Receive All",
  "close": "Close",
 }

 def _mark_mailbox_button(self, key: str) -> None:
  if not self._require_idle() or not self._require_anchor():
   return
  label = self.MAILBOX_BUTTON_LABELS.get(key, key)

  def capture() -> bool:
   rel = self._capture_cursor_in_anchor(warn_outside=False)
   if rel is None:
    return False
   profile = self._get_profile()
   profile.mailbox_buttons[key] = [rel[0], rel[1]]
   self._save_profile(profile, capture_template=bool(self._anchor))
   self._append_log(f">>> {label} @ ({rel[0]}, {rel[1]})")
   self._refresh_mailbox_hints()
   return True

  self._run_countdown_capture(
   title=f"Mark {label}",
   prompt=f"cursor to Game inside \"{label}\" buttonPosition",
   capture_fn=capture,
  )

 def _refresh_mailbox_hints(self) -> None:
  if not hasattr(self, "_mail_hint_vars"):
   return
  profile = self._get_profile()
  for key, var in self._mail_hint_vars.items():
   pos = profile.mailbox_buttons.get(key)
   if pos and len(pos) >= 2:
    var.set(f"({pos[0]:.3f}, {pos[1]:.3f})")
   else:
    var.set("✗")

 def _save_mailbox_config(self) -> None:
  """Save mailbox check toggle."""
  val = self.var_mailbox_enabled.get()
  self.cfg.setdefault("mailbox_check", {})["enabled"] = val
  save_config(CONFIG_PATH, self.cfg)
  self.engine.cfg = self.cfg
  self.engine.mailbox_check_enabled = val
  self._append_log(
   f">>> Mailbox Timeout Checked{'Enable' if val else 'Close'}"
  )


def main() -> None:
 if sys.platform == "win32":
  try:
   from tbh_helper.window import enable_dpi_awareness
   enable_dpi_awareness()
  except Exception:
   pass
 app = TBHApp()
 app.protocol("WM_DELETE_WINDOW", app.on_close)
 app.mainloop()


if __name__ == "__main__":
 main()

