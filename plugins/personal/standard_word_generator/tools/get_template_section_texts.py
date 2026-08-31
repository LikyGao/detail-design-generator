from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.template_store import get_registered_section_contents, normalize_document_type


def _collect_section_ids(value: Any, output: list[str]) -> None:
    if isinstance(value, str):
        section_id = value.strip()
        if section_id:
            output.append(section_id)
        return
    if isinstance(value, list):
        for item in value:
            _collect_section_ids(item, output)
        return
    if isinstance(value, dict):
        section_id = str(
            value.get("id")
            or value.get("section_id")
            or value.get("chapter_id")
            or value.get("source_template_number")
            or ""
        ).strip()
        if section_id:
            output.append(section_id)
        children = value.get("children")
        if isinstance(children, list):
            _collect_section_ids(children, output)


def _parse_section_ids(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, dict)):
        value = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return []
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = [part.strip() for part in text.split(",") if part.strip()]

    collected: list[str] = []
    _collect_section_ids(value, collected)
    deduplicated: list[str] = []
    seen: set[str] = set()
    for section_id in collected:
        if section_id not in seen:
            seen.add(section_id)
            deduplicated.append(section_id)
    return deduplicated


def _combined_reference_text(sections: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for section in sections:
        section_id = str(section.get("id") or "")
        title = str(section.get("title") or "")
        body = str(section.get("reference_text") or section.get("text") or "").strip()
        header = f"[{section_id}] {title}".strip()
        chunks.append(f"{header}\n{body}".rstrip())
    return "\n\n".join(chunks)


class GetTemplateSectionTextsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        document_type = normalize_document_type(tool_parameters.get("document_type"))
        template_id = str(tool_parameters.get("template_id") or "").strip()
        template_version = str(tool_parameters.get("template_version") or "").strip()
        requested_ids = _parse_section_ids(tool_parameters.get("section_ids_json"))

        result = get_registered_section_contents(
            self.session.storage,
            document_type=document_type,
            template_id=template_id,
            template_version=template_version,
        )
        all_sections = result["section_contents"]
        by_id = {str(item.get("id") or ""): item for item in all_sections}

        if requested_ids:
            requested_set = set(requested_ids)
            sections = [item for item in all_sections if str(item.get("id") or "") in requested_set]
            missing_section_ids = [section_id for section_id in requested_ids if section_id not in by_id]
        else:
            sections = all_sections
            missing_section_ids = []

        section_contents_json_text = json.dumps(sections, ensure_ascii=False)
        reference_text = _combined_reference_text(sections)
        payload = {
            "success": True,
            "document_type": result["document_type"],
            "template_id": result["template_id"],
            "template_version": result["template_version"],
            "template": result["template"],
            "requested_section_ids": requested_ids,
            "returned_section_count": len(sections),
            "missing_section_ids": missing_section_ids,
            "section_contents": sections,
            "section_contents_json_text": section_contents_json_text,
            "reference_text": reference_text,
        }

        yield self.create_variable_message("document_type", result["document_type"])
        yield self.create_variable_message("template_id", result["template_id"])
        yield self.create_variable_message("template_version", result["template_version"])
        yield self.create_variable_message("template", result["template"])
        yield self.create_variable_message("requested_section_ids", requested_ids)
        yield self.create_variable_message("returned_section_count", len(sections))
        yield self.create_variable_message("missing_section_ids", missing_section_ids)
        yield self.create_variable_message("section_contents", sections)
        yield self.create_variable_message("section_contents_json_text", section_contents_json_text)
        yield self.create_variable_message("reference_text", reference_text)
        yield self.create_json_message(payload)
        yield self.create_text_message(
            "標準テンプレート章節本文を取得しました: "
            f"{result['document_type']} / {result['template_version']} / {len(sections)}件"
        )
