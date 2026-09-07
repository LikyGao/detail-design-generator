"""FastAPI application used by the local desktop wrapper."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from .services.preview_state import get_preview_state, update_preview_state
from .services.staging import build_project_archive, stage_bytes, staged_path
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


class PreviewStateRequest(BaseModel):
    html: str = ""
    css: str = ""
    revision: int = 0
    nodeId: str | None = None
    blockId: str | None = None
    updatedAt: int | float = 0


class ProjectStageRequest(BaseModel):
    project: dict[str, Any]
    suggested_name: str = "案件.ddgproj"


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


def _preview_window_html() -> str:
    """Standalone preview shell. Content is synchronized from the editor over localhost."""
    return """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>基本設計書プレビュー</title>
<style id="ddgSharedPreviewCss"></style>
<style>
html,body{margin:0;min-height:100%;background:#e5e7eb}
body{overflow:auto}
#ddgPreviewStatus{position:sticky;top:0;z-index:9999;padding:7px 14px;background:#fff;color:#65717d;font:12px/1.5 sans-serif;border-bottom:1px solid #ccd3da}
#standalonePreview{padding:24px;min-height:calc(100vh - 31px);overflow:auto}
#standalonePreview .word-page{margin:0 auto 24px}
#standalonePreview .preview-page-shell{margin:0 auto 24px}
</style>
</head>
<body>
<div id="ddgPreviewStatus">基本設計書プレビュー</div>
<div id="standalonePreview"></div>
<script>
(() => {
  let revision = -1;
  let busy = false;
  const content = document.getElementById('standalonePreview');
  const sharedCss = document.getElementById('ddgSharedPreviewCss');
  const status = document.getElementById('ddgPreviewStatus');
  async function sync(){
    if(busy) return;
    busy = true;
    try{
      const response = await fetch('/api/preview-state', {cache:'no-store'});
      if(!response.ok) throw new Error('HTTP '+response.status);
      const state = await response.json();
      if(state.revision !== revision){
        revision = state.revision;
        if(state.css) sharedCss.textContent = state.css;
        content.innerHTML = state.html || '<div style="padding:30px;color:#65717d">プレビューを準備しています…</div>';
        status.textContent = '基本設計書プレビュー';
      }
    }catch(error){
      status.textContent = 'プレビュー同期待ち…';
    }finally{
      busy = false;
    }
  }
  sync();
  setInterval(sync, 250);
})();
</script>
</body>
</html>"""


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

    @app.post("/api/generate-word/stage")
    def stage_word(request: WordRequest) -> dict[str, str]:
        try:
            content, filename = words.generate(request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        token, _path = stage_bytes(content, ".docx")
        return {"token": token, "filename": filename}

    @app.post("/api/project/stage")
    def stage_project(request: ProjectStageRequest) -> dict[str, str]:
        try:
            content = build_project_archive(request.project)
            token, _path = stage_bytes(content, ".ddgproj")
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        filename = request.suggested_name.strip() or "案件.ddgproj"
        if not filename.lower().endswith(".ddgproj"):
            filename += ".ddgproj"
        return {"token": token, "filename": filename}

    @app.get("/api/project/staged/{token}")
    def staged_project(token: str) -> Response:
        try:
            path = staged_path(token, ".json")
            content = path.read_bytes()
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail="案件データが見つかりません。") from exc
        return Response(content, media_type="application/json; charset=utf-8")

    @app.post("/api/preview-state")
    def set_preview_state(request: PreviewStateRequest) -> dict[str, Any]:
        return update_preview_state(request.model_dump())

    @app.get("/api/preview-state")
    def preview_state() -> dict[str, Any]:
        return get_preview_state()

    @app.get("/preview-window", response_class=HTMLResponse)
    def preview_window() -> HTMLResponse:
        return HTMLResponse(_preview_window_html())

    @app.get("/local-bridge.js", response_class=FileResponse)
    def local_bridge() -> FileResponse:
        return FileResponse(resource_path(LOCAL_BRIDGE_FILENAME), media_type="application/javascript")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_desktop_html())

    return app


app = create_app()