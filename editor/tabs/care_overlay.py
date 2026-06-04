"""编辑 config/care_overlay.json"""
from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.app_paths import config_path
from core.loader import _load_action_specs
from core.playback.catalog import PET_STATES
from core.playback.flipbook import FlipbookPlayer
from core.playback.overlay_clip import PixmapOverlayConfig, clip_with_pixmap_overlay
from core.raising.care_overlay import CARE_OVERLAY_CONFIG
from core.raising.items import (
    ItemCategory,
    ItemDefinition,
    load_item_catalog,
    resolve_item_icon_path,
)
from editor.tabs.assets import _build_catalog

CONFIG_PATH = config_path(CARE_OVERLAY_CONFIG)
BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / ".vpet_editor_backups"
OVERLAY_LAYERS = (
    ("前景后面", "behind_front"),
    ("最上层", "top"),
)
DEFAULT_OVERLAY_CONFIG = {
    "item_icon_size_ratio": 0.12,
    "item_icon_center_x_ratio": 0.5,
    "item_icon_center_y_ratio": 0.45,
    "item_icon_visible_start_ratio": 0.25,
    "item_icon_visible_end_ratio": 0.85,
    "item_icon_opacity": 1.0,
    "item_icon_layer": "behind_front",
    "item_icon_background_enabled": False,
}
ACTION_ITEM_CATEGORIES: dict[str, ItemCategory] = {
    "eat": "food",
    "drink": "drink",
    "gift": "gift",
}


def _backup() -> None:
    if not CONFIG_PATH.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(CONFIG_PATH, BACKUP_DIR / f"care_overlay-{ts}.json")


class CareOverlayTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings: dict[str, object] = {}
        self._items: tuple[ItemDefinition, ...] = ()
        self._catalog = None
        self._loading = False
        self._preview_pixmap: QPixmap | None = None
        self._player = FlipbookPlayer(self)
        self._player.frame_changed.connect(self._on_frame)
        self._player.finished.connect(self._on_player_finished)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._build_editor_panel())
        splitter.addWidget(self._build_preview_panel())
        splitter.setSizes([430, 500])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._load()

    def _build_editor_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        target_group = QGroupBox("叠层目标", panel)
        target_form = QFormLayout(target_group)
        self._enabled = QCheckBox("启用照顾物品叠层", self)
        self._action = QComboBox(self)
        self._state = QComboBox(self)
        self._state.addItems(PET_STATES)
        target_form.addRow(self._enabled)
        target_form.addRow("动作", self._action)
        target_form.addRow("状态", self._state)
        layout.addWidget(target_group)

        position_group = QGroupBox("位置和显示", panel)
        position_form = QFormLayout(position_group)
        self._size = _ratio_spin(minimum=0.01, maximum=1.0, step=0.01)
        self._center_x = _ratio_spin(minimum=-1.0, maximum=2.0, step=0.01)
        self._center_y = _ratio_spin(minimum=-1.0, maximum=2.0, step=0.01)
        self._visible_start = _ratio_spin(minimum=0.0, maximum=1.0, step=0.01)
        self._visible_end = _ratio_spin(minimum=0.0, maximum=1.0, step=0.01)
        self._opacity = _ratio_spin(minimum=0.0, maximum=1.0, step=0.05)
        self._layer = QComboBox(self)
        for label, value in OVERLAY_LAYERS:
            self._layer.addItem(label, value)
        self._background = QCheckBox("图标后加浅色底", self)

        position_form.addRow("图标大小", self._size)
        position_form.addRow("中心 X", self._center_x)
        position_form.addRow("中心 Y", self._center_y)
        position_form.addRow("出现起点", self._visible_start)
        position_form.addRow("出现终点", self._visible_end)
        position_form.addRow("透明度", self._opacity)
        position_form.addRow("层级", self._layer)
        position_form.addRow(self._background)
        layout.addWidget(position_group)

        controls = QHBoxLayout()
        btn_refresh = QPushButton("刷新预览", self)
        btn_refresh.clicked.connect(lambda: self._refresh_preview(play=False))
        btn_play = QPushButton("播放一次", self)
        btn_play.clicked.connect(lambda: self._refresh_preview(play=True))
        btn_stop = QPushButton("停止", self)
        btn_stop.clicked.connect(self._stop_preview)
        controls.addWidget(btn_refresh)
        controls.addWidget(btn_play)
        controls.addWidget(btn_stop)
        layout.addLayout(controls)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch()

        self._enabled.toggled.connect(self._on_controls_changed)
        self._action.currentIndexChanged.connect(self._on_selection_changed)
        self._state.currentIndexChanged.connect(self._on_selection_changed)
        for spin in (
            self._size,
            self._center_x,
            self._center_y,
            self._visible_start,
            self._visible_end,
            self._opacity,
        ):
            spin.valueChanged.connect(self._on_controls_changed)
        self._layer.currentIndexChanged.connect(self._on_controls_changed)
        self._background.toggled.connect(self._on_controls_changed)
        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        preview_group = QGroupBox("动画预览", panel)
        preview_layout = QVBoxLayout(preview_group)
        self._preview_label = QLabel("选择动作和状态后预览", self)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(320)
        self._preview_label.setStyleSheet(
            "background: #1a1a1a; border-radius: 4px; color: #888;"
        )
        preview_layout.addWidget(self._preview_label)
        layout.addWidget(preview_group)

        item_group = QGroupBox("预览物品", panel)
        item_form = QFormLayout(item_group)
        self._item = QComboBox(self)
        self._item.currentIndexChanged.connect(self._on_item_changed)
        item_form.addRow("图标", self._item)
        layout.addWidget(item_group)

        info_group = QGroupBox("预览信息", panel)
        info_layout = QVBoxLayout(info_group)
        self._info = QLabel("", self)
        self._info.setWordWrap(True)
        info_layout.addWidget(self._info)
        layout.addWidget(info_group)
        layout.addStretch()
        return panel

    def _load(self) -> None:
        self._loading = True
        self._player.stop()
        self._preview_pixmap = None
        self._settings = _load_settings()
        self._enabled.setChecked(bool(self._settings.get("enabled", True)))
        self._load_catalog()
        self._load_items()
        self._replace_action_items()
        self._loading = False
        self._load_selected_config()
        self._choose_item_for_action()
        self._refresh_preview(play=False)

    def _load_catalog(self) -> None:
        try:
            self._catalog = _build_catalog(_load_action_specs())
        except Exception as exc:
            self._catalog = None
            self._status.setText(f"素材目录读取失败: {exc}")

    def _load_items(self) -> None:
        try:
            self._items = load_item_catalog().items()
        except Exception:
            self._items = ()

        self._item.blockSignals(True)
        self._item.clear()
        for item in self._items:
            self._item.addItem(f"{item.name} / {item.id}", item.id)
        self._item.blockSignals(False)

    def _replace_action_items(self) -> None:
        self._action.blockSignals(True)
        current = self._current_action()
        self._action.clear()

        action_ids: list[str] = []
        seen: set[str] = set()
        for action_id in _configured_actions(self._settings):
            if action_id not in seen:
                action_ids.append(action_id)
                seen.add(action_id)

        for action_id in action_ids:
            label = action_id
            if self._catalog is not None and self._catalog.has_action(action_id):
                title = self._catalog.action_title(action_id)
                if title != action_id:
                    label = f"{action_id} / {title}"
                if self._catalog.action_type(action_id) != "single":
                    label = f"{label} [非 single]"
            else:
                label = f"{label} [无素材]"
            self._action.addItem(label, action_id)

        if current:
            self._set_combo_data(self._action, current)
        self._action.blockSignals(False)

    def _on_selection_changed(self, *_args: object) -> None:
        if self._loading:
            return
        self._loading = True
        self._load_selected_config()
        self._choose_item_for_action()
        self._loading = False
        self._refresh_preview(play=False)

    def _on_controls_changed(self, *_args: object) -> None:
        if self._loading:
            return
        try:
            self._write_controls_to_settings()
            self._refresh_preview(play=False)
        except ValueError as exc:
            self._status.setText(str(exc))

    def _on_item_changed(self, *_args: object) -> None:
        if not self._loading:
            self._refresh_preview(play=False)

    def _load_selected_config(self) -> None:
        config = _state_config(
            self._settings,
            self._current_action(),
            self._current_state(),
        )
        self._set_control_values(config)

    def _set_control_values(self, values: Mapping[str, object]) -> None:
        widgets = (
            self._size,
            self._center_x,
            self._center_y,
            self._visible_start,
            self._visible_end,
            self._opacity,
            self._layer,
            self._background,
        )
        for widget in widgets:
            widget.blockSignals(True)
        self._size.setValue(_float_value(values, "item_icon_size_ratio"))
        self._center_x.setValue(_float_value(values, "item_icon_center_x_ratio"))
        self._center_y.setValue(_float_value(values, "item_icon_center_y_ratio"))
        self._visible_start.setValue(_float_value(values, "item_icon_visible_start_ratio"))
        self._visible_end.setValue(_float_value(values, "item_icon_visible_end_ratio"))
        self._opacity.setValue(_float_value(values, "item_icon_opacity"))
        self._set_combo_data(self._layer, str(values.get("item_icon_layer", "behind_front")))
        self._background.setChecked(bool(values.get("item_icon_background_enabled", False)))
        for widget in widgets:
            widget.blockSignals(False)

    def _write_controls_to_settings(self) -> None:
        action_id = self._current_action()
        state = self._current_state()
        if not action_id or not state:
            return
        self._settings["enabled"] = self._enabled.isChecked()
        actions = self._settings.setdefault("actions", {})
        if not isinstance(actions, dict):
            actions = {}
            self._settings["actions"] = actions
        action_settings = actions.setdefault(action_id, {})
        if not isinstance(action_settings, dict):
            action_settings = {}
            actions[action_id] = action_settings
        existing = action_settings.get(state, {})
        payload = dict(existing) if isinstance(existing, dict) else {}
        payload.update(self._current_payload())
        action_settings[state] = payload

    def _current_payload(self) -> dict[str, object]:
        if self._visible_end.value() <= self._visible_start.value():
            raise ValueError("出现终点必须大于出现起点。")
        layer = self._layer.currentData()
        return {
            "item_icon_size_ratio": round(self._size.value(), 2),
            "item_icon_center_x_ratio": round(self._center_x.value(), 2),
            "item_icon_center_y_ratio": round(self._center_y.value(), 2),
            "item_icon_visible_start_ratio": round(self._visible_start.value(), 2),
            "item_icon_visible_end_ratio": round(self._visible_end.value(), 2),
            "item_icon_opacity": round(self._opacity.value(), 2),
            "item_icon_layer": str(layer or "behind_front"),
            "item_icon_background_enabled": self._background.isChecked(),
        }

    def _current_config(self) -> PixmapOverlayConfig:
        payload = self._current_payload()
        return PixmapOverlayConfig(
            size_ratio=float(payload["item_icon_size_ratio"]),
            center_x_ratio=float(payload["item_icon_center_x_ratio"]),
            center_y_ratio=float(payload["item_icon_center_y_ratio"]),
            visible_start_ratio=float(payload["item_icon_visible_start_ratio"]),
            visible_end_ratio=float(payload["item_icon_visible_end_ratio"]),
            opacity=float(payload["item_icon_opacity"]),
            layer=str(payload["item_icon_layer"]),
            background_enabled=bool(payload["item_icon_background_enabled"]),
        )

    def _refresh_preview(self, *, play: bool) -> None:
        self._player.stop()
        self._preview_pixmap = None
        self._preview_label.clear()
        self._preview_label.setText("正在准备预览...")

        action_id = self._current_action()
        state = self._current_state()
        item = self._current_item()
        if self._catalog is None:
            self._set_preview_error("素材目录不可用。")
            return
        if not action_id or not state:
            self._set_preview_error("请选择动作和状态。")
            return
        if not self._catalog.has_action(action_id):
            self._set_preview_error(f"动作没有素材: {action_id}")
            return
        if self._catalog.action_type(action_id) != "single":
            self._set_preview_error("当前页只预览照顾用 single 动作。")
            return
        if item is None:
            self._set_preview_error("没有可用的预览物品图标。")
            return

        icon_path = resolve_item_icon_path(item)
        if icon_path is None:
            self._set_preview_error(f"找不到物品图标: {item.name}")
            return
        icon = QPixmap(str(icon_path))
        if icon.isNull():
            self._set_preview_error(f"物品图标无法读取: {icon_path}")
            return

        try:
            clip = self._catalog.single_for(action_id, state)
            clip = clip_with_pixmap_overlay(clip, icon, self._current_config())
        except Exception as exc:
            self._set_preview_error(f"无法生成预览: {exc}")
            return

        source_state = getattr(clip, "source_state", None) or state
        self._info.setText(
            f"动作: {action_id}\n"
            f"状态: {state}\n"
            f"素材状态: {source_state}\n"
            f"物品: {item.name}\n"
            f"帧数: {len(clip)}\n"
            f"时长: {clip.duration_ms} ms"
        )
        self._status.setText("预览已刷新。Ctrl+S 保存当前配置。")
        if play:
            self._player.play(clip, loop=False)
        else:
            self._on_frame(clip.frame(0))

    def _set_preview_error(self, message: str) -> None:
        self._player.stop()
        self._preview_pixmap = None
        self._preview_label.clear()
        self._preview_label.setText(message)
        self._info.setText(message)
        self._status.setText(message)

    def _stop_preview(self) -> None:
        self._player.stop()
        self._status.setText("预览已停止。")

    def _on_frame(self, pixmap: QPixmap) -> None:
        self._preview_pixmap = QPixmap(pixmap)
        self._paint_preview_pixmap()

    def _on_player_finished(self) -> None:
        self._status.setText("单次预览播放完成。Ctrl+S 保存当前配置。")

    def _paint_preview_pixmap(self) -> None:
        if self._preview_pixmap is None:
            return
        scaled = self._preview_pixmap.scaled(
            self._preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setText("")
        self._preview_label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._paint_preview_pixmap()

    def _choose_item_for_action(self) -> None:
        if self._item.count() == 0:
            return
        preferred = ACTION_ITEM_CATEGORIES.get(self._current_action())
        if preferred is None:
            return
        for index, item in enumerate(self._items):
            if item.category == preferred:
                self._item.blockSignals(True)
                self._item.setCurrentIndex(index)
                self._item.blockSignals(False)
                return

    def _current_action(self) -> str:
        data = self._action.currentData()
        return str(data) if data is not None else self._action.currentText().strip()

    def _current_state(self) -> str:
        return self._state.currentText().strip()

    def _current_item(self) -> ItemDefinition | None:
        item_id = self._item.currentData()
        if item_id is None:
            return None
        for item in self._items:
            if item.id == str(item_id):
                return item
        return None

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value or combo.itemText(index) == value:
                combo.setCurrentIndex(index)
                return

    def save(self) -> None:
        self._write_controls_to_settings()
        _validate_settings(self._settings)
        _backup()
        CONFIG_PATH.write_text(
            json.dumps(self._settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._status.setText("care_overlay.json 已保存。")


def _ratio_spin(*, minimum: float, maximum: float, step: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(3)
    spin.setSingleStep(step)
    return spin


def _load_settings() -> dict[str, object]:
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"enabled": True, "actions": {}}
    if not isinstance(payload, dict):
        return {"enabled": True, "actions": {}}
    result = dict(payload)
    result.setdefault("enabled", True)
    result.setdefault("actions", {})
    return result


def _configured_actions(settings: Mapping[str, object]) -> tuple[str, ...]:
    actions = settings.get("actions")
    if not isinstance(actions, Mapping):
        return ()
    return tuple(str(action_id) for action_id in actions if str(action_id).strip())


def _state_config(
    settings: Mapping[str, object],
    action_id: str,
    state: str,
) -> Mapping[str, object]:
    actions = settings.get("actions")
    if not isinstance(actions, Mapping):
        return DEFAULT_OVERLAY_CONFIG
    action_settings = actions.get(action_id)
    if not isinstance(action_settings, Mapping):
        return DEFAULT_OVERLAY_CONFIG
    state_settings = action_settings.get(state)
    if not isinstance(state_settings, Mapping):
        return DEFAULT_OVERLAY_CONFIG
    values = dict(DEFAULT_OVERLAY_CONFIG)
    values.update(state_settings)
    return values


def _float_value(values: Mapping[str, object], key: str) -> float:
    try:
        return float(values[key])
    except (KeyError, TypeError, ValueError):
        return float(DEFAULT_OVERLAY_CONFIG[key])


def _validate_settings(settings: Mapping[str, object]) -> None:
    actions = settings.get("actions")
    if not isinstance(actions, Mapping):
        raise ValueError("care_overlay.json 的 actions 必须是对象。")
    for action_id, action_settings in actions.items():
        if not isinstance(action_settings, Mapping):
            raise ValueError(f"{action_id} 的配置必须是对象。")
        for state, state_settings in action_settings.items():
            if state not in PET_STATES:
                raise ValueError(f"{action_id} 的状态不合法: {state}")
            if not isinstance(state_settings, Mapping):
                raise ValueError(f"{action_id}/{state} 的配置必须是对象。")
            start = _float_value(state_settings, "item_icon_visible_start_ratio")
            end = _float_value(state_settings, "item_icon_visible_end_ratio")
            if end <= start:
                raise ValueError(f"{action_id}/{state} 的出现终点必须大于出现起点。")
            layer = str(state_settings.get("item_icon_layer", "")).strip()
            if not layer:
                raise ValueError(f"{action_id}/{state} 的层级不能为空。")
            if not isinstance(
                state_settings.get("item_icon_background_enabled"),
                bool,
            ):
                raise ValueError(f"{action_id}/{state} 的浅色底开关必须是 true/false。")
