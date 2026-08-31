from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.template_store import get_template_status


class GetTemplateStatusTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        bundled = Path(__file__).resolve().parents[1] / "templates" / "基本設計書_template.docx"
        status = get_template_status(self.session.storage, bundled)
        active = status["active_template"]
        yield self.create_variable_message("active_template", status["active_template"])
        yield self.create_variable_message("templates", status["templates"])
        yield self.create_variable_message("registered_count", status["registered_count"])
        yield self.create_json_message(status)
        yield self.create_text_message(
            f"登録済みテンプレート: {status['registered_count']} / 4。"
            f"既定選択: {active.get('document_type', 'legacy')} / "
            f"{active.get('template_version', '-')} / {active.get('filename', '-')}"
        )
