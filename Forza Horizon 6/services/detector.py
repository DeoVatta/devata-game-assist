"""
Unified game detector — orchestrates all detection sources.
Provides priority-based detection with confidence scoring.
"""
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime
import time

import psutil

from config import DETECTION_INTERVAL
from detection import process as process_detector
from detection import window as window_detector
from detection import xbox as xbox_detector
from detection import stream as stream_detector


@dataclass
class DetectionResult:
    source: str
    detected: bool
    confidence: float   # 0.0 - 1.0
    details: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class GameState:
    is_running:       bool = False
    process_running:  bool = False
    window_active:   bool = False
    xbox_installed:  bool = False
    streaming:       bool = False
    results: List[DetectionResult] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)


class GameDetector:
    """
    Unified detector for a game.
    Inject game-specific config via constructor.
    Call detect_all() or start_watch() for continuous monitoring.
    """

    def __init__(
        self,
        process_names: List[str],
        window_titles: List[str],
        xbox_ids: List[str],
    ):
        self._proc  = process_names
        self._win   = window_titles
        self._xbox  = xbox_ids
        self.state: GameState = GameState()
        self._cbs: List[Callable] = []

    def on_state_change(self, cb: Callable[[GameState], None]):
        """Register callback(state) called on game state transitions."""
        self._cbs.append(cb)

    def _notify(self):
        for cb in self._cbs:
            try:
                cb(self.state)
            except Exception:
                pass

    def detect_all(self) -> GameState:
        """Run all detection sources. Returns updated GameState."""
        results: List[DetectionResult] = []

        # 1 — Process (fastest, highest confidence)
        procs = process_detector.get_forza_processes(self._proc)
        proc_running = bool(procs)
        results.append(DetectionResult(
            source="process", detected=proc_running,
            confidence=1.0 if proc_running else 0.0,
            details={"count": len(procs)}
        ))

        # 2 — Window (works for any launch method)
        wins     = window_detector.find_forza_windows(self._win)
        win_act  = window_detector.is_game_window_active(self._win)
        results.append(DetectionResult(
            source="window", detected=bool(wins),
            confidence=1.0 if win_act else (0.7 if wins else 0.0),
            details={"windows": wins, "is_foreground": win_act}
        ))

        # 3 — Xbox App / Game Pass
        xbox_ok = xbox_detector.is_xbox_game_in_library(self._xbox, self._win)
        results.append(DetectionResult(
            source="xbox", detected=xbox_ok,
            confidence=0.8 if xbox_ok else 0.0, details={}
        ))

        # 4 — OBS Stream Source
        obs_on  = stream_detector.is_obs_running()
        fh_obs  = stream_detector.is_forza_in_obs_sources() if obs_on else False
        results.append(DetectionResult(
            source="stream", detected=fh_obs,
            confidence=0.8 if fh_obs else 0.0,
            details={"obs_running": obs_on}
        ))

        prev = self.state.is_running
        self.state = GameState(
            is_running=proc_running or bool(wins),
            process_running=proc_running,
            window_active=win_act,
            xbox_installed=xbox_ok,
            streaming=fh_obs,
            results=results,
            last_updated=datetime.now(),
        )

        if prev != self.state.is_running:
            self._notify()

        return self.state

    def is_running(self) -> bool:
        return self.state.is_running

    def start_watch(self, interval: float = DETECTION_INTERVAL):
        """Continuous monitoring. Press Ctrl+C to stop."""
        print(f"[GameDetector] Watching (every {interval}s)...")
        self.detect_all()
        try:
            while True:
                time.sleep(interval)
                self.detect_all()
                s = self.state
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"{'RUNNING' if s.is_running else 'IDLE'} | "
                    f"proc:{'✓' if s.process_running else '✗'} "
                    f"win:{'✓' if s.window_active else '✗'} "
                    f"xbox:{'✓' if s.xbox_installed else '✗'} "
                    f"stream:{'✓' if s.streaming else '✗'}"
                )
        except KeyboardInterrupt:
            print("\n[GameDetector] Stopped.")

    def quick_detect(self) -> Dict[str, bool]:
        """One-shot detection dict. Fastest for automation triggers."""
        proc = process_detector.is_game_running(self._proc)
        wins = len(window_detector.find_forza_windows(self._win)) > 0
        return {"process": proc, "window": wins, "running": proc or wins}
