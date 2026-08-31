from __future__ import annotations

import io
import re
from typing import Any

from docx import Document
from docx.oxml.ns import qn


HEADING_STYLE_TO_LEVEL = {
    "Heading 1": 1,
    "Heading 2": 2,
    "Heading 3": 3,
}

_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_SKIP_BODY_STYLES = {
    "Caption",
    "TOC Heading",
    "Table of Figures",
    "Index Heading",
}


def _ascii_digits(value: str) -> str:
    return str(value or "").translate(_FULLWIDTH_DIGITS)


def _strip_expected_number_prefix(text: str, node_id: str, level: int) -> str:
    """Remove a visible numbering prefix only when it matches the generated node id.

    Word automatic numbering is normally not included in paragraph.text. Some templates,
    however, store the number as literal text. We remove only an exact expected prefix to
    avoid deleting meaningful numbers from the title.
    """
    title = str(text or "").strip()
    if not title:
        return ""

    normalized = _ascii_digits(title)
    expected_parts = node_id.split("-")
    if level == 1:
        candidates = [
            rf"^\s*{re.escape(expected_parts[0])}\s*[\.．、\-－―:]?\s+",
            rf"^\s*第\s*{re.escape(expected_parts[0])}\s*章\s*",
        ]
    else:
        joined = r"[\-－―\.．]".join(re.escape(part) for part in expected_parts)
        candidates = [rf"^\s*{joined}\s*[\.．、:]?\s+"]

    for pattern in candidates:
        match = re.match(pattern, normalized)
        if match:
            # Match indexes are safe because full-width digit translation does not change length.
            return title[match.end() :].strip()
    return title


def _first_child(element, tag: str):
    if element is None:
        return None
    return element.find(qn(tag))


def _numbering_values(paragraph) -> tuple[str, int] | None:
    """Return (numId, ilvl) from direct or paragraph-style numbering properties."""
    num_pr = None
    p_pr = paragraph._p.pPr
    if p_pr is not None:
        num_pr = p_pr.numPr

    if num_pr is None and paragraph.style is not None:
        style_p_pr = paragraph.style.element.pPr
        if style_p_pr is not None:
            num_pr = style_p_pr.numPr

    if num_pr is None:
        return None

    num_id_el = _first_child(num_pr, "w:numId")
    if num_id_el is None:
        return None
    num_id = str(num_id_el.get(qn("w:val")) or "").strip()
    if not num_id:
        return None

    ilvl_el = _first_child(num_pr, "w:ilvl")
    try:
        ilvl = int(ilvl_el.get(qn("w:val"))) if ilvl_el is not None else 0
    except (TypeError, ValueError):
        ilvl = 0
    return num_id, max(0, ilvl)


def _resolve_numbering_format(document, num_id: str, ilvl: int) -> tuple[str, str]:
    """Resolve Word numbering format and level text when numbering.xml is available."""
    try:
        numbering_root = document.part.numbering_part.element
    except Exception:
        return "", ""

    abstract_id = ""
    for num in numbering_root.findall(qn("w:num")):
        if str(num.get(qn("w:numId")) or "") != str(num_id):
            continue
        abstract_id_el = _first_child(num, "w:abstractNumId")
        if abstract_id_el is not None:
            abstract_id = str(abstract_id_el.get(qn("w:val")) or "")
        break
    if not abstract_id:
        return "", ""

    for abstract in numbering_root.findall(qn("w:abstractNum")):
        if str(abstract.get(qn("w:abstractNumId")) or "") != abstract_id:
            continue
        selected_level = None
        for level_el in abstract.findall(qn("w:lvl")):
            if str(level_el.get(qn("w:ilvl")) or "0") == str(ilvl):
                selected_level = level_el
                break
        if selected_level is None:
            return "", ""
        num_fmt_el = _first_child(selected_level, "w:numFmt")
        level_text_el = _first_child(selected_level, "w:lvlText")
        num_fmt = str(num_fmt_el.get(qn("w:val")) or "") if num_fmt_el is not None else ""
        level_text = (
            str(level_text_el.get(qn("w:val")) or "") if level_text_el is not None else ""
        )
        return num_fmt, level_text
    return "", ""


def _paragraph_structure(document, paragraph) -> dict[str, Any]:
    style_name = paragraph.style.name if paragraph.style is not None else ""
    numbering = _numbering_values(paragraph)
    num_id = ""
    list_level: int | None = None
    number_format = ""
    level_text = ""

    if numbering is not None:
        num_id, list_level = numbering
        number_format, level_text = _resolve_numbering_format(document, num_id, list_level)

    style_lower = style_name.lower()
    if numbering is not None:
        kind = "bullet" if number_format == "bullet" else "numbered"
    elif "bullet" in style_lower or "箇条" in style_name:
        kind = "bullet"
        list_level = 0
    elif "number" in style_lower or "番号" in style_name:
        kind = "numbered"
        list_level = 0
    else:
        kind = "paragraph"

    return {
        "style": style_name,
        "kind": kind,
        "list_level": list_level,
        "num_id": num_id,
        "number_format": number_format,
        "level_text": level_text,
    }


def _should_skip_body_paragraph(style_name: str, text: str) -> bool:
    style = str(style_name or "").strip()
    normalized = str(text or "").strip()
    if not normalized:
        return True
    if style in _SKIP_BODY_STYLES or style.startswith("TOC "):
        return True
    if "point" in style.lower():
        return True
    if re.fullmatch(r"(?i:point)\s*[!！]?", normalized) or normalized in {"ポイント", "ポイント！"}:
        return True
    return False


