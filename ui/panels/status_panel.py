"""轻量状态面板"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QRect, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.raising.activity import ActivitySnapshot
from core.raising.items import inventory_count
from core.raising.leveling import exp_to_next_level, required_exp_for_level
from core.raising.pet_state import PetState


class PetStatusPanel(QFrame):
    zoom_in_requested = pyqtSignal()
    zoom_out_requested = pyqtSignal()
    restore_size_requested = pyqtSignal()
    always_on_top_toggled = pyqtSignal(bool)
    click_through_toggled = pyqtSignal(bool)
    auto_move_toggled = pyqtSignal(bool)
    dev_mode_toggled = pyqtSignal(bool)
    status_decay_toggled = pyqtSignal(bool)
    auto_refill_toggled = pyqtSignal(bool)
    auto_purchase_toggled = pyqtSignal(bool)
    quit_requested = pyqtSignal()
    message_submitted = pyqtSignal(str)
    shop_requested = pyqtSignal()
    inventory_requested = pyqtSignal()
    activity_requested = pyqtSignal(str)
    activity_cancel_requested = pyqtSignal()
    activity_window_requested = pyqtSignal()
    plugin_toggled = pyqtSignal(str, bool)
    tomato_clock_toggled = pyqtSignal(bool)
    layout_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._info_labels: dict[str, QLabel] = {}
        self._metric_bars: dict[str, QProgressBar] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_button_sections: dict[QPushButton, str] = {}
        self._pages: dict[str, QWidget] = {}
        self._active_section: str | None = None
        self._shell: QFrame | None = None
        self._chat_row: QFrame | None = None
        self._detail_frame: QFrame | None = None
        self._page_stack: QStackedWidget | None = None
        self._activity_notice_label: QLabel | None = None
        self._care_notice_label: QLabel | None = None
        self._level_notice_label: QLabel | None = None
        self._shop_money_label: QLabel | None = None
        self._inventory_count_label: QLabel | None = None
        self._inventory: dict[str, int] = {}
        self._activity_summary_label: QLabel | None = None
        self._activity_progress_bar: QProgressBar | None = None
        self._activity_cancel_button: QPushButton | None = None
        self._activity_window_button: QPushButton | None = None
        self._plugin_toggle_layout: QVBoxLayout | None = None
        self._plugin_toggle_checks: dict[str, QCheckBox] = {}
        self._tomato_clock_check: QCheckBox | None = None
        self._current_activity_snapshot = ActivitySnapshot.idle()
        self._current_pet_state = PetState()
        self._activity_can_start = True
        self._applying_panel_style = False
        self._leave_close_timer = QTimer(self)
        self._leave_close_timer.setSingleShot(True)
        self._leave_close_timer.setInterval(200)
        self._leave_close_timer.timeout.connect(self._close_after_leave_delay)

        self._topmost_check = QCheckBox("置顶")
        self._click_through_check = QCheckBox("鼠标穿透")
        self._auto_move_check = QCheckBox("自动移动")
        self._dev_mode_check = QCheckBox("开发模式")
        self._status_decay_check = QCheckBox("状态变化开关")
        self._auto_refill_check = QCheckBox("自动使用背包物品")
        self._auto_purchase_check = QCheckBox("缺货时自动购买")

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(324)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._build_shell())

        self._topmost_check.toggled.connect(self.always_on_top_toggled)
        self._click_through_check.toggled.connect(self.click_through_toggled)
        self._auto_move_check.toggled.connect(self.auto_move_toggled)
        self._dev_mode_check.toggled.connect(self.dev_mode_toggled)
        self._status_decay_check.toggled.connect(self.status_decay_toggled)
        self._auto_refill_check.toggled.connect(self.auto_refill_toggled)
        self._auto_purchase_check.toggled.connect(self.auto_purchase_toggled)
        self._dev_mode_check.setToolTip("重启后生效")
        self._auto_refill_check.setToolTip("在线状态 tick 后，每次最多自动使用 1 个合适物品。")
        self._auto_purchase_check.setToolTip(
            "仅在自动使用开启且背包缺货时尝试购买 1 个便宜合适物品。"
        )

        self.set_pet_state(PetState())
        self.reset_view()
        self.hide()

    def reset_view(self, *, anchor_bottom: bool = False) -> None:
        bottom = self.geometry().bottom()
        self._leave_close_timer.stop()
        self._active_section = None
        if self._chat_row is not None:
            self._chat_row.show()
        if self._detail_frame is not None:
            self._detail_frame.hide()
        for button in self._nav_buttons.values():
            button.setChecked(False)
        self._resize_to_hint(anchor_bottom=anchor_bottom, bottom=bottom)

    def move_near(self, pet_geometry: QRect) -> None:
        self._resize_to_hint()
        panel_size = self.size()
        screen = QGuiApplication.screenAt(pet_geometry.center())
        available = screen.availableGeometry() if screen is not None else QRect(0, 0, 1440, 900)

        gap = 12
        right_x = pet_geometry.right() + gap
        left_x = pet_geometry.left() - panel_size.width() - gap
        if right_x + panel_size.width() <= available.right():
            x = right_x
        elif left_x >= available.left():
            x = left_x
        else:
            x = pet_geometry.left()

        y = pet_geometry.center().y() - panel_size.height() // 2
        x = min(max(x, available.left()), available.right() - panel_size.width())
        y = min(max(y, available.top()), available.bottom() - panel_size.height())
        self.move(x, y)

    def set_system_state(
        self,
        *,
        always_on_top: bool,
        click_through: bool,
        auto_move: bool,
        dev_mode: bool,
        status_decay_enabled: bool,
        auto_refill_enabled: bool,
        auto_purchase_enabled: bool,
    ) -> None:
        self._set_checked(self._topmost_check, always_on_top)
        self._set_checked(self._click_through_check, click_through)
        self._set_checked(self._auto_move_check, auto_move)
        self._set_checked(self._dev_mode_check, dev_mode)
        self._set_checked(self._status_decay_check, status_decay_enabled)
        self._set_checked(self._auto_refill_check, auto_refill_enabled)
        self._set_checked(self._auto_purchase_check, auto_purchase_enabled)
        self._auto_purchase_check.setEnabled(bool(auto_refill_enabled))

    def set_pet_state(
        self,
        state: PetState,
        *,
        current_visual_state: str | None = None,
    ) -> None:
        self._current_pet_state = state
        suggested_visual_state = state.suggested_visual_state()
        current_visual_state = current_visual_state or suggested_visual_state
        for key, value in {
            "饱腹": state.satiety,
            "心情": state.mood,
            "体力": state.energy,
            "健康": state.health,
            "清洁": state.cleanliness,
        }.items():
            self._metric_bars[key].setValue(value)
        self.set_info(
            affection=str(state.affection),
            coins=str(state.money),
            exp=f"{state.exp}/{required_exp_for_level(state.level)}",
            exp_to_next=f"{exp_to_next_level(state)} exp",
            level=f"Lv.{state.level}",
            activity=state.current_activity,
            visual_state=_visual_state_text(suggested_visual_state),
            current_visual_state=_visual_state_text(current_visual_state),
        )
        self._set_inventory_summary(state.money, inventory_count(self._inventory))

    def set_item_catalog(self, _items: tuple[object, ...]) -> None:
        return

    def set_inventory(self, inventory: dict[str, int], *, money: int) -> None:
        normalized: dict[str, int] = {}
        for item_id, count in inventory.items():
            try:
                value = max(0, int(count))
            except (TypeError, ValueError):
                continue
            if value > 0:
                normalized[str(item_id)] = value
        self._inventory = normalized
        self._set_inventory_summary(money, inventory_count(self._inventory))

    def set_activities(self, _activities: tuple[object, ...]) -> None:
        return

    def set_plugin_toggles(
        self,
        toggles: tuple[tuple[str, str, bool], ...],
    ) -> None:
        layout = self._plugin_toggle_layout
        if layout is None:
            return
        active_ids: set[str] = set()
        for plugin_id, title, enabled in toggles:
            plugin_id = str(plugin_id).strip()
            if not plugin_id:
                continue
            active_ids.add(plugin_id)
            check = self._plugin_toggle_checks.get(plugin_id)
            if check is None:
                check = QCheckBox(str(title).strip() or plugin_id)
                check.toggled.connect(
                    lambda checked=False, plugin_id=plugin_id: self.plugin_toggled.emit(
                        plugin_id,
                        bool(checked),
                    )
                )
                self._plugin_toggle_checks[plugin_id] = check
                layout.addWidget(check)
            else:
                check.setText(str(title).strip() or plugin_id)
            check.show()
            check.setEnabled(True)
            self._set_checked(check, bool(enabled))

        for plugin_id, check in self._plugin_toggle_checks.items():
            if plugin_id not in active_ids:
                check.hide()
                check.setEnabled(False)
        self._refresh_active_page_height()

    def set_tomato_clock_state(
        self,
        *,
        available: bool,
        running: bool,
        paused: bool = False,
    ) -> None:
        check = self._tomato_clock_check
        if check is None:
            return
        check.setEnabled(bool(available))
        if not available:
            check.setText("番茄钟")
            check.setToolTip("番茄钟插件未加载。")
            self._set_checked(check, False)
            return
        check.setText("番茄钟（暂停中）" if paused and running else "番茄钟")
        check.setToolTip("勾选开始番茄钟，取消勾选停止番茄钟。")
        self._set_checked(check, bool(running))

    def set_activity_snapshot(
        self,
        snapshot: ActivitySnapshot,
        *,
        can_start: bool,
    ) -> None:
        self._current_activity_snapshot = snapshot
        self._activity_can_start = bool(can_start)
        if self._activity_summary_label is not None:
            self._activity_summary_label.setText(_activity_summary_text(snapshot))
        if self._activity_progress_bar is not None:
            self._activity_progress_bar.setValue(snapshot.progress_percent)
            self._activity_progress_bar.setEnabled(snapshot.is_active)
        if self._activity_cancel_button is not None:
            self._activity_cancel_button.setEnabled(snapshot.is_active)
        if self._activity_window_button is not None:
            self._activity_window_button.setText(
                "活动详情" if snapshot.is_active else "打开互动"
            )
        self._refresh_active_page_height()

    def set_activity_notice(self, message: str) -> None:
        if self._activity_notice_label is None:
            return
        message = str(message).strip()
        self._activity_notice_label.setText(message)
        self._activity_notice_label.setVisible(bool(message))
        self._refresh_active_page_height()

    def set_care_notice(self, message: str) -> None:
        if self._care_notice_label is None:
            return
        message = str(message).strip()
        self._care_notice_label.setText(message)
        self._care_notice_label.setVisible(bool(message))
        self._refresh_active_page_height()

    def set_level_notice(self, message: str) -> None:
        if self._level_notice_label is None:
            return
        message = str(message).strip()
        self._level_notice_label.setText(message)
        self._level_notice_label.setVisible(bool(message))
        self._refresh_active_page_height()

    def set_info(
        self,
        *,
        affection: str,
        coins: str,
        exp: str,
        exp_to_next: str,
        level: str,
        activity: str,
        visual_state: str,
        current_visual_state: str,
    ) -> None:
        values = {
            "亲密度": affection,
            "金币": coins,
            "经验": exp,
            "距下一级": exp_to_next,
            "等级": level,
            "当前活动": activity,
            "建议表现状态": visual_state,
            "当前表现状态": current_visual_state,
        }
        for key, value in values.items():
            label = self._info_labels.get(key)
            if label is not None:
                label.setText(str(value))

    def _set_inventory_summary(self, money: int, total_items: int) -> None:
        if self._shop_money_label is not None:
            self._shop_money_label.setText(f"{max(0, int(money))}")
        if self._inventory_count_label is not None:
            self._inventory_count_label.setText(f"{max(0, int(total_items))}")

    def _submit_message(self) -> None:
        text = self._chat_input.text().strip()
        if not text:
            return
        self.message_submitted.emit(text)
        self._chat_input.clear()

    def _build_shell(self) -> QWidget:
        shell = QFrame()
        shell.setObjectName("statusPanelShell")
        self._shell = shell

        layout = QVBoxLayout(shell)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self._build_chat_row())
        layout.addWidget(self._build_detail_frame())
        layout.addWidget(self._build_nav_bar())

        self._apply_panel_style()
        return shell

    def _build_chat_row(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("chatRow")
        self._chat_row = frame

        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("和桌宠说")
        self._chat_input.returnPressed.connect(self._submit_message)

        send_button = QPushButton("发送")
        send_button.setObjectName("sendButton")
        send_button.clicked.connect(self._submit_message)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        row.addWidget(self._chat_input, 1)
        row.addWidget(send_button, 0)
        frame.setLayout(row)
        return frame

    def _build_detail_frame(self) -> QFrame:
        self._detail_frame = QFrame()
        self._detail_frame.setObjectName("detailPanel")

        layout = QVBoxLayout(self._detail_frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(0)

        self._page_stack = QStackedWidget()
        self._page_stack.setObjectName("pageStack")
        self._page_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        for key, page in (
            ("feed", self._build_feed_page()),
            ("stats", self._build_stats_page()),
            ("activity", self._build_activity_page()),
            ("custom", self._build_custom_page()),
            ("system", self._build_system_page()),
        ):
            self._pages[key] = page
            self._page_stack.addWidget(page)
        layout.addWidget(self._page_stack)
        self._detail_frame.hide()
        return self._detail_frame

    def _build_nav_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("functionBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)

        for key, title in (
            ("feed", "投喂"),
            ("stats", "面板"),
            ("activity", "互动"),
            ("custom", "自定"),
            ("system", "系统"),
        ):
            button = QPushButton(title)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setFixedHeight(28)
            button.installEventFilter(self)
            button.clicked.connect(lambda checked=False, key=key: self._show_section(key))
            self._nav_buttons[key] = button
            self._nav_button_sections[button] = key
            row.addWidget(button, 1)
        return bar

    def _toggle_section(self, key: str) -> None:
        self._show_section(key)

    def _show_section(self, key: str) -> None:
        self._leave_close_timer.stop()
        bottom = self.geometry().bottom()
        if key not in self._pages:
            return

        self._active_section = key
        for section, button in self._nav_buttons.items():
            button.setChecked(section == key)

        if self._chat_row is not None:
            self._chat_row.hide()
        assert self._page_stack is not None
        page = self._pages[key]
        self._page_stack.setCurrentWidget(page)
        self._page_stack.setFixedHeight(page.sizeHint().height())
        assert self._detail_frame is not None
        self._detail_frame.show()
        self._resize_to_hint(anchor_bottom=True, bottom=bottom)
        self.layout_changed.emit()

    def _build_feed_page(self) -> QWidget:
        page = QWidget()
        layout = self._page_layout(page)
        self._care_notice_label = QLabel("")
        self._care_notice_label.setObjectName("noticeLabel")
        self._care_notice_label.setWordWrap(True)
        self._care_notice_label.hide()
        layout.addWidget(self._care_notice_label)
        layout.addLayout(self._inventory_summary_row())
        layout.addLayout(self._shop_entry_row())
        return page

    def _inventory_summary_row(self) -> QHBoxLayout:
        money_title = QLabel("金币")
        self._shop_money_label = QLabel("0")
        self._shop_money_label.setObjectName("valueLabel")
        item_title = QLabel("背包")
        self._inventory_count_label = QLabel("0")
        self._inventory_count_label.setObjectName("valueLabel")

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(money_title)
        row.addWidget(self._shop_money_label)
        row.addStretch(1)
        row.addWidget(item_title)
        row.addWidget(self._inventory_count_label)
        return row

    def _shop_entry_row(self) -> QHBoxLayout:
        shop_button = QPushButton("打开商店")
        shop_button.setMinimumHeight(32)
        shop_button.clicked.connect(self.shop_requested.emit)

        inventory_button = QPushButton("打开背包")
        inventory_button.setMinimumHeight(32)
        inventory_button.clicked.connect(self.inventory_requested.emit)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        row.addWidget(shop_button, 1)
        row.addWidget(inventory_button, 1)
        return row

    def _build_stats_page(self) -> QWidget:
        page = QWidget()
        layout = self._page_layout(page)

        self._level_notice_label = QLabel("")
        self._level_notice_label.setObjectName("noticeLabel")
        self._level_notice_label.setWordWrap(True)
        self._level_notice_label.hide()
        layout.addWidget(self._level_notice_label)

        for title, value in (
            ("饱腹", 0),
            ("心情", 0),
            ("体力", 0),
            ("健康", 0),
            ("清洁", 0),
        ):
            layout.addLayout(self._metric_row(title, value))
        layout.addSpacing(3)

        for title in (
            "金币",
            "经验",
            "等级",
            "亲密度",
            "当前表现状态",
            "建议表现状态",
        ):
            layout.addLayout(self._info_row(title))
        return page

    def _build_activity_page(self) -> QWidget:
        page = QWidget()
        layout = self._page_layout(page)

        self._activity_notice_label = QLabel("")
        self._activity_notice_label.setObjectName("noticeLabel")
        self._activity_notice_label.setWordWrap(True)
        self._activity_notice_label.hide()
        layout.addWidget(self._activity_notice_label)

        status = QFrame()
        status.setObjectName("activityStatus")
        status_layout = QVBoxLayout(status)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(7)

        self._activity_summary_label = QLabel(_activity_summary_text(ActivitySnapshot.idle()))
        self._activity_summary_label.setObjectName("activitySummaryLabel")
        self._activity_summary_label.setWordWrap(True)
        status_layout.addWidget(self._activity_summary_label)

        self._activity_progress_bar = QProgressBar()
        self._activity_progress_bar.setRange(0, 100)
        self._activity_progress_bar.setValue(0)
        self._activity_progress_bar.setTextVisible(False)
        self._activity_progress_bar.setEnabled(False)
        status_layout.addWidget(self._activity_progress_bar)

        self._activity_cancel_button = QPushButton("取消活动")
        self._activity_cancel_button.setEnabled(False)
        self._activity_cancel_button.clicked.connect(self.activity_cancel_requested.emit)
        status_layout.addWidget(self._activity_cancel_button)

        self._activity_window_button = QPushButton("打开互动")
        self._activity_window_button.setObjectName("activityWindowButton")
        self._activity_window_button.setMinimumHeight(32)
        self._activity_window_button.clicked.connect(self.activity_window_requested.emit)
        status_layout.addWidget(self._activity_window_button)

        layout.addWidget(status)
        return page

    def _build_custom_page(self) -> QWidget:
        page = QWidget()
        layout = self._page_layout(page)
        for title, callback in (
            ("放大", self.zoom_in_requested.emit),
            ("缩小", self.zoom_out_requested.emit),
            ("恢复默认大小", self.restore_size_requested.emit),
        ):
            button = QPushButton(title)
            button.setMinimumHeight(32)
            button.clicked.connect(callback)
            layout.addWidget(button)

        layout.addSpacing(3)
        plugin_title = QLabel("插件")
        plugin_title.setObjectName("sectionTitleLabel")
        layout.addWidget(plugin_title)

        self._plugin_toggle_layout = QVBoxLayout()
        self._plugin_toggle_layout.setContentsMargins(0, 0, 0, 0)
        self._plugin_toggle_layout.setSpacing(6)
        layout.addLayout(self._plugin_toggle_layout)

        self._tomato_clock_check = QCheckBox("番茄钟")
        self._tomato_clock_check.setEnabled(False)
        self._tomato_clock_check.toggled.connect(
            lambda checked=False: self.tomato_clock_toggled.emit(bool(checked))
        )
        layout.addWidget(self._tomato_clock_check)
        return page

    def _build_system_page(self) -> QWidget:
        page = QWidget()
        layout = self._page_layout(page)
        for check in (
            self._topmost_check,
            self._click_through_check,
            self._auto_move_check,
            self._dev_mode_check,
            self._status_decay_check,
            self._auto_refill_check,
            self._auto_purchase_check,
        ):
            layout.addWidget(check)

        quit_button = QPushButton("退出")
        quit_button.clicked.connect(self.quit_requested)
        layout.addWidget(quit_button)
        return page

    def _page_layout(self, page: QWidget) -> QVBoxLayout:
        page.setObjectName("statusPanelPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        return layout

    def _metric_row(self, title: str, value: int) -> QHBoxLayout:
        label = QLabel(title)
        label.setFixedWidth(44)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(value)
        bar.setEnabled(False)
        bar.setTextVisible(False)
        self._metric_bars[title] = bar

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(label)
        row.addWidget(bar, 1)
        return row

    def _info_row(self, title: str) -> QHBoxLayout:
        title_label = QLabel(title)
        value_label = QLabel("-")
        value_label.setObjectName("valueLabel")
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._info_labels[title] = value_label

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(title_label)
        row.addStretch(1)
        row.addWidget(value_label)
        return row

    def _refresh_active_page_height(self) -> None:
        if self._active_section is None or self._page_stack is None:
            return
        bottom = self.geometry().bottom()
        page = self._pages[self._active_section]
        self._page_stack.setFixedHeight(page.sizeHint().height())
        self._resize_to_hint(anchor_bottom=True, bottom=bottom)
        self.layout_changed.emit()

    def _resize_to_hint(
        self,
        *,
        anchor_bottom: bool = False,
        bottom: int | None = None,
    ) -> None:
        for widget in (self._page_stack, self._detail_frame, self._shell):
            if widget is not None:
                widget.updateGeometry()
        layout = self.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        target_height = self.sizeHint().height()
        self.setFixedHeight(target_height)
        if anchor_bottom and bottom is not None and self.isVisible():
            self.move(self.x(), bottom - self.height() + 1)

    def _set_checked(self, check: QCheckBox, checked: bool) -> None:
        was_blocked = check.blockSignals(True)
        check.setChecked(bool(checked))
        check.blockSignals(was_blocked)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Enter:
            section = self._nav_button_sections.get(watched)
            if section is not None:
                self._show_section(section)
        return super().eventFilter(watched, event)

    def enterEvent(self, event) -> None:
        self._leave_close_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._leave_close_timer.start()
        super().leaveEvent(event)

    def _close_after_leave_delay(self) -> None:
        if self.underMouse():
            return
        self.hide()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.PaletteChange
            and not getattr(self, "_applying_panel_style", False)
        ):
            self._apply_panel_style()

    def _apply_panel_style(self) -> None:
        if self._applying_panel_style:
            return
        self._applying_panel_style = True
        palette = self.palette()
        window = palette.window().color()
        base = palette.base().color()
        text = palette.text().color()
        button = palette.button().color()
        highlight = palette.highlight().color()
        mid = palette.mid().color()
        disabled = _blend(text, window, 0.54)

        try:
            self.setStyleSheet(
                _PANEL_STYLE_TEMPLATE.format(
                    shell_bg=_rgba(window, 0.96),
                    shell_border=_rgba(mid, 0.32),
                    detail_bg=_rgba(base, 0.84),
                    detail_border=_rgba(mid, 0.26),
                    bar_bg=_rgba(button, 0.84),
                    field_bg=_rgba(base, 0.92),
                    button_bg=_rgba(button, 0.88),
                    button_hover=_rgba(_blend(button, highlight, 0.12), 0.96),
                    button_pressed=_rgba(_blend(button, highlight, 0.22), 0.96),
                    nav_checked=_rgba(base, 0.96),
                    text=_hex(text),
                    text_soft=_rgba(text, 0.74),
                    text_disabled=_hex(disabled),
                    border=_rgba(mid, 0.28),
                    accent=_hex(highlight),
                    progress_bg=_rgba(mid, 0.42),
                )
            )
        finally:
            self._applying_panel_style = False


def _hex(color: QColor) -> str:
    return color.name()


def _rgba(color: QColor, alpha: float) -> str:
    alpha_i = max(0, min(255, round(alpha * 255)))
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha_i})"


def _blend(a: QColor, b: QColor, ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, ratio))
    return QColor(
        round(a.red() * (1.0 - ratio) + b.red() * ratio),
        round(a.green() * (1.0 - ratio) + b.green() * ratio),
        round(a.blue() * (1.0 - ratio) + b.blue() * ratio),
    )


def _visual_state_text(value: str) -> str:
    labels = {
        "happy": "开心 (happy)",
        "normal": "正常 (normal)",
        "poor_condition": "状态欠佳 (poor_condition)",
        "ill": "生病 (ill)",
    }
    return labels.get(value, value)


def _format_seconds(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    if minutes <= 0:
        return f"{sec}秒"
    return f"{minutes}分{sec:02d}秒"


def _activity_summary_text(snapshot: ActivitySnapshot) -> str:
    if snapshot.is_active:
        return (
            f"{snapshot.name} · {snapshot.category} · "
            f"剩余 {_format_seconds(snapshot.remaining_seconds)} / "
            f"{snapshot.progress_percent}%"
        )
    return "待机 · 进度 0%"


_PANEL_STYLE_TEMPLATE = """
QFrame#statusPanelShell {{
    background: {shell_bg};
    border: 1px solid {shell_border};
    border-radius: 13px;
}}
QFrame#detailPanel {{
    background: {detail_bg};
    border: 1px solid {detail_border};
    border-radius: 10px;
}}
QFrame#functionBar {{
    background: {bar_bg};
    border: 1px solid {detail_border};
    border-radius: 9px;
}}
QFrame#activityStatus {{
    background: transparent;
    border: 0;
}}
QStackedWidget#pageStack,
QStackedWidget#pageStack > QWidget,
QWidget#statusPanelPage {{
    background: transparent;
}}
QLineEdit {{
    background: {field_bg};
    border: 1px solid {border};
    border-radius: 9px;
    padding: 7px 9px;
    color: {text};
    selection-background-color: {accent};
}}
QPushButton {{
    background: {button_bg};
    border: 1px solid {border};
    border-radius: 9px;
    padding: 6px 9px;
    color: {text};
}}
QPushButton#sendButton {{
    min-width: 50px;
}}
QPushButton#navButton {{
    background: transparent;
    border: 0;
    border-radius: 7px;
    padding: 3px 0;
    color: {text_soft};
    font-size: 12px;
}}
QPushButton#navButton:checked {{
    color: {text};
    background: {nav_checked};
}}
QPushButton:hover {{
    background: {button_hover};
}}
QPushButton:pressed {{
    background: {button_pressed};
}}
QLabel {{
    color: {text_soft};
}}
QLabel#valueLabel {{
    color: {text};
    font-weight: 600;
}}
QLabel#noticeLabel {{
    color: {text};
    font-weight: 600;
}}
QLabel#activitySummaryLabel {{
    color: {text};
    font-weight: 650;
}}
QProgressBar {{
    height: 7px;
    border: 0;
    border-radius: 4px;
    background: {progress_bg};
}}
QProgressBar::chunk {{
    border-radius: 4px;
    background: {accent};
}}
QCheckBox {{
    color: {text};
    spacing: 7px;
}}
QCheckBox:disabled {{
    color: {text_disabled};
}}
"""
