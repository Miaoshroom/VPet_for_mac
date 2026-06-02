"""右键菜单"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QMenu, QWidget


def populate_pet_menu(
    menu: QMenu,
    on_zoom_in: Callable[[], None],  # 放大/缩小回调函数
    on_zoom_out: Callable[[], None],
    mode_autoswitch_enabled: bool,
    on_toggle_mode_autoswitch: Callable[[bool], None],
    auto_move_enabled: bool,
    on_toggle_auto_move: Callable[[bool], None],
    mode_handlers: dict[str, Callable[[], None]],  # 生成动态动作列表
    plugin_handlers: dict[str, tuple[bool, Callable[[bool], None]]],
    plugin_menu_builders: list[Callable[[QMenu], None]],
    current_mode_title: str | None,
    on_quit: Callable[[], None],  # 退出程序
    on_set_start_pos: Callable[[], None],  # 设置启动位置回调
    on_open_editor: Callable[[], None] | None = None,  # 打开编辑器
    on_toggle_status_panel: Callable[[], None] | None = None,
) -> None:
    if on_toggle_status_panel is not None:
        status_panel = menu.addAction("状态面板")
        status_panel.triggered.connect(on_toggle_status_panel)
        menu.addSeparator()

    zoom_in = menu.addAction("放大")
    zoom_in.triggered.connect(on_zoom_in)
    zoom_out = menu.addAction("缩小")
    zoom_out.triggered.connect(on_zoom_out)
    mode_autoswitch = menu.addAction("随机切换动作")
    mode_autoswitch.setCheckable(True)
    mode_autoswitch.setChecked(mode_autoswitch_enabled)
    mode_autoswitch.triggered.connect(
        lambda checked=False: on_toggle_mode_autoswitch(bool(checked))
    )
    auto_move = menu.addAction("随机移动")
    auto_move.setCheckable(True)
    auto_move.setChecked(auto_move_enabled)
    auto_move.triggered.connect(lambda checked=False: on_toggle_auto_move(bool(checked)))

    for build_menu in plugin_menu_builders:
        build_menu(menu)

    plugin_menu = menu.addMenu("插件")
    for title, (enabled, handler) in plugin_handlers.items():
        action = plugin_menu.addAction(title)
        action.setCheckable(True)
        action.setChecked(enabled)
        action.triggered.connect(lambda checked=False, handler=handler: handler(bool(checked)))

    switch_menu = menu.addMenu("切换动作")
    for title, handler in mode_handlers.items():
        action = switch_menu.addAction(title)
        action.setCheckable(True)
        action.setChecked(title == current_mode_title)
        action.triggered.connect(lambda checked=False, handler=handler: handler())
    set_start_pos = menu.addAction("设置启动位置")
    set_start_pos.triggered.connect(on_set_start_pos)
    if on_open_editor is not None:
        editor_action = menu.addAction("编辑器")
        editor_action.triggered.connect(on_open_editor)
    menu.addSeparator()
    quit_action = menu.addAction("退出")
    quit_action.triggered.connect(on_quit)


def build_pet_menu(
    parent: QWidget | None,
    on_zoom_in: Callable[[], None],
    on_zoom_out: Callable[[], None],
    mode_autoswitch_enabled: bool,
    on_toggle_mode_autoswitch: Callable[[bool], None],
    auto_move_enabled: bool,
    on_toggle_auto_move: Callable[[bool], None],
    mode_handlers: dict[str, Callable[[], None]],  # 生成动态动作列表
    plugin_handlers: dict[str, tuple[bool, Callable[[bool], None]]],
    plugin_menu_builders: list[Callable[[QMenu], None]],
    current_mode_title: str | None,
    on_quit: Callable[[], None],  # 退出程序
    on_set_start_pos: Callable[[], None],  # 设置启动位置回调
    on_open_editor: Callable[[], None] | None = None,  # 打开编辑器
    on_toggle_status_panel: Callable[[], None] | None = None,
) -> QMenu:
    menu = QMenu(parent)
    populate_pet_menu(
        menu,
        on_zoom_in=on_zoom_in,
        on_zoom_out=on_zoom_out,
        mode_autoswitch_enabled=mode_autoswitch_enabled,
        on_toggle_mode_autoswitch=on_toggle_mode_autoswitch,
        auto_move_enabled=auto_move_enabled,
        on_toggle_auto_move=on_toggle_auto_move,
        mode_handlers=mode_handlers,
        plugin_handlers=plugin_handlers,
        plugin_menu_builders=plugin_menu_builders,
        current_mode_title=current_mode_title,
        on_quit=on_quit,
        on_set_start_pos=on_set_start_pos,
        on_open_editor=on_open_editor,
        on_toggle_status_panel=on_toggle_status_panel,
    )
    return menu


def show_pet_menu(
    parent: QWidget,
    global_pos: QPoint,
    on_zoom_in: Callable[[], None],  # 放大/缩小回调函数
    on_zoom_out: Callable[[], None],
    mode_autoswitch_enabled: bool,
    on_toggle_mode_autoswitch: Callable[[bool], None],
    auto_move_enabled: bool,
    on_toggle_auto_move: Callable[[bool], None],
    mode_handlers: dict[str, Callable[[], None]],  # 生成动态动作列表
    plugin_handlers: dict[str, tuple[bool, Callable[[bool], None]]],
    plugin_menu_builders: list[Callable[[QMenu], None]],
    current_mode_title: str | None,
    on_quit: Callable[[], None],  # 退出程序
    on_set_start_pos: Callable[[], None],  # 设置启动位置回调
    on_open_editor: Callable[[], None] | None = None,  # 打开编辑器
    on_toggle_status_panel: Callable[[], None] | None = None,
) -> None:
    menu = build_pet_menu(
        parent,
        on_zoom_in=on_zoom_in,
        on_zoom_out=on_zoom_out,
        mode_autoswitch_enabled=mode_autoswitch_enabled,
        on_toggle_mode_autoswitch=on_toggle_mode_autoswitch,
        auto_move_enabled=auto_move_enabled,
        on_toggle_auto_move=on_toggle_auto_move,
        mode_handlers=mode_handlers,
        plugin_handlers=plugin_handlers,
        plugin_menu_builders=plugin_menu_builders,
        current_mode_title=current_mode_title,
        on_quit=on_quit,
        on_set_start_pos=on_set_start_pos,
        on_open_editor=on_open_editor,
        on_toggle_status_panel=on_toggle_status_panel,
    )

    menu.exec(global_pos)
