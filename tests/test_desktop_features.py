from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from local_backend.app import create_app
from local_backend.desktop import BASE_URL, DesktopApi, PREVIEW_WINDOW_TITLE
from local_backend.services.staging import (
    build_project_archive,
    read_project_archive,
    remove_staged_file,
    stage_bytes,
    staged_path,
)


def test_preview_state_round_trip_and_detached_shell(tmp_path):
    client = TestClient(create_app(data_root=tmp_path))
    payload = {
        "html": '<div class="word-page">preview</div>',
        "css": ".word-page{width:210mm}",
        "revision": 12,
        "nodeId": "n-1",
        "blockId": "b-1",
        "updatedAt": 12345,
    }
    written = client.post("/api/preview-state", json=payload)
    assert written.status_code == 200
    loaded = client.get("/api/preview-state")
    assert loaded.status_code == 200
    assert loaded.json()["html"] == payload["html"]
    assert loaded.json()["css"] == payload["css"]
    assert loaded.json()["revision"] == 12

    shell = client.get("/preview-window")
    assert shell.status_code == 200
    assert 'id="standalonePreview"' in shell.text
    assert "/api/preview-state" in shell.text
    assert "setInterval(sync, 250)" in shell.text


def test_project_stage_preserves_image_data(tmp_path):
    client = TestClient(create_app(data_root=tmp_path))
    project = {
        "format": "detail-design-generator-project",
        "schema_version": 1,
        "phase": "edit",
        "doc": {
            "document_type": "network",
            "chapters": [
                {
                    "id": "n1",
                    "blocks": [
                        {
                            "type": "figure",
                            "fileName": "device.png",
                            "imageData": "data:image/png;base64,AAAA",
                        }
                    ],
                }
            ],
        },
    }
    response = client.post(
        "/api/project/stage",
        json={"project": project, "suggested_name": "案件テスト.ddgproj"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["filename"] == "案件テスト.ddgproj"
    path = staged_path(data["token"], ".ddgproj")
    try:
        restored = read_project_archive(path)
        assert restored == project
        assert restored["doc"]["chapters"][0]["blocks"][0]["imageData"].startswith("data:image/png")
    finally:
        remove_staged_file(path)


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class _FakeWindow:
    def __init__(self, dialog_result=None):
        self.dialog_result = dialog_result
        self.dialog_calls = []
        self.evaluated = []
        self.events = SimpleNamespace(closed=_Event())

    def create_file_dialog(self, *args, **kwargs):
        self.dialog_calls.append((args, kwargs))
        return self.dialog_result

    def evaluate_js(self, script):
        self.evaluated.append(script)


def _install_fake_webview(monkeypatch, created_windows, dialog_result=None):
    class FileDialog:
        SAVE = "SAVE"
        OPEN = "OPEN"

    def create_window(title, url, **kwargs):
        window = _FakeWindow(dialog_result=dialog_result)
        created_windows.append((title, url, kwargs, window))
        return window

    fake = SimpleNamespace(FileDialog=FileDialog, create_window=create_window)
    monkeypatch.setitem(sys.modules, "webview", fake)
    return fake


def test_desktop_api_creates_one_preview_window_and_notifies_main_on_close(monkeypatch):
    created = []
    _install_fake_webview(monkeypatch, created)
    main = _FakeWindow()
    api = DesktopApi()
    api.bind_main_window(main)

    first = api.open_preview_window()
    second = api.open_preview_window()
    assert first == {"opened": True, "existing": False}
    assert second == {"opened": True, "existing": True}
    assert len(created) == 1
    assert created[0][0] == PREVIEW_WINDOW_TITLE
    assert created[0][1] == BASE_URL + "/preview-window"

    preview = created[0][3]
    assert preview.events.closed.handlers
    preview.events.closed.handlers[0]()
    assert api.preview_window is None
    assert any("__ddgDesktopPreviewClosed" in script for script in main.evaluated)


def test_native_save_dialog_writes_staged_word(monkeypatch, tmp_path):
    target = tmp_path / "output.docx"
    created = []
    _install_fake_webview(monkeypatch, created)
    main = _FakeWindow(dialog_result=(str(target),))
    api = DesktopApi()
    api.bind_main_window(main)

    token, source = stage_bytes(b"PK-test-docx", ".docx")
    result = api.save_staged_file(token, "output.docx", "word", True)
    assert result["saved"] is True
    assert target.read_bytes() == b"PK-test-docx"
    assert not source.exists()
    assert main.dialog_calls


def test_project_save_reuses_current_path_until_save_as(monkeypatch, tmp_path):
    first_target = tmp_path / "first.ddgproj"
    created = []
    _install_fake_webview(monkeypatch, created)
    main = _FakeWindow(dialog_result=(str(first_target),))
    api = DesktopApi()
    api.bind_main_window(main)

    token1, _ = stage_bytes(build_project_archive({"doc": {"value": 1}}), ".ddgproj")
    first = api.save_staged_file(token1, "first.ddgproj", "project", False)
    assert first["saved"] is True
    assert len(main.dialog_calls) == 1

    token2, _ = stage_bytes(build_project_archive({"doc": {"value": 2}}), ".ddgproj")
    second = api.save_staged_file(token2, "first.ddgproj", "project", False)
    assert second["saved"] is True
    assert len(main.dialog_calls) == 1
    assert read_project_archive(first_target)["doc"]["value"] == 2


def test_open_project_uses_native_dialog_and_stages_json(monkeypatch, tmp_path):
    source = tmp_path / "loaded.ddgproj"
    source.write_bytes(build_project_archive({"format": "detail-design-generator-project", "doc": {"x": 7}}))
    created = []
    _install_fake_webview(monkeypatch, created)
    main = _FakeWindow(dialog_result=(str(source),))
    api = DesktopApi()
    api.bind_main_window(main)

    result = api.open_project_file()
    assert result["opened"] is True
    assert result["filename"] == "loaded.ddgproj"
    staged = staged_path(str(result["token"]), ".json")
    try:
        payload = json.loads(staged.read_text(encoding="utf-8"))
        assert payload["doc"]["x"] == 7
    finally:
        remove_staged_file(staged)
