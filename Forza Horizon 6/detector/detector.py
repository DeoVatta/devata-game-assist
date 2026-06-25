# ============================================================
#  detector.py — Template matching engine for Forza Horizon 6
#
#  Mirrors FAFE detector.py architecture:
#    - 33 named UI states with ROI + OCR hints
#    - Multi-scale matchTemplate (7 structural / 3 text)
#    - Gray + Canny edge composite scoring
#    - ROI-first with periodic full-screen fallback
#    - Stability filter (N consecutive frames)
#    - OCR confirmation (RapidOCR + pytesseract fallback)
#    - Adaptive ROI from capture box metadata
#
#  Dependencies:
#    pip install opencv-python numpy
#    pip install onnxruntime  # RapidOCR backend
#    # pip install rapidocr_onnxruntime  # or rapidocrapi
#    # pip install pytesseract  # fallback OCR
# ============================================================

import os
import sys
import time
import threading
import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Callable, Dict, List, Tuple, Any

# ── Constants ─────────────────────────────────────────────────

# Structural templates (textured/edge-heavy) — use 7 scales
STRUCTURAL_SCALES = [0.50, 0.60, 0.70, 0.80, 0.90, 1.00, 1.10]
# Text templates (pure text / clean edges) — use 3 scales
TEXT_SCALES       = [0.80, 0.90, 1.00]

# Thresholds
DEFAULT_THRESHOLD    = 0.70
STRICT_THRESHOLD     = 0.80
OCR_CONFIRM_THRESHOLD = 0.60  # template threshold below which OCR kicks in

# Stability filter — require N consecutive detections before confirming
DEFAULT_STABLE_FRAMES = 3

# Full-screen fallback interval — how often to do a full scan (seconds)
FULL_SCAN_INTERVAL = 5.0

# ROI scale counts per template type
_SCALES_STRUCTURAL = 7
_SCALES_TEXT = 3

# ── Template ROI definitions ──────────────────────────────────
# Each state: (x_ratio, y_ratio, w_ratio, h_ratio) in [0..1]
# Ratios are relative to the CONTENT BOX (16:9 centered), not raw frame
# For in-game HUD elements, anchoring is screen-edges

DEFAULT_ROIS: Dict[str, Tuple[float, float, float, float]] = {
    # ── Menu states ──
    "start_menu":         (0.30, 0.38, 0.40, 0.30),
    "main_menu":          (0.10, 0.10, 0.80, 0.80),
    "my_horizon_tab":     (0.70, 0.00, 0.30, 0.12),
    "creative_hub":       (0.00, 0.00, 0.25, 0.18),
    "eventlab":           (0.25, 0.18, 0.25, 0.15),
    "play_event":         (0.50, 0.33, 0.25, 0.15),
    "my_history":         (0.35, 0.55, 0.30, 0.12),
    "choose_race_type":   (0.20, 0.30, 0.60, 0.40),
    "car_select":         (0.30, 0.20, 0.40, 0.35),
    "next_activity":      (0.25, 0.30, 0.50, 0.40),
    # ── Race states ──
    "racing":             (0.35, 0.30, 0.30, 0.20),
    "restart_menu":       (0.30, 0.30, 0.40, 0.35),
    "confirm_race":      (0.35, 0.45, 0.30, 0.15),
    # ── Wheel spin states ──
    "super_wheelspin":    (0.00, 0.20, 0.35, 0.60),
    "normal_wheelspin":   (0.00, 0.20, 0.35, 0.60),
    "wheelspin_skip":     (0.40, 0.80, 0.20, 0.10),
    "wheelspin_collect":  (0.35, 0.70, 0.30, 0.15),
    "wheelspin_collect_final": (0.35, 0.70, 0.30, 0.15),
    "wheelspin_duplicate":(0.25, 0.35, 0.50, 0.30),
    # ── Garage / car states ──
    "my_cars":            (0.05, 0.10, 0.30, 0.80),
    "car_detail":         (0.20, 0.15, 0.60, 0.70),
    "buy_car":            (0.35, 0.70, 0.30, 0.15),
    "confirm_buy":       (0.35, 0.45, 0.30, 0.15),
    # ── Mastery states ──
    "mastery_ride_car":   (0.30, 0.60, 0.40, 0.20),
    "mastery_upgrade":    (0.40, 0.35, 0.20, 0.12),
    "mastery_tree":       (0.05, 0.05, 0.90, 0.88),
    "mastery_unlock":     (0.30, 0.60, 0.40, 0.20),
    # ── Other ──
    "pause_menu":         (0.30, 0.30, 0.40, 0.40),
    "settings_menu":      (0.20, 0.15, 0.60, 0.70),
    "loading_screen":      (0.30, 0.40, 0.40, 0.20),
}

