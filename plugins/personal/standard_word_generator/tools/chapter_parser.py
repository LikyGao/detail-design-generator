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


def _style_chain(paragraph) -> list[Any]:
    """Return the paragraph style and all its basedOn ancestors, without looping."""
    styles: list[Any] = []
    style = paragraph.style
    seen: set[str] = set()
    while style is not None:
        style_id = str(style.style_id or "")
        if style_id in seen:
            break
        seen.add(style_id)
        styles.append(style)
        style = style.base_style
    return styles


def _numbering_roots(document) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    part = getattr(document, "part", document)
    root = part.numbering_part.element
    nums = {str(n.get(qn("w:numId")) or ""): n for n in root.findall(qn("w:num"))}
    abstracts = {
        str(a.get(qn("w:abstractNumId")) or ""): a
        for a in root.findall(qn("w:abstractNum"))
    }
    return root, nums, abstracts


def _abstract_for_num(document, num_id: str) -> tuple[Any | None, Any | None, str]:
    try:
        _, nums, abstracts = _numbering_roots(document)
        num = nums.get(str(num_id))
        abstract_ref = _first_child(num, "w:abstractNumId")
        abstract_id = str(abstract_ref.get(qn("w:val")) or "") if abstract_ref is not None else ""
        return num, abstracts.get(abstract_id), abstract_id
    except (AttributeError, KeyError):
        return None, None, ""


def _level_for(abstract: Any, ilvl: int, num: Any | None = None) -> Any | None:
    """Resolve a level, including a complete lvl supplied by lvlOverride."""
    if num is not None:
        override = next((item for item in num.findall(qn("w:lvlOverride"))
                         if item.get(qn("w:ilvl"), "0") == str(ilvl)), None)
        override_level = _first_child(override, "w:lvl")
        if override_level is not None:
            return override_level
    if abstract is None:
        return None
    return next((item for item in abstract.findall(qn("w:lvl"))
                 if item.get(qn("w:ilvl"), "0") == str(ilvl)), None)


def _numbering_values(paragraph, document=None) -> tuple[str, int] | None:
    """Resolve numId/ilvl without flattening the paragraph's style ancestry.

    A style is checked before its base style.  For each style, an exact ``pStyle``
    link in numbering.xml wins over that style's own numPr.  This matters for
    templates whose similarly-shaped list styles form a basedOn chain.
    """
    document = document or paragraph.part
    direct_num_pr = paragraph._p.pPr.numPr if paragraph._p.pPr is not None else None
    chain = _style_chain(paragraph)

    def values(num_pr) -> tuple[str, int | None]:
        if num_pr is None:
            return "", None
        num_id_el = _first_child(num_pr, "w:numId")
        num_id = str(num_id_el.get(qn("w:val")) or "").strip() if num_id_el is not None else ""
        ilvl_el = _first_child(num_pr, "w:ilvl")
        try:
            explicit_level = int(ilvl_el.get(qn("w:val"))) if ilvl_el is not None else None
        except (TypeError, ValueError):
            explicit_level = None
        return num_id, explicit_level

    direct_num_id, direct_level = values(direct_num_pr)

    try:
        _, nums, abstracts = _numbering_roots(document)
    except (AttributeError, KeyError):
        return (direct_num_id, max(0, direct_level or 0)) if direct_num_id else None

    # numId=0 is Word's paragraph-local cancellation.  It must not erase the
    # identity/numbering semantics of the applied paragraph style.
    direct_constraint = direct_num_id if direct_num_id not in {"", "0"} else ""

    def p_style_match(style_id: str, constrained_num_id: str = "") -> tuple[str, int] | None:
        candidates = [(constrained_num_id, nums.get(constrained_num_id))] if constrained_num_id else nums.items()
        for candidate_id, num in candidates:
            if num is None:
                continue
            abstract_ref = _first_child(num, "w:abstractNumId")
            abstract_id = str(abstract_ref.get(qn("w:val")) or "") if abstract_ref is not None else ""
            abstract = abstracts.get(abstract_id)
            for level in abstract.findall(qn("w:lvl")) if abstract is not None else ():
                p_style = _first_child(level, "w:pStyle")
                if p_style is not None and str(p_style.get(qn("w:val")) or "") == style_id:
                    return candidate_id, max(0, int(level.get(qn("w:ilvl"), "0")))
        return None

    # Even a partial direct numPr limits the lookup to its num instance.
    current_style = chain[0] if chain else None
    if current_style is not None:
        # Style identity wins over paragraph-local list formatting.  Search the
        # exact current style globally before considering direct numPr.
        match = p_style_match(str(current_style.style_id or ""))
        if match is not None:
            return match
        style_num_pr = current_style.element.pPr.numPr if current_style.element.pPr is not None else None
        style_num_id, style_level = values(style_num_pr)
        if style_num_id:
            return style_num_id, max(0, style_level or direct_level or 0)

    if direct_constraint:
        return direct_constraint, max(0, direct_level or 0)

    # Only an undefined current style may inherit, nearest base style first.
    for ancestor in chain[1:]:
        match = p_style_match(str(ancestor.style_id or ""))
        if match is not None:
            return match
        ancestor_num_pr = ancestor.element.pPr.numPr if ancestor.element.pPr is not None else None
        ancestor_num_id, ancestor_level = values(ancestor_num_pr)
        if ancestor_num_id:
            return ancestor_num_id, max(0, ancestor_level or 0)
    return None


