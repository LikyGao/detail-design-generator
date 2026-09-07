"""In-memory state shared between the editor window and detached preview window."""
from __future__ import annotations

from threading import Lock
from typing import Any

_lock = Lock()
_state: dict[str, Any] = {
    "html": "",
    "css": "",
    "revision": 0,
    "nodeId": None,
    "blockId": None,
    "updatedAt": 0,
}


def update_preview_state(payload: dict[str, Any]) -> dict[str, Any]:
    global _state
    with _lock:
        revision = int(payload.get("revision") or (_state.get("revision", 0) + 1))
        _state = {
            "html": str(payload.get("html") or ""),
            "css": str(payload.get("css") or _state.get("css") or ""),
            "revision": revision,
            "nodeId": payload.get("nodeId"),
            "blockId": payload.get("blockId"),
            "updatedAt": payload.get("updatedAt") or 0,
        }
        return dict(_state)


def get_preview_state() -> dict[str, Any]:
    with _lock:
        return dict(_state)
