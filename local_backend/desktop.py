"""pywebview desktop lifecycle and single-instance coordination."""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import uvicorn

from .app import APP_HEADER, APP_HEADER_VALUE, create_app
from .services.staging import (
    read_project_archive,
    remove_staged_file,
    stage_bytes,
    staged_path,
)

HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"
WINDOW_TITLE = "基本設計書生成ツール"
PREVIEW_WINDOW_TITLE = "基本設計書プレビュー"
MUTEX_NAME = "Local\\DetailDesignGenerator-8765"
_mutex_handle = None


class DesktopStartupError(RuntimeError):
    """Raised when the local desktop host cannot start safely."""


def _request(path: str, method: str = "GET", timeout: float = 0.75):
    return urllib.request.urlopen(urllib.request.Request(BASE_URL + path, method=method), timeout=timeout)


def is_existing_instance() -> bool:
    """Return true only when port 8765 belongs to this application."""
    try:
        with _request("/api/health") as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.headers.get(APP_HEADER) == APP_HEADER_VALUE and payload == {"status": "ok"}
    except (OSError, ValueError, urllib.error.URLError):
        return False


def activate_existing_instance() -> bool:
    if not is_existing_instance():
        return False
    try:
        with _request("/api/app/activate", method="POST") as response:
            return response.status == 204 and response.headers.get(APP_HEADER) == APP_HEADER_VALUE
    except (OSError, urllib.error.URLError):
        return False


def port_is_in_use() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        return probe.connect_ex((HOST, PORT)) == 0


def acquire_single_instance_mutex() -> bool:
    """Atomically claim the Windows application instance."""
    global _mutex_handle
    if os.name != "nt":
        return True
    create_mutex = ctypes.windll.kernel32.CreateMutexW
    create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    create_mutex.restype = ctypes.c_void_p
    handle = create_mutex(None, False, MUTEX_NAME)
    if not handle:
        raise DesktopStartupError("単一インスタンス制御を初期化できませんでした。")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(handle)
        return False
    _mutex_handle = handle
    return True


def bring_named_window_to_front(title_value: str) -> None:
    """Restore and activate this process' matching top-level window on Windows."""
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    current_pid = os.getpid()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _lparam):
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == current_pid and user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            if title.value == title_value:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                return False
        return True

    user32.EnumWindows(callback, 0)


def bring_window_to_front() -> None:
    bring_named_window_to_front(WINDOW_TITLE)


@dataclass
class Backend:
    server: uvicorn.Server
    thread: threading.Thread

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


