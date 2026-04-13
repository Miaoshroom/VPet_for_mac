from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "VPet_for_mac"
ROOT = Path(__file__).resolve().parent
EXPORT_DIR = ROOT / "export"
BUILD_DIR = EXPORT_DIR / "build"
PYI_DIR = EXPORT_DIR / "pyinstaller"
DIST_DIR = EXPORT_DIR / "dist"
APP_PATH = EXPORT_DIR / f"{APP_NAME}.app"
HELPER_BIN = BUILD_DIR / "audio_level_helper_bin"
SWIFT_CACHE_DIR = BUILD_DIR / "swift-module-cache"
PYI_WORK_DIR = BUILD_DIR / "pyinstaller-work"
ICON_SOURCE = ROOT / "resources" / "app_icon.png"
ICONSET_DIR = BUILD_DIR / "app_icon.iconset"
ICON_FILE = BUILD_DIR / "app_icon.icns"


def _clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _prepare_export_dirs() -> None:
    EXPORT_DIR.mkdir(exist_ok=True)
    _clean_dir(BUILD_DIR)
    _clean_dir(PYI_DIR)
    _clean_dir(DIST_DIR)
    if APP_PATH.exists():
        shutil.rmtree(APP_PATH)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    PYI_DIR.mkdir(parents=True, exist_ok=True)


def _build_swift_helper() -> None:
    subprocess.run(
        [
            "swiftc",
            "-O",
            "-module-cache-path",
            str(SWIFT_CACHE_DIR),
            str(ROOT / "helpers" / "audio_level_helper.swift"),
            "-o",
            str(HELPER_BIN),
        ],
        check=True,
    )


def _build_icon() -> None:
    if not ICON_SOURCE.exists():
        raise RuntimeError(f"没有图标: {ICON_SOURCE}")
    ICONSET_DIR.mkdir(parents=True, exist_ok=True)
    sizes = [16, 32, 128, 256, 512]
    for size in sizes:
        out = ICONSET_DIR / f"icon_{size}x{size}.png"
        subprocess.run(["sips", "-z", str(size), str(size), str(ICON_SOURCE), "--out", str(out)], check=True)
        retina = ICONSET_DIR / f"icon_{size}x{size}@2x.png"
        if size < 512:
            subprocess.run(["sips", "-z", str(size * 2), str(size * 2), str(ICON_SOURCE), "--out", str(retina)], check=True)
    subprocess.run(["iconutil", "-c", "icns", str(ICONSET_DIR), "-o", str(ICON_FILE)], check=True)


def _build_app() -> None:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--icon",
        str(ICON_FILE),
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(PYI_WORK_DIR),
        "--specpath",
        str(PYI_DIR),
        "--add-data",
        f"{ROOT / 'assets'}:assets",
        "--add-data",
        f"{ROOT / 'config'}:config",
        "--add-binary",
        f"{HELPER_BIN}:helpers",
        str(ROOT / "main.py"),
    ]
    subprocess.run(cmd, check=True)


def _finalize_app() -> None:
    built_app = DIST_DIR / f"{APP_NAME}.app"
    if not built_app.exists():
        raise RuntimeError(f"没找到导出的 app: {built_app}")
    shutil.move(str(built_app), str(APP_PATH))
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(APP_PATH)], check=False)


def main() -> int:
    _prepare_export_dirs()
    _build_swift_helper()
    _build_icon()
    _build_app()
    _finalize_app()
    print(APP_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
