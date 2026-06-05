"""Shared chat sticker path resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from core.chat.config import ChatConfig
from core.chat.models import ChatSender

STICKER_SUFFIXES = (".png", ".webp", ".gif", ".jpg", ".jpeg")
EXPLICIT_PATH_KEYS = ("path", "image_path", "asset_path", "image", "file")


@dataclass(slots=True, frozen=True)
class ResolvedStickerPath:
    path: Path
    source: str


class StickerPathResolver:
    def __init__(self, config: ChatConfig) -> None:
        self.config = config

    def resolve(
        self,
        sticker_id: str,
        *,
        sender: ChatSender | None = None,
        metadata: Mapping[str, Any] | None = None,
        prefer: str | None = None,
    ) -> ResolvedStickerPath | None:
        sticker_id = str(sticker_id).strip()
        if not sticker_id:
            return None
        metadata = dict(metadata or {})
        for path in self._explicit_paths(metadata):
            if path.exists():
                return ResolvedStickerPath(path=path, source="configured")
        if prefer == "user" or sender == ChatSender.USER:
            path = _first_existing(self.config.storage.user_stickers_dir, sticker_id)
            if path is not None:
                return ResolvedStickerPath(path=path, source="user")
        for path in self._configured_sticker_paths(sticker_id):
            if path.exists():
                return ResolvedStickerPath(path=path, source="configured")
        for source, base_dir in self._directory_order(sender=sender, prefer=prefer):
            path = _first_existing(base_dir, sticker_id)
            if path is not None:
                return ResolvedStickerPath(path=path, source=source)
        return None

    def user_stickers(self) -> list[dict[str, object]]:
        stickers = _stickers_from_dir(self.config.storage.user_stickers_dir)
        if stickers:
            return stickers
        return list(self.config.available_stickers())

    def _explicit_paths(self, metadata: Mapping[str, Any]) -> list[Path]:
        paths: list[Path] = []
        for key in EXPLICIT_PATH_KEYS:
            path = self._resolve_configured_path(metadata.get(key))
            if path is not None:
                paths.append(path)
        return paths

    def _configured_sticker_paths(self, sticker_id: str) -> list[Path]:
        sticker = self.config.stickers.get(sticker_id)
        if sticker is None:
            return []
        return self._explicit_paths(sticker.metadata)

    def _resolve_configured_path(self, value: object) -> Path | None:
        text = str(value or "").strip()
        if not text:
            return None
        path = Path(text).expanduser()
        if path.is_absolute():
            return path
        return self.config.project_root / path

    def _directory_order(
        self,
        *,
        sender: ChatSender | None,
        prefer: str | None,
    ) -> tuple[tuple[str, Path], ...]:
        first = prefer or ("user" if sender == ChatSender.USER else "pet")
        if first == "user":
            return (
                ("user", self.config.storage.user_stickers_dir),
                ("pet", self.config.storage.pet_stickers_dir),
                ("legacy", self.config.project_root / "assets" / "sticker"),
            )
        return (
            ("pet", self.config.storage.pet_stickers_dir),
            ("user", self.config.storage.user_stickers_dir),
            ("legacy", self.config.project_root / "assets" / "sticker"),
        )


def _first_existing(directory: Path, sticker_id: str) -> Path | None:
    for suffix in STICKER_SUFFIXES:
        path = directory / f"{sticker_id}{suffix}"
        if path.exists():
            return path
    return None


def _stickers_from_dir(directory: Path) -> list[dict[str, object]]:
    if not directory.exists() or not directory.is_dir():
        return []
    stickers: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.suffix.lower() not in STICKER_SUFFIXES:
            continue
        sticker_id = path.stem.strip()
        if not sticker_id or sticker_id in seen:
            continue
        seen.add(sticker_id)
        stickers.append({"id": sticker_id, "label": sticker_id, "source": "user"})
    return stickers


__all__ = ["ResolvedStickerPath", "StickerPathResolver"]
