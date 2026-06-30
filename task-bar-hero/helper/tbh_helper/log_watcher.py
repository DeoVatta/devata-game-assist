from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


BOX_PATTERN = re.compile(
    r"GetBoxCount Success Count : (?P<count>\d+) // ItemKey : (?P<key>\d+)"
)

# ItemKey 规律（Player.log）:
#   92xxxx = Boss 箱（关卡 Boss / 蓝箱，内置 CD —— 换图触发目标）
#   93xxxx = 超级 Boss 箱（不触发换图）


@dataclass(frozen=True)
class BoxDropEvent:
    count: int
    item_key: str
    raw_line: str
    detected_at: float = field(default_factory=time.time)

    @property
    def box_type(self) -> str:
        if self.item_key.startswith("93"):
            return "super_boss"
        if self.item_key.startswith("92"):
            return "boss"
        return "other"


@dataclass
class DetectConfig:
    boss_key_prefix: str = "92"
    exclude_key_prefix: str = "93"
    boss_item_keys: set[str] = field(default_factory=set)
    exclude_item_keys: set[str] = field(default_factory=set)
    debounce_seconds: float = 10.0
    trigger_on_white: bool = False

    @classmethod
    def from_dict(cls, log_cfg: dict, detect_cfg: dict | None = None) -> DetectConfig:
        detect_cfg = detect_cfg or {}
        boss_keys = detect_cfg.get("boss_item_keys") or []
        exclude_keys = detect_cfg.get("exclude_item_keys") or []
        prefix = str(
            detect_cfg.get(
                "boss_key_prefix",
                log_cfg.get("boss_key_prefix", "92"),
            )
        )
        exclude_prefix = str(
            detect_cfg.get(
                "exclude_key_prefix",
                log_cfg.get("exclude_key_prefix", "93"),
            )
        )
        return cls(
            boss_key_prefix=prefix,
            exclude_key_prefix=exclude_prefix,
            boss_item_keys={str(k) for k in boss_keys},
            exclude_item_keys={str(k) for k in exclude_keys},
            debounce_seconds=float(detect_cfg.get("debounce_seconds", 10.0)),
            trigger_on_white=bool(detect_cfg.get("trigger_on_white", False)),
        )


class LogTailWatcher:
    def __init__(self, log_path: Path, config: DetectConfig) -> None:
        self.log_path = log_path
        self.config = config
        self._pos = 0
        self._last_trigger: dict[str, float] = {}

    def _ensure_open(self) -> None:
        if not self.log_path.exists():
            raise FileNotFoundError(f"日志不存在: {self.log_path}")

    def seek_end(self) -> None:
        self._ensure_open()
        self._pos = self.log_path.stat().st_size

    def poll_raw(self) -> Iterator[BoxDropEvent]:
        self._ensure_open()
        size = self.log_path.stat().st_size
        if size < self._pos:
            self._pos = 0
        if size == self._pos:
            return

        with self.log_path.open("r", encoding="utf-8", errors="ignore") as f:
            f.seek(self._pos)
            chunk = f.read()
            self._pos = f.tell()

        for line in chunk.splitlines():
            match = BOX_PATTERN.search(line)
            if not match:
                continue
            yield BoxDropEvent(
                count=int(match.group("count")),
                item_key=match.group("key"),
                raw_line=line.strip(),
            )

    def is_excluded(self, event: BoxDropEvent) -> bool:
        if event.item_key in self.config.exclude_item_keys:
            return True
        if self.config.exclude_key_prefix and event.item_key.startswith(
            self.config.exclude_key_prefix
        ):
            return True
        return False

    def is_boss_box(self, event: BoxDropEvent) -> bool:
        """是否为目标 Boss 箱（92 前缀，排除超级 Boss 93）。"""
        if self.is_excluded(event):
            return False
        if event.item_key in self.config.boss_item_keys:
            return True
        return event.item_key.startswith(self.config.boss_key_prefix)

    # 兼容旧名
    is_blue_box = is_boss_box

    def _is_debounced(self, item_key: str) -> bool:
        last = self._last_trigger.get(item_key, 0.0)
        return time.time() - last < self.config.debounce_seconds

    def mark_triggered(self, item_key: str) -> None:
        self._last_trigger[item_key] = time.time()

    def should_trigger(self, event: BoxDropEvent) -> bool:
        if self.is_boss_box(event):
            if self._is_debounced(event.item_key):
                return False
            self.mark_triggered(event.item_key)
            return True
        if self.config.trigger_on_white:
            if self._is_debounced(event.item_key):
                return False
            self.mark_triggered(event.item_key)
            return True
        return False

    def would_trigger(self, event: BoxDropEvent) -> bool:
        if not self.is_boss_box(event) and not self.config.trigger_on_white:
            return False
        return not self._is_debounced(event.item_key)

    def poll_triggers(self) -> Iterator[BoxDropEvent]:
        for event in self.poll_raw():
            if self.should_trigger(event):
                yield event


def wait_for_log(log_path: Path, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log_path.exists():
            return
        time.sleep(0.5)
    raise TimeoutError(f"等待日志文件超时: {log_path}")


def box_type_label(item_key: str) -> str:
    if item_key.startswith("93"):
        return "超级Boss箱"
    if item_key.startswith("92"):
        return "Boss箱"
    return "其他"


def scan_history(log_path: Path, config: DetectConfig) -> tuple[list[BoxDropEvent], list[BoxDropEvent]]:
    if not log_path.exists():
        return [], []
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    all_events: list[BoxDropEvent] = []
    for line in text.splitlines():
        match = BOX_PATTERN.search(line)
        if not match:
            continue
        all_events.append(
            BoxDropEvent(
                count=int(match.group("count")),
                item_key=match.group("key"),
                raw_line=line.strip(),
            )
        )
    watcher = LogTailWatcher(log_path, config)
    boss = [e for e in all_events if watcher.is_boss_box(e)]
    return all_events, boss
