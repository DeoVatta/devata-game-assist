"""监控游戏日志，测试蓝箱检测（不点击换图）。

用法:
  python watch_boxes.py              # 实时监控，蓝箱高亮
  python watch_boxes.py --history    # 查看历史掉落统计
  python watch_boxes.py --simulate   # 模拟写入一条蓝箱日志测试解析
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from tbh_helper.log_watcher import DetectConfig, LogTailWatcher, box_type_label, scan_history, wait_for_log
from tbh_helper.window import expand_path


def load_detect_config(cfg: dict) -> DetectConfig:
    return DetectConfig.from_dict(cfg.get("log", {}), cfg.get("detect"))


def print_event(event, *, is_trigger: bool) -> None:
    tag = box_type_label(event.item_key)
    mark = "***" if is_trigger else ""
    trigger = " -> 会触发换图" if is_trigger else ""
    print(f"[掉落] {mark}{tag}{mark} x{event.count} ItemKey={event.item_key}{trigger}")


def main() -> int:
    parser = argparse.ArgumentParser(description="TaskBarHero 箱子掉落监控")
    parser.add_argument("-c", "--config", default=str(Path(__file__).with_name("config.yaml")))
    parser.add_argument("--history", action="store_true", help="扫描历史日志")
    parser.add_argument("--simulate", action="store_true", help="模拟蓝箱日志行")
    parser.add_argument("--poll-interval", type=float, default=0.3)
    args = parser.parse_args()

    import yaml

    with Path(args.config).open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    detect = load_detect_config(cfg)
    log_path = Path(expand_path(cfg.get("log", {}).get("path", "")))

    print("=" * 50)
    print("TaskBarHero 蓝箱检测监控")
    print("=" * 50)
    print(f"日志: {log_path}")
    print(f"Boss箱规则: ItemKey 前缀 [{detect.boss_key_prefix}]，排除 [{detect.exclude_key_prefix}]")
    if detect.boss_item_keys:
        print(f"额外指定: {sorted(detect.boss_item_keys)}")
    print(f"防抖间隔: {detect.debounce_seconds}s")
    print("=" * 50)

    if args.simulate:
        line = "GetBoxCount Success Count : 1 // ItemKey : 920301\n"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)
        print("已写入模拟 Boss 箱日志: ItemKey=920301")
        print("若 watch 正在运行，应立刻看到触发")
        return 0

    if args.history:
        all_ev, blue_ev = scan_history(log_path, detect)
        print(f"\n历史总计: {len(all_ev)} 次掉落, 其中 Boss 箱 {len(blue_ev)} 次\n")
        counter = Counter(e.item_key for e in all_ev)
        for key, cnt in counter.most_common():
            kind = box_type_label(key)
            trigger = " (触发)" if key.startswith(detect.boss_key_prefix) and not key.startswith(detect.exclude_key_prefix) else ""
            print(f"  {kind}{trigger}  {key}  x{cnt}")
        if blue_ev:
            print(f"\n最近一次 Boss 箱: ItemKey={blue_ev[-1].item_key}")
        return 0

    wait_for_log(log_path)
    watcher = LogTailWatcher(log_path, detect)
    watcher.seek_end()
    print("监控中… 等游戏里掉箱子（Ctrl+C 停止）\n")

    try:
        while True:
            for event in watcher.poll_raw():
                is_boss = watcher.is_boss_box(event)
                would = watcher.would_trigger(event) if is_boss else False
                print_event(event, is_trigger=would)
                if event.item_key.startswith("93"):
                    print("  (超级Boss箱，不触发换图)")
                elif is_boss and not would:
                    print("  (防抖跳过，短时间内重复)")

            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print("\n已停止")
        return 0


if __name__ == "__main__":
    sys.exit(main())
