"""桌宠主入口：初始化动画、窗口，元神启动"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox

from animation import Clip, Mode, PressHoldAnimator, PetAnimationDirector, load_numbered_pngs
from click_through import ClickThroughBadge
from pet_window import PetWindow

# 定义路径
ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ACTION_SETTINGS = ROOT / "action_settings.json"


def _load_settings() -> dict:
    return json.loads(ACTION_SETTINGS.read_text(encoding="utf-8"))


def _clip_from_dir(folder: str, interval_ms: int) -> Clip:
    frames = load_numbered_pngs(ASSETS / folder)
    if not frames:
        raise RuntimeError(f"Missing frames in {ASSETS / folder}")
    return Clip(frames=frames, interval_ms=interval_ms)


def _load_modes(settings: dict) -> tuple[dict[str, Mode], dict[str, str], str, str]:
    modes: dict[str, Mode] = {}
    mode_titles: dict[str, str] = {}
    for item in settings["modes"]:
        mode_id = str(item["id"])
        mode_type = str(item["type"])
        mode_titles[mode_id] = str(item["title"])
        loop = item["loop"]
        loop_clip = _clip_from_dir(
            str(loop["folder"]),
            interval_ms=int(loop["interval_ms"]),
        )
        if mode_type == "loop":
            modes[mode_id] = Mode(loop=loop_clip)
            continue
        if mode_type != "phased":
            raise RuntimeError(f"未知模式类型: {mode_type}")
        start = item["start"]
        end = item["end"]
        modes[mode_id] = Mode(
            loop=loop_clip,
            start=_clip_from_dir(
                str(start["folder"]),
                interval_ms=int(start["interval_ms"]),
            ),
            end=_clip_from_dir(
                str(end["folder"]),
                interval_ms=int(end["interval_ms"]),
            ),
        )

    default_mode = str(settings["default_mode"])
    press_mode = str(settings["press_mode"])
    if default_mode not in modes:
        raise RuntimeError(f"default_mode 未在 modes 中定义: {default_mode}")
    if press_mode not in modes:
        raise RuntimeError(f"press_mode 未在 modes 中定义: {press_mode}")
    if not modes[press_mode].is_phased:
        raise RuntimeError("press_mode 必须是 phased 模式")
    return modes, mode_titles, default_mode, press_mode


def main() -> int:
    app = QApplication(sys.argv)

    try:
        settings = _load_settings()
        modes, mode_titles, default_mode, press_mode = _load_modes(settings)
        press_source = modes[press_mode]
        if press_source.start is None or press_source.end is None:
            raise RuntimeError("press_mode 缺少 start 或 end")

        press = PressHoldAnimator(press_source.start, press_source.loop, press_source.end)
        director = PetAnimationDirector(
            modes=modes,
            default_mode=default_mode,
            press=press,
        )
        director.start_default_mode()

        initial_mode = modes[default_mode]
        initial_clip = initial_mode.start if initial_mode.is_phased else initial_mode.loop
        win = PetWindow(
            director,
            initial_clip.frames[0],
            mode_titles=mode_titles,
        )
        win.show()
        badge = ClickThroughBadge(
            target_window=win,
            is_enabled=win.click_through_enabled,
            set_enabled=win.set_click_through_enabled,
        )
        badge.show()

        return app.exec()
    except Exception as exc:  # json配置错误
        box = QMessageBox()
        box.setWindowTitle("配置错误")
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText("action_settings.json 内容有问题，请检查 JSON 格式和字段。")
        box.setDetailedText(str(exc))
        box.exec()
        return 1


if __name__ == "__main__":
    sys.exit(main())
