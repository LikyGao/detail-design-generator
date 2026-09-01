from __future__ import annotations

import json
import socket
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import uvicorn
import webview

from local_backend.app import app
from local_backend.desktop import window_manager

HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"
HEALTH_URL = f"{BASE_URL}/api/health"
APP_MARKER_HEADER = "X-Detail-Design-Generator"
STARTUP_TIMEOUT = 15.0
_instance_mutex = None


def probe_instance(timeout: float = 0.5) -> str:
    """Return ``ours``, ``foreign``, or ``absent`` for the configured port."""
    try:
        with urlopen(HEALTH_URL, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if payload == {"status": "ok"} and response.headers.get(APP_MARKER_HEADER) == "1":
                return "ours"
            return "foreign"
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
        try:
            with socket.create_connection((HOST, PORT), timeout=timeout):
                return "foreign"
        except OSError:
            return "absent"


def activate_existing() -> bool:
    request = Request(f"{BASE_URL}/api/app/activate", data=b"", method="POST")
    try:
        with urlopen(request, timeout=2.0) as response:
            return response.status == 200
    except (HTTPError, URLError, OSError):
        return False


def run_server() -> None:
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def wait_for_server(timeout: float = STARTUP_TIMEOUT) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = probe_instance()
        if state != "absent":
            return state
        time.sleep(0.15)
    return "absent"


def show_error(message: str) -> None:
    """Show a GUI error in windowed builds, with stderr as a portable fallback."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "基本設計書生成ツール", 0x10)
            return
        except Exception:
            pass
    print(message, file=sys.stderr)


def acquire_instance_guard() -> bool:
    """Close the startup race before the health endpoint becomes available."""
    global _instance_mutex
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\DetailDesignGenerator-8765")
        if not handle:
            return False
        already_exists = ctypes.windll.kernel32.GetLastError() == 183
        if already_exists:
            ctypes.windll.kernel32.CloseHandle(handle)
            return False
        _instance_mutex = handle  # Keep it alive for the lifetime of this process.
        return True
    except Exception:
        # Health/port ownership checks remain the fallback on nonstandard hosts.
        return True


def main() -> int:
    state = probe_instance()
    if state == "ours":
        if not activate_existing():
            show_error("起動済みのアプリケーションをアクティブにできませんでした。")
            return 1
        return 0
    if state == "foreign":
        show_error(f"ポート {PORT} は別のアプリケーションによって使用されています。")
        return 1

    if not acquire_instance_guard():
        state = wait_for_server()
        if state == "ours" and activate_existing():
            return 0
        show_error("起動中のアプリケーションをアクティブにできませんでした。")
        return 1

    threading.Thread(target=run_server, name="local-api", daemon=True).start()
    state = wait_for_server()
    if state != "ours":
        reason = "別のアプリケーションがポートを使用しています。" if state == "foreign" else "ローカルサーバーが起動しませんでした。"
        show_error(reason)
        return 1

    try:
        window = webview.create_window(
            "基本設計書生成ツール",
            BASE_URL + "/",
            width=1440,
            height=900,
            min_size=(1000, 700),
            resizable=True,
        )
        window_manager.set_window(window)
        webview.start()
    except Exception as exc:
        show_error(f"アプリケーションウィンドウを開けませんでした。\n{exc}")
        return 1
    finally:
        window_manager.clear_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
