from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File

from tools.template_store import (
    DEFAULT_DOCUMENT_TYPE,
    infer_template_version,
    register_typed_template,
)


class RegisterStandardTemplateTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        template_file = tool_parameters.get("template_file")
        if not isinstance(template_file, File):
            raise ValueError("標準テンプレートDOCXを指定してください。")

        filename = template_file.filename or "基本設計書_template.docx"
        raw_extension = str(template_file.extension or "").strip().lower()
        extension = raw_extension.lstrip(".")
        if not extension and "." in filename:
            extension = filename.rsplit(".", 1)[-1].strip().lower().lstrip(".")
        if extension != "docx":
            raise ValueError(
                f"登録できるファイルは.docxのみです。"
                f"（受信した拡張子: {raw_extension or '未設定'}）"
            )

        document_type = str(
            tool_parameters.get("document_type") or DEFAULT_DOCUMENT_TYPE
        ).strip()
        template_version = str(tool_parameters.get("template_version") or "").strip()
        if not template_version:
            template_version = infer_template_version(filename)

        result = register_typed_template(
            self.session.storage,
            template_bytes=template_file.blob,
            filename=filename,
            document_type=document_type,
            template_version=template_version,
        )
        metadata = result["metadata"]

        master_json_text = json.dumps(result["master_json"], ensure_ascii=False)
        chapter_list_json_text = json.dumps(
            result["chapter_list_json"], ensure_ascii=False
        )
        payload = {
            "success": True,
            "document_type": metadata["document_type"],
            "template_id": metadata["id"],
            "template_version": metadata["template_version"],
            "template": metadata,
            "master_json": result["master_json"],
            "chapter_list_json": result["chapter_list_json"],
            "master_json_text": master_json_text,
            "chapter_list_json_text": chapter_list_json_text,
            "section_content_summary": result["section_content_summary"],
            "warnings": result["warnings"],
        }
        yield self.create_variable_message("document_type", metadata["document_type"])
        yield self.create_variable_message("template_id", metadata["id"])
        yield self.create_variable_message("template_version", metadata["template_version"])
        yield self.create_variable_message("template", metadata)
        yield self.create_variable_message("master_json", result["master_json"])
        yield self.create_variable_message("chapter_list_json", result["chapter_list_json"])
        yield self.create_variable_message("master_json_text", master_json_text)
        yield self.create_variable_message("chapter_list_json_text", chapter_list_json_text)
        yield self.create_variable_message("section_content_summary", result["section_content_summary"])
        yield self.create_variable_message("warnings", result["warnings"])
        yield self.create_json_message(payload)
        yield self.create_text_message(
            "標準テンプレートを登録・解析しました: "
            f"{metadata['document_type']} / {metadata['template_version']} / "
            f"{metadata['filename']} / 章節{metadata['chapter_summary']['total_count']}件"
        )
