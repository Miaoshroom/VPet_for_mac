"""桌宠主入口：初始化动画、窗口，元神启动"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QMessageBox

from animation import Clip, PressHoldAnimator, PetAnimationDirector, load_numbered_pngs
from pet_window import PetWindow

# 定义路径
ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"


def _clip_from_dir(name: str, interval_ms: int) -> Clip:
    frames = load_numbered_pngs(ASSETS / name)
    if not frames:
        raise RuntimeError(f"Missing frames in {ASSETS / name}")
    return Clip(frames=frames, interval_ms=interval_ms)


def _load_single_actions() -> dict[str, Clip]:
    # 从json读单次动画
    import json  # 局部导入

    settings_path = ROOT / "pet_settings.json"
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    actions: dict[str, Clip] = {}
    for item in data.get("single_actions", []):
        title = str(item["title"])
        folder = str(item["folder"])
        interval = int(item["interval_ms"])
        actions[title] = _clip_from_dir(folder, interval_ms=interval)
    return actions


def main() -> int:
    app = QApplication(sys.argv)

    try:

        idle = _clip_from_dir("idle", interval_ms=120)
        start_c = _clip_from_dir("press_start", interval_ms=90)
        loop_c = _clip_from_dir("press_loop", interval_ms=100)
        end_c = _clip_from_dir("press_end", interval_ms=90)
        single_actions = _load_single_actions()

        press = PressHoldAnimator(start_c, loop_c, end_c)
        director = PetAnimationDirector(idle=idle, press=press)
        director.start_idle()

        win = PetWindow(director, idle.frames[0], single_actions=single_actions)
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
