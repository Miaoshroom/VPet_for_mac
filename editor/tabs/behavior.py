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

SETTINGS_PATH = config_path("action_settings.json")
MODES_PATH = config_path("modes.json")
BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / ".vpet_editor_backups"


def _backup() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = BACKUP_DIR / f"action_settings-{ts}.json"
    shutil.copy2(SETTINGS_PATH, dst)


def _read_mode_ids() -> list[str]:
    data = json.loads(MODES_PATH.read_text(encoding="utf-8"))
    return [a["id"] for a in data.get("actions", [])]


def _mode_ids_by_type(*types: str) -> list[str]:
    data = json.loads(MODES_PATH.read_text(encoding="utf-8"))
    return [a["id"] for a in data.get("actions", []) if a["type"] in types]


def _collect_checked(w: QListWidget) -> list[str]:
    result = []
    for i in range(w.count()):
        item = w.item(i)
        if item.checkState() == Qt.CheckState.Checked:
            result.append(item.text())
    return result


class BehaviorTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
        all_ids = _read_mode_ids()
        phased_loop_ids = _mode_ids_by_type("phased", "loop")
        phased_ids = _mode_ids_by_type("phased")
        single_ids = _mode_ids_by_type("single")

        # default_mode / press_mode
        self._default_mode.clear()
        self._default_mode.addItems(phased_loop_ids)
        self._default_mode.setCurrentText(settings.get("default_mode", ""))
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
        data["default_mode"] = self._default_mode.currentText()
        data["press_mode"] = self._press_mode.currentText()
        data["idle_autoswitch_interval_min_ms"] = self._idle_min.value()
        data["idle_autoswitch_interval_max_ms"] = self._idle_max.value()
        data["auto_idle_modes"] = _collect_checked(self._auto_idle_modes)
        data["single_insert_interval_min_ms"] = self._single_min.value()
        data["single_insert_interval_max_ms"] = self._single_max.value()
        data["single_insert_modes"] = _collect_checked(self._single_modes)
        data["startup"] = _collect_checked(self._startup)
        data["shutdown"] = _collect_checked(self._shutdown)
        _backup()
        SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
