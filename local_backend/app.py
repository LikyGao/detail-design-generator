"""FastAPI application used by the local desktop wrapper."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from .services.template_service import TemplateService
from .services.word_service import WordService

APP_HEADER = "X-Detail-Design-Generator"
APP_HEADER_VALUE = "local-desktop-v2"
HTML_FILENAME = "基本設計書generator.html"
LOCAL_BRIDGE_FILENAME = "local_backend/local_bridge.js"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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


class WordRequest(BaseModel):
    document_type: str
    client_name: str = ""
    project_name: str = ""
    version: str = "1.0"
    issue_date: str = ""
    project_no: str = "-"
    revision_history_json: Any = Field(default_factory=list)
    chapters_json: Any = Field(default_factory=list)
    output_filename: str = "基本設計書.docx"


def _desktop_html() -> str:
    """Return the current HTML with the desktop-only API bridge injected."""
    html = resource_path(HTML_FILENAME).read_text(encoding="utf-8")
    bridge_tag = '<script src="/local-bridge.js"></script>'
    if bridge_tag in html:
        return html
    body_end = html.rfind("</body>")
    if body_end != -1:
        return html[:body_end] + f"  {bridge_tag}\n" + html[body_end:]
    return html + "\n" + bridge_tag + "\n"


def create_app(
    activate: Callable[[], None] | None = None,
    *,
    data_root: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="基本設計書生成ツール local backend")
    callback_lock = Lock()
    root = data_root or default_data_root()
    templates = TemplateService(root)
    words = WordService(root)
    app.state.template_service = templates
    app.state.word_service = words

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

    @app.post("/api/generate-word")
    def generate_word(request: WordRequest) -> Response:
        try:
            content, filename = words.generate(request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
        return Response(
            content,
            media_type=DOCX_MEDIA_TYPE,
            headers={"Content-Disposition": disposition},
        )

    @app.get("/local-bridge.js", response_class=FileResponse)
    def local_bridge() -> FileResponse:
        return FileResponse(resource_path(LOCAL_BRIDGE_FILENAME), media_type="application/javascript")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_desktop_html())

    return app


app = create_app()