def _resolve_numbering_format(document, num_id: str, ilvl: int) -> tuple[str, str, str, str]:
    """Resolve Word numbering format and level text when numbering.xml is available."""
    try:
        document.part.numbering_part.element
    except Exception:
        return "", "", "", ""

    num, abstract, _ = _abstract_for_num(document, num_id)
    selected_level = _level_for(abstract, ilvl, num)
    if selected_level is not None:
        num_fmt_el = _first_child(selected_level, "w:numFmt")
        level_text_el = _first_child(selected_level, "w:lvlText")
        p_style_el = _first_child(selected_level, "w:pStyle")
        fonts_el = _first_child(_first_child(selected_level, "w:rPr"), "w:rFonts")
        num_fmt = str(num_fmt_el.get(qn("w:val")) or "") if num_fmt_el is not None else ""
        level_text = (
            str(level_text_el.get(qn("w:val")) or "") if level_text_el is not None else ""
        )
        p_style = str(p_style_el.get(qn("w:val")) or "") if p_style_el is not None else ""
        symbol_font = ""
        if fonts_el is not None:
            symbol_font = str(fonts_el.get(qn("w:ascii")) or fonts_el.get(qn("w:hAnsi")) or "")
        return num_fmt, level_text, p_style, symbol_font
    return "", "", "", ""


def _resolve_numbering_indent(document, num_id: str, ilvl: int) -> tuple[int | None, int | None, int | None]:
    """Resolve left, first-line and hanging indents stored in numbering.xml."""
    try:
        root = document.part.numbering_part.element
        num = next((n for n in root.findall(qn("w:num")) if n.get(qn("w:numId")) == str(num_id)), None)
        abstract_id_el = _first_child(num, "w:abstractNumId")
        abstract_id = abstract_id_el.get(qn("w:val")) if abstract_id_el is not None else None
        abstract = next((a for a in root.findall(qn("w:abstractNum")) if a.get(qn("w:abstractNumId")) == abstract_id), None)
        level = next((lvl for lvl in abstract.findall(qn("w:lvl")) if lvl.get(qn("w:ilvl"), "0") == str(ilvl)), None)
        ind = _first_child(_first_child(level, "w:pPr"), "w:ind")
        def value(name: str) -> int | None:
            raw = ind.get(qn(f"w:{name}")) if ind is not None else None
            return int(raw) if raw is not None else None
        left = value("left")
        return (left if left is not None else value("start")), value("firstLine"), value("hanging")
    except (AttributeError, StopIteration, TypeError, ValueError):
        return None, None, None


def _paragraph_indent_twips(paragraph) -> tuple[int | None, int | None, int | None]:
    """Return effective left/first-line/hanging indents as raw Word twips."""
    sources = [paragraph._p.pPr]
    sources.extend(style.element.pPr for style in _style_chain(paragraph))
    result: list[int | None] = [None, None, None]
    for p_pr in sources:
        ind = _first_child(p_pr, "w:ind")
        if ind is None:
            continue

        def value(name: str) -> int | None:
            raw = ind.get(qn(f"w:{name}"))
            try:
                return int(raw) if raw is not None else None
            except (TypeError, ValueError):
                return None

        values = (value("left") if value("left") is not None else value("start"),
                  value("firstLine"), value("hanging"))
        result = [old if old is not None else new for old, new in zip(result, values)]
    return result[0], result[1], result[2]


