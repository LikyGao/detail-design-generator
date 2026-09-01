"""Small, thread-safe bridge between the HTTP API and the desktop window."""

from __future__ import annotations

import ctypes
import sys
import threading
from typing import Any


class WindowManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._window: Any | None = None
        self._activation_pending = False

    def set_window(self, window: Any) -> None:
        with self._lock:
            self._window = window
            activate_now = self._activation_pending
            self._activation_pending = False
        if activate_now:
            self.activate()

    def clear_window(self) -> None:
        with self._lock:
            self._window = None

    def activate(self) -> bool:
        """Restore and raise the window, remembering early startup requests."""
        with self._lock:
            window = self._window
            if window is None:
                self._activation_pending = True
                return False

        # pywebview methods are safe to request from the Uvicorn worker thread.
        # Not every GUI backend implements every operation, hence independent
        # best-effort calls rather than allowing one failure to skip the rest.
        for method_name in ("show", "restore"):
            try:
                getattr(window, method_name)()
            except Exception:
                pass

        if sys.platform == "win32":
            self._activate_native_window(window)
        return True

    @staticmethod
    def _activate_native_window(window: Any) -> None:
        """Ask Windows to foreground the native pywebview window when exposed."""
        try:
            native = getattr(window, "native", None)
            handle = getattr(native, "Handle", None) or getattr(native, "handle", None)
            if handle:
                user32 = ctypes.windll.user32
                user32.ShowWindow(int(handle), 9)  # SW_RESTORE
                user32.SetForegroundWindow(int(handle))
        except Exception:
            # show/restore above still provides a portable activation fallback.
            pass


window_manager = WindowManager()
