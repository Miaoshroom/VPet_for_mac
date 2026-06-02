"""桌宠插件和旧菜单控制"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QMenu

from ui.pet_menu import populate_pet_menu
from ui.pet_window_parts.settings import save_start_position_to_json


def set_plugins(self, plugins) -> None:
    self._plugins = list(plugins)
    self._sync_custom_panel()


def sync_custom_panel(self) -> None:
    if not hasattr(self, "_status_panel"):
        return
    set_plugin_toggles = getattr(self._status_panel, "set_plugin_toggles", None)
    if callable(set_plugin_toggles):
        set_plugin_toggles(runtime_plugin_toggle_entries(self))
    set_tomato_clock_state = getattr(
        self._status_panel,
        "set_tomato_clock_state",
        None,
    )
    if callable(set_tomato_clock_state):
        tomato = tomato_clock_plugin(self)
        set_running = getattr(tomato, "set_running", None) if tomato is not None else None
        available = tomato is not None and callable(set_running)
        is_running = getattr(tomato, "is_running", None) if tomato is not None else None
        is_paused = getattr(tomato, "is_paused", None) if tomato is not None else None
        running = bool(is_running()) if available and callable(is_running) else False
        paused = bool(is_paused()) if available and callable(is_paused) else False
        set_tomato_clock_state(
            available=available,
            running=running,
            paused=paused,
        )


def runtime_plugin_toggle_entries(self) -> tuple[tuple[str, str, bool], ...]:
    entries: list[tuple[str, str, bool]] = []
    for plugin in getattr(self, "_plugins", []):
        if callable(getattr(plugin, "build_menu", None)):
            continue
        menu_title = getattr(plugin, "menu_title", None)
        is_enabled = getattr(plugin, "is_enabled", None)
        set_enabled = getattr(plugin, "set_enabled", None)
        if callable(menu_title) and callable(is_enabled) and callable(set_enabled):
            entries.append(
                (
                    runtime_plugin_id(plugin),
                    str(menu_title()),
                    bool(is_enabled()),
                )
            )
    return tuple(entries)


def set_runtime_plugin_enabled(self, plugin_id: str, enabled: bool) -> None:
    target_id = str(plugin_id)
    for plugin in getattr(self, "_plugins", []):
        if runtime_plugin_id(plugin) != target_id:
            continue
        set_enabled = getattr(plugin, "set_enabled", None)
        if callable(set_enabled):
            set_enabled(bool(enabled))
        break
    sync_custom_panel(self)


def tomato_clock_plugin(self):
    for plugin in getattr(self, "_plugins", []):
        if runtime_plugin_id(plugin) == "tomato_clock":
            return plugin
    return None


def set_tomato_clock_running(self, enabled: bool) -> None:
    tomato = tomato_clock_plugin(self)
    set_running = getattr(tomato, "set_running", None) if tomato is not None else None
    if callable(set_running):
        set_running(bool(enabled))
    sync_custom_panel(self)


def plugin_handlers(self) -> dict[str, tuple[bool, Callable[[bool], None]]]:
    handlers = {}
    for plugin in self._plugins:
        if callable(getattr(plugin, "build_menu", None)):
            continue
        menu_title = getattr(plugin, "menu_title", None)
        is_enabled = getattr(plugin, "is_enabled", None)
        set_enabled = getattr(plugin, "set_enabled", None)
        if callable(menu_title) and callable(is_enabled) and callable(set_enabled):
            handlers[str(menu_title())] = (bool(is_enabled()), set_enabled)
    return handlers


def plugin_menu_builders(self) -> list[Callable]:
    builders = []
    for plugin in self._plugins:
        build_menu = getattr(plugin, "build_menu", None)
        if callable(build_menu):
            builders.append(build_menu)
    return builders


def mode_handlers(self) -> dict[str, Callable[[], None]]:
    available_modes = self._director.available_mode_ids(self._mode_titles)
    return {
        title: (lambda name=mode_name: self._switch_mode(name))
        # 旧菜单只展示当前状态能播的动作
        for mode_name in available_modes
        if (title := self._mode_titles.get(mode_name)) is not None
    }


def populate_legacy_menu(self, menu: QMenu, *, include_status_panel: bool) -> None:
    populate_pet_menu(
        menu,
        on_zoom_in=lambda: self._zoom(self.ZOOM_STEP),
        on_zoom_out=lambda: self._zoom(-self.ZOOM_STEP),
        mode_autoswitch_enabled=self._mode_autoswitch_enabled(),
        on_toggle_mode_autoswitch=self._set_mode_autoswitch_enabled,
        auto_move_enabled=self._auto_move_enabled(),
        on_toggle_auto_move=self._set_auto_move_enabled,
        mode_handlers=self._mode_handlers(),
        plugin_handlers=self._plugin_handlers(),
        plugin_menu_builders=self._plugin_menu_builders(),
        current_mode_title=self._mode_titles.get(self._director.current_mode_name()),
        on_quit=self._on_quit,
        on_set_start_pos=self._save_start_position,
        on_open_editor=self._on_open_editor,
        on_toggle_status_panel=self.toggle_status_panel if include_status_panel else None,
    )


def save_start_position(self) -> None:
    save_start_position_to_json(self.x(), self.y(), self._max_side)


def runtime_plugin_id(plugin) -> str:
    value = getattr(plugin, "PLUGIN_NAME", None)
    if value:
        return str(value)
    return plugin.__class__.__name__

