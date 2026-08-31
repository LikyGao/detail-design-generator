from __future__ import annotations

import base64
import io
import json
import re
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Twips

from tools.chapter_parser import _paragraph_structure
from tools.paragraph_numbering import calculate_paragraph_prefix


MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PARAGRAPH_STYLES = {f"level_{level}" for level in range(7)}
PARAGRAPH_FALLBACK_INDENTS = {0: 0, 1: 360, 2: 720, 3: 1080, 4: 1440, 5: 1800, 6: 2160}
PARAGRAPH_PREFIX_SEPARATOR = " "


def _replace_paragraph_text(paragraph, text: str) -> None:
    """Replace visible text while retaining the first run's formatting."""
    text = str(text or "")
    if not paragraph.runs:
        paragraph.add_run(text)
        return
    paragraph.runs[0].text = text
    for run in paragraph.runs[1:]:
        run.text = ""


def _replace_cell_text(cell, text: str) -> None:
    """Replace cell text while retaining the cell and first paragraph formatting."""
    text = str(text or "")
    if not cell.paragraphs:
        cell.add_paragraph(text)
        return
    first = cell.paragraphs[0]
    _replace_paragraph_text(first, text)
    for paragraph in cell.paragraphs[1:]:
        _replace_paragraph_text(paragraph, "")


def _set_update_fields(document: Document) -> None:
    settings = document.settings._element
    current = settings.find(qn("w:updateFields"))
    if current is None:
        current = OxmlElement("w:updateFields")
        settings.append(current)
    current.set(qn("w:val"), "true")


def _mark_all_fields_dirty(document: Document) -> None:
    """Mark template TOC fields and newly inserted caption fields for refresh."""
    root = document._element
    for field in root.xpath(".//w:fldSimple"):
        field.set(qn("w:dirty"), "true")
    for field_char in root.xpath(".//w:fldChar"):
        if field_char.get(qn("w:fldCharType")) == "begin":
            field_char.set(qn("w:dirty"), "true")


def _remove_existing_body(document: Document) -> None:
    """Remove template sample body beginning at the first Heading 1 paragraph."""
    start_element = None
    for paragraph in document.paragraphs:
        if paragraph.style and paragraph.style.name == "Heading 1":
            start_element = paragraph._element
            break
    if start_element is None:
        return

    body = document._element.body
    children = list(body)
    try:
        start_index = children.index(start_element)
    except ValueError:
        return

    for element in children[start_index:]:
        if element.tag == qn("w:sectPr"):
            continue
        body.remove(element)


def _fill_cover(
    document: Document,
    client_name: str,
    project_name: str,
    version: str,
    issue_date: str,
    file_name: str,
    project_no: str,
) -> None:
    title_paragraphs = [p for p in document.paragraphs if p.style and p.style.name == "Title"]
    if len(title_paragraphs) >= 2:
        _replace_paragraph_text(title_paragraphs[0], client_name)
        _replace_paragraph_text(title_paragraphs[1], project_name)

    if document.tables:
        property_table = document.tables[0]
        values = [version, issue_date, file_name, project_no]
        for row_index, value in enumerate(values):
            if value is None or row_index >= len(property_table.rows):
                continue
            cells = property_table.rows[row_index].cells
            if len(cells) >= 3:
                _replace_cell_text(cells[2], value)


def _fill_revision_history(document: Document, revisions: list[dict[str, Any]]) -> None:
    if len(document.tables) < 2:
        return
    table = document.tables[1]
    if len(table.rows) < 2:
        return

    base_row = deepcopy(table.rows[1]._tr)
    tbl = table._tbl
    while len(table.rows) > 1:
        tbl.remove(table.rows[-1]._tr)

    for item in revisions:
        tbl.append(deepcopy(base_row))
        row = table.rows[-1]
        values = [
            item.get("issue_date") or item.get("date") or "",
            item.get("version") or "",
            item.get("editor") or item.get("author") or "",
            item.get("description") or item.get("content") or "",
        ]
        for cell, value in zip(row.cells, values):
            _replace_cell_text(cell, value)


def _flatten_selected(nodes: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        if node.get("selected", True):
            yield node
            yield from _flatten_selected(node.get("children") or [])


def _append_simple_field(paragraph, instruction: str, result_text: str) -> None:
    """Append a simple Word field and keep a visible fallback result."""
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), instruction)
    field.set(qn("w:dirty"), "true")

    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text.text = str(result_text or "")
    run.append(text)
    field.append(run)
    paragraph._p.append(field)


def _caption_title(block: dict[str, Any], fallback_title: str) -> str:
    explicit = str(block.get("caption") or block.get("title") or "").strip()
    if explicit:
        return explicit

    file_name = str(block.get("fileName") or block.get("file_name") or "").strip()
    if file_name:
        stem = Path(file_name).stem.strip()
        if stem:
            return stem

    fallback = str(fallback_title or "").strip()
    return fallback or "タイトル未設定"