# OCR confirmation hints — bilingual substrings
# When template match is borderline, OCR confirms by checking if these
# strings appear near the match location in the frame
OCR_HINTS: Dict[str, Dict[str, List[str]]] = {
    "start_menu": {"en": ["START", "RACE", "START RACE"], "cht": ["開始", "賽事", "駕駛"]},
    "main_menu":  {"en": ["HOME", "PLAY", "MENU"],       "cht": ["主選單", "開始", "探索"]},
    "my_horizon_tab": {"en": ["MY", "HORIZON"],           "cht": ["我的", "地平線"]},
    "restart_menu": {"en": ["RESTART", "AGAIN", "RACE"],  "cht": ["重新", "開始", "再次"]},
    "wheelspin_collect": {"en": ["COLLECT", "PRIZE"],     "cht": ["領取", "獎勵", "收集"]},
    "wheelspin_duplicate": {"en": ["DUPLICATE", "CAR"],    "cht": ["重複", "車輛", "已擁有"]},
    "buy_car":    {"en": ["BUY", "PURCHASE"],              "cht": ["購買", "取得"]},
    "confirm_buy": {"en": ["CONFIRM", "BUY"],             "cht": ["確認", "購買"]},
    "mastery_ride_car": {"en": ["RIDE", "THIS CAR"],      "cht": ["駕駛", "這輛車"]},
    "mastery_upgrade": {"en": ["UPGRADE", "TUNING"],      "cht": ["升級", "調校"]},
    "pause_menu": {"en": ["PAUSE", "RESUME", "OPTIONS"],  "cht": ["暫停", "繼續", "選項"]},
    "loading_screen": {"en": ["LOADING", "PLEASE WAIT"],  "cht": ["載入", "請稍候", "讀取"]},
}


# ── Dataclasses ──────────────────────────────────────────────

