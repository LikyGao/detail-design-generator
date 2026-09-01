from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "personal" / "standard_word_generator"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from tools.template_store import (  # noqa: E402
    get_registered_master,
    get_registered_section_contents,
    infer_template_version,
    register_typed_template,
)

from .storage import FileStorage


class TemplateService:
    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.storage = FileStorage(data_root)

    def register(self, document_type: str, filename: str, content: bytes, version: str = "") -> dict[str, Any]:
        result = register_typed_template(
            self.storage, template_bytes=content, filename=filename,
            document_type=document_type, template_version=version or infer_template_version(filename),
        )
        metadata = result["metadata"]
        directory = self.data_root / document_type
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "template.docx").write_bytes(content)
        (directory / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        (directory / "master.json").write_text(json.dumps(result["master_json"], ensure_ascii=False, indent=2), encoding="utf-8")
        (directory / "chapter_list.json").write_text(json.dumps(result["chapter_list_json"], ensure_ascii=False, indent=2), encoding="utf-8")
        sections = get_registered_section_contents(self.storage, document_type=document_type)["section_contents"]
        (directory / "section_contents.json").write_text(json.dumps(sections, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"success": True, "document_type": document_type, "template_id": metadata["id"],
                "template_version": metadata["template_version"], **result}

    def get_data(self, document_type: str) -> dict[str, Any]:
        master = get_registered_master(self.storage, document_type)
        sections = get_registered_section_contents(self.storage, document_type=document_type)
        values = sections["section_contents"]
        reference = "\n\n".join(
            f"[{item.get('id', '')}] {item.get('title', '')}\n{item.get('reference_text') or item.get('text') or ''}".rstrip()
            for item in values
        )
        return {
            "document_type": document_type,
            "template_id": str(master["template"].get("id") or ""),
            "template_version": master["template_version"],
            "master_json": master["master_json"],
            "chapter_list_json": master["chapter_list_json"],
            "section_contents_json": values,
            "section_contents": values,
            "reference_text": reference,
            "returned_section_count": len(values),
        }
