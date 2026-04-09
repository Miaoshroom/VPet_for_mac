"""桌宠主入口：初始化动画、窗口，元神启动"""
from __future__ import annotations

import random
import sys
sys.dont_write_bytecode = True

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.animation import Clip, FlipbookPlayer, PressHoldAnimator, PetAnimationDirector
from core.idle_autoswitch import start_auto_idle_timer
from core.interaction_map import load_interaction_map
from core.loader import load_action_config
from core.music_dance import MusicDanceController
from ui.click_through import ClickThroughBadge
from ui.pet_window import PetWindow


def _pick_single_clip(config_ids: tuple[str, ...], single_clips: dict[str, Clip]) -> Clip | None:
    if not config_ids:
        return None
    return single_clips[random.choice(config_ids)]


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

        initial_mode = config.modes[config.default_mode]
        if initial_mode.is_phased:
            initial_clip = initial_mode.start
        else:
            initial_clip = initial_mode.loop
        assert initial_clip is not None

        startup_clip = _pick_single_clip(config.startup, config.single_clips)
        initial_pixmap = startup_clip.frame(0) if startup_clip is not None else initial_clip.frame(0)

        auto_idle_timer = start_auto_idle_timer(
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
            auto_idle_timer=auto_idle_timer,
            parent=app,
        )
        app.aboutToQuit.connect(music_dance.shutdown)
        win = PetWindow(
            director,
            initial_pixmap,
            interaction_map=interaction_map,
            mode_titles=config.mode_titles,
            music_dance_enabled=music_dance.is_enabled,
            on_toggle_music_dance=music_dance.set_enabled,
        )
        win.show()
        badge = ClickThroughBadge(
            target_window=win,
            is_enabled=win.click_through_enabled,
            set_enabled=win.set_click_through_enabled,
        )
        badge.show()

        startup_player = FlipbookPlayer(app)
        startup_player.frame_changed.connect(win.set_pixmap)

        def start_default_mode() -> None:
            director.start_default_mode()
            win.setEnabled(True)

        if startup_clip is not None:
            win.setEnabled(False)
            startup_player.finished.connect(start_default_mode)
            QTimer.singleShot(0, lambda: startup_player.play(startup_clip, loop=False))
        else:
            start_default_mode()

        shutdown_player = FlipbookPlayer(app)
        shutdown_player.frame_changed.connect(win.set_pixmap)
        is_shutting_down = False

        def request_shutdown() -> None:
            nonlocal is_shutting_down
            if is_shutting_down:
                return
            is_shutting_down = True
            win.setEnabled(False)
            badge.hide()
            if auto_idle_timer is not None:
                auto_idle_timer.stop()
            music_dance.shutdown()
            director.stop()

            shutdown_clip = _pick_single_clip(config.shutdown, config.single_clips)
            if shutdown_clip is None:
                app.quit()
                return
            shutdown_player.finished.connect(app.quit)
            shutdown_player.play(shutdown_clip, loop=False)

        win.set_quit_callback(request_shutdown)

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