def _numbering_metadata(document, num_id: str, ilvl: int) -> dict[str, Any]:
    """Capture group/restart facts which would otherwise be lost in JSON."""
    try:
        root = document.part.numbering_part.element
        num = next(n for n in root.findall(qn("w:num")) if n.get(qn("w:numId")) == str(num_id))
        abstract_el = _first_child(num, "w:abstractNumId")
        abstract_id = str(abstract_el.get(qn("w:val")) or "")
        abstract = next(a for a in root.findall(qn("w:abstractNum"))
                        if a.get(qn("w:abstractNumId")) == abstract_id)
        level = next(x for x in abstract.findall(qn("w:lvl"))
                     if x.get(qn("w:ilvl"), "0") == str(ilvl))
        start_el = _first_child(level, "w:start")
        restart_el = _first_child(level, "w:lvlRestart")
        override = next((x for x in num.findall(qn("w:lvlOverride"))
                         if x.get(qn("w:ilvl"), "0") == str(ilvl)), None)
        start_override_el = _first_child(override, "w:startOverride")
        return {
            "abstract_num_id": abstract_id,
            "numbering_start": int(start_el.get(qn("w:val"))) if start_el is not None else 1,
            "start_override": int(start_override_el.get(qn("w:val"))) if start_override_el is not None else None,
            "level_restart": int(restart_el.get(qn("w:val"))) if restart_el is not None else None,
        }
    except (AttributeError, StopIteration, TypeError, ValueError):
        return {"abstract_num_id": "", "numbering_start": None,
                "start_override": None, "level_restart": None}


def _literal_marker(text: str) -> tuple[str, str]:
    match = re.match(r"^\s*([①-⑳]|・|➢|)", str(text or ""))
    if not match:
        return "", ""
    marker = match.group(1)
    if marker == "・":
        return marker, "bullet"
    if marker in {"➢", ""}:
        return marker, "arrow"
    return marker, "circle"


def _paragraph_style(number_format: str, level_text: str, list_level: int | None,
                     left_indent_twips: int | None, style_name: str,
                     symbol_font: str = "") -> str:
    """Map native Word list semantics to the seven editor paragraph levels."""
    fmt = str(number_format or "").lower()
    marker = str(level_text or "").strip()
    style_lower = str(style_name or "").lower()
    depth = list_level if isinstance(list_level, int) else None

    is_dot = "・" in marker or "bullet" in fmt or "bullet" in style_lower or "箇条" in style_name
    is_arrow = "➢" in marker or "arrow" in style_lower or "wingdings" in symbol_font.lower()
    is_circle = "①" in marker or "②" in marker or "circle" in fmt or "囲み" in style_name
    indent = max(0, left_indent_twips or 0)
    # Native ilvl is the hierarchy. Marker shape and indentation must never
    # collapse two distinct levels which happen to use the same glyph.
    if depth is not None:
        native_level_map = ("level_1", "level_2", "level_4", "level_3", "level_5", "level_6")
        return native_level_map[min(max(depth, 0), len(native_level_map) - 1)]
    if is_arrow:
        return "level_3"
    if is_circle:
        return "level_6" if (depth is not None and depth >= 5) or indent >= 2400 else "level_4"
    if is_dot:
        return "level_5" if (depth is not None and depth >= 4) or indent >= 1920 else "level_2"
    # Multi-level definitions occasionally express every marker as a decimal
    # placeholder; in that case ilvl remains the authoritative hierarchy signal.
    if fmt and fmt != "none":
        return "level_1"
    return "level_0"


