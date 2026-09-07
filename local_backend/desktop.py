"""pywebview desktop lifecycle and single-instance coordination."""
from __future__ import annotations
import ctypes
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
import uvicorn
from .app import APP_HEADER, APP_HEADER_VALUE, create_app

HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"
WINDOW_TITLE = "基本設計書生成ツール"
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

def bring_window_to_front() -> None:
    """Restore and activate this process' top-level window on Windows."""
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
            if title.value == WINDOW_TITLE:
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                return False
        return True
    user32.EnumWindows(callback, 0)

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
    server = uvicorn.Server(uvicorn.Config(create_app(bring_window_to_front), host=HOST, port=PORT, log_level="warning"))
    thread = threading.Thread(target=server.run, name="local-backend", daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if is_existing_instance():
            return Backend(server, thread)
        if not thread.is_alive():
            break
        time.sleep(0.05)
    server.should_exit = True
    raise DesktopStartupError("ローカル Backend を起動できませんでした。")

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
        webview.create_window(WINDOW_TITLE, BASE_URL + "/", width=1440, height=900, min_size=(1024, 700))
        webview.start()
        return 0
    finally:
        backend.stop()
