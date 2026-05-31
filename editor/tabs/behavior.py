"""自动行为配置：编辑 config/action_settings.json"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.app_paths import config_path
from core.loader import _load_action_specs, load_animation_catalog
from core.playback.catalog import DEFAULT_PET_STATE, ActionSpec

SETTINGS_PATH = config_path("action_settings.json")
BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / ".vpet_editor_backups"


def _backup() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = BACKUP_DIR / f"action_settings-{ts}.json"
    shutil.copy2(SETTINGS_PATH, dst)


def _mode_ids_by_type(specs: tuple[ActionSpec, ...], *types: str) -> list[str]:
    return [spec.id for spec in specs if spec.type in types]


def _playable_mode_ids_for_default(specs: tuple[ActionSpec, ...]) -> list[str]:
    catalog = load_animation_catalog(action_specs=specs)
    modes = catalog.build_modes(specs, DEFAULT_PET_STATE)
    return [
        spec.id
        for spec in specs
        if spec.type in ("phased", "loop") and spec.id in modes
    ]


def _replace_combo_items(
    combo: QComboBox,
    items: list[str],
    current: str,
    *,
    invalid_note: str | None = None,
) -> None:
    combo.clear()
    for item in items:
        combo.addItem(item, item)
    if current in items:
        combo.setCurrentText(current)
        return
    if current and invalid_note is not None:
        combo.addItem(f"{current}（{invalid_note}）", current)
        combo.setCurrentIndex(combo.count() - 1)
        model_item = combo.model().item(combo.count() - 1)
        if model_item is not None:
            model_item.setEnabled(False)


def _combo_current_id(combo: QComboBox) -> str:
    data = combo.currentData()
    return str(data) if data is not None else combo.currentText()


def _collect_checked(w: QListWidget) -> list[str]:
    result = []
    for i in range(w.count()):
        item = w.item(i)
        if item.checkState() == Qt.CheckState.Checked:
            result.append(item.text())
    return result


def _require_interval_order(label: str, min_ms: int, max_ms: int) -> None:
    if min_ms > max_ms:
        raise ValueError(f"{label} 的最小间隔不能大于最大间隔")


class BehaviorTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._valid_default_modes: set[str] = set()
        layout = QVBoxLayout(self)

        # ---- 基础设置 ----
        basic = QGroupBox("基础设置", self)
        form = QFormLayout(basic)
        self._default_mode = QComboBox(self)
        self._press_mode = QComboBox(self)
        form.addRow("默认动作", self._default_mode)
        form.addRow("按住互动", self._press_mode)
        layout.addWidget(basic)

        # ---- 空闲自动切换 ----
        idle = QGroupBox("空闲自动切换", self)
        idle_form = QFormLayout(idle)
        self._idle_min = QSpinBox(self)
        self._idle_min.setRange(1000, 3600000)
        self._idle_min.setSingleStep(10000)
        self._idle_min.setSuffix(" ms")
        self._idle_max = QSpinBox(self)
        self._idle_max.setRange(1000, 3600000)
        self._idle_max.setSingleStep(10000)
        self._idle_max.setSuffix(" ms")
        self._auto_idle_modes = QListWidget(self)
        idle_form.addRow("最小间隔", self._idle_min)
        idle_form.addRow("最大间隔", self._idle_max)
        idle_form.addRow("候选动作", self._auto_idle_modes)
        layout.addWidget(idle)

        # ---- 单次插入 ----
        single = QGroupBox("单次插入", self)
        single_form = QFormLayout(single)
        self._single_min = QSpinBox(self)
        self._single_min.setRange(1000, 3600000)
        self._single_min.setSingleStep(10000)
        self._single_min.setSuffix(" ms")
        self._single_max = QSpinBox(self)
        self._single_max.setRange(1000, 3600000)
        self._single_max.setSingleStep(10000)
        self._single_max.setSuffix(" ms")
        self._single_modes = QListWidget(self)
        single_form.addRow("最小间隔", self._single_min)
        single_form.addRow("最大间隔", self._single_max)
        single_form.addRow("候选动作", self._single_modes)
        layout.addWidget(single)

        # ---- 启动/关机 ----
        edge = QGroupBox("启动 / 关机", self)
        edge_form = QFormLayout(edge)
        self._startup = QListWidget(self)
        self._shutdown = QListWidget(self)
        edge_form.addRow("启动动作", self._startup)
        edge_form.addRow("关机动作", self._shutdown)
        layout.addWidget(edge)

        layout.addStretch()
        self._load()

    def _load(self) -> None:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        specs = _load_action_specs()
        phased_loop_ids = _mode_ids_by_type(specs, "phased", "loop")
        phased_ids = _mode_ids_by_type(specs, "phased")
        single_ids = _mode_ids_by_type(specs, "single")
        default_ids = _playable_mode_ids_for_default(specs)
        self._valid_default_modes = set(default_ids)

        # default_mode / press_mode
        _replace_combo_items(
            self._default_mode,
            default_ids,
            settings.get("default_mode", ""),
            invalid_note=f"{DEFAULT_PET_STATE} 状态不可播放",
        )
        self._press_mode.clear()
        self._press_mode.addItems(phased_ids)
        self._press_mode.setCurrentText(settings.get("press_mode", ""))

        # idle
        self._idle_min.setValue(settings.get("idle_autoswitch_interval_min_ms", 180000))
        self._idle_max.setValue(settings.get("idle_autoswitch_interval_max_ms", 600000))
        self._replace_checkable_list(
            self._auto_idle_modes,
            phased_loop_ids,
            set(settings.get("auto_idle_modes", [])),
        )

        # single
        self._single_min.setValue(settings.get("single_insert_interval_min_ms", 180000))
        self._single_max.setValue(settings.get("single_insert_interval_max_ms", 600000))
        self._replace_checkable_list(
            self._single_modes,
            single_ids,
            set(settings.get("single_insert_modes", [])),
        )

        # startup / shutdown
        self._replace_checkable_list(
            self._startup, single_ids, set(settings.get("startup", []))
        )
        self._replace_checkable_list(
            self._shutdown, single_ids, set(settings.get("shutdown", []))
        )

    @staticmethod
    def _replace_checkable_list(w: QListWidget, items: list[str], checked: set[str]) -> None:
        w.clear()
        for item in items:
            list_item = QListWidgetItem(item, w)
            list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            list_item.setCheckState(
                Qt.CheckState.Checked if item in checked else Qt.CheckState.Unchecked
            )

    def save(self) -> None:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        default_mode = _combo_current_id(self._default_mode)
        if default_mode not in self._valid_default_modes:
            raise ValueError(
                f"default_mode 指向的动作在 {DEFAULT_PET_STATE} 状态不可播放: "
                f"{default_mode}"
            )
        data["default_mode"] = default_mode
        data["press_mode"] = self._press_mode.currentText()
        idle_min = self._idle_min.value()
        idle_max = self._idle_max.value()
        single_min = self._single_min.value()
        single_max = self._single_max.value()
        _require_interval_order("空闲自动切换", idle_min, idle_max)
        _require_interval_order("单次插入", single_min, single_max)
        data["idle_autoswitch_interval_min_ms"] = idle_min
        data["idle_autoswitch_interval_max_ms"] = idle_max
        data["auto_idle_modes"] = _collect_checked(self._auto_idle_modes)
        data["single_insert_interval_min_ms"] = single_min
        data["single_insert_interval_max_ms"] = single_max
        data["single_insert_modes"] = _collect_checked(self._single_modes)
        data["startup"] = _collect_checked(self._startup)
        data["shutdown"] = _collect_checked(self._shutdown)
        _backup()
        SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
