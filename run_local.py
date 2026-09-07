"""Launch the detail design generator as a native desktop window."""
from __future__ import annotations
import ctypes
import os
import sys
from local_backend.desktop import DesktopStartupError, run_desktop

def _show_error(message: str) -> None:
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, message, "基本設計書生成ツール", 0x10)
    else:
        print(message, file=sys.stderr)

def main() -> int:
    try:
        return run_desktop()
    except DesktopStartupError as exc:
        _show_error(str(exc))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
