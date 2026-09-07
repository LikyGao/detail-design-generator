from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# In a source checkout, expose the latest plugin core as a normal Python package.
# PyInstaller receives the same path via the .spec file, so the frozen executable
# imports the bundled modules directly and does not depend on the Dify Plugin SDK.
if not getattr(sys, "frozen", False):
    repo_root = Path(__file__).resolve().parents[2]
    plugin_root = repo_root / "plugins" / "personal" / "standard_word_generator"
    if str(plugin_root) not in sys.path:
        sys.path.insert(0, str(plugin_root))

from tools.template_store import (  # noqa: E402
    get_registered_master,
    get_registered_section_contents,
    get_registered_template,
    infer_template_version,
    normalize_document_type,
    register_typed_template,
)

from .storage import FileStorage


# Local desktop versions before the paragraph-style fixes reused the same
# ~/.detail-design-generator/data directory. Their cached section_contents can
# therefore survive an EXE upgrade and re-introduce old Style0-4 parsing bugs.
# Bump this whenever the canonical template parser semantics change.
LOCAL_TEMPLATE_PARSE_SCHEMA = 2
LOCAL_TEMPLATE_PARSE_SCHEMA_FIELD = "local_template_parse_schema"


class TemplateService:
    """Local adapter around the current standard_word_generator template core."""

    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)
        self.storage = FileStorage(self.data_root)

    def _directory(self, document_type: str) -> Path:
        return self.data_root / normalize_document_type(document_type)

    def _read_mirror_metadata(self, document_type: str) -> dict[str, Any]:
        path = self._directory(document_type) / "metadata.json"
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _cache_is_current(self, document_type: str) -> bool:
        metadata = self._read_mirror_metadata(document_type)
        try:
            schema = int(metadata.get(LOCAL_TEMPLATE_PARSE_SCHEMA_FIELD) or 0)
        except (TypeError, ValueError):
            schema = 0
        return schema >= LOCAL_TEMPLATE_PARSE_SCHEMA

    def _ensure_current_parse(self, document_type: str) -> bool:
        """Reparse an old local cache with the current paragraph-style parser.

        Old local builds (notably the pre-desktop branch based on the old plugin)
        used the same data directory as the current EXE. The DOCX itself is still
        correct, but cached master/section JSON can contain the pre-fix Style0-4
        classification. Re-registering the same bytes is deterministic: the
        template SHA/id and user-facing version remain unchanged while all parsed
        paragraph metadata is refreshed.
        """
        normalized = normalize_document_type(document_type)
        if self._cache_is_current(normalized):
            return False

        directory = self._directory(normalized)
        metadata = self._read_mirror_metadata(normalized)
        template_path = directory / "template.docx"

        if template_path.exists():
            try:
                content = template_path.read_bytes()
            except OSError as exc:
                raise ValueError(f"{normalized} の標準テンプレートを再解析できません。") from exc
        else:
            try:
                content, stored_metadata = get_registered_template(
                    self.storage, document_type=normalized
                )
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(f"{normalized} の標準テンプレートを再解析できません。") from exc
            if isinstance(stored_metadata, dict):
                merged = dict(stored_metadata)
                merged.update(metadata)
                metadata = merged

        filename = str(metadata.get("filename") or f"{normalized}_template.docx")
        version = str(metadata.get("template_version") or "").strip()
        self.register(
            normalized,
            filename,
            content,
            version or infer_template_version(filename),
        )
        return True

    def register(
        self,
        document_type: str,
        filename: str,
        content: bytes,
        version: str = "",
    ) -> dict[str, Any]:
        normalized = normalize_document_type(document_type)
        result = register_typed_template(
            self.storage,
            template_bytes=content,
            filename=filename,
            document_type=normalized,
            template_version=version or infer_template_version(filename),
        )
        metadata = result["metadata"]

        # Keep human-readable mirrors next to the KV storage for support/debugging.
        directory = self._directory(normalized)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "template.docx").write_bytes(content)
        mirror_metadata = dict(metadata)
        mirror_metadata[LOCAL_TEMPLATE_PARSE_SCHEMA_FIELD] = LOCAL_TEMPLATE_PARSE_SCHEMA
        (directory / "metadata.json").write_text(
            json.dumps(mirror_metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (directory / "master.json").write_text(
            json.dumps(result["master_json"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (directory / "chapter_list.json").write_text(
            json.dumps(result["chapter_list_json"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        sections = get_registered_section_contents(
            self.storage, document_type=normalized
        )["section_contents"]
        (directory / "section_contents.json").write_text(
            json.dumps(sections, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return {
            "success": True,
            "document_type": normalized,
            "template_id": metadata["id"],
            "template_version": metadata["template_version"],
            "local_template_parse_schema": LOCAL_TEMPLATE_PARSE_SCHEMA,
            **result,
        }

    def get_status(self, document_type: str) -> dict[str, Any]:
        """Return only small registration metadata for the template manager UI.

        The template-manager modal previously called get_data(), which serializes the
        complete master/section/reference payload. Large production templates can make
        WebView2 parse megabytes of JSON just to display version/count, temporarily
        making the desktop window appear hung. The local registration mirror already
        contains everything required for this status view.

        Deliberately do not trigger a potentially expensive migration here; stale caches
        are reparsed on the next real /api/template-data load instead.
        """
        normalized = normalize_document_type(document_type)
        metadata_path = self._directory(normalized) / "metadata.json"
        if not metadata_path.exists():
            raise ValueError(f"{normalized} の標準テンプレートは未登録です。")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{normalized} のテンプレート登録情報を読み込めません。") from exc
        if not isinstance(metadata, dict):
            raise ValueError(f"{normalized} のテンプレート登録情報が不正です。")

        summary = metadata.get("section_content_summary")
        if not isinstance(summary, dict):
            summary = {}
        section_count = summary.get("section_count")
        if section_count is None:
            chapter_summary = metadata.get("chapter_summary")
            if isinstance(chapter_summary, dict):
                section_count = chapter_summary.get("total_count")

        return {
            "registered": True,
            "document_type": normalized,
            "template_id": str(metadata.get("id") or ""),
            "template_version": str(metadata.get("template_version") or ""),
            "returned_section_count": int(section_count or 0),
            "updated_at": str(metadata.get("updated_at") or ""),
            "filename": str(metadata.get("filename") or ""),
            "parser_cache_current": self._cache_is_current(normalized),
        }

    def get_data(self, document_type: str) -> dict[str, Any]:
        normalized = normalize_document_type(document_type)
        reparsed = self._ensure_current_parse(normalized)
        master = get_registered_master(self.storage, normalized)
        sections = get_registered_section_contents(
            self.storage, document_type=normalized
        )
        values = sections["section_contents"]
        reference = "\n\n".join(
            f"[{item.get('id', '')}] {item.get('title', '')}\n"
            f"{item.get('reference_text') or item.get('text') or ''}".rstrip()
            for item in values
        )
        return {
            "document_type": normalized,
            "template_id": str(master["template"].get("id") or ""),
            "template_version": master["template_version"],
            "master_json": master["master_json"],
            "chapter_list_json": master["chapter_list_json"],
            "section_contents_json": values,
            "section_contents": values,
            "reference_text": reference,
            "returned_section_count": len(values),
            "local_template_parse_schema": LOCAL_TEMPLATE_PARSE_SCHEMA,
            "template_cache_reparsed": reparsed,
        }
