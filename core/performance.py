"""轻量性能探针"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from PyQt6.QtCore import QElapsedTimer

_ENABLE_ENV = "VPET_UI_PERF"
_LOG_ENV = "VPET_UI_PERF_LOG"
_LOG_MIN_ENV = "VPET_UI_PERF_LOG_MIN_MS"
_MAX_RECORDS = 512

_recording_enabled = False
_records: list["UiPerfRecord"] = []


@dataclass(frozen=True, slots=True)
class UiPerfRecord:
    name: str
    elapsed_ms: float
    detail: str = ""


def set_ui_perf_recording(enabled: bool) -> None:
    global _recording_enabled
    _recording_enabled = bool(enabled)


def clear_ui_perf_records() -> None:
    _records.clear()


def ui_perf_records() -> tuple[UiPerfRecord, ...]:
    return tuple(_records)


def ui_perf_enabled() -> bool:
    return _recording_enabled or _env_truthy(_ENABLE_ENV)


class measure_ui:
    def __init__(self, name: str, *, detail: str = "") -> None:
        self._name = str(name).strip() or "unnamed"
        self._detail = str(detail).strip()
        self._timer: QElapsedTimer | None = None
        self.elapsed_ms = 0.0

    def __enter__(self) -> "measure_ui":
        if ui_perf_enabled():
            self._timer = QElapsedTimer()
            self._timer.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._timer is None:
            return False
        self.elapsed_ms = self._timer.nsecsElapsed() / 1_000_000
        _append_record(UiPerfRecord(self._name, self.elapsed_ms, self._detail))
        if _should_log(self.elapsed_ms):
            suffix = f" {self._detail}" if self._detail else ""
            print(
                f"[ui-perf] {self._name}: {self.elapsed_ms:.2f} ms{suffix}",
                file=sys.stderr,
            )
        return False


def _append_record(record: UiPerfRecord) -> None:
    _records.append(record)
    if len(_records) > _MAX_RECORDS:
        del _records[: len(_records) - _MAX_RECORDS]


def _should_log(elapsed_ms: float) -> bool:
    if not (_env_truthy(_LOG_ENV) or os.environ.get(_ENABLE_ENV, "").strip().lower() == "log"):
        return False
    try:
        min_ms = float(os.environ.get(_LOG_MIN_ENV, "5"))
    except ValueError:
        min_ms = 5.0
    return elapsed_ms >= min_ms


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on", "log"}


__all__ = [
    "UiPerfRecord",
    "clear_ui_perf_records",
    "measure_ui",
    "set_ui_perf_recording",
    "ui_perf_enabled",
    "ui_perf_records",
]
