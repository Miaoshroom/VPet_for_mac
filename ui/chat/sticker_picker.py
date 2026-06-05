"""贴纸选择弹层"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QGridLayout, QToolButton, QWidget

from ui.chat.sticker_resolver import StickerPathResolver

PICKER_ICON_SIZE = 42


class StickerPicker(QFrame):
    sticker_selected = pyqtSignal(str)

    def __init__(
        self,
        stickers: list[dict[str, object]],
        sticker_resolver: StickerPathResolver | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self.setObjectName("stickerPicker")
        self._stickers = list(stickers)
        self._sticker_resolver = sticker_resolver
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        for index, sticker in enumerate(self._stickers):
            sticker_id = str(sticker.get("id", "")).strip()
            label = str(sticker.get("label", sticker_id)).strip() or sticker_id
            button = QToolButton()
            button.setObjectName("stickerButton")
            button.setText(label)
            button.setToolTip(label)
            resolved = (
                self._sticker_resolver.resolve(
                    sticker_id,
                    metadata=sticker,
                    prefer="user",
                )
                if self._sticker_resolver is not None
                else None
            )
            button.setProperty("stickerId", sticker_id)
            button.setProperty("stickerPath", str(resolved.path) if resolved else "")
            button.setProperty("stickerSource", resolved.source if resolved else "missing")
            button.setIcon(_sticker_icon(resolved.path if resolved else None, label))
            button.setIconSize(QSize(PICKER_ICON_SIZE, PICKER_ICON_SIZE))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setFixedSize(76, 70)
            button.clicked.connect(
                lambda checked=False, value=sticker_id: self._choose(value)
            )
            layout.addWidget(button, index // 3, index % 3)

    def show_near(self, widget: QWidget) -> None:
        point = widget.mapToGlobal(QPoint(0, -self.sizeHint().height() - 6))
        self.move(point)
        self.show()

    def _choose(self, sticker_id: str) -> None:
        if sticker_id:
            self.sticker_selected.emit(sticker_id)
        self.hide()


def _sticker_icon(path: Path | None, label: str) -> QIcon:
    pixmap = _load_preview_pixmap(path)
    if pixmap is None:
        pixmap = _placeholder_pixmap(label)
    return QIcon(pixmap)


def _load_preview_pixmap(path: Path | None) -> QPixmap | None:
    if path is None or not path.exists():
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap.scaled(
        PICKER_ICON_SIZE,
        PICKER_ICON_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _placeholder_pixmap(label: str) -> QPixmap:
    pixmap = QPixmap(PICKER_ICON_SIZE, PICKER_ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor(48, 52, 61, 230))
    painter.setPen(QColor(118, 128, 148, 210))
    painter.drawRoundedRect(1, 1, PICKER_ICON_SIZE - 2, PICKER_ICON_SIZE - 2, 9, 9)
    font = QFont()
    font.setBold(True)
    font.setPixelSize(18)
    painter.setFont(font)
    painter.setPen(QColor(238, 241, 247))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, _placeholder_text(label))
    painter.end()
    return pixmap


def _placeholder_text(label: str) -> str:
    text = str(label).strip()
    return text[:1] if text else "?"


__all__ = ["StickerPicker"]
