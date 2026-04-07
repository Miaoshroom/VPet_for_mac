"""互动区域配置与行为解析"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PyQt6.QtCore import QPoint, QSize

Gesture = Literal["press", "click", "drag"]
BehaviorType = Literal["none", "move_window", "switch_mode", "press_mode"]

ROOT = Path(__file__).resolve().parent.parent
INTERACTION_MAP = ROOT / "config" / "interaction_map.json"


@dataclass(frozen=True)
class InteractionBehavior:
    type: BehaviorType
    mode: str | None = None


@dataclass(frozen=True)
class InteractionRegion:
    name: str
    row_start: int
    row_end: int
    col_start: int
    col_end: int
    press: InteractionBehavior | None = None
    click: InteractionBehavior | None = None
    drag: InteractionBehavior | None = None

    def matches(self, row: int, col: int) -> bool:
        return (
            self.row_start <= row <= self.row_end
            and self.col_start <= col <= self.col_end
        )

    def behavior_for(self, gesture: Gesture) -> InteractionBehavior | None:
        if gesture == "press":
            return self.press
        if gesture == "click":
            return self.click
        return self.drag


@dataclass(frozen=True)
class InteractionMap:
    rows: int
    cols: int
    default_press: InteractionBehavior
    default_click: InteractionBehavior
    default_drag: InteractionBehavior
    regions: tuple[InteractionRegion, ...]

    def resolve(self, gesture: Gesture, local_pos: QPoint, size: QSize) -> InteractionBehavior:
        row, col = self._cell_for_point(local_pos, size)
        return self.resolve_cell(gesture, row, col)

    def resolve_cell(self, gesture: Gesture, row: int, col: int) -> InteractionBehavior:
        for region in self.regions:
            if region.matches(row, col):
                behavior = region.behavior_for(gesture)
                if behavior is not None:
                    return behavior
        if gesture == "press":
            return self.default_press
        if gesture == "click":
            return self.default_click
        return self.default_drag

    def _cell_for_point(self, local_pos: QPoint, size: QSize) -> tuple[int, int]:
        width = max(1, size.width())
        height = max(1, size.height())
        x = min(max(local_pos.x(), 0), width - 1)
        y = min(max(local_pos.y(), 0), height - 1)
        col = min(self.cols - 1, x * self.cols // width)
        row = min(self.rows - 1, y * self.rows // height)
        return row, col


def load_interaction_map(mode_ids: set[str]) -> InteractionMap:
    data = json.loads(INTERACTION_MAP.read_text(encoding="utf-8"))
    rows = int(data["grid"]["rows"])
    cols = int(data["grid"]["cols"])
    if rows < 1 or cols < 1:
        raise RuntimeError("interaction_map 的 grid.rows 和 grid.cols 必须大于 0")

    default_press = _load_behavior(
        data["default_behaviors"].get("press", {"type": "none"}),
        mode_ids,
    )
    default_click = _load_behavior(data["default_behaviors"]["click"], mode_ids)
    default_drag = _load_behavior(data["default_behaviors"]["drag"], mode_ids)
    regions: list[InteractionRegion] = []

    for item in data["regions"]:
        row_start = int(item["row_start"])
        row_end = int(item["row_end"])
        col_start = int(item["col_start"])
        col_end = int(item["col_end"])
        if row_start < 0 or col_start < 0:
            raise RuntimeError("interaction_map 的 region 起始坐标不能小于 0")
        if row_end < row_start or col_end < col_start:
            raise RuntimeError("interaction_map 的 region 结束坐标不能小于起始坐标")
        if row_end >= rows or col_end >= cols:
            raise RuntimeError("interaction_map 的 region 超出了 grid 范围")
        regions.append(
            InteractionRegion(
                name=str(item["name"]),
                row_start=row_start,
                row_end=row_end,
                col_start=col_start,
                col_end=col_end,
                press=_load_optional_behavior(item.get("press"), mode_ids),
                click=_load_optional_behavior(item.get("click"), mode_ids),
                drag=_load_optional_behavior(item.get("drag"), mode_ids),
            )
        )

    return InteractionMap(
        rows=rows,
        cols=cols,
        default_press=default_press,
        default_click=default_click,
        default_drag=default_drag,
        regions=tuple(regions),
    )


def _load_optional_behavior(data: object, mode_ids: set[str]) -> InteractionBehavior | None:
    if data is None:
        return None
    return _load_behavior(data, mode_ids)


def _load_behavior(data: object, mode_ids: set[str]) -> InteractionBehavior:
    if not isinstance(data, dict):
        raise RuntimeError("interaction_map 的 behavior 必须是对象")
    behavior_type = str(data["type"])
    if behavior_type == "none":
        return InteractionBehavior(type="none")
    if behavior_type == "move_window":
        return InteractionBehavior(type="move_window")
    if behavior_type == "press_mode":
        mode = str(data["mode"])
        if mode not in mode_ids:
            raise RuntimeError(f"interaction_map 引用了未知模式: {mode}")
        return InteractionBehavior(type="press_mode", mode=mode)
    if behavior_type == "switch_mode":
        mode = str(data["mode"])
        if mode not in mode_ids:
            raise RuntimeError(f"interaction_map 引用了未知模式: {mode}")
        return InteractionBehavior(type="switch_mode", mode=mode)
    raise RuntimeError(f"interaction_map 的行为类型未知: {behavior_type}")
