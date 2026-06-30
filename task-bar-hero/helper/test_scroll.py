"""测试传送门滚轮（锚点框模式）。

用法:
  python test_scroll.py down
  python test_scroll.py up
  python test_scroll.py down --legacy   # 使用 config.yaml 窗口坐标
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from tbh_helper.chest_open import double_click_at
from tbh_helper.config_loader import build_portal_ui, load_config, profile_path_from_cfg
from tbh_helper.profile import PortalProfile
from tbh_helper.region_picker import pick_region
from tbh_helper.scroll import scroll_wheel_clicks
from tbh_helper.window import find_game_window, get_window_rect


def main() -> int:
    parser = argparse.ArgumentParser(description="测试 TaskBarHero 滚轮")
    parser.add_argument("direction", choices=["up", "down"])
    parser.add_argument("count", nargs="?", type=int)
    parser.add_argument("-c", "--config", default=str(Path(__file__).with_name("config.yaml")))
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument(
        "--method",
        choices=["auto", "sendinput", "mouse_event", "wm_mousewheel"],
        default=None,
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    base_dir = config_path.parent
    cfg = load_config(config_path)
    portal = cfg.get("portal", {})

    use_anchor = bool(portal.get("use_anchor", True)) and not args.legacy
    profile_path = profile_path_from_cfg(cfg, base_dir)

    if use_anchor and profile_path.exists():
        profile = PortalProfile.load(profile_path)
        ui = profile.to_portal_ui()
        print(">>> 框选传送门面板")
        input("按 Enter 开始…")
        anchor = pick_region()
        x, y = anchor.to_screen(*ui.map_scroll_area)
    else:
        ui = build_portal_ui(portal)
        hwnd = find_game_window(
            process_name=cfg.get("game", {}).get("process_name", "TaskBarHero"),
            pid=cfg.get("game", {}).get("pid"),
        )
        if not hwnd:
            print("找不到游戏窗口")
            return 1
        rect = get_window_rect(hwnd)
        x, y = rect.to_screen(*ui.map_scroll_area)

    count = args.count
    if count is None:
        count = ui.scroll_clicks_down_to_1_7 if args.direction == "down" else ui.scroll_clicks_up_to_8_10
    clicks = count if args.direction == "up" else -count
    method = args.method or ui.scroll_method

    hwnd = find_game_window(
        process_name=cfg.get("game", {}).get("process_name", "TaskBarHero"),
        pid=cfg.get("game", {}).get("pid"),
    )
    if not hwnd:
        print("找不到游戏窗口")
        return 1

    print(f"3 秒后开始: 先双击聚焦 -> {args.direction} x{count} @ ({x},{y})")
    time.sleep(3)
    double_click_at(hwnd, x, y, click_interval=ui.scroll_interval)
    used = scroll_wheel_clicks(hwnd, x, y, clicks, method=method, interval=ui.scroll_interval)
    print(f"完成，方式: {used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
