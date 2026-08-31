from __future__ import annotations


def calculate_paragraph_prefix(paragraph_style: str, counters: dict[int, int]) -> str:
    """Return the next deterministic marker for a paragraph within one section."""
    level = int(paragraph_style.rsplit("_", 1)[1])
    if level in (1, 4, 6):
        counters[level] = counters.get(level, 0) + 1
        for deeper in tuple(key for key in counters if key > level):
            counters.pop(deeper, None)
    if level == 1:
        return f"（{counters[level]}）"
    if level in (2, 5):
        return "・"
    if level == 3:
        return "➢"
    if level in (4, 6):
        value = counters[level]
        return chr(0x2460 + value - 1) if 1 <= value <= 20 else f"({value})"
    return ""
