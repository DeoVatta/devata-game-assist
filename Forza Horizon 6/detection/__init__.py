"""
Game detection sources.
Each module exposes: detect() -> bool
"""
from . import process as process_detector
from . import window as window_detector
from . import xbox as xbox_detector
from . import stream as stream_detector

__all__ = ["process_detector", "window_detector", "xbox_detector", "stream_detector"]
