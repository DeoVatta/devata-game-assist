"""坐标校准。

推荐（锚点框模式）:
  python setup.py                 # 首次：框选区域 + 标注框内坐标
  python setup.py --from-config   # 从现有 config.yaml 一键迁移
  python run_rotator.py           # 每次启动时重新框选传送门

旧版（窗口相对坐标）:
  python calibrate.py --legacy --ui
  python calibrate.py --legacy
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pyautogui
import yaml

from tbh_helper.config_loader import (
    build_portal_ui,
    build_rotator,
    build_stage_targets,
    load_config,
    profile_path_from_cfg,
    save_config,
)
from tbh_helper.portal import PortalNavigator
from tbh_helper.profile import PortalProfile
from tbh_helper.region_picker import pick_region
from tbh_helper.window import find_game_window, get_window_rect


def record_mouse_rel(rect) -> tuple[float, float]:
    mx, my = pyautogui.position()
    return round((mx - rect.left) / rect.width, 4), round((my - rect.top) / rect.height, 4)


def legacy_calibrate_ui(cfg: dict, hwnd: int, rect) -> None:
    portal = cfg.setdefault("portal", {})
    ui = portal.setdefault("ui", {})
    ui.setdefault("chapter_tabs", {})
    ui.setdefault("difficulty_options", {})

    for ch in (1, 2, 3):
        input(f"第{ch}章标签 — 移动鼠标后 Enter…")
        ui["chapter_tabs"][ch] = list(record_mouse_rel(rect))

    input("难度下拉框 — Enter…")
    ui["difficulty_dropdown"] = list(record_mouse_rel(rect))
    input("点开下拉框，普通选项 — Enter…")
    ui["difficulty_options"]["normal"] = list(record_mouse_rel(rect))
    input("点开下拉框，噩梦选项 — Enter…")
    ui["difficulty_options"]["nightmare"] = list(record_mouse_rel(rect))
    input("滚轮区域 — Enter…")
    ui["map_scroll_area"] = list(record_mouse_rel(rect))


def legacy_calibrate_stages(cfg: dict, hwnd: int, rect, manual: bool) -> None:
    portal_cfg = cfg.get("portal", {})
    button_rel = portal_cfg.get("button_rel", [0.52, 0.92])
    navigator = PortalNavigator(
        build_portal_ui(portal_cfg),
        rect,
        hwnd=hwnd,
        open_portal=bool(portal_cfg.get("open_before_switch", False)),
        portal_button_rel=(float(button_rel[0]), float(button_rel[1])),
        portal_button_space=rect,
    )
    stages = cfg.get("stages", [])
    targets = build_stage_targets(stages)

    for stage_dict, target in zip(stages, targets):
        if not manual:
            navigator.reset_state()
            navigator.open_portal_if_needed()
            navigator.navigate_to_stage(target)
            time.sleep(0.5)
        input(f"节点 [{stage_dict['name']}] — Enter 记录…")
        stage_dict["rel_x"], stage_dict["rel_y"] = record_mouse_rel(rect)


def test_anchor_stage(cfg: dict, base_dir: Path, stage_name: str) -> None:
    profile_path = profile_path_from_cfg(cfg, base_dir)
    profile = PortalProfile.load(profile_path)
    match = next((s for s in profile.stages if s["name"] == stage_name), None)
    if not match:
        print("找不到节点:", stage_name)
        return

    hwnd = find_game_window(
        process_name=cfg.get("game", {}).get("process_name", "TaskBarHero"),
        pid=cfg.get("game", {}).get("pid"),
    )
    if not hwnd:
        print("找不到游戏窗口")
        return

    print("框选传送门面板…")
    input("按 Enter…")
    anchor = pick_region()
    rotator = build_rotator(cfg, hwnd=hwnd, anchor=anchor, profile=profile)
    target = next(t for t in rotator.stages if t.name == stage_name)
    rotator.navigator.reset_state()
    rotator.navigator.open_portal_if_needed()
    rotator.navigator.navigate_to_stage(target)
    input("确认导航正确后 Enter 点击节点…")
    rotator.navigator.click_stage_node(target)
    print("已点击")


def main() -> int:
    parser = argparse.ArgumentParser(description="TaskBarHero 坐标校准")
    parser.add_argument("--legacy", action="store_true", help="旧版窗口坐标模式")
    parser.add_argument("--ui", action="store_true")
    parser.add_argument("--manual", action="store_true")
    parser.add_argument("--test", metavar="NAME")
    parser.add_argument("-c", "--config", default=str(Path(__file__).with_name("config.yaml")))
    args = parser.parse_args()

    config_path = Path(args.config)
    base_dir = config_path.parent
    cfg = load_config(config_path)

    if args.test and not args.legacy:
        test_anchor_stage(cfg, base_dir, args.test)
        return 0

    if not args.legacy:
        print("请使用 setup.py 进行锚点框初始化:")
        print("  python setup.py")
        print("  python setup.py --from-config   # 从现有坐标迁移")
        return 0

    hwnd = find_game_window(
        process_name=cfg.get("game", {}).get("process_name", "TaskBarHero"),
        pid=cfg.get("game", {}).get("pid"),
    )
    if not hwnd:
        print("找不到 TaskBarHero 窗口")
        return 1

    rect = get_window_rect(hwnd)
    if args.ui:
        legacy_calibrate_ui(cfg, hwnd, rect)
    else:
        legacy_calibrate_stages(cfg, hwnd, rect, manual=args.manual)

    save_config(config_path, cfg)
    print(f"已写入 {config_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
