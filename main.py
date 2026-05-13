"""桌宠主入口：初始化动画、窗口，元神启动"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.animation import PressHoldAnimator, PetAnimationDirector
from core.auto_move import AutoMoveController
from core.plugin_loader import setup_plugins
from core.interaction_map import load_interaction_map
from core.loader import load_action_config
from core.mode_autoswitch import ModeAutoSwitch
from core.music_dance import MusicDanceController
from core.single_autoswitch import SingleAutoSwitch
from core.start_shut import build_shutdown_handler, pick_startup, play_startup
from ui.click_through import ClickThroughBadge
from ui.pet_window import PetWindow

ROOT = Path(__file__).resolve().parent
APP_ICON = ROOT / "resources" / "app_icon.png"


def main() -> int:
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(APP_ICON)))

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

        startup_clip, initial_pixmap = pick_startup(
            config.modes[config.default_mode],
            config.startup,
            config.single_clips,
        )

        mode_autoswitch = ModeAutoSwitch(
            app,
            director,
            config.idle_autoswitch_interval_min_ms,
            config.idle_autoswitch_interval_max_ms,
            config.auto_idle_modes,
        )
        music_dance = MusicDanceController(
            director=director,
            default_mode=config.default_mode,
            available_mode_ids=set(config.modes),
            auto_idle_timer=mode_autoswitch,
            parent=app,
        )
        auto_move: AutoMoveController | None = None

        def is_auto_move_enabled() -> bool:
            return auto_move.is_enabled() if auto_move is not None else False

        def set_auto_move_enabled(enabled: bool) -> None:
            if auto_move is not None:
                auto_move.set_enabled(enabled)

        app.aboutToQuit.connect(music_dance.shutdown)
        win = PetWindow(
            director,
            initial_pixmap,
            interaction_map=interaction_map,
            mode_titles=config.mode_titles,
            music_dance_enabled=music_dance.is_enabled,
            on_toggle_music_dance=music_dance.set_enabled,
            mode_autoswitch_enabled=mode_autoswitch.is_enabled,
            on_toggle_mode_autoswitch=mode_autoswitch.set_enabled,
            auto_move_enabled=is_auto_move_enabled,
            on_toggle_auto_move=set_auto_move_enabled,
        )
        win.show()
        badge = ClickThroughBadge(
            target_window=win,
            is_enabled=win.click_through_enabled,
            set_enabled=win.set_click_through_enabled,
        )
        badge.show()

        single_autoswitch = SingleAutoSwitch(
            parent=app,
            director=director,
            window=win,
            interval_min_ms=config.single_insert_interval_min_ms,
            interval_max_ms=config.single_insert_interval_max_ms,
            mode_ids=config.single_insert_modes,
            single_clips=config.single_clips,
            music_dance_enabled=music_dance.is_enabled,
            mode_autoswitch_timer=mode_autoswitch,
        )
        auto_move = AutoMoveController(
            parent=app,
            director=director,
            window=win,
            modes=config.modes,
            music_dance_enabled=music_dance.is_enabled,
            single_autoswitch=single_autoswitch,
            mode_autoswitch=mode_autoswitch,
        )
        app.aboutToQuit.connect(auto_move.shutdown)

        play_startup(app, win, director, single_autoswitch, startup_clip)

        win.set_quit_callback(
            build_shutdown_handler(
                app=app,
                window=win,
                badge=badge,
                director=director,
                single_autoswitch=single_autoswitch,
                music_dance=music_dance,
                mode_autoswitch_timer=mode_autoswitch,
                shutdown_ids=config.shutdown,
                single_clips=config.single_clips,
            )
        )

        _plugins = setup_plugins({
            "app": app,
            "window": win,
        })
        win.set_plugins(_plugins)

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
