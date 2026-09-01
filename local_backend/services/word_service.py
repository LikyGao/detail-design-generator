from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "personal" / "standard_word_generator"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from tools.docx_builder import generate_standard_docx, parse_json_array  # noqa: E402
from tools.template_store import get_registered_template  # noqa: E402

from .storage import FileStorage


def generate_word(data_root: Path, payload: dict[str, Any]) -> tuple[bytes, str]:
    document_type = str(payload.get("document_type") or "")
    template, _ = get_registered_template(FileStorage(data_root), document_type=document_type)
    filename = str(payload.get("output_filename") or "基本設計書.docx")
    if not filename.lower().endswith(".docx"):
        filename += ".docx"
    content = generate_standard_docx(
        template,
        client_name=str(payload.get("client_name") or "株式会社〇〇 様"),
        project_name=str(payload.get("project_name") or "プロジェクト名"),
        version=str(payload.get("version") or "1.0"), issue_date=str(payload.get("issue_date") or ""),
        project_no=str(payload.get("project_no") or "-"), file_name=filename,
        revisions=parse_json_array(payload.get("revision_history_json"), "revision_history_json"),
        chapters=parse_json_array(payload.get("chapters_json"), "chapters_json"),
    )
    return content, filename
