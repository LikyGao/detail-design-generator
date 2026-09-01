from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .services.template_service import TemplateService
from .services.word_service import generate_word

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
DATA_ROOT = Path(os.environ.get("DETAIL_DESIGN_DATA_DIR", Path.home() / ".detail-design-generator" / "data"))
service = TemplateService(DATA_ROOT)
app = FastAPI(title="基本設計書生成ツール Local API")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:8765", "http://localhost:8765", "null"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])


class DocumentTypeRequest(BaseModel):
    document_type: str


class WordRequest(BaseModel):
    document_type: str
    client_name: str = ""
    project_name: str = ""
    version: str = "1.0"
    issue_date: str = ""
    project_no: str = "-"
    revision_history_json: object = "[]"
    chapters_json: object = "[]"
    output_filename: str = "基本設計書.docx"


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(ROOT / "基本設計書generator.html", media_type="text/html; charset=utf-8")


@app.post("/api/templates/register")
async def register_template(document_type: str = Form(...), template_file: UploadFile = File(...),
                            template_version: str = Form("")):
    try:
        if not (template_file.filename or "").lower().endswith(".docx"):
            raise ValueError("登録できるファイルは.docxのみです。")
        return service.register(document_type, template_file.filename or "template.docx",
                                await template_file.read(), template_version)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/template-data")
def template_data(request: DocumentTypeRequest):
    try:
        return service.get_data(request.document_type)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/generate-word")
def word(request: WordRequest):
    try:
        content, filename = generate_word(DATA_ROOT, request.model_dump())
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": disposition})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