def start_backend() -> Backend:
    if port_is_in_use():
        raise DesktopStartupError(f"{HOST}:{PORT} は別のプログラムによって使用されています。")

    # A PyInstaller windowed executable has no console and may expose
    # sys.stdout/sys.stderr as None. Uvicorn's default logging configuration
    # probes stderr during startup, so disable console logging here and let the
    # desktop wrapper own user-visible error reporting.
    config = uvicorn.Config(
        create_app(bring_window_to_front),
        host=HOST,
        port=PORT,
        log_level="warning",
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread_errors: list[BaseException] = []

    def run_server() -> None:
        try:
            server.run()
        except BaseException as exc:  # preserve the real packaged-startup failure for diagnostics
            thread_errors.append(exc)

    thread = threading.Thread(target=run_server, name="local-backend", daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if is_existing_instance():
            return Backend(server, thread)
        if not thread.is_alive():
            break
        time.sleep(0.05)
    server.should_exit = True
    thread.join(timeout=1)
    if thread_errors:
        exc = thread_errors[0]
        raise DesktopStartupError(
            f"ローカル Backend を起動できませんでした: {type(exc).__name__}: {exc}"
        ) from exc
    raise DesktopStartupError("ローカル Backend を起動できませんでした。")


class DesktopApi:
    """Native desktop operations exposed to the editor via pywebview JS API."""

    def __init__(self) -> None:
        self.main_window = None
        self.preview_window = None
        self.current_project_path: Path | None = None
        self._preview_lock = threading.Lock()

    def bind_main_window(self, window) -> None:  # type: ignore[no-untyped-def]
        self.main_window = window

    @staticmethod
    def _dialog_type(webview, name: str):  # type: ignore[no-untyped-def]
        enum = getattr(webview, "FileDialog", None)
        if enum is not None:
            return getattr(enum, name)
        return getattr(webview, f"{name}_DIALOG")

    @staticmethod
    def _first_dialog_path(result) -> Path | None:  # type: ignore[no-untyped-def]
        if not result:
            return None
        if isinstance(result, (str, os.PathLike)):
            return Path(result)
        if isinstance(result, (list, tuple)) and result:
            return Path(result[0])
        return None

    def open_preview_window(self) -> dict[str, object]:
        """Create/focus a real second pywebview window for dual-monitor preview."""
        import webview

        with self._preview_lock:
            if self.preview_window is not None:
                try:
                    bring_named_window_to_front(PREVIEW_WINDOW_TITLE)
                    return {"opened": True, "existing": True}
                except Exception:
                    self.preview_window = None

            preview = webview.create_window(
                PREVIEW_WINDOW_TITLE,
                BASE_URL + "/preview-window",
                width=1000,
                height=900,
                min_size=(620, 480),
                resizable=True,
            )
            self.preview_window = preview

            def on_closed(*_args) -> None:
                with self._preview_lock:
                    self.preview_window = None
                if self.main_window is not None:
                    try:
                        self.main_window.evaluate_js(
                            "window.__ddgDesktopPreviewClosed && window.__ddgDesktopPreviewClosed();"
                        )
                    except Exception:
                        pass

            preview.events.closed += on_closed
            return {"opened": True, "existing": False}

    def save_staged_file(
        self,
        token: str,
        suggested_name: str,
        file_kind: str,
        save_as: bool = False,
    ) -> dict[str, object]:
        """Save a staged Word/project file through the native Windows Save As dialog."""
        import webview

        if self.main_window is None:
            return {"saved": False, "error": "メインウィンドウが利用できません。"}

        suffix = ".docx" if file_kind == "word" else ".ddgproj"
        try:
            source = staged_path(token, suffix)
        except (ValueError, FileNotFoundError):
            return {"saved": False, "error": "保存対象の一時ファイルが見つかりません。"}

        destination: Path | None = None
        if file_kind == "project" and self.current_project_path is not None and not save_as:
            destination = self.current_project_path
        else:
            try:
                dialog_type = self._dialog_type(webview, "SAVE")
                result = self.main_window.create_file_dialog(
                    dialog_type,
                    save_filename=suggested_name,
                    file_types=(
                        "Word Document (*.docx)" if file_kind == "word" else "DDG Project (*.ddgproj)",
                        "All files (*.*)",
                    ),
                )
                destination = self._first_dialog_path(result)
            except Exception as exc:
                return {"saved": False, "error": f"保存ダイアログを開けませんでした: {exc}"}

        if destination is None:
            return {"saved": False, "cancelled": True}
        if destination.suffix.lower() != suffix:
            destination = destination.with_suffix(suffix)

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            remove_staged_file(source)
            if file_kind == "project":
                self.current_project_path = destination
            return {"saved": True, "path": str(destination), "filename": destination.name}
        except OSError as exc:
            return {"saved": False, "error": f"ファイルを保存できませんでした: {exc}"}

    def open_project_file(self) -> dict[str, object]:
        """Open a .ddgproj through the native dialog and stage its JSON for localhost retrieval."""
        import webview

        if self.main_window is None:
            return {"opened": False, "error": "メインウィンドウが利用できません。"}
        try:
            dialog_type = self._dialog_type(webview, "OPEN")
            result = self.main_window.create_file_dialog(
                dialog_type,
                allow_multiple=False,
                file_types=("DDG Project (*.ddgproj)", "All files (*.*)"),
            )
            source = self._first_dialog_path(result)
        except Exception as exc:
            return {"opened": False, "error": f"ファイル選択ダイアログを開けませんでした: {exc}"}

        if source is None:
            return {"opened": False, "cancelled": True}
        try:
            project = read_project_archive(source)
            payload = json.dumps(project, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            token, _path = stage_bytes(payload, ".json")
            self.current_project_path = source
            return {"opened": True, "token": token, "filename": source.name}
        except (OSError, ValueError) as exc:
            return {"opened": False, "error": str(exc)}

    def clear_current_project_path(self) -> dict[str, bool]:
        self.current_project_path = None
        return {"ok": True}


def run_desktop() -> int:
    if not acquire_single_instance_mutex():
        # The first process may still be starting its HTTP server.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if activate_existing_instance():
                return 0
            time.sleep(0.1)
        raise DesktopStartupError("起動済みのアプリケーションをアクティブ化できませんでした。")
    if port_is_in_use():
        if activate_existing_instance():
            return 0
        raise DesktopStartupError(f"{HOST}:{PORT} は別のプログラムによって使用されています。")
    backend = start_backend()
    try:
        if os.environ.get("DDG_HEADLESS_SMOKE") == "1":
            while True:
                time.sleep(1)
        import webview

        api = DesktopApi()
        main_window = webview.create_window(
            WINDOW_TITLE,
            BASE_URL + "/",
            width=1440,
            height=900,
            min_size=(1024, 700),
            js_api=api,
        )
        api.bind_main_window(main_window)
        webview.start()
        return 0
    finally:
        backend.stop()
