"""统一音频电平 helper：播放状态 + 系统音量条。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_HELPER = ROOT / "helpers" / "audio_level_helper.swift"
APPLE_SCRIPT = "output volume of (get volume settings)"


def _read_system_volume() -> float:
    try:
        result = subprocess.run(
            ["osascript", "-e", APPLE_SCRIPT],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return 0.0
    if result.returncode != 0:
        return 0.0
    try:
        value = int(result.stdout.strip() or "0")
    except ValueError:
        return 0.0
    return max(0.0, min(1.0, value / 100.0))


def _start_playback_state_helper() -> tuple[subprocess.Popen[str], Path]:
    module_cache = Path(tempfile.mkdtemp(prefix="vpet-swift-module-cache-"))
    env = os.environ.copy()
    env["CLANG_MODULE_CACHE_PATH"] = str(module_cache)
    proc = subprocess.Popen(
        ["swift", str(SWIFT_HELPER)],
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
        env=env,
    )
    return proc, module_cache


def main() -> int:
    proc, module_cache = _start_playback_state_helper()
    try:
        while True:
            if proc.stdout is not None:
                line = proc.stdout.readline()
            else:
                line = ""
            if proc.poll() is not None and not line:
                return proc.returncode or 0
            latest_playing = line.strip() == "1"
            level = _read_system_volume() if latest_playing else 0.0
            print(f"{level:.2f}", flush=True)
    except BrokenPipeError:
        return 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=1.0)
        shutil.rmtree(module_cache, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
