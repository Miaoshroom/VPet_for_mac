"""将零散 PNG → 标准命名 → 输出到素材目录"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.app_paths import assets_dir

ANIM_ROOT = assets_dir() / "animations"
ROLE = Qt.ItemDataRole.UserRole
FRAME_FILE_RE = re.compile(r"^.*_(\d+)_(\d+)\.png$")

NODE_ACTION = 0
NODE_STATE = 1
NODE_PHASE = 2
NODE_VARIANT = 3
NODE_LAYER = 4

STATES = ("happy", "normal", "poor_condition", "ill", "any")
PHASES = ("loop", "start", "end", "single")
LAYERS = ("main", "back", "front")


class AssetPrepTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # ---- 左侧：树 + 创建按钮 ----
        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._tree = QTreeWidget(self)
        self._tree.setHeaderLabels(["素材目录", ""])
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.setColumnWidth(1, 80)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._tree)

        btn_bar = QHBoxLayout()
        self._btn_state = QPushButton("新建状态", self)
        self._btn_phase = QPushButton("新建阶段", self)
        self._btn_variant = QPushButton("新建变体", self)
        self._btn_layer = QPushButton("新建图层", self)
        self._btn_state.clicked.connect(self._create_state)
        self._btn_phase.clicked.connect(self._create_phase)
        self._btn_variant.clicked.connect(self._create_variant)
        self._btn_layer.clicked.connect(self._create_layer)
        for b in (self._btn_state, self._btn_phase, self._btn_variant, self._btn_layer):
            b.setEnabled(False)
        btn_bar.addWidget(self._btn_state)
        btn_bar.addWidget(self._btn_phase)
        btn_bar.addWidget(self._btn_variant)
        btn_bar.addWidget(self._btn_layer)
        btn_bar.addStretch()
        left_layout.addLayout(btn_bar)

        btn_new_action = QPushButton("新建动作...", self)
        btn_new_action.clicked.connect(self._create_action)
        left_layout.addWidget(btn_new_action)

        self._btn_delete = QPushButton("删除选中", self)
        self._btn_delete.setEnabled(False)
        self._btn_delete.clicked.connect(self._delete_selected_node)
        left_layout.addWidget(self._btn_delete)

        splitter.addWidget(left)

        # ---- 右侧：配置 + 帧列表 + 输出 ----
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 8)

        # 当前路径
        self._path_label = QLabel("请在左侧选择或创建图层节点", self)
        self._path_label.setWordWrap(True)
        mono = QFont("Menlo, monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._path_label.setFont(mono)
        right_layout.addWidget(self._path_label)

        # 配置行
        cfg = QHBoxLayout()
        cfg.addWidget(QLabel("前缀:", self))
        self._prefix = QLineEdit(self)
        self._prefix.setPlaceholderText("(空)")
        self._prefix.setMaximumWidth(100)
        self._prefix.textChanged.connect(self._update_preview)
        cfg.addWidget(self._prefix)
        cfg.addWidget(QLabel("起始序号:", self))
        self._start_index = QSpinBox(self)
        self._start_index.setRange(0, 9999)
        self._start_index.valueChanged.connect(self._update_preview)
        cfg.addWidget(self._start_index)
        cfg.addWidget(QLabel("默认延时:", self))
        self._default_delay = QSpinBox(self)
        self._default_delay.setRange(1, 99999)
        self._default_delay.setValue(125)
        self._default_delay.setSuffix(" ms")
        self._default_delay.valueChanged.connect(self._on_default_delay_changed)
        cfg.addWidget(self._default_delay)
        cfg.addStretch()
        right_layout.addLayout(cfg)

        # 帧列表
        frame_group = QGroupBox("帧序列", self)
        frame_layout = QVBoxLayout(frame_group)
        desc = QLabel("拖拽 PNG 图片到此窗口，自动追加到列表末尾。选中行可上移/下移。", self)
        desc.setStyleSheet("color: #888;")
        frame_layout.addWidget(desc)

        self._frame_table = QTableWidget(0, 5, self)
        self._frame_table.setHorizontalHeaderLabels(["序号", "源文件", "目标文件名", "延时", ""])
        self._frame_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._frame_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._frame_table.setColumnWidth(0, 50)
        self._frame_table.setColumnWidth(3, 80)
        self._frame_table.setColumnWidth(4, 40)
        self._frame_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._frame_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        frame_layout.addWidget(self._frame_table)

        btn_row = QHBoxLayout()
        btn_up = QPushButton("上移", self)
        btn_down = QPushButton("下移", self)
        btn_del = QPushButton("删除选中", self)
        btn_up.clicked.connect(self._move_up)
        btn_down.clicked.connect(self._move_down)
        btn_del.clicked.connect(self._delete_selected)
        btn_row.addWidget(btn_up)
        btn_row.addWidget(btn_down)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        frame_layout.addLayout(btn_row)
        right_layout.addWidget(frame_group)

        # 输出
        self._btn_output = QPushButton("输出到目标目录", self)
        self._btn_output.setEnabled(False)
        self._btn_output.clicked.connect(self._output)
        right_layout.addWidget(self._btn_output)

        right_layout.addStretch()
        splitter.addWidget(right)
        splitter.setSizes([400, 600])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._build_tree()

    # ===== 树 =====

    def _build_tree(self) -> None:
        self._tree.clear()
        if not ANIM_ROOT.is_dir():
            return
        for action_dir in sorted(ANIM_ROOT.iterdir()):
            if action_dir.name.startswith(".") or not action_dir.is_dir():
                continue
            a_item = QTreeWidgetItem(self._tree)
            a_item.setText(0, action_dir.name)
            a_item.setData(0, ROLE, {"node": NODE_ACTION, "action": action_dir.name, "path": str(action_dir)})
            for state_dir in sorted(action_dir.iterdir()):
                if state_dir.name.startswith(".") or not state_dir.is_dir():
                    continue
                s_item = QTreeWidgetItem(a_item)
                s_item.setText(0, state_dir.name)
                s_item.setData(0, ROLE, {"node": NODE_STATE, "action": action_dir.name, "state": state_dir.name, "path": str(state_dir)})
                for phase_dir in sorted(state_dir.iterdir()):
                    if phase_dir.name.startswith(".") or not phase_dir.is_dir():
                        continue
                    p_item = QTreeWidgetItem(s_item)
                    p_item.setText(0, phase_dir.name)
                    p_item.setData(0, ROLE, {"node": NODE_PHASE, "action": action_dir.name, "state": state_dir.name, "phase": phase_dir.name, "path": str(phase_dir)})
                    for variant_dir in sorted(phase_dir.iterdir()):
                        if variant_dir.name.startswith(".") or not variant_dir.is_dir():
                            continue
                        v_item = QTreeWidgetItem(p_item)
                        v_item.setText(0, variant_dir.name)
                        v_item.setData(0, ROLE, {"node": NODE_VARIANT, "action": action_dir.name, "state": state_dir.name, "phase": phase_dir.name, "variant": variant_dir.name, "path": str(variant_dir)})
                        for layer_dir in sorted(variant_dir.iterdir()):
                            if layer_dir.name.startswith(".") or not layer_dir.is_dir():
                                continue
                            pngs = [f for f in layer_dir.iterdir() if f.suffix.lower() == ".png" and not f.name.startswith(".")]
                            l_item = QTreeWidgetItem(v_item)
                            l_item.setText(0, layer_dir.name)
                            l_item.setText(1, str(len(pngs)))
                            l_item.setData(0, ROLE, {"node": NODE_LAYER, "action": action_dir.name, "state": state_dir.name, "phase": phase_dir.name, "variant": variant_dir.name, "layer": layer_dir.name, "path": str(layer_dir)})

    def _refresh_tree(self) -> None:
        expanded = self._collect_expanded_paths()
        selected_path = self._selected_path()
        self._build_tree()
        self._restore_expanded_paths(expanded)
        self._restore_selection(selected_path)

    @staticmethod
    def _item_path(item: QTreeWidgetItem) -> str:
        parts = []
        while item:
            parts.append(item.text(0))
            item = item.parent()
        return "/".join(reversed(parts))

    def _collect_expanded_paths(self) -> set[str]:
        expanded: set[str] = set()
        def walk(item: QTreeWidgetItem) -> None:
            if item.isExpanded():
                expanded.add(self._item_path(item))
            for i in range(item.childCount()):
                walk(item.child(i))
        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))
        return expanded

    def _selected_path(self) -> str | None:
        items = self._tree.selectedItems()
        if not items:
            return None
        return self._item_path(items[0])

    def _restore_expanded_paths(self, paths: set[str]) -> None:
        def walk(item: QTreeWidgetItem) -> None:
            if self._item_path(item) in paths:
                item.setExpanded(True)
            for i in range(item.childCount()):
                walk(item.child(i))
        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))

    def _restore_selection(self, path: str | None) -> None:
        if path is None:
            return
        def walk(item: QTreeWidgetItem) -> bool:
            if self._item_path(item) == path:
                self._tree.setCurrentItem(item)
                return True
            for i in range(item.childCount()):
                if walk(item.child(i)):
                    return True
            return False
        for i in range(self._tree.topLevelItemCount()):
            if walk(self._tree.topLevelItem(i)):
                return

    def _on_selection_changed(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            self._update_button_states(None)
            return
        data = items[0].data(0, ROLE)
        if data is None:
            self._update_button_states(None)
            return
        self._update_button_states(data)
        node_type = data["node"]
        if node_type == NODE_LAYER:
            self._load_layer(Path(data["path"]))
        else:
            self._frame_table.setRowCount(0)
            self._btn_output.setEnabled(False)
            path_parts = []
            item = items[0]
            while item:
                path_parts.append(item.text(0))
                item = item.parent()
            self._path_label.setText(" / ".join(reversed(path_parts)))

    def _update_button_states(self, data: dict | None) -> None:
        if data is None:
            for b in (self._btn_state, self._btn_phase, self._btn_variant, self._btn_layer):
                b.setEnabled(False)
            self._btn_delete.setEnabled(False)
            return
        node = data["node"]
        self._btn_state.setEnabled(node == NODE_ACTION)
        self._btn_phase.setEnabled(node == NODE_STATE)
        self._btn_variant.setEnabled(node == NODE_PHASE)
        self._btn_layer.setEnabled(node == NODE_VARIANT)
        self._btn_delete.setEnabled(True)

    # ===== 创建 / 删除节点 =====

    def _create_action(self) -> None:
        name, ok = QInputDialog.getText(self, "新建动作", "输入动作 ID（小写英文/数字/下划线）:")
        if not ok or not name.strip():
            return
        name = name.strip()
        path = ANIM_ROOT / name
        if path.exists():
            QMessageBox.warning(self, "已存在", f"动作 \"{name}\" 已存在")
            return
        path.mkdir(parents=True)
        self._refresh_tree()

    def _create_state(self) -> None:
        data = self._selected_data()
        if data is None or data["node"] != NODE_ACTION:
            return
        state, ok = QInputDialog.getItem(self, "新建状态", "选择状态:", STATES, 1, False)
        if not ok:
            return
        path = Path(data["path"]) / state
        if path.exists():
            QMessageBox.warning(self, "已存在", f"状态 \"{state}\" 已存在")
            return
        path.mkdir(parents=True)
        self._refresh_tree()

    def _create_phase(self) -> None:
        data = self._selected_data()
        if data is None or data["node"] != NODE_STATE:
            return
        phase, ok = QInputDialog.getItem(self, "新建阶段", "选择阶段:", PHASES, 0, False)
        if not ok:
            return
        path = Path(data["path"]) / phase
        if path.exists():
            QMessageBox.warning(self, "已存在", f"阶段 \"{phase}\" 已存在")
            return
        path.mkdir(parents=True)
        self._refresh_tree()

    def _create_variant(self) -> None:
        data = self._selected_data()
        if data is None or data["node"] != NODE_PHASE:
            return
        variant, ok = QInputDialog.getText(self, "新建变体", "输入变体编号（两位数字，如 01）:", text="01")
        if not ok or not variant.strip():
            return
        variant = variant.strip()
        if not re.fullmatch(r"\d{2}", variant):
            QMessageBox.warning(self, "格式错误", "变体必须是两位数字，如 01、02")
            return
        path = Path(data["path"]) / variant
        if path.exists():
            QMessageBox.warning(self, "已存在", f"变体 \"{variant}\" 已存在")
            return
        path.mkdir(parents=True)
        self._refresh_tree()

    def _create_layer(self) -> None:
        data = self._selected_data()
        if data is None or data["node"] != NODE_VARIANT:
            return
        layer, ok = QInputDialog.getItem(self, "新建图层", "选择图层:", LAYERS, 0, False)
        if not ok:
            return
        path = Path(data["path"]) / layer
        if path.exists():
            QMessageBox.warning(self, "已存在", f"图层 \"{layer}\" 已存在")
            return
        path.mkdir(parents=True)
        self._refresh_tree()

    def _delete_selected_node(self) -> None:
        data = self._selected_data()
        if data is None:
            return
        target = Path(data["path"])
        node_name = self._item_path(self._tree.selectedItems()[0])
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 \"{node_name}\" 及其所有内容吗？\n\n{target}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        shutil.rmtree(target)
        self._frame_table.setRowCount(0)
        self._btn_output.setEnabled(False)
        self._path_label.setText("请在左侧选择或创建图层节点")
        self._refresh_tree()

    def _selected_data(self) -> dict | None:
        items = self._tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, ROLE)

    # ===== 帧列表加载 =====

    def _load_layer(self, layer_path: Path) -> None:
        self._frame_table.setRowCount(0)

        existing = self._scan_existing(layer_path)
        max_idx = max((idx for idx, _, _ in existing), default=-1)
        self._start_index.blockSignals(True)
        self._start_index.setValue(max_idx + 1)
        self._start_index.blockSignals(False)
        self._prefix.blockSignals(True)
        self._prefix.setText("")
        self._prefix.blockSignals(False)

        for idx, delay, fpath in existing:
            row = self._frame_table.rowCount()
            self._frame_table.insertRow(row)
            self._add_frame_row(row, str(fpath), delay, existing=True)

        rel = layer_path.relative_to(ANIM_ROOT)
        self._path_label.setText(f"assets/animations/{rel}")
        self._btn_output.setEnabled(True)

    @staticmethod
    def _scan_existing(dir_path: Path) -> list[tuple[int, int, Path]]:
        result = []
        for f in sorted(dir_path.iterdir()):
            if not f.is_file() or f.suffix.lower() != ".png" or f.name.startswith("."):
                continue
            m = FRAME_FILE_RE.fullmatch(f.name)
            if m:
                result.append((int(m.group(1)), int(m.group(2)), f))
        return result

    def _add_frame_row(self, row: int, src_key: str, delay: int, *, existing: bool = False) -> None:
        """统一添加一行帧。existing=True 表示已有磁盘文件，灰色底 + 标记。"""
        seq_item = QTableWidgetItem("")
        seq_item.setData(ROLE, src_key)
        self._frame_table.setItem(row, 0, seq_item)
        src_name = Path(src_key).name if existing else Path(src_key).name
        src_mark = f" (已有)" if existing else ""
        self._frame_table.setItem(row, 1, QTableWidgetItem(src_name + src_mark))
        self._frame_table.setItem(row, 2, QTableWidgetItem(""))
        self._frame_table.setItem(row, 3, QTableWidgetItem(str(delay)))
        if existing:
            for col in range(5):
                item = self._frame_table.item(row, col)
                if item is not None:
                    item.setBackground(Qt.GlobalColor.darkGray)
        btn = QPushButton("✕", self)
        btn.setFixedSize(28, 24)
        btn.clicked.connect(self._on_delete_btn)
        self._frame_table.setCellWidget(row, 4, btn)
        self._update_preview()

    def _is_existing_row(self, row: int) -> bool:
        """通过灰色背景判断是否是已有磁盘帧"""
        item = self._frame_table.item(row, 0)
        return item is not None and item.background().color() == Qt.GlobalColor.darkGray

    def _src_for_row(self, row: int) -> Path | None:
        item = self._frame_table.item(row, 0)
        data = item.data(ROLE) if item is not None else None
        return Path(data) if data else None

    def _row_is_new(self, row: int) -> bool:
        return not self._is_existing_row(row)

    def _on_delete_btn(self) -> None:
        btn = self.sender()
        for row in range(self._frame_table.rowCount()):
            if self._frame_table.cellWidget(row, 4) is btn:
                self._delete_row(row)
                return

    def _delete_row(self, row: int) -> None:
        """删除一行帧。已有帧同时删除磁盘文件。"""
        if self._is_existing_row(row):
            src = self._src_for_row(row)
            if src is not None and src.is_file():
                src.unlink()
        self._frame_table.removeRow(row)
        self._update_preview()

    def _delete_selected(self) -> None:
        rows = sorted({idx.row() for idx in self._frame_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self._delete_row(row)

    def _move_up(self) -> None:
        rows = sorted({idx.row() for idx in self._frame_table.selectedIndexes()})
        if not rows or rows[0] == 0:
            return
        for row in rows:
            if row > 0:
                self._swap_rows(row, row - 1)
                self._frame_table.selectRow(row - 1)
        self._update_preview()

    def _move_down(self) -> None:
        rows = sorted({idx.row() for idx in self._frame_table.selectedIndexes()}, reverse=True)
        if not rows or rows[-1] >= self._frame_table.rowCount() - 1:
            return
        for row in rows:
            if row < self._frame_table.rowCount() - 1:
                self._swap_rows(row, row + 1)
                self._frame_table.selectRow(row + 1)
        self._update_preview()

    def _swap_rows(self, a: int, b: int) -> None:
        """只交换数据列 (0-3)，按钮留在原位。_on_delete_btn 通过 sender() 反查行号，不受影响。"""
        for col in range(4):
            item_a = self._frame_table.takeItem(a, col)
            item_b = self._frame_table.takeItem(b, col)
            self._frame_table.setItem(a, col, item_b)
            self._frame_table.setItem(b, col, item_a)

    # ===== 预览更新 =====

    def _update_preview(self) -> None:
        prefix = self._prefix.text()
        start = self._start_index.value()
        for row in range(self._frame_table.rowCount()):
            seq = start + row
            delay_item = self._frame_table.item(row, 3)
            try:
                delay = int(delay_item.text()) if delay_item and delay_item.text() else self._default_delay.value()
            except (ValueError, AttributeError):
                delay = self._default_delay.value()
            name = f"{prefix}_{seq:03d}_{delay}.png" if prefix else f"_{seq:03d}_{delay}.png"
            self._frame_table.item(row, 0).setText(str(seq).zfill(3))
            dst_item = self._frame_table.item(row, 2)
            if dst_item:
                dst_item.setText(name)

    def _on_default_delay_changed(self) -> None:
        delay = self._default_delay.value()
        for row in range(self._frame_table.rowCount()):
            if self._row_is_new(row):
                self._frame_table.item(row, 3).setText(str(delay))
        self._update_preview()

    # ===== 拖放 =====

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if not urls:
            super().dropEvent(event)
            return
        paths = [Path(url.toLocalFile()) for url in urls if Path(url.toLocalFile()).suffix.lower() == ".png"]
        if not paths:
            return
        event.acceptProposedAction()
        delay = self._default_delay.value()
        for p in paths:
            row = self._frame_table.rowCount()
            self._frame_table.insertRow(row)
            self._add_frame_row(row, str(p), delay, existing=False)
        self._update_preview()

    # ===== 输出 =====

    def _output(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, ROLE)
        if data is None or data["node"] != NODE_LAYER:
            return
        target_dir = Path(data["path"])

        self._update_preview()
        has_work = False
        for row in range(self._frame_table.rowCount()):
            src = self._src_for_row(row)
            if src is None:
                continue
            dst_name = self._frame_table.item(row, 2).text()
            dst = target_dir / dst_name

            if self._is_existing_row(row):
                if src.resolve() == dst.resolve():
                    continue
                if src.is_file() and src.parent == target_dir:
                    src.rename(dst)
                else:
                    if dst.exists():
                        action = _conflict_dialog(self, dst_name)
                        if action == "skip":
                            continue
                        elif action == "rename":
                            dst = _find_available_name(target_dir, dst_name)
                    shutil.copy2(src, dst)
                has_work = True
            else:
                if dst.exists():
                    if src.resolve() == dst.resolve():
                        continue
                    action = _conflict_dialog(self, dst_name)
                    if action == "skip":
                        continue
                    elif action == "rename":
                        dst = _find_available_name(target_dir, dst_name)
                shutil.copy2(src, dst)
                has_work = True

        self._refresh_tree()
        self._load_layer(target_dir)
        if has_work:
            QMessageBox.information(self, "完成", f"已输出到 {target_dir}")
        else:
            QMessageBox.information(self, "完成", "所有帧已是最新状态，无需操作。")


def _conflict_dialog(parent: QWidget, name: str) -> str:
    box = QMessageBox(parent)
    box.setWindowTitle("文件冲突")
    box.setText(f"目标文件 \"{name}\" 已存在。")
    box.setInformativeText("请选择处理方式：")
    btn_overwrite = box.addButton("覆盖", QMessageBox.ButtonRole.AcceptRole)
    btn_skip = box.addButton("跳过", QMessageBox.ButtonRole.RejectRole)
    btn_rename = box.addButton("自动改名", QMessageBox.ButtonRole.ActionRole)
    box.setDefaultButton(btn_rename)
    box.exec()
    clicked = box.clickedButton()
    if clicked is btn_skip:
        return "skip"
    elif clicked is btn_overwrite:
        return "overwrite"
    return "rename"


def _find_available_name(target_dir: Path, name: str) -> Path:
    stem, ext = os.path.splitext(name)
    candidate = target_dir / name
    n = 1
    while candidate.exists():
        candidate = target_dir / f"{stem}_{n}{ext}"
        n += 1
    return candidate
