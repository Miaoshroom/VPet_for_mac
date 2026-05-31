"""动作素材管理：扫描 assets/animations，预览动画和导入素材"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.app_paths import assets_dir, config_path
from core.loader import _load_action_specs
from core.playback.catalog import AnimationCatalog, ActionSpec
from core.playback.flipbook import FlipbookPlayer

ROLE = Qt.ItemDataRole.UserRole
NODE_ACTION = 0
NODE_STATE = 1
NODE_PHASE = 2
NODE_VARIANT = 3
NODE_LAYER = 4

ANIM_ROOT = assets_dir() / "animations"
MODES_PATH = config_path("modes.json")


class AssetsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._catalog: AnimationCatalog | None = None
        self._player = FlipbookPlayer(self)
        self._player.frame_changed.connect(self._on_frame)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # ---- 左侧目录树 ----
        self._tree = QTreeWidget(self)
        self._tree.setHeaderLabels(["素材目录", "信息"])
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.setColumnWidth(1, 120)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self._tree)

        # ---- 右侧 ----
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 8)

        preview_group = QGroupBox("预览", right)
        preview_layout = QVBoxLayout(preview_group)
        self._preview_label = QLabel(self)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(200)
        self._preview_label.setStyleSheet("background: #1a1a1a; border-radius: 4px;")
        preview_layout.addWidget(self._preview_label)
        right_layout.addWidget(preview_group)

        info_group = QGroupBox("素材信息", right)
        info_layout = QVBoxLayout(info_group)
        self._info_label = QLabel("选择左侧节点查看详情", self)
        self._info_label.setWordWrap(True)
        info_layout.addWidget(self._info_label)
        right_layout.addWidget(info_group)

        btn_refresh = QPushButton("刷新素材", right)
        btn_refresh.clicked.connect(self._reload)
        right_layout.addWidget(btn_refresh)

        right_layout.addStretch()
        splitter.addWidget(right)
        splitter.setSizes([480, 400])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._reload()

    def _reload(self) -> None:
        self._player.stop()
        self._preview_label.clear()
        self._tree.clear()
        try:
            specs = _load_action_specs()
        except Exception:
            specs = ()
        self._catalog = _build_catalog(specs)
        self._build_tree()

    def _build_tree(self) -> None:
        if not ANIM_ROOT.is_dir():
            return
        registered = _registered_ids()
        for action_dir in sorted(ANIM_ROOT.iterdir()):
            if action_dir.name.startswith(".") or not action_dir.is_dir():
                continue
            spec = _find_spec(action_dir.name)
            action_type = spec.type if spec else _infer_type(action_dir)
            registered_mark = "" if action_dir.name in registered else " [未注册]"
            action_item = QTreeWidgetItem(self._tree)
            action_item.setText(0, f"{action_dir.name}{registered_mark}")
            action_item.setText(1, action_type)
            action_item.setData(0, ROLE, {"node": NODE_ACTION, "action": action_dir.name, "type": action_type})
            action_item.setExpanded(False)
            for state_dir in sorted(action_dir.iterdir()):
                if state_dir.name.startswith(".") or not state_dir.is_dir():
                    continue
                state_item = QTreeWidgetItem(action_item)
                state_item.setText(0, state_dir.name)
                state_item.setData(0, ROLE, {"node": NODE_STATE, "action": action_dir.name, "state": state_dir.name})
                for phase_dir in sorted(state_dir.iterdir()):
                    if phase_dir.name.startswith(".") or not phase_dir.is_dir():
                        continue
                    phase_item = QTreeWidgetItem(state_item)
                    phase_item.setText(0, phase_dir.name)
                    phase_item.setData(0, ROLE, {
                        "node": NODE_PHASE,
                        "action": action_dir.name,
                        "state": state_dir.name,
                        "phase": phase_dir.name,
                    })
                    for variant_dir in sorted(phase_dir.iterdir()):
                        if variant_dir.name.startswith(".") or not variant_dir.is_dir():
                            continue
                        variant_item = QTreeWidgetItem(phase_item)
                        variant_item.setText(0, variant_dir.name)
                        variant_item.setData(0, ROLE, {
                            "node": NODE_VARIANT,
                            "action": action_dir.name,
                            "state": state_dir.name,
                            "phase": phase_dir.name,
                            "variant": variant_dir.name,
                        })
                        for layer_dir in sorted(variant_dir.iterdir()):
                            if layer_dir.name.startswith(".") or not layer_dir.is_dir():
                                continue
                            pngs = sorted(f for f in layer_dir.iterdir() if f.suffix.lower() == ".png")
                            layer_item = QTreeWidgetItem(variant_item)
                            layer_item.setText(0, layer_dir.name)
                            layer_item.setText(1, f"{len(pngs)} 帧")
                            layer_item.setData(0, ROLE, {
                                "node": NODE_LAYER,
                                "action": action_dir.name,
                                "state": state_dir.name,
                                "phase": phase_dir.name,
                                "variant": variant_dir.name,
                                "layer": layer_dir.name,
                            })

    def _on_selection_changed(self) -> None:
        self._player.stop()
        self._preview_label.clear()
        items = self._tree.selectedItems()
        if not items:
            return
        data = items[0].data(0, ROLE)
        if data is None:
            return
        node_type = data["node"]
        action_id = data["action"]

        # 不需要目录，直接用 action_id 拿 clip
        if node_type == NODE_ACTION:
            self._preview_action(action_id)
        elif node_type == NODE_STATE:
            self._preview_action(action_id, state=data["state"])
        elif node_type == NODE_PHASE:
            self._preview_phase(action_id, data["state"], data["phase"])
        elif node_type == NODE_VARIANT:
            self._preview_variant(action_id, data["state"], data["phase"], data["variant"])
        elif node_type == NODE_LAYER:
            self._show_layer_info(data)

    def _preview_action(self, action_id: str, state: str | None = None) -> None:
        if self._catalog is None:
            return
        states = self._catalog.material_states_for(action_id)
        if not states:
            self._info_label.setText("无可用状态素材")
            return
        use_state = state if state in states else states[0]
        try:
            clip = self._action_loop_clip(action_id, use_state)
        except Exception as e:
            self._info_label.setText(f"无法预览: {e}")
            return
        tag = " (兜底)" if use_state == "any" else ""
        self._info_label.setText(f"动作: {action_id}\n状态: {use_state}{tag}\n类型: {self._catalog.action_type(action_id)}")
        self._play_clip(clip)

    def _action_loop_clip(self, action_id: str, state: str):
        """取一个动作的 loop（或 single）clip，兼容 any 兜底状态"""
        if state != "any":
            return self._catalog.mode_for(action_id, state).loop
        # any 不走公开 API（mode_for 会 reject），直接拿 _state_data
        _, state_data = self._catalog._state_data(action_id, state)
        phase = "loop" if "loop" in state_data else next(iter(state_data))
        variants = self._catalog._playable_variants(state_data, phase)
        if not variants:
            raise KeyError(f"any 状态下 {phase} 无可播放变体")
        return self._catalog._clip_for_variant(
            state_data, phase, variants[0],
            action_id=action_id, source_state=state,
        )

    def _preview_phase(self, action_id: str, state: str, phase: str) -> None:
        if self._catalog is None:
            return
        try:
            _, state_data = self._catalog._state_data(action_id, state)
            variants = self._catalog._playable_variants(state_data, phase)
        except KeyError:
            self._info_label.setText(f"状态 {state} 不存在素材")
            return
        if not variants:
            self._info_label.setText(f"阶段 {phase} 无可播放变体")
            return
        clip = self._catalog._clip_for_variant(
            state_data, phase, variants[0],
            action_id=action_id, source_state=state,
        )
        tag = " (兜底)" if state == "any" else ""
        self._info_label.setText(f"动作: {action_id}\n状态: {state}{tag}\n阶段: {phase}\n变体: {variants[0]}")
        self._play_clip(clip)

    def _preview_variant(self, action_id: str, state: str, phase: str, variant: str) -> None:
        if self._catalog is None:
            return
        try:
            _, state_data = self._catalog._state_data(action_id, state)
            clip = self._catalog._clip_for_variant(state_data, phase, variant, action_id=action_id, source_state=state)
        except Exception as e:
            self._info_label.setText(f"无法预览: {e}")
            return
        frames = len(clip.frame_paths)
        self._info_label.setText(f"动作: {action_id}\n状态: {state}\n阶段: {phase}\n变体: {variant}\n帧数: {frames}")
        self._play_clip(clip)

    def _show_layer_info(self, data: dict) -> None:
        layer_dir = ANIM_ROOT / data["action"] / data["state"] / data["phase"] / data["variant"] / data["layer"]
        pngs = sorted(f for f in layer_dir.iterdir() if f.suffix.lower() == ".png")
        size_str = ""
        if pngs:
            pix = QPixmap(str(pngs[0]))
            size_str = f"{pix.width()}x{pix.height()}"
        self._info_label.setText(
            f"动作: {data['action']}\n"
            f"状态: {data['state']}\n"
            f"阶段: {data['phase']}\n"
            f"变体: {data['variant']}\n"
            f"图层: {data['layer']}\n"
            f"帧数: {len(pngs)}\n"
            f"尺寸: {size_str}"
        )

    def _play_clip(self, clip) -> None:
        self._player.stop()
        self._player.play(clip, loop=True)

    def _on_frame(self, pix: QPixmap) -> None:
        scaled = pix.scaled(
            self._preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(scaled)

    def _import_assets(self) -> None:
        action_id, ok = _prompt_text(self, "导入素材", "输入动作 ID（对应 assets/animations 下的目录名）:")
        if not ok or not action_id.strip():
            return
        action_id = action_id.strip()
        state, ok = _prompt_text(self, "导入素材", "输入状态名（happy / normal / poor_condition / ill / any）:", "normal")
        if not ok or not state.strip():
            return
        state = state.strip()
        phase, ok = _prompt_text(self, "导入素材", "输入阶段名（loop / start / end / single）:", "loop")
        if not ok or not phase.strip():
            return
        phase = phase.strip()
        variant, ok = _prompt_text(self, "导入素材", "输入变体编号（两位数字，如 01）:", "01")
        if not ok or not variant.strip():
            return
        variant = variant.strip()
        layer, ok = _prompt_text(self, "导入素材", "输入图层名（main / back / front）:", "main")
        if not ok or not layer.strip():
            return
        layer = layer.strip()

        files, _ = QFileDialog.getOpenFileNames(
            self, "选择 PNG 序列帧", "",
            "PNG 图片 (*.png);;所有文件 (*)",
        )
        if not files:
            return

        dest_dir = ANIM_ROOT / action_id / state / phase / variant / layer
        dest_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for src in files:
            dst = dest_dir / Path(src).name
            if not dst.exists():
                shutil.copy2(src, dst)
                copied += 1
        self._reload()
        QMessageBox.information(self, "导入完成", f"已复制 {copied} 个文件到 {dest_dir}")

    def save(self) -> None:
        pass  # assets tab 是只读扫描，无需保存


def _build_catalog(specs: tuple[ActionSpec, ...]) -> AnimationCatalog:
    from core.loader import _visible_dirs, _png_files
    from core.playback.catalog import (
        LAYERS, MATERIAL_STATES, PHASES, CatalogClips, is_valid_variant_name,
    )
    from core.playback.clip import Clip

    root = ANIM_ROOT
    if not root.is_dir():
        return AnimationCatalog({}, {})

    catalog: CatalogClips = {}
    for action_dir in _visible_dirs(root):
        action_id = action_dir.name
        action_data = catalog.setdefault(action_id, {})
        for state_dir in _visible_dirs(action_dir):
            state = state_dir.name
            if state not in MATERIAL_STATES:
                continue  # 跳过不合法状态
            state_data = action_data.setdefault(state, {})
            for phase_dir in _visible_dirs(state_dir):
                phase = phase_dir.name
                if phase not in PHASES:
                    continue
                phase_data = state_data.setdefault(phase, {})
                for variant_dir in _visible_dirs(phase_dir):
                    variant = variant_dir.name
                    if not is_valid_variant_name(variant):
                        continue
                    variant_data = phase_data.setdefault(variant, {})
                    for layer_dir in _visible_dirs(variant_dir):
                        layer = layer_dir.name
                        if layer not in LAYERS or layer in variant_data:
                            continue
                        png_paths = _png_files(layer_dir)
                        if not png_paths:
                            continue  # 宽容：跳过空图层
                        variant_data[layer] = Clip.from_paths(png_paths)

    spec_map = {spec.id: spec for spec in specs}
    return AnimationCatalog(catalog, spec_map)


def _registered_ids() -> set[str]:
    try:
        data = json.loads(MODES_PATH.read_text(encoding="utf-8"))
        return {a["id"] for a in data.get("actions", [])}
    except Exception:
        return set()


def _find_spec(action_id: str) -> ActionSpec | None:
    try:
        for spec in _load_action_specs():
            if spec.id == action_id:
                return spec
    except Exception:
        pass
    return None


def _infer_type(action_dir: Path) -> str:
    phases: set[str] = set()
    for state_dir in action_dir.iterdir():
        if state_dir.name.startswith(".") or not state_dir.is_dir():
            continue
        for phase_dir in state_dir.iterdir():
            if not phase_dir.name.startswith(".") and phase_dir.is_dir():
                phases.add(phase_dir.name)
    if {"start", "loop", "end"} <= phases:
        return "phased"
    if "single" in phases:
        return "single"
    if "loop" in phases:
        return "loop"
    return "未知"


def _prompt_text(parent: QWidget, title: str, label: str, default: str = "") -> tuple[str, bool]:
    from PyQt6.QtWidgets import QInputDialog
    text, ok = QInputDialog.getText(parent, title, label, text=default)
    return text, ok
