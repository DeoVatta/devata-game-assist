from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from tbh_helper.config_loader import build_rotator, load_config, profile_path_from_cfg
from tbh_helper.log_watcher import DetectConfig, LogTailWatcher, wait_for_log
from tbh_helper.profile import PortalProfile
from tbh_helper.region_picker import pick_region
from tbh_helper.window import expand_path, find_game_window


def pick_session_anchor(cfg: dict):
    skip = cfg.get("portal", {}).get("skip_anchor_pick", False)
    if skip:
        return None
    print("\n>>> 请框选「传送门」面板（与初始化时相同的区域）")
    input("传送门已打开后按 Enter…")
    return pick_region()


def main() -> int:
    parser = argparse.ArgumentParser(description="TaskBarHero 蓝箱自动换图")
    parser.add_argument(
        "-c",
        "--config",
        default=str(Path(__file__).with_name("config.yaml")),
        help="配置文件路径",
    )
    parser.add_argument("--setup", action="store_true", help="重新运行初始化向导")
    parser.add_argument("--once", action="store_true", help="检测到一次蓝箱后退出")
    parser.add_argument("--dry-run", action="store_true", help="只监控日志，不点击")
    parser.add_argument("--poll-interval", type=float, default=0.5, help="日志轮询间隔秒数")
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="使用 config.yaml 窗口坐标（不使用锚点框）",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    base_dir = config_path.parent
    cfg = load_config(config_path)
    game_cfg = cfg.get("game", {})
    log_cfg = cfg.get("log", {})
    portal_cfg = cfg.get("portal", {})

    log_path = Path(expand_path(log_cfg.get("path", "")))
    detect = DetectConfig.from_dict(log_cfg, cfg.get("detect"))
    pid = game_cfg.get("pid")
    process_name = game_cfg.get("process_name", "TaskBarHero")

    use_anchor = bool(portal_cfg.get("use_anchor", True)) and not args.legacy
    profile: PortalProfile | None = None
    anchor = None

    if use_anchor:
        profile_path = profile_path_from_cfg(cfg, base_dir)
        if args.setup or not profile_path.exists():
            if args.dry_run and not profile_path.exists():
                print("尚未初始化，请先运行: python setup.py")
                return 1
            from setup import run_setup

            auto_migrate = (
                not profile_path.exists()
                and not args.setup
                and bool(cfg.get("portal", {}).get("ui", {}).get("chapter_tabs"))
            )
            if auto_migrate:
                print("检测到 config.yaml 已有坐标，将自动迁移到锚点框（需游戏在线）…")
            profile = run_setup(base_dir, from_config=auto_migrate)
        else:
            profile = PortalProfile.load(profile_path)
        if not args.dry_run:
            anchor = pick_session_anchor(cfg)
            if anchor:
                print(f"锚点区域: {anchor.width}x{anchor.height} @ ({anchor.left},{anchor.top})")
        stage_names = [s["name"] for s in profile.stages]
    else:
        stage_names = [s["name"] for s in cfg.get("stages", [])]

    print("=" * 50)
    print("TaskBarHero 蓝箱换图助手")
    print("=" * 50)
    print(f"日志: {log_path}")
    print(f"Boss箱检测: ItemKey 前缀 [{detect.boss_key_prefix}]，排除超级Boss [{detect.exclude_key_prefix}]")
    print(f"防抖间隔: {detect.debounce_seconds}s（同 key 重复掉落不连触）")
    print(f"坐标模式: {'锚点框' if use_anchor else '窗口相对'}")
    print(f"轮换节点 ({len(stage_names)}): {' -> '.join(stage_names)}")
    print(f"模式: {'仅监控' if args.dry_run else '监控 + 自动换图'}")
    print("按 Ctrl+C 停止；鼠标移到屏幕左上角可紧急停止")
    print("=" * 50)

    wait_for_log(log_path)
    watcher = LogTailWatcher(log_path, detect)
    watcher.seek_end()

    hwnd = find_game_window(process_name=process_name, pid=pid)
    if not hwnd and not args.dry_run:
        print("[错误] 找不到 TaskBarHero 窗口")
        return 1

    rotator = None
    if hwnd:
        rotator = build_rotator(
            cfg,
            hwnd=hwnd,
            anchor=anchor,
            profile=profile,
        )

    switched = 0
    try:
        while True:
            for event in watcher.poll_triggers():
                print(f"[Boss箱] 检测到掉落 x{event.count} ItemKey={event.item_key}")

                if args.dry_run:
                    print("[dry-run] 跳过换图")
                    if args.once:
                        return 0
                    continue

                if not hwnd:
                    hwnd = find_game_window(process_name=process_name, pid=pid)
                    if not hwnd:
                        print("[错误] 找不到 TaskBarHero 窗口")
                        continue
                    if use_anchor and anchor is None:
                        anchor = pick_session_anchor(cfg)
                    rotator = build_rotator(
                        cfg,
                        hwnd=hwnd,
                        anchor=anchor,
                        profile=profile,
                    )

                rotator.switch_to_next(reason=event)
                switched += 1

                if args.once:
                    print(f"[完成] 已换图 {switched} 次，退出")
                    return 0

            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print(f"\n[停止] 共换图 {switched} 次")
        return 0


if __name__ == "__main__":
    sys.exit(main())
