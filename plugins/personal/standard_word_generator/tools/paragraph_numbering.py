from __future__ import annotations


PARAGRAPH_STYLE_NATIVE_ILVL = {
    "level_1": 0,
    "level_2": 1,
    "level_4": 2,
    "level_3": 3,
    "level_5": 4,
    "level_6": 5,
}


def calculate_paragraph_prefix(paragraph_style: str, counters: dict,
                               list_group_id: str | None = None,
                               marker_type: str | None = None,
                               numbering_start: int | None = None) -> str:
    """Return the next marker, scoped to its explicit numbering group."""
    level = int(paragraph_style.rsplit("_", 1)[1])
    key = (str(list_group_id), level) if list_group_id else level
    if level in (1, 4, 6):
        try:
            initial = max(1, int(numbering_start)) - 1
        except (TypeError, ValueError):
            initial = 0
        counters[key] = counters.get(key, initial) + 1
        # A level-1 item starts a new hierarchy even when the generator gives
        # that item a synthetic per-node group. Reset only fallback (integer)
        # child counters; tuple keys belong to real independent list groups.
        current_ilvl = PARAGRAPH_STYLE_NATIVE_ILVL.get(paragraph_style, -1)
        if not list_group_id or current_ilvl == 0:
            for deeper in tuple(
                key for key in counters
                if isinstance(key, int)
                and PARAGRAPH_STYLE_NATIVE_ILVL.get(f"level_{key}", -1) > current_ilvl
            ):
                counters.pop(deeper, None)
    if marker_type == "bullet":
        return "・"
    if marker_type == "arrow":
        return "➢"
    if level == 1:
        return f"（{counters[key]}）"
    if level in (2, 5):
        return "・"
    if level == 3:
        return "➢"
    if level in (4, 6):
        value = counters[key]
        return chr(0x2460 + value - 1) if 1 <= value <= 20 else f"({value})"
    return ""
