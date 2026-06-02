"""拆出独立的互动窗口"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.performance import measure_ui
from core.raising.activity import ActivityDefinition, ActivitySnapshot, missing_requirements
from core.raising.pet_state import PetState
from ui.shared.window_geometry import RememberedWindowGeometry


class ActivityWindow(QWidget):
    activity_requested = pyqtSignal(str)
    activity_cancel_requested = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        geometry_settings_path: Path | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("互动 / 活动")
        self.setMinimumSize(440, 430)
        self._remembered_geometry = RememberedWindowGeometry(
            self,
            "activity",
            settings_path=geometry_settings_path,
        )
        self._remembered_geometry.restore()

        self._activities: tuple[ActivityDefinition, ...] = ()
        self._activities_by_category: dict[str, tuple[ActivityDefinition, ...]] = {}
        self._current_activity_snapshot = ActivitySnapshot.idle()
        self._current_pet_state = PetState()
        self._activity_can_start = True
        self._activity_sync_dirty = False
        self._activity_catalog_dirty = False
        self._activity_detail_labels: dict[str, QLabel] = {}
        self._applying_style = False

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        root.addWidget(self._build_status_panel())

        self._notice_label = QLabel("")
        self._notice_label.setObjectName("noticeLabel")
        self._notice_label.setWordWrap(True)
        self._notice_label.hide()
        root.addWidget(self._notice_label)

        root.addWidget(self._build_selector_panel(), 1)

        self._apply_window_style()
        self._refresh_activity_category_combo()
        self._apply_activity_snapshot()

    def show_window(self) -> None:
        with measure_ui("activity_window.open"):
            if not self.isVisible():
                self._remembered_geometry.restore()
            self._flush_pending_activity_sync("open", force=True)
            self.show()
            self.raise_()
            self.activateWindow()
            self._remembered_geometry.enable_soon()

    def set_activities(self, activities: tuple[ActivityDefinition, ...]) -> None:
        with measure_ui("activity_window.set_activities"):
            self._activities = tuple(activities)
            self._activities_by_category = _group_activities_by_category(self._activities)
            self._activity_catalog_dirty = True
            self.mark_dirty()
            if self.isVisible():
                self._flush_pending_activity_sync("activities")

    def set_pet_state(self, state: PetState) -> None:
        with measure_ui("activity_window.set_pet_state"):
            self._current_pet_state = state
            self.mark_dirty()
            if self.isVisible():
                self._flush_pending_activity_sync("pet_state")

    def set_activity_snapshot(
        self,
        snapshot: ActivitySnapshot,
        *,
        can_start: bool,
    ) -> None:
        with measure_ui("activity_window.set_activity_snapshot"):
            self._current_activity_snapshot = snapshot
            self._activity_can_start = bool(can_start)
            self.mark_dirty()
            if self.isVisible():
                self._flush_pending_activity_sync("snapshot")

    def mark_dirty(self) -> None:
        self._activity_sync_dirty = True

    def _flush_pending_activity_sync(
        self,
        reason: str,
        *,
        force: bool = False,
    ) -> None:
        if (
            not force
            and not self._activity_sync_dirty
            and not self._activity_catalog_dirty
        ):
            return
        with measure_ui("activity_window.refresh", detail=reason):
            if force or self._activity_catalog_dirty:
                self._refresh_activity_category_combo()
            self._apply_activity_snapshot()
            self._refresh_activity_detail()
            self._activity_catalog_dirty = False
            self._activity_sync_dirty = False

    def _apply_activity_snapshot(self) -> None:
        snapshot = self._current_activity_snapshot
        self._activity_summary_label.setText(_activity_summary_text(snapshot))
        self._activity_progress_bar.setValue(snapshot.progress_percent)
        self._activity_progress_bar.setEnabled(snapshot.is_active)
        self._activity_cancel_button.setEnabled(snapshot.is_active)

    def set_activity_notice(self, message: str) -> None:
        message = str(message).strip()
        self._notice_label.setText(message)
        self._notice_label.setVisible(bool(message))

    def _build_status_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("activityStatusPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._activity_summary_label = QLabel(_activity_summary_text(ActivitySnapshot.idle()))
        self._activity_summary_label.setObjectName("activitySummaryLabel")
        self._activity_summary_label.setWordWrap(True)
        layout.addWidget(self._activity_summary_label)

        self._activity_progress_bar = QProgressBar()
        self._activity_progress_bar.setRange(0, 100)
        self._activity_progress_bar.setValue(0)
        self._activity_progress_bar.setTextVisible(False)
        self._activity_progress_bar.setEnabled(False)
        layout.addWidget(self._activity_progress_bar)

        self._activity_cancel_button = QPushButton("取消活动")
        self._activity_cancel_button.setEnabled(False)
        self._activity_cancel_button.clicked.connect(self.activity_cancel_requested.emit)
        layout.addWidget(self._activity_cancel_button)
        return panel

    def _build_selector_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("activitySelectorPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(9)

        self._activity_category_combo = QComboBox()
        self._activity_category_combo.setObjectName("activityCategoryCombo")
        self._activity_category_combo.currentIndexChanged.connect(
            self._on_activity_category_changed
        )
        layout.addLayout(self._combo_row("活动类型", self._activity_category_combo))

        self._activity_select_combo = QComboBox()
        self._activity_select_combo.setObjectName("activitySelectCombo")
        self._activity_select_combo.currentIndexChanged.connect(
            self._on_activity_selection_changed
        )
        layout.addLayout(self._combo_row("具体活动", self._activity_select_combo))

        for title in ("时长", "要求", "变化", "说明"):
            layout.addLayout(self._detail_row(title))

        layout.addStretch(1)
        self._activity_start_button = QPushButton("开始活动")
        self._activity_start_button.setObjectName("activityStartButton")
        self._activity_start_button.setMinimumHeight(34)
        self._activity_start_button.clicked.connect(self._request_selected_activity)
        layout.addWidget(self._activity_start_button)
        return panel

    def _combo_row(self, title: str, combo: QComboBox) -> QHBoxLayout:
        title_label = QLabel(title)
        title_label.setFixedWidth(64)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(title_label)
        row.addWidget(combo, 1)
        return row

    def _detail_row(self, title: str) -> QHBoxLayout:
        title_label = QLabel(title)
        title_label.setFixedWidth(64)
        value_label = QLabel("-")
        value_label.setObjectName("activityDetailValue")
        value_label.setWordWrap(True)
        value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._activity_detail_labels[title] = value_label

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(title_label)
        row.addWidget(value_label, 1)
        return row

    def _refresh_activity_category_combo(self) -> None:
        combo = self._activity_category_combo
        previous = combo.currentData()
        categories = tuple(self._activities_by_category)
        blocked = combo.blockSignals(True)
        combo.clear()
        for category in categories:
            combo.addItem(category, category)
        if previous in categories:
            combo.setCurrentIndex(categories.index(previous))
        elif categories:
            combo.setCurrentIndex(0)
        combo.setEnabled(bool(categories))
        combo.blockSignals(blocked)
        self._refresh_activity_select_combo()

    def _refresh_activity_select_combo(self) -> None:
        combo = self._activity_select_combo
        previous = combo.currentData()
        category = self._selected_activity_category()
        activities = self._activities_by_category.get(category, ())
        activity_ids = tuple(activity.id for activity in activities)
        blocked = combo.blockSignals(True)
        combo.clear()
        for activity in activities:
            combo.addItem(activity.name, activity.id)
        if previous in activity_ids:
            combo.setCurrentIndex(activity_ids.index(previous))
        elif activities:
            combo.setCurrentIndex(0)
        combo.setEnabled(bool(activities))
        combo.blockSignals(blocked)
        self._refresh_activity_detail()

    def _selected_activity_category(self) -> str:
        value = self._activity_category_combo.currentData()
        return str(value or "")

    def _selected_activity(self) -> ActivityDefinition | None:
        activity_id = str(self._activity_select_combo.currentData() or "")
        for activity in self._activities:
            if activity.id == activity_id:
                return activity
        return None

    def _on_activity_category_changed(self, _index: int) -> None:
        self._refresh_activity_select_combo()

    def _on_activity_selection_changed(self, _index: int) -> None:
        self._refresh_activity_detail()

    def _request_selected_activity(self) -> None:
        activity = self._selected_activity()
        if activity is None:
            self.set_activity_notice("请选择一个活动。")
            return
        if self._current_activity_snapshot.is_active:
            self.set_activity_notice("活动进行中，不能同时开始另一个活动。")
            return
        missing = missing_requirements(self._current_pet_state, activity)
        if missing:
            self.set_activity_notice(_format_missing_requirements(missing))
            return
        if not self._activity_can_start:
            self.set_activity_notice("当前动作占用中，稍后再开始活动。")
            return
        self.activity_requested.emit(activity.id)

    def _refresh_activity_detail(self) -> None:
        activity = self._selected_activity()
        enabled = False
        tooltip = ""
        if activity is None:
            values = {
                "时长": "-",
                "要求": "-",
                "变化": "-",
                "说明": "-",
            }
            tooltip = "暂无可选活动"
            button_text = "暂无活动"
        else:
            availability, enabled, tooltip = self._activity_availability(activity)
            values = {
                "时长": _format_seconds(activity.duration_seconds),
                "要求": _format_requirements(activity.requirements),
                "变化": _format_activity_changes(activity),
                "说明": activity.description or "无",
            }
            button_text = "开始活动" if enabled else _short_unavailable_text(availability)
        for title, value in values.items():
            self._activity_detail_labels[title].setText(value)
        self._activity_start_button.setEnabled(enabled)
        self._activity_start_button.setText(button_text)
        self._activity_start_button.setToolTip(tooltip)

    def _activity_availability(
        self,
        activity: ActivityDefinition,
    ) -> tuple[str, bool, str]:
        if self._current_activity_snapshot.is_active:
            message = "活动进行中，完成或取消后可开始新活动"
            return message, False, message
        if not self._activity_can_start:
            message = "当前动作占用中，稍后再开始"
            return message, False, message
        missing = missing_requirements(self._current_pet_state, activity)
        if missing:
            message = _format_missing_requirements(missing)
            return message, False, message
        return "可开始", True, f"开始：{activity.name}"

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.PaletteChange
            and not getattr(self, "_applying_style", False)
        ):
            self._apply_window_style()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._remembered_geometry.schedule_save()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._remembered_geometry.schedule_save()

    def closeEvent(self, event) -> None:
        self._remembered_geometry.save_now()
        self._remembered_geometry.disable()
        super().closeEvent(event)

    def _apply_window_style(self) -> None:
        if self._applying_style:
            return
        self._applying_style = True
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
                _WINDOW_STYLE_TEMPLATE.format(
                    window_bg=_hex(window),
                    panel_bg=_rgba(base, 0.86),
                    border=_rgba(mid, 0.34),
                    text=_hex(text),
                    text_soft=_rgba(text, 0.74),
                    text_disabled=_hex(disabled),
                    field_bg=_rgba(base, 0.94),
                    button_bg=_rgba(button, 0.88),
                    button_hover=_rgba(_blend(button, highlight, 0.12), 0.96),
                    button_pressed=_rgba(_blend(button, highlight, 0.22), 0.96),
                    accent=_hex(highlight),
                    progress_bg=_rgba(mid, 0.42),
                )
            )
        finally:
            self._applying_style = False


def _group_activities_by_category(
    activities: tuple[ActivityDefinition, ...],
) -> dict[str, tuple[ActivityDefinition, ...]]:
    grouped: dict[str, list[ActivityDefinition]] = {}
    for activity in activities:
        category = str(activity.category).strip() or "未分类"
        grouped.setdefault(category, []).append(activity)
    return {category: tuple(items) for category, items in grouped.items()}


def _activity_summary_text(snapshot: ActivitySnapshot) -> str:
    if snapshot.is_active:
        return (
            f"{snapshot.name} · {snapshot.category}\n"
            f"剩余 {_format_seconds(snapshot.remaining_seconds)} / "
            f"已用 {_format_seconds(snapshot.elapsed_seconds)} · "
            f"{snapshot.progress_percent}%"
        )
    return "待机\n活动时间：待机 · 进度 0%"


def _format_seconds(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    if minutes <= 0:
        return f"{sec}秒"
    return f"{minutes}分{sec:02d}秒"


def _format_requirements(requirements: dict[str, int]) -> str:
    if not requirements:
        return "无"
    return "、".join(
        f"{_field_label(field)} >= {amount}"
        for field, amount in requirements.items()
        if amount
    )


def _format_amounts(amounts: dict[str, int], *, sign: str) -> str:
    if not amounts:
        return "无"
    return "、".join(
        f"{_field_label(field)} {sign}{amount}"
        for field, amount in amounts.items()
        if amount
    )


def _format_activity_changes(activity: ActivityDefinition) -> str:
    costs = _format_amounts(activity.costs, sign="-")
    rewards = _format_amounts(activity.rewards, sign="+")
    if costs == "无" and rewards == "无":
        return "无"
    if costs == "无":
        return f"奖励 {rewards}"
    if rewards == "无":
        return f"消耗 {costs}"
    return f"消耗 {costs}；奖励 {rewards}"


def _format_missing_requirements(missing: dict[str, tuple[int, int]]) -> str:
    parts = [
        f"{_field_label(field)} {current}/{required}"
        for field, (current, required) in missing.items()
    ]
    return "状态不足：" + "，".join(parts)


def _short_unavailable_text(message: str) -> str:
    if "状态不足" in message:
        return "状态不足"
    if "活动进行中" in message:
        return "活动进行中"
    if "占用" in message:
        return "动作占用中"
    return "不可开始"


def _field_label(field: str) -> str:
    labels = {
        "money": "金币",
        "satiety": "饱腹",
        "mood": "心情",
        "energy": "体力",
        "health": "健康",
        "cleanliness": "清洁",
        "exp": "经验",
        "level": "等级",
        "affection": "亲密度",
    }
    return labels.get(field, field)


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


_WINDOW_STYLE_TEMPLATE = """
QWidget {{
    background: {window_bg};
    color: {text};
}}
QFrame#activityStatusPanel,
QFrame#activitySelectorPanel {{
    background: {panel_bg};
    border: 1px solid {border};
    border-radius: 8px;
}}
QLabel {{
    color: {text_soft};
}}
QLabel#noticeLabel,
QLabel#activitySummaryLabel,
QLabel#activityDetailValue {{
    color: {text};
    font-weight: 600;
}}
QComboBox {{
    background: {field_bg};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 6px 8px;
    color: {text};
}}
QComboBox::drop-down {{
    border: 0;
    width: 22px;
}}
QComboBox:disabled {{
    color: {text_disabled};
}}
QPushButton {{
    background: {button_bg};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 7px 10px;
    color: {text};
}}
QPushButton:hover {{
    background: {button_hover};
}}
QPushButton:pressed {{
    background: {button_pressed};
}}
QPushButton:disabled {{
    color: {text_disabled};
}}
QProgressBar {{
    height: 8px;
    border: 0;
    border-radius: 4px;
    background: {progress_bg};
}}
QProgressBar::chunk {{
    border-radius: 4px;
    background: {accent};
}}
"""
