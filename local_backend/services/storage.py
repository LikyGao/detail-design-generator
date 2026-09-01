from __future__ import annotations

import base64
import os
from pathlib import Path


class FileStorage:
    """Small filesystem implementation of the Dify plugin KV interface."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.kv = self.root / ".kv"
        self.kv.mkdir(exist_ok=True)

    def _path(self, key: str) -> Path:
        name = base64.urlsafe_b64encode(key.encode()).decode().rstrip("=")
        return self.kv / name

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise KeyError("key not found")
        return path.read_bytes()

    def set(self, key: str, value: bytes) -> None:
        path = self._path(key)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(value)
        os.replace(temporary, path)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