def _paragraph_structure(document, paragraph, text: str = "") -> dict[str, Any]:
    style_name = paragraph.style.name if paragraph.style is not None else ""
    word_style_id = str(paragraph.style.style_id or "") if paragraph.style is not None else ""
    base_style = paragraph.style.base_style if paragraph.style is not None else None
    word_style_based_on_id = str(base_style.style_id or "") if base_style is not None else ""
    numbering = _numbering_values(paragraph, document)
    num_id = ""
    list_level: int | None = None
    number_format = ""
    level_text = ""
    numbering_p_style = ""
    symbol_font = ""

    if numbering is not None:
        num_id, list_level = numbering
        number_format, level_text, numbering_p_style, symbol_font = _resolve_numbering_format(
            document, num_id, list_level
        )

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

    left_indent, first_line_indent, hanging_indent = _paragraph_indent_twips(paragraph)
    if numbering is not None:
        native_indents = _resolve_numbering_indent(document, num_id, list_level or 0)
        left_indent = left_indent if left_indent is not None else native_indents[0]
        first_line_indent = first_line_indent if first_line_indent is not None else native_indents[1]
        hanging_indent = hanging_indent if hanging_indent is not None else native_indents[2]
    literal_marker, literal_marker_type = _literal_marker(text)
    native_marker_type = (
        "arrow" if "wingdings" in symbol_font.lower() or "➢" in level_text or "" in level_text else
        "circle" if "decimalenclosedcircle" in number_format.lower() or "circle" in number_format.lower() else
        "bullet" if number_format.lower() == "bullet" else
        "decimal" if number_format.lower() in {"decimal", "decimalzero"} else ""
    )
    marker_type = native_marker_type if numbering is not None else literal_marker_type
    original_marker = level_text if numbering is not None else literal_marker
    if marker_type in {"bullet", "arrow"}:
        kind = "bullet"
    elif marker_type == "circle":
        kind = "numbered"
    paragraph_style = _paragraph_style(
        number_format, level_text, list_level, left_indent, style_name, symbol_font
    )
    # Literal markers are only a fallback when no native numbering semantics exist.
    if numbering is None and marker_type == "bullet":
        paragraph_style = "level_5" if (list_level or 0) >= 4 or (left_indent or 0) >= 700 else "level_2"
    elif numbering is None and marker_type == "arrow":
        paragraph_style = "level_3"
    elif numbering is None and marker_type == "circle":
        paragraph_style = "level_6" if (list_level or 0) >= 5 or (left_indent or 0) >= 700 else "level_4"
    metadata = (_numbering_metadata(document, num_id, list_level or 0) if numbering else
                {"abstract_num_id": "", "numbering_start": None,
                 "start_override": None, "level_restart": None})
    return {
        "style": style_name,
        "word_style_id": word_style_id,
        "word_style_name": style_name,
        "word_style_based_on_id": word_style_based_on_id,
        "kind": kind,
        "list_level": list_level,
        "native_ilvl": list_level,
        "num_id": num_id,
        "list_group_id": "",
        "number_format": number_format,
        "level_text": level_text,
        "numbering_p_style": numbering_p_style,
        "symbol_font": symbol_font,
        "original_marker": original_marker or level_text,
        "marker_type": marker_type,
        **metadata,
        "paragraph_style": paragraph_style,
        "left_indent_twips": left_indent,
        "first_line_indent_twips": first_line_indent,
        "hanging_indent_twips": hanging_indent,
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


def _strip_literal_paragraph_marker(text: str, paragraph_style: str) -> str:
    """Remove a literal list marker only after Word properties identified its level."""
    patterns = {
        "level_1": r"^\s*[（(][0-9０-９]+[）)]\s*",
        "level_2": r"^\s*・\s*",
        "level_3": r"^\s*➢\s*",
        "level_4": r"^\s*[①-⑳]\s*",
        "level_5": r"^\s*・\s*",
        "level_6": r"^\s*[①-⑳]\s*",
    }
    pattern = patterns.get(paragraph_style)
    return re.sub(pattern, "", text, count=1) if pattern else text


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
            structure = _paragraph_structure(document, paragraph, text)
            marker = str(structure.get("original_marker") or "")
            if structure.get("num_id"):
                # A Word num instance is the authoritative numbering-group boundary.
                structure["list_group_id"] = f"word:{structure['num_id']}"
            elif structure.get("marker_type") == "circle":
                # Literal circled numbers have no numId.  A visible return to ①
                # after ②+ is Word's strongest available restart signal.
                state_by_style = section.setdefault("_literal_group_state", {})
                state = state_by_style.setdefault(
                    structure["paragraph_style"], {"group": 1, "last": 0}
                )
                value = ord(marker[0]) - 0x2460 + 1 if marker and "①" <= marker[0] <= "⑳" else 0
                if value == 1 and state["last"] > 1:
                    state["group"] += 1
                state["last"] = value or state["last"]
                structure["list_group_id"] = (
                    f"literal:{current_section_id}:{structure['paragraph_style']}:{state['group']}"
                )
            text = _strip_literal_paragraph_marker(text, structure["paragraph_style"])
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
        section.pop("_literal_group_state", None)
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
