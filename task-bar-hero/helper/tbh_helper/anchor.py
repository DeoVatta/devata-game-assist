from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnchorRect:
    """屏幕上的锚点矩形区域。"""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def to_screen(self, rel_x: float, rel_y: float) -> tuple[int, int]:
        x = self.left + int(self.width * rel_x)
        y = self.top + int(self.height * rel_y)
        return x, y

    def contains_screen(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def screen_to_rel(self, screen_x: int, screen_y: int) -> tuple[float, float]:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("锚点区域尺寸无效")
        rel_x = (screen_x - self.left) / self.width
        rel_y = (screen_y - self.top) / self.height
        return round(rel_x, 4), round(rel_y, 4)

    def to_dict(self) -> dict:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AnchorRect:
        return cls(
            left=int(d["left"]),
            top=int(d["top"]),
            width=int(d["width"]),
            height=int(d["height"]),
        )
