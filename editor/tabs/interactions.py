"""互动区域配置：可视化编辑 config/interaction_map.json"""
from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.app_paths import assets_dir, config_path
from core.loader import _load_action_specs, load_animation_catalog
from core.playback.catalog import DEFAULT_PET_STATE, ActionSpec


INTERACTION_MAP_PATH = config_path("interaction_map.json")
ACTION_SETTINGS_PATH = config_path("action_settings.json")
BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / ".vpet_editor_backups"

BEHAVIOR_LABELS = {
    "inherit": "继承默认",
    "none": "无动作",
    "move_window": "拖动窗口",
    "press_mode": "按住动作",
    "switch_mode": "切换动作",
}
GESTURE_LABELS = {
    "press": "按下",
    "click": "点击",
    "drag": "拖动",
}
GESTURE_ALLOWED_TYPES = {
    "press": ("none", "press_mode", "switch_mode"),
    "click": ("none", "switch_mode"),
    "drag": ("none", "move_window"),
}
REGION_COLORS = (
    QColor(42, 141, 219, 92),
    QColor(236, 122, 8, 92),
    QColor(34, 160, 107, 92),
    QColor(180, 86, 198, 92),
    QColor(215, 66, 80, 92),
    QColor(60, 130, 120, 92),
)


def _backup() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = BACKUP_DIR / f"interaction_map-{ts}.json"
    shutil.copy2(INTERACTION_MAP_PATH, dst)


def _action_label(spec: ActionSpec) -> str:
    return f"{spec.id} - {spec.title}" if spec.title else spec.id


def _combo_current_id(combo: QComboBox) -> str:
    data = combo.currentData()
    return str(data) if data is not None else combo.currentText()


def _behavior_summary(behavior: dict | None, *, inherited: bool = False) -> str:
    if behavior is None:
        return "继承默认"
    behavior_type = str(behavior.get("type", "none"))
    label = BEHAVIOR_LABELS.get(behavior_type, behavior_type)
    prefix = "默认 " if inherited else ""
    if behavior_type in ("press_mode", "switch_mode"):
        mode = str(behavior.get("mode", "")).strip()
        return f"{prefix}{label}: {mode or '-'}"
    return f"{prefix}{label}"


def _first_preview_pixmap() -> QPixmap:
    try:
        settings = json.loads(ACTION_SETTINGS_PATH.read_text(encoding="utf-8"))
        specs = _load_action_specs()
        spec_map = {spec.id: spec for spec in specs}
        default_id = str(settings.get("default_mode", ""))
        default_spec = spec_map.get(default_id)
        if default_spec is not None:
            catalog = load_animation_catalog(action_specs=specs)
            clip = catalog.mode_for(
                default_id,
                DEFAULT_PET_STATE,
                action_type=default_spec.type,
            ).loop
            if clip.frame_paths:
                pixmap = QPixmap(str(clip.frame_paths[0]))
                if not pixmap.isNull():
                    return pixmap
    except Exception:
        pass

    for path in sorted((assets_dir() / "animations").rglob("*.png")):
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            return pixmap
    return QPixmap()


