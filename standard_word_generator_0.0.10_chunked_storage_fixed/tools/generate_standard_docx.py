from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.docx_builder import MIME_DOCX, generate_standard_docx, parse_json_array
from tools.template_store import select_template


class GenerateStandardDocxTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        bundled = Path(__file__).resolve().parents[1] / "templates" / "基本設計書_template.docx"
        document_type = str(tool_parameters.get("document_type") or "").strip()
        template_id = str(tool_parameters.get("template_id") or "").strip()
        template_version = str(tool_parameters.get("template_version") or "").strip()
        template_bytes, template_metadata = select_template(
            self.session.storage,
            bundled,
            document_type=document_type,
            template_version=template_version,
            template_id=template_id,
        )

        output_filename = str(tool_parameters.get("output_filename") or "基本設計書.docx").strip()
        if not output_filename.lower().endswith(".docx"):
            output_filename += ".docx"

        revisions = parse_json_array(
            tool_parameters.get("revision_history_json"), "revision_history_json"
        )
        chapters = parse_json_array(tool_parameters.get("chapters_json"), "chapters_json")

        docx_bytes = generate_standard_docx(
            template_bytes,
            client_name=str(tool_parameters.get("client_name") or "株式会社〇〇 様"),
            project_name=str(tool_parameters.get("project_name") or "プロジェクト名"),
            version=str(tool_parameters.get("version") or "1.0"),
            issue_date=str(tool_parameters.get("issue_date") or ""),
            project_no=str(tool_parameters.get("project_no") or "-"),
            file_name=output_filename,
            revisions=revisions,
            chapters=chapters,
        )

        yield self.create_blob_message(
            docx_bytes,
            meta={"mime_type": MIME_DOCX, "filename": output_filename},
        )
        yield self.create_json_message(
            {
                "success": True,
                "output_filename": output_filename,
                "document_type": template_metadata.get("document_type") or document_type or "full",
                "template_id": template_metadata.get("id") or "",
                "template_version": template_metadata.get("template_version") or "",
                "template": template_metadata,
            }
        )
        yield self.create_text_message(
            f"Generated: {output_filename} "
            f"(template: {template_metadata.get('document_type', 'default')} / "
            f"{template_metadata.get('template_version', '-')} / "
            f"{template_metadata.get('filename', '-')})"
        )
