"""桌宠主入口：初始化动画、窗口，元神启动"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

from pathlib import Path

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.raising.activity import load_activity_catalog
from core.animation import PressHoldAnimator, PetAnimationDirector
from core.auto_move import AutoMoveController
from core.interaction_map import load_interaction_map
from core.raising.items import load_item_catalog
from core.loader import load_action_config
from core.mode_autoswitch import ModeAutoSwitch
from core.plugin_host import PluginRuntime, setup_plugins
from core.raising.save_game import load_save_game, write_save_game
from core.single_autoswitch import SingleAutoSwitch
from core.single_player import SinglePlayer
from core.start_shut import build_shutdown_handler, pick_startup, play_startup
from ui.click_through import ClickThroughBadge
from ui.pet_window import PetWindow
from ui.statusbar_icon import create_statusbar_icon
from ui.shared.theme import apply_app_theme

ROOT = Path(__file__).resolve().parent
APP_ICON = ROOT / "resources" / "app_icon.png"
BAR_ICON = ROOT / "resources" / "bar_icon.png"


def main() -> int:
    app = QApplication(sys.argv)
    apply_app_theme(app)
    app.setWindowIcon(QIcon(str(APP_ICON)))

    try:
        config = load_action_config()
        save_game = load_save_game()
        activity_catalog = load_activity_catalog()
        item_catalog = load_item_catalog()
        interaction_map = load_interaction_map(set(config.animation_catalog.action_ids()))
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
            animation_catalog=config.animation_catalog,
            pet_state=config.pet_state,
        )

        startup_clip, initial_pixmap = pick_startup(
            config.modes[config.default_mode],
            config.startup,
            animation_catalog=config.animation_catalog,
            pet_state=config.pet_state,
        )

        plugin_runtime = PluginRuntime()
        win: PetWindow | None = None

        def window_automated_action_active() -> bool:
            return win.automated_action_active() if win is not None else False

        def automated_action_blocked() -> bool:
            return plugin_runtime.action_active() or window_automated_action_active()

        mode_autoswitch = ModeAutoSwitch(
            app,
            director,
            config.idle_autoswitch_interval_min_ms,
            config.idle_autoswitch_interval_max_ms,
            config.auto_idle_modes,
            action_blocked=automated_action_blocked,
        )
        auto_move: AutoMoveController | None = None

        def is_auto_move_enabled() -> bool:
            return auto_move.is_enabled() if auto_move is not None else False

        def set_auto_move_enabled(enabled: bool) -> None:
            if auto_move is not None:
                auto_move.set_enabled(enabled)

        def open_editor() -> None:
            QProcess.startDetached(
                sys.executable,
                [str(ROOT / "editor" / "main.py")],
            )

        win = PetWindow(
            director,
            initial_pixmap,
            interaction_map=interaction_map,
            mode_titles=config.mode_titles,
            mode_autoswitch_enabled=mode_autoswitch.is_enabled,
            on_toggle_mode_autoswitch=mode_autoswitch.set_enabled,
            auto_move_enabled=is_auto_move_enabled,
            on_toggle_auto_move=set_auto_move_enabled,
            action_blocked=plugin_runtime.action_active,
            on_open_editor=open_editor,
            save_game=save_game,
            activity_catalog=activity_catalog,
            item_catalog=item_catalog,
            animation_catalog=config.animation_catalog,
        )
        win.show()
        badge = ClickThroughBadge(
            target_window=win,
            is_enabled=win.click_through_enabled,
            set_enabled=win.set_click_through_enabled,
        )
        badge.show()

        single_player = SinglePlayer(
            parent=app,
            director=director,
            window=win,
            animation_catalog=config.animation_catalog,
        )
        win.set_single_player(single_player)
        win.set_single_debug_callbacks(
            single_player.debug_snapshot,
            single_player.replay_current_action,
        )
        single_autoswitch = SingleAutoSwitch(
            parent=app,
            director=director,
            interval_min_ms=config.single_insert_interval_min_ms,
            interval_max_ms=config.single_insert_interval_max_ms,
            mode_ids=config.single_insert_modes,
            action_blocked=automated_action_blocked,
            single_player=single_player,
            animation_catalog=config.animation_catalog,
            mode_autoswitch_timer=mode_autoswitch,
        )
        auto_move = AutoMoveController(
            parent=app,
            director=director,
            window=win,
            action_blocked=automated_action_blocked,
            single_autoswitch=single_autoswitch,
            mode_autoswitch=mode_autoswitch,
            single_active=single_player.is_active,
        )
        app.aboutToQuit.connect(auto_move.shutdown)

        save_dirty = False

        def mark_save_dirty() -> None:
            nonlocal save_dirty
            save_dirty = True

        win.save_game_changed.connect(mark_save_dirty)
        if win.save_game_dirty_on_load():
            mark_save_dirty()

        def save_player_progress() -> bool:
            try:
                write_save_game(win.save_game())
                return True
            except OSError:
                return False

        def autosave_player_progress() -> None:
            nonlocal save_dirty
            if not save_dirty:
                return
            if save_player_progress():
                save_dirty = False

        autosave_timer = QTimer(app)
        autosave_timer.setInterval(5 * 60 * 1000)
        autosave_timer.timeout.connect(autosave_player_progress)
        autosave_timer.start()

        app.aboutToQuit.connect(save_player_progress)
        win.set_single_active_callback(single_player.blocks_interaction)
        win.set_auto_move_interrupt_callback(auto_move.interrupt)

        single_player.finished.connect(win.on_playback_idle)
        play_startup(
            win,
            director,
            single_autoswitch,
            single_player,
            startup_clip,
            after_startup=win.on_startup_complete,
        )

        _plugins = setup_plugins({
            "app": app,
            "window": win,
            "director": director,
            "animation_catalog": config.animation_catalog,
            "default_mode": config.default_mode,
            "mode_autoswitch": mode_autoswitch,
            "plugin_runtime": plugin_runtime,
            "single_player": single_player,
            "auto_move": auto_move,
        })
        win.set_plugins(_plugins)

        def shutdown_plugins() -> None:
            for plugin in _plugins:
                shutdown = getattr(plugin, "shutdown", None)
                if callable(shutdown):
                    shutdown()

        # 右键和状态栏共用退出流程
        quit_callback = build_shutdown_handler(
            app=app,
            window=win,
            badge=badge,
            director=director,
            single_autoswitch=single_autoswitch,
            single_player=single_player,
            mode_autoswitch_timer=mode_autoswitch,
            shutdown_hooks=(auto_move.shutdown, shutdown_plugins),
            shutdown_ids=config.shutdown,
            animation_catalog=config.animation_catalog,
        )
        win.set_quit_callback(quit_callback)
        _statusbar_icon = create_statusbar_icon(
            app,
            BAR_ICON,
            quit_callback,
            build_menu=win.populate_statusbar_menu,
        )

        return app.exec()
    except Exception as exc:  # 启动阶段的 JSON 或存档错误
        box = QMessageBox()
        box.setWindowTitle("启动失败")
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText("配置文件或存档内容有问题，请检查 JSON 格式和字段。")
        box.setDetailedText(str(exc))
        box.exec()
        return 1


if __name__ == "__main__":
    sys.exit(main())
