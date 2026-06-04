"""桌宠窗口：组合显示、输入和养成协调"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import monotonic

from PyQt6.QtCore import QPoint, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from core.animation import PET_STATES, PlaybackDebugSnapshot, PetAnimationDirector
from core.interaction_map import InteractionBehavior, InteractionMap
from core.playback.catalog import AnimationCatalog
from core.raising.activity import ActivityCatalog, ActivitySystem, load_activity_catalog
from core.raising.activity_playback import (
    ActivityPlaybackBridge,
    CarePlaybackBridge,
    VisualStateBridge,
)
from core.raising.items import ItemCatalog, load_item_catalog
from core.raising.notices import (
    auto_refill_missing_notice as _auto_refill_missing_notice,
    care_action_for_item_category as _care_action_for_item_category,
    format_item_deltas as _format_item_deltas,
    join_notice as _join_notice,
)
from core.raising.pet_session import AUTO_REFILL_MISSING_NOTICE_SECONDS
from core.raising.save_game import SaveGame
from core.raising.status_ticker import DEFAULT_TICK_SECONDS, PetStatusTicker
from ui.panels.status_panel import PetStatusPanel
from ui.pet_display import DevModePanel, PetDisplay
from ui.pet_window_parts import (
    dev_mode_controller,
    display_controller,
    input_controller,
    plugin_controls,
    status_presenter,
)
from ui.pet_window_parts.settings import (
    RESIZE_GRIP,
    ZOOM_STEP,
    dev_mode_from_json,
    load_settings,
    max_side_from_json,
    save_dev_mode_to_json,
    save_display_size_to_json,
    window_settings_path,
)
from ui.windows.activity_window import ActivityWindow
from ui.windows.shop_inventory_window import ShopInventoryWindow

import core.raising.pet_session as pet_session

_drop_paths = input_controller.drop_paths
_runtime_plugin_id = plugin_controls.runtime_plugin_id
_window_settings_path = window_settings_path
_load_settings = load_settings
_max_side_from_json = max_side_from_json
_dev_mode_from_json = dev_mode_from_json
_save_display_size_to_json = save_display_size_to_json
_save_dev_mode_to_json = save_dev_mode_to_json


class PetWindow(QMainWindow):
    save_game_changed = pyqtSignal()
    ZOOM_STEP = ZOOM_STEP

    click_through_enabled = display_controller.click_through_enabled
    set_click_through_enabled = display_controller.set_click_through_enabled
    always_on_top_enabled = display_controller.always_on_top_enabled
    set_always_on_top_enabled = display_controller.set_always_on_top_enabled
    _apply_window_flags = display_controller.apply_window_flags
    _fit_pixmap = display_controller.fit_pixmap
    _logical_pixmap_size = display_controller.logical_pixmap_size
    _resize_for_pixmap_size = display_controller.resize_for_pixmap_size
    set_pixmap = display_controller.set_pixmap
    _on_frame = display_controller.on_frame
    _refresh_current_pixmap = display_controller.refresh_current_pixmap
    _zoom = display_controller.zoom
    _restore_default_size = display_controller.restore_default_size
    _set_mode_autoswitch_enabled = display_controller.set_mode_autoswitch_enabled
    _set_auto_move_enabled = display_controller.set_auto_move_enabled
    _set_dev_mode_config_enabled = display_controller.set_dev_mode_config_enabled

    _current_debug_snapshot = dev_mode_controller.current_debug_snapshot
    _refresh_dev_debug = dev_mode_controller.refresh_dev_debug
    _set_dev_pet_state = dev_mode_controller.set_dev_pet_state
    _replay_dev_action = dev_mode_controller.replay_dev_action

    toggle_status_panel = status_presenter.toggle_status_panel
    show_status_panel = status_presenter.show_status_panel
    hide_status_panel = status_presenter.hide_status_panel
    populate_statusbar_menu = status_presenter.populate_statusbar_menu
    _connect_status_panel = status_presenter.connect_status_panel
    _show_shop_inventory_window = status_presenter.show_shop_inventory_window
    _show_activity_window = status_presenter.show_activity_window
    _handle_status_panel_message = status_presenter.handle_status_panel_message
    _reposition_status_panel = status_presenter.reposition_status_panel
    _clamp_status_panel_to_screen = status_presenter.clamp_status_panel_to_screen
    _sync_status_panel = status_presenter.sync_status_panel
    _sync_status_panel_controls = status_presenter.sync_status_panel_controls
    _sync_status_panel_info = status_presenter.sync_status_panel_info
    _sync_activity_panel = status_presenter.sync_activity_panel
    _sync_activity_window = status_presenter.sync_activity_window
    _sync_inventory_panel = status_presenter.sync_inventory_panel
    _sync_shop_inventory_window = status_presenter.sync_shop_inventory_window

    set_plugins = plugin_controls.set_plugins
    _sync_custom_panel = plugin_controls.sync_custom_panel
    _runtime_plugin_toggle_entries = plugin_controls.runtime_plugin_toggle_entries
    _set_runtime_plugin_enabled = plugin_controls.set_runtime_plugin_enabled
    _tomato_clock_plugin = plugin_controls.tomato_clock_plugin
    _set_tomato_clock_running = plugin_controls.set_tomato_clock_running
    _plugin_handlers = plugin_controls.plugin_handlers
    _plugin_menu_builders = plugin_controls.plugin_menu_builders
    _mode_handlers = plugin_controls.mode_handlers
    _populate_legacy_menu = plugin_controls.populate_legacy_menu
    _save_start_position = plugin_controls.save_start_position

    _advance_pet_status = pet_session.advance_pet_status
    _purchase_item = pet_session.purchase_item
    _use_item = pet_session.use_item
    _try_auto_refill_after_tick = pet_session.try_auto_refill_after_tick
    _auto_refill_missing_notice_state = pet_session.auto_refill_missing_notice_state
    _clear_auto_refill_missing_notice = pet_session.clear_auto_refill_missing_notice
    _clear_all_auto_refill_missing_notices = pet_session.clear_all_auto_refill_missing_notices
    _clear_resolved_auto_refill_missing_notices = (
        pet_session.clear_resolved_auto_refill_missing_notices
    )
    _show_auto_refill_missing_notice = pet_session.show_auto_refill_missing_notice
    _use_inventory_item_for_care = pet_session.use_inventory_item_for_care
    _start_activity = pet_session.start_activity
    _cancel_activity = pet_session.cancel_activity
    _set_status_decay_enabled = pet_session.set_status_decay_enabled
    _set_auto_refill_enabled = pet_session.set_auto_refill_enabled
    _set_auto_purchase_enabled = pet_session.set_auto_purchase_enabled
    _show_item_notice = pet_session.show_item_notice
    _show_activity_notice = pet_session.show_activity_notice
    _show_level_notice = pet_session.show_level_notice
    on_startup_complete = pet_session.on_startup_complete
    on_playback_idle = pet_session.on_playback_idle
    _on_care_playback_finished = pet_session.on_care_playback_finished
    _resume_loaded_activity_animation = pet_session.resume_loaded_activity_animation
    _request_visual_state_update = pet_session.request_visual_state_update
    _on_playback_idle = pet_session.handle_playback_idle
    _on_director_pet_state_changed = pet_session.handle_director_pet_state_changed

    _switch_mode = input_controller.switch_mode
    _in_resize_grip = input_controller.in_resize_grip
    _display_local_pos = input_controller.display_local_pos
    _resolve_display_behavior = input_controller.resolve_display_behavior
    _handle_behavior = input_controller.handle_behavior
    _start_user_press_interaction = input_controller.start_user_press_interaction
    _suspend_activity_animation_for_user_interaction = (
        input_controller.suspend_activity_animation_for_user_interaction
    )
    _resume_activity_animation_if_needed = input_controller.resume_activity_animation_if_needed
    _should_pause_plugins_for_press = input_controller.should_pause_plugins_for_press
    _reset_pointer_state = input_controller.reset_pointer_state
    _interaction_end_locked = input_controller.interaction_end_locked
    pause_plugins_for_interaction = input_controller.pause_plugins_for_interaction
    resume_plugins_after_interaction = input_controller.resume_plugins_after_interaction
    dragEnterEvent = input_controller.drag_enter_event
    dragMoveEvent = input_controller.drag_move_event
    dropEvent = input_controller.drop_event
    mousePressEvent = input_controller.mouse_press_event
    mouseMoveEvent = input_controller.mouse_move_event
    mouseReleaseEvent = input_controller.mouse_release_event
    contextMenuEvent = input_controller.context_menu_event

    def __init__(
        self,
        director: PetAnimationDirector,
        initial_pixmap: QPixmap,
        interaction_map: InteractionMap,
        mode_titles: dict[str, str] | None = None,
        mode_autoswitch_enabled: Callable[[], bool] | None = None,
        on_toggle_mode_autoswitch: Callable[[bool], None] | None = None,
        auto_move_enabled: Callable[[], bool] | None = None,
        on_toggle_auto_move: Callable[[bool], None] | None = None,
        action_blocked: Callable[[], bool] | None = None,
        on_open_editor: Callable[[], None] | None = None,
        save_game: SaveGame | None = None,
        activity_catalog: ActivityCatalog | None = None,
        item_catalog: ItemCatalog | None = None,
        animation_catalog: AnimationCatalog | None = None,
        *,
        max_side: int | None = None,
    ) -> None:
        super().__init__()
        self._director = director
        self._save_game = save_game or SaveGame()
        self._status_ticker = PetStatusTicker(self._save_game.pet_state)
        self._activity_system = ActivitySystem(
            self._save_game,
            activity_catalog or load_activity_catalog(),
        )
        self._item_catalog = item_catalog or load_item_catalog()
        self._auto_refill_missing_notice_shown_at: dict[str, float] = {}
        self._auto_refill_missing_notice_interval_seconds = (
            AUTO_REFILL_MISSING_NOTICE_SECONDS
        )
        self._auto_refill_notice_clock: Callable[[], float] = monotonic
        self._save_game_dirty_on_load = self._activity_system.changed_on_load
        self._interaction_map = interaction_map
        self._mode_titles = mode_titles or {}
        self._drag_anchor: QPoint | None = None
        self._press_global: QPoint | None = None
        self._press_is_drag = False
        self._press_interaction_started = False
        self._pressed_press_behavior = InteractionBehavior(type="none")
        self._pressed_click_behavior = InteractionBehavior(type="none")
        self._pressed_drag_behavior = InteractionBehavior(type="none")
        self._click_through_enabled = False
        self._mode_autoswitch_enabled = mode_autoswitch_enabled or (lambda: False)
        self._on_toggle_mode_autoswitch = on_toggle_mode_autoswitch or (lambda enabled: None)
        self._auto_move_enabled = auto_move_enabled or (lambda: False)
        self._on_toggle_auto_move = on_toggle_auto_move or (lambda enabled: None)
        self._action_blocked = action_blocked or (lambda: False)
        self._on_quit = QApplication.quit
        self._plugins = []
        self._drop_handlers: list[Callable[[list[Path]], None]] = []
        self._single_active = lambda: False
        self._single_debug_snapshot: Callable[[], PlaybackDebugSnapshot | None] = lambda: None
        self._single_replay_current: Callable[[], bool] = lambda: False
        self._interrupt_auto_move = lambda: None
        self._on_open_editor = on_open_editor
        if animation_catalog is None:
            raise ValueError("PetWindow 需要 animation_catalog 才能桥接活动动画")
        self._activity_playback = ActivityPlaybackBridge(
            director,
            animation_catalog,
            action_blocked=lambda: self._action_blocked(),
            single_active=lambda: self._single_active(),
        )
        self._care_playback = CarePlaybackBridge(
            director,
            animation_catalog,
            action_blocked=lambda: self._action_blocked(),
            activity_active=lambda: self._activity_system.is_active(),
            single_active=lambda: self._single_active(),
            schedule_once=lambda delay_ms, callback: QTimer.singleShot(delay_ms, callback),
            on_finished=self._on_care_playback_finished,
        )
        self._visual_state_bridge = VisualStateBridge(
            self._save_game.pet_state,
            director,
            action_blocked=lambda: self._action_blocked(),
            single_active=lambda: self._single_active(),
            activity_animation_active=self._activity_playback.is_active,
            care_animation_active=self._care_playback.is_active,
        )
        self._dev_mode = dev_mode_from_json()
        self._dev_mode_config_enabled = self._dev_mode
        self._always_on_top_enabled = True
        if max_side is None:
            max_side = max_side_from_json()
        self._max_side = max(0, max_side)
        self._default_max_side = self._max_side

        if self._dev_mode:
            self._base_window_flags = Qt.WindowType.Window
        else:
            self._base_window_flags = (
                Qt.WindowType.Window
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.NoDropShadowWindowHint
            )
        self._apply_window_flags()
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, not self._dev_mode)

        self._label = PetDisplay(self._interaction_map, self._dev_mode)
        self._dev_panel: DevModePanel | None = None
        self._source_pixmap = initial_pixmap

        pix0 = self._fit_pixmap(initial_pixmap)
        self._label.set_pet_pixmap(pix0)
        if self._dev_mode:
            self._dev_panel = DevModePanel(PET_STATES)
            self._dev_panel.pet_state_requested.connect(self._set_dev_pet_state)
            self._dev_panel.replay_requested.connect(self._replay_dev_action)
            central = QWidget(self)
            layout = QVBoxLayout(central)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(self._label, 1)
            layout.addWidget(self._dev_panel, 0)
            self.setCentralWidget(central)
        else:
            self.setCentralWidget(self._label)

        self._status_panel = PetStatusPanel(self)
        self._status_panel.set_activities(self._activity_system.activities())
        self._status_panel.set_item_catalog(self._item_catalog.items())
        self._shop_inventory_window = ShopInventoryWindow(self)
        self._shop_inventory_window.set_item_catalog(self._item_catalog.items())
        self._activity_window = ActivityWindow(self)
        self._activity_window.set_activities(self._activity_system.activities())
        self._connect_status_panel()
        self._sync_shop_inventory_window()
        self._sync_activity_window()
        self._status_tick_timer = QTimer(self)
        self._status_tick_timer.setInterval(DEFAULT_TICK_SECONDS * 1000)
        self._status_tick_timer.timeout.connect(self._advance_pet_status)
        self._status_tick_timer.start()

        w, h = self._logical_pixmap_size(pix0)
        self._resize_for_pixmap_size(w, h)
        self.setMinimumSize(48, 48)
        settings = load_settings()
        self.move(int(settings["display_x"]), int(settings["display_y"]))

        director.frame_changed.connect(self._on_frame)
        director.pet_state_changed.connect(self._on_director_pet_state_changed)
        director.interaction_finished.connect(self._on_playback_idle)
        self._refresh_dev_debug()

    def set_quit_callback(self, callback) -> None:
        self._on_quit = callback

    def save_game(self) -> SaveGame:
        return self._save_game

    def save_game_dirty_on_load(self) -> bool:
        return self._save_game_dirty_on_load

    def activity_active(self) -> bool:
        return self._activity_system.is_active()

    def automated_action_active(self) -> bool:
        return (
            self._activity_system.is_active()
            or self._activity_playback.is_active()
            or self._care_playback.is_active()
        )

    def add_drop_handler(self, handler: Callable[[list[Path]], None]) -> None:
        self._drop_handlers.append(handler)

    def set_single_active_callback(self, callback: Callable[[], bool]) -> None:
        self._single_active = callback

    def set_single_player(self, single_player) -> None:
        self._care_playback.set_single_player(single_player)

    def set_single_debug_callbacks(
        self,
        snapshot: Callable[[], PlaybackDebugSnapshot | None],
        replay_current: Callable[[], bool],
    ) -> None:
        self._single_debug_snapshot = snapshot
        self._single_replay_current = replay_current

    def set_auto_move_interrupt_callback(self, callback: Callable[[], None]) -> None:
        self._interrupt_auto_move = callback
