"""桌宠主入口：初始化动画、窗口，元神启动"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox

from animation import Clip, PressHoldAnimator, PetAnimationDirector, load_numbered_pngs
from pet_window import PetWindow

# 定义路径
ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
SETTINGS = ROOT / "pet_settings.json"


def _load_settings() -> dict:
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


def _clip_from_dir(folder: str, interval_ms: int) -> Clip:
    frames = load_numbered_pngs(ASSETS / folder)
    if not frames:
        raise RuntimeError(f"Missing frames in {ASSETS / folder}")
    return Clip(frames=frames, interval_ms=interval_ms)


def _load_states(settings: dict) -> tuple[dict[str, Clip], dict[str, str], str]:
    states: dict[str, Clip] = {}
    state_titles: dict[str, str] = {}
    for item in settings.get("states", []):
        state_id = str(item["id"])
        state_titles[state_id] = str(item["title"])
        states[state_id] = _clip_from_dir(
            str(item["folder"]),
            interval_ms=int(item["interval_ms"]),
        )

    default_state = str(settings["default_state"])
    if default_state not in states:
        raise RuntimeError(f"default_state 未在 states 中定义: {default_state}")
    return states, state_titles, default_state


def _load_press_clip(settings: dict, phase: str) -> Clip:
    press = settings["interactions"]["press"][phase]
    return _clip_from_dir(
        str(press["folder"]),
        interval_ms=int(press["interval_ms"]),
    )


def main() -> int:
    app = QApplication(sys.argv)

    try:
        settings = _load_settings()
        states, state_titles, default_state = _load_states(settings)
        start_c = _load_press_clip(settings, "start")
        loop_c = _load_press_clip(settings, "loop")
        end_c = _load_press_clip(settings, "end")

        press = PressHoldAnimator(start_c, loop_c, end_c)
        director = PetAnimationDirector(
            states=states,
            default_state=default_state,
            press=press,
        )
        director.start_default_state()

        initial_clip = states[default_state]
        win = PetWindow(
            director,
            initial_clip.frames[0],
            state_titles=state_titles,
        )
        win.show()

        return app.exec()
    except Exception as exc:  # json配置错误
        box = QMessageBox()
        box.setWindowTitle("配置错误")
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText("pet_settings.json 内容有问题，请检查 JSON 格式和字段。")
        box.setDetailedText(str(exc))
        box.exec()
        return 1


if __name__ == "__main__":
    sys.exit(main())
