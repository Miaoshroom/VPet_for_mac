"""动作注册管理：编辑 config/modes.json"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtWidgets import (
    QComboBox,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from core.app_paths import config_path

MODES_PATH = config_path("modes.json")
BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / ".vpet_editor_backups"
ACTION_TYPES = ("loop", "phased", "single")


def _backup() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = BACKUP_DIR / f"modes-{ts}.json"
    shutil.copy2(MODES_PATH, dst)


class ActionsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._table = QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels(["动作 ID", "标题", "类型"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        btn_add = QPushButton("添加", self)
        btn_del = QPushButton("删除", self)
        btn_up = QPushButton("上移", self)
        btn_down = QPushButton("下移", self)
        btn_add.clicked.connect(self._add_row)
        btn_del.clicked.connect(self._delete_row)
        btn_up.clicked.connect(self._move_up)
        btn_down.clicked.connect(self._move_down)

        btn_bar = QHBoxLayout()
        btn_bar.addWidget(btn_add)
        btn_bar.addWidget(btn_del)
        btn_bar.addWidget(btn_up)
        btn_bar.addWidget(btn_down)
        btn_bar.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(btn_bar)
        layout.addWidget(self._table)
        self._load()

    def _load(self) -> None:
        self._table.setRowCount(0)
        data = json.loads(MODES_PATH.read_text(encoding="utf-8"))
        for action in data.get("actions", []):
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(action["id"]))
            self._table.setItem(row, 1, QTableWidgetItem(action["title"]))
            combo = QComboBox(self)
            combo.addItems(ACTION_TYPES)
            combo.setCurrentText(action["type"])
            self._table.setCellWidget(row, 2, combo)

    def _add_row(self) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(""))
        self._table.setItem(row, 1, QTableWidgetItem(""))
        combo = QComboBox(self)
        combo.addItems(ACTION_TYPES)
        combo.setCurrentText("loop")
        self._table.setCellWidget(row, 2, combo)

    def _delete_row(self) -> None:
        for row in sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True):
            self._table.removeRow(row)

    def _move_up(self) -> None:
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()})
        if not rows or rows[0] == 0:
            return
        for row in rows:
            self._swap_rows(row, row - 1)
            self._table.selectRow(row - 1)

    def _move_down(self) -> None:
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True)
        if not rows or rows[-1] >= self._table.rowCount() - 1:
            return
        for row in rows:
            self._swap_rows(row, row + 1)
            self._table.selectRow(row + 1)

    def _swap_rows(self, a: int, b: int) -> None:
        for col in range(2):
            item_a = self._table.takeItem(a, col)
            item_b = self._table.takeItem(b, col)
            self._table.setItem(a, col, item_b)
            self._table.setItem(b, col, item_a)
        combo_a = self._table.cellWidget(a, 2)
        combo_b = self._table.cellWidget(b, 2)
        type_a = combo_a.currentText() if combo_a else "loop"
        type_b = combo_b.currentText() if combo_b else "loop"
        self._table.removeCellWidget(a, 2)
        self._table.removeCellWidget(b, 2)
        new_a = QComboBox(self); new_a.addItems(ACTION_TYPES); new_a.setCurrentText(type_b)
        new_b = QComboBox(self); new_b.addItems(ACTION_TYPES); new_b.setCurrentText(type_a)
        self._table.setCellWidget(a, 2, new_a)
        self._table.setCellWidget(b, 2, new_b)

    def _collect(self) -> list[dict]:
        actions = []
        seen: set[str] = set()
        for row in range(self._table.rowCount()):
            id_item = self._table.item(row, 0)
            title_item = self._table.item(row, 1)
            combo = self._table.cellWidget(row, 2)
            action_id = (id_item.text() if id_item else "").strip()
            if not action_id:
                raise ValueError(f"第 {row + 1} 行动作 ID 不能为空")
            if action_id in seen:
                raise ValueError(f"动作 ID 重复: {action_id}")
            seen.add(action_id)
            actions.append({
                "id": action_id,
                "title": (title_item.text() if title_item else "").strip(),
                "type": combo.currentText() if combo else "loop",
            })
        return actions

    def save(self) -> None:
        actions = self._collect()
        _backup()
        data = json.loads(MODES_PATH.read_text(encoding="utf-8"))
        data["actions"] = actions
        MODES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