class BehaviorControl(QWidget):
    changed = pyqtSignal()

    def __init__(
        self,
        gesture: str,
        action_specs: tuple[ActionSpec, ...],
        parent: QWidget | None = None,
        *,
        allow_inherit: bool,
    ) -> None:
        super().__init__(parent)
        self._gesture = gesture
        self._action_specs = action_specs
        self._allow_inherit = allow_inherit
        self._updating = False

        self._type = QComboBox(self)
        if allow_inherit:
            self._type.addItem(BEHAVIOR_LABELS["inherit"], "inherit")
        for behavior_type in GESTURE_ALLOWED_TYPES[gesture]:
            self._type.addItem(BEHAVIOR_LABELS[behavior_type], behavior_type)

        self._mode = QComboBox(self)
        self._mode.setMinimumWidth(180)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._type, 0)
        layout.addWidget(self._mode, 1)

        self._type.currentIndexChanged.connect(self._on_type_changed)
        self._mode.currentIndexChanged.connect(self._emit_changed)
        self._on_type_changed()

    def set_behavior(self, behavior: dict | None) -> None:
        self._updating = True
        try:
            if behavior is None and self._allow_inherit:
                self._set_type("inherit")
                self._mode.clear()
                return
            behavior_type = str((behavior or {}).get("type", "none"))
            if self._type.findData(behavior_type) < 0:
                self._type.addItem(
                    f"{BEHAVIOR_LABELS.get(behavior_type, behavior_type)}（不建议）",
                    behavior_type,
                )
            self._set_type(behavior_type)
            self._replace_mode_items(behavior_type)
            mode = str((behavior or {}).get("mode", ""))
            if mode:
                if self._mode.findData(mode) < 0:
                    self._mode.addItem(f"{mode}（未注册）", mode)
                index = self._mode.findData(mode)
                self._mode.setCurrentIndex(max(0, index))
        finally:
            self._updating = False
        self._sync_mode_enabled()

    def behavior(self) -> dict | None:
        behavior_type = self.behavior_type()
        if behavior_type == "inherit":
            return None
        if behavior_type in ("press_mode", "switch_mode"):
            return {"type": behavior_type, "mode": _combo_current_id(self._mode)}
        return {"type": behavior_type}

    def behavior_type(self) -> str:
        return _combo_current_id(self._type)

    def _set_type(self, behavior_type: str) -> None:
        index = self._type.findData(behavior_type)
        self._type.setCurrentIndex(max(0, index))

    def _on_type_changed(self) -> None:
        self._replace_mode_items(self.behavior_type())
        self._sync_mode_enabled()
        self._emit_changed()

    def _replace_mode_items(self, behavior_type: str) -> None:
        current = _combo_current_id(self._mode)
        self._mode.clear()
        if behavior_type == "press_mode":
            specs = [spec for spec in self._action_specs if spec.type == "phased"]
        elif behavior_type == "switch_mode":
            specs = [spec for spec in self._action_specs if spec.type in ("loop", "phased")]
        else:
            specs = []
        for spec in specs:
            self._mode.addItem(_action_label(spec), spec.id)
        if current:
            index = self._mode.findData(current)
            if index >= 0:
                self._mode.setCurrentIndex(index)

    def _sync_mode_enabled(self) -> None:
        self._mode.setEnabled(self.behavior_type() in ("press_mode", "switch_mode"))

    def _emit_changed(self) -> None:
        if not self._updating:
            self.changed.emit()


