from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.docx_builder import MIME_DOCX
from tools.template_store import select_template


class DownloadCurrentTemplateTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        bundled = Path(__file__).resolve().parents[1] / "templates" / "基本設計書_template.docx"
        document_type = str(tool_parameters.get("document_type") or "").strip()
        template_version = str(tool_parameters.get("template_version") or "").strip()
        template_bytes, metadata = select_template(
            self.session.storage,
            bundled,
            document_type=document_type,
            template_version=template_version,
        )
        filename = str(metadata.get("filename") or "基本設計書_template.docx")
        yield self.create_blob_message(
            template_bytes,
            meta={"mime_type": MIME_DOCX, "filename": filename},
        )
        yield self.create_json_message({"template": metadata})
        yield self.create_text_message(
            f"標準テンプレートを出力しました: "
            f"{metadata.get('document_type', 'default')} / "
            f"{metadata.get('template_version', '-')} / {filename}"
        )
