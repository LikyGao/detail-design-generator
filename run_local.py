"""Launch the detail design generator as a native desktop window."""
from __future__ import annotations
import ctypes
import os
import sys
import traceback
from pathlib import Path
from local_backend.desktop import DesktopStartupError, run_desktop

def _show_error(message: str, details: str = "") -> None:
    if os.environ.get("DDG_HEADLESS_SMOKE") == "1":
        log_path = os.environ.get("DDG_SMOKE_LOG", "").strip()
        text = message if not details else f"{message}\n\n{details}"
        if log_path:
            Path(log_path).write_text(text, encoding="utf-8")
        return
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, message, "基本設計書生成ツール", 0x10)
    else:
        print(message, file=sys.stderr)

def main() -> int:
    try:
        return run_desktop()
    except DesktopStartupError as exc:
        _show_error(str(exc), traceback.format_exc())
        return 1
    except Exception as exc:
        _show_error(f"予期しない起動エラー: {exc}", traceback.format_exc())
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
