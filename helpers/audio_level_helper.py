"""每秒输出一次 macOS 当前系统输出音量，范围 0.0 ~ 1.0。"""

from __future__ import annotations

import subprocess
import sys
import time

INTERVAL_SECONDS = 1.0
APPLE_SCRIPT = "output volume of (get volume settings)"


def read_level() -> float:
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
    value = max(0, min(100, value))
    return value / 100.0


def main() -> int:
    try:
        while True:
            print(f"{read_level():.2f}", flush=True)
            time.sleep(INTERVAL_SECONDS)
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