@dataclass
class MatchResult:
    key: str
    score: float
    x: int
    y: int
    w: int
    h: int
    method: str = "template"
    ocr_verified: bool = False
    stable: bool = False

    @property
    def location(self) -> Tuple[int, int]:
        """Center point of the match — use as click target."""
        return (self.x + self.w // 2, self.y + self.h // 2)


class ScreenState:
    """Named UI state descriptor."""
    def __init__(self, key: str,
                 roi: Tuple[float, float, float, float] = None,
                 ocr_hints: Dict[str, List[str]] = None,
                 threshold: float = DEFAULT_THRESHOLD,
                 stable_frames: int = DEFAULT_STABLE_FRAMES,
                 is_text: bool = False):
        self.key = key
        self.roi = roi or DEFAULT_ROIS.get(key)
        self.ocr_hints = ocr_hints or OCR_HINTS.get(key, {})
        self.threshold = threshold
        self.stable_frames = stable_frames
        self.is_text = is_text


# ── OCR Engine ───────────────────────────────────────────────

class OCREngine:
    """
    Bilingual OCR engine with two backends:
      1. RapidOCR (onnxruntime) — fast, accurate, preferred
      2. pytesseract — fallback

    Features:
      - Per-result cache (avoids re-reading same region)
      - Cooldown timer to avoid flooding
      - Veto / confirm modes
    """

    def __init__(self):
        self._engine = None
        self._backend = None
        self._cache: Dict[Tuple, Tuple[float, str]] = {}
        self._cooldown = 0.0
        self._init_engine()

    def _init_engine(self):
        # Try RapidOCR first
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR()
            self._backend = "rapidocr"
            return
        except ImportError:
            pass

        try:
            from rapidocrapi import RapidOCR
            self._engine = RapidOCR()
            self._backend = "rapidocr"
            return
        except ImportError:
            pass

        # Fallback to pytesseract
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            self._engine = pytesseract
            self._backend = "pytesseract"
        except Exception:
            self._backend = None

    def read(self, frame: np.ndarray,
             region: Tuple[int, int, int, int] = None,
             hints: Dict[str, List[str]] = None,
             mode: str = "confirm") -> Tuple[bool, float, str]:
        """
        Read text from a frame region.
        mode: 'confirm' (return True if hint found), 'veto' (return False if hint found),
              'raw' (return text regardless)
        Returns (success, confidence, text)
        """
        if self._backend is None:
            return False, 0.0, ""

        # Check cooldown
        if time.time() < self._cooldown:
            return False, 0.0, ""

        # Cache key: region + approx frame hash
        if region:
            x, y, w, h = region
            # Clip to frame bounds
            fh, fw = frame.shape[:2]
            x, y = max(0, x), max(0, y)
            w = min(w, fw - x)
            h = min(h, fh - y)
            if w <= 0 or h <= 0:
                return False, 0.0, ""
            cache_key = (x, y, w, h, int(frame.size / 1000))
        else:
            cache_key = ("full", int(frame.size / 1000))

        if cache_key in self._cache:
            conf, text = self._cache[cache_key]
            # Cache valid for 2 seconds
            if time.time() - self._cache.get(cache_key, (0, ""))[0] < 2:
                return self._evaluate(conf, text, hints, mode)
            del self._cache[cache_key]

        # Crop region
        if region:
            x, y, w, h = region
            img = frame[y:y+h, x:x+w]
        else:
            img = frame

        text, conf = self._do_ocr(img)
        self._cache[cache_key] = (time.time(), text)

        if mode == "raw":
            return True, conf, text

        return self._evaluate(conf, text, hints, mode)

    def _do_ocr(self, img: np.ndarray) -> Tuple[str, float]:
        """Run OCR on the image. Returns (text, confidence)."""
        if self._backend == "rapidocr":
            try:
                result, elapse = self._engine(img)
                if not result:
                    return "", 0.0
                # RapidOCR returns list of [box, text, conf]
                texts = []
                confs = []
                for item in result:
                    texts.append(item[1])
                    confs.append(item[2])
                combined = " ".join(texts)
                avg_conf = sum(confs) / len(confs) if confs else 0.0
                return combined, avg_conf
            except Exception:
                return "", 0.0

        elif self._backend == "pytesseract":
            try:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
                data = self._engine.image_to_string(gray, lang="eng+chi_tra", output_type=self._engine.Output.DICT)
                texts = " ".join(data.get("text", []))
                return texts, 0.7  # pytesseract doesn't give per-result conf
            except Exception:
                return "", 0.0

        return "", 0.0

    def _evaluate(self, conf: float, text: str,
                  hints: Dict[str, List[str]],
                  mode: str) -> Tuple[bool, float, str]:
        """Evaluate OCR text against hint substrings."""
        if not hints or not text:
            return False, 0.0, text

        text_lower = text.lower()
        found = False
        for lang, substrings in hints.items():
            for sub in substrings:
                if sub.lower() in text_lower:
                    found = True
                    break

        if mode == "confirm":
            return found, conf, text
        elif mode == "veto":
            return not found, conf, text
        return True, conf, text

    def set_cooldown(self, seconds: float):
        """Set cooldown before next OCR call."""
        self._cooldown = time.time() + seconds

    def clear_cache(self):
        self._cache.clear()


# ── ScreenDetector ───────────────────────────────────────────

class ScreenDetector:
    """
    Template matching detector with adaptive ROI, multi-scale scoring,
    stability filtering, and OCR confirmation.

    Usage:
        detector = ScreenDetector(config)
        detector.register_template("start_menu", template_img, threshold=0.80)
        result = detector.detect(frame, "start_menu")
        if result:
            click_x, click_y = result.location
    """

    def __init__(self, cfg: dict = None):
        self.cfg = cfg or {}
        self._templates: Dict[str, np.ndarray] = {}
        self._meta: Dict[str, dict] = {}
        self._geometries: Dict[str, dict] = {}  # key -> box, screen_w, screen_h
        self._last_result: Dict[str, MatchResult] = {}
        self._consecutive: Dict[str, int] = {}   # key -> consecutive frame count
        self._ocr = OCREngine()
        self._last_full_scan = 0.0

        # Optional per-key custom thresholds
        self._thresholds: Dict[str, float] = {}

        # Thread safety
        self._lock = threading.Lock()

    def register_template(self, key: str, img: np.ndarray,
                         threshold: float = DEFAULT_THRESHOLD,
                         meta: dict = None):
        """Register a template image for a named state."""
        with self._lock:
            self._templates[key] = img
            self._meta[key] = meta or {}
            self._thresholds[key] = threshold
            self._consecutive[key] = 0

    def set_threshold(self, key: str, threshold: float):
        self._thresholds[key] = threshold

    def set_template_geometry(self, key: str, box: Tuple,
                               screen_w: int, screen_h: int):
        """Store template capture geometry for adaptive ROI calculation."""
        self._geometries[key] = {
            "box": box,  # (x,y,w,h) ratio in content box
            "screen_width": screen_w,
            "screen_height": screen_h,
        }

    def _compute_roi(self, key: str, frame_w: int, frame_h: int,
                     custom_roi: Tuple = None) -> Tuple[int, int, int, int]:
        """Compute pixel ROI from ratio definition + optional custom override."""
        if custom_roi:
            x_r, y_r, w_r, h_r = custom_roi
        else:
            roi = DEFAULT_ROIS.get(key)
            if not roi:
                return (0, 0, frame_w, frame_h)
            x_r, y_r, w_r, h_r = roi

        x = int(x_r * frame_w)
        y = int(y_r * frame_h)
        w = int(w_r * frame_w)
        h = int(h_r * frame_h)

        # Clamp
        x = max(0, min(x, frame_w - 1))
        y = max(0, min(y, frame_h - 1))
        w = max(1, min(w, frame_w - x))
        h = max(1, min(h, frame_h - y))

        return (x, y, w, h)

    def _match(self, frame: np.ndarray, key: str,
               threshold: float = None) -> Optional[MatchResult]:
        """Run multi-scale template matching on the frame for the given key."""
        with self._lock:
            if key not in self._templates:
                return None
            template = self._templates[key]
            thresh = threshold or self._thresholds.get(key, DEFAULT_THRESHOLD)

        fh, fw = frame.shape[:2]

        # Determine search region
        x, y, rw, rh = self._compute_roi(key, fw, fh)

        # Check template fits in search region
        if template.shape[0] > rh or template.shape[1] > rw:
            # Fall back to full frame
            x, y, rw, rh = 0, 0, fw, fh

        search = frame[y:y+rh, x:x+rw]

        # Grayscale if not already
        if len(search.shape) == 3:
            gray_s = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
        else:
            gray_s = search

        if len(template.shape) == 3:
            gray_t = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        else:
            gray_t = template

        # Choose scales based on template type (is_text flag)
        meta = self._meta.get(key, {})
        is_text = meta.get("is_text", False)
        scales = TEXT_SCALES if is_text else STRUCTURAL_SCALES

        best_score = 0.0
        best_loc = None

        for scale in scales:
            tw = int(gray_t.shape[1] * scale)
            th = int(gray_t.shape[0] * scale)
            if tw <= 0 or th <= 0:
                continue
            scaled = cv2.resize(gray_t, (tw, th), interpolation=cv2.INTER_AREA)

            if scaled.shape[0] > gray_s.shape[0] or scaled.shape[1] > gray_s.shape[1]:
                continue

            # Main match: grayscale
            try:
                result = cv2.matchTemplate(gray_s, scaled, cv2.TM_CCOEFF_NORMED)
            except Exception:
                continue

            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > best_score:
                best_score = max_val
                # max_loc is in search region coords
                best_loc = (max_loc[0] + x, max_loc[1] + y, tw, th)

        if best_score < thresh:
            return None

        bx, by, bw, bh = best_loc

        # Edge composite bonus for non-text templates
        if not is_text:
            edge_s = cv2.Canny(gray_s, 50, 150)
            gray_t_full = gray_t
            tw, th = gray_t_full.shape[1], gray_t_full.shape[0]
            # Find best scale for edge too
            best_edge_score = 0.0
            for scale in STRUCTURAL_SCALES[:3]:  # only top 3 scales for edge
                sw = int(gray_t_full.shape[1] * scale)
                sh = int(gray_t_full.shape[0] * scale)
                if sw <= 0 or sh <= 0:
                    continue
                scaled_t = cv2.resize(gray_t_full, (sw, sh), interpolation=cv2.INTER_AREA)
                if scaled_t.shape[0] > edge_s.shape[0] or scaled_t.shape[1] > edge_s.shape[1]:
                    continue
                try:
                    edge_t = cv2.Canny(scaled_t, 50, 150)
                    result_e = cv2.matchTemplate(edge_s, edge_t, cv2.TM_CCOEFF_NORMED)
                except Exception:
                    continue
                _, ev, _, _ = cv2.minMaxLoc(result_e)
                if ev > best_edge_score:
                    best_edge_score = ev

            # Composite: gray * 0.62 + edge * 0.28
            composite = best_score * 0.72 + best_edge_score * 0.28
            if composite < thresh:
                return None
            best_score = composite

        return MatchResult(
            key=key,
            score=best_score,
            x=bx, y=by, w=bw, h=bh,
            method="template",
            ocr_verified=False,
            stable=False,
        )

    def _ocr_confirm(self, frame: np.ndarray, result: MatchResult) -> bool:
        """Confirm a borderline match with OCR. Returns True if confirmed."""
        hints = OCR_HINTS.get(result.key, {})
        if not hints:
            return True  # No hints = auto-confirm

        # Expand the match region slightly for OCR context
        x, y, w, h = result.x, result.y, result.w, result.h
        margin = max(w, h) // 2
        x0 = max(0, x - margin)
        y0 = max(0, y - margin)
        x1 = min(frame.shape[1], x + w + margin)
        y1 = min(frame.shape[0], y + h + margin)

        success, conf, text = self._ocr.read(
            frame, region=(x0, y0, x1 - x0, y1 - y0),
            hints=hints, mode="confirm"
        )
        self._ocr.set_cooldown(0.5)
        return success

    def detect(self, frame: np.ndarray, key: str,
               threshold: float = None,
               stable: bool = True,
               use_full_scan: bool = False) -> Optional[MatchResult]:
        """
        Detect a named state in the frame.
        stable=True: require N consecutive detections before returning a result.
        use_full_scan=True: always scan full frame (skip ROI optimization).
        Returns MatchResult or None.
        """
        if frame is None:
            return None

        result = self._match(frame, key, threshold)

        with self._lock:
            if result is None:
                self._consecutive[key] = 0
                self._last_result[key] = None
                return None

            self._consecutive[key] = self._consecutive.get(key, 0) + 1

            stable_n = DEFAULT_STABLE_FRAMES
            if stable and self._consecutive[key] < stable_n:
                # Not yet stable — return but mark unstable
                result.stable = False
                return None

            # Stable — do OCR confirmation if borderline
            thresh = threshold or self._thresholds.get(key, DEFAULT_THRESHOLD)
            if result.score < OCR_CONFIRM_THRESHOLD + 0.10:
                result.ocr_verified = self._ocr_confirm(frame, result)
                if not result.ocr_verified:
                    self._consecutive[key] = 0
                    return None

            result.stable = True
            self._last_result[key] = result
            return result

    def detect_any(self, frame: np.ndarray,
                   keys: List[str],
                   threshold: float = None,
                   stable: bool = True) -> Optional[MatchResult]:
        """Detect any of the given states. Returns first match or None."""
        for key in keys:
            result = self.detect(frame, key, threshold, stable=stable)
            if result:
                return result
        return None

    def wait_for(self,
                 frame_cb: Callable[[], np.ndarray],
                 key: str,
                 threshold: float = None,
                 stop_cb: Callable[[], bool] = None,
                 interval: float = 0.5,
                 timeout: float = float("inf"),
                 on_warn: Callable[[MatchResult], None] = None,
                 on_progress: Callable[[float], None] = None) -> Optional[MatchResult]:
        """
        Poll frame_cb until key is detected or timeout/stop.
        Returns the MatchResult or None.
        """
        thresh = threshold or self._thresholds.get(key, DEFAULT_THRESHOLD)
        start = time.time()
        warn_sent = False

        while True:
            if stop_cb and stop_cb():
                return None

            elapsed = time.time() - start
            if timeout and elapsed > timeout:
                return None

            if on_progress:
                on_progress(min(elapsed / max(timeout, 1), 1.0))

            frame = frame_cb()
            result = self.detect(frame, key, threshold=thresh, stable=True)

            if result:
                return result

            # Warning: not detected after 10s
            if not warn_sent and elapsed > 10.0 and on_warn:
                last = self._last_result.get(key)
                on_warn(last or MatchResult(key=key, score=0.0, x=0, y=0, w=0, h=0))
                warn_sent = True

            time.sleep(interval)

    def set_thresholds(self, thresholds: Dict[str, float]):
        """Bulk-set thresholds from a dict."""
        self._thresholds.update(thresholds)

    def get_last_result(self, key: str) -> Optional[MatchResult]:
        return self._last_result.get(key)

    def clear_stability(self, key: str = None):
        """Reset stability counters. If key is None, clear all."""
        with self._lock:
            if key:
                self._consecutive[key] = 0
            else:
                self._consecutive.clear()
                self._last_result.clear()


# ── Click recording (for debug overlay) ─────────────────────

_last_click: Tuple[int, int] = (0, 0)
_click_lock = threading.Lock()


def record_click(x: int, y: int):
    global _last_click
    with _click_lock:
        _last_click = (x, y)


def get_last_click() -> Tuple[int, int]:
    with _click_lock:
        return _last_click


# ── Debug image export ───────────────────────────────────────

def draw_debug(frame: np.ndarray, result: MatchResult,
               roi: Tuple[int, int, int, int] = None,
               label: str = None) -> np.ndarray:
    """
    Draw debug annotations on a frame.
    - Yellow rectangle: ROI region
    - Green cross: match center
    - Magenta cross: last click point
    Returns annotated copy (doesn't mutate original).
    """
    dbg = frame.copy()
    fh, fw = dbg.shape[:2]

    # ROI rectangle (yellow)
    if roi:
        rx, ry, rw, rh = roi
        cv2.rectangle(dbg, (rx, ry), (rx + rw, ry + rh), (0, 255, 255), 2)

    # Match center (green)
    if result:
        cx, cy = result.location
        cv2.drawMarker(dbg, (cx, cy), (0, 255, 0), cv2.MARKER_CROSS, 30, 2)
        # Score text
        text = f"{result.key}: {result.score:.0%}"
        if label:
            text = f"{label}: {result.score:.0%}"
        cv2.putText(dbg, text, (cx + 15, cy - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # Last click (magenta)
    cx, cy = get_last_click()
    if cx > 0 or cy > 0:
        cv2.drawMarker(dbg, (cx, cy), (255, 0, 255), cv2.MARKER_CROSS, 20, 2)

    return dbg


def save_debug(frame: np.ndarray, result: MatchResult,
               path: str,
               roi: Tuple[int, int, int, int] = None):
    """Save a debug-annotated frame."""
    dbg = draw_debug(frame, result, roi)
    cv2.imwrite(path, dbg)
