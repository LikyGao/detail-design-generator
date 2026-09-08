from __future__ import annotations

import importlib
import json
from pathlib import Path

from local_backend.desktop import DesktopApi
from local_backend.services.staging import build_project_archive, stage_bytes, staged_path


def _load_patch_temporarily():
    original_save = DesktopApi.save_staged_file
    original_open = DesktopApi.open_project_file
    patch = importlib.import_module("local_backend.native_dialog_patch")
    return patch, original_save, original_open


def test_word_save_uses_native_path_chooser_without_pywebview_dialog(monkeypatch, tmp_path):
    patch, original_save, original_open = _load_patch_temporarily()
    try:
        target = tmp_path / "generated.docx"
        monkeypatch.setattr(patch, "_choose_path", lambda *_args, **_kwargs: target)

        api = DesktopApi()
        # Intentionally leave main_window=None. The patched implementation must not
        # depend on pywebview.Window.create_file_dialog from the FastAPI worker thread.
        token, source = stage_bytes(b"PK-native-word", ".docx")
        result = api.save_staged_file(token, "generated.docx", "word", True)

        assert result["saved"] is True
        assert Path(result["path"]) == target.resolve()
        assert target.read_bytes() == b"PK-native-word"
        assert not source.exists()
    finally:
        DesktopApi.save_staged_file = original_save
        DesktopApi.open_project_file = original_open


def test_project_open_uses_native_path_chooser_without_pywebview_dialog(monkeypatch, tmp_path):
    patch, original_save, original_open = _load_patch_temporarily()
    try:
        source = tmp_path / "case.ddgproj"
        source.write_bytes(
            build_project_archive({"format": "detail-design-generator-project", "doc": {"x": 9}})
        )
        monkeypatch.setattr(patch, "_choose_path", lambda *_args, **_kwargs: source)

        api = DesktopApi()
        result = api.open_project_file()
        assert result["opened"] is True
        staged = staged_path(str(result["token"]), ".json")
        payload = json.loads(staged.read_text(encoding="utf-8"))
        assert payload["doc"]["x"] == 9
    finally:
        DesktopApi.save_staged_file = original_save
        DesktopApi.open_project_file = original_open


def test_win32_common_dialog_functions_are_used_instead_of_pywebview_gui_calls():
    source = Path("local_backend/native_dialog_patch.py").read_text(encoding="utf-8")
    assert "GetSaveFileNameW" in source
    assert "GetOpenFileNameW" in source
    assert "DesktopApi.save_staged_file = save_staged_file_native" in source
    assert "DesktopApi.open_project_file = open_project_file_native" in source
