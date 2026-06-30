"""打包发布：生成 dist/TaskBarHero助手 文件夹与 zip 压缩包。

用法:
  python build_release.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST_NAME = "TaskBarHero助手"
DIST_DIR = ROOT / "dist" / DIST_NAME
ZIP_PATH = ROOT / "dist" / f"{DIST_NAME}.zip"
PACKAGING = ROOT / "packaging"


def _run_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("正在安装 PyInstaller…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"])

    subprocess.check_call(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", str(ROOT / "TaskBarHero助手.spec")],
        cwd=str(ROOT),
    )


def _assemble_release() -> None:
    if not DIST_DIR.is_dir():
        raise FileNotFoundError(f"未找到构建输出: {DIST_DIR}")

    # 启动脚本与说明放在压缩包根目录（与 exe 文件夹同级）
    release_root = ROOT / "dist" / "release"
    if release_root.exists():
        shutil.rmtree(release_root)
    release_root.mkdir(parents=True)

    shutil.copytree(DIST_DIR, release_root / DIST_NAME)
    shutil.copy2(PACKAGING / "启动挂机助手.bat", release_root / "启动挂机助手.bat")
    shutil.copy2(PACKAGING / "使用说明.txt", release_root / "使用说明.txt")

    # 预置可写配置模板（首次运行 exe 也会自动复制，这里方便用户直接看到）
    cfg_dst = release_root / DIST_NAME / "config.yaml"
    if not cfg_dst.exists():
        shutil.copy2(ROOT / "config.default.yaml", cfg_dst)
    prof_dir = release_root / DIST_NAME / "profiles"
    prof_dir.mkdir(exist_ok=True)
    prof_dst = prof_dir / "portal_profile.yaml"
    if not prof_dst.exists():
        shutil.copy2(ROOT / "profiles" / "portal_profile.default.yaml", prof_dst)


def _make_zip() -> None:
    release_root = ROOT / "dist" / "release"
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in release_root.rglob("*"):
            if path.is_file():
                arc = path.relative_to(release_root)
                zf.write(path, arc.as_posix())

    size_mb = ZIP_PATH.stat().st_size / (1024 * 1024)
    print(f"\n[OK] 压缩包: {ZIP_PATH}")
    print(f"     大小约 {size_mb:.1f} MB")
    print(f"[OK] 文件夹: {release_root}")
    print("\n发给朋友: 解压 release 目录内容，双击「启动挂机助手.bat」。")


def main() -> int:
    print("=" * 50)
    print("TaskBarHero 挂机助手 — 打包")
    print("=" * 50)
    _run_pyinstaller()
    print("\n>>> 组装发布文件…")
    _assemble_release()
    _make_zip()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
