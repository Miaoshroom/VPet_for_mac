"""桌宠窗口：负责显示动画、处理鼠标交互"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow

from animation import Clip, PetAnimationDirector
from pet_menu import show_pet_menu

RESIZE_GRIP = 22
_SETTINGS = Path(__file__).resolve().parent / "pet_settings.json"
ZOOM_STEP = 30


def _load_settings() -> dict:
    # json不对就该直接崩（
    return json.loads(_SETTINGS.read_text(encoding="utf-8"))


def _max_side_from_json() -> int:
    data = _load_settings()
    return max(0, int(data["display_size"]))


def _save_display_size_to_json(size: int) -> None:
    try:
        payload = _load_settings()
        payload["display_size"] = max(0, int(size))
        _SETTINGS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


class PetWindow(QMainWindow):
    def __init__(
        self,
        director: PetAnimationDirector,
        initial_pixmap: QPixmap,
        single_actions: dict[str, Clip] | None = None,
        *,
        max_side: int | None = None,
    ) -> None:
        super().__init__()
        self._director = director
        self._single_actions = single_actions or {}
        self._drag_anchor: QPoint | None = None
        if max_side is None:
            max_side = _max_side_from_json()
        self._max_side = max(0, max_side)

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background: transparent;")
        self._label.setScaledContents(False)
        self._source_pixmap = initial_pixmap

        pix0 = self._fit_pixmap(initial_pixmap)
        self._label.setPixmap(pix0)
        self.setCentralWidget(self._label)

        w = max(64, pix0.width())
        h = max(64, pix0.height())
        self.resize(w, h)
        self.setMinimumSize(48, 48)
        settings = _load_settings()
        self.move(int(settings["display_x"]), int(settings["display_y"]))

        director.frame_changed.connect(self._on_frame)

    def _fit_pixmap(self, pix: QPixmap) -> QPixmap:
        if self._max_side <= 0:
            return pix
        if pix.width() <= self._max_side and pix.height() <= self._max_side:
            return pix
        return pix.scaled(
            self._max_side,
            self._max_side,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _on_frame(self, pix: QPixmap) -> None:
        self._source_pixmap = pix
        fitted = self._fit_pixmap(pix)
        self._label.setPixmap(fitted)
        self.resize(max(64, fitted.width()), max(64, fitted.height()))

    def _refresh_current_pixmap(self) -> None:
        fitted = self._fit_pixmap(self._source_pixmap)
        self._label.setPixmap(fitted)
        self.resize(max(64, fitted.width()), max(64, fitted.height()))

    def _zoom(self, delta: int) -> None:
        self._max_side = max(0, self._max_side + delta)
        self._refresh_current_pixmap()
        _save_display_size_to_json(self._max_side)

    def _play_single_action(self, action_name: str) -> None:
        clip = self._single_actions.get(action_name)
        if clip is None:
            return
        self._director.play_single(clip)

    def _save_start_position(self) -> None:
        try:
            payload = _load_settings()
            payload["display_x"] = int(self.x())
            payload["display_y"] = int(self.y())
            payload["display_size"] = max(0, int(self._max_side))
            _SETTINGS.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _in_resize_grip(self, local_pos: QPoint) -> bool:
        r = self.rect()
        return (
            local_pos.x() >= r.width() - RESIZE_GRIP
            and local_pos.y() >= r.height() - RESIZE_GRIP
        )

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            lp = e.position().toPoint()
            if self._in_resize_grip(lp) and self.windowHandle() is not None:
                self.windowHandle().startSystemResize(
                    Qt.Edge.RightEdge | Qt.Edge.BottomEdge
                )
                e.accept()
                return
            self._drag_anchor = e.globalPosition().toPoint() - self.pos()
            self._director.on_mouse_press()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if (
            e.buttons() & Qt.MouseButton.LeftButton
            and self._drag_anchor is not None
        ):
            self.move(e.globalPosition().toPoint() - self._drag_anchor)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._director.on_mouse_release()
            self._drag_anchor = None
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e) -> None:
        action_handlers = {
            title: (lambda name=title: self._play_single_action(name))
            for title in self._single_actions
        }
        show_pet_menu(
            self,
            e.globalPos(),
            on_zoom_in=lambda: self._zoom(ZOOM_STEP),
            on_zoom_out=lambda: self._zoom(-ZOOM_STEP),
            action_handlers=action_handlers,
            on_set_start_pos=self._save_start_position,
            on_quit=QApplication.quit,
        )
