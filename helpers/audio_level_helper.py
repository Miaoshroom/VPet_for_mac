"""用swift脚本读音量条+检测播放状态"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.app_paths import helper_swift_path


def _start_playback_state_helper() -> tuple[subprocess.Popen[str], Path]:
    module_cache = Path(tempfile.mkdtemp(prefix="vpet-swift-module-cache-"))
    env = os.environ.copy()
    env["CLANG_MODULE_CACHE_PATH"] = str(module_cache)
    proc = subprocess.Popen(
        ["swift", str(helper_swift_path())],
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

            text = line.strip()
            if not text:
                continue
            try:
                level = float(text)
            except ValueError:
                continue
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