def _add_caption(
    document: Document,
    kind: str,
    caption: str,
    chapter_number: str,
    sequence_number: int,
) -> None:
    """Add a real Word caption using STYLEREF + SEQ fields.

    The template's table-of-figures fields can only discover native SEQ
    fields. Plain text styled as Caption is not enough.
    """
    paragraph = document.add_paragraph(style="Caption")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run(f"【{kind} ")
    _append_simple_field(paragraph, r"STYLEREF 1 \s", chapter_number)
    paragraph.add_run("-")
    _append_simple_field(
        paragraph,
        rf"SEQ {kind} \* ARABIC \s 1",
        str(sequence_number),
    )
    if caption:
        paragraph.add_run(f"：{caption}")
    paragraph.add_run("】")


def _add_table(document: Document, block: dict[str, Any]) -> None:
    headers = [str(v or "") for v in block.get("headers") or []]
    rows = block.get("rows") or []
    col_count = max(len(headers), max((len(r or []) for r in rows), default=0), 1)
    table = document.add_table(rows=1, cols=col_count)
    table.style = "Table Grid"

    if headers:
        for index in range(col_count):
            value = headers[index] if index < len(headers) else ""
            _replace_cell_text(table.rows[0].cells[index], value)
            for run in table.rows[0].cells[index].paragraphs[0].runs:
                run.bold = True
                run.font.name = "Meiryo UI"
    else:
        tbl = table._tbl
        tbl.remove(table.rows[0]._tr)

    for source_row in rows:
        target = table.add_row()
        source_row = source_row or []
        for index in range(col_count):
            value = source_row[index] if index < len(source_row) else ""
            _replace_cell_text(target.cells[index], value)


def _image_bytes(data_url: str) -> bytes:
    if not data_url:
        return b""
    if "," in data_url and data_url.startswith("data:"):
        data_url = data_url.split(",", 1)[1]
    return base64.b64decode(data_url)


def _add_figure(document: Document, block: dict[str, Any]) -> None:
    raw = _image_bytes(str(block.get("imageData") or block.get("image_data") or ""))
    if not raw:
        paragraph = document.add_paragraph("（画像未挿入）")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run().add_picture(io.BytesIO(raw), width=Inches(6.1))


def _collect_paragraph_prototypes(document: Document) -> dict[str, Any]:
    """Capture template-native list paragraph properties before sample body removal."""
    result: dict[str, Any] = {}
    for paragraph in document.paragraphs:
        if paragraph.style and paragraph.style.name in {"Heading 1", "Heading 2", "Heading 3"}:
            continue
        structure = _paragraph_structure(document, paragraph)
        paragraph_style = structure.get("paragraph_style")
        if paragraph_style in PARAGRAPH_STYLES - {"level_0"} and paragraph._p.pPr is not None:
            result.setdefault(paragraph_style, deepcopy(paragraph._p.pPr))
    return result


def _remove_numbering_properties(paragraph_properties) -> None:
    """Remove template numbering while retaining its other paragraph formatting."""
    if paragraph_properties is None:
        return
    num_properties = paragraph_properties.find(qn("w:numPr"))
    if num_properties is not None:
        paragraph_properties.remove(num_properties)


def _valid_indent_twips(value: Any) -> int | None:
    """Return a non-negative Word indent in twips, or None when unavailable."""
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        twips = int(value)
    except (TypeError, ValueError):
        return None
    return twips if twips >= 0 else None


def _restore_body_indents(paragraph, block: dict[str, Any], paragraph_style: str) -> None:
    """Restore indents made ineffective when the template numPr is removed."""
    left_indent = _valid_indent_twips(block.get("left_indent_twips"))
    if left_indent is None:
        left_indent = PARAGRAPH_FALLBACK_INDENTS[int(paragraph_style[-1])]
    paragraph.paragraph_format.left_indent = Twips(left_indent)

    hanging_indent = _valid_indent_twips(block.get("hanging_indent_twips"))
    first_line_indent = _valid_indent_twips(block.get("first_line_indent_twips"))
    if hanging_indent is not None:
        paragraph.paragraph_format.first_line_indent = Twips(-hanging_indent)
    elif first_line_indent is not None:
        paragraph.paragraph_format.first_line_indent = Twips(first_line_indent)


