"""桌宠状态面板同步"""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QMenu

from core.performance import measure_ui


def toggle_status_panel(self) -> None:
    if self._status_panel.isVisible():
        self.hide_status_panel()
        return
    self.show_status_panel()


def show_status_panel(self) -> None:
    with measure_ui("status_panel.open"):
        self._sync_status_panel()
        self._status_panel.reset_view()
        self._reposition_status_panel()
        self._status_panel.show()
        self._status_panel.raise_()


def hide_status_panel(self) -> None:
    with measure_ui("status_panel.close"):
        self._status_panel.hide()


def populate_statusbar_menu(self, menu: QMenu) -> None:
    self._populate_legacy_menu(menu, include_status_panel=True)


def connect_status_panel(self) -> None:
    self._status_panel.zoom_in_requested.connect(lambda: self._zoom(self.ZOOM_STEP))
    self._status_panel.zoom_out_requested.connect(lambda: self._zoom(-self.ZOOM_STEP))
    self._status_panel.restore_size_requested.connect(self._restore_default_size)
    self._status_panel.always_on_top_toggled.connect(self.set_always_on_top_enabled)
    self._status_panel.click_through_toggled.connect(self.set_click_through_enabled)
    self._status_panel.auto_move_toggled.connect(self._set_auto_move_enabled)
    self._status_panel.dev_mode_toggled.connect(self._set_dev_mode_config_enabled)
    self._status_panel.status_decay_toggled.connect(self._set_status_decay_enabled)
    self._status_panel.auto_refill_toggled.connect(self._set_auto_refill_enabled)
    self._status_panel.auto_purchase_toggled.connect(self._set_auto_purchase_enabled)
    self._status_panel.quit_requested.connect(lambda: self._on_quit())
    self._status_panel.chat_requested.connect(self.open_chat_window)
    self._status_panel.shop_requested.connect(
        lambda: self._show_shop_inventory_window("shop")
    )
    self._status_panel.inventory_requested.connect(
        lambda: self._show_shop_inventory_window("inventory")
    )
    self._status_panel.activity_window_requested.connect(self._show_activity_window)
    self._shop_inventory_window.purchase_requested.connect(self._purchase_item)
    self._shop_inventory_window.use_requested.connect(self._use_item)
    self._status_panel.activity_requested.connect(self._start_activity)
    self._status_panel.activity_cancel_requested.connect(self._cancel_activity)
    self._status_panel.plugin_toggled.connect(self._set_runtime_plugin_enabled)
    self._status_panel.tomato_clock_toggled.connect(self._set_tomato_clock_running)
    self._activity_window.activity_requested.connect(self._start_activity)
    self._activity_window.activity_cancel_requested.connect(self._cancel_activity)
    self._status_panel.layout_changed.connect(self._clamp_status_panel_to_screen)


def show_shop_inventory_window(self, page: str) -> None:
    with measure_ui("shop_inventory.open_presenter", detail=page):
        self._sync_shop_inventory_window(force=True)
        self._shop_inventory_window.show_page(page)


def show_activity_window(self) -> None:
    with measure_ui("activity_window.open_presenter"):
        sync_activity_window(self, force=True)
        self._activity_window.show_window()


def handle_status_panel_message(self, message: str) -> None:
    del message


def reposition_status_panel(self) -> None:
    self._status_panel.move_near(self.geometry())


def clamp_status_panel_to_screen(self) -> None:
    panel = self._status_panel
    screen = QApplication.screenAt(panel.geometry().center())
    if screen is None:
        return
    available = screen.availableGeometry()
    x = min(max(panel.x(), available.left()), available.right() - panel.width())
    y = panel.y()
    if y < available.top():
        y = available.top()
    elif panel.y() + panel.height() > available.bottom() + 1:
        y = available.bottom() - panel.height() + 1
    if x != panel.x() or y != panel.y():
        panel.move(x, y)


def sync_status_panel(self) -> None:
    self._sync_status_panel_controls()
    self._sync_status_panel_info()
    self._sync_activity_panel()
    self._sync_inventory_panel()
    self._sync_custom_panel()


def sync_status_panel_controls(self) -> None:
    if not hasattr(self, "_status_panel"):
        return
    self._status_panel.set_system_state(
        always_on_top=self._always_on_top_enabled,
        click_through=self._click_through_enabled,
        auto_move=self._auto_move_enabled(),
        dev_mode=self._dev_mode_config_enabled,
        status_decay_enabled=self._save_game.status_decay_enabled,
        auto_refill_enabled=self._save_game.auto_refill_enabled,
        auto_purchase_enabled=self._save_game.auto_purchase_enabled,
    )


def sync_status_panel_info(self) -> None:
    if not hasattr(self, "_status_panel"):
        return
    self._status_panel.set_pet_state(
        self._save_game.pet_state,
        current_visual_state=self._director.pet_state(),
    )
    self._sync_shop_inventory_window()
    sync_activity_window(self)


def sync_activity_panel(self) -> None:
    if not hasattr(self, "_status_panel"):
        return
    snapshot = self._activity_system.snapshot()
    can_start = True
    if not snapshot.is_active:
        can_start = self._activity_playback.can_start_activity().ok
    self._status_panel.set_activity_snapshot(
        snapshot,
        can_start=can_start,
    )
    sync_activity_window(self, snapshot=snapshot, can_start=can_start)


def sync_activity_window(
    self,
    *,
    snapshot=None,
    can_start: bool | None = None,
    force: bool = False,
) -> None:
    if not hasattr(self, "_activity_window"):
        return
    window = self._activity_window
    if not force:
        is_visible = getattr(window, "isVisible", None)
        if callable(is_visible) and not is_visible():
            mark_dirty = getattr(window, "mark_dirty", None)
            if callable(mark_dirty):
                mark_dirty()
            return
    if snapshot is None:
        snapshot = self._activity_system.snapshot()
    if can_start is None:
        can_start = True
        if not snapshot.is_active:
            can_start = self._activity_playback.can_start_activity().ok
    with measure_ui("activity_window.sync", detail="force" if force else "visible"):
        window.set_pet_state(self._save_game.pet_state)
        window.set_activity_snapshot(snapshot, can_start=can_start)


def sync_inventory_panel(self) -> None:
    if not hasattr(self, "_status_panel"):
        return
    self._status_panel.set_inventory(
        self._save_game.inventory,
        money=self._save_game.pet_state.money,
    )
    self._sync_shop_inventory_window()


def sync_shop_inventory_window(self, *, force: bool = False) -> None:
    if not hasattr(self, "_shop_inventory_window"):
        return
    window = self._shop_inventory_window
    if not force:
        is_visible = getattr(window, "isVisible", None)
        if callable(is_visible) and not is_visible():
            mark_dirty = getattr(window, "mark_dirty", None)
            if callable(mark_dirty):
                mark_dirty()
            return
    with measure_ui("shop_inventory.sync", detail="force" if force else "visible"):
        window.set_pet_state(self._save_game.pet_state)
        window.set_inventory(self._save_game.inventory)
