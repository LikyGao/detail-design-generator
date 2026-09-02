from __future__ import annotations


def calculate_paragraph_prefix(paragraph_style: str, counters: dict,
                               list_group_id: str | None = None,
                               marker_type: str | None = None) -> str:
    """Return the next marker, scoped to its explicit numbering group."""
    level = int(paragraph_style.rsplit("_", 1)[1])
    key = (str(list_group_id), level) if list_group_id else level
    if level in (1, 4, 6):
        counters[key] = counters.get(key, 0) + 1
        if not list_group_id:
            for deeper in tuple(k for k in counters if isinstance(k, int) and k > level):
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
