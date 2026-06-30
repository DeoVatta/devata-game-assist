from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal, Protocol

from .mouse import click_at, double_click_at
from .scroll import scroll_wheel_clicks
from .window import WindowRect

Difficulty = Literal["normal", "nightmare", "hell", "torment"]


class CoordSpace(Protocol):
    def to_screen(self, rel_x: float, rel_y: float) -> tuple[int, int]: ...


@dataclass
class PortalUIConfig:
    """UI 控件在坐标空间内的相对位置 (0~1)。"""

    chapter_tabs: dict[int, tuple[float, float]] = field(default_factory=dict)
    difficulty_dropdown: tuple[float, float] = (0.5, 0.15)
    difficulty_options: dict[str, tuple[float, float]] = field(
        default_factory=lambda: {
            "normal": (0.5, 0.22),
            "nightmare": (0.5, 0.28),
            "hell": (0.5, 0.34),
            "torment": (0.5, 0.40),
        }
    )
    map_scroll_area: tuple[float, float] = (0.5, 0.55)
    scroll_clicks_down_to_1_7: int = 5
    scroll_clicks_up_to_8_10: int = 5
    scroll_method: str = "sendinput"
    scroll_interval: float = 0.06
    action_delay: float = 0.35
    click_method: str = "auto"
    focus_delay: float = 0.2
    move_delay: float = 0.08
    click_hold: float = 0.05


@dataclass
class StageTarget:
    name: str
    chapter: int
    difficulty: Difficulty
    stage_num: int
    rel_x: float
    rel_y: float
    scroll_page: int | None = None

    def resolved_scroll_page(self) -> int:
        if self.scroll_page is not None:
            return self.scroll_page
        return 1 if self.stage_num >= 8 else 0


class PortalNavigator:
    def __init__(
        self,
        ui: PortalUIConfig,
        coord_space: CoordSpace,
        *,
        hwnd: int,
        open_portal: bool = False,
        portal_button_rel: tuple[float, float] | None = None,
        portal_button_space: WindowRect | None = None,
        helper_hwnd: int | None = None,
    ) -> None:
        self.ui = ui
        self.coord_space = coord_space
        self.hwnd = hwnd
        self.helper_hwnd = helper_hwnd
        self.open_portal = open_portal
        self.portal_button_rel = portal_button_rel
        self.portal_button_space = portal_button_space
        self._scroll_page: int | None = None

    def reset_state(self) -> None:
        self._scroll_page = None

    def _screen(self, rel_x: float, rel_y: float) -> tuple[int, int]:
        return self.coord_space.to_screen(rel_x, rel_y)

    def _click_opts(self) -> dict:
        return {
            "helper_hwnd": self.helper_hwnd,
            "method": self.ui.click_method,  # type: ignore[arg-type]
            "focus_delay": self.ui.focus_delay,
            "move_delay": self.ui.move_delay,
            "click_hold": self.ui.click_hold,
        }

    def _click_rel(self, rel_x: float, rel_y: float) -> None:
        x, y = self._screen(rel_x, rel_y)
        used = click_at(self.hwnd, x, y, **self._click_opts())
        print(f"[点击] ({x},{y}) 方式={used}")
        time.sleep(self.ui.action_delay)

    def _scroll_at(self, clicks: int) -> None:
        x, y = self._screen(*self.ui.map_scroll_area)
        used = double_click_at(
            self.hwnd,
            x,
            y,
            click_interval=max(self.ui.scroll_interval, 0.12),
            **self._click_opts(),
        )
        time.sleep(self.ui.action_delay * 0.5)
        scroll_used = scroll_wheel_clicks(
            self.hwnd,
            x,
            y,
            clicks,
            method=self.ui.scroll_method,  # type: ignore[arg-type]
            interval=self.ui.scroll_interval,
        )
        print(
            f"[滚轮] 先双击聚焦({used}) -> {'向上' if clicks > 0 else '向下'} "
            f"x{abs(clicks)} @ ({x},{y}) 方式={scroll_used}"
        )
        time.sleep(self.ui.action_delay)

    def open_portal_if_needed(self) -> None:
        if not self.open_portal or not self.portal_button_rel or not self.portal_button_space:
            return
        x, y = self.portal_button_space.to_screen(*self.portal_button_rel)
        click_at(self.hwnd, x, y, **self._click_opts())
        time.sleep(0.5)

    def select_chapter(self, chapter: int) -> None:
        tab = self.ui.chapter_tabs.get(chapter)
        if not tab:
            raise ValueError(f"未配置第 {chapter} 章标签坐标")
        self._click_rel(*tab)
        self._scroll_page = None

    def select_difficulty(self, difficulty: Difficulty) -> None:
        self._click_rel(*self.ui.difficulty_dropdown)
        option = self.ui.difficulty_options.get(difficulty)
        if not option:
            raise ValueError(f"未配置难度 {difficulty} 选项坐标")
        self._click_rel(*option)
        self._scroll_page = None

    def set_scroll_page(self, page: int) -> None:
        if self._scroll_page == page:
            return
        if page == 0:
            self._scroll_at(-self.ui.scroll_clicks_down_to_1_7)
        else:
            self._scroll_at(self.ui.scroll_clicks_up_to_8_10)
        self._scroll_page = page

    def navigate_to_stage(self, target: StageTarget) -> None:
        self.select_difficulty(target.difficulty)
        self.select_chapter(target.chapter)
        self.set_scroll_page(target.resolved_scroll_page())

    def click_stage_node(self, target: StageTarget) -> None:
        self._click_rel(target.rel_x, target.rel_y)
