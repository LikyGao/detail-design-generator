"""FastAPI application used by the local desktop wrapper."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from threading import Lock
from typing import Callable

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .services.template_service import TemplateService

APP_HEADER = "X-Detail-Design-Generator"
APP_HEADER_VALUE = "local-desktop-v2"
HTML_FILENAME = "基本設計書generator.html"


def resource_path(filename: str) -> Path:
    """Locate data in a checkout and in a PyInstaller one-file app."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    root = Path(bundle_root) if bundle_root else Path(__file__).resolve().parents[1]
    return root / filename


def default_data_root() -> Path:
    configured = os.environ.get("DETAIL_DESIGN_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".detail-design-generator" / "data"


class DocumentTypeRequest(BaseModel):
    document_type: str


def create_app(
    activate: Callable[[], None] | None = None,
    *,
    data_root: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="基本設計書生成ツール local backend")
    callback_lock = Lock()
    templates = TemplateService(data_root or default_data_root())
    app.state.template_service = templates

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

    @app.post("/api/templates/register")
    async def register_template(
        document_type: str = Form(...),
        template_file: UploadFile = File(...),
        template_version: str = Form(""),
    ):
        filename = template_file.filename or "template.docx"
        if not filename.lower().endswith(".docx"):
            raise HTTPException(status_code=400, detail="登録できるファイルは.docxのみです。")
        try:
            return templates.register(
                document_type,
                filename,
                await template_file.read(),
                template_version,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/template-data")
    def template_data(request: DocumentTypeRequest):
        try:
            return templates.get_data(request.document_type)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/", response_class=FileResponse)
    def index() -> FileResponse:
        return FileResponse(resource_path(HTML_FILENAME), media_type="text/html")

    return app


app = create_app()
