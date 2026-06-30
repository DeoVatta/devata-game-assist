"""应用路径：开发模式与 PyInstaller 打包通用。

打包模式将配置存到 %LOCALAPPDATA%/TaskBarHeroHelper，
与程序文件夹分离，版本更新时直接替换 exe 文件夹不丢配置。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """用户可读写目录（配置、profiles 存于此）。

    打包模式 → %LOCALAPPDATA%/TaskBarHeroHelper（不随版本替换丢失）
    开发模式 → 项目根目录
    """
    if is_frozen():
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return local / "TaskBarHeroHelper"
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path:
    """打包内嵌的只读资源目录（config.default.yaml 等模板存放处）。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def _migrate_old_config(data_dir: Path) -> None:
    """从旧位置（exe 同目录）复制已有配置到新位置，避免更新丢配置。"""
    old_root = Path(sys.executable).resolve().parent if is_frozen() else None
    if not old_root or old_root == data_dir:
        return

    # 迁移 config.yaml
    old_cfg = old_root / "config.yaml"
    new_cfg = data_dir / "config.yaml"
    if old_cfg.exists() and not new_cfg.exists():
        shutil.copy2(old_cfg, new_cfg)
        # 更新 config 里的 profile 路径指向新位置
        try:
            import yaml
            with new_cfg.open("r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            portal = cfg.get("portal", {})
            if portal.get("profile"):
                old_rel = Path(portal["profile"])
                # 旧 profile 路径可能是相对 old_root 的
                old_prof = old_root / old_rel
                new_prof = data_dir / "profiles" / "portal_profile.yaml"
                if old_prof.exists() and not new_prof.exists():
                    shutil.copy2(old_prof, new_prof)
                # 更新配置指向新位置
                cfg["portal"]["profile"] = "profiles/portal_profile.yaml"
            with new_cfg.open("w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
        except Exception:
            pass

    # 直接迁移 profiles 目录（如果单独存在）
    old_profiles = old_root / "profiles"
    new_profiles = data_dir / "profiles"
    if old_profiles.is_dir() and not new_profiles.exists():
        shutil.copytree(old_profiles, new_profiles, dirs_exist_ok=True)


def ensure_runtime_files() -> Path:
    """首次运行：从模板复制 config.yaml / portal_profile.yaml。"""
    base = app_dir()
    base.mkdir(parents=True, exist_ok=True)

    # 从旧位置迁移已有配置（一次性）
    _migrate_old_config(base)

    profiles = base / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)

    config = base / "config.yaml"
    if not config.exists():
        src = bundle_dir() / "config.default.yaml"
        if src.exists():
            shutil.copy2(src, config)

    profile = profiles / "portal_profile.yaml"
    if not profile.exists():
        src = bundle_dir() / "profiles" / "portal_profile.default.yaml"
        if src.exists():
            shutil.copy2(src, profile)

    return base


VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
"""Visual C++ Redistributable for Visual Studio 2015-2022 (x64)。"""


def check_vc_runtime() -> bool:
    """检测 VC++ 运行库是否可用。

    尝试加载 vcruntime140.dll（2015-2022 Redistributable 的核心文件），
    加载失败说明系统缺少必要的运行库。
    """
    try:
        import ctypes
        ctypes.windll.LoadLibrary("vcruntime140.dll")
        return True
    except Exception:
        return False


def prompt_vc_runtime(parent) -> None:
    """如果缺少 VC++ 运行库，弹出提示并可选跳转下载页。"""
    if check_vc_runtime():
        return
    try:
        import tkinter as tk

        dlg = tk.Toplevel(parent)
        dlg.title("缺少 VC++ 运行库")
        dlg.configure(bg="#0C0C0C")
        dlg.resizable(False, False)
        dlg.transient(parent)
        dlg.grab_set()

        tk.Label(
            dlg,
            text="检测到系统缺少 Visual C++ 运行库",
            font=("Microsoft YaHei UI", 12, "bold"),
            bg="#0C0C0C",
            fg="#ECECEC",
        ).pack(padx=24, pady=(20, 8))

        tk.Label(
            dlg,
            text=(
                "本软件依赖 Microsoft Visual C++ Redistributable\n"
                "(Visual Studio 2015-2022)\n\n"
                "请点击下方按钮下载安装后重启本软件"
            ),
            font=("Microsoft YaHei UI", 10),
            bg="#0C0C0C",
            fg="#8A8A8A",
            justify="center",
        ).pack(padx=24, pady=(0, 16))

        btn_row = tk.Frame(dlg, bg="#0C0C0C")
        btn_row.pack(pady=(0, 20))

        def download():
            import webbrowser
            webbrowser.open(VC_REDIST_URL)
            dlg.destroy()

        def skip():
            dlg.destroy()

        tk.Button(
            btn_row,
            text="下载并安装",
            command=download,
            bg="#9B2335",
            fg="#FFFFFF",
            activebackground="#B82E45",
            activeforeground="#FFFFFF",
            font=("Microsoft YaHei UI", 10),
            relief="flat",
            padx=16,
            pady=6,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(
            btn_row,
            text="跳过（不推荐）",
            command=skip,
            bg="#1E1E1E",
            fg="#8A8A8A",
            activebackground="#282828",
            activeforeground="#ECECEC",
            font=("Microsoft YaHei UI", 10),
            relief="flat",
            padx=16,
            pady=6,
            cursor="hand2",
        ).pack(side=tk.LEFT)

        dlg.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - dlg.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")
        parent.wait_window(dlg)
    except Exception:
        pass
