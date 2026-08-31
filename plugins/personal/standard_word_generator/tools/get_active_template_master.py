from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.template_store import get_registered_master, normalize_document_type


class GetActiveTemplateMasterTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        document_type = normalize_document_type(tool_parameters.get("document_type"))
        result = get_registered_master(self.session.storage, document_type)
        payload = {
            **result,
            "template_id": str(result["template"].get("id") or ""),
            "master_json_text": json.dumps(result["master_json"], ensure_ascii=False),
            "chapter_list_json_text": json.dumps(
                result["chapter_list_json"], ensure_ascii=False
            ),
        }
        yield self.create_variable_message("document_type", result["document_type"])
        yield self.create_variable_message("template_id", payload["template_id"])
        yield self.create_variable_message("template_version", result["template_version"])
        yield self.create_variable_message("template", result["template"])
        yield self.create_variable_message("master_json", result["master_json"])
        yield self.create_variable_message("chapter_list_json", result["chapter_list_json"])
        yield self.create_variable_message("master_json_text", payload["master_json_text"])
        yield self.create_variable_message(
            "chapter_list_json_text", payload["chapter_list_json_text"]
        )
        yield self.create_json_message(payload)
        yield self.create_text_message(
            f"章節Masterを取得しました: {document_type} / "
            f"{result['template_version']} / {len(result['chapter_list_json'])}件"
        )
