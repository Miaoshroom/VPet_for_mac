"""桌宠主入口：初始化动画、窗口，元神启动"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

from PyQt6.QtWidgets import QApplication, QMessageBox

from core.animation import PressHoldAnimator, PetAnimationDirector
from core.idle_autoswitch import start_auto_idle_timer
from core.interaction_map import load_interaction_map
from core.loader import load_action_config
from ui.click_through import ClickThroughBadge
from ui.dev_window import PetWindow


def main() -> int:
    app = QApplication(sys.argv)

    try:
        config = load_action_config()
        interaction_map = load_interaction_map(set(config.modes))
        interactions: dict[str, PressHoldAnimator] = {}
        for mode_name, mode in config.modes.items():
            if not mode.is_phased:
                continue
            if mode.start is None or mode.end is None:
                raise RuntimeError(f"{mode_name} 缺少 start 或 end")
            interactions[mode_name] = PressHoldAnimator(mode.start, mode.loop, mode.end)
        director = PetAnimationDirector(
            modes=config.modes,
            default_mode=config.default_mode,
            interactions=interactions,
            default_interaction=config.press_mode,
        )
        director.start_default_mode()

        initial_mode = config.modes[config.default_mode]
        initial_clip = initial_mode.start if initial_mode.is_phased else initial_mode.loop
        win = PetWindow(
            director,
            initial_clip.frames[0],
            interaction_map=interaction_map,
            mode_titles=config.mode_titles,
        )
        win.show()
        badge = ClickThroughBadge(
            target_window=win,
            is_enabled=win.click_through_enabled,
            set_enabled=win.set_click_through_enabled,
        )
        badge.show()
        auto_idle_timer = start_auto_idle_timer(
            app,
            director,
            config.idle_autoswitch_interval_min_ms,
            config.idle_autoswitch_interval_max_ms,
            config.auto_idle_modes,
        )

        return app.exec()
    except Exception as exc:  # json配置错误
        box = QMessageBox()
        box.setWindowTitle("配置错误")
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText("config 下的配置文件内容有问题，请检查 JSON 格式和字段。")
        box.setDetailedText(str(exc))
        box.exec()
        return 1


if __name__ == "__main__":
    sys.exit(main())
