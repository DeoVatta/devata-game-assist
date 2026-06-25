"""
app_lang.py — GUI string translations for Forza Horizon 6 Game Assistant.
Supports: English (en), Traditional Chinese (zh-tw).
"""
STRINGS = {
    "app_title": {
        "en":    "Forza Assistant",
        "zh-tw": "Forza 助手",
    },
    "tab_race": {
        "en":    "Race Auto",
        "zh-tw": "自動刷賽",
    },
    "tab_mastery": {
        "en":    "Auto Mastery",
        "zh-tw": "自動熟練度",
    },
    "tab_wheelspin": {
        "en":    "Auto Spin Wheel",
        "zh-tw": "自動轉盤",
    },
    "tab_buy": {
        "en":    "Auto Buy",
        "zh-tw": "自動購買",
    },
    "race_description": {
        "en":    "AFK-race an EventLab event for skill points — holds W the whole way and restarts each time.\n\nBefore you start:\n• Be in the car you want to race with.\n• Make sure your last-played EventLab event is the one you want to grind.",
        "zh-tw": "在 EventLab 賽事中掛機刷技術點——全程按住 W，每場結束自動重開。",
    },
    "mastery_description": {
        "en":    "Unlocks the mastery tree on every car in your garage, one at a time.",
        "zh-tw": "自動為車庫中每一輛車解鎖熟練度樹。",
    },
    "wheelspin_description": {
        "en":    "Auto-spins the Super or Normal Wheelspin, handling duplicates automatically.",
        "zh-tw": "自動轉動超級或普通轉盤，自動處理重複車輛。",
    },
    "buy_description": {
        "en":    "Buys a specific car repeatedly from the Car Collection.",
        "zh-tw": "從車輛收藏中重複購買指定車輛。",
    },
    "btn_start": {"en": "Start", "zh-tw": "開始"},
    "btn_stop":  {"en": "Stop",  "zh-tw": "停止"},
    "status_running":   {"en": "Running...", "zh-tw": "執行中..."},
    "status_stopped":   {"en": "Stopped",    "zh-tw": "已停止"},
    "status_detecting": {"en": "Detecting game...", "zh-tw": "偵測遊戲中..."},
    "log_race_started": {"en": "Race started", "zh-tw": "開始刷賽"},
    "log_mastery_started": {"en": "Mastery started", "zh-tw": "開始熟練度"},
    "log_wheelspin_started": {"en": "Wheelspin started", "zh-tw": "開始轉盤"},
    "log_buy_started": {"en": "Buy started", "zh-tw": "開始購買"},
    "log_stopped": {"en": "Stopped", "zh-tw": "已停止"},
    "log_detected": {"en": "Detected: %(label)s", "zh-tw": "已偵測：%(label)s"},
    "log_pressing": {"en": "Pressing %(key)s — %(label)s", "zh-tw": "按下 %(key)s — %(label)s"},
    "log_not_detected": {"en": "Not detected: %(label)s", "zh-tw": "未偵測：%(label)s"},
    "log_template_missing": {"en": "Template missing: %(key)s", "zh-tw": "模板缺失：%(key)s"},
    "log_grid_missing": {"en": "Grid path file missing", "zh-tw": "網格路徑檔案缺失"},
    "log_bg_input_on":  {"en": "Background input ON", "zh-tw": "背景輸入已開啟"},
    "log_game_muted":   {"en": "Game muted", "zh-tw": "遊戲已靜音"},
    "log_keep_active":  {"en": "Keep-alive active", "zh-tw": "保持活躍已啟動"},
}


def t(key, lang=None, **kwargs):
    """Translate string key. Falls back to English if lang/key not found."""
    lang = lang or "en"
    strings = STRINGS.get(key, {})
    text = strings.get(lang) or strings.get("en") or key
    if kwargs:
        try:
            text = text % kwargs
        except Exception:
            pass
    return text
