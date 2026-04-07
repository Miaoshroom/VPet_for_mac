"""桌宠主入口：初始化动画、窗口，元神启动"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

from PyQt6.QtWidgets import QApplication, QMessageBox

from core.animation import PressHoldAnimator, PetAnimationDirector
from core.loader import load_action_config
from ui.click_through import ClickThroughBadge
from ui.pet_window import PetWindow


def main() -> int:
    app = QApplication(sys.argv)

    try:
        config = load_action_config()
        press_source = config.modes[config.press_mode]
        if press_source.start is None or press_source.end is None:
            raise RuntimeError("press_mode 缺少 start 或 end")

        press = PressHoldAnimator(press_source.start, press_source.loop, press_source.end)
        director = PetAnimationDirector(
            modes=config.modes,
            default_mode=config.default_mode,
            press=press,
        )
        director.start_default_mode()

        initial_mode = config.modes[config.default_mode]
        initial_clip = initial_mode.start if initial_mode.is_phased else initial_mode.loop
        win = PetWindow(
            director,
            initial_clip.frames[0],
            mode_titles=config.mode_titles,
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