def _build_reference_text(paragraphs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    numbered_counters: dict[int, int] = {}
    for item in paragraphs:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        kind = str(item.get("kind") or "paragraph")
        level_raw = item.get("list_level")
        level = int(level_raw) if isinstance(level_raw, int) else 0
        indent = "  " * max(0, level)
        if kind == "bullet":
            lines.append(f"{indent}・{text}")
        elif kind == "numbered":
            numbered_counters[level] = numbered_counters.get(level, 0) + 1
            for deeper in [key for key in numbered_counters if key > level]:
                numbered_counters.pop(deeper, None)
            lines.append(f"{indent}{numbered_counters[level]}. {text}")
        else:
            numbered_counters.clear()
            lines.append(text)
    return "\n".join(lines)


def parse_template_chapters(template_bytes: bytes) -> dict[str, Any]:
    """Extract Heading 1-3 and ordinary body text under each heading.

    Tables, images, captions, and Point-only paragraphs are intentionally not extracted.
    Text inside Word tables is also excluded because only document-level paragraphs are read.
    """
    document = Document(io.BytesIO(template_bytes))

    roots: list[dict[str, Any]] = []
    flat: list[dict[str, Any]] = []
    section_contents: list[dict[str, Any]] = []
    section_by_id: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    counters = [0, 0, 0]
    parents: dict[int, dict[str, Any] | None] = {1: None, 2: None, 3: None}
    order = 0
    current_section_id: str | None = None
    skipped_body_count = 0

    for paragraph_index, paragraph in enumerate(document.paragraphs, start=1):
        style_name = paragraph.style.name if paragraph.style is not None else ""
        level = HEADING_STYLE_TO_LEVEL.get(style_name)

        if level is None:
            if current_section_id is None:
                continue
            text = str(paragraph.text or "").strip()
            if _should_skip_body_paragraph(style_name, text):
                if text:
                    skipped_body_count += 1
                continue
            section = section_by_id[current_section_id]
            structure = _paragraph_structure(document, paragraph)
            section["paragraphs"].append(
                {
                    "order": len(section["paragraphs"]) + 1,
                    "text": text,
                    **structure,
                }
            )
            continue

        raw_title = str(paragraph.text or "").strip()
        if not raw_title:
            warnings.append(
                f"段落{paragraph_index}: {style_name}ですがタイトルが空のためスキップしました。"
            )
            continue

        if level == 2 and parents[1] is None:
            warnings.append(
                f"段落{paragraph_index}: Heading 1より前のHeading 2「{raw_title}」をスキップしました。"
            )
            continue
        if level == 3 and (parents[1] is None or parents[2] is None):
            warnings.append(
                f"段落{paragraph_index}: 親Heading 2がないHeading 3「{raw_title}」をスキップしました。"
            )
            continue

        counters[level - 1] += 1
        for deeper in range(level, 3):
            counters[deeper] = 0

        if level == 1:
            node_id = str(counters[0])
        elif level == 2:
            node_id = f"{counters[0]}-{counters[1]}"
        else:
            node_id = f"{counters[0]}-{counters[1]}-{counters[2]}"

        title = _strip_expected_number_prefix(raw_title, node_id, level) or raw_title
        parent_id = None
        if level == 2 and parents[1] is not None:
            parent_id = str(parents[1]["id"])
        elif level == 3 and parents[2] is not None:
            parent_id = str(parents[2]["id"])

        node: dict[str, Any] = {
            "id": node_id,
            "source_template_number": node_id,
            "title": title,
            "level": level,
            "selected": True,
            "children": [],
        }

        if level == 1:
            roots.append(node)
            parents[1] = node
            parents[2] = None
            parents[3] = None
        elif level == 2:
            assert parents[1] is not None
            parents[1]["children"].append(node)
            parents[2] = node
            parents[3] = None
        else:
            assert parents[2] is not None
            parents[2]["children"].append(node)
            parents[3] = node

        order += 1
        flat.append(
            {
                "id": node_id,
                "source_template_number": node_id,
                "title": title,
                "level": level,
                "parent_id": parent_id,
                "order": order,
                "selected": True,
            }
        )
        section = {
            "id": node_id,
            "source_template_number": node_id,
            "title": title,
            "level": level,
            "parent_id": parent_id,
            "order": order,
            "paragraphs": [],
            "text": "",
            "reference_text": "",
        }
        section_contents.append(section)
        section_by_id[node_id] = section
        current_section_id = node_id

    if not roots:
        raise ValueError("Heading 1～3から章節を抽出できませんでした。Heading 1が必要です。")

    body_paragraph_count = 0
    body_character_count = 0
    sections_with_text = 0
    for section in section_contents:
        paragraphs = section["paragraphs"]
        section["text"] = "\n".join(str(item["text"]) for item in paragraphs)
        section["reference_text"] = _build_reference_text(paragraphs)
        body_paragraph_count += len(paragraphs)
        body_character_count += len(section["text"])
        if section["text"]:
            sections_with_text += 1

    return {
        "master_json": roots,
        "chapter_list_json": flat,
        "section_contents_json": section_contents,
        "warnings": warnings,
        "summary": {
            "heading_1_count": sum(1 for item in flat if item["level"] == 1),
            "heading_2_count": sum(1 for item in flat if item["level"] == 2),
            "heading_3_count": sum(1 for item in flat if item["level"] == 3),
            "total_count": len(flat),
            "sections_with_text": sections_with_text,
            "body_paragraph_count": body_paragraph_count,
            "body_character_count": body_character_count,
            "skipped_body_paragraph_count": skipped_body_count,
        },
    }