class InteractionMapPreview(QWidget):
    cell_selected = pyqtSignal(int, int)
    cell_hovered = pyqtSignal(int, int)
    hover_left = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows = 1
        self._cols = 1
        self._regions: list[dict] = []
        self._selected_index: int | None = None
        self._hover_cell: tuple[int, int] | None = None
        self._pixmap = QPixmap()
        self.setMouseTracking(True)
        self.setMinimumSize(360, 360)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.update()

    def set_map(
        self,
        *,
        rows: int,
        cols: int,
        regions: list[dict],
        selected_index: int | None,
    ) -> None:
        self._rows = max(1, rows)
        self._cols = max(1, cols)
        self._regions = regions
        self._selected_index = selected_index
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(22, 24, 28))

        grid_rect = self._grid_rect()
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                grid_rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = grid_rect.left() + (grid_rect.width() - scaled.width()) // 2
            y = grid_rect.top() + (grid_rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.fillRect(grid_rect, QColor(40, 43, 48))

        painter.fillRect(grid_rect, QColor(255, 255, 255, 18))

        for index, region in enumerate(self._regions):
            self._draw_region(painter, grid_rect, region, index)

        self._draw_grid(painter, grid_rect)
        self._draw_hover(painter, grid_rect)
        painter.setPen(QPen(QColor(210, 220, 230), 1))
        painter.drawRect(grid_rect.adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            cell = self._cell_at(event.position().toPoint())
            if cell is not None:
                self.cell_selected.emit(cell[0], cell[1])
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        cell = self._cell_at(event.position().toPoint())
        if cell != self._hover_cell:
            self._hover_cell = cell
            if cell is None:
                self.hover_left.emit()
            else:
                self.cell_hovered.emit(cell[0], cell[1])
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_cell = None
        self.hover_left.emit()
        self.update()
        super().leaveEvent(event)

    def _grid_rect(self) -> QRect:
        bounds = self.rect().adjusted(12, 12, -12, -12)
        if bounds.width() <= 0 or bounds.height() <= 0:
            return QRect(0, 0, 1, 1)
        if self._pixmap.isNull():
            side = min(bounds.width(), bounds.height())
            return QRect(
                bounds.left() + (bounds.width() - side) // 2,
                bounds.top() + (bounds.height() - side) // 2,
                side,
                side,
            )
        pix_size = self._pixmap.size()
        aspect = pix_size.width() / max(1, pix_size.height())
        width = bounds.width()
        height = round(width / aspect)
        if height > bounds.height():
            height = bounds.height()
            width = round(height * aspect)
        return QRect(
            bounds.left() + (bounds.width() - width) // 2,
            bounds.top() + (bounds.height() - height) // 2,
            max(1, width),
            max(1, height),
        )

    def _cell_rect(self, grid_rect: QRect, row: int, col: int) -> QRect:
        x0 = grid_rect.left() + round(col * grid_rect.width() / self._cols)
        x1 = grid_rect.left() + round((col + 1) * grid_rect.width() / self._cols)
        y0 = grid_rect.top() + round(row * grid_rect.height() / self._rows)
        y1 = grid_rect.top() + round((row + 1) * grid_rect.height() / self._rows)
        return QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))

    def _region_rect(self, grid_rect: QRect, region: dict) -> QRect:
        row_start = int(region.get("row_start", 0))
        row_end = int(region.get("row_end", row_start))
        col_start = int(region.get("col_start", 0))
        col_end = int(region.get("col_end", col_start))
        top_left = self._cell_rect(grid_rect, row_start, col_start)
        bottom_right = self._cell_rect(grid_rect, row_end, col_end)
        return QRect(
            top_left.left(),
            top_left.top(),
            bottom_right.right() - top_left.left() + 1,
            bottom_right.bottom() - top_left.top() + 1,
        )

    def _draw_region(
        self,
        painter: QPainter,
        grid_rect: QRect,
        region: dict,
        index: int,
    ) -> None:
        rect = self._region_rect(grid_rect, region)
        color = QColor(REGION_COLORS[index % len(REGION_COLORS)])
        if index == self._selected_index:
            color.setAlpha(150)
        painter.fillRect(rect, color)
        pen_color = (
            QColor(255, 255, 255, 230)
            if index == self._selected_index
            else QColor(30, 45, 60, 190)
        )
        painter.setPen(QPen(pen_color, 2 if index == self._selected_index else 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        painter.setPen(QColor(255, 255, 255, 235))
        painter.drawText(
            rect.adjusted(5, 4, -5, -4),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            str(region.get("name", "")),
        )

    def _draw_grid(self, painter: QPainter, grid_rect: QRect) -> None:
        painter.setPen(QPen(QColor(255, 255, 255, 120), 1))
        for row in range(1, self._rows):
            y = grid_rect.top() + round(row * grid_rect.height() / self._rows)
            painter.drawLine(grid_rect.left(), y, grid_rect.right(), y)
        for col in range(1, self._cols):
            x = grid_rect.left() + round(col * grid_rect.width() / self._cols)
            painter.drawLine(x, grid_rect.top(), x, grid_rect.bottom())

    def _draw_hover(self, painter: QPainter, grid_rect: QRect) -> None:
        if self._hover_cell is None:
            return
        row, col = self._hover_cell
        rect = self._cell_rect(grid_rect, row, col)
        painter.fillRect(rect, QColor(255, 255, 255, 46))
        painter.setPen(QPen(QColor(255, 255, 255, 230), 2))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

    def _cell_at(self, point: QPoint) -> tuple[int, int] | None:
        grid_rect = self._grid_rect()
        if not grid_rect.contains(point):
            return None
        x = min(max(point.x() - grid_rect.left(), 0), grid_rect.width() - 1)
        y = min(max(point.y() - grid_rect.top(), 0), grid_rect.height() - 1)
        col = min(self._cols - 1, x * self._cols // max(1, grid_rect.width()))
        row = min(self._rows - 1, y * self._rows // max(1, grid_rect.height()))
        return row, col


class InteractionsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._updating = False
        self._selected_index: int | None = None
        self._selected_cell: tuple[int, int] | None = None
        self._action_specs = _load_action_specs()
        self._regions: list[dict] = []

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._build_preview_panel())
        splitter.addWidget(self._build_editor_panel())
        splitter.setSizes([560, 360])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._preview.set_pixmap(_first_preview_pixmap())
        self._load()

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 4, 8)
        layout.setSpacing(8)

        self._preview = InteractionMapPreview(panel)
        self._preview.cell_selected.connect(self._on_cell_selected)
        self._preview.cell_hovered.connect(self._on_cell_hovered)
        self._preview.hover_left.connect(self._on_hover_left)
        layout.addWidget(self._preview, 1)

        self._cell_status = QLabel("选择一个格子或区域", panel)
        self._cell_status.setWordWrap(True)
        self._cell_status.setMinimumHeight(44)
        layout.addWidget(self._cell_status)
        return panel

    def _build_editor_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 8, 8, 8)
        layout.setSpacing(8)

        grid_group = QGroupBox("网格", panel)
        grid_form = QFormLayout(grid_group)
        self._rows = QSpinBox(grid_group)
        self._rows.setRange(1, 50)
        self._cols = QSpinBox(grid_group)
        self._cols.setRange(1, 50)
        self._rows.valueChanged.connect(self._on_grid_changed)
        self._cols.valueChanged.connect(self._on_grid_changed)
        grid_form.addRow("行数", self._rows)
        grid_form.addRow("列数", self._cols)
        layout.addWidget(grid_group)

        defaults_group = QGroupBox("默认行为", panel)
        defaults_form = QFormLayout(defaults_group)
        self._default_controls: dict[str, BehaviorControl] = {}
        for gesture in ("press", "click", "drag"):
            control = BehaviorControl(
                gesture,
                self._action_specs,
                defaults_group,
                allow_inherit=False,
            )
            control.changed.connect(self._refresh_preview)
            self._default_controls[gesture] = control
            defaults_form.addRow(GESTURE_LABELS[gesture], control)
        layout.addWidget(defaults_group)

        regions_group = QGroupBox("区域", panel)
        regions_layout = QVBoxLayout(regions_group)
        self._region_list = QListWidget(regions_group)
        self._region_list.currentRowChanged.connect(self._on_region_selected)
        regions_layout.addWidget(self._region_list)

        button_row = QHBoxLayout()
        self._add_button = QPushButton("添加", regions_group)
        self._delete_button = QPushButton("删除", regions_group)
        self._add_button.clicked.connect(self._add_region)
        self._delete_button.clicked.connect(self._delete_region)
        button_row.addWidget(self._add_button)
        button_row.addWidget(self._delete_button)
        regions_layout.addLayout(button_row)
        layout.addWidget(regions_group, 1)

        detail_group = QGroupBox("选中区域", panel)
        detail_form = QFormLayout(detail_group)
        self._name = QLineEdit(detail_group)
        self._name.textChanged.connect(self._on_region_form_changed)
        detail_form.addRow("名称", self._name)

        self._row_start = self._make_region_spinbox(detail_group)
        self._row_end = self._make_region_spinbox(detail_group)
        self._col_start = self._make_region_spinbox(detail_group)
        self._col_end = self._make_region_spinbox(detail_group)
        detail_form.addRow("起始行", self._row_start)
        detail_form.addRow("结束行", self._row_end)
        detail_form.addRow("起始列", self._col_start)
        detail_form.addRow("结束列", self._col_end)

        self._region_controls: dict[str, BehaviorControl] = {}
        for gesture in ("press", "click", "drag"):
            control = BehaviorControl(
                gesture,
                self._action_specs,
                detail_group,
                allow_inherit=True,
            )
            control.changed.connect(self._on_region_form_changed)
            self._region_controls[gesture] = control
            detail_form.addRow(GESTURE_LABELS[gesture], control)
        layout.addWidget(detail_group)
        self._detail_group = detail_group
        return panel

    def _make_region_spinbox(self, parent: QWidget) -> QSpinBox:
        spinbox = QSpinBox(parent)
        spinbox.setRange(0, 0)
        spinbox.valueChanged.connect(self._on_region_form_changed)
        return spinbox

    def _load(self) -> None:
        data = json.loads(INTERACTION_MAP_PATH.read_text(encoding="utf-8"))
        self._updating = True
        try:
            grid = data.get("grid", {})
            self._rows.setValue(int(grid.get("rows", 1)))
            self._cols.setValue(int(grid.get("cols", 1)))
            defaults = data.get("default_behaviors", {})
            for gesture, control in self._default_controls.items():
                control.set_behavior(defaults.get(gesture, {"type": "none"}))
            self._regions = [deepcopy(region) for region in data.get("regions", [])]
            self._selected_index = 0 if self._regions else None
            self._sync_spin_ranges()
            self._refresh_region_list()
            self._load_selected_region()
        finally:
            self._updating = False
        self._refresh_preview()

    def _sync_spin_ranges(self) -> None:
        max_row = max(0, self._rows.value() - 1)
        max_col = max(0, self._cols.value() - 1)
        for spinbox in (self._row_start, self._row_end):
            spinbox.setRange(0, max_row)
        for spinbox in (self._col_start, self._col_end):
            spinbox.setRange(0, max_col)

    def _refresh_preview(self) -> None:
        self._preview.set_map(
            rows=self._rows.value(),
            cols=self._cols.value(),
            regions=self._regions,
            selected_index=self._selected_index,
        )
        if self._selected_cell is not None:
            self._show_cell_status(*self._selected_cell)

    def _refresh_region_list(self) -> None:
        current = self._selected_index
        self._region_list.blockSignals(True)
        try:
            self._region_list.clear()
            for region in self._regions:
                item = QListWidgetItem(self._format_region_label(region))
                self._region_list.addItem(item)
            if current is not None and 0 <= current < self._region_list.count():
                self._region_list.setCurrentRow(current)
            else:
                self._region_list.setCurrentRow(-1)
        finally:
            self._region_list.blockSignals(False)

    def _format_region_label(self, region: dict) -> str:
        name = str(region.get("name", "")).strip() or "未命名区域"
        return (
            f"{name}  "
            f"r{region.get('row_start', 0)}-{region.get('row_end', 0)} "
            f"c{region.get('col_start', 0)}-{region.get('col_end', 0)}"
        )

    def _load_selected_region(self) -> None:
        self._updating = True
        try:
            enabled = self._selected_index is not None
            self._detail_group.setEnabled(enabled)
            if self._selected_index is None:
                self._name.clear()
                for spinbox in (
                    self._row_start,
                    self._row_end,
                    self._col_start,
                    self._col_end,
                ):
                    spinbox.setValue(0)
                for control in self._region_controls.values():
                    control.set_behavior(None)
                return

            region = self._regions[self._selected_index]
            self._name.setText(str(region.get("name", "")))
            self._row_start.setValue(int(region.get("row_start", 0)))
            self._row_end.setValue(int(region.get("row_end", 0)))
            self._col_start.setValue(int(region.get("col_start", 0)))
            self._col_end.setValue(int(region.get("col_end", 0)))
            for gesture, control in self._region_controls.items():
                control.set_behavior(region.get(gesture))
        finally:
            self._updating = False

    def _on_grid_changed(self) -> None:
        self._sync_spin_ranges()
        self._refresh_preview()

    def _on_region_selected(self, row: int) -> None:
        if self._updating:
            return
        self._selected_index = row if row >= 0 else None
        self._load_selected_region()
        self._refresh_preview()

    def _on_region_form_changed(self) -> None:
        if self._updating or self._selected_index is None:
            return
        region = self._regions[self._selected_index]
        region["name"] = self._name.text().strip()
        region["row_start"] = self._row_start.value()
        region["row_end"] = self._row_end.value()
        region["col_start"] = self._col_start.value()
        region["col_end"] = self._col_end.value()
        for gesture, control in self._region_controls.items():
            behavior = control.behavior()
            if behavior is None:
                region.pop(gesture, None)
            else:
                region[gesture] = behavior
        self._refresh_region_list()
        self._refresh_preview()

    def _add_region(self) -> None:
        row, col = self._selected_cell or (0, 0)
        index = len(self._regions) + 1
        self._regions.append(
            {
                "name": f"region_{index}",
                "row_start": row,
                "row_end": row,
                "col_start": col,
                "col_end": col,
                "press": {"type": "none"},
            }
        )
        self._selected_index = len(self._regions) - 1
        self._refresh_region_list()
        self._load_selected_region()
        self._refresh_preview()

    def _delete_region(self) -> None:
        if self._selected_index is None:
            return
        del self._regions[self._selected_index]
        if not self._regions:
            self._selected_index = None
        else:
            self._selected_index = min(self._selected_index, len(self._regions) - 1)
        self._refresh_region_list()
        self._load_selected_region()
        self._refresh_preview()

    def _on_cell_selected(self, row: int, col: int) -> None:
        self._selected_cell = (row, col)
        region_index = self._region_index_at(row, col)
        if region_index is not None:
            self._selected_index = region_index
        else:
            self._selected_index = None
        self._refresh_region_list()
        self._load_selected_region()
        self._show_cell_status(row, col)
        self._refresh_preview()

    def _on_cell_hovered(self, row: int, col: int) -> None:
        self._show_cell_status(row, col)

    def _on_hover_left(self) -> None:
        if self._selected_cell is None:
            self._cell_status.setText("选择一个格子或区域")
        else:
            self._show_cell_status(*self._selected_cell)

    def _region_index_at(self, row: int, col: int) -> int | None:
        for index, region in enumerate(self._regions):
            if (
                int(region.get("row_start", 0)) <= row <= int(region.get("row_end", 0))
                and int(region.get("col_start", 0)) <= col <= int(region.get("col_end", 0))
            ):
                return index
        return None

    def _show_cell_status(self, row: int, col: int) -> None:
        matches = [
            region
            for region in self._regions
            if (
                int(region.get("row_start", 0)) <= row <= int(region.get("row_end", 0))
                and int(region.get("col_start", 0)) <= col <= int(region.get("col_end", 0))
            )
        ]
        region = matches[0] if matches else None
        conflict = ""
        if len(matches) > 1:
            names = "、".join(str(item.get("name", "未命名区域")) for item in matches)
            conflict = f" | 冲突: {names}"
        owner = str(region.get("name", "未命名区域")) if region else "默认"
        parts = [f"格子 r{row} c{col} | 区域: {owner}{conflict}"]
        for gesture in ("press", "click", "drag"):
            behavior, inherited = self._resolve_behavior(region, gesture)
            parts.append(
                f"{GESTURE_LABELS[gesture]}: "
                f"{_behavior_summary(behavior, inherited=inherited)}"
            )
        self._cell_status.setText("\n".join(parts))

    def _resolve_behavior(
        self,
        region: dict | None,
        gesture: str,
    ) -> tuple[dict | None, bool]:
        if region is not None and gesture in region:
            return region.get(gesture), False
        return self._default_controls[gesture].behavior(), True

    def _collect(self) -> dict:
        data = {
            "grid": {
                "rows": self._rows.value(),
                "cols": self._cols.value(),
            },
            "default_behaviors": {
                gesture: control.behavior() or {"type": "none"}
                for gesture, control in self._default_controls.items()
            },
            "regions": deepcopy(self._regions),
        }
        self._validate(data)
        return data

    def _validate(self, data: dict) -> None:
        rows = int(data["grid"]["rows"])
        cols = int(data["grid"]["cols"])
        if rows < 1 or cols < 1:
            raise ValueError("网格行数和列数必须大于 0")

        action_types = {spec.id: spec.type for spec in self._action_specs}
        for gesture in ("press", "click", "drag"):
            self._validate_behavior(
                data["default_behaviors"].get(gesture),
                gesture,
                action_types,
                f"默认 {GESTURE_LABELS[gesture]}",
                allow_none=False,
            )

        occupied: dict[tuple[int, int], str] = {}
        seen_names: set[str] = set()
        for index, region in enumerate(data["regions"]):
            label = f"第 {index + 1} 个区域"
            name = str(region.get("name", "")).strip()
            if not name:
                raise ValueError(f"{label} 名称不能为空")
            if name in seen_names:
                raise ValueError(f"区域名称重复: {name}")
            seen_names.add(name)

            row_start = int(region.get("row_start", 0))
            row_end = int(region.get("row_end", 0))
            col_start = int(region.get("col_start", 0))
            col_end = int(region.get("col_end", 0))
            if row_start < 0 or col_start < 0:
                raise ValueError(f"{name} 的起始行列不能小于 0")
            if row_end < row_start or col_end < col_start:
                raise ValueError(f"{name} 的结束行列不能小于起始行列")
            if row_end >= rows or col_end >= cols:
                raise ValueError(f"{name} 超出了当前网格范围")

            for row in range(row_start, row_end + 1):
                for col in range(col_start, col_end + 1):
                    cell = (row, col)
                    if cell in occupied:
                        raise ValueError(
                            f"格子 r{row} c{col} 同时被 {occupied[cell]} 和 {name} 覆盖。"
                            "interaction_map 不允许区域重叠。"
                        )
                    occupied[cell] = name

            for gesture in ("press", "click", "drag"):
                self._validate_behavior(
                    region.get(gesture),
                    gesture,
                    action_types,
                    f"{name} 的 {GESTURE_LABELS[gesture]}",
                    allow_none=True,
                )

    def _validate_behavior(
        self,
        behavior: dict | None,
        gesture: str,
        action_types: dict[str, str],
        label: str,
        *,
        allow_none: bool,
    ) -> None:
        if behavior is None:
            if allow_none:
                return
            raise ValueError(f"{label} 行为不能为空")
        if not isinstance(behavior, dict):
            raise ValueError(f"{label} 行为必须是对象")
        behavior_type = str(behavior.get("type", "none"))
        if behavior_type not in GESTURE_ALLOWED_TYPES[gesture]:
            allowed = "、".join(
                BEHAVIOR_LABELS[item] for item in GESTURE_ALLOWED_TYPES[gesture]
            )
            raise ValueError(f"{label} 不支持 {behavior_type}，只允许 {allowed}")
        if behavior_type == "press_mode":
            mode = str(behavior.get("mode", "")).strip()
            if not mode:
                raise ValueError(f"{label} 必须选择动作")
            if action_types.get(mode) != "phased":
                raise ValueError(f"{label} 只能选择 phased 动作: {mode}")
        if behavior_type == "switch_mode":
            mode = str(behavior.get("mode", "")).strip()
            if not mode:
                raise ValueError(f"{label} 必须选择动作")
            if action_types.get(mode) not in ("loop", "phased"):
                raise ValueError(f"{label} 只能选择 loop 或 phased 动作: {mode}")

    def save(self) -> None:
        data = self._collect()
        _backup()
        INTERACTION_MAP_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
