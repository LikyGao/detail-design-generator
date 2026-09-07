"""Minimal FastAPI application used by the desktop wrapper."""
from __future__ import annotations
import sys
from pathlib import Path
from threading import Lock
from typing import Callable
from fastapi import FastAPI, Response
from fastapi.responses import FileResponse

APP_HEADER = "X-Detail-Design-Generator"
APP_HEADER_VALUE = "local-desktop-v2"
HTML_FILENAME = "基本設計書generator.html"

def resource_path(filename: str) -> Path:
    """Locate data in a checkout and in a PyInstaller one-file app."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    root = Path(bundle_root) if bundle_root else Path(__file__).resolve().parents[1]
    return root / filename

def create_app(activate: Callable[[], None] | None = None) -> FastAPI:
    app = FastAPI(title="基本設計書生成ツール local backend")
    callback_lock = Lock()

    @app.middleware("http")
    async def identify_application(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers[APP_HEADER] = APP_HEADER_VALUE
        return response

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/app/activate", status_code=204)
    def activate_application() -> Response:
        if activate is not None:
            with callback_lock:
                activate()
        return Response(status_code=204)

    @app.get("/", response_class=FileResponse)
    def index() -> FileResponse:
        return FileResponse(resource_path(HTML_FILENAME), media_type="text/html")
    return app

app = create_app()
