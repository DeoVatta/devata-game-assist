"""首次初始化：框选传送门区域，标注框内相对坐标。

用法:
  python setup.py              # 完整初始化向导
  python setup.py --from-config  # 用 config.yaml 里现有坐标反推（需先框选区域）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyautogui

from tbh_helper.config_loader import load_config, profile_path_from_cfg, save_config
from tbh_helper.profile import (
    PortalProfile,
    default_stage_defs,
    mark_point_in_anchor,
)
from tbh_helper.region_picker import pick_region


def run_setup(base_dir: Path, from_config: bool = False) -> PortalProfile:
    cfg = load_config(base_dir / "config.yaml")
    profile_path = profile_path_from_cfg(cfg, base_dir)
    template_path = profile_path.parent / "portal_anchor.png"

    print("=" * 55)
    print("TaskBarHero 传送门初始化")
    print("=" * 55)
    print("步骤 1/3：请打开游戏「传送门」面板")
    input("准备好后按 Enter 开始框选…")

    print("\n>>> 拖拽鼠标框选整个「传送门」面板（含章节标签和地图）")
    anchor = pick_region()
    print(f"已选区域: left={anchor.left} top={anchor.top} size={anchor.width}x{anchor.height}")

    profile = PortalProfile()

    if from_config and cfg.get("portal", {}).get("ui"):
        print("\n>>> 从 config.yaml 迁移坐标到框内相对坐标…")
        ui_old = cfg["portal"]["ui"]
        window_rect = None
        try:
            from tbh_helper.window import find_game_window, get_window_rect

            hwnd = find_game_window(
                process_name=cfg.get("game", {}).get("process_name", "TaskBarHero"),
                pid=cfg.get("game", {}).get("pid"),
            )
            if hwnd:
                window_rect = get_window_rect(hwnd)
        except Exception:
            pass

        def win_to_anchor(rel_x: float, rel_y: float) -> tuple[float, float]:
            if window_rect:
                sx, sy = window_rect.to_screen(rel_x, rel_y)
            else:
                raise RuntimeError("需要游戏窗口在线才能从 config 迁移坐标")
            return (
                round((sx - anchor.left) / anchor.width, 4),
                round((sy - anchor.top) / anchor.height, 4),
            )

        for ch, pos in ui_old.get("chapter_tabs", {}).items():
            profile.chapter_tabs[int(ch)] = win_to_anchor(float(pos[0]), float(pos[1]))
        dd = ui_old.get("difficulty_dropdown", [0.5, 0.15])
        profile.difficulty_dropdown = win_to_anchor(float(dd[0]), float(dd[1]))
        for key, pos in ui_old.get("difficulty_options", {}).items():
            profile.difficulty_options[key] = win_to_anchor(float(pos[0]), float(pos[1]))
        sa = ui_old.get("map_scroll_area", [0.5, 0.55])
        profile.map_scroll_area = win_to_anchor(float(sa[0]), float(sa[1]))
        profile.scroll_clicks_down_to_1_7 = int(ui_old.get("scroll_clicks_down_to_1_7", 5))
        profile.scroll_clicks_up_to_8_10 = int(ui_old.get("scroll_clicks_up_to_8_10", 5))
        profile.scroll_method = str(ui_old.get("scroll_method", "sendinput"))
        profile.scroll_interval = float(ui_old.get("scroll_interval", 0.06))
        profile.action_delay = float(ui_old.get("action_delay", 0.35))

        profile.stages = []
        for s in cfg.get("stages", default_stage_defs()):
            rel_x, rel_y = win_to_anchor(float(s["rel_x"]), float(s["rel_y"]))
            profile.stages.append(
                {
                    "name": s["name"],
                    "chapter": s["chapter"],
                    "difficulty": s["difficulty"],
                    "stage_num": s["stage_num"],
                    "rel_x": rel_x,
                    "rel_y": rel_y,
                }
            )
        print("迁移完成。")
    else:
        print("\n步骤 2/3：标注 UI 控件（坐标相对于框选区域）")
        print("提示：难度选项需先手动点开下拉框再标记\n")

        for ch in (1, 2, 3):
            profile.chapter_tabs[ch] = mark_point_in_anchor(anchor, f"第{ch}章 标签")

        profile.difficulty_dropdown = mark_point_in_anchor(anchor, "难度下拉框")
        input("  请手动点开难度下拉框，然后按 Enter…")
        profile.difficulty_options["normal"] = mark_point_in_anchor(anchor, "「普通」选项")
        input("  请再次点开难度下拉框，然后按 Enter…")
        profile.difficulty_options["nightmare"] = mark_point_in_anchor(anchor, "「噩梦」选项")
    for key, label in [("hell", "「地狱」"), ("torment", "「折磨」")]:
        if input(f"标定 {label} 选项？(y/N): ").strip().lower() == "y":
            profile.difficulty_options[key] = mark_point_in_anchor(anchor, f"{label}选项")
        profile.map_scroll_area = mark_point_in_anchor(anchor, "地图滚轮区域（地形图中央）")

        print("\n滚轮参数（直接回车使用默认 5）:")
        down_in = input("  滚到 1-7 视图（向下滚）次数 [5]: ").strip()
        up_in = input("  滚到 8-10 视图（向上滚）次数 [5]: ").strip()
        if down_in:
            profile.scroll_clicks_down_to_1_7 = int(down_in)
        if up_in:
            profile.scroll_clicks_up_to_8_10 = int(up_in)

        print("\n步骤 3/3：标注轮换关卡节点")
        print("1-7 节点：请先把地图滚到 1-7 视图（向下滚到底）")
        print("8-10 节点：请先把地图滚到 8-10 视图（向上滚到底）\n")

        profile.stages = []
        for sdef in default_stage_defs():
            view = "8-10 视图" if sdef["stage_num"] >= 8 else "1-7 视图"
            print(f"--- {sdef['name']}（需要 {view}）---")
            if sdef["stage_num"] >= 8:
                input("  请切换到对应章节/难度，并滚到 8-10 视图后按 Enter…")
            rel_x, rel_y = mark_point_in_anchor(anchor, f"关卡节点 {sdef['name']}")
            profile.stages.append({**sdef, "rel_x": rel_x, "rel_y": rel_y})

    profile.capture_template(anchor, template_path)
    profile.save(profile_path)

    cfg.setdefault("portal", {})
    cfg["portal"]["use_anchor"] = True
    cfg["portal"]["profile"] = str(profile_path.relative_to(base_dir)).replace("\\", "/")
    save_config(base_dir / "config.yaml", cfg)

    print("\n" + "=" * 55)
    print(f"初始化完成！")
    print(f"  配置文件: {profile_path}")
    print(f"  参考截图: {template_path}")
    print("下次运行 run_rotator.py 时，只需重新框选传送门区域即可。")
    print("=" * 55)
    return profile


def main() -> int:
    parser = argparse.ArgumentParser(description="TaskBarHero 传送门初始化向导")
    parser.add_argument(
        "--from-config",
        action="store_true",
        help="从 config.yaml 现有窗口坐标迁移（需游戏在线）",
    )
    args = parser.parse_args()
    base_dir = Path(__file__).parent
    try:
        run_setup(base_dir, from_config=args.from_config)
        return 0
    except KeyboardInterrupt:
        print("\n已取消")
        return 1


if __name__ == "__main__":
    sys.exit(main())
