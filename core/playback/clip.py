"""动画片段与帧加载"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPixmap

_FRAME_CACHE_MAX = 96
_FRAME_CACHE: OrderedDict[str, QPixmap] = OrderedDict()
_FRAME_FILE_RE = re.compile(r"^.*_(\d+)_(\d+)\.png$")
LayerFramePaths = tuple[tuple[tuple[str, Path], ...], ...]


def parse_frame_filename(path: Path) -> tuple[int, int]:
    """从新帧文件名中解析帧序号和延时"""

    match = _FRAME_FILE_RE.fullmatch(path.name)
    if match is None:
        raise ValueError(
            f"图片命名不符合规范: {path}。必须形如 任意前缀_000_125.png"
        )
    frame_index = int(match.group(1))
    delay_ms = int(match.group(2))
    if delay_ms < 1:
        raise ValueError(f"图片帧延时必须大于 0ms: {path}")
    return frame_index, delay_ms


def _load_cached_pixmap(path: Path) -> QPixmap:
    key = str(path)
    cached = _FRAME_CACHE.get(key)
    if cached is not None:
        _FRAME_CACHE.move_to_end(key)
        return cached
    pixmap = QPixmap(key)
    if pixmap.isNull():
        raise ValueError(f"无法加载图片: {path}")
    _FRAME_CACHE[key] = pixmap
    _FRAME_CACHE.move_to_end(key)
    while len(_FRAME_CACHE) > _FRAME_CACHE_MAX:
        _FRAME_CACHE.popitem(last=False)
    return pixmap


def _remember_cached_pixmap(key: str, pixmap: QPixmap) -> QPixmap:
    _FRAME_CACHE[key] = pixmap
    _FRAME_CACHE.move_to_end(key)
    while len(_FRAME_CACHE) > _FRAME_CACHE_MAX:
        _FRAME_CACHE.popitem(last=False)
    return pixmap


def _load_layered_cached_pixmap(frame_layers: tuple[tuple[str, Path], ...]) -> QPixmap:
    key = "layered:" + "|".join(f"{layer}:{path}" for layer, path in frame_layers)
    cached = _FRAME_CACHE.get(key)
    if cached is not None:
        _FRAME_CACHE.move_to_end(key)
        return cached

    pixmaps = [_load_cached_pixmap(path) for _, path in frame_layers]
    width = max(pixmap.width() for pixmap in pixmaps)
    height = max(pixmap.height() for pixmap in pixmaps)
    result = QPixmap(width, height)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    for pixmap in pixmaps:
        painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return _remember_cached_pixmap(key, result)


@dataclass(frozen=True)
class Clip:
    """包含逐帧延时的可播放图片序列"""

    frame_paths: tuple[Path, ...]
    frame_intervals_ms: tuple[int, ...]
    action_id: str | None = None
    source_state: str | None = None
    phase: str | None = None
    variant: str | None = None
    frame_layers: LayerFramePaths | None = None

    def __post_init__(self) -> None:
        if not self.frame_paths:
            raise ValueError("Clip 必须至少包含一帧")
        if len(self.frame_paths) != len(self.frame_intervals_ms):
            raise ValueError("Clip 的图片帧数量必须和帧延时数量一致")
        if self.frame_layers is not None and len(self.frame_layers) != len(self.frame_paths):
            raise ValueError("Clip 的叠层帧数量必须和图片帧数量一致")
        if any(interval < 1 for interval in self.frame_intervals_ms):
            raise ValueError("Clip 的所有帧延时都必须大于 0ms")

    @classmethod
    def from_paths(cls, frame_paths: list[Path] | tuple[Path, ...]) -> "Clip":
        if not frame_paths:
            raise ValueError("Clip 必须至少包含一帧")
        parsed: list[tuple[int, str, int, Path]] = []
        seen_indices: set[int] = set()
        for path in frame_paths:
            frame_index, delay_ms = parse_frame_filename(path)
            if frame_index in seen_indices:
                raise ValueError(f"图片帧序号重复: {path}")
            seen_indices.add(frame_index)
            parsed.append((frame_index, path.name, delay_ms, path))
        parsed.sort(key=lambda item: (item[0], item[1]))
        return cls(
            frame_paths=tuple(path for _, _, _, path in parsed),
            frame_intervals_ms=tuple(delay_ms for _, _, delay_ms, _ in parsed),
        )

    @classmethod
    def from_layer_clips(
        cls,
        layer_clips: dict[str, "Clip"],
        layer_order: tuple[str, ...],
    ) -> "Clip":
        if not layer_clips:
            raise ValueError("叠层 Clip 必须至少包含一个图层")
        ordered_layers = tuple(layer for layer in layer_order if layer in layer_clips)
        if not ordered_layers:
            raise ValueError("叠层 Clip 没有可播放图层")

        timelines: dict[str, list[tuple[int, int, Path]]] = {}
        boundaries = {0}
        max_duration = 0
        for layer in ordered_layers:
            clip = layer_clips[layer]
            start = 0
            segments: list[tuple[int, int, Path]] = []
            for path, duration in zip(clip.frame_paths, clip.frame_intervals_ms):
                end = start + duration
                segments.append((start, end, path))
                boundaries.add(start)
                boundaries.add(end)
                start = end
            timelines[layer] = segments
            max_duration = max(max_duration, start)
        boundaries.add(max_duration)

        sorted_boundaries = sorted(boundaries)
        frame_layers: list[tuple[tuple[str, Path], ...]] = []
        intervals: list[int] = []
        debug_paths: list[Path] = []
        for start, end in zip(sorted_boundaries, sorted_boundaries[1:]):
            if end <= start:
                continue
            active_layers: list[tuple[str, Path]] = []
            for layer in ordered_layers:
                path = _active_path_at(timelines[layer], start)
                if path is not None:
                    active_layers.append((layer, path))
            if not active_layers:
                continue
            frame_layers.append(tuple(active_layers))
            intervals.append(end - start)
            debug_paths.append(active_layers[-1][1])
        return cls(
            frame_paths=tuple(debug_paths),
            frame_intervals_ms=tuple(intervals),
            frame_layers=tuple(frame_layers),
        )

    def __len__(self) -> int:
        return len(self.frame_paths)

    @property
    def duration_ms(self) -> int:
        return sum(self.frame_intervals_ms)

    @property
    def interval_ms(self) -> int:
        """迁移期兼容旧调用方的单一帧间隔字段"""

        return self.frame_intervals_ms[0]

    def interval_for(self, index: int) -> int:
        return self.frame_intervals_ms[index]

    def frame(self, index: int) -> QPixmap:
        if self.frame_layers is not None:
            return _load_layered_cached_pixmap(self.frame_layers[index])
        return _load_cached_pixmap(self.frame_paths[index])

    def with_debug_metadata(
        self,
        *,
        action_id: str,
        source_state: str,
        phase: str,
        variant: str,
    ) -> "Clip":
        return Clip(
            frame_paths=self.frame_paths,
            frame_intervals_ms=self.frame_intervals_ms,
            action_id=action_id,
            source_state=source_state,
            phase=phase,
            variant=variant,
            frame_layers=self.frame_layers,
        )


@dataclass(frozen=True)
class Mode:
    """循环动作或 start-loop-end 分段动作"""

    loop: Clip
    start: Clip | None = None
    end: Clip | None = None
    action_id: str | None = None
    source_state: str | None = None
    loop_variant: str | None = None
    start_variant: str | None = None
    end_variant: str | None = None

    def __post_init__(self) -> None:
        has_start = self.start is not None
        has_end = self.end is not None
        if has_start != has_end:
            raise ValueError("分段动画必须同时提供 start 和 end")

    @property
    def is_phased(self) -> bool:
        return self.start is not None


def _active_path_at(segments: list[tuple[int, int, Path]], timestamp_ms: int) -> Path | None:
    for start, end, path in segments:
        if start <= timestamp_ms < end:
            return path
    return None
