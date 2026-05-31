"""插件开关：编辑 config/plugin_loader.json"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHeaderView,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.app_paths import config_path

LOADER_PATH = config_path("plugin_loader.json")
BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / ".vpet_editor_backups"
PLUGINS_ROOT = Path(__file__).resolve().parent.parent.parent / "plugins"
ROLE_PLUGIN_ID = Qt.ItemDataRole.UserRole
MENU_TITLE_RE = re.compile(r"MENU_TITLE\s*=\s*[\"']([^\"']+)[\"']")


@dataclass(frozen=True)
class PluginInfo:
    plugin_id: str
    title: str
    source: str
    missing: bool = False


def _backup() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = BACKUP_DIR / f"plugin_loader-{ts}.json"
    shutil.copy2(LOADER_PATH, dst)


def _read_enabled_plugins() -> list[str]:
    data = json.loads(LOADER_PATH.read_text(encoding="utf-8"))
    return [str(name) for name in data.get("plugins", [])]


def _discover_plugins() -> dict[str, PluginInfo]:
    plugins: dict[str, PluginInfo] = {}
    if not PLUGINS_ROOT.is_dir():
        return plugins

    for path in sorted(PLUGINS_ROOT.iterdir()):
        if path.name.startswith(".") or path.name.startswith("__"):
            continue
        if path.is_file() and path.suffix == ".py":
            plugin_id = path.stem
            plugins[plugin_id] = PluginInfo(
                plugin_id=plugin_id,
                title=_read_menu_title(path) or plugin_id,
                source=f"plugins/{path.name}",
            )
        elif path.is_dir() and (path / "plugin.py").is_file():
            plugin_id = path.name
            plugin_path = path / "plugin.py"
            plugins[plugin_id] = PluginInfo(
                plugin_id=plugin_id,
                title=_read_menu_title(plugin_path) or plugin_id,
                source=f"plugins/{path.name}/plugin.py",
            )
    return plugins


def _ordered_plugins(enabled: list[str], discovered: dict[str, PluginInfo]) -> list[PluginInfo]:
    ordered: list[PluginInfo] = []
    seen: set[str] = set()
    for plugin_id in enabled:
        if plugin_id in seen:
            continue
        info = discovered.get(plugin_id)
        if info is None:
            info = PluginInfo(plugin_id=plugin_id, title=plugin_id, source="未找到插件文件", missing=True)
        ordered.append(info)
        seen.add(plugin_id)
    for plugin_id in sorted(discovered):
        if plugin_id not in seen:
            ordered.append(discovered[plugin_id])
    return ordered


def _read_menu_title(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = MENU_TITLE_RE.search(text)
    return match.group(1) if match is not None else None


class PluginsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._table = QTableWidget(0, 4, self)
        self._table.setHorizontalHeaderLabels(["启用", "插件 ID", "名称", "来源"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 64)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        btn_refresh = QPushButton("刷新插件", self)
        btn_refresh.clicked.connect(self._load)
        btn_bar = QHBoxLayout()
        btn_bar.addWidget(btn_refresh)
        btn_bar.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(btn_bar)
        layout.addWidget(self._table)
        self._load()

    def _load(self) -> None:
        enabled = _read_enabled_plugins()
        enabled_set = set(enabled)
        plugins = _ordered_plugins(enabled, _discover_plugins())

        self._table.setRowCount(0)
        for info in plugins:
            row = self._table.rowCount()
            self._table.insertRow(row)

            enabled_item = QTableWidgetItem("")
            enabled_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            enabled_item.setCheckState(
                Qt.CheckState.Checked if info.plugin_id in enabled_set else Qt.CheckState.Unchecked
            )
            enabled_item.setData(ROLE_PLUGIN_ID, info.plugin_id)
            self._table.setItem(row, 0, enabled_item)

            id_item = QTableWidgetItem(info.plugin_id)
            title_item = QTableWidgetItem(info.title)
            source_item = QTableWidgetItem(info.source)
            for item in (id_item, title_item, source_item):
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if info.missing:
                for item in (enabled_item, id_item, title_item, source_item):
                    item.setBackground(Qt.GlobalColor.darkGray)
            self._table.setItem(row, 1, id_item)
            self._table.setItem(row, 2, title_item)
            self._table.setItem(row, 3, source_item)

    def save(self) -> None:
        enabled: list[str] = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            plugin_id = item.data(ROLE_PLUGIN_ID)
            if plugin_id is not None:
                enabled.append(str(plugin_id))

        data = json.loads(LOADER_PATH.read_text(encoding="utf-8"))
        data["plugins"] = enabled
        _backup()
        LOADER_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