def _add_body_paragraph(document: Document, block: dict[str, Any], prototypes: dict[str, Any],
                        counters: dict[int, int]) -> None:
    paragraph_style = str(block.get("paragraph_style") or "level_0")
    if paragraph_style not in PARAGRAPH_STYLES:
        paragraph_style = "level_0"
    text = str(block.get("text") or "").replace("\r\n", "\n").replace("\r", "\n")
    paragraph = document.add_paragraph(style="Normal")
    prototype = prototypes.get(paragraph_style)
    if prototype is not None:
        if paragraph._p.pPr is not None:
            paragraph._p.remove(paragraph._p.pPr)
        paragraph_properties = deepcopy(prototype)
        _remove_numbering_properties(paragraph_properties)
        paragraph._p.insert(0, paragraph_properties)
        # A prototype can point at a list style whose numPr lives in styles.xml.
        # Keep the copied direct formatting, but use a non-list paragraph style so
        # literal prefixes are not combined with inherited automatic numbering.
        paragraph.style = "Normal"

    _restore_body_indents(paragraph, block, paragraph_style)
    prefix = calculate_paragraph_prefix(paragraph_style, counters)
    separator = PARAGRAPH_PREFIX_SEPARATOR if prefix and text else ""
    paragraph.add_run(f"{prefix}{separator}{text}")


def _add_blocks(
    document: Document,
    blocks: list[dict[str, Any]],
    *,
    chapter_number: str,
    section_title: str,
    caption_counters: dict[str, int],
    paragraph_prototypes: dict[str, Any],
) -> None:
    paragraph_counters: dict[int, int] = {}
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "paragraph")
        if block_type == "paragraph":
            _add_body_paragraph(document, block, paragraph_prototypes, paragraph_counters)
        elif block_type == "table":
            caption_counters["表"] += 1
            _add_caption(
                document,
                "表",
                _caption_title(block, section_title),
                chapter_number,
                caption_counters["表"],
            )
            _add_table(document, block)
            document.add_paragraph("")
        elif block_type == "figure":
            caption_counters["図"] += 1
            _add_caption(
                document,
                "図",
                _caption_title(block, section_title),
                chapter_number,
                caption_counters["図"],
            )
            _add_figure(document, block)
            document.add_paragraph("")
        elif block_type == "table_placeholder":
            caption_counters["表"] += 1
            _add_caption(
                document,
                "表",
                _caption_title(block, section_title),
                chapter_number,
                caption_counters["表"],
            )
            paragraph = document.add_paragraph("（表は別途作成）")
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif block_type == "figure_placeholder":
            caption_counters["図"] += 1
            _add_caption(
                document,
                "図",
                _caption_title(block, section_title),
                chapter_number,
                caption_counters["図"],
            )
            paragraph = document.add_paragraph("（図は別途作成）")
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _chapter_number_from_node(node: dict[str, Any], fallback: int) -> str:
    display = str(node.get("display_number") or "").strip()
    if display:
        match = re.match(r"^([0-9０-９]+)", display)
        if match:
            return match.group(1)
    source = str(node.get("source_template_number") or "").strip()
    if source:
        match = re.match(r"^([0-9０-９]+)", source)
        if match:
            return match.group(1)
    return str(fallback)


def _add_chapters(document: Document, chapters: list[dict[str, Any]], paragraph_prototypes: dict[str, Any]) -> None:
    first_level_one = True
    chapter_index = 0
    current_chapter_number = "1"
    caption_counters = {"表": 0, "図": 0}

    for node in _flatten_selected(chapters):
        level = int(node.get("level") or 1)
        level = min(max(level, 1), 3)
        if level == 1:
            chapter_index += 1
            current_chapter_number = _chapter_number_from_node(node, chapter_index)
            caption_counters = {"表": 0, "図": 0}
            if not first_level_one:
                document.add_page_break()
            first_level_one = False

        title = str(node.get("title") or "(無題)")
        document.add_paragraph(title, style=f"Heading {level}")
        _add_blocks(
            document,
            node.get("blocks") or [],
            chapter_number=current_chapter_number,
            section_title=title,
            caption_counters=caption_counters,
            paragraph_prototypes=paragraph_prototypes,
        )


def parse_json_array(value: Any, field_name: str) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        result = value
    else:
        try:
            result = json.loads(str(value))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} is not valid JSON: {exc}") from exc
    if not isinstance(result, list):
        raise ValueError(f"{field_name} must be a JSON array")
    return result


def generate_standard_docx(
    template_source: bytes | bytearray | str | Path,
    *,
    client_name: str,
    project_name: str,
    version: str = "1.0",
    issue_date: str = "",
    project_no: str = "-",
    file_name: str = "基本設計書.docx",
    revisions: list[dict[str, Any]] | None = None,
    chapters: list[dict[str, Any]] | None = None,
) -> bytes:
    issue_date = issue_date or date.today().strftime("%Y/%m/%d")
    if isinstance(template_source, (bytes, bytearray)):
        document = Document(io.BytesIO(bytes(template_source)))
    else:
        document = Document(str(template_source))
    _fill_cover(document, client_name, project_name, version, issue_date, file_name, project_no)
    _fill_revision_history(document, revisions or [])
    paragraph_prototypes = _collect_paragraph_prototypes(document)
    _remove_existing_body(document)
    _add_chapters(document, chapters or [], paragraph_prototypes)
    _mark_all_fields_dirty(document)
    _set_update_fields(document)

    output = io.BytesIO()
    document.save(output)
    return output.getvalue()
