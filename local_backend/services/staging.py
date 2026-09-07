"""Temporary file staging shared by the local HTTP API and pywebview shell."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

_STAGE_ROOT = Path(tempfile.gettempdir()) / "detail-design-generator-stage"
_STAGE_ROOT.mkdir(parents=True, exist_ok=True)


def _new_token() -> str:
    return uuid.uuid4().hex


def _safe_token(token: str) -> str:
    value = str(token or "").strip().lower()
    if len(value) != 32 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("無効な一時ファイル識別子です。")
    return value


def stage_bytes(content: bytes, suffix: str) -> tuple[str, Path]:
    suffix = suffix if suffix.startswith(".") else "." + suffix
    token = _new_token()
    path = _STAGE_ROOT / f"{token}{suffix}"
    path.write_bytes(content)
    return token, path


def staged_path(token: str, suffix: str) -> Path:
    suffix = suffix if suffix.startswith(".") else "." + suffix
    path = _STAGE_ROOT / f"{_safe_token(token)}{suffix}"
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    return path


def consume_staged_file(token: str, suffix: str) -> Path:
    return staged_path(token, suffix)


def remove_staged_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def build_project_archive(project: dict[str, Any]) -> bytes:
    """Create the single-file .ddgproj container.

    Images are currently already stored by the editor as data URLs under block.imageData,
    so keeping project.json intact preserves text, tables, figures and all Step 1/2/3 state.
    """
    payload = json.dumps(project, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project.json", payload)
    return buffer.getvalue()


def read_project_archive(path: str | os.PathLike[str]) -> dict[str, Any]:
    source = Path(path)
    if not source.exists() or not source.is_file():
        raise ValueError("案件ファイルが見つかりません。")
    try:
        with zipfile.ZipFile(source, "r") as archive:
            if "project.json" not in archive.namelist():
                raise ValueError("案件ファイルに project.json がありません。")
            raw = archive.read("project.json")
        data = json.loads(raw.decode("utf-8"))
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("案件ファイルを読み込めません。") from exc
    if not isinstance(data, dict):
        raise ValueError("案件ファイルの形式が正しくありません。")
    return data
